# Ajustes de diseño de Administración

- Iconos del menú con tamaño uniforme, sin contenedores superpuestos.
- Identificación del módulo activo al crear, consultar y editar parámetros.
- Etiquetas largas del menú visibles en varias líneas.
- Casillas de productos y retenciones agrupadas; controles individuales conservan su tamaño.
- Filtros de inspecciones y liquidación distribuidos con adaptación móvil.
- Catálogos y notificaciones con estados, acciones y mensajes sin registros.
- Estilos separados para el administrador Django, con tablas desplazables y acciones que se distribuyen en varias líneas.

No requiere migraciones nuevas ni cambios de permisos. Al actualizar el proyecto, ejecutar `python manage.py collectstatic --noinput`, reiniciar el servicio y recargar el navegador sin caché.
