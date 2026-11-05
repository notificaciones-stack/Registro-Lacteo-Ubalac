from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers, mixins, viewsets
from rest_framework.response import Response
from apps.api.v1.permissions import RoleWritePermission
from apps.operations.models import RouteTrip
from .models import FatigueSurvey, FuelEntry
from .services import visible_trips, save_record, WRITERS


class FleetSerializer(serializers.ModelSerializer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        self.fields['trip'].queryset = visible_trips(request.user) if request else RouteTrip.objects.none()

    def create(self, validated_data):
        try:
            return save_record(self.Meta.model, validated_data, self.context['request'].user, self.context['request'])
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc


class FatigueSerializer(FleetSerializer):
    expected_cycle = serializers.CharField(required=False, allow_blank=True, write_only=True)
    class Meta:
        model = FatigueSurvey
        fields = ['id', 'external_id', 'trip', 'expected_cycle', 'sleep_hours', 'sleepy', 'rested', 'fatigue', 'observations', 'commitment', 'has_risk', 'created_at']
        read_only_fields = ['id', 'has_risk', 'created_at']
        extra_kwargs = {'external_id': {'validators': []}}


class FuelSerializer(FleetSerializer):
    fuel_photo = serializers.CharField(write_only=True, max_length=5600000)
    invoice_photo = serializers.CharField(write_only=True, max_length=5600000)
    class Meta:
        model = FuelEntry
        fields = ['id', 'external_id', 'trip', 'fueled_at', 'gallons', 'total_price', 'odometer_km', 'full_tank', 'observations', 'fuel_photo', 'invoice_photo', 'created_at']
        read_only_fields = ['id', 'created_at']
        extra_kwargs = {'external_id': {'validators': []}}


class FleetViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    permission_classes = [RoleWritePermission]
    write_roles = WRITERS
    def get_queryset(self):
        return self.serializer_class.Meta.model.objects.filter(trip__in=visible_trips(self.request.user))


class FatigueViewSet(FleetViewSet):
    serializer_class = FatigueSerializer


class FuelViewSet(FleetViewSet):
    serializer_class = FuelSerializer
