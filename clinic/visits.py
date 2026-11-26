"""Visit notes with a plain-language summary, patient questions for the doctor, and optional AI drafting.
Fixes: "I forgot what the doctor told me" and "I forgot to ask my question"."""
from flask import g, jsonify, request

from . import ai
from .core import bp, db, staff, patient_only, iso, now_local, audit, text_arg, clamp_int, target_user
from .insights import analyze, plain_brief


# ───────── notes ─────────
@bp.get("/api/clinic/patients/<int:uid>/notes")
@staff
def list_notes(uid):
    row, err = target_user(uid)
    if err:
        return err
    rows = db().execute("SELECT id,author,internal_note,plain_summary,created_at FROM visit_notes WHERE user_id=? ORDER BY id DESC LIMIT 30", (uid,)).fetchall()
    return jsonify([dict(r) for r in rows])


@bp.post("/api/clinic/patients/<int:uid>/notes")
@staff
def add_note(uid):
    row, err = target_user(uid)
    if err:
        return err
    d = request.get_json(silent=True) or {}
    internal, plain = text_arg(d, "internal_note", 3000), text_arg(d, "plain_summary", 1500)
    if not internal and not plain:
        return jsonify(error="Write a note or a plain-language summary."), 400
    cur = db().execute("INSERT INTO visit_notes(user_id,author,internal_note,plain_summary,created_at) VALUES(?,?,?,?,?)",
                       (uid, g.me["name"], internal, plain, iso(now_local())))
    db().commit()
    audit("note.create", f"user:{uid}", "published to patient" if plain else "internal only")
    return jsonify(id=cur.lastrowid), 201


@bp.delete("/api/clinic/notes/<int:nid>")
@staff
def del_note(nid):
    db().execute("DELETE FROM visit_notes WHERE id=?", (nid,))
    db().commit()
    audit("note.delete", f"note:{nid}")
    return jsonify(ok=True)


@bp.get("/api/clinic/me/notes")
@patient_only
def my_notes():
    """Patients only ever see the plain-language summary, never the internal note."""
    rows = db().execute("SELECT id,author,plain_summary,created_at FROM visit_notes WHERE user_id=? AND plain_summary<>'' ORDER BY id DESC LIMIT 10", (g.me["id"],)).fetchall()
    return jsonify([dict(r) for r in rows])


# ───────── questions for the doctor ─────────
@bp.get("/api/clinic/me/questions")
@patient_only
def my_questions():
    rows = db().execute("SELECT id,question,answer,answered_by,answered_at,created_at FROM visit_questions WHERE user_id=? ORDER BY id DESC LIMIT 30", (g.me["id"],)).fetchall()
    return jsonify([dict(r) for r in rows])


@bp.post("/api/clinic/me/questions")
@patient_only
def add_question():
    q = text_arg(request.get_json(silent=True) or {}, "question", 400)
    if not q:
        return jsonify(error="Type your question first."), 400
    db().execute("INSERT INTO visit_questions(user_id,question,created_at) VALUES(?,?,?)", (g.me["id"], q, iso(now_local())))
    db().commit()
    return jsonify(ok=True), 201


@bp.delete("/api/clinic/me/questions/<int:qid>")
@patient_only
def del_my_question(qid):
    db().execute("DELETE FROM visit_questions WHERE id=? AND user_id=? AND answered_at IS NULL", (qid, g.me["id"]))
    db().commit()
    return jsonify(ok=True)


@bp.get("/api/clinic/patients/<int:uid>/questions")
@staff
def staff_questions(uid):
    row, err = target_user(uid)
    if err:
        return err
    rows = db().execute("SELECT id,question,answer,answered_by,answered_at,created_at FROM visit_questions WHERE user_id=? ORDER BY (answered_at IS NOT NULL), id DESC LIMIT 30", (uid,)).fetchall()
    return jsonify([dict(r) for r in rows])


@bp.post("/api/clinic/questions/<int:qid>/answer")
@staff
def answer_question(qid):
    a = text_arg(request.get_json(silent=True) or {}, "answer", 1000)
    if not a:
        return jsonify(error="Write an answer."), 400
    cur = db().execute("UPDATE visit_questions SET answer=?,answered_by=?,answered_at=? WHERE id=?", (a, g.me["name"], iso(now_local()), qid))
    db().commit()
    if not cur.rowcount:
        return jsonify(error="Question not found."), 404
    audit("question.answer", f"question:{qid}")
    return jsonify(ok=True)


# ───────── optional AI drafting (staff-triggered only) ─────────
@bp.get("/api/clinic/ai/status")
@staff
def ai_status():
    return jsonify(available=ai.available())


@bp.post("/api/clinic/ai/plain-language")
@staff
def ai_plain():
    d = request.get_json(silent=True) or {}
    text = text_arg(d, "text", 3000)
    if not text:
        return jsonify(error="Write the clinical note first."), 400
    uid = clamp_int(d.get("user_id"), 0, 10**9, 0)
    names = [r["name"] for r in db().execute("SELECT name FROM users WHERE id=?", (uid,))] + [g.me["name"]]
    out = ai.plain_language(text, names)
    audit("ai.plain_language", f"user:{uid}", "ai" if out["ai"] else "fallback")
    return jsonify(out)


@bp.post("/api/clinic/ai/brief")
@staff
def ai_brief():
    d = request.get_json(silent=True) or {}
    uid = clamp_int(d.get("user_id"), 0, 10**9, 0)
    row, err = target_user(uid)
    if err:
        return err
    a = analyze(db(), uid, now_local(), clamp_int(d.get("days"), 7, 90, 30))
    out = ai.brief(a, plain_brief(a))
    audit("ai.brief", f"user:{uid}", "ai" if out["ai"] else "fallback")
    return jsonify(out)
