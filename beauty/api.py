# beauty/api.py
from django.http import JsonResponse, HttpResponseNotAllowed, HttpResponseBadRequest
from django.views.decorators.http import require_GET, require_POST
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.shortcuts import get_object_or_404
from django.db import transaction
from datetime import timedelta
import json

from main.models import Deal, Employee, Client
from beauty.models import Booking, Resource, Service, DealLine  # усе з beauty.models

# ---- helpers ----

def staff_only(user):
    return user.is_staff or user.is_superuser

def parse_json(request):
    try:
        return json.loads(request.body.decode("utf-8"))
    except Exception:
        return None

def to_aware(dt_str):
    """
    Приймає ISO-строку. Повертає aware-datetime в поточній TZ.
    """
    dt = parse_datetime(dt_str)  # парсить як з TZ, так і без
    if not dt:
        return None
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt

def iso(dt):
    return timezone.localtime(dt).isoformat() if dt else None

def booking_to_event(b: Booking):
    """
    Перетворює Booking → FullCalendar event dict.
    """
    client_name = b.deal.client.name if (b.deal_id and b.deal.client_id) else ""
    deal_title = getattr(b.deal, "title", "") if b.deal_id else ""
    title = deal_title or client_name or "Запис"

    # витягнемо першу послугу з угоди (якщо є)
    first_line = None
    try:
        first_line = b.deal.lines.select_related("service").first()
    except Exception:
        pass

    master_name = None
    if b.master_id:
        master_name = getattr(b.master, "full_name", None) or b.master.user.get_username()

    return {
        "id": b.pk,
        "title": title,
        "start": iso(b.start_at),
        "end":   iso(b.end_at),
        "backgroundColor": b.color or "#88CCEE",
        "borderColor": b.color or "#88CCEE",
        "url": f"/deals/{b.deal.pk}/" if b.deal_id else None,
        "extendedProps": {
            "client": client_name,
            "master": master_name,
            "resource": b.resource.name if b.resource_id else "",
            "status": b.status,
            "allow_unskilled": b.allow_unskilled,
            "service": first_line.service.name if first_line else "",
        },
    }

# ---- endpoints ----

@login_required
@require_GET
def calendar_events(request):
    """
    GET /api/calendar/events?start=...&end=...&master=optional
    FullCalendar дає ISO-інтервал для завантаження подій.
    """
    start_str = request.GET.get("start")
    end_str   = request.GET.get("end")
    master_id = request.GET.get("master")  # optional

    if not start_str or not end_str:
        return HttpResponseBadRequest("start/end required")

    # FullCalendar вже дає ISO з TZ → можна фільтрувати напряму по строках,
    # але безпечніше привести до aware-datetime.
    start_dt = to_aware(start_str)
    end_dt   = to_aware(end_str)
    if not start_dt or not end_dt:
        return HttpResponseBadRequest("Invalid start/end")

    qs = (Booking.objects
          .select_related("deal__client", "master__user", "resource")
          .filter(start_at__lt=end_dt, end_at__gt=start_dt))

    if master_id:
        qs = qs.filter(master_id=master_id)

    events = [booking_to_event(b) for b in qs]
    return JsonResponse(events, safe=False)


@login_required
@user_passes_test(staff_only)
@require_POST
def booking_create(request):
    """
    POST /api/calendar/bookings/
    Режими:
      1) deal_id + [master_id] [+ duration_min] → Booking для існуючої угоди
      2) client_id + service_id + [master_id] [+ duration_min] → створюємо Deal(+DealLine) і Booking

    Також приймає:
      - start_at (ISO, required)
      - resource_id (optional)
      - note (optional)
      - allow_unskilled (bool, optional)
    """
    data = parse_json(request)
    if not data:
        return HttpResponseBadRequest("Invalid JSON")

    start_at = to_aware(data.get("start_at"))
    if not start_at:
        return HttpResponseBadRequest("start_at required")

    duration_min = int(data.get("duration_min") or 0)
    allow_unskilled = bool(data.get("allow_unskilled"))

    # master може бути None (запис без майстра)
    master = None
    if "master_id" in data and data.get("master_id") not in (None, "", "null"):
        master = get_object_or_404(Employee, pk=data["master_id"])

    resource = None
    if data.get("resource_id"):
        resource = get_object_or_404(Resource, pk=data["resource_id"])

    # ---- визначаємо угоду ----
    deal = None
    service = None

    if not deal:
        client_id = data.get("client_id")
        client_name = (data.get("client_name") or "").strip()
        client_phone = (data.get("client_phone") or "").strip()
        service_id = data.get("service_id")

        if not service_id:
            return HttpResponseBadRequest("service_id required")

        service = get_object_or_404(Service, pk=service_id)

        # визначаємо клієнта:
        if client_id:
            client = get_object_or_404(Client, pk=client_id)
        else:
            if not client_name:
                return HttpResponseBadRequest("client_id or client_name required")
            # створюємо мінімального клієнта
            client = Client.objects.create(
                name=client_name,
                phone=client_phone,
                owner=request.user  # якщо хочеш прив’язати
            )

        if duration_min <= 0:
            duration_min = int(getattr(service, "duration_min", 30) or 30)

        with transaction.atomic():
            deal = Deal.objects.create(
                client=client,
                title=getattr(service, "name", "Послуга"),
                amount=getattr(service, "base_price", 0) or 0,
                status="in_progress",
                owner=request.user,
                notes=data.get("note", "")
            )
            DealLine.objects.create(
                deal=deal,
                service=service,
                quantity=1,
                unit_price=getattr(service, "base_price", 0) or 0,
            )
    # ---- валідація навички майстра (якщо заданий і є service) ----
    if master and service and not allow_unskilled:
        if not master.services.filter(pk=service.pk).exists():
            return JsonResponse({"error": "skill", "message": "Майстер не має цієї навички"}, status=422)

    # ---- статус за замовчуванням ----
    status = "confirmed"
    if allow_unskilled or master is None:
        status = "tentative"

    # ---- кінець запису ----
    end_at = start_at + timedelta(minutes=duration_min) if duration_min > 0 else None

    # ---- перевірка конфліктів (тільки якщо master заданий) ----
    with transaction.atomic():
        if master:
            overlap = (Booking.objects
                       .select_for_update()
                       .filter(master=master, start_at__lt=end_at, end_at__gt=start_at))
            if overlap.exists():
                return JsonResponse({"error": "conflict", "message": "Час зайнято"}, status=409)

        b = Booking.objects.create(
            deal=deal,
            start_at=start_at,
            end_at=end_at,           # якщо None — порахується у Booking.save()
            master=master,           # може бути None
            resource=resource,
            note=data.get("note", ""),
            color="#88CCEE",
            status=status,
            allow_unskilled=allow_unskilled,
        )

    return JsonResponse(booking_to_event(b), status=201)


@login_required
@user_passes_test(staff_only)
def booking_update(request, pk):
    """
    PATCH /api/calendar/bookings/<id>
      {
        "start_at": "2025-09-17T11:00:00+02:00",  # optional
        "end_at":   "2025-09-17T11:30:00+02:00",  # optional
        "duration_min": 30,                       # optional (якщо нема end_at)
        "master_id": 7 | null,                    # optional (null → без майстра)
        "resource_id": 3 | null,                  # optional
        "note": "...",                            # optional
        "allow_unskilled": true|false,            # optional
        "status": "tentative|confirmed|cancelled" # optional
      }

    DELETE /api/calendar/bookings/<id>
    """
    b = get_object_or_404(Booking.objects.select_related("deal", "master__user"), pk=pk)

    if request.method == "DELETE":
        b.delete()
        return JsonResponse({"ok": True})

    if request.method not in ("PATCH", "POST"):  # деякі клієнти шлють POST як PATCH
        return HttpResponseNotAllowed(["PATCH", "DELETE"])

    data = parse_json(request)
    if not data:
        return HttpResponseBadRequest("Invalid JSON")

    # оновлення базових полів
    start_at_str = data.get("start_at")
    end_at_str   = data.get("end_at")
    duration_min = data.get("duration_min")

    if start_at_str:
        b.start_at = to_aware(start_at_str)

    if end_at_str:
        b.end_at = to_aware(end_at_str)
    elif duration_min and b.start_at:
        b.end_at = b.start_at + timedelta(minutes=int(duration_min))

    # master може бути None
    if "master_id" in data:
        master_id = data.get("master_id")
        b.master = get_object_or_404(Employee, pk=master_id) if master_id else None

    if "resource_id" in data:
        res_id = data.get("resource_id")
        b.resource = get_object_or_404(Resource, pk=res_id) if res_id else None

    if "note" in data:
        b.note = data["note"] or ""

    if "allow_unskilled" in data:
        b.allow_unskilled = bool(data["allow_unskilled"])

    if "status" in data:
        if data["status"] in {"tentative", "confirmed", "cancelled"}:
            b.status = data["status"]

    # перевірка навички (якщо master є і є service у deal)
    service_line = b.deal.lines.select_related("service").first()
    service = service_line.service if service_line else None
    if b.master_id and service and not b.allow_unskilled:
        if not b.master.services.filter(pk=service.pk).exists():
            return JsonResponse({"error": "skill", "message": "Майстер не має цієї навички"}, status=422)

    # конфлікти (тільки якщо master є)
    with transaction.atomic():
        if b.master_id:
            overlap = (Booking.objects
                       .select_for_update()
                       .filter(master=b.master, start_at__lt=b.end_at, end_at__gt=b.start_at)
                       .exclude(pk=b.pk))
            if overlap.exists():
                return JsonResponse({"error": "conflict", "message": "Час зайнято"}, status=409)
        b.save()

    return JsonResponse(booking_to_event(b), status=200)
