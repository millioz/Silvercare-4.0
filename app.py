from __future__ import annotations

import os
import secrets
import sqlite3
from datetime import datetime, date, time, timedelta
from functools import wraps
from pathlib import Path
from zoneinfo import ZoneInfo

from flask import Flask, g, jsonify, redirect, render_template, request, session, url_for, flash
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB = BASE_DIR / "silvercare.db"


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
        DATABASE=os.environ.get("DATABASE", str(DEFAULT_DB)),
        TIMEZONE=os.environ.get("APP_TIMEZONE", "Asia/Seoul"),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "0") == "1",
    )
    if test_config:
        app.config.update(test_config)

    def now_local():
        return datetime.now(ZoneInfo(app.config["TIMEZONE"])).replace(tzinfo=None, microsecond=0)

    def connect_db():
        db = sqlite3.connect(app.config["DATABASE"])
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        return db

    def get_db():
        if "db" not in g:
            g.db = connect_db()
        return g.db

    @app.teardown_appcontext
    def close_db(_error=None):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    def init_db():
        db = connect_db()
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user' CHECK(role IN ('admin','caregiver','user')),
            device_token TEXT NOT NULL UNIQUE,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS medications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            dosage TEXT NOT NULL DEFAULT '',
            instructions TEXT NOT NULL DEFAULT '',
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS schedules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            medication_id INTEGER NOT NULL REFERENCES medications(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            time_local TEXT NOT NULL,
            grace_minutes INTEGER NOT NULL DEFAULT 60,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS dose_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            medication_id INTEGER NOT NULL REFERENCES medications(id) ON DELETE CASCADE,
            schedule_id INTEGER NOT NULL REFERENCES schedules(id) ON DELETE CASCADE,
            scheduled_for TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','taken','missed')),
            confirmed_at TEXT,
            confirmation_source TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(schedule_id, scheduled_for)
        );
        CREATE INDEX IF NOT EXISTS idx_events_user_time ON dose_events(user_id, scheduled_for DESC);
        CREATE INDEX IF NOT EXISTS idx_schedule_user ON schedules(user_id, active);
        """)
        db.commit()
        # A first-run admin is created for local setup. Change the password before exposing the app.
        admin_email = os.environ.get("ADMIN_EMAIL", "admin@silvercare.local")
        admin_password = os.environ.get("ADMIN_PASSWORD", "ChangeMe123!")
        existing = db.execute("SELECT id FROM users WHERE email = ?", (admin_email,)).fetchone()
        if not existing:
            db.execute(
                "INSERT INTO users(name,email,password_hash,role,device_token,created_at) VALUES(?,?,?,?,?,?)",
                ("SilverCare Admin", admin_email, generate_password_hash(admin_password), "admin", secrets.token_urlsafe(32), now_local().isoformat(timespec="seconds")),
            )
            db.commit()
        db.close()

    def current_user():
        user_id = session.get("user_id")
        if not user_id:
            return None
        return get_db().execute("SELECT id,name,email,role,active,device_token FROM users WHERE id=? AND active=1", (user_id,)).fetchone()

    def login_required(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            if not current_user():
                return redirect(url_for("login"))
            return fn(*args, **kwargs)
        return wrapped

    def staff_required(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            user = current_user()
            if not user:
                return jsonify({"error": "Authentication required"}), 401
            if user["role"] not in ("admin", "caregiver"):
                return jsonify({"error": "Caregiver or admin access required"}), 403
            return fn(*args, **kwargs)
        return wrapped

    def user_scope(requested_user_id=None):
        user = current_user()
        if user["role"] in ("admin", "caregiver") and requested_user_id:
            return int(requested_user_id)
        return int(user["id"])

    def ensure_today_events(user_id):
        db = get_db()
        now = now_local()
        today = now.date().isoformat()
        schedules = db.execute("""
            SELECT s.id AS schedule_id, s.time_local, s.grace_minutes, s.user_id,
                   m.id AS medication_id
            FROM schedules s JOIN medications m ON m.id=s.medication_id
            WHERE s.user_id=? AND s.active=1 AND m.active=1
        """, (user_id,)).fetchall()
        for schedule in schedules:
            scheduled_for = f"{today}T{schedule['time_local']}"
            db.execute("""
                INSERT OR IGNORE INTO dose_events
                (user_id, medication_id, schedule_id, scheduled_for, status, created_at)
                VALUES(?,?,?,?, 'pending', ?)
            """, (user_id, schedule["medication_id"], schedule["schedule_id"], scheduled_for, now.isoformat(timespec="seconds")))
        events = db.execute("""
            SELECT e.id,e.scheduled_for,e.status,s.grace_minutes
            FROM dose_events e JOIN schedules s ON s.id=e.schedule_id
            WHERE e.user_id=? AND e.status='pending' AND e.scheduled_for<=?
        """, (user_id, now.isoformat(timespec="seconds"))).fetchall()
        for event in events:
            due = datetime.fromisoformat(event["scheduled_for"])
            if now > due + timedelta(minutes=int(event["grace_minutes"])):
                db.execute("UPDATE dose_events SET status='missed' WHERE id=? AND status='pending'", (event["id"],))
        db.commit()

    def event_rows(user_id, limit=100):
        ensure_today_events(user_id)
        return get_db().execute("""
            SELECT e.id,e.scheduled_for,e.status,e.confirmed_at,e.confirmation_source,
                   m.name AS medication_name,m.dosage,m.instructions
            FROM dose_events e JOIN medications m ON m.id=e.medication_id
            WHERE e.user_id=? ORDER BY e.scheduled_for DESC LIMIT ?
        """, (user_id, limit)).fetchall()

    def serialize_event(row):
        return {key: row[key] for key in row.keys()}

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            email = request.form.get("email", "").strip()
            password = request.form.get("password", "")
            user = get_db().execute("SELECT * FROM users WHERE email=? AND active=1", (email,)).fetchone()
            if user and check_password_hash(user["password_hash"], password):
                session.clear()
                session["user_id"] = user["id"]
                return redirect(url_for("home"))
            flash("Email or password is incorrect.", "error")
        return render_template("login.html")

    @app.get("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.route("/change-password", methods=["GET", "POST"])
    @login_required
    def change_password():
        if request.method == "POST":
            old_password = request.form.get("current_password", "")
            new_password = request.form.get("new_password", "")
            user = get_db().execute("SELECT id,password_hash FROM users WHERE id=?", (session["user_id"],)).fetchone()
            if not check_password_hash(user["password_hash"], old_password):
                flash("Current password is incorrect.", "error")
            elif len(new_password) < 8:
                flash("New password must contain at least 8 characters.", "error")
            else:
                get_db().execute("UPDATE users SET password_hash=? WHERE id=?", (generate_password_hash(new_password), user["id"]))
                get_db().commit()
                flash("Password updated successfully.", "success")
                return redirect(url_for("home"))
        return render_template("change_password.html", user=current_user())

    @app.get("/")
    @login_required
    def home():
        user = current_user()
        if user["role"] in ("admin", "caregiver"):
            return render_template("admin.html", user=user)
        return render_template("dashboard.html", user=user)

    @app.get("/api/me")
    @login_required
    def api_me():
        u = current_user()
        return jsonify({"id": u["id"], "name": u["name"], "email": u["email"], "role": u["role"]})

    @app.get("/api/users")
    @login_required
    def api_users():
        u = current_user()
        if u["role"] not in ("admin", "caregiver"):
            return jsonify({"error": "Forbidden"}), 403
        rows = get_db().execute("SELECT id,name,email,role,active,created_at FROM users WHERE role='user' ORDER BY name").fetchall()
        return jsonify([dict(r) for r in rows])

    @app.post("/api/users")
    @staff_required
    def create_user():
        data = request.get_json(silent=True) or request.form
        name = str(data.get("name", "")).strip()
        email = str(data.get("email", "")).strip().lower()
        password = str(data.get("password", ""))
        if not name or not email or len(password) < 8:
            return jsonify({"error": "Name, email and a password of at least 8 characters are required."}), 400
        token = secrets.token_urlsafe(32)
        try:
            cur = get_db().execute(
                "INSERT INTO users(name,email,password_hash,role,device_token,created_at) VALUES(?,?,?,?,?,?)",
                (name, email, generate_password_hash(password), "user", token, now_local().isoformat(timespec="seconds")),
            )
            get_db().commit()
        except sqlite3.IntegrityError:
            return jsonify({"error": "That email address is already registered."}), 409
        return jsonify({"id": cur.lastrowid, "name": name, "email": email, "device_token": token}), 201

    @app.get("/api/medications")
    @login_required
    def api_medications():
        user = current_user()
        uid = user_scope(request.args.get("user_id"))
        rows = get_db().execute("""
            SELECT m.id,m.user_id,m.name,m.dosage,m.instructions,m.active,
                   GROUP_CONCAT(s.time_local, ', ') AS times
            FROM medications m LEFT JOIN schedules s ON s.medication_id=m.id AND s.active=1
            WHERE m.user_id=? GROUP BY m.id ORDER BY m.created_at DESC
        """, (uid,)).fetchall()
        return jsonify([dict(r) for r in rows])

    @app.post("/api/medications")
    @staff_required
    def create_medication():
        data = request.get_json(silent=True) or {}
        try:
            uid = int(data.get("user_id"))
            name = str(data.get("name", "")).strip()
            dosage = str(data.get("dosage", "")).strip()
            instructions = str(data.get("instructions", "")).strip()
            schedule_time = str(data.get("time", "")).strip()
            grace = max(5, min(240, int(data.get("grace_minutes", 60))))
            time.fromisoformat(schedule_time)
        except (TypeError, ValueError):
            return jsonify({"error": "Choose a patient, medication name and valid 24-hour time (HH:MM)."}), 400
        if not name:
            return jsonify({"error": "Medication name is required."}), 400
        patient = get_db().execute("SELECT id FROM users WHERE id=? AND role='user' AND active=1", (uid,)).fetchone()
        if not patient:
            return jsonify({"error": "Patient account not found."}), 404
        cur = get_db().execute("INSERT INTO medications(user_id,name,dosage,instructions,created_at) VALUES(?,?,?,?,?)", (uid,name,dosage,instructions,now_local().isoformat(timespec="seconds")))
        med_id = cur.lastrowid
        get_db().execute("INSERT INTO schedules(medication_id,user_id,time_local,grace_minutes,created_at) VALUES(?,?,?,?,?)", (med_id,uid,schedule_time,grace,now_local().isoformat(timespec="seconds")))
        get_db().commit()
        return jsonify({"id": med_id, "message": "Medication and daily reminder created."}), 201

    @app.delete("/api/medications/<int:medication_id>")
    @staff_required
    def deactivate_medication(medication_id):
        get_db().execute("UPDATE medications SET active=0 WHERE id=?", (medication_id,))
        get_db().execute("UPDATE schedules SET active=0 WHERE medication_id=?", (medication_id,))
        get_db().commit()
        return jsonify({"ok": True})

    @app.get("/api/events")
    @login_required
    def api_events():
        uid = user_scope(request.args.get("user_id"))
        return jsonify([serialize_event(r) for r in event_rows(uid)])

    @app.post("/api/events/<int:event_id>/confirm")
    @login_required
    def confirm_event(event_id):
        user = current_user()
        event = get_db().execute("SELECT * FROM dose_events WHERE id=?", (event_id,)).fetchone()
        if not event or (user["role"] == "user" and event["user_id"] != user["id"]):
            return jsonify({"error": "Event not found."}), 404
        if event["status"] == "taken":
            return jsonify({"ok": True, "message": "This event is already marked as confirmed."})
        get_db().execute("UPDATE dose_events SET status='taken',confirmed_at=?,confirmation_source='dashboard' WHERE id=?", (now_local().isoformat(timespec="seconds"), event_id))
        get_db().commit()
        return jsonify({"ok": True, "message": "Marked as user-confirmed. This records a confirmation, not independent proof of ingestion."})

    @app.get("/api/summary")
    @login_required
    def api_summary():
        uid = user_scope(request.args.get("user_id"))
        ensure_today_events(uid)
        today = now_local().date().isoformat()
        db = get_db()
        today_rows = db.execute("SELECT status,COUNT(*) AS n FROM dose_events WHERE user_id=? AND substr(scheduled_for,1,10)=? GROUP BY status", (uid,today)).fetchall()
        counts = {r["status"]: r["n"] for r in today_rows}
        week_start = (now_local().date() - timedelta(days=6)).isoformat()
        weekly = db.execute("""
            SELECT substr(scheduled_for,1,10) AS day,
                   SUM(CASE WHEN status='taken' THEN 1 ELSE 0 END) AS taken,
                   SUM(CASE WHEN status='missed' THEN 1 ELSE 0 END) AS missed,
                   SUM(CASE WHEN status IN ('taken','missed') THEN 1 ELSE 0 END) AS decided
            FROM dose_events WHERE user_id=? AND substr(scheduled_for,1,10)>=?
            GROUP BY substr(scheduled_for,1,10) ORDER BY day
        """, (uid,week_start)).fetchall()
        taken = sum(r["taken"] or 0 for r in weekly)
        decided = sum(r["decided"] or 0 for r in weekly)
        rate = round((taken / decided) * 100) if decided else None
        return jsonify({
            "today": {"taken": counts.get("taken",0), "missed": counts.get("missed",0), "pending": counts.get("pending",0), "total": sum(counts.values())},
            "confirmation_rate": rate,
            "rate_label": "User-confirmation rate",
            "weekly": [dict(r) for r in weekly],
            "timezone": app.config["TIMEZONE"],
        })

    def device_user():
        token = request.headers.get("X-Device-Token", "")
        if not token:
            return None
        return get_db().execute("SELECT id FROM users WHERE device_token=? AND active=1", (token,)).fetchone()

    @app.get("/api/device/next")
    def device_next():
        device = device_user()
        if not device:
            return jsonify({"error": "Valid X-Device-Token required."}), 401
        rows = event_rows(device["id"], 100)
        pending = sorted((r for r in rows if r["status"] == "pending"), key=lambda r: r["scheduled_for"])
        now_text = now_local().isoformat(timespec="seconds")
        due = [r for r in pending if r["scheduled_for"] <= now_text]
        return jsonify({"due": [serialize_event(r) for r in due[:5]], "upcoming": [serialize_event(r) for r in pending[:5]]})

    @app.post("/api/device/confirm")
    def device_confirm():
        device = device_user()
        if not device:
            return jsonify({"error": "Valid X-Device-Token required."}), 401
        data = request.get_json(silent=True) or {}
        try:
            event_id = int(data.get("event_id"))
        except (TypeError, ValueError):
            return jsonify({"error": "event_id is required."}), 400
        event = get_db().execute("SELECT id FROM dose_events WHERE id=? AND user_id=?", (event_id,device["id"])).fetchone()
        if not event:
            return jsonify({"error": "Event not found for this device."}), 404
        get_db().execute("UPDATE dose_events SET status='taken',confirmed_at=?,confirmation_source='esp32_button' WHERE id=?", (now_local().isoformat(timespec="seconds"),event_id))
        get_db().commit()
        return jsonify({"ok": True, "event_id": event_id, "status": "taken"})

    @app.get("/api/health")
    def api_health():
        return jsonify({"status": "ok", "service": "SilverCare", "time": now_local().isoformat(timespec="seconds")})

    with app.app_context():
        init_db()

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=os.environ.get("FLASK_DEBUG", "0") == "1")
