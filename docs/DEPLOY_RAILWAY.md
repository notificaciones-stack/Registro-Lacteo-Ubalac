# Despliegue en Railway

## Servicios

1. Crear proyecto y añadir PostgreSQL.
2. Conectar el repositorio o desplegar el `Dockerfile`.
3. Generar dominio HTTPS.
4. Confirmar que `DATABASE_URL` llega al servicio web.

## Variables

```text
DJANGO_SETTINGS_MODULE=config.settings.production
DJANGO_SECRET_KEY=<valor aleatorio de 50+ caracteres>
DJANGO_ALLOWED_HOSTS=<dominio sin https://>
DJANGO_CSRF_TRUSTED_ORIGINS=https://<dominio>
DJANGO_SECURE_SSL_REDIRECT=true
DJANGO_HSTS_SECONDS=3600
DJANGO_HSTS_INCLUDE_SUBDOMAINS=false
DJANGO_HSTS_PRELOAD=false
DJANGO_LOG_LEVEL=INFO
API_TOKEN_TTL_HOURS=12
```

El contenedor aplica migraciones e inicia Gunicorn. Para el primer administrador use temporalmente las variables `DJANGO_SUPERUSER_*`, ejecute `python manage.py create_admin_from_env` y después retire la contraseña del ambiente.

## Smoke test

1. Verificar `GET https://<dominio>/api/v1/health/`.
2. Crear productor y vehículo.
3. Registrar un recibido con litros conocidos.
4. Abrir el comprobante y comparar todos los datos.
5. Imprimir en el ancho real de la impresora (58 u 80 mm) y guardar una copia PDF.
6. Confirmar que un rol de consulta no pueda modificar.
7. Anular un recibido de prueba y verificar la marca `ANULADO`.
8. Cerrar un recorrido, registrar peso bruto, tara y densidad con un usuario de laboratorio.
9. Validar la báscula y comprobar que el informe muestre litros reales, varianza e historial.
10. Confirmar que laboratorio no pueda corregir una validación cerrada y que administrador/supervisor sí pueda habilitarla con motivo.

## Rollback

Conserve el despliegue anterior y un backup previo. Si falla el smoke test, retire tráfico, restaure la aplicación anterior y solo restaure base de datos cuando sea necesario y esté aprobado. Nunca modifique manualmente tablas de producción para corregir una migración.
