from django.db import models
from django.utils.translation import gettext_lazy as _
from django.contrib.auth.models import User
from decimal import Decimal
from datetime import timedelta

# Імпорти твоїх моделей з поточного апу (замінити на реальну назву апу)
from main.models import Deal, Employee  # <- заміни your_app на свій app label

class Service(models.Model):
    """Послуга салону (каталог)."""
    name = models.CharField(max_length=160, db_index=True, verbose_name=_("Назва"))
    code = models.CharField(max_length=40, blank=True, verbose_name=_("Код/артикул"))
    base_price = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name=_("Базова ціна"))
    duration_min = models.PositiveIntegerField(default=30, verbose_name=_("Тривалість, хв"))
    is_active = models.BooleanField(default=True, verbose_name=_("Активна"))

    class Meta:
        verbose_name = _("Послуга")
        verbose_name_plural = _("Послуги")
        ordering = ["name"]

    def __str__(self):
        return self.name


class DealLine(models.Model):
    """Рядок угоди: одна або кілька послуг в межах Deal."""
    deal = models.ForeignKey(Deal, on_delete=models.CASCADE, related_name="lines", verbose_name=_("Угода"))
    service = models.ForeignKey(Service, on_delete=models.PROTECT, related_name="deal_lines", verbose_name=_("Послуга"))
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("1.00"), verbose_name=_("К-сть"))
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name=_("Ціна за од."))
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_("Сума"))

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Рядок угоди")
        verbose_name_plural = _("Рядки угоди")

    def __str__(self):
        return f"{self.deal} · {self.service} × {self.quantity}"

    def save(self, *args, **kwargs):
        if not self.unit_price:
            self.unit_price = self.service.base_price
        self.subtotal = (self.unit_price * self.quantity).quantize(Decimal("0.01"))
        super().save(*args, **kwargs)
        # Після збереження — оновити суму в Deal
        self.recalc_deal_total()

    def delete(self, *args, **kwargs):
        deal = self.deal
        super().delete(*args, **kwargs)
        # Після видалення — оновити суму в Deal
        DealLine.recalc_total_for(deal)

    def recalc_deal_total(self):
        DealLine.recalc_total_for(self.deal)

    @staticmethod
    def recalc_total_for(deal: Deal):
        from django.db.models import Sum
        total = deal.lines.aggregate(s=Sum("subtotal"))["s"] or Decimal("0.00")
        if deal.amount != total:
            deal.amount = total
            deal.save(update_fields=["amount"])


class Resource(models.Model):
    """Крісло/кабінет/мийка — опційно для календаря."""
    name = models.CharField(max_length=80, verbose_name=_("Ресурс"))
    is_active = models.BooleanField(default=True, verbose_name=_("Активний"))

    class Meta:
        verbose_name = _("Ресурс")
        verbose_name_plural = _("Ресурси")

    def __str__(self):
        return self.name


class Booking(models.Model):
    """
    Деталі бронювання поверх Deal.
    Не чіпаємо структуру Deal: додаємо start/end, майстра, ресурс, колір для календаря.
    """
    deal = models.OneToOneField(Deal, on_delete=models.CASCADE, related_name="booking", verbose_name=_("Угода"))
    start_at = models.DateTimeField(db_index=True, verbose_name=_("Початок"))
    end_at = models.DateTimeField(db_index=True, verbose_name=_("Кінець"), null=True, blank=True)
    master = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="bookings", verbose_name=_("Майстер"))
    resource = models.ForeignKey(Resource, null=True, blank=True, on_delete=models.SET_NULL, verbose_name=_("Ресурс"))
    color = models.CharField(max_length=7, default="#88CCEE", verbose_name=_("Колір"))

    note = models.CharField(max_length=200, blank=True, verbose_name=_("Нотатка"))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Запис")
        verbose_name_plural = _("Записи")
        indexes = [models.Index(fields=["start_at"]), models.Index(fields=["end_at"])]

    def __str__(self):
        return f"{self.deal} @ {self.start_at:%Y-%m-%d %H:%M}"

    def save(self, *args, **kwargs):
        # якщо не задано end_at — порахуємо як суму тривалостей усіх послуг
        if not self.end_at:
            total_min = 0
            for line in self.deal.lines.select_related("service"):
                total_min += int(line.service.duration_min * float(line.quantity))
            if total_min <= 0:
                total_min = 30
            self.end_at = self.start_at + timedelta(minutes=total_min)
        super().save(*args, **kwargs)
