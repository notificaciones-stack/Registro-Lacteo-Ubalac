# UBALAC 1.0 · Productos, compras e inspección vehicular

## Instalación conservando los datos

1. Haga una copia de la base y de la versión anterior antes de actualizar.
2. Reemplace el código con este proyecto, conservando su base real y sus variables de entorno. No copie bases de prueba sobre la base real.
3. Active el entorno virtual y ejecute:

```powershell
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test apps
```

La migración agrega leche y suero, conserva los recibidos y recorridos anteriores como leche y habilita leche en los proveedores existentes. No inventa precios para registros históricos. Las nuevas inspecciones no se exigen retroactivamente a recorridos existentes, pero todo nuevo recorrido de conductor o recolector debe tener una inspección del día confirmada en la API.

## Configuración inicial

1. Como administrador, abra **Productos**. Leche y suero ya existen. Puede crear otros productos medidos en litros.
2. Abra **Retenciones e impuestos** y cree los conceptos con su porcentaje. Retención descuenta del bruto e impuesto adiciona al bruto. No se cargan tarifas fiscales predeterminadas.
3. Cree o edite el proveedor. La clasificación aparece primero. **Cuantías menores** permite omitir tipo y número de documento. **Documento soporte** y **Facturación electrónica** requieren ambos. El nombre sigue siendo necesario para identificarlo.
4. Marque los productos que entrega y establezca el precio por litro, independiente para cada producto. Asigne los conceptos fiscales. Solo el administrador puede asignarlos o cambiar su definición.
5. En Conductores configure productos, rutas, placas y productores. Si no limita los productos, el conductor ve los productos activos, conservando la compatibilidad con las cuentas anteriores.
6. Actualice el APK móvil. Inicie sesión y sincronice. Seleccione el vehículo, complete **Inspección**, envíela y después seleccione producto y abra el recorrido.

Cada recorrido tiene un producto para que el pesaje final no distribuya una sola medición entre leche y suero. Para otro producto, cierre el recorrido anterior, sincronice y abra otro. Un proveedor puede entregar ambos productos en recorridos independientes. Un vehículo no puede tener dos recorridos abiertos simultáneamente.

## Precios y liquidación

- Cada recibido captura el precio y los parámetros vigentes en la fecha/hora de recolección. Los reintentos offline consultan ese historial, no el precio del día en que llegan a la API.
- Bruto = litros para informe × precio histórico, en COP. Los conceptos porcentuales se calculan independientemente sobre el bruto, sin composición entre impuestos. El redondeo es por recibido, a dos decimales, con ROUND_HALF_UP.
- Neto = bruto − retenciones + impuestos. No incluye automáticamente umbrales, UVT, tarifas legales, reglas contables externas ni impuestos compuestos. Configure las tarifas con su responsable contable.
- Si laboratorio validó báscula, la liquidación usa los litros reales distribuidos proporcionalmente, como ya lo hacía el módulo de informes. El precio permanece histórico. Si se corrige báscula, el informe se recalcula y la revisión queda registrada.
- Los anulados se excluyen del cálculo y permanecen en historial.
- Los recibidos sin precio no se suman como $0: aparecen expresamente como pendientes de valoración. Desde el detalle del proveedor, el administrador puede **valorar recibidos pendientes** del rango con las condiciones actuales, después de marcar una confirmación. Esta acción queda auditada y no cambia recibidos que ya tenían precio.
- Abra el nombre del proveedor o **Detalle y comprobante** en Informes. Verá productos, precios, rango de fechas, cada recibido, bruto, conceptos, descuentos y neto. **Comprobante para imprimir / PDF** abre la vista imprimible. Use Imprimir y elija Guardar como PDF en el navegador.
- Estos comprobantes son informativos. La clasificación fiscal no emite facturación electrónica ni documento soporte ante DIAN, ni acredita un pago.

## Excel

Exporte Productores para obtener la plantilla vigente. Mantiene las columnas anteriores y agrega clasificación, productos, retenciones, ID de proveedor y una columna de precio por cada producto del catálogo. No usa CSV ni separación de punto y coma.

- En Productos indique códigos del catálogo, por ejemplo `leche|suero` dentro de una celda. Los precios siempre tienen sus columnas separadas.
- Las retenciones se identifican por sus nombres exactos, separados por `|` si aplica más de una.
- Para crear un proveedor deje ID proveedor vacío. Para actualizar uno sin documento utilice su ID exportado. El nombre solo sirve como alternativa si identifica de forma única al proveedor.
- Los archivos anteriores siguen siendo compatibles y pueden dejar valores monetarios pendientes.
- La importación es atómica: un error revierte todas sus escrituras.
- Recolecciones agrega Producto y Precio histórico COP/L. Producto usa el código. El precio exportado es informativo: la importación de recibidos consulta el historial de condiciones para no aceptar un precio arbitrario desde Excel.
- Los informes incluyen hojas adicionales de liquidación, conceptos y detalle económico, además de todas las hojas operativas anteriores.

## Inspección y auditoría

La inspección conserva conductor, vehículo, fecha, kilometraje, frenos, llantas, luces, fluidos, higiene de tanque, documentación, equipo de carretera, novedades y declaración de aptitud. Las fallas en frenos, llantas, higiene o documentación impiden declarar el vehículo apto. Las demás novedades requieren observaciones. Se utiliza la inspección más reciente del día para ese conductor y vehículo.

La web incluye un módulo separado de inspecciones con filtros por fechas y novedades. Conductores ven las propias; administración y supervisión pueden revisar el historial. No se editan inspecciones enviadas desde el móvil: una nueva evaluación genera otro registro.

La eliminación definitiva en Django admin queda habilitada únicamente al superusuario, incluso para relaciones protegidas. La pantalla de confirmación muestra los registros dependientes que también se eliminarán. Es una eliminación en cascada, no un modo de conservar registros huérfanos. La web operativa y la API mantienen sus protecciones y anulaciones. **Use una copia de seguridad antes de eliminar datos reales.**

## Correos

La app no almacena credenciales de correo. Envía las solicitudes a la API, que notifica a contabilidad. Las solicitudes fallidas siguen guardadas y la app conserva pendientes hasta la confirmación. Las anomalías de inspección y los grupos de recibidos duplicados generan una cola persistente de correos.

Variables:

```text
ACCOUNTING_NOTIFICATION_EMAILS=contabilidad@example.com
OPERATIONS_NOTIFICATION_EMAILS=operaciones@example.com
DJANGO_DEFAULT_FROM_EMAIL=notificaciones@dominio-verificado.com
```

Para Railway puede usar HTTPS con Resend:

```text
DJANGO_EMAIL_BACKEND=apps.operations.email_backend.ResendEmailBackend
RESEND_API_KEY=clave-solo-del-servidor
```

Para SMTP configure las variables DJANGO_EMAIL_HOST, PORT, HOST_USER, HOST_PASSWORD y USE_TLS del archivo de ejemplo. Railway limita SMTP a Pro y superiores; HTTPS funciona en todos los planes según su documentación. Verifique dominio remitente y permisos del proveedor.

```powershell
python manage.py check_notifications
# Este siguiente comando SÍ envía un correo de prueba:
python manage.py check_notifications --send-test
python manage.py process_notifications
```

La validación sin `--send-test` no comprueba credenciales remotas ni recepción. Para la prueba local use `django.core.mail.backends.console.EmailBackend`; en producción el control de despliegue rechaza transportes de consola, memoria o dummy. La cola admite reintentos. La entrega final al buzón debe comprobarse con credenciales reales y revisando spam.

## Railway

1. Cree un proyecto y un servicio PostgreSQL. Suba el contenido de `ubalac_web` como raíz del servicio web.
2. El proyecto incluye Dockerfile y railway.json. Configure las variables de `.env.railway.example` en Railway, cambiando dominio, destinatarios, remitente y credenciales. Utilice una referencia al DATABASE_URL del servicio PostgreSQL.
3. Genere una clave con `python -c "import secrets; print(secrets.token_urlsafe(64))"` y guárdela como DJANGO_SECRET_KEY. Si está actualizando un servidor existente, conserve la clave anterior: también protege el almacén actual de claves de conductor.
4. Configure DJANGO_ALLOWED_HOSTS con su dominio sin protocolo y `healthcheck.railway.app`. CSRF_TRUSTED_ORIGINS requiere el dominio completo con HTTPS.
5. El predeploy aplica migraciones y comprueba el correo. Gunicorn usa el PORT de Railway. WhiteNoise sirve estáticos. El endpoint `/api/v1/health/` comprueba la base de datos.
6. Cree el administrador con `python manage.py createsuperuser` desde el entorno del servicio (no ejecute el comando contra una base local pensando que es producción).
7. Agregue un segundo servicio Cron usando el mismo código, variables y PostgreSQL. En su configuración seleccione `railway.cron.example.json` como archivo de configuración. Programa: `*/5 * * * *`. Ejecuta `close_expired_trips` y `process_notifications`. El cierre se registra con hora 23:59 de Colombia aunque el proceso lo ejecute unos minutos después. Railway interpreta el cron en UTC.
8. Ejecute `python manage.py check --deploy`, valide correo real, permisos y una copia/restauración de PostgreSQL antes del piloto. No use SQLite ni `runserver` en Railway.
9. No suba `.env`, la base local, entornos virtuales, node_modules ni claves privadas al repositorio.

El móvil se compila en EAS, no en Railway. Railway aloja la web y API. Configure EXPO_PUBLIC_API_URL con `https://su-dominio.up.railway.app`, sin `/api/v1`, y genere un APK preview nuevo. SQLCipher y BLE requieren el APK propio, no Expo Go.

## Validación de aceptación

1. Cree un proveedor de cuantías menores sin documento y habilite leche y suero con distintos precios.
2. Asigne una retención de prueba y compruebe que supervisor y conductor no acceden a su módulo de configuración.
3. Intente abrir un recorrido sin inspección: la API debe rechazarlo.
4. Complete y envíe inspección, abra recorrido de leche, capture e imprima un recibido sin red. Cierre y vuelva a abrir la app: el pendiente debe conservarse.
5. Cambie el precio desde la web, recupere red y sincronice: el recibido capturado antes debe usar el precio anterior.
6. Cierre y sincronice. Abra otro recorrido para suero y pruebe el filtro por producto y la tirilla.
7. Genere dos recibidos del mismo proveedor en el mismo recorrido, resuelva la alerta desde web y sincronice: el móvil retira el anulado, la web conserva historial.
8. Valide báscula. Compruebe litros reales, ajuste económico, desglose por proveedor, Excel y comprobante imprimible.
9. Revise correos, fallas de envío, reintento por cron, permisos y restauración antes de operar con datos reales.

Fuentes técnicas: https://docs.railway.com/guides/django · https://docs.railway.com/cron-jobs · https://docs.railway.com/networking/outbound-networking · https://docs.expo.dev/versions/v57.0.0/sdk/sqlite/ · https://github.com/resend/resend-openapi
