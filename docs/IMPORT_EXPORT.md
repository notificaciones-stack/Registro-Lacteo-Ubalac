# Carga y exportación de datos

## Puesta en marcha

Después de actualizar el código, instale dependencias con `pip install -r requirements.txt` y ejecute `python manage.py migrate`. Las migraciones `operations.0002` y `operations.0003`, además de `accounts.0002`, incorporan rutas, recorridos y el rol Conductor. No eliminan recibidos anteriores; sus relaciones nuevas son opcionales.

Entre en **Rutas**, **Productores**, **Vehículos** o **Recibidos**. Cada lista ofrece **Exportar Excel**. Los roles habilitados ven **Importar Excel**. En el admin de Django, los mismos accesos están encima de las listas; abren las pantallas protegidas de la plataforma.

| Función | Administrador | Supervisor | Conductor | Recolector | Contabilidad | Consulta |
| --- | --- | --- | --- | --- | --- | --- |
| Importar rutas, productores y vehículos | Sí | Sí | No | No | No | No |
| Importar recibidos históricos | Sí | No | No | No | No | No |
| Exportar Excel | Sí | Sí | Sí | Sí | Sí | Sí |

Un superusuario tiene permisos de importación. Los enlaces ocultos no sustituyen el control del servidor: las rutas responden 403 a roles no autorizados. El acceso al admin de Django requiere también `is_staff` y permisos propios de Django.

## Orden recomendado y columnas

1. **Rutas:** hoja `Rutas` con `Ruta`, `Descripción` y `Estado` opcional; o columna `Ruta` de `Vehículos`. Se consolidan nombres repetidos.
2. **Productores:** hoja `Productores`; documento, nombre, finca, teléfono, municipio, vereda, observaciones y `Estado` opcional. Clave: tipo y número de documento.
3. **Vehículos:** hoja `Vehículos`; placa, ruta opcional, conductor, documento, teléfono, capacidad y observaciones. Puede agregar `Usuario conductor`, `Nombre del vehículo` y `Estado`. Clave: placa. Si la ruta indicada no existe, se crea. El usuario conductor debe existir con rol Conductor o Recolector.
4. **Recolecciones:** hoja `Recolecciones`; ruta, ID, productor, placa, fecha, hora, litros, estado, soporte, medio de pago, número de soporte y observaciones. Requiere productor por documento o nombre único, vehículo existente, fecha `AAAA-MM-DD`, hora `HH:MM`, litros positivos, estado confirmado e ID único. Se crea como recibido de origen `IMPORT` con consecutivo propio y auditoría. Una anulación debe realizarse en la plataforma.

El Excel acepta hasta 5 MB y 5000 filas. Valida todas las filas antes de guardar; si alguna falla, no guarda ninguna. Las altas y actualizaciones de catálogos generan eventos de auditoría. Al importar de nuevo, productores, vehículos y rutas se actualizan por su clave. Un ID de recolección ya importado se rechaza para evitar duplicados. La exportación genera un `.xlsx` con hoja, columnas, encabezado, autofiltro y primera fila fija. Los catálogos pueden editarse y volver a importarse en ese formato; los recibidos existentes se mantienen únicos y no se duplican.

La plantilla proporcionada trae 11 productores y 5 rutas válidas. En `Vehículos` hay una fila con conductor sin placa: debe completarse o quitarse antes de importar la hoja. Las recolecciones de ejemplo carecen de placa u hora concreta en varias filas; complete esos datos y confirme el productor antes de importar. El texto `AM` o `PM` por sí solo no representa una hora. El campo `Medio de pago` se conserva como referencia informativa: el comprobante registra litros y no emite factura electrónica ni calcula valores.

## Estructura técnica

- `apps/operations/models.py`: `Route`, `RouteTrip`, campos nuevos de `Producer`, `Vehicle` y `MilkReceipt`.
- `apps/operations/forms.py` y `views.py`: formularios y pantallas protegidas de listas, edición, importación y exportación.
- `apps/operations/services/bulk.py`: lectura y salida Excel, correspondencia de columnas, validación y actualización transaccional.
- `apps/operations/admin.py`: accesos en listas administrativas.
- `apps/api/v1/`: consulta de rutas, productores y vehículos, y recibidos con nuevos campos. La creación móvil conserva el flujo anterior; la ruta del vehículo se asigna por defecto cuando no se envía una.
- `templates/operations/` y `static/css/app.css`: vistas responsivas, acciones masivas y movimientos suaves con respeto a la preferencia de movimiento reducido.

Para verificar: `python manage.py check`, `python manage.py makemigrations --check --dry-run` y `python manage.py test`.
