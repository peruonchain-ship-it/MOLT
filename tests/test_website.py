import json
from dataclasses import replace
from html.parser import HTMLParser
from xml.etree import ElementTree

import pytest
from fastapi.testclient import TestClient

from molt.app import create_app
from scripts.build_public_site import build


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attrs):
        for k, v in attrs:
            if k in ("href", "src"):
                self.urls.append(v)


def test_public_page_and_private_panel_are_separate(client):
    page = client.get("/")
    assert page.status_code == 200 and "DATALICITA" in page.text
    assert 'name="robots" content="index,follow"' in page.text
    assert 'id="opportunities-list"' not in page.text
    assert "x-robots-tag" not in page.headers
    assert client.get("/app").headers["x-robots-tag"].startswith("noindex")
    assert 'name="robots" content="noindex' in client.get("/app").text
    assert client.get("/api/opportunities").status_code == 401
    assert "noindex" in client.get("/api/opportunities").headers["x-robots-tag"]


def test_domain_is_required_before_emitting_a_sitemap(client):
    assert client.get("/sitemap.xml").status_code == 503
    assert "Sitemap:" not in client.get("/robots.txt").text


def test_google_metadata_and_sitemap_only_publish_the_public_page(config):
    config = replace(config, public_url="https://datalicita.example", google_site_verification='verify-code-123')
    with TestClient(create_app(config)) as client:
        body = client.get("/").text
        assert '<link rel="canonical" href="https://datalicita.example/">' in body
        assert 'name="google-site-verification" content="verify-code-123"' in body
        assert "Disallow: /app" in client.get("/robots.txt").text
        root = ElementTree.fromstring(client.get("/sitemap.xml").text)
        urls = [e.text for e in root.iter() if e.tag.endswith("loc")]
        assert urls == ["https://datalicita.example/"]


@pytest.mark.parametrize("url", ["http://example.com", "https://user:pass@example.com", "https://example.com/path", "https://example.com?x=1"])
def test_dynamic_site_requires_an_https_origin(config, url):
    with pytest.raises(ValueError):
        replace(config, public_url=url)


def test_static_site_has_relative_assets_and_no_false_private_access(tmp_path):
    path = build(tmp_path / "site", "https://example.github.io/MOLT")
    body = (path / "index.html").read_text()
    assert 'href="/app"' not in body
    assert "El panel aún no está conectado" in body
    parser = Links()
    parser.feed(body)
    for u in parser.urls:
        if u.startswith("./assets/"):
            assert (path / u[2:]).is_file()
    assert 'href="https://example.github.io/MOLT/"' in body
    assert set(p.name for p in path.iterdir()) == {"index.html", "assets", "sitemap.xml", "robots.txt", ".nojekyll", ".datalicita-build"}
    assert "owner@example.com" not in body


def test_build_preserves_an_unrelated_output_folder(tmp_path):
    folder = tmp_path / "my-files"
    folder.mkdir()
    (folder / "notes.txt").write_text("Do not overwrite")
    with pytest.raises(ValueError):
        build(folder, "https://example.com")
    assert (folder / "notes.txt").read_text() == "Do not overwrite"


def test_public_structured_data_is_valid_json(client):
    body = client.get("/").text
    graph = json.loads(body.split('<script type="application/ld+json">')[1].split('</script>')[0])
    assert graph["name"] == "DATALICITA" and graph["@type"] == "WebApplication"
