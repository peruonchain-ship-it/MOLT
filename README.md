# MOLT · Radar privado de eventos

**Nombre público: DATALICITA.** La portada está en `/` y el radar privado en `/app`. La publicación gratuita y la configuración para Google se describen en [docs/PUBLICACION.md](docs/PUBLICACION.md). El módulo Python y las variables `MOLT_*` conservan su nombre para mantener compatibilidad.

**Para usar el radar privado en Internet:** sigue [la guía de alojamiento gratuito](docs/ALOJAMIENTO_GRATUITO.md). Incluye Render, PostgreSQL persistente en Neon y consultas programadas con GitHub Actions que funcionan sin este chat y sin una IA. La portada de GitHub Pages ya publicada no ejecuta el panel privado.

Aplicación privada para encontrar y seguir contrataciones relacionadas con eventos, pantallas LED y servicios audiovisuales en Perú. Primera cobertura: **Lima, Cusco, Trujillo y Arequipa**.

Incluye panel en español, filtros, lectura de registros OCDS, coincidencias en contratos integrales, extracción de texto de PDFs oficiales, seguimiento comercial, notas privadas, Excel y resúmenes por correo con adjunto.

## Empezar

Requiere Python 3.12+ y [uv](https://docs.astral.sh/uv/). En el entorno preparado, ambos ya están disponibles.

```bash
cd /workspace/MOLT
bash scripts/install.sh
bash scripts/start.sh
```

El servidor escucha en el puerto **8000**, únicamente en la interfaz local por defecto. En tu propio equipo, abre la dirección de la interfaz local en ese puerto. Para acceso remoto, usa un servidor propio con HTTPS según las indicaciones de despliegue más abajo.

Si descargaste el ZIP, trabaja desde la carpeta descomprimida en lugar de `/workspace/MOLT`. Sin Bash, los comandos equivalentes son `uv sync --frozen` y `uv run --frozen python -m molt serve`.

En otra consola, obtén el código de un solo uso:

```bash
cd /workspace/MOLT
uv run --frozen python -m molt setup-code
```

En la pantalla inicial ingresa ese código y crea tu usuario y contraseña de al menos 12 caracteres. No existe contraseña compartida, registro público ni usuario predeterminado creado. **No publiques el código ni lo copies a un chat.** Se elimina después de crear el usuario.

Si necesitas recuperar acceso desde la consola del servidor:

```bash
uv run --frozen python -m molt reset-password
```

## Uso diario

1. **Actualizar radar:** consulta los últimos 90 días por defecto. El proceso es paginado y se puede reanudar si se interrumpe; una consulta parcial nunca se etiqueta como completa.
2. **Filtrar:** zona, familia de servicios, estado, texto, etapa comercial y orden. La consulta completa puede tardar varios minutos.
3. **Revisar oportunidad:** abre la ficha, los documentos y el enlace oficial. Comprueba cronograma, requisitos, dimensiones, jornadas, personal, entregables y lugar de prestación.
4. **Seguir:** guarda notas y cambia la etapa a Revisar, Cotizar, Presentada o Descartada. Las notas se conservan al actualizar la fuente.
5. **Descargar Excel:** exporta todo el resultado del filtro actual, no solo la página visible. Incluye evidencia, documentos, seguimiento y metadatos de cobertura.

Los importes corresponden al proceso completo, **no al presupuesto aislado del componente audiovisual**. Monedas distintas se conservan; no se suman como si fueran soles.

## Datos reales y límites de la fuente

- Fuente: [API de Contrataciones Abiertas OECE](https://contratacionesabiertas.oece.gob.pe/api), enlazada desde [gob.pe/52005](https://www.gob.pe/52005).
- Integración: `GET /api/v1/recordsAfter?size=100&startDate=...&endDate=...`, siguiendo el cursor oficial `links.next`. El filtro corresponde al período de licitación definido por la API, no a todas las modificaciones publicadas durante ese intervalo.
- Se lee `compiledRelease`: entidad, objeto, ítems, montos, fechas, adjudicaciones, contratos, domicilios y adjuntos. No se depende de operadores OR ni de búsquedas complejas del portal.
- **Vigente según fuente:** requiere estado `active` explícito, fecha futura, registro de origen de los últimos 7 días y ausencia de adjudicaciones/contratos. Se debe confirmar en SEACE.
- **Por verificar:** faltan datos, el registro está desactualizado o hay indicios de un procedimiento parcialmente adjudicado.
- **Histórica:** fecha vencida, proceso terminado o adjudicado. Sirve para estudiar compradores habituales; no se vende como una oferta abierta.
- Esta API no garantiza oportunidades en tiempo real ni cobertura de todas las modalidades de contratación. No se ha integrado un acceso autenticado al buscador SEACE, ni se eluden controles del portal.
- Se prefiere la dirección de entrega/prestación. Si falta, el domicilio del comprador se etiqueta expresamente como referencia. Los datos solo departamentales de Lima, Cusco y Arequipa se indican como tales; Trujillo requiere provincia/localidad o ubigeo compatible. No se usa la dirección del proveedor.
- Una palabra en el objeto del contrato no identifica por sí sola un lugar de prestación. La detección en documentos busca una indicación explícita de lugar.

### Buscar dentro del contrato

El vocabulario contiene 18 familias basadas en los términos del negocio: producción integral, institucionales, congresos, ferias/stands, logística, equipos audiovisuales, pantallas/proyección, sonido, iluminación/estructuras, streaming, virtuales/híbridos, producción audiovisual, cobertura, televisión, estudios, posproducción, comunicación y personal técnico.

Un contrato de organización puede aparecer sin nombrar las pantallas en el título. Se comparan **objeto, descripciones de ítems y texto de documentos**. Cada hallazgo identifica familia, expresión, fragmento y origen. El alcance diferencia servicio específico, integral por revisar e integral con componente técnico detectado. La afinidad es una regla de ordenamiento, no una predicción de adjudicación.

Se excluyen falsos positivos evidentes como la provincia **La Convención**, referencias administrativas al **Congreso de la República**, paneles LED de alumbrado y ciertos usos de “lanzamiento” en obras civiles.

### Documentos

- Se ponen en cola bases, términos de referencia y especificaciones de contratos candidatos. No se descargan todos los archivos del Estado.
- Destinos de descarga automática: HTTPS del portal OECE y subdominios de `seace.gob.pe`. Cada redirección se valida. La política de red del entorno debe permitir el host concreto.
- Límite por PDF: 12 MB, primeras 160 páginas, 400.000 caracteres. Las lecturas parciales se indican.
- PDF escaneado/protegido, ZIP y otros formatos: **revisión manual**. No se afirma haber leído un documento bloqueado y no se incorpora OCR en esta versión.
- Los errores de acceso quedan visibles y pueden reintentarse desde la ficha. Si cambia un adjunto, su texto anterior se invalida.
- Si el proxy bloquea SEACE, la cola automática se pausa para no repetir descargas imposibles. Tras habilitar el dominio, pulsa **Revisar pendientes** para reanudarla.
- Los contratos sin señal de eventos en su objeto/ítems pueden quedar fuera de esta selección inicial, aunque contengan una necesidad audiovisual en un documento. No se garantiza una búsqueda exhaustiva dentro de todos los TDR del Estado.

## Activar correos

El envío está implementado con **Resend por HTTPS**. En el entorno actual ya se guardó el destinatario indicado por el propietario en la configuración local privada; no está incluido en el código del proyecto.

1. Crea/configura una cuenta en [Resend](https://resend.com), con remitente o dominio autorizado y una clave para enviar correos.
2. Configura de forma segura estas variables en el servidor o en la configuración del entorno:

```dotenv
RESEND_API_KEY=<clave privada, nunca en Git ni en el chat>
MOLT_MAIL_FROM=Radar MOLT <radar@tu-dominio-verificado.com>
MOLT_MAIL_TO=tu@correo.com
```

También puedes copiar `.env.example` a `.env` **solo si este último no existe** y completar sus valores. `.env` está excluido de Git. Reinicia MOLT después de cambiar variables.

3. En **Preferencias**, confirma el destino y activa el resumen diario. Hora predeterminada: **08:00, America/Lima**. El servidor debe permanecer encendido.
4. Usa **Ver próximo resumen** antes de enviar. El botón de envío está desactivado mientras falte configuración.

Solo se envían al correo guardado las coincidencias nuevas/cambios y recordatorios diarios de vigentes que vencen en menos de 72 horas. Se excluyen descartadas e históricas por defecto. Si quieres estudiar compradores históricos en el correo, activa esa opción explícitamente.

Se necesita una consulta completa de la fuente en las últimas 24 horas para enviar. Los registros se marcan como notificados solo después de que el proveedor acepte el correo; se conserva una bandeja de salida y una clave de idempotencia para reintentos. La aceptación del proveedor no demuestra llegada a la bandeja de entrada.

**Durante la construcción no se envió ningún correo real.** Las pruebas de entrega usan un proveedor simulado. Faltan la clave y un remitente autorizado para validar una entrega real.

## Programación y privacidad

- Un proceso de fondo consulta cada 6 horas por defecto, refresca antes del resumen y revisa documentos pendientes en lotes de cuatro. Las preferencias permiten ajustar el intervalo, el horario y la ventana de búsqueda.
- Los procesos no sobreviven a apagar/restaurar la máquina: inicia de nuevo el servidor. Los datos y cursores se conservan en `.data/`.
- SQLite local, sin servicios de base de datos externos. Credenciales derivadas con PBKDF2, sesiones aleatorias almacenadas como hash, cookies HttpOnly/SameSite y protección CSRF. La instalación inicial exige un código local; no permite que un visitante anónimo cree la cuenta sin él.
- No hay analítica ni solicitudes de fuentes tipográficas externas.
- Las oportunidades consultadas se almacenan localmente; los resúmenes seleccionados se transmiten a Resend y al destinatario configurado. No se envían notas a las entidades compradoras.
- Respalda `.data/` y tus variables de forma privada. Para una copia consistente con el servidor en marcha usa la API de backup de SQLite, no copies solo el archivo principal omitiendo WAL.

### Servidor privado permanente

Ejecuta MOLT bajo un supervisor (por ejemplo systemd o tu plataforma de contenedores), con reinicio automático, almacenamiento persistente para `.data/` y **un único proceso web**. Coloca un proxy HTTPS propio delante del puerto interno y configura `MOLT_SECURE_COOKIES=true`. Mantén el puerto interno fuera de acceso público directo. Crea el usuario antes de habilitar acceso remoto y protege también el acceso a la consola.

No se ha desplegado en un dominio público ni se ha contratado infraestructura. El entorno actual es de desarrollo; no es un alojamiento permanente. La publicación de la configuración cloud conserva la preparación, pero no mantiene procesos activos por sí sola.

## Comandos y validación

```bash
uv run --frozen python -m molt sync
uv run --frozen python -m molt documents --limit 4
uv run --frozen python -m molt export --output .data/MOLT-oportunidades.xlsx
# Envía únicamente si están configurados proveedor y destinatario:
uv run --frozen python -m molt digest

uv run --frozen pytest -q
uv run --frozen ruff check molt tests scripts
PYTHONPATH=. uv run --frozen python scripts/browser_smoke.py
```

El smoke test del navegador usa Chromium instalado en `/usr/bin/chromium`, una base temporal y una copia de registros públicos reales. Prueba alta privada, búsqueda, ficha, seguimiento, Excel, preferencias, resumen, móvil y cierre de sesión. No altera tu cuenta ni envía correos. Los tests de clasificación/entrega usan fixtures identificados como pruebas.

Los resultados y limitaciones de la instancia preparada se documentan en [docs/VALIDACION.md](docs/VALIDACION.md).
