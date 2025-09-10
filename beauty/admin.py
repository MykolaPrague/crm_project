from django.contrib import admin
from .models import Service, DealLine, Booking, Resource

@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ("name", "base_price", "duration_min", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "code")

@admin.register(DealLine)
class DealLineAdmin(admin.ModelAdmin):
    list_display = ("deal", "service", "quantity", "unit_price", "subtotal", "created_at")
    search_fields = ("deal__title", "deal__client__name", "service__name")

@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ("deal", "start_at", "end_at", "master", "resource")
    list_filter = ("master", "resource")
    date_hierarchy = "start_at"
    search_fields = ("deal__title", "deal__client__name")

admin.site.register(Resource)
