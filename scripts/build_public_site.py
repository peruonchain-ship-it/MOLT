"""Build a static public site. Includes no database, account details, mail recipient, or credentials."""

import argparse
import html
import json
import shutil
from pathlib import Path
from urllib.parse import urlparse
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent


def checked_url(value):
    parsed = urlparse(value)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or parsed.port not in (None, 443)):
        raise ValueError("Se necesita una dirección pública HTTPS sin credenciales, consulta ni fragmento.")
    return value.rstrip("/")


def build(output, url, private_app_url="", verification=""):
    url = checked_url(url)
    if private_app_url:
        private_app_url = checked_url(private_app_url)
    output = Path(output).resolve()
    protected = (ROOT, ROOT / "molt", ROOT / ".data", ROOT / "tests", ROOT / "scripts", ROOT / ".git")
    if any(output == p or output in p.parents or p in output.parents for p in protected):
        # Permit only a dedicated new build folder beside source folders, never a source/data directory.
        if output != ROOT / "public-site":
            raise ValueError("La salida debe ser una carpeta de compilación separada del código y datos privados.")
    if output.exists() and any(p.name != ".datalicita-build" for p in output.iterdir()) and not (output / ".datalicita-build").exists():
        raise ValueError("La carpeta de salida contiene archivos ajenos a la compilación.")
    output.mkdir(parents=True, exist_ok=True)
    (output / ".datalicita-build").touch()
    page = (ROOT / "molt/public/index.html").read_text()
    metadata = [f'<link rel="canonical" href="{html.escape(url, quote=True)}/">',
                f'<meta property="og:url" content="{html.escape(url, quote=True)}/">']
    if verification:
        metadata.append(f'<meta name="google-site-verification" content="{html.escape(verification, quote=True)}">')
    graph = {"@context": "https://schema.org", "@type": "WebApplication", "name": "DATALICITA",
             "url": url + "/", "applicationCategory": "BusinessApplication", "operatingSystem": "Web",
             "inLanguage": "es-PE", "description": "Radar privado de contrataciones públicas para eventos y servicios audiovisuales en Perú."}
    schema = json.dumps(graph, ensure_ascii=False).replace("<", "\\u003c")
    page = page.replace("<!-- SITE_METADATA -->", "\n".join(metadata)).replace(
        "<!-- STRUCTURED_DATA -->", '<script type="application/ld+json">' + schema + '</script>')
    page = page.replace('/public-assets/', './assets/').replace('href="/"', 'href="./"')
    if private_app_url:
        page = page.replace('href="/app"', 'href="' + html.escape(private_app_url, quote=True) + '"')
    else:
        page = page.replace('href="/app"', 'href="#privado"')
        page = page.replace('Acceso privado <span>', 'Sobre el radar <span>')
        page = page.replace('Entrar a mi radar <span>', 'Conocer el radar <span>')
        page = page.replace('Abrir mi espacio privado <span>', 'Conoce el acceso privado <span>')
        page = page.replace('Ir al radar privado <span>', 'Conoce el radar <span>')
        page = page.replace('Acceso privado ↗', 'Sobre el acceso privado ↗')
        page = page.replace('Tus oportunidades seleccionadas, notas, destinatario de correo y seguimiento requieren iniciar sesión en el panel.',
                            'Tus oportunidades, notas y seguimiento requieren una instancia privada. El panel aún no está conectado a esta página pública.')
    (output / "index.html").write_text(page)
    shutil.copytree(ROOT / "molt/public/assets", output / "assets", dirs_exist_ok=True)
    (output / ".nojekyll").touch()
    (output / "robots.txt").write_text("User-agent: *\nAllow: /\n\nSitemap: " + url + "/sitemap.xml\n")
    (output / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>' + escape(url + "/") + '</loc></url></urlset>')
    expected = {"index.html", "assets", ".nojekyll", "robots.txt", "sitemap.xml", ".datalicita-build"}
    if set(p.name for p in output.iterdir()) != expected:
        raise ValueError("La carpeta pública contiene archivos inesperados. No debe publicarse.")
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compilar exclusivamente la página pública DATALICITA")
    parser.add_argument("--url", required=True)
    parser.add_argument("--private-app-url", default="")
    parser.add_argument("--verification", default="")
    parser.add_argument("--output", default="public-site")
    args = parser.parse_args()
    print(build(args.output, args.url, args.private_app_url, args.verification))
