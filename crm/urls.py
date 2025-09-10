from django.contrib import admin
from django.urls import path, include
from main import views as main_views
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', main_views.home, name='home'),
    path('dashboard/', main_views.dashboard, name='dashboard'),
    path('accounts/', include('accounts.urls')),
    path('accounts/', include('django.contrib.auth.urls')),
    path('admin-panel/', main_views.admin_panel, name='admin_panel'),
    path("admin-panel/employees/<int:user_id>/", main_views.employee_detail, name="employee_detail"),
    path("admin-panel/employees/<int:user_id>/edit/", main_views.employee_edit, name="employee_edit"),
    path('activities/new/', main_views.activity_create, name='activity_create'),
    path("activities/<int:pk>/edit/", main_views.activity_edit, name="activity_edit"),
    path("activities/<int:pk>/delete/", main_views.activity_delete, name="activity_delete"),
    path("clients/", main_views.client_list, name="client_list"),
    path("clients/new/", main_views.client_create, name="client_create"),
    path("clients/<int:pk>/", main_views.client_detail, name="client_detail"),
    path("clients/<int:pk>/edit/", main_views.client_edit, name="client_edit"),
    path("clients/<int:pk>/delete/", main_views.client_delete, name="client_delete"),
    path("deals/new/", main_views.deal_create, name="deal_create"),
    path("clients/<int:client_pk>/deals/new/", main_views.deal_create, name="deal_create_for_client"),
    path("deals/<int:pk>/edit/", main_views.deal_edit, name="deal_edit"),
    path("deals/<int:pk>/delete/", main_views.deal_delete, name="deal_delete"),
    path("deals/<int:pk>/", main_views.deal_detail, name="deal_detail"),
    path("deals/<int:pk>/upload/", main_views.deal_attachment_upload, name="deal_attachment_upload"),
    path("attachments/<int:att_id>/delete/", main_views.deal_attachment_delete, name="deal_attachment_delete"),
    path("deals/<int:pk>/status/", main_views.deal_change_status, name="deal_change_status"),
    path("i18n/", include("django.conf.urls.i18n")),
    path("", include("beauty.urls")),

]


if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)