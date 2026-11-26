"""Side-effect / symptom diary + the "I need help" button. Fixes: side effects never reach the doctor."""
from datetime import timedelta

from flask import g, jsonify, request

from .core import bp, db, staff, patient_only, iso, now_local, audit, text_arg, clamp_int, emergency_number
from .safety import red_flags, urgent_text


@bp.post("/api/clinic/me/symptoms")
@patient_only
def add_symptom():
    d = request.get_json(silent=True) or {}
    body = text_arg(d, "body", 500)
    if not body:
        return jsonify(error="Please describe how you feel."), 400
    sev = clamp_int(d.get("severity"), 1, 5, 3)
    con, now = db(), now_local()
    med_id = None
    if d.get("medication_id"):
        m = con.execute("SELECT id FROM medications WHERE id=? AND user_id=?", (clamp_int(d.get("medication_id"), 0, 10**9, 0), g.me["id"])).fetchone()
        med_id = m["id"] if m else None
    flags = red_flags(body)
    flagged = 1 if (flags or sev >= 4) else 0
    con.execute("INSERT INTO symptom_logs(user_id,medication_id,severity,body,flagged,created_at) VALUES(?,?,?,?,?,?)",
                (g.me["id"], med_id, sev, body, flagged, iso(now)))
    if flags or sev == 5:
        con.execute("INSERT INTO help_requests(user_id,kind,note,created_at) VALUES(?,?,?,?)",
                    (g.me["id"], "urgent_symptom", body[:200], iso(now)))
    con.commit()
    out = {"ok": True, "flagged": bool(flagged)}
    if flags or sev == 5:
        out.update(urgent=True, urgent_text=urgent_text(emergency_number()))
    return jsonify(out), 201


@bp.get("/api/clinic/me/symptoms")
@patient_only
def my_symptoms():
    rows = db().execute(
        """SELECT s.id,s.severity,s.body,s.created_at,s.staff_note,s.reviewed_at,m.name AS medication FROM symptom_logs s
           LEFT JOIN medications m ON m.id=s.medication_id WHERE s.user_id=? ORDER BY s.id DESC LIMIT 30""", (g.me["id"],)).fetchall()
    return jsonify([dict(r) for r in rows])


@bp.get("/api/clinic/symptoms")
@staff
def staff_symptoms():
    q = """SELECT s.id,s.user_id,u.name AS patient,s.severity,s.body,s.flagged,s.created_at,s.reviewed_by,s.reviewed_at,s.staff_note,m.name AS medication
           FROM symptom_logs s JOIN users u ON u.id=s.user_id LEFT JOIN medications m ON m.id=s.medication_id WHERE 1=1"""
    args = []
    if request.args.get("user_id"):
        q += " AND s.user_id=?"
        args.append(clamp_int(request.args.get("user_id"), 0, 10**9, 0))
    q += " ORDER BY (s.reviewed_at IS NOT NULL), s.flagged DESC, s.id DESC LIMIT 100"
    return jsonify([dict(r) for r in db().execute(q, args).fetchall()])


@bp.post("/api/clinic/symptoms/<int:sid>/review")
@staff
def review_symptom(sid):
    note = text_arg(request.get_json(silent=True) or {}, "note", 500)
    cur = db().execute("UPDATE symptom_logs SET reviewed_by=?,reviewed_at=?,staff_note=? WHERE id=?", (g.me["name"], iso(now_local()), note, sid))
    db().commit()
    if not cur.rowcount:
        return jsonify(error="Report not found."), 404
    audit("symptom.review", f"symptom:{sid}", note)
    return jsonify(ok=True)


# ───────── help requests ─────────
@bp.post("/api/clinic/me/help")
@patient_only
def ask_help():
    d = request.get_json(silent=True) or {}
    kind = "sos" if d.get("kind") == "sos" else "call_me"
    con, now = db(), now_local()
    dup = con.execute("SELECT id FROM help_requests WHERE user_id=? AND kind=? AND status='open' AND created_at>=?",
                      (g.me["id"], kind, iso(now - timedelta(minutes=5)))).fetchone()
    if not dup:
        con.execute("INSERT INTO help_requests(user_id,kind,note,created_at) VALUES(?,?,?,?)", (g.me["id"], kind, text_arg(d, "note", 200), iso(now)))
        con.commit()
    contact = con.execute("SELECT emergency_name,emergency_phone FROM patient_profiles WHERE user_id=?", (g.me["id"],)).fetchone()
    return jsonify(ok=True, emergency_number=emergency_number(), already_sent=bool(dup),
                   text=urgent_text(emergency_number()) if kind == "sos" else "Your care team has been asked to call you.",
                   contact=dict(contact) if contact else None)


@bp.get("/api/clinic/help")
@staff
def list_help():
    rows = db().execute(
        """SELECT h.id,h.user_id,u.name AS patient,h.kind,h.note,h.created_at,h.status,p.emergency_name,p.emergency_phone
           FROM help_requests h JOIN users u ON u.id=h.user_id LEFT JOIN patient_profiles p ON p.user_id=h.user_id
           WHERE h.status='open' ORDER BY h.id DESC""").fetchall()
    return jsonify([dict(r) for r in rows])


@bp.post("/api/clinic/help/<int:hid>/resolve")
@staff
def resolve_help(hid):
    cur = db().execute("UPDATE help_requests SET status='resolved',resolved_by=?,resolved_at=? WHERE id=? AND status='open'", (g.me["name"], iso(now_local()), hid))
    db().commit()
    if not cur.rowcount:
        return jsonify(error="Open request not found."), 404
    audit("help.resolve", f"help:{hid}")
    return jsonify(ok=True)


@bp.get("/api/clinic/badge")
@staff
def clinic_badge():
    con = db()
    n = lambda q: con.execute(q).fetchone()[0]
    out = {
        "open_help": n("SELECT COUNT(*) FROM help_requests WHERE status='open'"),
        "unread_messages": n("SELECT COUNT(*) FROM messages WHERE sender_role='user' AND read_by_staff=0"),
        "flagged_symptoms": n("SELECT COUNT(*) FROM symptom_logs WHERE flagged=1 AND reviewed_at IS NULL"),
        "pending_refills": n("SELECT COUNT(*) FROM refill_requests WHERE status='pending'"),
    }
    out["total"] = sum(out.values())
    return jsonify(out)
