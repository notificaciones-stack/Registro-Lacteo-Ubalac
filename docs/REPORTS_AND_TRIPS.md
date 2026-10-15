# Recorridos e informes

## Operación del conductor

1. Cree el usuario con rol **Conductor** (o use un Recolector existente).
2. Asigne el usuario al vehículo en la ficha de Vehículos, panel admin o columna `Usuario conductor` del Excel. Esto requiere permisos para administrar catálogos.
3. El conductor entra a **Recorridos → Abrir recorrido**, selecciona ruta y su vehículo. El servidor fija conductor y hora de inicio. Solo puede tener un recorrido abierto; un vehículo tampoco puede estar en dos recorridos abiertos.
4. Durante el recorrido registra recibidos. Los del rol Conductor requieren un recorrido abierto del mismo vehículo; cada recibido queda vinculado al recorrido. Los recibidos históricos siguen funcionando y pueden carecer de esa relación.
5. Al terminar, el conductor pulsa **Cerrar recorrido**. Administrador o supervisor también pueden cerrar un recorrido. El servidor fija la hora final, conserva el historial y registra auditoría.

Los recolectores existentes pueden seguir creando recibidos sin recorrido para no interrumpir el flujo ya aprobado. Para medir su desempeño, asígneles un vehículo y pídales abrir y cerrar cada recorrido.

## Informes

**Informes** usa exclusivamente un rango «Desde» y «Hasta», ambas fechas obligatorias. Al abrir precarga el primer día del mes actual y hoy. Filtros combinables: productor, ruta, vehículo, conductor, estado y jornada. Los filtros quedan en una barra lateral fija al desplazarse por el informe en escritorio; en pantallas estrechas ocupan una sección plegable y desplazable encima de los resultados. Los litros suman solo recibidos confirmados; las anulaciones no inflan la producción. El filtro de conductor considera recibidos asociados a recorridos, por lo que recibidos anteriores sin recorrido no se atribuyen a un conductor.

El gráfico muestra litros por día y escala cada barra frente al día con más litros del periodo; también imprime los litros y la participación porcentual sobre el total. Las tablas muestran productores, litros por ruta y conductores. El desempeño se ordena por número de recorridos **cerrados** y duración media en caso de empate; también indica recorridos por hora. Para elegir el periodo de un recorrido cerrado se usa su fecha de cierre, incluso si empezó el día anterior. Un recorrido cerrado sin recibidos aparece en el desempeño, pero aporta cero litros. El resumen inicial muestra los recorridos recientes y los conteos de abiertos y cerrados hoy. No se usa la asignación nominal del vehículo para inferir tiempos. La duración medida va de apertura a cierre y no descuenta pausas: compare jornadas similares y use filtros.

**Descargar informe Excel** conserva el rango y los filtros y crea hojas `Resumen`, `Productores`, `Conductores`, `Recibidos` y `Recorridos`, con encabezados y columnas editables. Si un filtro devuelve más de 50.000 recibidos o recorridos, reduzca el rango de fechas.

## API móvil

La app puede consultar `GET /api/v1/route-trips/`, iniciar con `POST /api/v1/route-trips/` enviando `route` y `vehicle`, y cerrar con `POST /api/v1/route-trips/<uuid>/close/`. Usa el mismo token y controles de asignación que el portal. El conductor no envía horas de inicio ni fin: las asigna el servidor. La API de recibidos devuelve `trip` y `route` cuando corresponden.

Para el cliente móvil: consultar el recorrido activo al entrar, impedir abrir otro mientras esté abierto, mostrar su hora de inicio, registrar recibidos ligados al recorrido, confirmar el cierre y refrescar los indicadores. La aplicación debe tratar la pérdida de conexión y los reintentos de creación de recibidos mediante la clave de idempotencia ya disponible; probar en un dispositivo real con red intermitente antes de liberar. No inferir duración desde el reloj del teléfono. En el portal, las tablas anchas se desplazan horizontalmente y el gráfico conserva una escala y valores legibles en pantallas estrechas.
