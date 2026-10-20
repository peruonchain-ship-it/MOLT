# DATALICITA · Publicación gratuita

El sitio público está publicado en **GitHub Pages**, sin comprar dominio ni contratar servicios de pago: **https://peruonchain-ship-it.github.io/MOLT/**. Se comprobó respuesta HTTPS 200 y contenido DATALICITA. GitHub informa `status: built`, HTTPS obligatorio y fuente `gh-pages` / `(root)`.

## Activación en GitHub

Durante la preparación, GitHub rechazó la activación mediante API con **HTTP 403: Resource not accessible by integration**. Después el ajuste quedó activado y se verificó el sitio publicado. **No queda pendiente activar Pages.** Si hace falta revisar ese ajuste en el futuro, está en:

`https://github.com/peruonchain-ship-it/MOLT/settings/pages`

Configuración actual:

1. En **Build and deployment**, elige **Deploy from a branch**.
2. Selecciona **gh-pages**, carpeta **/(root)**.
3. Pulsa **Save**. GitHub prepara el sitio; la propagación puede tardar unos minutos.

No se necesita un dominio propio ni una tarjeta para GitHub Pages en este repositorio público.

## Qué se publica

La rama `gh-pages` contiene únicamente HTML, CSS, icono, robots.txt y sitemap.xml generados por `scripts/build_public_site.py`. La base SQLite, notas, destinatario, cuenta privada, código de instalación y `.env` no forman parte del sitio estático.

El código de la aplicación se conserva en `main`. El panel necesita ejecutar Python y almacenar datos; GitHub Pages sirve archivos estáticos y no ejecuta ese backend. Por eso la portada gratuita explica que el panel todavía debe conectarse y no muestra un acceso roto como si funcionara.

Para publicar el panel privado con Render, Neon y consultas independientes de la web, sigue [la guía de alojamiento gratuito](ALOJAMIENTO_GRATUITO.md).

Para reconstruir el sitio:

```bash
python scripts/build_public_site.py --url https://peruonchain-ship-it.github.io/MOLT/
```

Para reconstruir y actualizar la rama pública sin cambiar de checkout:

```bash
python scripts/publish_public_site.py --url https://peruonchain-ship-it.github.io/MOLT/
```

El comando publica archivos en GitHub, conserva la rama de trabajo y no fuerza sobrescrituras. No crea worktrees ni activa Pages por sí mismo.

Cuando exista alojamiento para el panel, añade `--private-app-url https://TU-SERVIDOR/app`. No introduzcas contraseñas ni tokens en esa URL. Las instrucciones de contenedor de más abajo son una opción futura, no una contratación ni un despliegue ya realizado.

## Google

La portada incluye título, descripción, contenido legible sin JavaScript, canonical, datos estructurados y sitemap con la URL pública. El panel dinámico se sirve en `/app`, con `noindex`; sus APIs mantienen autenticación y no están en el sitemap.

Una vez que la web esté activa:

1. Accede a Google Search Console con tu propia cuenta.
2. Añade una propiedad de **prefijo de URL** para `https://peruonchain-ship-it.github.io/MOLT/`.
3. Obtén el método de verificación por etiqueta HTML. Esa etiqueta es pública; no se necesita compartir tu contraseña de Google.
4. Reconstruye con `--verification CODIGO_DE_LA_ETIQUETA` y vuelve a publicar la rama estática.
5. Verifica la propiedad y envía `https://peruonchain-ship-it.github.io/MOLT/sitemap.xml`; solicita la indexación de la portada.

No se ha verificado una propiedad de Search Console ni confirmado presencia en resultados. Preparar SEO o publicar una página no demuestra que Google ya la indexó.

## Comprobaciones realizadas

- 62 pruebas automatizadas pasaron; se comprobó también la portada estática en escritorio y móvil, sus recursos, enlaces internos y comportamiento de las preguntas frecuentes.
- El panel privado pasó la comprobación de navegador con los registros reales existentes, sin publicar esos datos en la portada.
- Las ramas `main` y `gh-pages` se subieron al repositorio. La actualización estática es repetible y no genera commits duplicados cuando no hay cambios.
- La activación por API fue rechazada inicialmente con HTTP 403; posteriormente se confirmó la configuración habilitada y el sitio publicado mediante consulta a Pages y solicitud HTTPS 200 a la portada. No se atribuye a una petición que falló el cambio de permisos o configuración.
- El contenedor opcional no se completó en este entorno por un fallo de DNS de la red de Docker al descargar dependencias. No es necesario para la publicación gratuita estática y no se presenta como despliegue validado.

## Aplicación completa y dominio propio, en el futuro

Se proporcionan `Dockerfile`, `compose.yaml` y `deploy/Caddyfile` para un servidor con almacenamiento persistente y HTTPS. No se requiere esta alternativa para la portada gratuita.

Con un dominio ya registrado y un servidor propio:

```bash
# Completa .env de forma privada y apunta el DNS al servidor.
# MOLT_SITE_DOMAIN debe ser un dominio que controles, sin https://.
docker compose up -d --build
docker compose exec web /opt/venv/bin/python -m molt setup-code
```

Caddy necesita que DNS y los puertos 80/443 apunten a ese servidor para emitir HTTPS. El volumen `radar_data` guarda la cuenta y SQLite. No compartas el código de instalación y conserva copias privadas. No se ha comprado ni comprobado la disponibilidad de `datalicita.pe` o `datalicita.com`.
