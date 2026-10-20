import argparse
import getpass
import json
import os

import psycopg
import uvicorn

from .auth import hash_password
from .config import Config
from .db import Database
from .documents import process_documents
from .mail import send_digest
from .repository import list_items
from .source import SyncService


def main():
    parser = argparse.ArgumentParser(description="DATALICITA · Radar privado de oportunidades")
    parser.add_argument("command", choices=["serve", "sync", "collect", "documents", "digest", "setup-code", "reset-password", "export"])
    parser.add_argument("--limit", type=int, default=4)
    parser.add_argument("--output", default="MOLT-oportunidades.xlsx")
    args = parser.parse_args()
    config = Config.from_env()
    if args.command == "collect" and not config.database_url:
        parser.error("El recolector externo requiere DATABASE_URL para compartir los datos con la web.")
    db = Database(config)
    if args.command == "serve":
        from .app import create_app
        uvicorn.run(create_app(config), host=os.getenv("MOLT_HOST", "127.0.0.1"),
                    port=int(os.getenv("PORT", os.getenv("MOLT_PORT", "8000"))), proxy_headers=False,
                    access_log=False)
    elif args.command == "setup-code":
        if db.initialized():
            print("El usuario privado ya existe. Usa reset-password si necesitas recuperar acceso.")
        else:
            print((config.data_dir / "setup-code").read_text())
    elif args.command == "reset-password":
        if not db.initialized():
            parser.error("Crea primero el acceso privado desde la pantalla de instalación.")
        password = getpass.getpass("Nueva contraseña (mínimo 12 caracteres): ")
        if len(password) < 12 or password != getpass.getpass("Repetir contraseña: "):
            parser.error("La contraseña es corta o no coincide.")
        with db.connect() as conn:
            conn.execute("UPDATE users SET password_hash=? WHERE id=1", (hash_password(password),))
            conn.execute("DELETE FROM sessions")
        print("Contraseña actualizada. Todas las sesiones anteriores fueron cerradas.")
    elif args.command == "collect":
        from .worker import collect_once
        result = collect_once(db)
        print(json.dumps(result))
        if result["status"] == "error":
            raise SystemExit(1)
    elif args.command == "sync":
        result = SyncService(db).run()
        print(json.dumps(result, ensure_ascii=False))
        if result["status"] in ("error", "partial"):
            raise SystemExit(1)
    elif args.command == "documents":
        if not 1 <= args.limit <= 50:
            parser.error("--limit debe estar entre 1 y 50.")
        print(json.dumps(process_documents(db, args.limit, force=True), ensure_ascii=False))
    elif args.command == "digest":
        result = send_digest(db)
        print(json.dumps(result, ensure_ascii=False))
        if result["status"] in ("blocked", "error"):
            raise SystemExit(1)
    elif args.command == "export":
        from pathlib import Path

        from .export import spreadsheet
        Path(args.output).write_bytes(spreadsheet(list_items(db), db.sync_status()))
        print("Excel creado: " + args.output)


if __name__ == "__main__":
    try:
        main()
    except psycopg.Error:
        raise SystemExit("No se pudo operar la base PostgreSQL. Revisa conexión, permisos y disponibilidad en el panel privado del proveedor.") from None
