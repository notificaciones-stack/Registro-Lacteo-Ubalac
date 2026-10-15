# UBALAC Web MVP — versión 0.2.0

Fecha de corte: 24 de septiembre de 2026.

## Alcance corregido

El documento central es el **recibido de leche**. A partir de él se genera una constancia para entregar al proveedor con productor, documento, finca, municipio, fecha, vehículo, recolector, litros, observaciones, consecutivo y código de verificación.

No se incluyen precios, valores, impuestos ni cálculos monetarios.

## Entrega

- Panel web responsivo con usuarios, roles, productores, vehículos y recibidos.
- Comprobante imprimible en tirilla térmica de 58/80 mm o PDF.
- API móvil con creación idempotente y endpoint estructurado del comprobante.
- Auditoría, anulaciones lógicas, seguridad de sesión/token y producción estricta.
- Plan acelerado de 14 días y guías técnicas.

## Evidencia automatizada

- 19 pruebas automáticas aprobadas.
- Chequeos normal y de despliegue sin observaciones.
- Migraciones sin cambios pendientes.
- Auditoría de dependencias sin vulnerabilidades conocidas.

Las pruebas automáticas usan SQLite por velocidad. Antes del go-live se debe probar impresión física y backup/restauración contra PostgreSQL en staging.
# v0.3.0 — catálogos e importación

- Nuevos modelos de rutas y campos de vereda, conductor y referencias de soporte conforme a la plantilla.
- Carga Excel de rutas, productores, vehículos y recibidos con validación por fila, auditoría y transacción completa.
- Exportación CSV y acciones en la plataforma y el admin, con importación limitada por rol.
- API ampliada con consulta de rutas y campos nuevos de recibidos.
- Interfaz renovada, adaptable a móvil y con movimiento reducido según preferencia del sistema.
- Migración `operations.0002`; ejecutar `python manage.py migrate` al instalar la actualización.
# v0.4.0 — Excel, recorridos e informes

- Exportaciones reales `.xlsx` con encabezados y columnas; se eliminó CSV.
- Rol Conductor, asignación de vehículo, apertura y cierre de recorridos desde web y API con horas del servidor.
- Recibidos vinculados a recorridos activos; informes visuales con filtros y descarga Excel de cinco hojas.
- Migraciones `accounts.0002` y `operations.0003`. Ejecutar `python manage.py migrate` al actualizar.
# v0.4.1 — corrección de importación masiva de recibidos

- Las recolecciones de un mismo vehículo se validan por su ID de recolección, no por la placa. Esto permite importar periodos completos con recorridos diarios.
- Verificado con un Excel ficticio de agosto y septiembre de 2026: 3 rutas, 5 productores, 3 vehículos y 118 recibidos.
- No requiere migraciones adicionales respecto a v0.4.0.

# v0.4.2 — informes de recorridos y diseño móvil

- Informes abre en el mes actual; el resumen muestra recorridos recientes, cerrados hoy y abiertos.
- Recorridos cerrados se atribuyen al día del cierre, también si empezaron el día anterior y si no tuvieron recibidos.
- Barras diarias proporcionadas al máximo del periodo, con litros, porcentaje del total y escala explícita.
- Filtros de informes en barra lateral fija en escritorio y sección plegable en pantallas estrechas; tablas y tarjetas adaptadas a móvil.
- Pruebas de recorridos sin recibidos, cierre entre días y escala del gráfico. Sin nuevas migraciones.

# v0.4.3 — rango único de fechas

- Se retiró el selector de periodos de Informes. Los campos obligatorios «Desde» y «Hasta» determinan toda la consulta y el Excel.
- El rango inicial va del primer día del mes actual hasta hoy; «Analizar hoy» envía ambas fechas explícitamente.
- Sin nuevas migraciones.

# v0.5.0 — módulo Conductores y configuración móvil

- Clave adicional del módulo establecida exclusivamente en admin, almacenada como hash, con caducidad de acceso y límite de intentos.
- Ficha editable en la plataforma para datos, ID de equipo, múltiples rutas, placas y productores; contraseña de inicio de sesión administrada en admin.
- «Mi configuración» de solo lectura y API `GET /api/v1/drivers/me/configuration/` para el conductor autenticado.
- La API y el servicio validan rutas/productores asignados y el ID de equipo cuando se configure; el rol Conductor solo consulta sus propios recibidos.
- Migración `operations.0004`; ejecutar `python manage.py migrate` antes de usar el módulo.

# v0.5.1 — alta y contraseñas de conductores en la plataforma

- El módulo protegido permite crear al conductor con datos, contraseña, equipo, múltiples rutas, placas y productores en una sola pantalla.
- Restablecimiento de contraseña en la ficha; revoca tokens móviles existentes. La contraseña nueva aparece una sola vez, oculta inicialmente con opción de mostrarla; las anteriores no pueden recuperarse del hash.
- La clave adicional del módulo continúa gestionándose solo desde admin. Sin nuevas migraciones respecto a v0.5.0.

# v0.5.2 — consulta protegida y confirmación de asignaciones

- La ficha protegida muestra la contraseña del conductor en una casilla oculta con botón «Mostrar» cuando fue creada o restablecida con esta versión. Se guarda cifrada además del hash; las cuentas antiguas requieren restablecimiento.
- Mínimo de 6 caracteres para la clave adicional del módulo y contraseñas nuevas de conductores; la política de otros usuarios conserva su mínimo anterior.
- Rutas, placas y productores se seleccionan mediante casillas marcadas o vacías. Antes de guardar, un diálogo resume las modificaciones y solicita confirmación.
- Migración `operations.0005` y dependencia `cryptography==46.0.0`. Ejecute `pip install -r requirements.txt` y `python manage.py migrate`.
