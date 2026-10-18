from django.urls import path

from . import views

urlpatterns = [
    path("", views.notification_list, name="notification_list"),
    path("read-all/", views.mark_all_read, name="notifications_read_all"),
    path("badge/", views.badge, name="notifications_badge"),
]
