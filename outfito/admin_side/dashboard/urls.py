from django.urls import path
from . import views

urlpatterns = [
    path('dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('sales-report/', views.sales_report, name='sales_report'),
    path('sales-report/pdf/', views.download_sales_report_pdf, name='download_sales_report_pdf'),
    path('sales-report/excel/', views.download_sales_report_excel, name='download_sales_report_excel'),
]
