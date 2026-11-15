"""Secure in-app messages between a patient and the care team (replaces scattered phone calls/texts)."""
from datetime import datetime, timedelta

from flask import g, jsonify, request

from .core import bp, db, staff, patient_only, iso, now_local, audit, text_arg, target_user, emergency_number
from .safety import red_flags, urgent_text


def _thread(uid, limit=100):
    rows = db().execute("SELECT id,sender_role,sender_name,body,created_at FROM messages WHERE patient_id=? ORDER BY id DESC LIMIT ?",
                        (uid, limit)).fetchall()
    return [dict(r) for r in reversed(rows)]


@bp.get("/api/clinic/messages/inbox")
@staff
def inbox():
    rows = db().execute(
        """SELECT u.id,u.name,
             (SELECT body FROM messages m WHERE m.patient_id=u.id ORDER BY m.id DESC LIMIT 1) AS last_body,
             (SELECT created_at FROM messages m WHERE m.patient_id=u.id ORDER BY m.id DESC LIMIT 1) AS last_at,
             (SELECT COUNT(*) FROM messages m WHERE m.patient_id=u.id AND m.sender_role='user' AND m.read_by_staff=0) AS unread
           FROM users u WHERE u.role='user' AND u.active=1 ORDER BY last_at IS NULL, last_at DESC, u.name""").fetchall()
    return jsonify([dict(r) for r in rows])


@bp.get("/api/clinic/messages/<int:uid>")
@staff
def staff_thread(uid):
    row, err = target_user(uid)
    if err:
        return err
    db().execute("UPDATE messages SET read_by_staff=1 WHERE patient_id=? AND sender_role='user'", (uid,))
    db().commit()
    return jsonify(_thread(uid))


@bp.post("/api/clinic/messages/<int:uid>")
@staff
def staff_send(uid):
    row, err = target_user(uid)
    if err:
        return err
    body = text_arg(request.get_json(silent=True) or {}, "body", 1000)
    if not body:
        return jsonify(error="Write a message first."), 400
    db().execute("INSERT INTO messages(patient_id,sender_id,sender_role,sender_name,body,created_at,read_by_staff) VALUES(?,?,?,?,?,?,1)",
                 (uid, g.me["id"], g.me["role"], g.me["name"], body, iso(now_local())))
    db().commit()
    return jsonify(ok=True)


@bp.get("/api/clinic/me/messages")
@patient_only
def my_thread():
    db().execute("UPDATE messages SET read_by_patient=1 WHERE patient_id=? AND sender_role<>'user'", (g.me["id"],))
    db().commit()
    return jsonify(_thread(g.me["id"]))


@bp.post("/api/clinic/me/messages")
@patient_only
def my_send():
    con, now = db(), now_local()
    body = text_arg(request.get_json(silent=True) or {}, "body", 1000)
    if not body:
        return jsonify(error="Write a message first."), 400
    recent = con.execute("SELECT COUNT(*) FROM messages WHERE patient_id=? AND sender_role='user' AND created_at>=?",
                         (g.me["id"], iso(now - timedelta(hours=1)))).fetchone()[0]
    if recent >= 30:
        return jsonify(error="Too many messages in the last hour. Please wait a little."), 429
    con.execute("INSERT INTO messages(patient_id,sender_id,sender_role,sender_name,body,created_at,read_by_patient) VALUES(?,?,?,?,?,?,1)",
                (g.me["id"], g.me["id"], "user", g.me["name"], body, iso(now)))
    flags = red_flags(body)
    if flags:
        con.execute("INSERT INTO help_requests(user_id,kind,note,created_at) VALUES(?,?,?,?)",
                    (g.me["id"], "urgent_message", body[:200], iso(now)))
    con.commit()
    out = {"ok": True}
    if flags:
        out.update(urgent=True, urgent_text=urgent_text(emergency_number()))
    return jsonify(out)
