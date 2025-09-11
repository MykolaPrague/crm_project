from django import forms
from .models import DealLine, Booking, Service
from django.utils import timezone
from datetime import timedelta
from django.utils.translation import gettext_lazy as _

class DealLineForm(forms.ModelForm):
    class Meta:
        model = DealLine
        fields = ["service", "quantity", "unit_price"]
        widgets = {
            "quantity": forms.NumberInput(attrs={"step": "0.5", "min": "0.5"}),
            "unit_price": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # ціна за замовчуванням з сервісу (при створенні)
        if not self.instance.pk:
            self.fields["unit_price"].help_text = _("Якщо лишите порожнім — візьмемо базову ціну послуги.")

    def clean(self):
        cd = super().clean()
        service = cd.get("service")
        unit_price = cd.get("unit_price")
        if service and (unit_price is None):
            cd["unit_price"] = service.base_price
        return cd


class BookingForm(forms.ModelForm):
    """Основна форма для редагування запису у календарі."""
    class Meta:
        model = Booking
        fields = ["start_at", "master", "resource", "note"]
        widgets = {
            "start_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }

class BookingQuickForm(forms.ModelForm):
    """
    Швидке бронювання під час створення угоди.
    Додаємо поле тривалості, щоб прорахувати end_at
    ще до збереження.
    """
    duration_min = forms.IntegerField(
        min_value=5, max_value=600,
        initial=30, required=True,
        label=_("Тривалість (хв)")
    )

    class Meta:
        model = Booking
        fields = ["start_at", "master", "resource", "note", "duration_min"]
        widgets = {
            "start_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "note": forms.Textarea(attrs={"rows": 2}),
        }
        labels = {
            "start_at": _("Початок"),
            "master": _("Майстер"),
            "resource": _("Ресурс"),
            "note": _("Нотатка"),
            "duration_min": _("Тривалість (хв)"),
        }

    def clean(self):
        cleaned = super().clean()
        start_at = cleaned.get("start_at")
        duration = cleaned.get("duration_min")
        if start_at and duration:
            if timezone.is_naive(start_at):
                start_at = timezone.make_aware(start_at, timezone.get_current_timezone())
                cleaned["start_at"] = start_at
            cleaned["end_at"] = start_at + timedelta(minutes=duration)
        return cleaned