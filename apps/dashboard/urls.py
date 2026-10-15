from django.urls import path

from .views import DashboardView, ReportExportView, ReportView


app_name = "dashboard"

urlpatterns = [
    path("", DashboardView.as_view(), name="index"),
    path("informes/", ReportView.as_view(), name="reports"),
    path("informes/excel/", ReportExportView.as_view(), name="report_export"),
]
