"""
SilverCare PLUS — extra features that plug into the existing app WITHOUT editing app.py.

How it works: run.py imports your original `app`, then calls init_extensions(app).
That registers new API routes (/api/plus/...), a new page (/care-tools), new database
tables (CREATE IF NOT EXISTS — your old tables are never altered), a background
scheduler, login protection, and a small script that adds buttons to your pages.

Safety note: statuses are operational records only (not proof of ingestion), and
nothing here recommends, calculates or changes doses.
"""
from __future__ import annotations

import csv
import io
import os
import secrets
import sqlite3
import threading
import time as _time
from datetime import datetime, timedelta
from functools import wraps
from zoneinfo import ZoneInfo

from flask import (Blueprint, Response, current_app, flash, g, jsonify, redirect,
                   render_template, request, session, url_for)
from werkzeug.security import generate_password_hash

MAX_LOGIN_FAILS = 5
LOGIN_LOCK_MINUTES = 15
DEVICE_ONLINE_SECONDS = 180  # ESP32 polls every ~15 s; 3 min silence = offline

bp = Blueprint("plus", __name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id INTEGER, actor_name TEXT, action TEXT NOT NULL,
    target TEXT, detail TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS patient_profiles (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    emergency_name TEXT DEFAULT '', emergency_phone TEXT DEFAULT '',
    care_notes TEXT DEFAULT '', updated_at TEXT
);
CREATE TABLE IF NOT EXISTS med_stock (
    medication_id INTEGER PRIMARY KEY REFERENCES medications(id) ON DELETE CASCADE,
    quantity INTEGER NOT NULL DEFAULT 0,
    pills_per_dose INTEGER NOT NULL DEFAULT 1,
    low_days INTEGER NOT NULL DEFAULT 5,
    as_of TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS alert_ack (
    event_id INTEGER PRIMARY KEY REFERENCES dose_events(id) ON DELETE CASCADE,
    acked_by INTEGER, acked_by_name TEXT, note TEXT DEFAULT '', acked_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS device_status (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    last_seen TEXT NOT NULL, last_ip TEXT
);
CREATE TABLE IF NOT EXISTS login_attempts (
    key TEXT PRIMARY KEY, fails INTEGER NOT NULL DEFAULT 0,
    first_at TEXT NOT NULL, locked_until TEXT
);
"""


# ───────────────────────── helpers ─────────────────────────
def now_local(app=None):
    app = app or current_app
    return datetime.now(ZoneInfo(app.config["TIMEZONE"])).replace(tzinfo=None, microsecond=0)


def iso(dt):
    return dt.isoformat(timespec="seconds")


def open_db(path):
    con = sqlite3.connect(path, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def db():
    if "plus_db" not in g:
        g.plus_db = open_db(current_app.config["DATABASE"])
    return g.plus_db


def current_me():
    uid = session.get("user_id")
    if not uid:
        return None
    return db().execute("SELECT id,name,email,role FROM users WHERE id=? AND active=1", (uid,)).fetchone()


def guard(roles):
    """Role check + a simple CSRF defence (custom header) for every write request."""
    def deco(fn):
        @wraps(fn)
        def wrapped(*a, **kw):
            u = current_me()
            if not u:
                return jsonify(error="Authentication required"), 401
            if u["role"] not in roles:
                return jsonify(error="Your role is not allowed to do this."), 403
            if request.method not in ("GET", "HEAD") and request.headers.get("X-Requested-With") != "SilverCare":
                return jsonify(error="Missing security header."), 400
            g.me = u
            return fn(*a, **kw)
        return wrapped
    return deco


staff = guard(("admin", "caregiver"))
admin_only = guard(("admin",))
any_role = guard(("admin", "caregiver", "user"))


def audit(action, target="", detail=""):
    u = g.get("me")
    db().execute(
        "INSERT INTO audit_log(actor_id,actor_name,action,target,detail,created_at) VALUES(?,?,?,?,?,?)",
        (u["id"] if u else None, u["name"] if u else "system", action, str(target), str(detail)[:300], iso(now_local())),
    )
    db().commit()


def clean_time(value):
    """'8:05' / '08:05' / '08:05:00' -> '08:05' or raises ValueError."""
    parts = str(value).strip().split(":")
    if len(parts) < 2:
        raise ValueError
    h, m = int(parts[0]), int(parts[1])
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise ValueError
    return f"{h:02d}:{m:02d}"


def clamp_int(value, lo, hi, default):
    try:
        return max(lo, min(hi, int(value)))
    except (TypeError, ValueError):
        return default


def other_active_admins(con, excluding_id):
    return con.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND active=1 AND id<>?", (excluding_id,)).fetchone()[0]


def target_user(uid):
    """Return (row, error_response). Staff may only manage patients; admins manage everyone."""
    row = db().execute("SELECT id,name,email,role,active FROM users WHERE id=?", (uid,)).fetchone()
    if not row:
        return None, (jsonify(error="Account not found."), 404)
    if g.me["role"] != "admin" and row["role"] != "user":
        return None, (jsonify(error="Only an admin can manage staff accounts."), 403)
    return row, None


# ───────────────────── events / scheduler ─────────────────────
def refresh_events(con, now, user_id=None):
    """Same rules as the original app: create today's events, mark overdue ones missed."""
    today = now.date().isoformat()
    q = """SELECT s.id AS sid, s.time_local, s.user_id, m.id AS mid
           FROM schedules s JOIN medications m ON m.id=s.medication_id JOIN users u ON u.id=s.user_id
           WHERE s.active=1 AND m.active=1 AND u.active=1 AND u.role='user'"""
    args = []
    if user_id:
        q += " AND s.user_id=?"
        args.append(user_id)
    for r in con.execute(q, args).fetchall():
        con.execute(
            "INSERT OR IGNORE INTO dose_events(user_id,medication_id,schedule_id,scheduled_for,status,created_at) "
            "VALUES(?,?,?,?, 'pending', ?)",
            (r["user_id"], r["mid"], r["sid"], f"{today}T{r['time_local']}", iso(now)),
        )
    q2 = """SELECT e.id,e.scheduled_for,s.grace_minutes FROM dose_events e JOIN schedules s ON s.id=e.schedule_id
            WHERE e.status='pending' AND e.scheduled_for<=?"""
    a2 = [iso(now)]
    if user_id:
        q2 += " AND e.user_id=?"
        a2.append(user_id)
    for e in con.execute(q2, a2).fetchall():
        if now > datetime.fromisoformat(e["scheduled_for"]) + timedelta(minutes=int(e["grace_minutes"])):
            con.execute("UPDATE dose_events SET status='missed' WHERE id=? AND status='pending'", (e["id"],))
    con.commit()


def start_scheduler(app):
    """Marks missed doses every minute even when nobody has the dashboard open."""
    if os.environ.get("ENABLE_SCHEDULER", "1") != "1" or app.config.get("TESTING"):
        return

    def loop():
        while True:
            try:
                con = open_db(app.config["DATABASE"])
                refresh_events(con, now_local(app))
                con.close()
            except Exception:  # keep the thread alive no matter what
                app.logger.exception("SilverCare scheduler error")
            _time.sleep(60)

    threading.Thread(target=loop, daemon=True, name="silvercare-scheduler").start()


# ───────────────────────── stock ─────────────────────────
def stock_info(con, med_row):
    """Estimated remaining supply, derived from stored count minus later confirmations."""
    st = con.execute("SELECT * FROM med_stock WHERE medication_id=?", (med_row["id"],)).fetchone()
    if not st:
        return None
    used = con.execute(
        "SELECT COUNT(*) FROM dose_events WHERE medication_id=? AND status='taken' AND confirmed_at>=?",
        (med_row["id"], st["as_of"]),
    ).fetchone()[0]
    per_day = max(1, con.execute(
        "SELECT COUNT(*) FROM schedules WHERE medication_id=? AND active=1", (med_row["id"],)).fetchone()[0])
    ppd = max(1, st["pills_per_dose"])
    remaining = max(0, st["quantity"] - used * ppd)
    doses_left = remaining // ppd
    days_left = round(doses_left / per_day, 1)
    return {
        "quantity_set": st["quantity"], "pills_per_dose": ppd, "low_days": st["low_days"],
        "as_of": st["as_of"], "remaining": remaining, "doses_left": doses_left,
        "days_left": days_left, "low": days_left <= st["low_days"],
    }


def low_stock_list(con, user_id=None):
    q = """SELECT m.id,m.name,m.user_id,u.name AS patient FROM medications m
           JOIN users u ON u.id=m.user_id WHERE m.active=1 AND u.active=1 AND u.role='user'"""
    args = []
    if user_id:
        q += " AND m.user_id=?"
        args.append(user_id)
    out = []
    for m in con.execute(q, args).fetchall():
        info = stock_info(con, m)
        if info and info["low"]:
            out.append({"medication_id": m["id"], "medication": m["name"], "user_id": m["user_id"],
                        "patient": m["patient"], "days_left": info["days_left"], "remaining": info["remaining"]})
    return out


# ───────────────────── overview / alerts ─────────────────────
@bp.get("/api/plus/badge")
@staff
def badge():
    con, now = db(), now_local()
    refresh_events(con, now)
    unacked = con.execute(
        """SELECT COUNT(*) FROM dose_events e LEFT JOIN alert_ack a ON a.event_id=e.id
           WHERE e.status='missed' AND a.event_id IS NULL AND substr(e.scheduled_for,1,10)>=?""",
        ((now.date() - timedelta(days=7)).isoformat(),)).fetchone()[0]
    overdue = con.execute("SELECT COUNT(*) FROM dose_events WHERE status='pending' AND scheduled_for<=?", (iso(now),)).fetchone()[0]
    return jsonify(unacked_missed=unacked, overdue_now=overdue, low_stock=len(low_stock_list(con)))


@bp.get("/api/plus/overview")
@staff
def overview():
    con, now = db(), now_local()
    refresh_events(con, now)
    today = now.date().isoformat()
    week = (now.date() - timedelta(days=6)).isoformat()
    out = []
    for p in con.execute("SELECT id,name,email,active FROM users WHERE role='user' ORDER BY name").fetchall():
        c = {r["status"]: r["n"] for r in con.execute(
            "SELECT status,COUNT(*) n FROM dose_events WHERE user_id=? AND substr(scheduled_for,1,10)=? GROUP BY status",
            (p["id"], today))}
        w = con.execute(
            "SELECT SUM(status='taken') t, SUM(status IN ('taken','missed')) d FROM dose_events "
            "WHERE user_id=? AND substr(scheduled_for,1,10)>=?", (p["id"], week)).fetchone()
        rate = round((w["t"] or 0) / w["d"] * 100) if w["d"] else None
        unacked = con.execute(
            """SELECT COUNT(*) FROM dose_events e LEFT JOIN alert_ack a ON a.event_id=e.id
               WHERE e.user_id=? AND e.status='missed' AND a.event_id IS NULL AND substr(e.scheduled_for,1,10)>=?""",
            (p["id"], week)).fetchone()[0]
        overdue = con.execute("SELECT COUNT(*) FROM dose_events WHERE user_id=? AND status='pending' AND scheduled_for<=?",
                              (p["id"], iso(now))).fetchone()[0]
        d = con.execute("SELECT last_seen FROM device_status WHERE user_id=?", (p["id"],)).fetchone()
        seen_ago = int((now - datetime.fromisoformat(d["last_seen"])).total_seconds()) if d else None
        out.append({
            "id": p["id"], "name": p["name"], "email": p["email"], "active": bool(p["active"]),
            "today": {"taken": c.get("taken", 0), "pending": c.get("pending", 0), "missed": c.get("missed", 0)},
            "rate": rate, "overdue_now": overdue, "unacked_missed": unacked,
            "device_seen_seconds_ago": seen_ago,
            "device_online": seen_ago is not None and seen_ago <= DEVICE_ONLINE_SECONDS,
            "low_stock": len(low_stock_list(con, p["id"])),
        })
    return jsonify(patients=out, time=iso(now))


@bp.get("/api/plus/alerts")
@staff
def alerts():
    con, now = db(), now_local()
    refresh_events(con, now)
    days = clamp_int(request.args.get("days"), 1, 60, 7)
    since = (now.date() - timedelta(days=days - 1)).isoformat()
    missed = con.execute(
        """SELECT e.id,e.user_id,u.name AS patient,m.name AS medication,m.dosage,e.scheduled_for,
                  a.acked_at,a.acked_by_name,a.note
           FROM dose_events e JOIN users u ON u.id=e.user_id JOIN medications m ON m.id=e.medication_id
           LEFT JOIN alert_ack a ON a.event_id=e.id
           WHERE e.status='missed' AND substr(e.scheduled_for,1,10)>=?
           ORDER BY (a.event_id IS NOT NULL), e.scheduled_for DESC LIMIT 300""", (since,)).fetchall()
    overdue = con.execute(
        """SELECT e.id,e.user_id,u.name AS patient,m.name AS medication,e.scheduled_for,s.grace_minutes
           FROM dose_events e JOIN users u ON u.id=e.user_id JOIN medications m ON m.id=e.medication_id
           JOIN schedules s ON s.id=e.schedule_id
           WHERE e.status='pending' AND e.scheduled_for<=? ORDER BY e.scheduled_for""", (iso(now),)).fetchall()
    od = []
    for r in overdue:
        row = dict(r)
        row["minutes_overdue"] = int((now - datetime.fromisoformat(r["scheduled_for"])).total_seconds() // 60)
        od.append(row)
    return jsonify(missed=[dict(r) for r in missed], overdue=od, low_stock=low_stock_list(con))


@bp.post("/api/plus/alerts/<int:event_id>/ack")
@staff
def ack_alert(event_id):
    con = db()
    ev = con.execute("SELECT id,status FROM dose_events WHERE id=?", (event_id,)).fetchone()
    if not ev or ev["status"] != "missed":
        return jsonify(error="Missed event not found."), 404
    note = str((request.get_json(silent=True) or {}).get("note", "")).strip()[:300]
    con.execute("INSERT OR REPLACE INTO alert_ack(event_id,acked_by,acked_by_name,note,acked_at) VALUES(?,?,?,?,?)",
                (event_id, g.me["id"], g.me["name"], note, iso(now_local())))
    con.commit()
    audit("alert.acknowledge", f"event:{event_id}", note)
    return jsonify(ok=True)


# ───────────────────────── accounts ─────────────────────────
@bp.get("/api/plus/users")
@staff
def list_users():
    q = "SELECT u.id,u.name,u.email,u.role,u.active,u.created_at,d.last_seen FROM users u LEFT JOIN device_status d ON d.user_id=u.id"
    if g.me["role"] != "admin":
        q += " WHERE u.role='user'"
    q += " ORDER BY u.role, u.name"
    return jsonify([dict(r) for r in db().execute(q).fetchall()])


@bp.post("/api/plus/users")
@admin_only
def create_account():
    data = request.get_json(silent=True) or {}
    name, email = str(data.get("name", "")).strip(), str(data.get("email", "")).strip().lower()
    password, role = str(data.get("password", "")), str(data.get("role", "caregiver"))
    if role not in ("user", "caregiver", "admin"):
        return jsonify(error="Role must be user, caregiver or admin."), 400
    if not name or "@" not in email or len(password) < 8:
        return jsonify(error="Name, valid email and a password of 8+ characters are required."), 400
    token = secrets.token_urlsafe(32)
    try:
        cur = db().execute(
            "INSERT INTO users(name,email,password_hash,role,device_token,created_at) VALUES(?,?,?,?,?,?)",
            (name, email, generate_password_hash(password), role, token, iso(now_local())))
        db().commit()
    except sqlite3.IntegrityError:
        return jsonify(error="That email address is already registered."), 409
    audit("user.create", f"user:{cur.lastrowid}", f"{role} {email}")
    return jsonify(id=cur.lastrowid, name=name, email=email, role=role, device_token=token), 201


@bp.delete("/api/plus/users/<int:uid>")
@admin_only
def delete_user(uid):
    row, err = target_user(uid)
    if err:
        return err
    if uid == g.me["id"]:
        return jsonify(error="You cannot delete your own account while signed in."), 400
    if row["role"] == "admin" and row["active"] and other_active_admins(db(), uid) == 0:
        return jsonify(error="You cannot delete the last active admin."), 400
    confirm = str((request.get_json(silent=True) or {}).get("confirm_email", "")).strip().lower()
    if confirm != row["email"].lower():
        return jsonify(error="Type the account's exact email address to confirm deletion."), 400
    db().execute("DELETE FROM users WHERE id=?", (uid,))  # cascades: medications, schedules, events, stock, profile
    db().commit()
    audit("user.delete", f"user:{uid}", f"{row['role']} {row['email']} and all linked records")
    return jsonify(ok=True)


@bp.post("/api/plus/users/<int:uid>/active")
@staff
def set_active(uid):
    row, err = target_user(uid)
    if err:
        return err
    active = 1 if (request.get_json(silent=True) or {}).get("active") else 0
    if uid == g.me["id"] and not active:
        return jsonify(error="You cannot disable your own account."), 400
    if row["role"] == "admin" and not active and other_active_admins(db(), uid) == 0:
        return jsonify(error="You cannot disable the last active admin."), 400
    db().execute("UPDATE users SET active=? WHERE id=?", (active, uid))
    db().commit()
    audit("user.enable" if active else "user.disable", f"user:{uid}", row["email"])
    return jsonify(ok=True, active=bool(active))


@bp.post("/api/plus/users/<int:uid>/reset-password")
@staff
def reset_password(uid):
    row, err = target_user(uid)
    if err:
        return err
    pw = str((request.get_json(silent=True) or {}).get("password", "")).strip()
    if pw and len(pw) < 8:
        return jsonify(error="Password must be at least 8 characters."), 400
    pw = pw or secrets.token_urlsafe(9)
    db().execute("UPDATE users SET password_hash=? WHERE id=?", (generate_password_hash(pw), uid))
    db().commit()
    audit("user.reset_password", f"user:{uid}", row["email"])
    return jsonify(ok=True, temporary_password=pw)


@bp.post("/api/plus/users/<int:uid>/rotate-token")
@staff
def rotate_token(uid):
    row, err = target_user(uid)
    if err:
        return err
    token = secrets.token_urlsafe(32)
    db().execute("UPDATE users SET device_token=? WHERE id=?", (token, uid))
    db().commit()
    audit("device.rotate_token", f"user:{uid}", row["email"])
    return jsonify(ok=True, device_token=token)


@bp.route("/api/plus/users/<int:uid>/profile", methods=["GET", "PUT"])
@staff
def profile(uid):
    row, err = target_user(uid)
    if err:
        return err
    con = db()
    if request.method == "PUT":
        d = request.get_json(silent=True) or {}
        con.execute(
            """INSERT INTO patient_profiles(user_id,emergency_name,emergency_phone,care_notes,updated_at) VALUES(?,?,?,?,?)
               ON CONFLICT(user_id) DO UPDATE SET emergency_name=excluded.emergency_name,
               emergency_phone=excluded.emergency_phone, care_notes=excluded.care_notes, updated_at=excluded.updated_at""",
            (uid, str(d.get("emergency_name", ""))[:100], str(d.get("emergency_phone", ""))[:40],
             str(d.get("care_notes", ""))[:1000], iso(now_local())))
        con.commit()
        audit("profile.update", f"user:{uid}")
    p = con.execute("SELECT emergency_name,emergency_phone,care_notes,updated_at FROM patient_profiles WHERE user_id=?", (uid,)).fetchone()
    return jsonify(dict(p) if p else {"emergency_name": "", "emergency_phone": "", "care_notes": "", "updated_at": None})


# ───────────────────── medications & schedules ─────────────────────
def med_or_404(med_id):
    m = db().execute("SELECT m.*,u.role AS owner_role FROM medications m JOIN users u ON u.id=m.user_id WHERE m.id=?", (med_id,)).fetchone()
    return (m, None) if m else (None, (jsonify(error="Medication not found."), 404))


@bp.get("/api/plus/patients/<int:uid>/medications")
@staff
def patient_meds(uid):
    row, err = target_user(uid)
    if err:
        return err
    con = db()
    out = []
    for m in con.execute("SELECT * FROM medications WHERE user_id=? ORDER BY active DESC, created_at DESC", (uid,)).fetchall():
        scheds = [dict(s) for s in con.execute(
            "SELECT id,time_local,grace_minutes,active FROM schedules WHERE medication_id=? ORDER BY active DESC,time_local", (m["id"],))]
        out.append({"id": m["id"], "name": m["name"], "dosage": m["dosage"], "instructions": m["instructions"],
                    "active": bool(m["active"]), "schedules": scheds, "stock": stock_info(con, m)})
    return jsonify(out)


@bp.post("/api/plus/patients/<int:uid>/medications")
@staff
def add_med_multi(uid):
    row, err = target_user(uid)
    if err:
        return err
    if row["role"] != "user" or not row["active"]:
        return jsonify(error="Choose an active patient account."), 400
    d = request.get_json(silent=True) or {}
    name = str(d.get("name", "")).strip()
    if not name:
        return jsonify(error="Medication name is required."), 400
    try:
        times = sorted({clean_time(t) for t in (d.get("times") or [])})
    except ValueError:
        return jsonify(error="Use valid 24-hour times (HH:MM)."), 400
    if not 1 <= len(times) <= 12:
        return jsonify(error="Add between 1 and 12 reminder times."), 400
    grace = clamp_int(d.get("grace_minutes"), 5, 240, 60)
    con, ts = db(), iso(now_local())
    cur = con.execute("INSERT INTO medications(user_id,name,dosage,instructions,created_at) VALUES(?,?,?,?,?)",
                      (uid, name, str(d.get("dosage", "")).strip(), str(d.get("instructions", "")).strip(), ts))
    for t in times:
        con.execute("INSERT INTO schedules(medication_id,user_id,time_local,grace_minutes,created_at) VALUES(?,?,?,?,?)",
                    (cur.lastrowid, uid, t, grace, ts))
    con.commit()
    audit("medication.create", f"med:{cur.lastrowid}", f"{name} at {', '.join(times)} for user {uid}")
    return jsonify(id=cur.lastrowid, times=times), 201


@bp.route("/api/plus/medications/<int:med_id>", methods=["PATCH", "DELETE"])
@staff
def med_item(med_id):
    m, err = med_or_404(med_id)
    if err:
        return err
    con = db()
    if request.method == "PATCH":
        d = request.get_json(silent=True) or {}
        name = str(d.get("name", m["name"])).strip() or m["name"]
        con.execute("UPDATE medications SET name=?,dosage=?,instructions=? WHERE id=?",
                    (name, str(d.get("dosage", m["dosage"])).strip(), str(d.get("instructions", m["instructions"])).strip(), med_id))
        con.commit()
        audit("medication.edit", f"med:{med_id}", name)
        return jsonify(ok=True)
    if g.me["role"] != "admin":
        return jsonify(error="Only an admin can permanently delete a medication and its history."), 403
    confirm = str((request.get_json(silent=True) or {}).get("confirm_name", "")).strip().lower()
    if confirm != m["name"].lower():
        return jsonify(error="Type the medication name exactly to confirm."), 400
    con.execute("DELETE FROM medications WHERE id=?", (med_id,))
    con.commit()
    audit("medication.delete", f"med:{med_id}", f"{m['name']} (history removed)")
    return jsonify(ok=True)


@bp.post("/api/plus/medications/<int:med_id>/active")
@staff
def med_active(med_id):
    m, err = med_or_404(med_id)
    if err:
        return err
    active = 1 if (request.get_json(silent=True) or {}).get("active") else 0
    con = db()
    con.execute("UPDATE medications SET active=? WHERE id=?", (active, med_id))
    if active:  # resuming a medication re-enables its schedules
        con.execute("UPDATE schedules SET active=1 WHERE medication_id=?", (med_id,))
    else:       # pausing removes today's not-yet-decided events so they don't turn into false "missed"
        con.execute("UPDATE schedules SET active=0 WHERE medication_id=?", (med_id,))
        con.execute("DELETE FROM dose_events WHERE medication_id=? AND status='pending'", (med_id,))
    con.commit()
    audit("medication.resume" if active else "medication.pause", f"med:{med_id}", m["name"])
    return jsonify(ok=True, active=bool(active))


@bp.post("/api/plus/medications/<int:med_id>/schedules")
@staff
def add_schedule(med_id):
    m, err = med_or_404(med_id)
    if err:
        return err
    d = request.get_json(silent=True) or {}
    try:
        t = clean_time(d.get("time", ""))
    except ValueError:
        return jsonify(error="Use a valid 24-hour time (HH:MM)."), 400
    con = db()
    if con.execute("SELECT 1 FROM schedules WHERE medication_id=? AND time_local=? AND active=1", (med_id, t)).fetchone():
        return jsonify(error="That reminder time already exists for this medication."), 409
    cur = con.execute("INSERT INTO schedules(medication_id,user_id,time_local,grace_minutes,created_at) VALUES(?,?,?,?,?)",
                      (med_id, m["user_id"], t, clamp_int(d.get("grace_minutes"), 5, 240, 60), iso(now_local())))
    con.commit()
    audit("schedule.add", f"med:{med_id}", t)
    return jsonify(id=cur.lastrowid), 201


@bp.route("/api/plus/schedules/<int:sid>", methods=["PATCH"])
@staff
def edit_schedule(sid):
    con = db()
    s = con.execute("SELECT * FROM schedules WHERE id=?", (sid,)).fetchone()
    if not s:
        return jsonify(error="Schedule not found."), 404
    d = request.get_json(silent=True) or {}
    try:
        t = clean_time(d["time"]) if "time" in d else s["time_local"]
    except ValueError:
        return jsonify(error="Use a valid 24-hour time (HH:MM)."), 400
    grace = clamp_int(d.get("grace_minutes"), 5, 240, s["grace_minutes"]) if "grace_minutes" in d else s["grace_minutes"]
    active = (1 if d.get("active") else 0) if "active" in d else s["active"]
    con.execute("UPDATE schedules SET time_local=?,grace_minutes=?,active=? WHERE id=?", (t, grace, active, sid))
    if t != s["time_local"] or not active:  # drop undecided events at the old time
        con.execute("DELETE FROM dose_events WHERE schedule_id=? AND status='pending'", (sid,))
    con.commit()
    audit("schedule.edit", f"schedule:{sid}", f"time={t} grace={grace} active={active}")
    return jsonify(ok=True)


@bp.put("/api/plus/medications/<int:med_id>/stock")
@staff
def set_stock(med_id):
    m, err = med_or_404(med_id)
    if err:
        return err
    d = request.get_json(silent=True) or {}
    qty = clamp_int(d.get("quantity"), 0, 100000, None)
    if qty is None:
        return jsonify(error="Enter the number of pills/units currently on hand."), 400
    con = db()
    con.execute(
        """INSERT INTO med_stock(medication_id,quantity,pills_per_dose,low_days,as_of) VALUES(?,?,?,?,?)
           ON CONFLICT(medication_id) DO UPDATE SET quantity=excluded.quantity,pills_per_dose=excluded.pills_per_dose,
           low_days=excluded.low_days,as_of=excluded.as_of""",
        (med_id, qty, clamp_int(d.get("pills_per_dose"), 1, 20, 1), clamp_int(d.get("low_days"), 1, 60, 5), iso(now_local())))
    con.commit()
    audit("stock.set", f"med:{med_id}", f"quantity={qty}")
    return jsonify(ok=True, stock=stock_info(con, m))


# ───────────────────────── export / audit ─────────────────────────
def _csv_safe(v):
    s = "" if v is None else str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s  # blocks spreadsheet formula injection


@bp.get("/api/plus/export/events.csv")
@staff
def export_events():
    con, now = db(), now_local()
    days = clamp_int(request.args.get("days"), 1, 365, 30)
    since = (now.date() - timedelta(days=days - 1)).isoformat()
    q = """SELECT u.name AS patient,m.name AS medication,m.dosage,e.scheduled_for,e.status,e.confirmed_at,
                  e.confirmation_source,CASE WHEN a.event_id IS NULL THEN '' ELSE 'yes' END AS alert_acknowledged
           FROM dose_events e JOIN users u ON u.id=e.user_id JOIN medications m ON m.id=e.medication_id
           LEFT JOIN alert_ack a ON a.event_id=e.id WHERE substr(e.scheduled_for,1,10)>=?"""
    args = [since]
    if request.args.get("user_id"):
        q += " AND e.user_id=?"
        args.append(clamp_int(request.args.get("user_id"), 0, 10**9, 0))
    q += " ORDER BY e.scheduled_for DESC"
    buf = io.StringIO()
    w = csv.writer(buf)
    cols = ["patient", "medication", "dosage", "scheduled_for", "status", "confirmed_at", "confirmation_source", "alert_acknowledged"]
    w.writerow(cols)
    for r in con.execute(q, args):
        w.writerow([_csv_safe(r[c]) for c in cols])
    audit("export.events", f"days:{days}", request.args.get("user_id", "all patients"))
    return Response("\ufeff" + buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename=silvercare_events_{now.date()}.csv"})


@bp.get("/api/plus/audit")
@admin_only
def audit_list():
    rows = db().execute("SELECT id,actor_name,action,target,detail,created_at FROM audit_log ORDER BY id DESC LIMIT 200").fetchall()
    return jsonify([dict(r) for r in rows])


# ───────────────────── patient-side status ─────────────────────
@bp.get("/api/plus/me/status")
@any_role
def my_status():
    con, now = db(), now_local()
    uid = g.me["id"]
    refresh_events(con, now, uid)
    base = """SELECT e.id,e.scheduled_for,m.name AS medication,m.dosage,s.grace_minutes FROM dose_events e
              JOIN medications m ON m.id=e.medication_id JOIN schedules s ON s.id=e.schedule_id
              WHERE e.user_id=? AND e.status='pending' AND """
    due = []
    for r in con.execute(base + "e.scheduled_for<=? ORDER BY e.scheduled_for", (uid, iso(now))).fetchall():
        row = dict(r)
        end = datetime.fromisoformat(r["scheduled_for"]) + timedelta(minutes=int(r["grace_minutes"]))
        row["minutes_left"] = max(0, int((end - now).total_seconds() // 60))
        due.append(row)
    nxt = con.execute(base + "e.scheduled_for>? ORDER BY e.scheduled_for LIMIT 1", (uid, iso(now))).fetchone()
    return jsonify(due=due, next=dict(nxt) if nxt else None, low_stock=low_stock_list(con, uid), time=iso(now))


# ───────────────────────── page ─────────────────────────
@bp.get("/care-tools")
def care_tools_page():
    u = current_me()
    if not u:
        return redirect(url_for("login"))
    if u["role"] not in ("admin", "caregiver"):
        return redirect("/")
    return render_template("care_tools.html", user=u)


# ───────────────────────── init + hooks ─────────────────────────
def init_extensions(app):
    if app.extensions.get("silvercare_plus"):
        return app
    app.extensions["silvercare_plus"] = True

    con = open_db(app.config["DATABASE"])
    con.executescript(SCHEMA)
    con.commit()
    con.close()

    app.register_blueprint(bp)

    @app.teardown_appcontext
    def _close_plus_db(_e=None):
        c = g.pop("plus_db", None)
        if c is not None:
            c.close()

    # 1) Brute-force protection on the existing /login route
    def login_key():
        return f"{(request.form.get('email') or '').strip().lower()}|{request.remote_addr}"

    @app.before_request
    def _login_throttle():
        if request.endpoint == "login" and request.method == "POST":
            row = db().execute("SELECT locked_until FROM login_attempts WHERE key=?", (login_key(),)).fetchone()
            if row and row["locked_until"] and row["locked_until"] > iso(now_local()):
                flash(f"Too many failed attempts. Try again in {LOGIN_LOCK_MINUTES} minutes.", "error")
                return render_template("login.html"), 429

    @app.after_request
    def _login_track(resp):
        if request.endpoint == "login" and request.method == "POST" and resp.status_code != 429:
            con2, now, key = db(), now_local(), login_key()
            if resp.status_code in (301, 302, 303):
                con2.execute("DELETE FROM login_attempts WHERE key=?", (key,))
            else:
                row = con2.execute("SELECT fails,first_at FROM login_attempts WHERE key=?", (key,)).fetchone()
                if row and datetime.fromisoformat(row["first_at"]) > now - timedelta(minutes=LOGIN_LOCK_MINUTES):
                    fails, first = row["fails"] + 1, row["first_at"]
                else:
                    fails, first = 1, iso(now)
                locked = iso(now + timedelta(minutes=LOGIN_LOCK_MINUTES)) if fails >= MAX_LOGIN_FAILS else None
                con2.execute("INSERT OR REPLACE INTO login_attempts(key,fails,first_at,locked_until) VALUES(?,?,?,?)",
                             (key, fails, first, locked))
            con2.commit()
        return resp

    # 2) Remember when each ESP32 last contacted the server (online/offline status)
    @app.after_request
    def _device_seen(resp):
        if request.endpoint in ("device_next", "device_confirm") and resp.status_code == 200:
            token = request.headers.get("X-Device-Token", "")
            row = db().execute("SELECT id FROM users WHERE device_token=?", (token,)).fetchone()
            if row:
                db().execute(
                    "INSERT INTO device_status(user_id,last_seen,last_ip) VALUES(?,?,?) "
                    "ON CONFLICT(user_id) DO UPDATE SET last_seen=excluded.last_seen,last_ip=excluded.last_ip",
                    (row["id"], iso(now_local(app)), request.remote_addr))
                db().commit()
        return resp

    # 3) Add the new buttons/alarm script to existing pages (no template edits needed)
    @app.after_request
    def _inject_assets(resp):
        if (resp.status_code == 200 and resp.mimetype == "text/html" and not resp.direct_passthrough
                and request.endpoint not in (None, "static")):
            body = resp.get_data()
            if b"</body>" in body and b"care_tools.css" not in body:
                tag = (b'<link rel="stylesheet" href="/static/care_tools.css">'
                       b'<script defer src="/static/enhance.js"></script></body>')
                resp.set_data(body.replace(b"</body>", tag, 1))
        return resp

    start_scheduler(app)
    return app
