> Actualización 1.0: consulte primero ACTUALIZACION_1_0.md para migración, precios, productos, inspección y Railway. VALIDACION_1_0.md detalla las pruebas y sus límites.

# UBALAC Web MVP — recibidos y comprobantes

Aplicación web para registrar la leche recogida a cada proveedor y generar inmediatamente un **comprobante de recolección**. El comprobante puede imprimirse en formato térmico de 58 o 80 mm, o guardarse como PDF desde el navegador.

El sistema no calcula valores monetarios: registra la cantidad realmente recogida y entrega al proveedor una constancia trazable.

## Incluido

- Inicio de sesión, cambio obligatorio de claves temporales y roles de acceso.
- Productores, rutas y vehículos con activación/inactivación; finca, vereda, conductor y datos de soporte.
- Importación y exportación Excel por columnas desde la plataforma y el panel administrativo.
- Recorridos con apertura y cierre por conductor, y tablero filtrable de producción y tiempos.
- Reapertura excepcional de recorridos desde la web por administración o supervisión, durante el mismo día y con motivo auditado.
- Alertas de productores con más de un recibido por recorrido: se conserva el seleccionado y los demás quedan anulados con motivo e historial.
- Cierre de báscula por laboratorio: peso bruto, tara, densidad, litros reales, pérdida/ganancia, tolerancia, historial de revisiones y ajuste trazable de informes.
- Recibidos con consecutivo anual, fecha, proveedor, finca, vehículo, recolector, litros y observaciones.
- Comprobante individual para el proveedor con código UUID de verificación y espacios de firma.
- Diseño de impresión para tirilla térmica de 58/80 mm y opción de guardar como PDF.
- Anulación lógica con responsable, fecha y motivo; nunca se elimina el histórico.
- Auditoría de altas, cambios, activaciones y anulaciones.
- Panel responsivo y API `/api/v1/` preparada para la aplicación móvil.
- Reintentos idempotentes por `external_id` para no duplicar registros al recuperar conectividad.
- Configuración separada para desarrollo/producción, PostgreSQL, Docker y Railway.
- Pruebas automáticas, auditoría de dependencias y CI.

## Ejecución local

Requisitos: Python 3.12+.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
set -a; source .env; set +a
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

La configuración local usa SQLite si no se define `DATABASE_URL`. Para PostgreSQL local:

```bash
docker compose up -d db
export DATABASE_URL=postgresql://ubalac:ubalac_local_password@localhost:5432/ubalac
python manage.py migrate
```

Abra `http://127.0.0.1:8000/`. Desde el detalle seleccione **Comprobante del proveedor**, elija 58 u 80 mm y después la impresora térmica o “Guardar como PDF”.

## Validación

```bash
python manage.py check
python manage.py test
python manage.py makemigrations --check --dry-run
```

## Documentación

- [Arquitectura](docs/ARCHITECTURE.md)
- [Seguridad](docs/SECURITY.md)
- [Plan de entrega en 14 días](docs/PLAN_14_DIAS.md)
- [API para aplicación móvil](docs/API.md)
- [Configuración de conductores y equipos móviles](docs/DRIVERS_MOBILE_CONFIGURATION.md)
- [Despliegue en Railway](docs/DEPLOY_RAILWAY.md)
- [Carga masiva, permisos y campos de la plantilla](docs/IMPORT_EXPORT.md)
- [Recorridos e informes](docs/REPORTS_AND_TRIPS.md)
- [Báscula y validación de laboratorio](docs/WEIGHBRIDGE.md)
