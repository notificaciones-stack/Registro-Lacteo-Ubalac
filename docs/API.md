# API v1 para aplicación móvil

Base: `/api/v1/`. Excepto `health/` y `auth/token/`, todas las rutas requieren token.

## Autenticación

```http
POST /api/v1/auth/token/
Content-Type: application/json

{"username":"recolector1","password":"..."}
```

```http
Authorization: Token <token>
```

La respuesta incluye `expires_at`, usuario y rol. El token vence a las 12 horas por defecto y un nuevo inicio de sesión revoca el anterior.
Si el administrador configuró un ID de equipo para el conductor, incluya `X-Device-ID: <id>` en el inicio de sesión y en todas las peticiones con token; un ID distinto o ausente será rechazado. La app genera y comunica este ID al administrador para registrarlo desde **Conductores** en la plataforma.

`GET /api/v1/drivers/me/configuration/` devuelve al conductor autenticado sus datos, rutas, placas y productores permitidos. No entrega contraseñas ni permite cambiar asignaciones desde el teléfono.

## Catálogos

- `GET /api/v1/producers/`
- `GET /api/v1/vehicles/`
- `GET /api/v1/routes/`
- `GET /api/v1/route-trips/` (recorridos propios para conductor y recolector; todos para administración)

Los catálogos se filtran según las asignaciones del conductor. Una ficha con selección específica de productores muestra solo los suyos. Sin selección específica, se muestran los productores activos.

Para un usuario con rol Conductor, asigne primero su usuario al vehículo. Abra el recorrido con `POST /api/v1/route-trips/` y JSON `{"route":"<uuid>","vehicle":"<uuid>"}`. Cierre mediante `POST /api/v1/route-trips/<uuid>/close/`. Inicio, cierre y conductor son definidos por el servidor. Un conductor necesita un recorrido abierto del vehículo para registrar recibidos.

## Registrar recolección

El teléfono crea `external_id` antes del primer intento y lo conserva durante cada reenvío.

```http
POST /api/v1/receipts/
Content-Type: application/json
Authorization: Token <token>

{
  "external_id": "7b101570-3b6e-4b2c-a4f1-53eefdf816ea",
  "producer": "0d0f0c60-f22c-4dd0-9bbb-edc8402f47c4",
  "vehicle": "e2bba9af-3182-4796-9045-8e455aa22182",
  "collected_at": "2026-09-24T13:30:00-05:00",
  "liters": "125.50",
  "observations": "Ruta norte"
}
```

- Primera creación: HTTP `201`.
- Reintento del mismo UUID por el mismo usuario: HTTP `200` y el registro existente. Si otro usuario lo registró, HTTP `409`.
- Roles de escritura: administrador, supervisor, recolector y conductor.
- El servidor define origen, estado, usuario y consecutivo.

## Datos del comprobante

```http
GET /api/v1/receipts/<uuid>/voucher/
Authorization: Token <token>
```

La respuesta contiene `document_type`, `copy_for` y todos los datos necesarios para una tirilla de 58/80 mm: número, fecha, productor, documento, finca, vehículo, recolector, litros, observaciones, estado y código UUID.

La app debe imprimir los datos devueltos por el servidor y no inventar consecutivos. Un comprobante con estado `VOIDED` debe mostrar claramente “ANULADO”.

## Reglas del cliente móvil

- Guardar token y cola local en almacenamiento cifrado.
- Mantener el mismo `external_id` en todos los reintentos.
- Considerar éxito tanto `200` como `201`.
- No reintentar automáticamente errores `400` o `403`.
- Usar espera exponencial para errores temporales.
- Borrar token y datos sensibles al retirar el dispositivo.
- Para impresión Bluetooth, formatear la respuesta a 58 u 80 mm sin alterar litros ni consecutivo.
