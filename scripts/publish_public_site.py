"""Update only the public gh-pages branch without checking out another branch or exposing app data."""

import argparse
import os
import subprocess
import tempfile
from pathlib import Path

from build_public_site import ROOT, build


def publish(url, private_app_url="", verification=""):
    output = build(ROOT / "public-site", url, private_app_url, verification)
    remote = subprocess.check_output(["git", "ls-remote", "origin", "refs/heads/gh-pages"], cwd=ROOT, text=True).strip()
    parent = None
    if remote:
        subprocess.run(["git", "fetch", "origin", "gh-pages"], cwd=ROOT, check=True)
        parent = subprocess.check_output(["git", "rev-parse", "FETCH_HEAD^{commit}"], cwd=ROOT, text=True).strip()
        old_html = subprocess.check_output(["git", "show", parent + ":index.html"], cwd=ROOT, text=True)
        if "DATALICITA" not in old_html:
            raise ValueError("La rama remota contiene otro sitio. No se reemplazará automáticamente.")
    with tempfile.TemporaryDirectory(prefix="datalicita-pages-") as tmp:
        env = {**os.environ, "GIT_INDEX_FILE": str(Path(tmp) / "index")}

        def git(*args):
            return subprocess.check_output(["git", *args], cwd=ROOT, env=env, text=True).strip()

        git("read-tree", "--empty")
        git("--work-tree=" + str(output), "add", "-f", "--", "index.html", "assets", "robots.txt", "sitemap.xml", ".nojekyll")
        tree = git("write-tree")
        if parent and git("rev-parse", parent + "^{tree}") == tree:
            print("El sitio público ya contiene esta versión. No se generaron commits duplicados.")
            return
        args = ["commit-tree", tree, "-m", "Update DATALICITA public website"]
        if parent:
            args += ["-p", parent]
        commit = git(*args)
        subprocess.run(["git", "push", "origin", commit + ":refs/heads/gh-pages"], cwd=ROOT, check=True)
        git("update-ref", "refs/heads/gh-pages", commit)
        print("Rama pública actualizada. La publicación web requiere GitHub Pages activado en Settings > Pages.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Publicar únicamente los archivos públicos de DATALICITA")
    parser.add_argument("--url", required=True)
    parser.add_argument("--private-app-url", default="")
    parser.add_argument("--verification", default="")
    args = parser.parse_args()
    publish(args.url, args.private_app_url, args.verification)
