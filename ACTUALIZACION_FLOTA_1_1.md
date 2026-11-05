# UBALAC 1.1 · Encuesta de fatiga, tanqueos y reapertura

## Qué incluye

- Encuesta de fatiga al cierre del turno, en web y móvil: horas de descanso, sueño/cansancio, descanso suficiente, condición de fatiga, observaciones y compromiso. Se adaptó la redacción del formulario suministrado al cierre del turno. Las horas se capturan como número (0–24), para no excluir valores fuera de las dos opciones de la imagen.
- Historial por recorrido y por reapertura. Las respuestas anteriores se conservan. Hay aviso visual y notificación mediante la cola de correos existente cuando hay sueño, fatiga, descanso insuficiente o menos de 6 horas declaradas. Este último es un criterio operativo de señalización, no un diagnóstico.
- Tanqueos vinculados al recorrido: conductor, vehículo y ruta históricos; galones US, valor total COP, kilometraje, tanque lleno y dos fotos obligatorias.
- Informes con fechas desde/hasta, conductor, ruta, vehículo y agrupación día/semana/mes. Totales por placa y conductor, gráficos de gasto/galones y Excel con encabezados.
- Rendimiento estimado km/galón entre cargas de tanque lleno; incluye cargas parciales intermedias y toma el intervalo completo aunque el primer tanqueo quede fuera del filtro. Sin dos referencias válidas se muestra “sin intervalo”. El gasto de una ruta es el combustible comprado durante ese recorrido, no una medición directa del consumo de esa ruta.
- Fotos privadas: validación de tipo y tamaño, conversión a JPEG, reducción de resolución y eliminación de metadatos EXIF. Se guardan en PostgreSQL junto con los registros, sin depender del disco efímero de Railway. Incluya estas imágenes en su planificación de espacio y copias de seguridad.
- El conductor consulta sus propios registros y fotos. Administrador/supervisor pueden registrar y consultar; contabilidad/laboratorio consultan informes. El borrado conserva el mecanismo existente exclusivo del superadministrador.
- Sincronización móvil: revisa la reapertura remota antes de enviar un cierre, utiliza una revisión del servidor, conserva las capturas pendientes y evita duplicar tanqueos al reintentar. Las encuestas y fotos pendientes impiden limpiar la jornada.
- Navegación móvil con cuatro accesos inferiores y menú de botones grandes. Tanqueos pendientes rechazados pueden corregirse y reenviarse, incluso de la jornada anterior.

## Orden de actualización

1. Haga una copia de seguridad de PostgreSQL antes de desplegar. Pruebe primero con una copia del entorno si dispone de ella.
2. Actualice el código web conservando sus variables actuales de Railway. No cambie DJANGO_SECRET_KEY, DATABASE_URL ni las claves de cifrado por esta actualización.
3. Instale dependencias y aplique la migración nueva:

```bash
python -m pip install -r requirements.txt
python manage.py check
python manage.py migrate
python manage.py collectstatic --noinput
```

En Railway mantenga `DJANGO_SETTINGS_MODULE=config.settings.production`. La migración `fleet/0001_initial.py` crea dos tablas; no borra ni transforma recibidos existentes. Conserve el comando de inicio actual que ejecuta las migraciones y Gunicorn.

4. Compruebe en el menú web “Tanqueo vehicular” y “Fatiga del conductor”. Pruebe permisos y filtros con un conductor de pruebas.
5. Después de que la web esté operativa, distribuya el nuevo móvil 1.1.0. Se necesita una nueva compilación nativa por `expo-image-picker`; no basta una actualización de JavaScript. Expo Go sigue sin soportar la base SQLCipher de esta app.
6. Mantenga instalada la aplicación anterior hasta sincronizar sus pendientes. Actualice sobre ella con la misma identidad y firma; no desinstale ni borre sus datos.

Las versiones móviles anteriores conservan su contrato de cierre. La validación adicional de encuesta/revisión se activa en los cierres de la nueva app que envían `expected_cycle`. Actualice todos los equipos para utilizar el flujo nuevo. El cierre automático a las 23:59 continúa funcionando y no inventa respuestas de encuesta: el formulario debe completarse por el conductor.

## Compilar el móvil

Desde la carpeta del proyecto móvil:

```bash
npm ci
npm run typecheck
npm run lint
npm test
npx eas-cli@latest login
npx eas-cli@latest build --platform android --profile preview
```

El perfil `preview` genera un APK. Para iPhone mediante TestFlight/App Store:

```bash
npx eas-cli@latest build --platform ios --profile production
npx eas-cli@latest submit --platform ios --profile production
```

Use su cuenta Expo y sus credenciales Apple Developer. Estos comandos usan el proyecto EAS y el dominio Railway ya configurados. No se generaron ni publicaron APK/IPA desde esta entrega.

## Prueba de aceptación con teléfono real

1. Iniciar sesión; registrar inspección; abrir recorrido.
2. Recoger leche y suero, repetir un productor y comprobar la alerta existente.
3. Registrar tanqueo con ambas fotos; desconectar internet; guardar y reiniciar la app; comprobar que sigue pendiente.
4. Completar encuesta y cerrar sin internet. Recuperar conexión y sincronizar: un solo tanqueo y una sola encuesta en web.
5. Reabrir el recorrido desde web. Sincronizar el móvil: debe mostrarlo activo, sin reenviar el cierre anterior. Registrar otro recibido, completar nueva encuesta y cerrar de nuevo.
6. Verificar totales de galones y COP, filtros, Excel, fotos privadas y rendimiento con dos cargas de tanque lleno.
7. Probar permiso de cámara denegado, foto inválida, sesión vencida y error de red: ningún pendiente debe borrarse sin confirmación.
8. Verificar la impresora física y la tirilla: su código se conserva, pero una prueba con el hardware es parte de la aceptación.

## Verificación de esta entrega

- 82 pruebas Django aprobadas, incluyendo API, roles, fotos, reintentos, encuesta, cierre/reapertura, informes y carga web.
- 12 pruebas Node aprobadas, incluyendo migración SQLite con pendientes y reconciliación de jornadas.
- TypeScript y ESLint aprobados.
- Exportación del paquete JavaScript de Android e iOS aprobada. Esto no reemplaza una compilación nativa firmada ni la prueba de cámara, SQLCipher o Bluetooth en equipos físicos.
- Auditoría Python sin vulnerabilidades conocidas al momento de ejecutarla.
- Pruebas locales con SQLite; la prueba final sobre PostgreSQL/Railway y dispositivos reales debe hacerse antes de habilitar la operación completa.

## API nueva

- `GET/POST /api/v1/fuel-entries/`: fotos base64 en `fuel_photo` e `invoice_photo`; UUID `external_id` estable para reintentos.
- `GET/POST /api/v1/fatigue-surveys/`: respuestas, UUID estable y revisión `expected_cycle`.
- `GET /api/v1/route-trips/{id}/`: estado/reapertura para reconciliar.
- `POST /api/v1/route-trips/{id}/close/`: la nueva app envía `expected_cycle`; 409 indica una reapertura posterior. Se debe sincronizar, no repetir el cierre viejo.

Los registros confirmados son históricos. Las fotos de la API no se listan públicamente; se consultan desde vistas web autenticadas. Los avisos de fatiga utilizan `OPERATIONS_NOTIFICATION_EMAILS` (o el respaldo de contabilidad) y el procesador de notificaciones ya existentes. No se cambiaron destinatarios ni se enviaron correos reales en las pruebas.
