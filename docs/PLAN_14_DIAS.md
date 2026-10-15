# Plan acelerado de entrega — 14 días calendario

## Objetivo

Poner en producción el flujo completo **productor → recolección → comprobante impreso → consulta/anulación → auditoría** en 14 días calendario. El alcance se congela al finalizar el día 2.

| Día | Objetivo | Resultado verificable |
|---:|---|---|
| 1 | Inicio | Confirmar campos del comprobante, ancho 58/80 mm, impresora, responsables y criterios de aceptación. |
| 2 | Reglas y muestras | Validar consecutivo, roles, estados y dos comprobantes reales anonimizados. Alcance firmado. |
| 3 | Base técnica | PostgreSQL, repositorio, ambientes, autenticación y primer despliegue interno. |
| 4 | Catálogos | Productores y vehículos con búsquedas, estados, permisos y auditoría. |
| 5 | Recibidos | Captura de fecha, proveedor, vehículo, recolector, litros y observaciones. |
| 6 | Comprobante | Vista térmica de 58/80 mm, PDF, código de verificación, firmas y marca de anulación. |
| 7 | Panel | Indicadores, listados, filtros, responsividad y manejo de errores. |
| 8 | API móvil | Token, catálogos, captura idempotente y endpoint del comprobante. |
| 9 | Seguridad | CSRF, CSP, HTTPS, secretos, cookies, throttling y pruebas de permisos. |
| 10 | Prueba de impresión | Impresora real, ancho, corte, legibilidad, copias y funcionamiento en teléfono. |
| 11 | QA integral | Casos felices, errores, duplicados, anulaciones, navegadores y regresión. |
| 12 | UAT | Validación con recolector y responsable UBALAC; solo correcciones, sin funciones nuevas. |
| 13 | Ensayo de salida | Backup/restauración, migraciones, rollback, usuarios y capacitación. |
| 14 | Producción | Despliegue, smoke test, soporte intensivo y acta de entrega. |

## Hitos

| Hito | Momento | Criterio |
|---|---|---|
| H1 Alcance congelado | Fin día 2 | Campos y formato físico aprobados |
| H2 Flujo principal | Fin día 6 | Se registra leche y se imprime el comprobante correcto |
| H3 Candidato | Fin día 10 | Seguridad y prueba física aprobadas |
| H4 Aceptación | Fin día 12 | Usuario ejecuta los casos acordados |
| H5 Producción | Día 14 | Backup, monitoreo y smoke test correctos |

## Equipo mínimo

| Rol | Dedicación | Responsabilidad |
|---|---:|---|
| Líder/full-stack | 100% | Aplicación, API, pruebas y despliegue |
| QA funcional | 50% desde día 5; 100% días 10–14 | Regresión, impresión y UAT |
| Product owner UBALAC | 60–90 min diarios | Resolver reglas y aceptar el mismo día |
| Infra/DevOps | Parcial; 100% días 13–14 | Dominio, secretos, backup y salida |

## Prioridad

**P0:** usuarios/roles, productores, vehículos, recibidos, comprobante térmico 58/80 mm/PDF, consulta, anulación, auditoría, backup y despliegue.

**P1:** filtros adicionales, exportación y mejoras visuales.

**Posterior:** app móvil offline completa, integración directa Bluetooth, mediciones de calidad, firma digital y notificaciones.

Todo cambio posterior al día 2 debe reemplazar una tarea equivalente. La disponibilidad de una impresora física para pruebas no puede aplazarse más allá del día 9.
