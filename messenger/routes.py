"""SilverCare MESSENGER — 1:1 chat (patient <-> care team) with photos / video / voice / files, read receipts,
typing, presence and WebRTC video + voice calls. Adds files only. Uses the existing `messages` table, so old chats stay."""
from __future__ import annotations

import json
import os
import re
import secrets
import time
from datetime import datetime, timedelta

from flask import Blueprint, current_app, g, jsonify, render_template, request, send_file

from clinic.core import any_role, db, iso, now_local, page_guard
from clinic.safety import red_flags, urgent_text
from clinic.core import emergency_number

mbp = Blueprint("messenger", __name__)
VERSION = "messenger-1.0"
MAX_MB = int(os.environ.get("CHAT_MAX_MB", "25"))
RING_SECONDS = 45          # unanswered call becomes "missed"
STALE_SECONDS = 25         # a side that stops polling for 25 s is treated as hung up

SCHEMA = """
CREATE TABLE IF NOT EXISTS chat_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id INTEGER REFERENCES messages(id) ON DELETE CASCADE,
    patient_id INTEGER NOT NULL, uploader_id INTEGER NOT NULL,
    kind TEXT NOT NULL, mime TEXT NOT NULL, name TEXT NOT NULL, size INTEGER NOT NULL,
    stored TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chat_files_msg ON chat_files(message_id);
CREATE TABLE IF NOT EXISTS calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL, caller_id INTEGER NOT NULL, caller_name TEXT NOT NULL, caller_role TEXT NOT NULL,
    callee_id INTEGER, callee_name TEXT, kind TEXT NOT NULL, state TEXT NOT NULL,
    created_at TEXT NOT NULL, answered_at TEXT, ended_at TEXT, hb_caller TEXT, hb_callee TEXT
);
CREATE INDEX IF NOT EXISTS idx_calls_patient ON calls(patient_id, state);
CREATE TABLE IF NOT EXISTS call_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    call_id INTEGER NOT NULL, from_id INTEGER NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_call_signals ON call_signals(call_id, id);
"""

_typing: dict = {}     # (patient_id, 'p'|'s') -> time   (in memory; fine for one server process)
_seen: dict = {}       # user_id -> time of last request  (presence)
_SAFE_KINDS = ("image/", "video/", "audio/")


def _side(): return "p" if g.me["role"] == "user" else "s"
def _staff(): return g.me["role"] != "user"


def _patient(pid):
    r = db().execute("SELECT id,name FROM users WHERE id=? AND role='user' AND active=1", (pid,)).fetchone()
    if not r or (g.me["role"] == "user" and g.me["id"] != pid):
        return None
    return r


def _mark_present():
    _seen[g.me["id"]] = time.time()


def _online(uid): return time.time() - _seen.get(uid, 0) < 8


# ───────────── threads / messages ─────────────
def _last_read_id(con, pid):
    """Highest id of MY messages that the other side has read."""
    if g.me["role"] == "user":
        q = "SELECT COALESCE(MAX(id),0) FROM messages WHERE patient_id=? AND sender_role='user' AND read_by_staff=1"
    else:
        q = "SELECT COALESCE(MAX(id),0) FROM messages WHERE patient_id=? AND sender_role<>'user' AND read_by_patient=1"
    return con.execute(q, (pid,)).fetchone()[0]


@mbp.get("/api/chat/threads")
@any_role
def threads():
    con, me = db(), g.me
    _mark_present()
    if me["role"] == "user":
        q = "WHERE u.id=?"; args = (me["id"],)
    else:
        q = "WHERE u.role='user' AND u.active=1"; args = ()
    unread_col = "read_by_patient=0 AND m.sender_role<>'user'" if me["role"] == "user" else "read_by_staff=0 AND m.sender_role='user'"
    rows = con.execute(
        f"""SELECT u.id,u.name,
              (SELECT body FROM messages m WHERE m.patient_id=u.id ORDER BY m.id DESC LIMIT 1) AS last_body,
              (SELECT created_at FROM messages m WHERE m.patient_id=u.id ORDER BY m.id DESC LIMIT 1) AS last_at,
              (SELECT sender_role FROM messages m WHERE m.patient_id=u.id ORDER BY m.id DESC LIMIT 1) AS last_role,
              (SELECT COUNT(*) FROM messages m WHERE m.patient_id=u.id AND m.{unread_col}) AS unread
            FROM users u {q} ORDER BY last_at IS NULL, last_at DESC, u.name""", args).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["online"] = False if me["role"] == "user" else _online(r["id"])
        if me["role"] == "user":
            d["name"] = "My care team"
        out.append(d)
    return jsonify(out)


def _attach(con, rows):
    ids = [r["id"] for r in rows]
    files = {}
    if ids:
        for f in con.execute(f"SELECT id,message_id,kind,mime,name,size FROM chat_files WHERE message_id IN ({','.join('?' * len(ids))})", ids):
            files.setdefault(f["message_id"], []).append(dict(f))
    out = []
    for r in rows:
        d = dict(r); d["files"] = files.get(r["id"], []); out.append(d)
    return out


@mbp.get("/api/chat/threads/<int:pid>/messages")
@any_role
def get_messages(pid):
    con = db()
    if not _patient(pid):
        return jsonify(error="Chat not found."), 404
    _mark_present()
    after = request.args.get("after", type=int) or 0
    before = request.args.get("before", type=int) or 0
    cols = "id,sender_id,sender_role,sender_name,body,created_at"
    if after:
        rows = con.execute(f"SELECT {cols} FROM messages WHERE patient_id=? AND id>? ORDER BY id LIMIT 200", (pid, after)).fetchall()
    elif before:
        rows = list(reversed(con.execute(f"SELECT {cols} FROM messages WHERE patient_id=? AND id<? ORDER BY id DESC LIMIT 40", (pid, before)).fetchall()))
    else:
        rows = list(reversed(con.execute(f"SELECT {cols} FROM messages WHERE patient_id=? ORDER BY id DESC LIMIT 40", (pid,)).fetchall()))
    if g.me["role"] == "user":
        con.execute("UPDATE messages SET read_by_patient=1 WHERE patient_id=? AND sender_role<>'user' AND read_by_patient=0", (pid,))
    else:
        con.execute("UPDATE messages SET read_by_staff=1 WHERE patient_id=? AND sender_role='user' AND read_by_staff=0", (pid,))
    con.commit()
    other = "s" if _side() == "p" else "p"
    return jsonify(messages=_attach(con, rows), last_read_id=_last_read_id(con, pid),
                   typing=time.time() - _typing.get((pid, other), 0) < 4, has_more=len(rows) >= 40 and not after)


def _insert(con, pid, body, now):
    me = g.me
    cur = con.execute(
        "INSERT INTO messages(patient_id,sender_id,sender_role,sender_name,body,created_at,read_by_staff,read_by_patient) VALUES(?,?,?,?,?,?,?,?)",
        (pid, me["id"], me["role"], me["name"], body, iso(now), 0 if me["role"] == "user" else 1, 1 if me["role"] == "user" else 0))
    return cur.lastrowid


def _clean_name(n):
    n = re.sub(r"[^\w.\- ()\u1000-\u109F]+", "_", os.path.basename(n or "file"))[:80]
    return n or "file"


@mbp.post("/api/chat/threads/<int:pid>/messages")
@any_role
def send(pid):
    con, now = db(), now_local()
    if not _patient(pid):
        return jsonify(error="Chat not found."), 404
    _mark_present()
    if request.files:
        text = str(request.form.get("body", "")).strip()[:1000]
        files = request.files.getlist("file")
    else:
        text = str((request.get_json(silent=True) or {}).get("body", "")).strip()[:1000]
        files = []
    if not text and not files:
        return jsonify(error="Write a message first."), 400
    if g.me["role"] == "user":
        recent = con.execute("SELECT COUNT(*) FROM messages WHERE patient_id=? AND sender_role='user' AND created_at>=?",
                             (pid, iso(now - timedelta(hours=1)))).fetchone()[0]
        if recent >= 120:
            return jsonify(error="Too many messages in the last hour. Please wait a little."), 429
    ids, urgent = [], None
    if text:
        ids.append(_insert(con, pid, text, now))
        if g.me["role"] == "user" and red_flags(text):
            con.execute("INSERT INTO help_requests(user_id,kind,note,created_at) VALUES(?,?,?,?)", (pid, "urgent_message", text[:200], iso(now)))
            urgent = urgent_text(emergency_number())
    folder = current_app.config["CHAT_UPLOAD_DIR"]
    os.makedirs(folder, exist_ok=True)
    for f in files:
        mime = (f.mimetype or "application/octet-stream").split(";")[0].lower()
        if mime == "image/svg+xml" or not (mime.startswith(_SAFE_KINDS) or mime == "application/pdf"):
            return jsonify(error=f"“{_clean_name(f.filename)}” is not allowed. Send photos, video, audio or PDF."), 415
        stored = secrets.token_hex(16) + (os.path.splitext(f.filename or "")[1].lower()[:6] if re.fullmatch(r"\.[a-z0-9]{1,5}", os.path.splitext(f.filename or "")[1].lower()) else "")
        path = os.path.join(folder, stored)
        f.save(path)
        size = os.path.getsize(path)
        if size > MAX_MB * 1024 * 1024:
            os.remove(path)
            return jsonify(error=f"File is larger than {MAX_MB} MB."), 413
        kind = "image" if mime.startswith("image/") else "video" if mime.startswith("video/") else "audio" if mime.startswith("audio/") else "file"
        label = {"image": "🖼 Photo", "video": "🎬 Video", "audio": "🎤 Voice message", "file": "📎 " + _clean_name(f.filename)}[kind]
        mid = _insert(con, pid, label, now)
        con.execute("INSERT INTO chat_files(message_id,patient_id,uploader_id,kind,mime,name,size,stored,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                    (mid, pid, g.me["id"], kind, mime, _clean_name(f.filename), size, stored, iso(now)))
        ids.append(mid)
    con.commit()
    return jsonify(ok=True, ids=ids, urgent=urgent)


@mbp.post("/api/chat/threads/<int:pid>/typing")
@any_role
def typing(pid):
    if _patient(pid):
        _typing[(pid, _side())] = time.time()
    return jsonify(ok=True)


@mbp.get("/api/chat/files/<int:fid>")
@any_role
def get_file(fid):
    f = db().execute("SELECT * FROM chat_files WHERE id=?", (fid,)).fetchone()
    if not f or not _patient(f["patient_id"]):
        return jsonify(error="Not found."), 404
    path = os.path.join(current_app.config["CHAT_UPLOAD_DIR"], f["stored"])
    if not os.path.exists(path):
        return jsonify(error="File was removed from the server."), 410
    r = send_file(path, mimetype=f["mime"], download_name=f["name"], as_attachment=(f["kind"] == "file" or request.args.get("dl") == "1"),
                  conditional=True, max_age=3600)
    r.headers["X-Content-Type-Options"] = "nosniff"
    r.headers["Content-Security-Policy"] = "sandbox"
    return r


# ───────────── global pulse (1 request/second per open page) ─────────────
def _call_note(con, c, text, now):
    side_read = ("read_by_staff", 1) if c["caller_role"] != "user" else ("read_by_patient", 1)
    con.execute(f"INSERT INTO messages(patient_id,sender_id,sender_role,sender_name,body,created_at,{side_read[0]}) VALUES(?,?,?,?,?,?,1)",
                (c["patient_id"], c["caller_id"], c["caller_role"], c["caller_name"], text, iso(now)))


def _icon(c): return "📹" if c["kind"] == "video" else "📞"


def _dur(c, now):
    try:
        s = int((datetime.fromisoformat(c["ended_at"] or iso(now)) - datetime.fromisoformat(c["answered_at"])).total_seconds())
        return f"{s // 60}:{s % 60:02d}"
    except Exception:
        return "0:00"


def _finish(con, c, state, now):
    cur = con.execute("UPDATE calls SET state=?,ended_at=? WHERE id=? AND state IN ('ringing','active')", (state, iso(now), c["id"]))
    if not cur.rowcount:
        return
    c = dict(c); c["ended_at"] = iso(now)
    if state == "active" or c["answered_at"]:
        _call_note(con, c, f"{_icon(c)} {c['kind'].title()} call · {_dur(c, now)}", now)
    elif state == "declined":
        _call_note(con, c, f"{_icon(c)} Declined {c['kind']} call", now)
    else:
        _call_note(con, c, f"{_icon(c)} Missed {c['kind']} call", now)


def _expire(con, now):
    for c in con.execute("SELECT * FROM calls WHERE state='ringing' AND created_at<?", (iso(now - timedelta(seconds=RING_SECONDS)),)).fetchall():
        _finish(con, c, "missed", now)
    stale = iso(now - timedelta(seconds=STALE_SECONDS))
    for c in con.execute("SELECT * FROM calls WHERE state='active' AND (COALESCE(hb_caller,answered_at)<? OR COALESCE(hb_callee,answered_at)<?)", (stale, stale)).fetchall():
        _finish(con, c, "ended", now)
    con.commit()


@mbp.get("/api/chat/pulse")
@any_role
def pulse():
    con, me, now = db(), g.me, now_local()
    _mark_present()
    _expire(con, now)
    if me["role"] == "user":
        last = con.execute("SELECT COALESCE(MAX(id),0) FROM messages WHERE patient_id=?", (me["id"],)).fetchone()[0]
        unread = con.execute("SELECT COUNT(*) FROM messages WHERE patient_id=? AND sender_role<>'user' AND read_by_patient=0", (me["id"],)).fetchone()[0]
        inc = con.execute("SELECT * FROM calls WHERE patient_id=? AND state='ringing' AND caller_role<>'user' ORDER BY id DESC LIMIT 1", (me["id"],)).fetchone()
    else:
        last = con.execute("SELECT COALESCE(MAX(id),0) FROM messages").fetchone()[0]
        unread = con.execute("SELECT COUNT(*) FROM messages WHERE sender_role='user' AND read_by_staff=0").fetchone()[0]
        inc = con.execute("SELECT * FROM calls WHERE state='ringing' AND caller_role='user' ORDER BY id DESC LIMIT 1").fetchone()
    out = {"last": last, "unread": unread, "incoming": None, "now": iso(now)}
    if inc:
        out["incoming"] = {"id": inc["id"], "kind": inc["kind"], "from": inc["caller_name"], "patient_id": inc["patient_id"]}
    t = request.args.get("t", type=int)
    if t and _patient(t):
        other = "s" if _side() == "p" else "p"
        out["typing"] = time.time() - _typing.get((t, other), 0) < 4
        out["seen"] = _last_read_id(con, t)
    r = jsonify(out)
    r.headers["Cache-Control"] = "no-store"
    return r


# ───────────── calls (WebRTC signalling by simple polling) ─────────────
@mbp.get("/api/chat/ice")
@any_role
def ice():
    """STUN + TURN list for calls. Best: set TURN_URL / TURN_USERNAME / TURN_CREDENTIAL (or ICE_SERVERS_JSON)."""
    raw = os.environ.get("ICE_SERVERS_JSON")
    try:
        servers = json.loads(raw) if raw else None
    except ValueError:
        servers = None
    if not servers:
        servers = [{"urls": ["stun:stun.l.google.com:19302", "stun:stun1.l.google.com:19302"]}]
        turn = os.environ.get("TURN_URL")
        if turn:
            servers.append({"urls": [u.strip() for u in turn.split(",") if u.strip()],
                            "username": os.environ.get("TURN_USERNAME", ""), "credential": os.environ.get("TURN_CREDENTIAL", "")})
        else:   # public best-effort relay (may be slow, limited or withdrawn) — use your own TURN for real use
            servers.append({"urls": ["turn:openrelay.metered.ca:80", "turn:openrelay.metered.ca:443", "turn:openrelay.metered.ca:443?transport=tcp"],
                            "username": "openrelayproject", "credential": "openrelayproject"})
    return jsonify(iceServers=servers, has_turn=any(str(u).startswith("turn") for s in servers for u in (s["urls"] if isinstance(s["urls"], list) else [s["urls"]])))


def _call(cid):
    c = db().execute("SELECT * FROM calls WHERE id=?", (cid,)).fetchone()
    if not c or not _patient(c["patient_id"]):
        return None
    return c


@mbp.post("/api/chat/threads/<int:pid>/call")
@any_role
def call_start(pid):
    con, now = db(), now_local()
    if not _patient(pid):
        return jsonify(error="Chat not found."), 404
    _mark_present(); _expire(con, now)
    kind = "audio" if (request.get_json(silent=True) or {}).get("kind") == "audio" else "video"
    busy = con.execute("SELECT id FROM calls WHERE patient_id=? AND state IN ('ringing','active')", (pid,)).fetchone()
    if busy:
        return jsonify(error="There is already a call in this chat.", id=busy["id"]), 409
    cur = con.execute("INSERT INTO calls(patient_id,caller_id,caller_name,caller_role,kind,state,created_at,hb_caller) VALUES(?,?,?,?,?,'ringing',?,?)",
                      (pid, g.me["id"], g.me["name"], g.me["role"], kind, iso(now), iso(now)))
    con.commit()
    return jsonify(id=cur.lastrowid, kind=kind)


@mbp.post("/api/chat/calls/<int:cid>/accept")
@any_role
def call_accept(cid):
    con, now = db(), now_local()
    c = _call(cid)
    if not c or c["caller_id"] == g.me["id"] or (c["caller_role"] != "user" and g.me["role"] != "user") or (c["caller_role"] == "user" and g.me["role"] == "user"):
        return jsonify(error="Call not found."), 404
    cur = con.execute("UPDATE calls SET state='active',callee_id=?,callee_name=?,answered_at=?,hb_callee=? WHERE id=? AND state='ringing'",
                      (g.me["id"], g.me["name"], iso(now), iso(now), cid))
    con.commit()
    if not cur.rowcount:
        return jsonify(error="This call was already answered or ended."), 409
    return jsonify(ok=True, kind=c["kind"])


@mbp.post("/api/chat/calls/<int:cid>/decline")
@any_role
def call_decline(cid):
    con, now = db(), now_local()
    c = _call(cid)
    if not c or c["caller_id"] == g.me["id"]:
        return jsonify(error="Call not found."), 404
    _finish(con, c, "declined", now); con.commit()
    return jsonify(ok=True)


@mbp.post("/api/chat/calls/<int:cid>/end")
@any_role
def call_end(cid):
    con, now = db(), now_local()
    c = _call(cid)
    if not c:
        return jsonify(error="Call not found."), 404
    _finish(con, c, "ended" if c["state"] == "active" else "missed", now); con.commit()
    return jsonify(ok=True)


@mbp.post("/api/chat/calls/<int:cid>/signal")
@any_role
def call_signal(cid):
    con, now = db(), now_local()
    c = _call(cid)
    d = request.get_json(silent=True) or {}
    payload = json.dumps(d.get("payload"))
    if not c or c["state"] not in ("ringing", "active") or d.get("kind") not in ("offer", "answer", "ice") or len(payload) > 30000:
        return jsonify(error="Cannot send signal."), 400
    con.execute("INSERT INTO call_signals(call_id,from_id,kind,payload,created_at) VALUES(?,?,?,?,?)", (cid, g.me["id"], d["kind"], payload, iso(now)))
    con.commit()
    return jsonify(ok=True)


@mbp.get("/api/chat/calls/<int:cid>/poll")
@any_role
def call_poll(cid):
    con, now = db(), now_local()
    c = _call(cid)
    if not c:
        return jsonify(error="Call not found."), 404
    mine = "hb_caller" if c["caller_id"] == g.me["id"] else "hb_callee"
    if c["state"] in ("ringing", "active"):
        con.execute(f"UPDATE calls SET {mine}=? WHERE id=?", (iso(now), cid)); con.commit()
    _expire(con, now)
    c = con.execute("SELECT * FROM calls WHERE id=?", (cid,)).fetchone()
    after = request.args.get("after", type=int) or 0
    sigs = [{"id": s["id"], "kind": s["kind"], "payload": json.loads(s["payload"])} for s in
            con.execute("SELECT * FROM call_signals WHERE call_id=? AND id>? AND from_id<>? ORDER BY id", (cid, after, g.me["id"]))]
    peer = (c["callee_name"] or "Care team") if c["caller_id"] == g.me["id"] else c["caller_name"]
    return jsonify(state=c["state"], kind=c["kind"], peer=peer, i_am_caller=c["caller_id"] == g.me["id"], signals=sigs)


# ───────────── page ─────────────
@mbp.get("/chat")
@page_guard(("admin", "caregiver", "user"))
def page_chat(u):
    return render_template("chat.html", user=u)
