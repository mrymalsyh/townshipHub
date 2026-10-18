from django.urls import path

from . import views

urlpatterns = [
    path("", views.facility_list, name="facility_list"),
    path("mine/", views.my_bookings, name="my_bookings"),
    path("manage/", views.manage_bookings, name="manage_bookings"),
    path("manage/closure/<int:pk>/delete/", views.block_delete, name="block_delete"),
    path("<int:pk>/", views.facility_detail, name="facility_detail"),
    path("cancel/<int:pk>/", views.booking_cancel, name="booking_cancel"),
]
