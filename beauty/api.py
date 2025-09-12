# beauty/api.py
from django.http import JsonResponse, HttpResponseNotAllowed, HttpResponseBadRequest
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.shortcuts import get_object_or_404
from django.db import transaction
from datetime import timedelta
import json

from main.models import Deal, Employee
from .models import Booking, Resource
from beauty.models import Booking, Resource, Service, DealLine  

def staff_only(user): 
    return user.is_staff or user.is_superuser

def parse_json(request):
    try:
        return json.loads(request.body.decode("utf-8"))
    except Exception:
        return None

def to_aware(dt_str):
    dt = parse_datetime(dt_str)  # парсить і з часовою зоною, і без
    if not dt:
        return None
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt

def iso(dt):
    if not dt:
        return None
    return timezone.localtime(dt).isoformat()

def booking_to_event(b: Booking):
    title = f"{b.deal.client.name if b.deal and b.deal.client else 'Клієнт'}"
    if hasattr(b.deal, "title") and b.deal.title:
        title = f"{b.deal.title} — {title}"
    return {
        "id": b.pk,
        "title": title,
        "start": iso(b.start_at),
        "end":   iso(b.end_at),
        "backgroundColor": b.color or "#88CCEE",
        "borderColor": b.color or "#88CCEE",
        "url": f"/deals/{b.deal.pk}/" if b.deal_id else None,
        "extendedProps": {
            "client": b.deal.client.name if b.deal and b.deal.client else "",
            "master": b.master.full_name if hasattr(b.master, "full_name") else b.master.user.get_username(),
            "resource": b.resource.name if b.resource_id else "",
        }
    }

@login_required
@require_GET
def calendar_events(request):
    """
    FullCalendar викликає GET /api/calendar/events?start=...&end=...&master=optional
    start/end — ISO строки. Ми віддаємо події у вікні.
    """
    start = request.GET.get("start")
    end   = request.GET.get("end")
    master = request.GET.get("master")  # optional filter

    if not start or not end:
        return HttpResponseBadRequest("start/end required")

    qs = Booking.objects.select_related("deal__client", "master__user", "resource") \
                        .filter(start_at__lt=end, end_at__gt=start)
    if master:
        qs = qs.filter(master_id=master)

    events = [booking_to_event(b) for b in qs]
    return JsonResponse(events, safe=False)


@login_required
@user_passes_test(staff_only)
@require_POST
def booking_create(request):
    """
    Підтримує два режими:
    1) deal_id + master_id [+ duration_min] → створюємо Booking для існуючої угоди
    2) client_id + service_id + master_id [+ duration_min] → створюємо Deal (+ DealLine) і Booking
    """
    data = parse_json(request)
    if not data:
        return HttpResponseBadRequest("Invalid JSON")

    start_at = to_aware(data.get("start_at"))
    if not start_at:
        return HttpResponseBadRequest("start_at required")

    duration_min = int(data.get("duration_min") or 0)

    # ---- режим 1: існуюча угода ----
    deal = None
    if data.get("deal_id"):
        deal = get_object_or_404(Deal, pk=data["deal_id"])

    # ---- режим 2: створення угоди з клієнта/послуги ----
    if not deal:
        client_id = data.get("client_id")
        service_id = data.get("service_id")
        if not (client_id and service_id):
            return HttpResponseBadRequest("Provide deal_id OR (client_id and service_id)")

        client = get_object_or_404(Client, pk=client_id)
        service = get_object_or_404(Service, pk=service_id)

        # якщо duration не передали — беремо з послуги
        if duration_min <= 0:
            duration_min = int(getattr(service, "duration_min", 30) or 30)

        # створюємо Deal + DealLine
        with transaction.atomic():
            deal = Deal.objects.create(
                client=client,
                title=getattr(service, "name", "Послуга"),
                amount=getattr(service, "price", 0) or 0,
                status="in_progress",
                owner=request.user,
                notes=data.get("note", "")
            )
            # якщо у тебе інше ім'я моделі/полів — підправ нижче
            DealLine.objects.create(
                deal=deal,
                service=service,
                quantity=1,
                unit_price=getattr(service, "price", 0) or 0,
            )

    master = get_object_or_404(Employee, pk=data["master_id"])
    resource = None
    if data.get("resource_id"):
        resource = get_object_or_404(Resource, pk=data["resource_id"])

    if duration_min <= 0:
        # fallback: якщо нема ні від послуги, ні з payload — використовуємо автологіку в твоєму Booking.save()
        # але краще явно задати end_at з duration_min
        duration_min = 30

    end_at = start_at + timedelta(minutes=duration_min)

    # перевірка конфліктів
    with transaction.atomic():
        conflict = Booking.objects.select_for_update().filter(
            master=master, start_at__lt=end_at, end_at__gt=start_at
        )
        if conflict.exists():
            return JsonResponse({"error": "conflict", "message": "Час зайнято"}, status=409)

        b = Booking.objects.create(
            deal=deal,
            start_at=start_at,
            end_at=end_at,
            master=master,
            resource=resource,
            note=data.get("note", ""),
            color="#88CCEE",
        )

    return JsonResponse(booking_to_event(b), status=201)


@login_required
@user_passes_test(staff_only)
def booking_update(request, pk):
    """
    PATCH /api/calendar/bookings/<id>
    {
      "start_at": "2025-09-17T11:00",   # optional
      "end_at": "2025-09-17T11:30",     # optional
      "duration_min": 30,               # optional (якщо нема end_at)
      "master_id": 7,                   # optional
      "resource_id": null,              # optional
      "note": "..."                     # optional
    }
    DELETE /api/calendar/bookings/<id>
    """
    b = get_object_or_404(Booking.objects.select_related("master"), pk=pk)

    if request.method == "DELETE":
        b.delete()
        return JsonResponse({"ok": True})

    if request.method not in ("PATCH", "POST"):  # деякі браузери не шлють PATCH з форм
        return HttpResponseNotAllowed(["PATCH", "DELETE"])

    data = parse_json(request)
    if not data:
        return HttpResponseBadRequest("Invalid JSON")

    start_at = data.get("start_at")
    end_at = data.get("end_at")
    duration = data.get("duration_min")

    if start_at:
        start_at = timezone.make_aware(timezone.datetime.fromisoformat(start_at))
        b.start_at = start_at

    if end_at:
        end_at = timezone.make_aware(timezone.datetime.fromisoformat(end_at))
        b.end_at = end_at
    elif duration and b.start_at:
        b.end_at = b.start_at + timedelta(minutes=int(duration))

    if "master_id" in data:
        b.master = get_object_or_404(Employee, pk=data["master_id"])
    if "resource_id" in data:
        b.resource = get_object_or_404(Resource, pk=data["resource_id"]) if data["resource_id"] else None
    if "note" in data:
        b.note = data["note"]

    # конфлікти
    with transaction.atomic():
        conflict = Booking.objects.select_for_update().filter(
            master=b.master,
            start_at__lt=b.end_at,
            end_at__gt=b.start_at
        ).exclude(pk=b.pk)
        if conflict.exists():
            return JsonResponse({"error": "conflict", "message": "Час зайнято"}, status=409)
        b.save()

    return JsonResponse(booking_to_event(b), status=200)
