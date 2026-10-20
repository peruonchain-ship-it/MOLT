"""Public presentation and crawler metadata. Never reads private records or preferences."""

import html
import json
from xml.sax.saxutils import escape

from fastapi import HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse, Response

from .config import ROOT


def landing(config):
    origin = config.public_url.rstrip("/")
    metadata = []
    if origin:
        url = html.escape(origin + "/", quote=True)
        metadata.extend([f'<link rel="canonical" href="{url}">',
                         f'<meta property="og:url" content="{url}">'])
    if config.google_site_verification:
        token = html.escape(config.google_site_verification, quote=True)
        metadata.append(f'<meta name="google-site-verification" content="{token}">')
    graph = {"@context": "https://schema.org", "@type": "WebApplication", "name": "DATALICITA",
             "applicationCategory": "BusinessApplication", "operatingSystem": "Web",
             "inLanguage": "es-PE", "description": "Radar privado de contrataciones públicas para eventos y servicios audiovisuales en Perú.",
             "featureList": ["Filtros por zona y servicio", "Revisión de documentos", "Seguimiento privado", "Exportación a Excel"]}
    if origin:
        graph["url"] = origin + "/"
    schema = json.dumps(graph, ensure_ascii=False).replace("<", "\\u003c")
    page = (ROOT / "molt/public/index.html").read_text()
    page = page.replace("<!-- SITE_METADATA -->", "\n".join(metadata))
    page = page.replace("<!-- STRUCTURED_DATA -->", '<script type="application/ld+json">' + schema + '</script>')
    return HTMLResponse(page)


def robots(config):
    body = "User-agent: *\nAllow: /\nDisallow: /app\nDisallow: /api/\nDisallow: /health\nDisallow: /static/\n"
    if config.public_url:
        body += "\nSitemap: " + config.public_url.rstrip("/") + "/sitemap.xml\n"
    return PlainTextResponse(body)


def sitemap(config):
    if not config.public_url:
        raise HTTPException(503, "El mapa del sitio se habilita al configurar el dominio público HTTPS.")
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
           '<url><loc>' + escape(config.public_url.rstrip("/") + "/") + '</loc></url></urlset>')
    return Response(xml, media_type="application/xml")
