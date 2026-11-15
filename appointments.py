"""Doctor visits: staff schedule them, patients see them (so visits aren't forgotten)."""
from datetime import datetime, timedelta

from flask import g, jsonify, request

from .core import bp, db, staff, patient_only, iso, now_local, audit, text_arg, clamp_int, target_user


@bp.get("/api/clinic/appointments")
@staff
def list_appts():
    uid = clamp_int(request.args.get("user_id"), 0, 10**9, 0)
    if not uid:
        return jsonify(error="user_id is required."), 400
    rows = db().execute("SELECT * FROM appointments WHERE user_id=? ORDER BY starts_at DESC LIMIT 40", (uid,)).fetchall()
    return jsonify([dict(r) for r in rows])


@bp.post("/api/clinic/appointments")
@staff
def add_appt():
    d = request.get_json(silent=True) or {}
    uid = clamp_int(d.get("user_id"), 0, 10**9, 0)
    row, err = target_user(uid)
    if err:
        return err
    try:
        when = datetime.fromisoformat(str(d.get("starts_at", "")).strip()).replace(second=0, microsecond=0)
    except ValueError:
        return jsonify(error="Choose a valid date and time."), 400
    title = text_arg(d, "title", 120)
    if not title:
        return jsonify(error="Give the appointment a title."), 400
    cur = db().execute(
        "INSERT INTO appointments(user_id,title,with_name,location,starts_at,notes,created_by,created_at) VALUES(?,?,?,?,?,?,?,?)",
        (uid, title, text_arg(d, "with_name", 100), text_arg(d, "location", 160), when.isoformat(timespec="minutes"),
         text_arg(d, "notes", 400), g.me["name"], iso(now_local())))
    db().commit()
    audit("appointment.create", f"user:{uid}", f"{title} {when}")
    return jsonify(id=cur.lastrowid), 201


@bp.patch("/api/clinic/appointments/<int:aid>")
@staff
def set_appt_status(aid):
    status = (request.get_json(silent=True) or {}).get("status")
    if status not in ("scheduled", "done", "cancelled"):
        return jsonify(error="Invalid status."), 400
    cur = db().execute("UPDATE appointments SET status=? WHERE id=?", (status, aid))
    db().commit()
    return jsonify(ok=True) if cur.rowcount else (jsonify(error="Not found."), 404)


@bp.delete("/api/clinic/appointments/<int:aid>")
@staff
def del_appt(aid):
    db().execute("DELETE FROM appointments WHERE id=?", (aid,))
    db().commit()
    audit("appointment.delete", f"appointment:{aid}")
    return jsonify(ok=True)


@bp.get("/api/clinic/me/appointments")
@patient_only
def my_appts():
    cutoff = iso(now_local() - timedelta(hours=3))
    rows = db().execute("SELECT id,title,with_name,location,starts_at,notes FROM appointments WHERE user_id=? AND status='scheduled' AND starts_at>=? ORDER BY starts_at LIMIT 5",
                        (g.me["id"], cutoff[:16])).fetchall()
    return jsonify([dict(r) for r in rows])
