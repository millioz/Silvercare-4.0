"""SilverCare GROWTH — routes. Adds files only: nothing in app.py / extensions.py / clinic/ is edited."""
from __future__ import annotations

import json
from datetime import datetime
import re


from flask import Blueprint, g, jsonify, render_template, request

from clinic import ai as ai_mod
from clinic.core import any_role, audit, db, iso, now_local, page_guard, patient_only, refresh_events, staff, target_user
from clinic.insights import analyze, cohort, plain_brief
from clinic.safety import red_flags, urgent_text
from clinic.core import emergency_number

from . import engine

gbp = Blueprint("growth", __name__)
VERSION = "growth-1.0"

SCHEMA = """
CREATE TABLE IF NOT EXISTS dose_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL REFERENCES dose_events(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL, author TEXT NOT NULL, body TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_dose_notes_user ON dose_notes(user_id, event_id);
CREATE TABLE IF NOT EXISTS device_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL, at TEXT NOT NULL, kind TEXT NOT NULL, event_id INTEGER, detail TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_device_log_user ON device_log(user_id, id);
"""

PATIENT_SYSTEM = (
    "You are a calm helper inside a medication-reminder app for an older adult. Rules: (1) answer ONLY from the FACTS given; "
    "(2) never diagnose; (3) never advise starting, stopping, skipping, repeating or changing any medicine or dose — "
    "for such questions say to follow the prescription label or ask the pharmacist or care team; (4) if it sounds urgent, say to "
    "call the emergency number or ask someone nearby; (5) reply in the SAME LANGUAGE as the question (Burmese, English, etc.), "
    "at most 3 short sentences, very simple words."
)


def _ci(v, lo, hi, default):
    try:
        return max(lo, min(hi, int(v)))
    except (TypeError, ValueError):
        return default


def _sig(con, sql, args=()):
    return ",".join("|".join(str(c) for c in r) for r in con.execute(sql, args).fetchall())


# ═════════════ ESP32 v2: the button confirms ONLY the nearest reminder ═════════════
def _device_user(con):
    tok = request.headers.get("X-Device-Token", "")
    if not tok:
        return None
    return con.execute("SELECT id,name FROM users WHERE device_token=? AND active=1", (tok,)).fetchone()


def _touch(con, uid, now):
    con.execute("INSERT INTO device_status(user_id,last_seen,last_ip) VALUES(?,?,?) "
                "ON CONFLICT(user_id) DO UPDATE SET last_seen=excluded.last_seen,last_ip=excluded.last_ip",
                (uid, iso(now), request.remote_addr))


def _dose_out(d):
    return None if not d else {k: d[k] for k in ("id", "medication_name", "dosage", "scheduled_for", "minutes_from_now")}


@gbp.get("/api/device/v2/next")
def device_next_v2():
    con, now = db(), now_local()
    dev = _device_user(con)
    if not dev:
        return jsonify(error="Valid X-Device-Token required."), 401
    refresh_events(con, now, dev["id"])
    was_online = engine.device_info(con, dev["id"], now)["online"]
    _touch(con, dev["id"], now)
    if not was_online:
        con.execute("INSERT INTO device_log(user_id,at,kind,detail) VALUES(?,?,?,?)", (dev["id"], iso(now), "online", request.remote_addr or ""))
    con.commit()
    near, others, later = engine.nearest_dose(con, dev["id"], now)
    label = ""
    if near:
        label = f"{near['medication_name']} {near['scheduled_for'][11:16]}"
    return jsonify(current=_dose_out(near), next=_dose_out(later), others_pending=len(others), label=label,
                   server_time=iso(now), early_minutes=engine.EARLY_MIN)


@gbp.post("/api/device/v2/confirm")
def device_confirm_v2():
    con, now = db(), now_local()
    dev = _device_user(con)
    if not dev:
        return jsonify(error="Valid X-Device-Token required."), 401
    uid = dev["id"]
    refresh_events(con, now, uid)
    _touch(con, uid, now)

    def done(code, **body):
        con.commit()
        return jsonify(**body), code

    last = con.execute("SELECT at FROM device_log WHERE user_id=? AND kind='confirm' ORDER BY id DESC LIMIT 1", (uid,)).fetchone()
    if last and (now - datetime.fromisoformat(last["at"])).total_seconds() < engine.COOLDOWN_SEC:
        con.execute("INSERT INTO device_log(user_id,at,kind,detail) VALUES(?,?,?,?)", (uid, iso(now), "ignored", "double press"))
        return done(200, ok=False, reason="cooldown")
    near, others, later = engine.nearest_dose(con, uid, now)
    if not near:
        con.execute("INSERT INTO device_log(user_id,at,kind,detail) VALUES(?,?,?,?)", (uid, iso(now), "ignored", "no dose in window"))
        return done(200, ok=False, reason="no_dose_due", next=_dose_out(later))
    want = (request.get_json(silent=True) or {}).get("event_id")
    if want is not None and str(want) != str(near["id"]):
        con.execute("INSERT INTO device_log(user_id,at,kind,event_id,detail) VALUES(?,?,?,?,?)", (uid, iso(now), "ignored", near["id"], f"asked {want}, nearest is {near['id']}"))
        return done(409, ok=False, reason="not_nearest", nearest=near["id"])
    cur = con.execute("UPDATE dose_events SET status='taken',confirmed_at=?,confirmation_source='esp32_button' WHERE id=? AND status='pending'",
                      (iso(now), near["id"]))
    if not cur.rowcount:
        return done(200, ok=False, reason="already_done")
    con.execute("INSERT INTO device_log(user_id,at,kind,event_id,detail) VALUES(?,?,?,?,?)",
                (uid, iso(now), "confirm", near["id"], f"{near['medication_name']} {near['scheduled_for'][11:16]}"))
    n2, others2, later2 = engine.nearest_dose(con, uid, now)
    return done(200, ok=True, event_id=near["id"], medication=near["medication_name"], status="taken",
                still_pending_today=len(others2), next=_dose_out(later2))


# ═════════════ live pulse (1 request / second / page, tiny) ═════════════
@gbp.get("/api/growth/ping")
def ping():
    return jsonify(ok=True, version=VERSION)


@gbp.get("/api/growth/pulse")
@any_role
def pulse():
    con, me, now = db(), g.me, now_local()
    if me["role"] == "user":
        uid = me["id"]
        msg = con.execute("SELECT COALESCE(MAX(id),0) FROM messages WHERE patient_id=?", (uid,)).fetchone()[0]
        ev = _sig(con, "SELECT status,COUNT(*),COALESCE(MAX(confirmed_at),'') FROM dose_events WHERE user_id=? GROUP BY status", (uid,))
        near = engine.nearest_dose(con, uid, now)[0]
        other = "/".join([_sig(con, "SELECT id,status FROM refill_requests WHERE user_id=?", (uid,)),
                          _sig(con, "SELECT id FROM dose_notes WHERE user_id=?", (uid,)),
                          _sig(con, "SELECT id,COALESCE(answered_at,'') FROM visit_questions WHERE user_id=?", (uid,)),
                          str(engine.device_info(con, uid, now)["online"])])
    else:
        uid = 0
        msg = con.execute("SELECT COALESCE(MAX(id),0) FROM messages").fetchone()[0]
        ev = _sig(con, "SELECT status,COUNT(*),COALESCE(MAX(confirmed_at),'') FROM dose_events GROUP BY status")
        other = "/".join([_sig(con, "SELECT COUNT(*),COALESCE(MAX(id),0),COALESCE(SUM(status='open'),0) FROM help_requests"),
                          _sig(con, "SELECT COUNT(*),COALESCE(MAX(id),0) FROM device_log"),
                          _sig(con, "SELECT COUNT(*),COALESCE(MAX(id),0) FROM dose_notes")])
        near = None
    r = jsonify(msg=msg, ev=ev, other=other, nearest=(near or {}).get("id", 0), t=iso(now))
    r.headers["Cache-Control"] = "no-store"
    return r


# ═════════════ patient APIs ═════════════
@gbp.get("/api/growth/me/today")
@patient_only
def me_today():
    con, now = db(), now_local()
    refresh_events(con, now, g.me["id"]); con.commit()
    out = engine.timeline(con, g.me["id"], now)
    out["device"] = engine.device_info(con, g.me["id"], now)
    return jsonify(out)


@gbp.get("/api/growth/me/stats")
@patient_only
def me_stats():
    a = analyze(db(), g.me["id"], now_local(), 14)
    return jsonify({k: a[k] for k in ("rate", "streak_days", "decided", "taken", "missed", "by_time_of_day", "this_week", "prev_week", "trend")})


@gbp.post("/api/growth/me/ask")
@patient_only
def me_ask():
    con, now = db(), now_local()
    text = str((request.get_json(silent=True) or {}).get("text", "")).strip()[:500]
    if not text:
        return jsonify(error="Type a question first."), 400
    flags = red_flags(text)
    if flags:
        con.execute("INSERT INTO help_requests(user_id,kind,note,created_at) VALUES(?,?,?,?)", (g.me["id"], "urgent_message", text[:200], iso(now)))
        con.commit()
        return jsonify(text=urgent_text(emergency_number()), intent="urgent", urgent=True, ai=False, lang=engine.lang_of(text))
    res = engine.assistant(con, g.me, text, now, analyze)
    if res["intent"] == "unknown" and ai_mod.available():
        try:
            facts = engine.facts_for_ai(con, g.me, now, analyze)
            prompt = "FACTS:\n" + json.dumps(facts, ensure_ascii=False) + "\n\nQUESTION:\n" + ai_mod.redact(text, [g.me["name"]])
            res = {"text": ai_mod.ask(PATIENT_SYSTEM, prompt, 300), "intent": "ai", "ai": True, "lang": res["lang"]}
        except Exception as exc:                                    # network/key problem → friendly rule-based fallback
            res["note"] = f"AI unavailable ({type(exc).__name__})"
    res["can_forward"] = res["intent"] in ("unknown", "ai")
    return jsonify(res)


@gbp.post("/api/growth/me/forward")
@patient_only
def me_forward():
    con, now = db(), now_local()
    text = str((request.get_json(silent=True) or {}).get("text", "")).strip()[:900]
    if not text:
        return jsonify(error="Nothing to send."), 400
    con.execute("INSERT INTO messages(patient_id,sender_id,sender_role,sender_name,body,created_at,read_by_patient) VALUES(?,?,?,?,?,?,1)",
                (g.me["id"], g.me["id"], "user", g.me["name"], text, iso(now)))
    con.commit()
    return jsonify(ok=True)


@gbp.post("/api/growth/notes")
@any_role
def add_note():
    con, now = db(), now_local()
    d = request.get_json(silent=True) or {}
    body = str(d.get("body", "")).strip()[:300]
    try:
        eid = int(d.get("event_id"))
    except (TypeError, ValueError):
        return jsonify(error="event_id is required."), 400
    if not body:
        return jsonify(error="Write a short note first."), 400
    ev = con.execute("SELECT id,user_id FROM dose_events WHERE id=?", (eid,)).fetchone()
    if not ev or (g.me["role"] == "user" and ev["user_id"] != g.me["id"]):
        return jsonify(error="Dose not found."), 404
    con.execute("INSERT INTO dose_notes(event_id,user_id,author,body,created_at) VALUES(?,?,?,?,?)",
                (eid, ev["user_id"], g.me["name"], body, iso(now)))
    if red_flags(body):
        con.execute("INSERT INTO help_requests(user_id,kind,note,created_at) VALUES(?,?,?,?)", (ev["user_id"], "urgent_message", body[:200], iso(now)))
    con.commit()
    return jsonify(ok=True)


# ═════════════ staff APIs ═════════════
@gbp.get("/api/growth/command")
@staff
def command():
    con, now = db(), now_local()
    refresh_events(con, now); con.commit()
    out = []
    for c in cohort(con, now):
        tl = engine.timeline(con, c["id"], now)
        dev = engine.device_info(con, c["id"], now)
        near = tl["nearest"]
        reasons = list(c["reasons"])
        if near and near["minutes_from_now"] < -10 and not dev["online"]:
            reasons.append("A dose is waiting and the box is offline")
        level = c["priority"]
        if level in ("low", "unknown") and near and near["minutes_from_now"] < -10 and not dev["online"]:
            level = "medium"
        out.append({"id": c["id"], "name": c["name"], "level": level, "score": c["score"], "reasons": reasons,
                    "rate": c["rate"], "streak_days": c["streak_days"], "taken": tl["taken"], "total": tl["total"], "missed": tl["missed"],
                    "nearest": _dose_out(near), "next": _dose_out(tl["next"]), "device": dev})
    order = {"high": 0, "medium": 1, "low": 2, "unknown": 3}
    out.sort(key=lambda x: (order.get(x["level"], 3), -x["score"], x["name"]))
    summary = {"patients": len(out), "act": sum(x["level"] == "high" for x in out),
               "offline": sum(not x["device"]["online"] for x in out),
               "due_now": sum(bool(x["nearest"] and x["nearest"]["minutes_from_now"] <= 0) for x in out)}
    return jsonify(summary=summary, patients=out, ai=ai_mod.available())


@gbp.get("/api/growth/patients/<int:uid>/detail")
@staff
def detail(uid):
    row, err = target_user(uid)
    if err:
        return err
    con, now = db(), now_local()
    refresh_events(con, now, uid); con.commit()
    a = analyze(con, uid, now, 14)
    return jsonify(name=row["name"], analysis=a, brief=plain_brief(a), today=engine.timeline(con, uid, now),
                   device=engine.device_info(con, uid, now), device_log=engine.device_log(con, uid))


@gbp.post("/api/growth/patients/<int:uid>/ai-brief")
@staff
def ai_brief(uid):
    row, err = target_user(uid)
    if err:
        return err
    a = analyze(db(), uid, now_local(), 14)
    res = ai_mod.brief(a, plain_brief(a))
    audit("growth.ai_brief", f"user:{uid}", "ai" if res["ai"] else "rules")
    return jsonify(res)


@gbp.post("/api/growth/ai/digest")
@staff
def ai_digest():
    """Today's priorities for the whole care team. Names are replaced by P1, P2… before anything leaves the server."""
    con, now = db(), now_local()
    refresh_events(con, now); con.commit()
    board = cohort(con, now)[:6]
    labels = {f"P{i + 1}": c for i, c in enumerate(board)}
    fallback = "\n".join(f"• {c['name']}: {'; '.join(c['reasons']) or 'nothing urgent'}" for c in board) or "No patients yet."
    if not ai_mod.available() or not board:
        return jsonify(text=fallback, ai=False, note="AI is not configured; showing the rule-based priority list.")
    facts = [{"label": k, "level": c["priority"], "reasons": [ai_mod.redact(r) for r in c["reasons"]], "rate_14d": c["rate"]} for k, c in labels.items()]
    prompt = ("Write a 4-line shift hand-over for a care team: who to check first and why, using only these facts. "
              "These are reminder confirmations, not clinical findings. No medical advice.\n\n" + json.dumps(facts))
    try:
        text = ai_mod.ask(ai_mod.SYSTEM, prompt, 350)
        for k, c in labels.items():
            text = re.sub(rf"\b{k}\b", c["name"], text)
        return jsonify(text=text, ai=True, note="AI-drafted — review before relying on it.")
    except Exception as exc:
        return jsonify(text=fallback, ai=False, note=f"AI request failed ({type(exc).__name__}); showing rule-based list.")


# ═════════════ pages ═════════════
@gbp.get("/growth")
@page_guard(("admin", "caregiver"))
def page_staff(u):
    return render_template("growth_staff.html", user=u)


@gbp.get("/growth/me")
@page_guard(("user",))
def page_me(u):
    return render_template("growth_me.html", user=u)
