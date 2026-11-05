# Actualización conductores
- Listado de conductores alineado con el patrón de tabla y búsqueda de rutas.
- Importación masiva exclusivamente en Django Admin > Operations > Perfiles de conductor > Importar conductores Excel.
- Descargar plantilla XLSX desde la pantalla de importación. La importación es transaccional y rechaza duplicados, asignaciones inválidas y placas ocupadas.
- Contraseñas de conductor y módulo: mínimo 4 caracteres, sin restricciones de complejidad. Se mantienen hash, control de acceso y bloqueo de intentos del módulo.
- Precaución: contraseñas de cuatro caracteres son vulnerables a ataques de adivinación; se recomienda usar contraseñas más largas cuando sea posible.
- No se modificaron los validadores globales de cuentas administrativas.
