# Báscula y validación de laboratorio

## Flujo

1. El conductor sincroniza todos los recibidos y cierra el recorrido.
2. Laboratorio entra a **Báscula**, selecciona el recorrido cerrado y registra fecha, tiquete, peso bruto, tara, densidad, tolerancia y observaciones.
3. El sistema calcula `peso neto = bruto - tara` y `litros reales = peso neto / densidad`.
4. Antes de validar se deben resolver las alertas de más de un recibido para el mismo productor en el recorrido.
5. Al validar se guardan litros operativos, litros reales, varianza en litros y porcentaje, resultado y responsable.
6. Los informes usan el valor real del recorrido. Para mantener el análisis por productor, el ajuste se distribuye proporcionalmente entre los recibidos sin cambiar sus litros originales.

## Resultado

La tolerancia se calcula sobre los litros operativos confirmados. Una varianza inferior al límite negativo es **pérdida**; una superior al límite positivo es **ganancia**; dentro del rango queda **en tolerancia**. El valor inicial de densidad es 1,0300 kg/L y debe sustituirse por la medición real del laboratorio.

## Correcciones y seguridad

Laboratorio puede crear, modificar y validar borradores, pero no editar una validación final. Solo administración o supervisión puede habilitar una corrección con motivo de mínimo ocho caracteres. Cada nueva validación genera una revisión inalterable con valores, responsable, fecha y motivo. Mientras la báscula está validada se bloquea la creación, edición o anulación de recibidos del recorrido para evitar diferencias silenciosas.

La validación exige recorrido cerrado, pesos válidos, densidad entre 0,9000 y 1,2000 kg/L, tolerancia entre 0 y 100 %, litros confirmados y ausencia de duplicados sin resolver.

## Antes de validar en operación real

- Confirmar que el teléfono indique sincronización completa.
- Verificar placa, ruta y número del tiquete físico.
- Usar tara correspondiente al mismo vehículo y pesaje.
- Ingresar la densidad medida para ese lote, no asumir permanentemente el valor inicial.
- Resolver alertas de recibidos repetidos.
- Comparar la vista previa con el tiquete antes de la validación final.
