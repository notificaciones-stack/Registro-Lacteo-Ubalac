# Actualización de web y móvil · 27 de octubre de 2026

## Orden de actualización

1. Respalde la base PostgreSQL de producción. Conserve las variables y credenciales de Railway.
2. Actualice el código web con este paquete, sin sustituir su configuración de entorno por valores locales.
3. Ejecute la migración nueva antes de utilizar formularios o API:

```bash
python manage.py migrate --settings=config.settings.production
python manage.py collectstatic --noinput --settings=config.settings.production
```

Si su comando de arranque ya ejecuta estas instrucciones, revise en el despliegue que `operations.0011_producer_assignments` termine correctamente. No vuelva a crear la base de datos.

4. Revise un proveedor en la web, sus asignaciones y los productos/precios existentes.
5. Compile e instale la nueva aplicación móvil después de actualizar la API. Actualice sobre la instalación existente con el mismo identificador y firma. No desinstale ni borre almacenamiento si hay datos pendientes.

## Asignaciones de proveedores

El formulario añade conductor, ruta y placa predeterminados. Al seleccionar conductor, ruta o placa se completan las relaciones únicas existentes. Cuando hay varias opciones, el usuario elige; el sistema no asigna una ruta arbitraria. Se rechazan placas de otro conductor o de otra ruta. Los datos personales del proveedor no se copian del conductor.

Las asignaciones están disponibles en Django admin, listado web, API y configuración móvil. Los formularios de recibidos sugieren ruta y placa del proveedor. La ficha del vehículo completa nombre, documento y teléfono con la información del conductor. Los cambios desde la configuración del conductor también actualizan su ficha de vehículo.

La exportación/importación Excel agrega `Usuario conductor asignado`, `Ruta asignada` y `Placa asignada`. Use nombres de ruta, usuario y placa existentes. Las plantillas antiguas siguen siendo válidas: las columnas ausentes no borran asignaciones. Los conductores mantienen la selección de proveedores existente, limitada por las asignaciones explícitas nuevas. Un proveedor asignado directamente al conductor también aparece en su configuración.

## Borrado desde Django admin

La eliminación extendida se aplica a todos los modelos registrados en el admin y solo al superusuario. La confirmación muestra los registros afectados, incluidos dependientes protegidos. Relaciones opcionales SET_NULL se desvinculan; dependencias obligatorias se borran en una transacción. Se registra la acción de borrado. No se ejecutó ningún borrado en producción.

## Recorridos y productos

Cada recibido permite elegir un producto habilitado simultáneamente para el proveedor y el conductor. Un recorrido admite leche y suero. Se conservan precios históricos, retenciones, consecutivos, impresión y sincronización por UUID.

Puede registrar repetidos. La app pide confirmación cuando encuentra otro recibido del mismo proveedor/producto/recorrido; la web mantiene la revisión administrativa. Elegir un recibido válido de leche no anula el suero. Los anulados permanecen en la web y se retiran del teléfono al sincronizar su confirmación.

Los filtros de producto incluyen recorridos mixtos y calculan la varianza proporcional únicamente de los recibidos filtrados. La báscula conserva el método existente: un pesaje total por recorrido y reparto proporcional de la variación. En cargas mixtas se muestra esta condición expresamente; un pesaje global no mide los litros reales de cada producto por separado.

## Inspección y base local

La app presenta el siguiente paso: inspección obligatoria de hoy, inicio de día, recolección y sincronización. Cambiar de placa exige su propia inspección apta. Novedades aparecen con texto, símbolo y color tanto en web como móvil. Las fallas críticas mantienen el bloqueo vigente.

Se serializa la apertura y el acceso SQLite. Las transacciones usan la conexión que ya recibió la clave SQLCipher, evitando abrir otra sin clave al limpiar una jornada. La recuperación de un mismo recorrido es idempotente y no se acepta captura tras el cierre. Las migraciones son aditivas y no cambian la clave existente. Un error de cifrado no provoca borrado ni reinicialización destructiva.

Expo Go sigue sin ser compatible con SQLCipher. Use un APK o una compilación de desarrollo con los módulos nativos incluidos.

## Prueba de aceptación

1. Cree proveedor seleccionando solo conductor con una ruta/placa: confirme autocompletado. Repita con varias rutas y compruebe que exige elegir la combinación deseada.
2. Exporte e importe Excel y compruebe asignaciones y precios.
3. Entre en la app: siga el aviso de inspección. Registre una novedad y compruebe aviso en web. Una falla crítica no debe permitir declarar apto.
4. Con inspección apta, inicie día. Registre leche, suero y otro recibido de leche al mismo proveedor. Debe aparecer confirmación y una sola alerta de leche en web.
5. Sin conexión registre otro proveedor. Cierre y abra la app: los pendientes deben conservarse. Reconecte y sincronice.
6. En web conserve un recibido duplicado y anule los restantes con motivo. Sincronice y verifique historial web y móvil.
7. Finalice recorrido y sincronice. Compruebe que la limpieza no produce el error SQLite y que los datos no confirmados nunca se eliminan.
8. Revise filtros de leche/suero, báscula, liquidaciones e impresión de un ticket de cada producto.
9. Compruebe borrado únicamente con superusuario en una base de pruebas y revise la lista de dependencias antes de confirmar.

## Validación técnica

Se incluyen pruebas Django de asignaciones, Excel, permisos y revisión de duplicados por producto, además de la suite existente. La app incluye pruebas de guía operativa, apertura concurrente, migración con pendientes, captura por producto, cierre y limpieza segura. Las comprobaciones de tipos y lint se ejecutan con Node 24. Los paquetes JavaScript se exportan para Android e iOS.

Estas comprobaciones no sustituyen la prueba nativa en teléfonos y con impresora física. Este paquete contiene código fuente, no APK/IPA firmados, y no modifica por sí solo el despliegue de Railway.
