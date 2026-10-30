import uuid
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("operations", "0011_producer_assignments"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(name="RouteSchedule", fields=[
            ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
            ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
            ("scheduled_date", models.DateField(db_index=True)),
            ("shift", models.CharField(choices=[("DAY", "Día"), ("NIGHT", "Noche")], db_index=True, default="DAY", max_length=10)),
            ("collection_type", models.CharField(choices=[("MILK", "Leche"), ("WHEY", "Suero")], db_index=True, default="MILK", max_length=10)),
            ("status", models.CharField(choices=[("PLANNED", "Programada"), ("COMPLETED", "Cumplida"), ("CANCELLED", "Cancelada")], db_index=True, default="PLANNED", max_length=12)),
            ("notes", models.TextField(blank=True, max_length=1500)),
            ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="created_route_schedules", to=settings.AUTH_USER_MODEL)),
            ("driver", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="route_schedules", to=settings.AUTH_USER_MODEL)),
            ("route", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="schedules", to="operations.route")),
            ("updated_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="updated_route_schedules", to=settings.AUTH_USER_MODEL)),
            ("vehicle", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="schedules", to="operations.vehicle")),
            ("producers", models.ManyToManyField(related_name="route_schedules", to="operations.producer")),
        ], options={"ordering": ["-scheduled_date", "shift", "route__name"]}),
        migrations.AddIndex(model_name="routeschedule", index=models.Index(fields=["scheduled_date", "shift", "status"], name="schedule_day_shift_idx")),
        migrations.CreateModel(name="RouteScheduleHistory", fields=[
            ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
            ("version", models.PositiveIntegerField()), ("changed_at", models.DateTimeField(auto_now_add=True, db_index=True)),
            ("reason", models.CharField(blank=True, max_length=500)), ("snapshot", models.JSONField(default=dict)),
            ("changed_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="route_schedule_changes", to=settings.AUTH_USER_MODEL)),
            ("schedule", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="history", to="operations.routeschedule")),
        ], options={"ordering": ["-version"]}),
        migrations.AddConstraint(model_name="routeschedulehistory", constraint=models.UniqueConstraint(fields=("schedule", "version"), name="unique_schedule_history_version")),
    ]
