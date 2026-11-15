"""OPTIONAL AI helpers. Works with no AI at all (rule-based fallback).

To switch on AI drafting:   export ANTHROPIC_API_KEY="your key"
Optional:                   export ANTHROPIC_MODEL="claude-sonnet-5-5"

PRIVACY: only de-identified text is sent (names/emails/phone numbers are stripped on a best-effort
basis) and ONLY when a staff member presses an AI button. AI output is a DRAFT that a human must
review. The AI is told never to diagnose, never to suggest dose changes, and not to add facts.
Uses only the Python standard library (urllib) — no new pip packages."""
from __future__ import annotations

import json
import os
import re
import urllib.request

API_URL = "https://api.anthropic.com/v1/messages"

SYSTEM = (
    "You help a care team communicate clearly. Rules: (1) never diagnose; (2) never recommend starting, "
    "stopping, skipping or changing any medicine or dose; (3) only use facts given in the input — do not add "
    "medical facts; (4) if something sounds urgent, say to contact the care team or emergency services; "
    "(5) keep wording short, calm and easy to read."
)


def available():
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def redact(text, names=()):
    text = re.sub(r"[\w.+-]+@[\w-]+\.[\w.-]+", "[email]", text or "")
    text = re.sub(r"\+?\d[\d\s().-]{6,}\d", "[number]", text)
    for n in names:
        for part in str(n).split():
            if len(part) >= 2:
                text = re.sub(re.escape(part), "[name]", text, flags=re.I)
    return text


def ask(system, user, max_tokens=600):
    body = json.dumps({"model": os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5-5"), "max_tokens": max_tokens,
                       "system": system, "messages": [{"role": "user", "content": user}]}).encode()
    req = urllib.request.Request(API_URL, data=body, headers={
        "content-type": "application/json", "x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text").strip()


def brief(analysis, fallback_text):
    """Clinician-facing summary of the adherence numbers."""
    if not available():
        return {"text": fallback_text, "ai": False, "note": "AI is not configured; showing the rule-based summary."}
    facts = {k: analysis[k] for k in ("days", "taken", "missed", "decided", "rate", "streak_days", "missed_in_a_row",
                                      "this_week", "prev_week", "median_confirm_delay_min", "by_time_of_day", "by_weekday", "by_medication")}
    prompt = ("Write a 4-6 sentence neutral summary for a clinician reviewing a patient's medication-reminder confirmations. "
              "These are user/device confirmations, not proof of ingestion. Mention patterns and 2-3 questions worth asking the patient. "
              "Do not give medical advice.\n\nDATA:\n" + json.dumps(facts))
    try:
        return {"text": ask(SYSTEM, prompt), "ai": True, "note": "AI-drafted — review before relying on it."}
    except Exception as exc:  # network down, bad key, etc.
        return {"text": fallback_text, "ai": False, "note": f"AI request failed ({type(exc).__name__}); showing rule-based summary."}


def plain_language(note, names=()):
    """Rewrite a clinician's note into simple words for an older patient (staff reviews it first)."""
    clean = redact(note, names)
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", clean) if s.strip()]
    fallback = "\n".join("• " + s for s in sentences)
    if not available():
        return {"text": fallback, "ai": False, "note": "AI is not configured; split into short bullet points for you to edit."}
    prompt = ("Rewrite this note for an elderly patient: short sentences, everyday words, no jargon, under 120 words. "
              "Use 'What to remember' bullets. Do NOT add anything that is not in the note. Keep placeholders like [name] as they are.\n\nNOTE:\n" + clean)
    try:
        return {"text": ask(SYSTEM, prompt, 400), "ai": True, "note": "AI-drafted — read and edit before publishing to the patient."}
    except Exception as exc:
        return {"text": fallback, "ai": False, "note": f"AI request failed ({type(exc).__name__}); split into bullet points instead."}
