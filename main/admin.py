from django.contrib import admin
from .models import Employee, Activity, PerformanceReview, Client, Deal, DealAttachment

@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ("user", "position", "department", "is_active", "hired_at")
    search_fields = ("user__username", "user__email", "position", "department")
    list_filter = ("department", "is_active")
    filter_horizontal = ("services",)

@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = ("user", "kind", "created_at", "duration_min")
    list_filter = ("kind", "created_at")
    search_fields = ("user__username", "notes")

@admin.register(PerformanceReview)
class PerformanceReviewAdmin(admin.ModelAdmin):
    list_display = ("user", "period_start", "period_end", "score", "created_at")
    list_filter = ("score", "period_end")
    search_fields = ("user__username", "comment")

@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "email", "deal_status", "created_at", "owner")
    search_fields = ("name", "phone", "email")
    list_filter = ("deal_status", "created_at")

@admin.register(Deal)
class DealAdmin(admin.ModelAdmin):
    list_display = ("title", "client", "amount", "status", "created_at", "owner")
    list_filter = ("status", "created_at")
    search_fields = ("title", "client__name")

@admin.register(DealAttachment)
class DealAttachmentAdmin(admin.ModelAdmin):
    list_display = ("deal", "filename", "uploaded_at", "uploaded_by")
    search_fields = ("deal__title",)