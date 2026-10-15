import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Administrador"
        SUPERVISOR = "SUPERVISOR", "Supervisor"
        COLLECTOR = "COLLECTOR", "Recolector"
        DRIVER = "DRIVER", "Conductor"
        ACCOUNTING = "ACCOUNTING", "Contabilidad"
        LABORATORY = "LABORATORY", "Laboratorio"
        VIEWER = "VIEWER", "Consulta"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.VIEWER, db_index=True)
    must_change_password = models.BooleanField(default=False)

    class Meta:
        ordering = ["username"]

    @property
    def can_manage_master_data(self) -> bool:
        return self.is_superuser or self.role in {self.Role.ADMIN, self.Role.SUPERVISOR}

    @property
    def can_manage_drivers(self) -> bool:
        return self.is_superuser or self.role == self.Role.ADMIN

    @property
    def can_record_receipts(self) -> bool:
        return self.is_superuser or self.role in {
            self.Role.ADMIN,
            self.Role.SUPERVISOR,
            self.Role.COLLECTOR,
            self.Role.DRIVER,
        }

    @property
    def can_manage_weighbridge(self) -> bool:
        return self.is_superuser or self.role in {
            self.Role.ADMIN,
            self.Role.SUPERVISOR,
            self.Role.LABORATORY,
        }
