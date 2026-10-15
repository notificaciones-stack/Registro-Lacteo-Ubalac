# Seguridad y operación

## Controles incluidos

| Riesgo | Control |
|---|---|
| Acceso no autorizado | Autenticación obligatoria y roles de mínimo privilegio |
| Fuerza bruta | Límite de intentos web y throttle del token |
| CSRF/XSS | Token CSRF, escape de plantillas y CSP restrictiva |
| Robo de sesión | Cookies `HttpOnly`, `SameSite`, `Secure`; sesión de 8 h; token de 12 h |
| Interceptación | HTTPS obligatorio y HSTS configurable |
| Duplicidad móvil | UUID idempotente y restricciones de base de datos |
| Alteración del histórico | Anulación lógica y auditoría con actor, IP, fecha y `request_id` |
| Caché sensible | `Cache-Control: no-store` en páginas privadas y API |
| Secretos expuestos | Variables de entorno y validación estricta en producción |

## Roles

| Acción | Admin | Supervisor | Recolector/conductor | Laboratorio | Contabilidad | Consulta |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| Consultar recibidos | Sí | Sí | Sí | Sí | Sí | Sí |
| Imprimir comprobante | Sí | Sí | Sí | Sí | Sí | Sí |
| Gestionar productor/vehículo | Sí | Sí | No | No | No | No |
| Crear recibidos | Sí | Sí | Sí | No | No | No |
| Registrar y validar báscula | Sí | Sí | No | Sí | No | No |
| Habilitar corrección de báscula | Sí | Sí | No | No | No | No |
| Editar/anular recibidos | Sí | Sí | No | No | No | No |
| Administrar usuarios/auditoría | Sí | Según delegación | No | No | No | No |

## Antes de producción

- [ ] Usar `config.settings.production` y una clave aleatoria de 50+ caracteres.
- [ ] Configurar hosts y orígenes HTTPS exactos; nunca usar `*`.
- [ ] Ejecutar `python manage.py check --deploy` y todas las pruebas.
- [ ] Probar los roles permitidos y denegados.
- [ ] Crear usuarios de laboratorio con el rol `Laboratorio`; no compartir cuentas.
- [ ] Verificar que una corrección de báscula conserve la revisión anterior y registre el motivo.
- [ ] Eliminar usuarios/datos de prueba.
- [ ] Validar backup y restauración de PostgreSQL.
- [ ] Probar impresora física sin instalar software desconocido en el servidor.
- [ ] Verificar que tirillas de recibidos anulados muestren la marca correspondiente.
- [ ] Activar alertas de errores, almacenamiento y health check.

El CI ejecuta pruebas, revisa migraciones y audita dependencias; Dependabot queda configurado semanalmente.

## Copias e incidentes

- Copia diaria con retención mínima de 30 días y copia semanal separada.
- Backup verificable antes de cada despliegue.
- RPO sugerido: 24 horas; RTO sugerido: 4 horas, sujetos a aprobación.
- Ante incidente: bloquear usuario, conservar logs/auditoría, rotar credenciales, evaluar registros afectados y documentar la corrección.

## Limitaciones del MVP

- Con varias instancias, el throttle debe usar caché compartido o rate limiting del proveedor.
- Antes de distribuir la app móvil se requiere almacenamiento seguro validado y revocación por dispositivo.
- No incluye MFA, SSO ni SIEM.
- No procesa valores monetarios, pagos ni documentos de cobro.
