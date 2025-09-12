from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import redirect, render, get_object_or_404
from django.views.decorators.http import require_http_methods, require_POST
from django.contrib.auth.models import User
from django.contrib import messages
from django.db.models import Avg, Count, Q, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone
from django import forms
from django.core.paginator import Paginator
from datetime import datetime, timedelta
from .forms import ActivityForm, ClientForm, DealForm, EmployeeForm
from .models import Activity, Employee, PerformanceReview, Client, Deal, DealAttachment
import json
from beauty.models import DealLine, Booking, Service, Resource
from beauty.forms import DealLineForm, BookingForm, BookingQuickForm
from beauty.utils import free_slots_for_employee


# ---- helpers ----
def is_superuser(user):
    return user.is_superuser


# ---- admin panel (superuser only) ----
@user_passes_test(is_superuser)
def admin_panel(request):
    now = timezone.now()
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    # Загальна статистика
    total_users = User.objects.count()
    staff_count = User.objects.filter(is_staff=True).count()
    active_employees = Employee.objects.filter(is_active=True).count()
    activities_last_week = Activity.objects.filter(created_at__gte=week_ago).count()

    # Топ активних співробітників за 30 днів
    top_active = (
        Activity.objects.filter(created_at__gte=month_ago)
        .values("user__username")
        .annotate(total=Count("id"))
        .order_by("-total")[:5]
    )

    # Середній скор по оцінках (по користувачу)
    latest_reviews = (
        PerformanceReview.objects
        .values("user__username")
        .annotate(avg_score=Avg("score"), count=Count("id"))
        .order_by("-avg_score")
    )

    # Список співробітників
    employees = (
        Employee.objects.select_related("user")
        .order_by("department", "user__username")
    )

    context = {
        "total_users": total_users,
        "staff_count": staff_count,
        "active_employees": active_employees,
        "activities_last_week": activities_last_week,
        "top_active": top_active,
        "latest_reviews": latest_reviews,
        "employees": employees,
    }
    return render(request, "admin_panel.html", context)

@user_passes_test(is_superuser)
@login_required
def employee_detail(request, user_id):
    emp = get_object_or_404(Employee, user__id=user_id)
    return render(request, "admin/employee_detail.html", {"emp": emp})

@user_passes_test(is_superuser)
@login_required
def employee_edit(request, user_id):
    emp = get_object_or_404(Employee, user__id=user_id)
    if request.method == "POST":
        form = EmployeeForm(request.POST, request.FILES, instance=emp)
        if form.is_valid():
            form.save()
            messages.success(request, "Профіль співробітника збережено ✅")
            return redirect("employee_detail", user_id=user_id)
    else:
        form = EmployeeForm(instance=emp)
    return render(request, "admin/employee_form.html", {"form": form, "emp": emp})

# ---- public home ----
def home(request):
    return render(request, "home.html")


# ---- dashboard (with filters & sorting) ----
@login_required
def dashboard(request):
    # Фільтри з GET
    kind = request.GET.get("kind")                 # call/meet/deal/task/other
    date_from = request.GET.get("from")            # YYYY-MM-DD
    date_to = request.GET.get("to")                # YYYY-MM-DD
    sort = request.GET.get("sort", "-created_at")  # -created_at, created_at, -duration_min, duration_min

    # Базовий QS: тільки мої активності
    qs_my = Activity.objects.filter(user=request.user)

    # Тип
    if kind:
        qs_my = qs_my.filter(kind=kind)

    # Діапазон дат (включно)
    if date_from:
        try:
            dt_from = datetime.strptime(date_from, "%Y-%m-%d").date()
            qs_my = qs_my.filter(created_at__date__gte=dt_from)
        except ValueError:
            pass

    if date_to:
        try:
            dt_to = datetime.strptime(date_to, "%Y-%m-%d").date()
            qs_my = qs_my.filter(created_at__date__lte=dt_to)
        except ValueError:
            pass

    # Сортування (білий список)
    allowed_sorts = {"created_at", "-created_at", "duration_min", "-duration_min"}
    if sort not in allowed_sorts:
        sort = "-created_at"
    qs_my = qs_my.order_by(sort)

    # Сьогоднішній лічильник
    start_today = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    my_today_count = Activity.objects.filter(user=request.user, created_at__gte=start_today).count()

    # Результати: перші 10 після фільтрів
    latest_my = qs_my.select_related("user")[:10]

    ctx = {
        "user_name": request.user.get_username(),
        "my_latest_activities": latest_my,
        "my_today_count": my_today_count,
        "filter_kind": kind or "",
        "filter_from": date_from or "",
        "filter_to": date_to or "",
        "sort": sort,
    }

    # Додаткова зведена статистика для суперюзера
    if request.user.is_superuser:
        last_7 = timezone.now() - timedelta(days=7)
        ctx.update({
            "all_week_count": Activity.objects.filter(created_at__gte=last_7).count(),
            "all_total": Activity.objects.count(),
        })


    # ==== ЗВІТИ / KPI ====
    now = timezone.now()
    month_ago = now - timedelta(days=30)
    six_months_ago = (now - timedelta(days=180)).replace(day=1)

    # 1) Кількість клієнтів за місяць
    clients_last_month = Client.objects.filter(created_at__gte=month_ago).count()

    # 2) Кількість угод і сума продажів (усі угоди і сума по "closed")
    deals_total = Deal.objects.count()
    sales_sum = Deal.objects.filter(status="closed").aggregate(total=Sum("amount"))["total"] or 0

    # 3) Дані для графіка за місяцями (останні 6 міс.)
    clients_by_month = (
        Client.objects.filter(created_at__gte=six_months_ago)
        .annotate(m=TruncMonth("created_at"))
        .values("m").annotate(c=Count("id")).order_by("m")
    )
    deals_closed_by_month = (
        Deal.objects.filter(status="closed", created_at__gte=six_months_ago)
        .annotate(m=TruncMonth("created_at"))
        .values("m").annotate(s=Sum("amount")).order_by("m")
    )

    # Звести у паралельні масиви (мітки + значення)
    # Переконаємось, що в обох наборах однакові місяці
    months = sorted({row["m"].date() for row in clients_by_month} | {row["m"].date() for row in deals_closed_by_month})
    labels = [d.strftime("%Y-%m") for d in months]
    map_clients = {row["m"].date(): row["c"] for row in clients_by_month}
    map_sales = {row["m"].date(): float(row["s"] or 0) for row in deals_closed_by_month}
    data_clients = [map_clients.get(d, 0) for d in months]
    data_sales = [map_sales.get(d, 0) for d in months]

    ctx_reports = {
        "greet_name": request.user.get_username(),
        "clients_last_month": clients_last_month,
        "deals_total": deals_total,
        "sales_sum": sales_sum,
        "chart_labels_json": json.dumps(labels),
        "chart_clients_json": json.dumps(data_clients),
        "chart_sales_json": json.dumps(data_sales),
    }
    ctx.update(ctx_reports)


    tznow = timezone.localtime()
    today = tznow.date()
    yesterday = today - timedelta(days=1)
    month_start = today.replace(day=1)

    # 1) Записів сьогодні
    bookings_today_count = Booking.objects.filter(start_at__date=today).count()

    # 2) Вільні слоти (по кожному майстру)
    free_slots = {}
    for emp in Employee.objects.filter(is_active=True):
        slots = free_slots_for_employee(timezone.now(), emp, start_hour=9, end_hour=18, slot_min=60)
        # для компактності перетворимо в "HH:MM"
        free_slots[emp.full_name if hasattr(emp, "full_name") else emp.user.username] = [
            s.strftime("%H:%M") for s in slots
        ]

    # 3) Виручка за вчора/місяць (сума Deal.amount)
    revenue_yesterday = Deal.objects.filter(updated_at__date=yesterday, status="closed").aggregate(
        s=Sum("amount")
    )["s"] or 0
    revenue_month = Deal.objects.filter(updated_at__date__gte=month_start, status="closed").aggregate(
        s=Sum("amount")
    )["s"] or 0

    ctx.update({
    "bookings_today_count": bookings_today_count,
    "free_slots": free_slots,
    "revenue_yesterday": revenue_yesterday,
    "revenue_month": revenue_month,
    })

    ctx.update({
    "masters": Employee.objects.filter(is_active=True).select_related("user"),
    "services": Service.objects.all().order_by("name"),
    "clients": Client.objects.order_by("-created_at")[:200],  # топ-200 останніх (щоб не довго)
    "resources": Resource.objects.all().order_by("name"),
})
    return render(request, "main/dashboard.html", ctx)


# ---- create activity ----
@require_http_methods(["GET", "POST"])
@login_required
def activity_create(request):
    if request.method == "POST":
        form = ActivityForm(request.POST)
        if form.is_valid():
            activity = form.save(commit=False)
            activity.user = request.user  # автор — поточний користувач
            activity.save()
            messages.success(request, "Активність додано ✅")
            return redirect(request.GET.get("next") or "dashboard")
        messages.error(request, "Будь ласка, виправте помилки у формі.")
    else:
        # Prefill: /activities/new/?kind=call
        form = ActivityForm(initial={"kind": request.GET.get("kind", "")})

    return render(request, "activity_form.html", {"form": form, "title": "Нова активність"})


# ---- edit activity ----
@require_http_methods(["GET", "POST"])
@login_required
def activity_edit(request, pk):
    activity = get_object_or_404(Activity, pk=pk, user=request.user)  # щоб юзер міг редагувати тільки свої
    if request.method == "POST":
        form = ActivityForm(request.POST, instance=activity)
        if form.is_valid():
            form.save()
            messages.success(request, "Активність оновлено ✏️")
            return redirect("dashboard")
    else:
        form = ActivityForm(instance=activity)
    return render(request, "activity_form.html", {"form": form, "title": "Редагувати активність"})


# ---- delete activity ----
@require_http_methods(["GET", "POST"])
@login_required
def activity_delete(request, pk):
    activity = get_object_or_404(Activity, pk=pk, user=request.user)
    if request.method == "POST":
        activity.delete()
        messages.success(request, "Активність видалено 🗑️")
        return redirect("dashboard")
    return render(request, "confirm_delete.html", {"object": activity})



@login_required
def client_list(request):
    q = request.GET.get("q", "").strip()
    sort = request.GET.get("sort", "-created_at")

    qs = Client.objects.all()

    # простий пошук по імені/телефону/емейлу
    if q:
        qs = qs.filter(
            Q(name__icontains=q) |
            Q(phone__icontains=q) |
            Q(email__icontains=q)
        )

    allowed_sorts = {
        "name": "name",
        "-name": "-name",
        "phone": "phone",
        "-phone": "-phone",
        "email": "email",
        "-email": "-email",
        "deal": "deal_status",
        "-deal": "-deal_status",
        "created_at": "created_at",
        "-created_at": "-created_at",
    }        

    if sort not in allowed_sorts:
        sort = "-created_at"
    qs = qs.order_by(allowed_sorts[sort])

    # Пагінація (по 10)
    paginator = Paginator(qs, 10)
    page = request.GET.get("page")
    page_obj = paginator.get_page(page)

    return render(
        request,
        "clients/list.html",
        {"page_obj": page_obj, "q": q, "sort": sort},
    )



@require_http_methods(["GET", "POST"])
@user_passes_test(lambda u: u.is_staff or u.is_superuser)
@login_required
def client_create(request):
    if request.method == "POST":
        form = ClientForm(request.POST)
        if form.is_valid():
            client = form.save(commit=False)
            client.owner = request.user
            client.save()
            messages.success(request, "Клієнта додано ✅")
            return redirect("client_list")
    else:
        form = ClientForm()
    return render(request, "clients/form.html", {"form": form, "title": "Новий клієнт"})

@require_http_methods(["GET", "POST"])
@user_passes_test(lambda u: u.is_staff or u.is_superuser)
@login_required
def client_edit(request, pk):
    client = get_object_or_404(Client, pk=pk)
    if request.method == "POST":
        form = ClientForm(request.POST, instance=client)
        if form.is_valid():
            form.save()
            messages.success(request, "Клієнта оновлено ✏️")
            return redirect("client_list")
    else:
        form = ClientForm(instance=client)
    return render(request, "clients/form.html", {"form": form, "title": f"Редагувати: {client.name}"})

@require_http_methods(["GET", "POST"])
@user_passes_test(lambda u: u.is_staff or u.is_superuser)
@login_required
def client_delete(request, pk):
    client = get_object_or_404(Client, pk=pk)
    if request.method == "POST":
        client.delete()
        messages.success(request, "Клієнта видалено 🗑️")
        return redirect("client_list")
    return render(request, "confirm_delete.html", {"object": client})

@login_required
def client_detail(request, pk):
    client = get_object_or_404(Client, pk=pk)
    deals = client.deals.all()  # already ordered by -created_at
    return render(request, "clients/detail.html", {"client": client, "deals": deals})

# дозволяємо менеджерам/адмінам керувати угодами
only_staff = user_passes_test(lambda u: u.is_staff or u.is_superuser)

@require_http_methods(["GET", "POST"])
@login_required
@only_staff
def deal_create(request, client_pk=None):
    preset_client = get_object_or_404(Client, pk=client_pk) if client_pk else None

    if request.method == "POST":
        # підставляємо клієнта, якщо поле disabled
        data = request.POST.copy()
        if preset_client:
            data["client"] = str(preset_client.pk)

        deal_form = DealForm(data)
        booking_form = BookingQuickForm(request.POST)

        if deal_form.is_valid():
            deal = deal_form.save(commit=False)
            if preset_client:
                deal.client = preset_client
            deal.owner = request.user
            deal.save()

            # якщо заповнили поля бронювання — створимо Booking
            if booking_form.is_valid():
                start_at = booking_form.cleaned_data.get("start_at")
                master   = booking_form.cleaned_data.get("master")
                duration = booking_form.cleaned_data.get("duration_min")

                if start_at and master and duration:
                    booking = booking_form.save(commit=False)
                    booking.end_at = booking_form.cleaned_data["end_at"]
                    booking.deal = deal           # ← зв’язок з угодою
                    booking.client = deal.client  # корисно для фільтрів
                    booking.created_by = request.user if hasattr(booking, "created_by") else None
                    booking.save()

            messages.success(request, "Угоду створено ✅")
            return redirect("client_detail", pk=deal.client.pk)
        else:
            # форма угоди не валідна → покажемо помилки
            pass

    else:
        initial_deal = {}
        if preset_client:
            initial_deal["client"] = preset_client
        deal_form = DealForm(initial=initial_deal)
        if preset_client:
            deal_form.fields["client"].disabled = True
            deal_form.fields["client"].required = False

        # стартове значення для зручності
        tznow = timezone.localtime()
        # округлити до найближчих 30 хв — опціонально
        initial_booking = {"start_at": tznow.replace(minute=(0 if tznow.minute < 30 else 30), second=0, microsecond=0)}
        booking_form = BookingQuickForm(initial=initial_booking)

    return render(
        request,
        "deals/form.html",
        {"form": deal_form, "booking_form": booking_form, "title": "Нова угода"}
    )


@require_http_methods(["GET", "POST"])
@login_required
@only_staff
def deal_edit(request, pk):
    deal = get_object_or_404(Deal, pk=pk)
    if request.method == "POST":
        form = DealForm(request.POST, instance=deal)
        if form.is_valid():
            form.save()
            messages.success(request, "Угоду оновлено ✏️")
            return redirect("client_detail", pk=deal.client.pk)
    else:
        form = DealForm(instance=deal)
    return render(request, "deals/form.html", {"form": form, "title": f"Редагувати угоду: {deal.title}"})

@require_http_methods(["GET", "POST"])
@login_required
@only_staff
def deal_delete(request, pk):
    deal = get_object_or_404(Deal, pk=pk)
    client_pk = deal.client.pk
    if request.method == "POST":
        deal.delete()
        messages.success(request, "Угоду видалено 🗑️")
        return redirect("client_detail", pk=client_pk)
    return render(request, "confirm_delete.html", {"object": deal})

class DealAttachmentForm(forms.ModelForm):
    class Meta:
        model = DealAttachment
        fields = ["file"]

@login_required
def deal_detail(request, pk):
    deal = get_object_or_404(Deal, pk=pk)
    attachments = deal.attachments.order_by("-uploaded_at")

    # форми за замовчуванням
    line_form = DealLineForm()
    booking_form = BookingForm(instance=getattr(deal, "booking", None))

    # обробка POST з двох форм (визначаємо по hidden input)
    if request.method == "POST":
        form_type = request.POST.get("form_type")
        if form_type == "line":
            line_form = DealLineForm(request.POST)
            if line_form.is_valid():
                line = line_form.save(commit=False)
                line.deal = deal
                line.save()  # сам перерахує subtotal і total угоди
                messages.success(request, "Послугу додано до угоди ✅")
                return redirect("deal_detail", pk=deal.pk)
            # якщо помилка — показуємо форму з помилками
        elif form_type == "booking":
            booking_form = BookingForm(request.POST, instance=getattr(deal, "booking", None))
            if booking_form.is_valid():
                b = booking_form.save(commit=False)
                b.deal = deal
                b.save()  # у save() рахується end_at із тривалостей послуг
                messages.success(request, "Запис збережено ✅")
                return redirect("deal_detail", pk=deal.pk)

    # список рядків (для таблиці)
    lines = deal.lines.select_related("service").all() if hasattr(deal, "lines") else []

    # стара форма для вкладень (лишаємо як було)
    att_form = None
    if request.user.is_staff or request.user.is_superuser:
        class DealAttachmentForm(forms.ModelForm):
            class Meta:
                model = DealAttachment
                fields = ["file"]
        att_form = DealAttachmentForm()

    return render(request, "deals/detail.html", {
        "deal": deal,
        "attachments": attachments,
        "form": att_form,          # твоя форма вкладень
        "lines": lines,            # НОВЕ
        "line_form": line_form,    # НОВЕ
        "booking_form": booking_form,  # НОВЕ
    })


@require_http_methods(["POST"])
@login_required
def deal_attachment_upload(request, pk):
    # тільки staff/superuser можуть вантажити
    if not (request.user.is_staff or request.user.is_superuser):
        messages.error(request, "Недостатньо прав для завантаження файлів.")
        return redirect("deal_detail", pk=pk)

    deal = get_object_or_404(Deal, pk=pk)
    form = DealAttachmentForm(request.POST, request.FILES)
    if form.is_valid():
        att = form.save(commit=False)
        att.deal = deal
        att.uploaded_by = request.user
        att.save()
        messages.success(request, "Файл додано ✅")
    else:
        messages.error(request, "Не вдалося завантажити файл.")
    return redirect("deal_detail", pk=pk)

@require_http_methods(["POST"])
@login_required
def deal_attachment_delete(request, att_id):
    att = get_object_or_404(DealAttachment, pk=att_id)
    deal_pk = att.deal.pk
    if not (request.user.is_staff or request.user.is_superuser):
        messages.error(request, "Недостатньо прав для видалення.")
        return redirect("deal_detail", pk=deal_pk)
    att.file.delete(save=False)  # видалити файл з диска
    att.delete()
    messages.success(request, "Файл видалено 🗑️")
    return redirect("deal_detail", pk=deal_pk)

only_staff = user_passes_test(lambda u: u.is_staff or u.is_superuser)

@require_POST
@login_required
@only_staff
def deal_change_status(request, pk):
    deal = get_object_or_404(Deal, pk=pk)
    status = request.POST.get("status")
    if status not in {"new", "in_progress", "closed"}:
        messages.error(request, "Невалідний статус.")
        return redirect("client_detail", pk=deal.client.pk)
    deal.status = status
    deal.save(update_fields=["status"])
    messages.success(request, "Статус оновлено ✅")
    return redirect("client_detail", pk=deal.client.pk)