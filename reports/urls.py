from django.urls import path

from . import views

urlpatterns = [
    path("", views.report_list, name="report_list"),
    path("new/", views.report_create, name="report_create"),
    path("map/", views.report_map, name="report_map"),
    path("manage/", views.manage_reports, name="manage_reports"),
    path("<int:pk>/", views.report_detail, name="report_detail"),
    path("<int:pk>/confirm/", views.report_confirm, name="report_confirm"),
    path("<int:pk>/tip/", views.report_tip, name="report_tip"),
    path("<int:pk>/update/", views.report_update, name="report_update"),
]
