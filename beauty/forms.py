from django import forms
from .models import DealLine, Booking, Service
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
    class Meta:
        model = Booking
        fields = ["start_at", "master", "resource", "note"]
        widgets = {
            "start_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }
