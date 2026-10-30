from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.contrib.auth.models import update_last_login
from django.db import connection, transaction
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.authtoken.models import Token
from rest_framework.authtoken.serializers import AuthTokenSerializer
from rest_framework.decorators import action
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.operations.models import MilkReceipt, Producer, ProducerRequest, Route, RouteTrip, RouteSchedule, Vehicle
from apps.operations.assignments import assigned_producers, assigned_routes, assigned_vehicles, driver_profile
from apps.operations.services.trips import auto_close_expired_trips, close_trip, start_trip

from .permissions import RoleWritePermission
from .serializers import MilkReceiptSerializer, ProducerRequestSerializer, ProducerSerializer, RouteSerializer, RouteScheduleSerializer, RouteTripSerializer, VehicleSerializer
from .serializers import ProductSerializer, VehicleInspectionSerializer
from apps.operations.models import CollectionProduct, VehicleInspection


class ProducerRequestViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    serializer_class = ProducerRequestSerializer
    permission_classes = [RoleWritePermission]
    write_roles = {User.Role.DRIVER, User.Role.COLLECTOR}
    queryset = ProducerRequest.objects.all()

    def get_queryset(self):
        if self.request.user.is_superuser or self.request.user.role in {User.Role.ADMIN, User.Role.SUPERVISOR, User.Role.ACCOUNTING}:
            return super().get_queryset()
        return super().get_queryset().filter(requested_by=self.request.user)

    def create(self, request):
        if not settings.ACCOUNTING_NOTIFICATION_EMAILS:
            return Response({"detail": "No se ha configurado el correo del equipo contable. Conserve la solicitud pendiente y reintente."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        external_id = serializer.validated_data["external_id"]
        existing = ProducerRequest.objects.filter(external_id=external_id).first()
        if existing and existing.requested_by_id != request.user.pk:
            return Response({"detail": "Identificador ya registrado por otro usuario."}, status=status.HTTP_409_CONFLICT)
        item = existing or serializer.save(requested_by=request.user)
        if item.email_status != ProducerRequest.EmailStatus.SENT:
            body = (
                f"Solicitud de alta de productor (sin crear el productor automáticamente)\n"
                f"Conductor: {request.user.get_full_name() or request.user.username} ({request.user.username})\n"
                f"Nombre: {item.name}\nDocumento: {item.document_number}\nFinca: {item.farm_name}\n"
                f"Clasificación: {item.get_fiscal_category_display()}\nTipo documento: {item.document_type}\nProductos: {', '.join(item.requested_products)}\n"
                f"Teléfono: {item.phone}\nMunicipio: {item.municipality}\nVereda: {item.village}\n"
                f"Observaciones: {item.notes}\nReferencia: {item.external_id}\n"
                "Revise la información y cree el productor desde la plataforma si corresponde."
            )
            try:
                if send_mail("UBALAC · Solicitud de nuevo productor", body, settings.DEFAULT_FROM_EMAIL, settings.ACCOUNTING_NOTIFICATION_EMAILS, fail_silently=False) != 1:
                    raise RuntimeError("El proveedor de correo no confirmó el envío")
            except Exception:
                item.email_status = ProducerRequest.EmailStatus.FAILED
                item.save(update_fields=["email_status", "updated_at"])
                return Response({"detail": "No se pudo enviar el correo. La solicitud sigue pendiente; reintente sincronizar."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
            item.email_status = ProducerRequest.EmailStatus.SENT
            item.emailed_at = timezone.now()
            item.save(update_fields=["email_status", "emailed_at", "updated_at"])
        return Response(self.get_serializer(item).data, status=status.HTTP_200_OK if existing else status.HTTP_201_CREATED)


class HealthCheckView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = []

    def get(self, request):
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return Response({"status": "ok"})


class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ProductSerializer
    queryset = CollectionProduct.objects.filter(active=True)


class VehicleInspectionViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    serializer_class = VehicleInspectionSerializer
    permission_classes = [RoleWritePermission]
    write_roles = {User.Role.DRIVER, User.Role.COLLECTOR}
    queryset = VehicleInspection.objects.select_related("vehicle", "driver")

    def get_queryset(self):
        qs = super().get_queryset()
        if not (self.request.user.is_superuser or self.request.user.role in {User.Role.ADMIN, User.Role.SUPERVISOR}):
            qs = qs.filter(driver=self.request.user)
        return qs

    def create(self, request, *args, **kwargs):
        import uuid
        external_id = request.data.get("external_id")
        try:
            external_id = uuid.UUID(str(external_id))
        except (ValueError, TypeError):
            return Response({"detail": "external_id inválido"}, status=400)
        existing = VehicleInspection.objects.filter(external_id=external_id).first()
        if existing:
            if existing.driver_id != request.user.pk:
                return Response({"detail": "Identificador de otro conductor"}, status=409)
            return Response(self.get_serializer(existing).data)
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        from apps.operations.services.notifications import enqueue_notification
        from apps.auditlog.services import record_event
        from apps.auditlog.models import AuditEvent
        with transaction.atomic():
            item = serializer.save(driver=self.request.user)
            record_event(actor=self.request.user, action=AuditEvent.Action.CREATE, instance=item, request=self.request)
            if item.has_issues or not item.safe_to_operate:
                enqueue_notification(key=f"inspection:{item.pk}", subject="UBALAC · Novedad en inspección vehicular", body=f"Placa: {item.vehicle.plate}\nConductor: {self.request.user}\nNovedades: {item.observations}\nApto: {item.safe_to_operate}")


class SecureTokenView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle]

    def post(self, request):
        serializer = AuthTokenSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        if user.must_change_password:
            return Response(
                {"detail": "Debe cambiar la contraseña desde el portal web."},
                status=status.HTTP_403_FORBIDDEN,
            )
        profile = driver_profile(user) if user.role in {User.Role.DRIVER, User.Role.COLLECTOR} else None
        if profile and profile.device_id and request.headers.get("X-Device-ID") != profile.device_id:
            return Response({"detail": "Equipo no autorizado. Solicite al administrador que registre el ID de este dispositivo."}, status=status.HTTP_403_FORBIDDEN)
        with transaction.atomic():
            Token.objects.filter(user=user).delete()
            token = Token.objects.create(user=user)
            update_last_login(None, user)
        expires_at = timezone.now() + timedelta(hours=settings.API_TOKEN_TTL_HOURS)
        return Response(
            {
                "token": token.key,
                "expires_at": expires_at.isoformat(),
                "user": {"id": str(user.pk), "username": user.username, "role": user.role},
            }
        )


class ProducerViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ProducerSerializer
    permission_classes = [RoleWritePermission]
    queryset = Producer.objects.filter(active=True)
    search_fields = ["name", "document_number", "farm_name"]
    ordering_fields = ["name", "document_number"]

    def get_queryset(self):
        return assigned_producers(self.request.user)


class VehicleViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = VehicleSerializer
    permission_classes = [RoleWritePermission]
    queryset = Vehicle.objects.filter(active=True)
    search_fields = ["plate", "name"]
    ordering_fields = ["plate", "name"]

    def get_queryset(self):
        return assigned_vehicles(self.request.user)


class RouteViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = RouteSerializer
    permission_classes = [RoleWritePermission]
    queryset = Route.objects.filter(active=True)
    search_fields = ["name"]
    ordering_fields = ["name"]

    def get_queryset(self):
        return assigned_routes(self.request.user)


class DriverConfigurationView(APIView):
    """The authenticated driver only; never expose module or login passwords."""

    def get(self, request):
        if request.user.role not in {User.Role.DRIVER, User.Role.COLLECTOR}:
            return Response({"detail": "Disponible solo para conductores."}, status=status.HTTP_403_FORBIDDEN)
        user = request.user
        profile = driver_profile(user)
        return Response({
            "user": {"id": str(user.pk), "username": user.username, "name": user.get_full_name(), "email": user.email, "role": user.role},
            "document_number": profile.document_number if profile else "",
            "phone": profile.phone if profile else "",
            "device_registered": bool(profile and profile.device_id),
            "products": ProductSerializer(profile.products.filter(active=True) if profile and profile.products.exists() else CollectionProduct.objects.filter(active=True), many=True).data,
            "today_inspections": VehicleInspectionSerializer(VehicleInspection.objects.filter(driver=user, inspected_on=timezone.localdate()), many=True).data,
            "routes": RouteSerializer(assigned_routes(user), many=True).data,
            "vehicles": VehicleSerializer(Vehicle.objects.filter(active=True, driver=user), many=True).data,
            "producers": ProducerSerializer(assigned_producers(user), many=True).data,
            "schedules": RouteScheduleSerializer(RouteSchedule.objects.filter(driver=user, status=RouteSchedule.Status.PLANNED, scheduled_date__gte=timezone.localdate()).select_related("driver", "route", "vehicle").prefetch_related("producers").order_by("scheduled_date", "shift", "route__name"), many=True).data,
        })


class DriverScheduleViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = RouteScheduleSerializer
    permission_classes = [RoleWritePermission]
    queryset = RouteSchedule.objects.select_related("driver", "route", "vehicle").prefetch_related("producers")

    def get_queryset(self):
        qs = super().get_queryset().filter(status=RouteSchedule.Status.PLANNED)
        if not (self.request.user.is_superuser or self.request.user.role in {User.Role.ADMIN, User.Role.SUPERVISOR}):
            qs = qs.filter(driver=self.request.user)
        return qs.filter(scheduled_date__gte=timezone.localdate()).order_by("scheduled_date", "shift", "route__name")


class RouteTripViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = RouteTripSerializer
    permission_classes = [RoleWritePermission]
    write_roles = {User.Role.ADMIN, User.Role.SUPERVISOR, User.Role.COLLECTOR, User.Role.DRIVER}
    queryset = RouteTrip.objects.select_related("route", "vehicle", "driver")

    def get_queryset(self):
        auto_close_expired_trips()
        qs = super().get_queryset()
        if self.request.user.is_superuser or self.request.user.role in {User.Role.ADMIN, User.Role.SUPERVISOR}:
            return qs
        return qs.filter(driver=self.request.user)

    def create(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            trip = start_trip(user=request.user, route=serializer.validated_data["route"], vehicle=serializer.validated_data["vehicle"], product=serializer.validated_data.get("product"), inspection=serializer.validated_data.get("inspection"), request=request)
        except DjangoValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(trip).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        try:
            trip = self.get_object()
            if trip.ended_at:
                return Response(self.get_serializer(trip).data)
            trip = close_trip(trip=trip, user=request.user, request=request)
        except DjangoValidationError as exc:
            trip = self.get_object()
            if trip.ended_at:
                return Response(self.get_serializer(trip).data)
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(trip).data)


class MilkReceiptViewSet(viewsets.ModelViewSet):
    serializer_class = MilkReceiptSerializer
    permission_classes = [RoleWritePermission]
    write_roles = {User.Role.ADMIN, User.Role.SUPERVISOR, User.Role.COLLECTOR, User.Role.DRIVER}
    http_method_names = ["get", "post", "head", "options"]
    queryset = MilkReceipt.objects.select_related("producer", "vehicle", "route", "trip", "collected_by")
    filterset_fields = ["producer", "product", "vehicle", "status", "sync_status", "collected_at"]
    search_fields = ["internal_number", "producer__name", "vehicle__plate"]
    ordering_fields = ["collected_at", "liters", "created_at"]
    ordering = ["-collected_at"]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.user.role in {User.Role.DRIVER, User.Role.COLLECTOR} and not self.request.user.is_superuser:
            return qs.filter(collected_by=self.request.user)
        return qs

    def create(self, request, *args, **kwargs):
        external_id = request.data.get("external_id")
        if external_id:
            existing = MilkReceipt.objects.filter(external_id=external_id).first()
            if existing:
                if existing.collected_by_id != request.user.pk:
                    return Response({"detail": "El identificador de sincronización ya está en uso."}, status=status.HTTP_409_CONFLICT)
                return Response(self.get_serializer(existing).data, status=status.HTTP_200_OK)
        return super().create(request, *args, **kwargs)

    @action(detail=True, methods=["get"], url_path="voucher")
    def voucher(self, request, pk=None):
        receipt = self.get_object()
        return Response(
            {
                "document_type": "MILK_COLLECTION_RECEIPT",
                "copy_for": "PRODUCER",
                "receipt": self.get_serializer(receipt).data,
            }
        )
