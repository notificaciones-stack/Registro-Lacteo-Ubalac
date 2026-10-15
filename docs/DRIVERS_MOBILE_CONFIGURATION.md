# Módulo Conductores y parametrización móvil

## Puesta en marcha

1. Aplique la migración `operations.0004` con `python manage.py migrate`.
2. En **Admin → Operación → Acceso al módulo de conductores**, establezca una clave adicional de al menos 6 caracteres. Solo un administrador con acceso al panel admin puede crearla o cambiarla; se guarda como hash. Si la cambia, los accesos abiertos dejan de funcionar.
3. Abra **Conductores** en la plataforma, introduzca la clave adicional y pulse **Nuevo conductor**. Capture nombre, documento, teléfono, correo, usuario, contraseña inicial de al menos 6 caracteres, ID del equipo, rutas, placas y productores en la misma ficha. Las tres asignaciones usan casillas: las marcadas están asignadas y las vacías no. Antes de guardar, un diálogo enumera los cambios para confirmarlos.
4. Desde la ficha existente use **Cambiar contraseña** para establecer una nueva; el sistema revoca sus tokens móviles. En la ficha protegida la contraseña del conductor se presenta oculta por defecto y puede mostrarse. Se conserva cifrada por separado del hash de autenticación, usando una clave derivada de `DJANGO_SECRET_KEY`; el servidor puede descifrarla para un administrador que haya desbloqueado el módulo. Las contraseñas anteriores a esta versión no se pueden recuperar: restablézcalas para habilitar esa casilla. Si se cambia la contraseña fuera de este módulo, la copia cifrada anterior deja de mostrarse. Conserve la clave de Django de forma segura y estable: al rotarla, las copias previas dejarán de descifrarse y requerirán restablecimiento. El módulo se bloquea después de 30 minutos o al salir, y ofrece **Bloquear módulo**. Tras cinco errores de la clave adicional, espere 15 minutos. Esa clave de acceso al módulo sigue configurándose exclusivamente desde el panel admin.
5. Si crea nuevas rutas, productores o vehículos, vuelva a la ficha y asígnelos al conductor. Una placa solo puede asignarse a un conductor. No se pueden quitar la ruta o la placa de un recorrido abierto: ciérrelo primero.

La ficha propia **Mi configuración** es de solo lectura para el conductor autenticado. El módulo de administración requiere rol Administrador y la clave adicional. El supervisor no recibe acceso a este módulo.

## Regla de asignaciones

- Una ficha configurada admite varias rutas y varios vehículos. Sin rutas asignadas, el conductor no puede abrir un recorrido. Antes de crear una ficha, los conductores existentes conservan las rutas predeterminadas de sus vehículos para facilitar la transición.
- Las placas activas aparecen si `Vehículo.driver` señala al usuario. Al abrir, el servidor verifica tanto la placa como la ruta asignada; la interfaz y la API aplican el mismo control.
- Si se seleccionan productores en la ficha, el conductor solo puede registrar leche de ellos. Con la selección vacía puede consultar todos los productores activos. La creación de un productor no lo asigna automáticamente a una ficha restringida.
- La API filtra catálogos de rutas, vehículos y productores por asignación. Los recibidos del rol Conductor se limitan a los creados por su usuario.
- El ID del equipo es opcional. Si se configura, la app debe incluir `X-Device-ID: <id>` al solicitar token y en **todas** las llamadas autenticadas con token. Cambiar el ID bloquea el uso del token desde otro ID. Este control identifica el valor declarado por el cliente; no sustituye una validación criptográfica del hardware ni protege un dispositivo comprometido.

## Contrato para la app

Después de `POST /api/v1/auth/token/`, consultar `GET /api/v1/drivers/me/configuration/` con `Authorization: Token <token>` y, si se vinculó un equipo, `X-Device-ID`. Devuelve `user`, `document_number`, `phone`, `device_registered`, `routes`, `vehicles` y `producers`; no incluye contraseñas ni el ID de equipo. Las operaciones existentes de apertura/cierre de recorridos y recibidos quedan sujetas a estas asignaciones. Un `external_id` usado por otro usuario devuelve conflicto y no expone su recibido.

Para probar: configurar la clave adicional en admin, crear conductor con contraseña, ruta, placa y productor desde la plataforma, iniciar sesión en la API con el ID del equipo, consultar la configuración propia, abrir recorrido y registrar un recibido. Después restablecer la contraseña desde la ficha y comprobar que el token anterior deja de funcionar. Probar también ID incorrecto, ruta/productor no asignados y cierre antes de cambiar asignaciones. Los recolectores sin ficha mantienen su flujo anterior de recibidos.
