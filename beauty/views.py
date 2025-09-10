from django.http import JsonResponse
from django.utils import timezone
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods
from main.models import Deal  # твої існуючі моделі
from .models import DealLine, Booking
from .forms import DealLineForm, BookingForm

@login_required
@require_http_methods(["POST"])
def line_delete(request, pk):
    line = get_object_or_404(DealLine, pk=pk)
    deal_id = line.deal_id
    line.delete()
    messages.success(request, _("Рядок видалено"))
    return redirect("deal_detail", pk=deal_id)

@login_required
def deal_lines_manage(request, pk):
    """
    Рендеримо сторінку Deal (твій шаблон), додаємо форму для рядків та букінг.
    Можна викликати з detail-в’юшки або зробити маленьку обгортку.
    """
    deal = get_object_or_404(Deal, pk=pk)
    attachments = deal.attachments.all() if hasattr(deal, "attachments") else []

    # --- форма рядка угоди ---
    if request.method == "POST" and request.POST.get("form_type") == "line":
        line_form = DealLineForm(request.POST)
        if line_form.is_valid():
            line = line_form.save(commit=False)
            line.deal = deal
            line.save()
            messages.success(request, _("Послугу додано до угоди"))
            return redirect("deal_detail", pk=deal.pk)
        booking_form = BookingForm(instance=getattr(deal, "booking", None))
    # --- форма букінгу ---
    elif request.method == "POST" and request.POST.get("form_type") == "booking":
        booking = getattr(deal, "booking", None)
        booking_form = BookingForm(request.POST, instance=booking)
        if booking_form.is_valid():
            b = booking_form.save(commit=False)
            b.deal = deal
            b.save()  # сам порахує end_at з тривалостей послуг
            messages.success(request, _("Запис збережено"))
            return redirect("deal_detail", pk=deal.pk)
        line_form = DealLineForm()
    else:
        line_form = DealLineForm()
        booking_form = BookingForm(instance=getattr(deal, "booking", None))

    ctx = {
        "deal": deal,
        "attachments": attachments,
        "line_form": line_form,
        "booking_form": booking_form,
        "lines": deal.lines.select_related("service").all() if hasattr(deal, "lines") else [],
    }
    # Використаємо твій існуючий шаблон deal_detail.html, додавши туди секції (див. розділ 4)
    return render(request, "main/deal_detail.html", ctx)


@login_required
def calendar_feed(request):
    """
    FullCalendar запитує події в діапазоні [start, end).
    Повертаємо масив {title, start, end, color, url}.
    """
    start = request.GET.get("start")
    end = request.GET.get("end")

    qs = Booking.objects.select_related("deal", "deal__client", "master")
    if start and end:
        qs = qs.filter(start_at__lt=end, end_at__gt=start)

    events = []
    for b in qs:
        title = f"{b.deal.client.name} — {b.deal.title} ({b.master.user.username})"
        events.append({
            "id": str(b.pk),
            "title": title,
            "start": b.start_at.isoformat(),
            "end":   b.end_at.isoformat() if b.end_at else None,
            "color": b.color or None,
            "url":   f"/deals/{b.deal_id}/",  # на деталі угоди
        })
    return JsonResponse(events, safe=False)