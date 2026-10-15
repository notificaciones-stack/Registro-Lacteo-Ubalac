from apps.accounts.models import User
from .models import DriverProfile, Producer, Route, Vehicle


def driver_profile(user):
    return DriverProfile.objects.filter(user=user).first()


def assigned_routes(user):
    routes = Route.objects.filter(active=True)
    if user.is_superuser or user.role not in {User.Role.DRIVER, User.Role.COLLECTOR}:
        return routes
    profile = driver_profile(user)
    if profile:
        return routes.filter(driver_profiles=profile)
    if user.role == User.Role.COLLECTOR:
        return routes
    # Existing accounts without a profile keep their vehicle's default routes.
    return routes.filter(vehicles__driver=user, vehicles__active=True).distinct()


def assigned_vehicles(user):
    vehicles = Vehicle.objects.filter(active=True)
    if user.is_superuser or user.role not in {User.Role.DRIVER, User.Role.COLLECTOR}:
        return vehicles
    if user.role == User.Role.COLLECTOR and not driver_profile(user):
        return vehicles
    return vehicles.filter(driver=user)


def assigned_producers(user):
    producers = Producer.objects.filter(active=True)
    if user.is_superuser or user.role not in {User.Role.DRIVER, User.Role.COLLECTOR}:
        return producers
    profile = driver_profile(user)
    if profile and profile.producers.exists():
        return producers.filter(driver_profiles=profile)
    return producers
