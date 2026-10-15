# Verificación de la entrega

La verificación se realizó con copias aisladas de los proyectos adjuntos, sin modificar bases de datos reales.

- 67 pruebas de Django correctas, incluidas las pruebas operativas anteriores actualizadas donde ahora se exige inspección o se agregan hojas económicas al Excel.
- Casos nuevos: cálculo de 400 litros, precios históricos, sincronización tardía con precio anterior, descuentos/adiciones, litros ajustados, cuantías menores sin documento, validación documental normal, productos habilitados, filtros, exclusión de anulados, valoración histórica explícita, permisos, Excel, inspección e idempotencia, borrado protegido por superusuario y reintentos de correo.
- Migración comprobada desde 0009 con un proveedor y recibido anteriores: conserva identificadores y litros, asigna leche y mantiene precio pendiente.
- `manage.py check`, ausencia de migraciones sin generar y recolección de estáticos correctos.
- `check --deploy` sin errores, con avisos opcionales de HSTS para subdominios y preload. Permanecen desactivados hasta confirmar que todos los subdominios propios usan HTTPS.
- Móvil: typecheck y lint correctos, 2 pruebas automáticas correctas, 21/21 controles Expo Doctor correctos y exportación del bundle Android/Hermes correcta.
- La prueba de almacenamiento usa un adaptador SQLite de Node para ejecutar la migración y verificar que no se borran pendientes. No verifica el cifrado nativo de Android.

Límites: no se compiló un APK firmado con la cuenta EAS del propietario, no se conectó una impresora física ni se enviaron correos con sus credenciales. La base de pruebas fue SQLite; la configuración de producción requiere PostgreSQL y debe validarse en su servicio Railway. La revisión de plantillas se realizó mediante respuestas HTTP y pruebas de renderizado Django. No se completó la inspección visual con navegador porque su ejecutable no estuvo disponible.

Los ZIP excluyen bases de datos, datos de prueba generados durante la revisión, entornos virtuales, dependencias, cachés, registros de Expo, repositorios internos y variables privadas. Conserve su base original, secretos y firma de Android al actualizar.
