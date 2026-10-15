from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("operations", "0006_producerrequest"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(model_name="routetrip", name="reopened_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="routetrip", name="reopen_reason", field=models.CharField(blank=True, max_length=500)),
        migrations.AddField(model_name="routetrip", name="reopened_by", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="reopened_route_trips", to=settings.AUTH_USER_MODEL)),
    ]
