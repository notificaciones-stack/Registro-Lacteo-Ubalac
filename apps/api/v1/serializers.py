from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.operations.models import CollectionProduct, VehicleInspection, MilkReceipt, Producer, ProducerRequest, Route, RouteTrip, Vehicle


class ProducerRequestSerializer(serializers.ModelSerializer):
    external_id = serializers.UUIDField(validators=[])

    def validate(self, attrs):
        category = attrs.get("fiscal_category", "SUPPORT")
        if category != "SMALL" and not attrs.get("document_number", "").strip():
            raise serializers.ValidationError({"document_number": "Indique documento para esta clasificación."})
        if category != "SMALL" and not attrs.get("document_type"):
            attrs["document_type"] = "CC"  # compatibility with older mobile requests
        codes = attrs.get("requested_products", [])
        if not isinstance(codes, list) or not all(isinstance(code, str) for code in codes) or len(codes) > 100:
            raise serializers.ValidationError({"requested_products": "Seleccione una lista de códigos de producto."})
        if set(codes) - set(CollectionProduct.objects.filter(active=True).values_list("code", flat=True)):
            raise serializers.ValidationError({"requested_products": "Producto desconocido o inactivo."})
        return attrs

    class Meta:
        model = ProducerRequest
        fields = ["id", "external_id", "name", "fiscal_category", "document_type", "requested_products", "document_number", "farm_name", "phone", "municipality", "village", "notes", "email_status", "emailed_at", "created_at"]
        read_only_fields = ["id", "email_status", "emailed_at", "created_at"]
from apps.operations.services import create_receipt


class ProducerSerializer(serializers.ModelSerializer):
    product_prices = serializers.SerializerMethodField()

    def get_product_prices(self, obj):
        return [{"product": str(p.product_id), "product_name": p.product.name, "unit_price": str(p.unit_price) if p.unit_price is not None else None} for p in obj.product_prices.select_related("product").filter(product__active=True)]

    class Meta:
        model = Producer
        fields = ["id", "fiscal_category", "document_type", "document_number", "name", "farm_name", "phone", "municipality", "village", "notes", "active", "product_prices", "assigned_driver", "assigned_route", "assigned_vehicle"]


class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = CollectionProduct
        fields = ["id", "code", "name", "active"]


class VehicleInspectionSerializer(serializers.ModelSerializer):
    external_id = serializers.UUIDField(validators=[])
    vehicle_plate = serializers.CharField(source="vehicle.plate", read_only=True)

    class Meta:
        model = VehicleInspection
        fields = ["id", "external_id", "vehicle", "vehicle_plate", "inspected_on", "odometer_km", "brakes", "tires", "lights", "fluids", "tank_hygiene", "documents", "safety_kit", "observations", "safe_to_operate", "created_at"]
        read_only_fields = ["id", "inspected_on", "created_at"]

    def validate(self, attrs):
        from apps.operations.assignments import assigned_vehicles
        if not assigned_vehicles(self.context["request"].user).filter(pk=attrs["vehicle"].pk).exists():
            raise serializers.ValidationError("Vehículo no asignado a este conductor.")
        instance = VehicleInspection(**attrs, driver=self.context["request"].user)
        try:
            instance.full_clean(exclude=["external_id"])
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict if hasattr(exc, "message_dict") else exc.messages)
        return attrs


class RouteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Route
        fields = ["id", "name", "description", "active"]


class VehicleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vehicle
        fields = ["id", "plate", "route", "name", "driver", "driver_name", "driver_document", "driver_phone", "capacity_liters", "notes", "active"]


class RouteTripSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    route_name = serializers.CharField(source="route.name", read_only=True)
    vehicle_plate = serializers.CharField(source="vehicle.plate", read_only=True)
    driver_name = serializers.CharField(source="driver.get_full_name", read_only=True)

    class Meta:
        model = RouteTrip
        fields = ["id", "product", "product_name", "inspection", "route", "route_name", "vehicle", "vehicle_plate", "driver", "driver_name", "started_at", "ended_at", "reopened_at", "notes"]
        read_only_fields = ["id", "driver", "driver_name", "started_at", "ended_at", "reopened_at"]


class MilkReceiptSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    amounts = serializers.SerializerMethodField()

    def get_amounts(self, obj):
        from apps.operations.services.pricing import receipt_amounts
        return receipt_amounts(obj)
    external_id = serializers.UUIDField(required=False, validators=[])
    collected_by_username = serializers.CharField(source="collected_by.username", read_only=True)
    collected_by_name = serializers.SerializerMethodField()
    producer_name = serializers.CharField(source="producer.name", read_only=True)
    producer_document = serializers.SerializerMethodField()
    farm_name = serializers.CharField(source="producer.farm_name", read_only=True)
    vehicle_plate = serializers.CharField(source="vehicle.plate", read_only=True)
    vehicle_name = serializers.CharField(source="vehicle.name", read_only=True)
    route_name = serializers.CharField(source="route.name", read_only=True, default="")

    class Meta:
        model = MilkReceipt
        fields = [
            "id",
            "external_id",
            "internal_number",
            "producer",
            "product", "product_name", "unit_price", "amounts",
            "producer_name",
            "producer_document",
            "farm_name",
            "route",
            "route_name",
            "trip",
            "vehicle",
            "vehicle_plate",
            "vehicle_name",
            "collected_by_username",
            "collected_by_name",
            "collected_at",
            "liters",
            "collection_shift",
            "source_reference",
            "support_type",
            "payment_method",
            "support_number",
            "observations",
            "source",
            "status",
            "sync_status",
            "created_at",
        ]
        read_only_fields = [
            "unit_price",
            "id",
            "internal_number",
            "collected_by_username",
            "producer_name",
            "producer_document",
            "farm_name",
            "vehicle_plate",
            "vehicle_name",
            "route_name",
            "trip",
            "source",
            "source_reference",
            "status",
            "sync_status",
            "created_at",
        ]

    def get_producer_document(self, obj):
        return f"{obj.producer.get_document_type_display()} {obj.producer.document_number}"

    def get_collected_by_name(self, obj):
        return obj.collected_by.get_full_name() or obj.collected_by.username

    def validate_producer(self, producer):
        if not producer.active:
            raise serializers.ValidationError("El productor está inactivo.")
        return producer

    def validate_vehicle(self, vehicle):
        if not vehicle.active:
            raise serializers.ValidationError("El vehículo está inactivo.")
        return vehicle

    def create(self, validated_data):
        request = self.context["request"]
        external_id = validated_data.pop("external_id", None)
        try:
            return create_receipt(
                user=request.user,
                request=request,
                external_id=external_id,
                source=MilkReceipt.Source.MOBILE,
                sync_status=MilkReceipt.SyncStatus.SYNCED,
                **validated_data,
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict if hasattr(exc, "message_dict") else exc.messages)
