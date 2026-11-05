from django.contrib import admin
from .models import FatigueSurvey, FuelEntry

@admin.register(FatigueSurvey)
class FatigueAdmin(admin.ModelAdmin):
    list_display = ['trip', 'sleep_hours', 'has_risk', 'created_at']
    list_filter = ['sleepy', 'fatigue', 'rested']
    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False

@admin.register(FuelEntry)
class FuelAdmin(admin.ModelAdmin):
    list_display = ['trip', 'fueled_at', 'gallons', 'total_price', 'odometer_km']
    exclude = ['fuel_photo', 'invoice_photo']
    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
