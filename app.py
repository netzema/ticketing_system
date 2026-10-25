from datetime import datetime, timedelta, timezone
from functools import wraps
import hashlib
import os
import re
import secrets
import sqlite3
import time
import unicodedata

from dotenv import load_dotenv
from flask import (
    Flask,
    abort,
    g,
    jsonify,
    redirect,
    render_template,
    render_template_string,
    request,
    session,
    url_for,
)

from config import BASE_PATH, PORT, URL


load_dotenv()

DB = os.getenv("TICKETS_DB_PATH", f"{BASE_PATH}/tickets.db")
SCANNER_VERSION = "2026-10-25.1"
MUSIC_REQUEST_STATUSES = {"new", "later", "played", "rejected"}
GUEST_COOKIE_NAME = "oktoberfest_musikwunsch"
MUSIC_REQUESTS_BEFORE_COOLDOWN = 3

app = Flask(__name__)
app.config.update(
    SECRET_KEY=(
        os.getenv("FLASK_SECRET_KEY")
        or os.getenv("RESET_SECRET")
        or secrets.token_hex(32)
    ),
    DJ_PASSWORD=os.getenv("DJ_PASSWORD"),
    MUSIC_REQUEST_COOLDOWN_SECONDS=int(
        os.getenv("MUSIC_REQUEST_COOLDOWN_SECONDS", "600")
    ),
    MAX_CONTENT_LENGTH=16 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("SESSION_COOKIE_SECURE", "1") == "1",
)


def utc_now():
    return datetime.now(timezone.utc)


def utc_timestamp(value=None):
    return (value or utc_now()).isoformat(timespec="seconds")


def parse_timestamp(value):
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def ensure_music_request_schema(db):
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS music_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            song TEXT NOT NULL,
            title TEXT NOT NULL,
            artist TEXT NOT NULL,
            normalized_song TEXT NOT NULL,
            normalized_title TEXT NOT NULL,
            normalized_artist TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'new'
                CHECK (status IN ('new', 'later', 'played', 'rejected')),
            request_count INTEGER NOT NULL DEFAULT 1 CHECK (request_count >= 1),
            sort_order INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            last_requested_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS music_request_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS music_request_clients (
            client_hash TEXT PRIMARY KEY,
            last_submitted_at TEXT NOT NULL,
            submission_count INTEGER NOT NULL DEFAULT 0,
            blocked_until TEXT
        );

        CREATE TABLE IF NOT EXISTS music_request_submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_hash TEXT NOT NULL,
            submitted_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS dj_login_attempts (
            client_hash TEXT PRIMARY KEY,
            failures INTEGER NOT NULL,
            window_started_at REAL NOT NULL,
            blocked_until REAL
        );
        """
    )

    columns = {
        row[1] for row in db.execute("PRAGMA table_info(music_requests)").fetchall()
    }
    migration_columns = {
        "title": "TEXT",
        "artist": "TEXT",
        "normalized_title": "TEXT",
        "normalized_artist": "TEXT",
        "sort_order": "INTEGER",
    }
    for column, data_type in migration_columns.items():
        if column not in columns:
            try:
                db.execute(f"ALTER TABLE music_requests ADD COLUMN {column} {data_type}")
            except sqlite3.OperationalError as error:
                if "duplicate column name" not in str(error).casefold():
                    raise

    client_columns = {
        row[1]
        for row in db.execute("PRAGMA table_info(music_request_clients)").fetchall()
    }
    client_migration_columns = {
        "submission_count": "INTEGER NOT NULL DEFAULT 0",
        "blocked_until": "TEXT",
    }
    for column, data_type in client_migration_columns.items():
        if column not in client_columns:
            try:
                db.execute(
                    f"ALTER TABLE music_request_clients ADD COLUMN {column} {data_type}"
                )
            except sqlite3.OperationalError as error:
                if "duplicate column name" not in str(error).casefold():
                    raise

    db.execute(
        """
        UPDATE music_requests
        SET title = COALESCE(NULLIF(title, ''), song),
            artist = COALESCE(artist, ''),
            normalized_title = COALESCE(NULLIF(normalized_title, ''), normalized_song),
            normalized_artist = COALESCE(normalized_artist, '')
        WHERE title IS NULL OR title = ''
           OR artist IS NULL
           OR normalized_title IS NULL OR normalized_title = ''
           OR normalized_artist IS NULL
        """
    )
    if db.execute(
        "SELECT 1 FROM music_requests WHERE sort_order IS NULL LIMIT 1"
    ).fetchone():
        status_ordering = {
            "new": "last_requested_at DESC, id DESC",
            "later": "updated_at ASC, id ASC",
            "played": "updated_at DESC, id DESC",
            "rejected": "updated_at DESC, id DESC",
        }
        for status, ordering in status_ordering.items():
            rows = db.execute(
                f"SELECT id FROM music_requests WHERE status = ? ORDER BY {ordering}",
                (status,),
            ).fetchall()
            db.executemany(
                "UPDATE music_requests SET sort_order = ? WHERE id = ?",
                ((position, row["id"]) for position, row in enumerate(rows)),
            )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_music_requests_status ON music_requests(status, updated_at)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_music_requests_order ON music_requests(status, sort_order, id)"
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_music_request_submissions_client_time
        ON music_request_submissions(client_hash, submitted_at)
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_music_requests_match
        ON music_requests(normalized_title, normalized_artist, status)
        """
    )
    db.execute(
        """
        INSERT OR IGNORE INTO music_request_settings(key, value, updated_at)
        VALUES ('accepting_requests', '1', ?)
        """,
        (utc_timestamp(),),
    )
    db.commit()


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB, timeout=10)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA busy_timeout = 10000")
        g.db.execute("PRAGMA foreign_keys = ON")
        ensure_music_request_schema(g.db)
    return g.db


@app.teardown_appcontext
def close_db(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def requests_are_open(db=None):
    row = (db or get_db()).execute(
        "SELECT value FROM music_request_settings WHERE key = 'accepting_requests'"
    ).fetchone()
    return bool(row and row["value"] == "1")


def recent_music_request_submissions(db, hashed_token, now):
    cutoff = utc_timestamp(
        now - timedelta(seconds=app.config["MUSIC_REQUEST_COOLDOWN_SECONDS"])
    )
    return db.execute(
        """
        SELECT submitted_at
        FROM music_request_submissions
        WHERE client_hash = ? AND submitted_at > ?
        ORDER BY submitted_at, id
        """,
        (hashed_token, cutoff),
    ).fetchall()


def music_request_retry_after(submissions, now):
    if len(submissions) < MUSIC_REQUESTS_BEFORE_COOLDOWN:
        return 0
    oldest = parse_timestamp(submissions[0]["submitted_at"])
    if not oldest:
        return app.config["MUSIC_REQUEST_COOLDOWN_SECONDS"]
    available_at = oldest + timedelta(
        seconds=app.config["MUSIC_REQUEST_COOLDOWN_SECONDS"]
    )
    return max(1, int((available_at - now).total_seconds() + 0.999))


def normalize_music_text(value):
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    return "".join(character for character in decomposed if character.isalnum())


def secure_text_equals(supplied, expected):
    if not isinstance(supplied, str) or not isinstance(expected, str):
        return False
    return secrets.compare_digest(
        supplied.encode("utf-8"),
        expected.encode("utf-8"),
    )


def guest_token():
    token = request.cookies.get(GUEST_COOKIE_NAME, "")
    if re.fullmatch(r"[A-Za-z0-9_-]{24,100}", token):
        return token, False
    return secrets.token_urlsafe(24), True


def set_guest_cookie(response, token, is_new):
    if is_new:
        response.set_cookie(
            GUEST_COOKIE_NAME,
            token,
            max_age=60 * 60 * 24 * 3,
            httponly=True,
            secure=request.is_secure,
            samesite="Lax",
            path="/",
        )
    return response


def client_hash(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def serialize_music_request(row):
    return {
        "id": row["id"],
        "song": row["song"],
        "title": row["title"] or row["song"],
        "artist": row["artist"] or "",
        "status": row["status"],
        "request_count": row["request_count"],
        "sort_order": row["sort_order"],
        "created_at": row["created_at"],
        "last_requested_at": row["last_requested_at"],
        "updated_at": row["updated_at"],
    }


def next_music_request_order(db, status, place_first):
    aggregate = "MIN" if place_first else "MAX"
    row = db.execute(
        f"SELECT {aggregate}(sort_order) AS edge FROM music_requests WHERE status = ?",
        (status,),
    ).fetchone()
    edge = row["edge"] if row and row["edge"] is not None else 0
    return edge - 1 if place_first else edge + 1


def csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


app.jinja_env.globals["csrf_token"] = csrf_token


def dj_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("dj_authenticated"):
            if request.path.startswith("/api/"):
                return jsonify(error="Anmeldung erforderlich"), 401
            return redirect(url_for("dj_login"))
        return view(*args, **kwargs)

    return wrapped


def csrf_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        supplied = request.headers.get("X-CSRF-Token", "")
        expected = session.get("csrf_token", "")
        if not supplied or not expected or not secure_text_equals(supplied, expected):
            return jsonify(error="Ungültige Sicherheitsanfrage"), 403
        return view(*args, **kwargs)

    return wrapped


def login_client_hash():
    address = request.headers.get("X-Real-IP") or request.remote_addr or "unknown"
    return client_hash(address)


def login_is_blocked(db, key):
    now = time.time()
    row = db.execute(
        "SELECT failures, window_started_at, blocked_until FROM dj_login_attempts WHERE client_hash = ?",
        (key,),
    ).fetchone()
    if not row:
        return False
    if row["blocked_until"] and row["blocked_until"] > now:
        return True
    if now - row["window_started_at"] > 600:
        db.execute("DELETE FROM dj_login_attempts WHERE client_hash = ?", (key,))
        db.commit()
    return False


def register_failed_login(db, key):
    now = time.time()
    row = db.execute(
        "SELECT failures, window_started_at FROM dj_login_attempts WHERE client_hash = ?",
        (key,),
    ).fetchone()
    if not row or now - row["window_started_at"] > 600:
        failures = 1
        window_started_at = now
    else:
        failures = row["failures"] + 1
        window_started_at = row["window_started_at"]
    blocked_until = now + 600 if failures >= 5 else None
    db.execute(
        """
        INSERT INTO dj_login_attempts(client_hash, failures, window_started_at, blocked_until)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(client_hash) DO UPDATE SET
            failures = excluded.failures,
            window_started_at = excluded.window_started_at,
            blocked_until = excluded.blocked_until
        """,
        (key, failures, window_started_at, blocked_until),
    )
    db.commit()


@app.after_request
def set_response_headers(response):
    no_store_endpoints = {
        "home",
        "scan",
        "scan_count",
        "validate",
        "music_request_page",
        "submit_music_request",
        "dj_login",
        "dj_dashboard",
        "api_dj_requests",
    }
    if request.endpoint in no_store_endpoints or request.path.startswith("/api/dj/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    if request.endpoint == "scan":
        response.headers["X-Scanner-Version"] = SCANNER_VERSION
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    return response


@app.route("/")
def home():
    return redirect("https://www.netzldatasolutions.at/", code=302)


@app.route("/musikwunsch")
def music_request_page():
    token, is_new = guest_token()
    db = get_db()
    now = utc_now()
    submissions = recent_music_request_submissions(db, client_hash(token), now)
    device_retry_after = music_request_retry_after(submissions, now)
    response = app.make_response(
        render_template(
            "music_request.html",
            accepting_requests=requests_are_open(db),
            cooldown_seconds=app.config["MUSIC_REQUEST_COOLDOWN_SECONDS"],
            device_retry_after=device_retry_after,
        )
    )
    return set_guest_cookie(response, token, is_new)


@app.post("/api/musikwunsch")
def submit_music_request():
    token, is_new = guest_token()

    if not request.is_json:
        response = jsonify(error="Bitte das Formular verwenden")
        response.status_code = 415
        return set_guest_cookie(response, token, is_new)

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        response = jsonify(error="Ungültige Anfrage")
        response.status_code = 400
        return set_guest_cookie(response, token, is_new)
    if str(payload.get("website", "")).strip():
        response = jsonify(
            message="Dein Musikwunsch wurde an DJ Leo gesendet.",
            accepted=True,
        )
        response.status_code = 201
        return set_guest_cookie(response, token, is_new)

    title_value = payload.get("title", "")
    artist_value = payload.get("artist", "")
    if not isinstance(title_value, str) or not isinstance(artist_value, str):
        response = jsonify(error="Bitte gib Titel und Interpret ein")
        response.status_code = 400
        return set_guest_cookie(response, token, is_new)
    title = re.sub(r"\s+", " ", title_value).strip()
    artist = re.sub(r"\s+", " ", artist_value).strip()
    if len(title) < 2:
        response = jsonify(error="Bitte gib den Titel ein")
        response.status_code = 400
        return set_guest_cookie(response, token, is_new)
    if len(artist) < 2:
        response = jsonify(error="Bitte gib den Interpreten ein")
        response.status_code = 400
        return set_guest_cookie(response, token, is_new)
    if len(title) > 100 or len(artist) > 100:
        response = jsonify(error="Bitte kürze Titel und Interpret auf jeweils 100 Zeichen")
        response.status_code = 400
        return set_guest_cookie(response, token, is_new)

    normalized_title = normalize_music_text(title)
    normalized_artist = normalize_music_text(artist)
    if len(normalized_title) < 2 or len(normalized_artist) < 2:
        response = jsonify(error="Bitte gib Titel und Interpret ein")
        response.status_code = 400
        return set_guest_cookie(response, token, is_new)
    song = f"{title} - {artist}"
    normalized_song = f"{normalized_title}|{normalized_artist}"

    db = get_db()
    if not requests_are_open(db):
        response = jsonify(error="Musikwünsche sind momentan pausiert")
        response.status_code = 423
        return set_guest_cookie(response, token, is_new)

    now = utc_now()
    now_text = utc_timestamp(now)
    hashed_token = client_hash(token)

    try:
        db.execute("BEGIN IMMEDIATE")
        cutoff = utc_timestamp(
            now - timedelta(seconds=app.config["MUSIC_REQUEST_COOLDOWN_SECONDS"])
        )
        db.execute(
            "DELETE FROM music_request_submissions WHERE submitted_at <= ?",
            (cutoff,),
        )
        submissions = recent_music_request_submissions(db, hashed_token, now)
        if len(submissions) >= MUSIC_REQUESTS_BEFORE_COOLDOWN:
            retry_after = music_request_retry_after(submissions, now)
            blocked_until_text = utc_timestamp(
                now + timedelta(seconds=retry_after)
            )
            db.execute(
                """
                UPDATE music_request_clients
                SET submission_count = ?, blocked_until = ?
                WHERE client_hash = ?
                """,
                (len(submissions), blocked_until_text, hashed_token),
            )
            db.commit()
            response = jsonify(
                error="Du hast bereits drei Wünsche innerhalb von zehn Minuten gesendet. Bitte warte kurz.",
                retry_after=retry_after,
            )
            response.status_code = 429
            response.headers["Retry-After"] = str(retry_after)
            return set_guest_cookie(response, token, is_new)

        existing = db.execute(
            """
            SELECT * FROM music_requests
            WHERE normalized_title = ?
              AND normalized_artist = ?
              AND status IN ('new', 'later')
            ORDER BY id DESC
            LIMIT 1
            """,
            (normalized_title, normalized_artist),
        ).fetchone()

        if existing:
            db.execute(
                """
                UPDATE music_requests
                SET request_count = request_count + 1,
                    last_requested_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (now_text, now_text, existing["id"]),
            )
            request_id = existing["id"]
            duplicate = True
        else:
            sort_order = next_music_request_order(db, "new", place_first=True)
            cursor = db.execute(
                """
                INSERT INTO music_requests(
                    song, title, artist,
                    normalized_song, normalized_title, normalized_artist,
                    status, request_count, sort_order,
                    created_at, last_requested_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'new', 1, ?, ?, ?, ?)
                """,
                (
                    song,
                    title,
                    artist,
                    normalized_song,
                    normalized_title,
                    normalized_artist,
                    sort_order,
                    now_text,
                    now_text,
                    now_text,
                ),
            )
            request_id = cursor.lastrowid
            duplicate = False

        db.execute(
            """
            INSERT INTO music_request_submissions(client_hash, submitted_at)
            VALUES (?, ?)
            """,
            (hashed_token, now_text),
        )
        submissions = recent_music_request_submissions(db, hashed_token, now)
        submission_count = len(submissions)
        cooldown_active = submission_count >= MUSIC_REQUESTS_BEFORE_COOLDOWN
        retry_after = music_request_retry_after(submissions, now)
        blocked_until_text = (
            utc_timestamp(now + timedelta(seconds=retry_after))
            if cooldown_active
            else None
        )

        db.execute(
            """
            INSERT INTO music_request_clients(
                client_hash, last_submitted_at, submission_count, blocked_until
            )
            VALUES (?, ?, ?, ?)
            ON CONFLICT(client_hash) DO UPDATE SET
                last_submitted_at = excluded.last_submitted_at,
                submission_count = excluded.submission_count,
                blocked_until = excluded.blocked_until
            """,
            (hashed_token, now_text, submission_count, blocked_until_text),
        )
        db.commit()
    except sqlite3.Error:
        db.rollback()
        app.logger.exception("Musikwunsch konnte nicht gespeichert werden")
        response = jsonify(error="Der Musikwunsch konnte gerade nicht gespeichert werden")
        response.status_code = 503
        return set_guest_cookie(response, token, is_new)

    saved = db.execute("SELECT * FROM music_requests WHERE id = ?", (request_id,)).fetchone()
    response = jsonify(
        message="Dein Musikwunsch wurde an DJ Leo gesendet.",
        accepted=True,
        duplicate=duplicate,
        request_count=saved["request_count"],
        remaining_requests=max(
            0, MUSIC_REQUESTS_BEFORE_COOLDOWN - submission_count
        ),
        cooldown_active=cooldown_active,
        retry_after=retry_after,
    )
    response.status_code = 201
    return set_guest_cookie(response, token, is_new)


@app.route("/dj/musikwunsch/anmelden", methods=["GET", "POST"])
def dj_login():
    if session.get("dj_authenticated"):
        return redirect(url_for("dj_dashboard"))

    error = None
    configured = bool(app.config.get("DJ_PASSWORD"))
    if request.method == "POST":
        supplied_csrf = request.form.get("csrf_token", "")
        if not supplied_csrf or not secure_text_equals(supplied_csrf, csrf_token()):
            abort(400)
        if not configured:
            error = "Der DJ-Zugang ist noch nicht eingerichtet."
        else:
            db = get_db()
            key = login_client_hash()
            if login_is_blocked(db, key):
                error = "Zu viele Versuche. Bitte warte zehn Minuten."
            else:
                password = request.form.get("password", "")
                if secure_text_equals(password, app.config["DJ_PASSWORD"]):
                    db.execute("DELETE FROM dj_login_attempts WHERE client_hash = ?", (key,))
                    db.commit()
                    session.clear()
                    session["dj_authenticated"] = True
                    csrf_token()
                    return redirect(url_for("dj_dashboard"))
                register_failed_login(db, key)
                error = "Das Passwort ist nicht korrekt."

    return render_template("dj_login.html", error=error, configured=configured)


@app.post("/dj/musikwunsch/abmelden")
@dj_required
def dj_logout():
    supplied = request.form.get("csrf_token", "")
    expected = session.get("csrf_token", "")
    if not supplied or not expected or not secure_text_equals(supplied, expected):
        abort(400)
    session.clear()
    return redirect(url_for("dj_login"))


@app.route("/dj/musikwunsch")
@dj_required
def dj_dashboard():
    return render_template("dj_dashboard.html")


@app.get("/api/dj/musikwunsch")
@dj_required
def api_dj_requests():
    db = get_db()
    rows = db.execute(
        "SELECT * FROM music_requests ORDER BY status, sort_order, id"
    ).fetchall()
    return jsonify(
        requests=[serialize_music_request(row) for row in rows],
        accepting_requests=requests_are_open(db),
        csrf_token=csrf_token(),
        server_time=utc_timestamp(),
    )


@app.post("/api/dj/musikwunsch/<int:request_id>/status")
@dj_required
@csrf_required
def update_music_request_status(request_id):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(error="Ungültige Anfrage"), 400
    new_status = payload.get("status")
    if new_status not in MUSIC_REQUEST_STATUSES:
        return jsonify(error="Unbekannter Status"), 400

    db = get_db()
    db.execute("BEGIN IMMEDIATE")
    current = db.execute(
        "SELECT * FROM music_requests WHERE id = ?", (request_id,)
    ).fetchone()
    if not current:
        db.rollback()
        return jsonify(error="Musikwunsch nicht gefunden"), 404

    previous_status = current["status"]
    sort_order = current["sort_order"]
    if new_status != previous_status:
        sort_order = next_music_request_order(
            db,
            new_status,
            place_first=new_status != "later",
        )
    db.execute(
        """
        UPDATE music_requests
        SET status = ?, sort_order = ?, updated_at = ?
        WHERE id = ?
        """,
        (new_status, sort_order, utc_timestamp(), request_id),
    )
    db.commit()
    updated = db.execute(
        "SELECT * FROM music_requests WHERE id = ?", (request_id,)
    ).fetchone()
    return jsonify(
        request=serialize_music_request(updated),
        previous_status=previous_status,
    )


@app.post("/api/dj/musikwunsch/reihenfolge")
@dj_required
@csrf_required
def update_music_request_order():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(error="Ungültige Anfrage"), 400

    status = payload.get("status")
    request_ids = payload.get("request_ids")
    if status not in MUSIC_REQUEST_STATUSES:
        return jsonify(error="Unbekannter Status"), 400
    if (
        not isinstance(request_ids, list)
        or any(not isinstance(item, int) or isinstance(item, bool) for item in request_ids)
        or len(request_ids) != len(set(request_ids))
    ):
        return jsonify(error="Ungültige Reihenfolge"), 400

    db = get_db()
    db.execute("BEGIN IMMEDIATE")
    current_rows = db.execute(
        """
        SELECT * FROM music_requests
        WHERE status = ?
        ORDER BY sort_order, id
        """,
        (status,),
    ).fetchall()
    current_ids = [row["id"] for row in current_rows]
    if set(request_ids) != set(current_ids):
        db.rollback()
        return (
            jsonify(error="Die Liste hat sich geändert. Sie wird neu geladen."),
            409,
        )

    db.executemany(
        "UPDATE music_requests SET sort_order = ? WHERE id = ? AND status = ?",
        ((position, request_id, status) for position, request_id in enumerate(request_ids)),
    )
    db.commit()
    updated_rows = db.execute(
        """
        SELECT * FROM music_requests
        WHERE status = ?
        ORDER BY sort_order, id
        """,
        (status,),
    ).fetchall()
    return jsonify(requests=[serialize_music_request(row) for row in updated_rows])


@app.post("/api/dj/musikwunsch/annahme")
@dj_required
@csrf_required
def update_request_acceptance():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(error="Ungültige Anfrage"), 400
    accepting = payload.get("accepting")
    if not isinstance(accepting, bool):
        return jsonify(error="Ungültige Einstellung"), 400

    db = get_db()
    db.execute(
        """
        UPDATE music_request_settings
        SET value = ?, updated_at = ?
        WHERE key = 'accepting_requests'
        """,
        ("1" if accepting else "0", utc_timestamp()),
    )
    db.commit()
    return jsonify(accepting_requests=accepting)


@app.post("/api/dj/musikwunsch/alle-loeschen")
@dj_required
@csrf_required
def delete_all_music_requests():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(error="Ungültige Anfrage"), 400
    if payload.get("confirmation") != "ALLE LÖSCHEN":
        return jsonify(error="Bestätigung fehlt"), 400

    db = get_db()
    db.execute("BEGIN IMMEDIATE")
    db.execute("DELETE FROM music_requests")
    db.execute("DELETE FROM music_request_submissions")
    db.execute("DELETE FROM music_request_clients")
    db.commit()
    return jsonify(deleted=True)


@app.route("/validate/<tid>")
def validate(tid):
    db = get_db()
    now = datetime.now()
    scanned_at = now.isoformat(sep=" ", timespec="seconds")

    updated = db.execute(
        "UPDATE tickets SET scanned_at = ? WHERE ticket_id = ? AND scanned_at IS NULL",
        (scanned_at, tid),
    )
    db.commit()

    count = None
    detail = None
    scanned_time = None
    age_seconds = None

    if updated.rowcount == 1:
        status = "valid"
        message = "Ticket gültig"
        color = "green"
        count = db.execute(
            "SELECT COUNT(*) FROM tickets WHERE scanned_at IS NOT NULL"
        ).fetchone()[0]
    else:
        row = db.execute(
            "SELECT scanned_at FROM tickets WHERE ticket_id = ?", (tid,)
        ).fetchone()
        if not row:
            status = "invalid"
            message = "Ungültiges Ticket"
            color = "red"
        else:
            validated_at = datetime.fromisoformat(row[0])
            age_seconds = max(0, int((now - validated_at).total_seconds()))
            scanned_time = validated_at.strftime("%H:%M:%S")
            detail = f"Validiert um {scanned_time} Uhr"
            if age_seconds < 60:
                status = "recent"
                message = "Soeben validiert"
                color = "#159a91"
            else:
                status = "already_used"
                message = "Ticket bereits validiert"
                color = "#d88700"

    payload = {
        "status": status,
        "message": message,
        "detail": detail,
        "scanned_time": scanned_time,
        "age_seconds": age_seconds,
        "count": count,
    }

    if request.accept_mimetypes.best == "application/json":
        return jsonify(payload)

    html = """
    <!doctype html>
    <html lang="de">
      <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Ticketprüfung - Jugend Göttlesbrunn</title>
        <link rel="icon" type="image/svg+xml" href="/static/favicon.svg">
        <link rel="apple-touch-icon" href="/static/apple-touch-icon.png">
      </head>
      <body style="display:grid;min-height:100vh;margin:0;place-items:center;background:#f6f7f5;text-align:center;font-family:system-ui,sans-serif;color:#172019">
        <main>
          <h1 style="color:{{ color }}">{{ message }}</h1>
          {% if detail %}<p style="font-size:1.25em">{{ detail }}</p>{% endif %}
          {% if count is not none %}<p style="font-size:1.25em">Bereits eingescannt: <strong>{{ count }}</strong></p>{% endif %}
          <small style="display:block;margin-top:3rem;color:#6b756e">Technik von <a href="https://www.netzldatasolutions.at/" target="_blank" rel="noopener" style="color:inherit">Netzl Data Solutions</a></small>
        </main>
      </body>
    </html>
    """
    return render_template_string(
        html,
        message=message,
        color=color,
        count=count,
        detail=detail,
    )


@app.route("/reset")
def reset_tickets():
    key = request.args.get("key")
    reset_secret = os.getenv("RESET_SECRET")
    if not reset_secret or not key or not secure_text_equals(key, reset_secret):
        abort(403)

    db = get_db()
    db.execute("UPDATE tickets SET scanned_at = NULL")
    db.commit()
    return render_template_string(
        """
        <!doctype html><html lang="de"><head>
        <meta name="viewport" content="width=device-width">
        <link rel="icon" type="image/svg+xml" href="/static/favicon.svg">
        <link rel="apple-touch-icon" href="/static/apple-touch-icon.png">
        </head>
        <body style="text-align:center;font-family:system-ui,sans-serif;padding:3rem">
          <h2 style="color:green">Alle Tickets wurden zurückgesetzt.</h2>
          <small style="color:#6b756e">Technik von <a href="https://www.netzldatasolutions.at/" target="_blank" rel="noopener" style="color:inherit">Netzl Data Solutions</a></small>
        </body></html>
        """
    )


@app.route("/scan")
def scan():
    scanned_count = get_db().execute(
        "SELECT COUNT(*) FROM tickets WHERE scanned_at IS NOT NULL"
    ).fetchone()[0]
    return render_template(
        "scan.html",
        scanner_version=SCANNER_VERSION,
        scanned_count=scanned_count,
    )


@app.route("/api/scan-count")
def scan_count():
    count = get_db().execute(
        "SELECT COUNT(*) FROM tickets WHERE scanned_at IS NOT NULL"
    ).fetchone()[0]
    return jsonify(count=count)


if __name__ == "__main__":
    app.run(
        host=URL,
        port=int(PORT),
        ssl_context=(f"{BASE_PATH}/cert.pem", f"{BASE_PATH}/key.pem"),
    )
