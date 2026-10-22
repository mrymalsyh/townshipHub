from django.urls import path

from . import views

urlpatterns = [
    path("", views.item_list, name="item_list"),
    path("mine/", views.my_loans, name="my_loans"),
    path("manage/", views.manage_inventory, name="manage_inventory"),
    path("manage/lockers/add/", views.add_locker, name="add_item_locker"),
    path("manage/lockers/<int:pk>/toggle/", views.toggle_locker, name="toggle_item_locker"),
    path("waitlist/<int:pk>/", views.item_waitlist, name="item_waitlist"),
    path("return-request/<int:pk>/", views.request_return, name="request_return"),
    path("extension/<int:pk>/", views.loan_extension, name="loan_extension"),
    path("<int:pk>/", views.item_detail, name="item_detail"),
    path("<int:pk>/repaired/", views.item_repaired, name="item_repaired"),
    path("return/<int:pk>/", views.loan_return, name="loan_return"),
]
