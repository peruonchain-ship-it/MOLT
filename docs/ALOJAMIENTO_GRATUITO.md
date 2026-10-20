# DATALICITA privada en Internet

La aplicación consulta la API oficial sin usar una IA. Se puede abrir desde el celular y la computadora con usuario y contraseña. La portada pública de GitHub Pages sigue siendo independiente del panel privado.

El despliegue preparado usa **Render Free** para la web, **Neon Free** para guardar datos y **GitHub Actions** para las consultas programadas. El código y las pruebas están preparados; no se han creado cuentas externas ni desplegado el panel privado sin las cuentas del propietario.

## 1. Crear la base gratuita

1. Abre [Neon](https://console.neon.tech/signup), crea una cuenta y un proyecto llamado `datalicita` en el plan **Free**. Elige una región cercana a la de tu servicio Render.
2. En **Connect**, copia la conexión PostgreSQL (`Connection string`), preferiblemente con **Connection pooling** activado. Es un secreto: contiene el usuario y contraseña de la base. No la compartas en el chat, el repositorio o capturas públicas.
3. Consérvala para los dos ajustes seguros que vienen a continuación. Ambos deben apuntar a **la misma base y rama de Neon**.

## 2. Publicar la web privada

1. Abre [Deploy to Render](https://render.com/deploy?repo=https://github.com/peruonchain-ship-it/MOLT) y crea una cuenta gratuita. Conecta GitHub y permite acceder al repositorio `peruonchain-ship-it/MOLT` si Render lo solicita.
2. Revisa el servicio `datalicita`, plan **Free**, definido en `render.yaml`.
3. Introduce `DATABASE_URL` con la conexión de Neon y `MOLT_INITIAL_PASSWORD` con una contraseña propia de **12 a 200 caracteres**. Solo se introducen en el formulario seguro de Render. El usuario inicial es `propietario`.
4. Pulsa **Deploy**. Cuando el servicio esté listo, Render mostrará su dirección HTTPS gratuita, terminada en `.onrender.com`. El nombre exacto lo asigna Render; no se presupone que `datalicita.onrender.com` esté disponible.
5. Abre esa dirección añadiendo `/app` e ingresa con tu usuario y contraseña. En **Preferencias**, configura tus zonas, correo y frecuencia. La ventana inicial es de 90 días y la consulta cada 6 horas, configurable.

La contraseña inicial solo crea al propietario cuando no existe. Cambiar esa variable no sustituye una contraseña ya guardada. Puedes cambiarla desde el panel. Tras verificar el primer acceso, puedes eliminar `MOLT_INITIAL_PASSWORD` de Render. Conserva una copia segura de tu acceso; no hay recuperación por correo en esta versión.

La web de Render tiene `MOLT_WORKER_ENABLED=false`: la programación depende del siguiente paso y su estado se muestra en el panel.

## 3. Activar las consultas independientes

1. En GitHub abre [Secrets de Actions](https://github.com/peruonchain-ship-it/MOLT/settings/secrets/actions). Crea un **Repository secret** llamado `DATABASE_URL` con la misma conexión de Neon.
2. Abre [Actions](https://github.com/peruonchain-ship-it/MOLT/actions), habilita los workflows si GitHub lo solicita, selecciona **Actualizar DATALICITA** y pulsa **Run workflow**, rama `main`.
3. Espera el resultado de la ejecución. Si falla, revisa el paso indicado; una ejecución fallida no significa que el radar esté actualizado.
4. En el panel privado verifica **La fuente, a la vista**: consulta completa, ventana, fecha del dato más reciente de OECE y señal del recolector externo. Los registros y tus notas se guardan en Neon y sobreviven al reinicio de Render.

El workflow comprueba el horario aproximadamente cada hora, al minuto 17, y consulta cuando corresponde según las preferencias. GitHub puede retrasar ejecuciones. Los documentos se procesan en lotes de cuatro por ejecución. No se necesita abrir la web ni mantener este chat activo. No se envían datos privados como artefactos de Actions.

**En repositorios públicos GitHub puede desactivar la programación tras 60 días sin actividad del repositorio.** Revisa Actions periódicamente y reactívala si sucede. La señal del recolector en el panel permite detectar falta de actividad.

## 4. Correos opcionales

El panel y la descarga de Excel funcionan sin proveedor de correo. Para activar el resumen:

1. Crea/configura Resend y un remitente autorizado por el proveedor. El remitente de pruebas tiene restricciones; el envío desde un dominio propio requiere verificarlo.
2. Añade `RESEND_API_KEY` y `MOLT_MAIL_FROM` tanto en los ajustes seguros de Render como en los secrets de GitHub Actions. No introduzcas claves en el panel de la aplicación.
3. En **Preferencias**, guarda tu correo y activa el resumen diario. Por defecto es a las 08:00 de Perú, sujeto a la siguiente ejecución de Actions, y excluye registros históricos. Requiere una consulta completa y reciente de OECE.

No se ha enviado correo real durante las pruebas. No se promete una entrega hasta configurar y verificar el proveedor.

## Límites y comprobación

- [Render Free](https://render.com/docs/free) pausa la web tras 15 minutos sin tráfico. Al abrirla puede tardar en despertar. Sus archivos locales son temporales, por eso la base se guarda en Neon. El plan gratuito tiene límites de horas y recursos.
- [Neon Free](https://neon.com/pricing) tiene cuotas de cómputo, transferencia y almacenamiento. Conserva copias de tus datos y revisa el consumo. No se contrata ningún plan de pago automáticamente desde este proyecto.
- GitHub Actions y los planes gratuitos no garantizan disponibilidad continua ni horarios exactos.
- OECE determina la actualización de la fuente. La consulta periódica no garantiza tiempo real ni que todo el contenido de SEACE esté publicado en esta API. Revisa cronogramas en el documento original.
- El **20 de octubre de 2026** se verificaron portal, documentación y descargas, y la lectura real paginada con el cliente de DATALICITA. Debe comprobarse también desde el alojamiento elegido. Si OECE rechaza una consulta o está indisponible, se conservan los registros anteriores y se muestra el error; una consulta parcial nunca acredita cobertura completa.
- Los registros locales anteriores de este entorno no se copian automáticamente a Neon. La base original se conserva. Una primera sincronización remota importa la ventana elegida; una transferencia de notas o registros anteriores requiere una migración explícita antes de retirar el almacenamiento original.
- GitHub Pages contiene la portada; **el panel privado todavía no está publicado** hasta completar y validar los pasos de Render y Neon.

## Verificación técnica reproducible

`uv run --frozen pytest -q` prueba SQLite. Para repetir las mismas pruebas con PostgreSQL, define `MOLT_TEST_DATABASE_URL` con una base de pruebas y ejecuta el mismo comando. Cada prueba crea y elimina únicamente un esquema aleatorio `test_*`; nunca uses credenciales de producción para esta comprobación.

Se comprobaron 68 pruebas en SQLite y 68 con PostgreSQL 17 real: autenticación, sesiones, CSRF, persistencia tras reiniciar, notas, filtros, Excel, PDFs, cursores, exclusión mutua, reversión de transacciones y correo simulado. La conexión remota PostgreSQL exige TLS con verificación del servidor. También pasaron el navegador en escritorio y celular y el arranque nativo con dependencias de producción, puerto asignado por el proveedor y acceso privado sobre PostgreSQL.

`uv run --frozen python -m molt collect` ejecuta una pasada del recolector externo y requiere `DATABASE_URL`. Un fallo de la fuente devuelve código de salida distinto de cero. No publica un volcado de oportunidades ni credenciales en la salida.
