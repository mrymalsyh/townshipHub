from django.urls import path

from . import views

urlpatterns = [
    path("", views.item_list, name="item_list"),
    path("mine/", views.my_loans, name="my_loans"),
    path("manage/", views.manage_inventory, name="manage_inventory"),
    path("<int:pk>/", views.item_detail, name="item_detail"),
    path("<int:pk>/repaired/", views.item_repaired, name="item_repaired"),
    path("return/<int:pk>/", views.loan_return, name="loan_return"),
]
