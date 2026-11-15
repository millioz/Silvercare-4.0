"""Shared pieces for the clinic package: blueprint, database tables, small helpers."""
from __future__ import annotations

import os

from flask import Blueprint, redirect, url_for

# Re-use the helpers from the first add-on (extensions.py) so rules stay identical.
from extensions import (admin_only, any_role, audit, clamp_int, db, guard, iso, now_local,  # noqa: F401
                        refresh_events, staff, stock_info, low_stock_list, target_user, current_me)

bp = Blueprint("clinic", __name__)
patient_only = guard(("user",))


def emergency_number():
    """Set EMERGENCY_NUMBER in the environment for your country (default 119, Korea)."""
    return os.environ.get("EMERGENCY_NUMBER", "119")


def text_arg(data, key, limit):
    return str(data.get(key, "") or "").strip()[:limit]


def page_guard(roles):
    """For HTML pages: send visitors to login (or home) instead of returning JSON errors."""
    def deco(fn):
        from functools import wraps

        @wraps(fn)
        def wrapped(*a, **kw):
            u = current_me()
            if not u:
                return redirect(url_for("login"))
            if u["role"] not in roles:
                return redirect("/")
            return fn(u, *a, **kw)
        return wrapped
    return deco


SCHEMA = """
CREATE TABLE IF NOT EXISTS clinical_profiles (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    doctor_name TEXT DEFAULT '', doctor_contact TEXT DEFAULT '', pharmacy TEXT DEFAULT '',
    allergies TEXT DEFAULT '', conditions TEXT DEFAULT '', updated_at TEXT
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    sender_id INTEGER, sender_role TEXT NOT NULL, sender_name TEXT NOT NULL,
    body TEXT NOT NULL, created_at TEXT NOT NULL,
    read_by_staff INTEGER NOT NULL DEFAULT 0, read_by_patient INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_msg_patient ON messages(patient_id, id);
CREATE TABLE IF NOT EXISTS symptom_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    medication_id INTEGER REFERENCES medications(id) ON DELETE SET NULL,
    severity INTEGER NOT NULL, body TEXT NOT NULL, flagged INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL, reviewed_by TEXT, reviewed_at TEXT, staff_note TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS help_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind TEXT NOT NULL, note TEXT DEFAULT '', created_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open', resolved_by TEXT, resolved_at TEXT
);
CREATE TABLE IF NOT EXISTS appointments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL, with_name TEXT DEFAULT '', location TEXT DEFAULT '',
    starts_at TEXT NOT NULL, notes TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'scheduled', created_by TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS visit_questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    question TEXT NOT NULL, answer TEXT DEFAULT '', answered_by TEXT, answered_at TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS visit_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    author TEXT NOT NULL, internal_note TEXT DEFAULT '', plain_summary TEXT DEFAULT '', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS refill_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    medication_id INTEGER REFERENCES medications(id) ON DELETE SET NULL,
    med_name TEXT NOT NULL, note TEXT DEFAULT '', status TEXT NOT NULL DEFAULT 'pending',
    decided_by TEXT, decided_at TEXT, decision_note TEXT DEFAULT '', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS share_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token_hash TEXT NOT NULL UNIQUE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_by TEXT, created_at TEXT NOT NULL, expires_at TEXT NOT NULL,
    revoked INTEGER NOT NULL DEFAULT 0, views INTEGER NOT NULL DEFAULT 0, days INTEGER NOT NULL DEFAULT 30
);
"""
