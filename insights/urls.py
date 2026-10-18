from django.urls import path

from . import views

urlpatterns = [
    path("", views.insights_home, name="insights_home"),
    path("analyse/", views.analyse, name="insights_analyse"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("proposal/<int:location_id>/<str:category>/", views.proposal, name="insight_proposal"),
]
