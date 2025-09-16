from django.urls import path
from . import views, api

urlpatterns = [
    path("deal/<int:pk>/beauty/", views.deal_lines_manage, name="deal_beauty"),
    path("deal-line/<int:pk>/delete/", views.line_delete, name="deal_line_delete"),
    path("calendar/feed/", views.calendar_feed, name="calendar_feed"),
    path("calendar/events/", api.calendar_events, name="calendar_events"),       # GET
    path("calendar/bookings/", api.booking_create, name="booking_create"),       # POST
    path("calendar/bookings/<int:pk>/", api.booking_update, name="booking_update"),  # PATCH / DELETE
]
