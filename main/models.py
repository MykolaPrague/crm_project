from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.exceptions import ValidationError
import os

ALLOWED_EXTS = {".pdf", ".png", ".jpg", ".jpeg"}
MAX_MB = 20

def employee_upload_path(instance, filename):
    # media/employees/<user_id>/<filename>
    return os.path.join("employees", str(instance.user_id or "unassigned"), filename)

class Employee(models.Model):

    GENDER_CHOICES = [("m", "Чоловіча"), ("f", "Жіноча"), ("x", "Інше/Не вказано")]
    MARITAL_CHOICES = [
        ("single", "Вільний/вільна"),
        ("married", "Одружений/заміжня"),
        ("divorced", "Розлучений/розлучена"),
        ("widowed", "Вдівець/вдова"),
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="employee")
    position = models.CharField(max_length=100, blank=True)
    department = models.CharField(max_length=100, blank=True)
    hired_at = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    first_name = models.CharField(max_length=100, blank=True)
    last_name  = models.CharField(max_length=100, blank=True)
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES, default="x")
    birth_date = models.DateField(null=True, blank=True)
    birth_place = models.CharField(max_length=150, blank=True)
    registration_address = models.CharField(max_length=255, blank=True)

    marital_status = models.CharField(max_length=10, choices=MARITAL_CHOICES, default="single")

    photo = models.ImageField(upload_to=employee_upload_path, null=True, blank=True)
    contract_file = models.FileField(upload_to=employee_upload_path, null=True, blank=True)

    hire_date = models.DateField(null=True, blank=True)
    termination_date = models.DateField(null=True, blank=True)

    is_active = models.BooleanField(default=True)

    # простий лічильник прогулів; для деталізації — зробимо окрему модель Absence
    absences_count = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["last_name", "first_name"]

    def __str__(self):
        return self.full_name or self.user.username

    @property
    def full_name(self):
        name = f"{self.first_name} {self.last_name}".strip()
        return name or self.user.get_username()

class Activity(models.Model):
    TYPE_CHOICES = [
        ("call", "Дзвінок"),
        ("meet", "Зустріч"),
        ("deal", "Угода"),
        ("task", "Завдання"),
        ("other", "Інше"),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="activities")
    kind = models.CharField(max_length=20, choices=TYPE_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    duration_min = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.username} · {self.get_kind_display()} · {self.created_at:%Y-%m-%d %H:%M}"

class PerformanceReview(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="reviews")
    period_start = models.DateField()
    period_end = models.DateField()
    score = models.PositiveSmallIntegerField()  # 1..10 або 0..100
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-period_end"]

class Client(models.Model):
    DEAL_CHOICES = [
        ("none", "—"),
        ("active", "Триває"),
        ("pause", "Пауза"),
        ("done", "Завершено"),
    ]

    name = models.CharField(max_length=150)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    owner = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="clients")
    deal_status = models.CharField(max_length=10, choices=DEAL_CHOICES, default="none")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name


class Deal(models.Model):
    STATUS_CHOICES = [
        ("new", "Новий"),
        ("in_progress", "В роботі"),
        ("closed", "Закрито"),
    ]
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="deals")
    title = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="new")
    owner = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="deals")
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} · {self.client.name}"
    
def recalc_client_deal_status(client: Client):
    # якщо є хоча б одна активна угода → "active"
    if client.deals.filter(status__in=["new", "in_progress"]).exists():
        new_status = "active"
    # інакше якщо є хоча б одна закрита → "done"
    elif client.deals.filter(status="closed").exists():
        new_status = "done"
    else:
        new_status = "none"

    if client.deal_status != new_status:
        client.deal_status = new_status
        client.save(update_fields=["deal_status"])

@receiver(post_save, sender=Deal)
def on_deal_save(sender, instance, **kwargs):
    recalc_client_deal_status(instance.client)

@receiver(post_delete, sender=Deal)
def on_deal_delete(sender, instance, **kwargs):
    # після видалення теж перерахувати
    recalc_client_deal_status(instance.client)

def deal_upload_path(instance, filename):
    # media/deals/<deal_id>/<original_name>
    return os.path.join("deals", str(instance.deal_id), filename)

def validate_attachment(file):
    import os
    ext = os.path.splitext(file.name)[1].lower()
    if ext not in ALLOWED_EXTS:
        raise ValidationError("Дозволені формати: PDF, PNG, JPG.")
    if file.size > MAX_MB * 1024 * 1024:
        raise ValidationError(f"Максимальний розмір файлу {MAX_MB}MB.")
    

class DealAttachment(models.Model):
    deal = models.ForeignKey("Deal", on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(upload_to=deal_upload_path, validators=[validate_attachment])
    uploaded_at = models.DateTimeField(auto_now_add=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    def filename(self):
        return os.path.basename(self.file.name)

    def __str__(self):
        return f"{self.deal} · {self.filename()}"
    
