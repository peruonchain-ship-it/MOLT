import hashlib
import hmac
import secrets
import time

from fastapi import HTTPException, Request


def hash_password(password):
    salt = secrets.token_hex(16)
    value = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 600_000)
    return f"pbkdf2_sha256$600000${salt}${value.hex()}"


def verify_password(password, encoded):
    try:
        _, rounds, salt, expected = encoded.split("$")
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(rounds))
        return hmac.compare_digest(actual.hex(), expected)
    except (ValueError, TypeError):
        return False


def attempt(db, request):
    ip = request.client.host if request.client else "unknown"
    key = hashlib.sha256(ip.encode()).hexdigest()
    now = time.time()
    with db.connect() as conn:
        conn.execute("DELETE FROM login_attempts WHERE created<?", (now - 900,))
        count = conn.execute("SELECT COUNT(*) FROM login_attempts WHERE key=?", (key,)).fetchone()[0]
        if count >= 8:
            raise HTTPException(429, "Demasiados intentos. Espera 15 minutos.")
        conn.execute("INSERT INTO login_attempts VALUES (?,?)", (key, now))


def create_session(db, response):
    token, csrf = secrets.token_urlsafe(40), secrets.token_urlsafe(32)
    expires = time.time() + 12 * 3600
    with db.connect() as conn:
        conn.execute("DELETE FROM sessions WHERE expires<?", (time.time(),))
        conn.execute("INSERT INTO sessions VALUES (?,?,?)", (hashlib.sha256(token.encode()).hexdigest(), csrf, expires))
    response.set_cookie("molt_session", token, max_age=12 * 3600, httponly=True,
                        secure=db.config.secure_cookies, samesite="strict", path="/")
    return csrf


def require_user(request: Request):
    db = request.app.state.db
    token = request.cookies.get("molt_session", "")
    with db.connect() as conn:
        session = conn.execute("SELECT * FROM sessions WHERE token=? AND expires>?",
                               (hashlib.sha256(token.encode()).hexdigest(), time.time())).fetchone()
    if not session:
        raise HTTPException(401, "Inicia sesión para acceder a tu radar privado.")
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        csrf = request.headers.get("X-CSRF-Token", "")
        if not hmac.compare_digest(csrf, session["csrf"]):
            raise HTTPException(403, "La sesión de seguridad cambió. Actualiza la página.")
    return dict(session)
