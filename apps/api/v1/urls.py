from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    ProductViewSet, VehicleInspectionViewSet,
    HealthCheckView,
    DriverConfigurationView,
    MilkReceiptViewSet,
    ProducerRequestViewSet,
    ProducerViewSet,
    RouteViewSet,
    RouteTripViewSet,
    DriverScheduleViewSet,
    SecureTokenView,
    VehicleViewSet,
)


router = DefaultRouter()
router.register("products", ProductViewSet, basename="product")
router.register("vehicle-inspections", VehicleInspectionViewSet, basename="vehicle-inspection")
router.register("producers", ProducerViewSet, basename="producer")
router.register("producer-requests", ProducerRequestViewSet, basename="producer-request")
router.register("routes", RouteViewSet, basename="route")
router.register("driver-schedules", DriverScheduleViewSet, basename="driver-schedule")
router.register("route-trips", RouteTripViewSet, basename="route-trip")
router.register("vehicles", VehicleViewSet, basename="vehicle")
router.register("receipts", MilkReceiptViewSet, basename="receipt")

urlpatterns = [
    path("health/", HealthCheckView.as_view(), name="health"),
    path("auth/token/", SecureTokenView.as_view(), name="token"),
    path("drivers/me/configuration/", DriverConfigurationView.as_view(), name="driver-configuration"),
    path("", include(router.urls)),
]
