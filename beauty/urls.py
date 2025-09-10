from django.urls import path
from . import views

urlpatterns = [
    path("deal/<int:pk>/beauty/", views.deal_lines_manage, name="deal_beauty"),
    path("deal-line/<uuid:pk>/delete/", views.line_delete, name="deal_line_delete"),
    path("calendar/feed/", views.calendar_feed, name="calendar_feed"),
]
