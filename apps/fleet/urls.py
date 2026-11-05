from django.urls import path
from . import views
app_name = 'fleet'
urlpatterns = [
    path('tanqueos/', views.FleetReport.as_view(), name='fuel'),
    path('tanqueos/nuevo/', views.FuelCreate.as_view(), name='fuel_create'),
    path('tanqueos/exportar/', views.FuelExport.as_view(), name='fuel_export'),
    path('tanqueos/<uuid:pk>/editar/', views.FuelUpdate.as_view(), name='fuel_update'),
    path('tanqueos/<uuid:pk>/foto/<str:kind>/', views.FuelPhoto.as_view(), name='photo'),
    path('fatiga/', views.FatigueReport.as_view(), name='fatigue'),
    path('fatiga/nueva/', views.FatigueCreate.as_view(), name='fatigue_create'),
]
