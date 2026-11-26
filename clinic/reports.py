"""Printable doctor report + expiring, revocable read-only share links.
Fixes: the doctor sees only what the patient remembers at the visit — now they get real data."""
import hashlib
import secrets
from datetime import datetime, timedelta

from flask import Response, g, jsonify, render_template, request

from .clinical import get_profile, safety_scan
from .core import (bp, db, staff, patient_only, any_role, iso, now_local, audit, clamp_int, target_user, page_guard,
                   emergency_number, stock_info)
from .insights import analyze, plain_brief


def build_report(con, uid, now, days):
    u = con.execute("SELECT id,name FROM users WHERE id=?", (uid,)).fetchone()
    prof = get_profile(con, uid)
    contact = con.execute("SELECT emergency_name,emergency_phone,care_notes FROM patient_profiles WHERE user_id=?", (uid,)).fetchone()
    meds = []
    for m in con.execute("SELECT * FROM medications WHERE user_id=? AND active=1 ORDER BY name", (uid,)).fetchall():
        times = [s["time_local"] for s in con.execute("SELECT time_local FROM schedules WHERE medication_id=? AND active=1 ORDER BY time_local", (m["id"],))]
        st = stock_info(con, m)
        meds.append({"name": m["name"], "dosage": m["dosage"], "instructions": m["instructions"], "times": times,
                     "days_left": st["days_left"] if st else None, "low": bool(st and st["low"])})
    a = analyze(con, uid, now, days)
    since = (now.date() - timedelta(days=min(days, 30) - 1)).isoformat()
    missed = [dict(r) for r in con.execute(
        """SELECT e.scheduled_for,m.name FROM dose_events e JOIN medications m ON m.id=e.medication_id
           WHERE e.user_id=? AND e.status='missed' AND substr(e.scheduled_for,1,10)>=? ORDER BY e.scheduled_for DESC LIMIT 40""", (uid, since))]
    symptoms = [dict(r) for r in con.execute(
        """SELECT s.severity,s.body,s.created_at,m.name AS medication FROM symptom_logs s LEFT JOIN medications m ON m.id=s.medication_id
           WHERE s.user_id=? AND substr(s.created_at,1,10)>=? ORDER BY s.id DESC LIMIT 30""", (uid, (now.date() - timedelta(days=days - 1)).isoformat()))]
    questions = [dict(r) for r in con.execute("SELECT question,answer FROM visit_questions WHERE user_id=? ORDER BY (answered_at IS NOT NULL), id DESC LIMIT 15", (uid,))]
    appts = [dict(r) for r in con.execute("SELECT title,with_name,starts_at,location FROM appointments WHERE user_id=? AND status='scheduled' AND starts_at>=? ORDER BY starts_at LIMIT 3", (uid, iso(now)[:16]))]
    safety = [i for i in safety_scan(con, uid) if i["level"] in ("danger", "warn")]
    return {"patient": u["name"], "generated": iso(now).replace("T", " "), "days": days, "profile": prof,
            "contact": dict(contact) if contact else None, "meds": meds, "a": a, "brief": plain_brief(a), "missed": missed,
            "symptoms": symptoms, "questions": questions, "appts": appts, "safety": safety, "emergency": emergency_number()}


def _render(uid, days, shared=None):
    return render_template("report.html", r=build_report(db(), uid, now_local(), days), shared=shared)


@bp.get("/report/<int:uid>")
@page_guard(("admin", "caregiver"))
def staff_report(u, uid):
    row = db().execute("SELECT id FROM users WHERE id=? AND role='user'", (uid,)).fetchone()
    if not row:
        return "Patient not found", 404
    g.me = u
    audit("report.view", f"user:{uid}")
    return _render(uid, clamp_int(request.args.get("days"), 7, 90, 30))


@bp.get("/my-report")
@page_guard(("user",))
def my_report(u):
    return _render(u["id"], clamp_int(request.args.get("days"), 7, 90, 30))


# ───────── share links ─────────
def _hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def _make_link(uid, by, hours, days):
    token = secrets.token_urlsafe(24)
    now = now_local()
    db().execute("INSERT INTO share_links(token_hash,user_id,created_by,created_at,expires_at,days) VALUES(?,?,?,?,?,?)",
                 (_hash(token), uid, by, iso(now), iso(now + timedelta(hours=hours)), days))
    db().commit()
    return {"path": f"/shared-report/{token}", "expires_at": iso(now + timedelta(hours=hours)), "hours": hours}


@bp.post("/api/clinic/patients/<int:uid>/share")
@staff
def staff_share(uid):
    row, err = target_user(uid)
    if err:
        return err
    d = request.get_json(silent=True) or {}
    out = _make_link(uid, g.me["name"], clamp_int(d.get("hours"), 1, 336, 48), clamp_int(d.get("days"), 7, 90, 30))
    audit("share.create", f"user:{uid}", f"{out['hours']}h")
    return jsonify(out), 201


@bp.post("/api/clinic/me/share")
@patient_only
def my_share():
    d = request.get_json(silent=True) or {}
    out = _make_link(g.me["id"], g.me["name"], clamp_int(d.get("hours"), 1, 168, 48), 30)
    audit("share.create", f"user:{g.me['id']}", f"patient {out['hours']}h")
    return jsonify(out), 201


def _list_links(uid):
    now = iso(now_local())
    rows = db().execute("SELECT id,created_by,created_at,expires_at,views,revoked FROM share_links WHERE user_id=? ORDER BY id DESC LIMIT 10", (uid,)).fetchall()
    return [dict(r, active=(not r["revoked"] and r["expires_at"] > now)) for r in rows]


@bp.get("/api/clinic/patients/<int:uid>/shares")
@staff
def staff_shares(uid):
    row, err = target_user(uid)
    return err if err else jsonify(_list_links(uid))


@bp.get("/api/clinic/me/shares")
@patient_only
def my_shares():
    return jsonify(_list_links(g.me["id"]))


@bp.post("/api/clinic/shares/<int:sid>/revoke")
@any_role
def revoke_share(sid):
    row = db().execute("SELECT id,user_id FROM share_links WHERE id=?", (sid,)).fetchone()
    if not row or (g.me["role"] == "user" and row["user_id"] != g.me["id"]):
        return jsonify(error="Link not found."), 404
    db().execute("UPDATE share_links SET revoked=1 WHERE id=?", (sid,))
    db().commit()
    audit("share.revoke", f"share:{sid}")
    return jsonify(ok=True)


@bp.get("/shared-report/<token>")
def shared_report(token):
    """PUBLIC, read-only, expiring page for an outside doctor. Only a hash of the token is stored."""
    con, now = db(), now_local()
    row = con.execute("SELECT id,user_id,expires_at,revoked,days FROM share_links WHERE token_hash=?", (_hash(token),)).fetchone()
    if not row or row["revoked"] or row["expires_at"] <= iso(now):
        resp = Response("This link is invalid, expired or was revoked. Ask the patient or care team for a new one.", status=404, mimetype="text/plain")
    else:
        con.execute("UPDATE share_links SET views=views+1 WHERE id=?", (row["id"],))
        con.commit()
        audit("share.view", f"share:{row['id']}", f"user:{row['user_id']}")
        resp = Response(_render(row["user_id"], row["days"], shared={"expires": row["expires_at"].replace("T", " ")}))
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["X-Robots-Tag"] = "noindex, nofollow"
    resp.headers["Referrer-Policy"] = "no-referrer"
    return resp
