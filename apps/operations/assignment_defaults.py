"""Shared assignment catalogue and unambiguous defaults for forms/imports."""
from django.core.exceptions import ValidationError

from apps.accounts.models import User


def assignment_catalog():
    from .models import DriverProfile, Route, Vehicle
    profiles = {p.user_id: p for p in DriverProfile.objects.prefetch_related('routes')}
    vehicles = list(Vehicle.objects.filter(active=True))
    drivers = []
    for user in User.objects.filter(is_active=True, role__in=['DRIVER', 'COLLECTOR']):
        profile = profiles.get(user.pk)
        from .assignments import assigned_routes
        routes = set(assigned_routes(user).values_list('pk', flat=True))
        drivers.append({'id': str(user.pk), 'name': user.get_full_name() or user.username,
                        'document': profile.document_number if profile else '',
                        'phone': profile.phone if profile else '', 'routes': [str(r) for r in routes]})
    return {'drivers': drivers,
            'routes': [{'id': str(r.pk)} for r in Route.objects.filter(active=True)],
            'vehicles': [{'id': str(v.pk), 'driver': str(v.driver_id or ''), 'route': str(v.route_id or '')} for v in vehicles]}


def complete_producer_assignment(producer):
    from .models import Vehicle
    driver, route, vehicle = producer.assigned_driver, producer.assigned_route, producer.assigned_vehicle
    if vehicle:
        if driver and vehicle.driver_id and vehicle.driver_id != driver.pk:
            raise ValidationError({'assigned_vehicle': 'La placa no corresponde al conductor seleccionado.'})
        if route and vehicle.route_id and vehicle.route_id != route.pk:
            raise ValidationError({'assigned_vehicle': 'La placa pertenece a otra ruta.'})
        driver, route = driver or vehicle.driver, route or vehicle.route
    if route and not driver:
        ids = [d['id'] for d in assignment_catalog()['drivers'] if str(route.pk) in d['routes']]
        candidates = User.objects.filter(pk__in=ids)
        if candidates.count() == 1:
            driver = candidates.first()
    if driver and not route:
        from .assignments import assigned_routes
        candidates = assigned_routes(driver)
        if candidates.count() == 1:
            route = candidates.first()
    if driver and route:
        allowed = any(d['id'] == str(driver.pk) and str(route.pk) in d['routes'] for d in assignment_catalog()['drivers'])
        if not allowed:
            raise ValidationError({'assigned_route': 'La ruta no está asignada al conductor. Configure primero sus asignaciones.'})
    if not vehicle and (driver or route):
        candidates = Vehicle.objects.filter(active=True)
        if driver:
            candidates = candidates.filter(driver=driver)
        if route:
            candidates = candidates.filter(route=route)
        if candidates.count() == 1:
            vehicle = candidates.first()
    producer.assigned_driver, producer.assigned_route, producer.assigned_vehicle = driver, route, vehicle
