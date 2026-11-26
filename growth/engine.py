"""SilverCare GROWTH — logic that has no web code in it (easy to test, easy to read).

* nearest_dose()  : which ONE reminder a physical button press belongs to
* timeline()      : today's doses for the patient / staff screens
* assistant()     : rule-based Q&A about the patient's OWN schedule (English + Burmese), AI optional
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

EARLY_MIN = 45        # a dose can be confirmed up to 45 min before its time ...
COOLDOWN_SEC = 8      # ... and a 2nd press within 8 s is ignored (stops double-press eating the next dose)
ONLINE_SEC = 180      # ESP32 silent for 3 min = offline (same as extensions.py)


# ───────────────────────── nearest dose ─────────────────────────
def _pending(con, uid, now):
    since = (now.date() - timedelta(days=1)).isoformat()
    rows = con.execute(
        """SELECT e.id,e.scheduled_for,e.status,m.name AS medication_name,m.dosage,m.instructions,s.grace_minutes
           FROM dose_events e JOIN medications m ON m.id=e.medication_id JOIN schedules s ON s.id=e.schedule_id
           WHERE e.user_id=? AND e.status='pending' AND substr(e.scheduled_for,1,10)>=? ORDER BY e.scheduled_for""",
        (uid, since)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["minutes_from_now"] = round((datetime.fromisoformat(r["scheduled_for"]) - now).total_seconds() / 60)  # + future / - overdue
        out.append(d)
    return out


def nearest_dose(con, uid, now):
    """Return (nearest, others_pending, next_later).
    nearest = the pending reminder whose time is closest to now, only if it is inside its window
    (EARLY_MIN before … grace minutes after). All other reminders stay untouched."""
    pend = _pending(con, uid, now)
    ok = [p for p in pend if -p["grace_minutes"] <= p["minutes_from_now"] <= EARLY_MIN]
    nearest = min(ok, key=lambda p: (abs(p["minutes_from_now"]), p["scheduled_for"])) if ok else None
    others = [p for p in pend if not nearest or p["id"] != nearest["id"]]
    later = next((p for p in others if p["minutes_from_now"] > 0), None)
    return nearest, others, later


# ───────────────────────── device info ─────────────────────────
def device_info(con, uid, now):
    r = con.execute("SELECT last_seen,last_ip FROM device_status WHERE user_id=?", (uid,)).fetchone()
    if not r or not r["last_seen"]:
        return {"online": False, "seen_ago_s": None, "last_seen": None}
    ago = int((now - datetime.fromisoformat(r["last_seen"])).total_seconds())
    return {"online": 0 <= ago <= ONLINE_SEC, "seen_ago_s": max(ago, 0), "last_seen": r["last_seen"]}


def device_log(con, uid, limit=15):
    return [dict(r) for r in con.execute(
        "SELECT at,kind,event_id,detail FROM device_log WHERE user_id=? ORDER BY id DESC LIMIT ?", (uid, limit))]


# ───────────────────────── today ─────────────────────────
def timeline(con, uid, now):
    today = now.date().isoformat()
    rows = con.execute(
        """SELECT e.id,e.scheduled_for,e.status,e.confirmed_at,e.confirmation_source,m.name AS medication_name,m.dosage
           FROM dose_events e JOIN medications m ON m.id=e.medication_id
           WHERE e.user_id=? AND substr(e.scheduled_for,1,10)=? ORDER BY e.scheduled_for""", (uid, today)).fetchall()
    notes = {}
    for n in con.execute("SELECT event_id,author,body,created_at FROM dose_notes WHERE user_id=? ORDER BY id", (uid,)):
        notes.setdefault(n["event_id"], []).append({"author": n["author"], "body": n["body"], "at": n["created_at"]})
    nearest, _, later = nearest_dose(con, uid, now)
    items = []
    for r in rows:
        d = dict(r)
        d["notes"] = notes.get(r["id"], [])
        d["is_nearest"] = bool(nearest and nearest["id"] == r["id"])
        items.append(d)
    return {"now": now.isoformat(timespec="seconds"), "items": items, "nearest": nearest, "next": later,
            "taken": sum(i["status"] == "taken" for i in items), "total": len(items),
            "missed": sum(i["status"] == "missed" for i in items)}


# ───────────────────────── assistant (rule-based) ─────────────────────────
MY = re.compile(r"[\u1000-\u109F]")

T = {
    "en": {
        "next_due": "Your nearest medicine is {med}{dose} ({time}). It is time now — press the box button or tap “I took it”.",
        "next_overdue": "{med}{dose} was planned for {time}, {n} min ago. You can still confirm it with the box button or the app.",
        "next_soon": "Your next medicine is {med}{dose} at {time} (in {n} min).",
        "next_none": "No more medicine reminders are waiting today.",
        "today": "Today you have {total} medicine reminder(s). {taken} confirmed, {missed} passed without confirmation.",
        "taken_last": "The last one you confirmed was {med} at {time}.",
        "taken_none": "You have not confirmed any medicine yet today.",
        "missed_some": "{n} reminder(s) passed without confirmation today. Please do not take extra to catch up — follow your prescription label or ask your pharmacist or care team.",
        "missed_none": "Nothing was missed today. Well done.",
        "stats": "In the last 14 days {rate}% of your reminders were confirmed, and you have {streak} good day(s) in a row.",
        "stats_none": "There is not enough history yet to show progress.",
        "device_on": "Your box is online. Pressing its button confirms only the medicine whose time is closest to now.",
        "device_off": "Your box looks offline right now. Check that it is powered and on WiFi. You can also tap “I took it” in the app.",
        "hello": "Hello! Ask me things like: “What is my next medicine?”, “What did I take today?” or “How am I doing?”",
        "unknown": "I can answer questions about your own medicine schedule. For anything else please ask your care team.",
        "st": {"taken": "confirmed", "pending": "waiting", "missed": "missed"},
    },
    "my": {
        "next_due": "အခု သောက်ရမယ့် အနီးဆုံးဆေးက {med}{dose} ({time}) ပါ။ သောက်ချိန်ရောက်ပါပြီ — box ခလုတ်ကို နှိပ်ပါ၊ ဒါမှမဟုတ် “သောက်ပြီး” ကို နှိပ်ပါ။",
        "next_overdue": "{med}{dose} ကို {time} မှာ သောက်ရမှာပါ၊ {n} မိနစ်ကျော်နေပါပြီ။ box ခလုတ် ဒါမှမဟုတ် app ကနေ အခုလည်း အတည်ပြုလို့ရပါသေးတယ်။",
        "next_soon": "နောက်ထပ်ဆေးက {med}{dose} ကို {time} မှာ သောက်ရပါမယ် (နောက် {n} မိနစ်)။",
        "next_none": "ဒီနေ့ ကျန်တဲ့ ဆေးသောက်ချိန် မရှိတော့ပါဘူး။",
        "today": "ဒီနေ့ ဆေးသောက်ချိန် {total} ကြိမ်ရှိပါတယ်။ အတည်ပြုပြီး {taken} ကြိမ်၊ လွတ်သွား {missed} ကြိမ်။",
        "taken_last": "နောက်ဆုံး အတည်ပြုထားတာက {time} က {med} ပါ။",
        "taken_none": "ဒီနေ့ ဆေးသောက်ပြီးကြောင်း မှတ်ထားတာ မရှိသေးပါဘူး။",
        "missed_some": "ဒီနေ့ အတည်ပြုခြင်းမရှိဘဲ ကျော်သွားတာ {n} ကြိမ်ရှိပါတယ်။ လွတ်သွားတာကို အစားထိုးဖို့ ထပ်မသောက်ပါနဲ့။ ဆေးညွှန်းအတိုင်း လိုက်နာပါ၊ ဒါမှမဟုတ် ဆေးဆိုင်/ဆရာဝန်ကို မေးပါ။",
        "missed_none": "ဒီနေ့ လွတ်တာ မရှိပါဘူး၊ တော်ပါတယ်။",
        "stats": "နောက်ဆုံး ၁၄ ရက်အတွင်း {rate}% အတည်ပြုထားပြီး ကောင်းမွန်တဲ့ရက် {streak} ရက် ဆက်တိုက်ရှိပါတယ်။",
        "stats_none": "တိုးတက်မှုပြဖို့ မှတ်တမ်း မလုံလောက်သေးပါဘူး။",
        "device_on": "သင့် box က online ဖြစ်နေပါတယ်။ ခလုတ်နှိပ်ရင် အချိန်အနီးဆုံး ဆေးတစ်ခုကိုပဲ အတည်ပြုပါတယ်။",
        "device_off": "သင့် box က offline ဖြစ်နေပုံရပါတယ်။ ဓာတ်အားနဲ့ WiFi ကို စစ်ပါ။ app ထဲက “သောက်ပြီး” ကိုလည်း နှိပ်လို့ရပါတယ်။",
        "hello": "မင်္ဂလာပါ! ဥပမာ — “နောက်ဆေး ဘယ်အချိန်လဲ”၊ “ဒီနေ့ ဘာသောက်ပြီးပြီလဲ”၊ “ကျွန်တော် ဘယ်လိုနေလဲ” လို့ မေးနိုင်ပါတယ်။",
        "unknown": "သင့်ဆေးအချိန်ဇယားအကြောင်း မေးခွန်းတွေကို ဖြေပေးနိုင်ပါတယ်။ တခြားကိစ္စတွေကို care team ကို မေးပါ။",
        "st": {"taken": "အတည်ပြုပြီး", "pending": "စောင့်နေ", "missed": "လွတ်သွား"},
    },
}

INTENTS = [
    ("hello", r"^\s*(hi|hello|hey|help)\b|မင်္ဂလာ|ဟိုင်း|ကူညီ"),
    ("device", r"\bbutton\b|\bbox\b|device|esp32|wifi|offline|online|ခလုတ်|စက်"),
    ("stats", r"how am i|progress|streak|adherence|my rate|score|ဘယ်လိုနေ|တိုးတက်|ရာခိုင်နှုန်း"),
    ("missed", r"\bmiss|forgot|forget|skipped|too late|မေ့|လွတ်|ကျော်"),
    ("taken", r"did i|have i|\btaken\b|\btook\b|swallow|သောက်ပြီး|သောက်ခဲ့|သောက်ထား"),
    ("today", r"(today|schedule|list).*(medicine|pill|dose|meds|schedule)|(medicine|pill|dose|meds).*today|^\s*today|my schedule|ဒီနေ့.*ဆေး|ယနေ့.*ဆေး|ဇယား"),
    ("next", r"next (medicine|pill|dose|one)|when.*(take|medicine|pill|dose)|what time|which (medicine|pill)|medicine now|နောက်.*ဆေး|ဘယ်အချိန်|ဘာဆေး|အခု.*ဆေး"),
]


def lang_of(text):
    return "my" if MY.search(text or "") else "en"


def intent_of(text):
    t = (text or "").lower()
    for name, rx in INTENTS:
        if re.search(rx, t):
            return name
    return "unknown"


def _hm(iso_s):
    return iso_s[11:16]


def assistant(con, user, text, now, analyze):
    """Rule-based answer built ONLY from this patient's own data. Never doses, never diagnosis."""
    lang, intent = lang_of(text), intent_of(text)
    tx = T[lang]
    tl = timeline(con, user["id"], now)
    near, later = tl["nearest"], tl["next"]
    dose = lambda d: (" " + d["dosage"]) if d.get("dosage") else ""
    if intent == "next":
        if near and near["minutes_from_now"] <= 0 and near["minutes_from_now"] > -3:
            out = tx["next_due"].format(med=near["medication_name"], dose=dose(near), time=_hm(near["scheduled_for"]))
        elif near and near["minutes_from_now"] < 0:
            out = tx["next_overdue"].format(med=near["medication_name"], dose=dose(near), time=_hm(near["scheduled_for"]), n=abs(near["minutes_from_now"]))
        elif near:
            out = tx["next_soon"].format(med=near["medication_name"], dose=dose(near), time=_hm(near["scheduled_for"]), n=near["minutes_from_now"])
        elif later:
            out = tx["next_soon"].format(med=later["medication_name"], dose=dose(later), time=_hm(later["scheduled_for"]), n=later["minutes_from_now"])
        else:
            out = tx["next_none"]
    elif intent == "today":
        lines = [f"• {_hm(i['scheduled_for'])} {i['medication_name']} — {tx['st'].get(i['status'], i['status'])}" for i in tl["items"]]
        out = tx["today"].format(total=tl["total"], taken=tl["taken"], missed=tl["missed"]) + ("\n" + "\n".join(lines) if lines else "")
    elif intent == "taken":
        done = [i for i in tl["items"] if i["status"] == "taken"]
        out = tx["taken_last"].format(med=done[-1]["medication_name"], time=_hm(done[-1]["confirmed_at"] or done[-1]["scheduled_for"])) if done else tx["taken_none"]
    elif intent == "missed":
        out = tx["missed_some"].format(n=tl["missed"]) if tl["missed"] else tx["missed_none"]
    elif intent == "stats":
        a = analyze(con, user["id"], now, 14)
        out = tx["stats"].format(rate=a["rate"], streak=a["streak_days"]) if a["decided"] else tx["stats_none"]
    elif intent == "device":
        out = tx["device_on"] if device_info(con, user["id"], now)["online"] else tx["device_off"]
    elif intent == "hello":
        out = tx["hello"]
    else:
        out = tx["unknown"]
    return {"text": out, "intent": intent, "lang": lang, "ai": False}


def facts_for_ai(con, user, now, analyze):
    """Small, de-identified fact sheet sent to the optional AI (no name/email)."""
    tl = timeline(con, user["id"], now)
    a = analyze(con, user["id"], now, 14)
    return {"now": now.isoformat(timespec="minutes"),
            "today": [{"time": _hm(i["scheduled_for"]), "medicine": i["medication_name"], "status": i["status"]} for i in tl["items"]],
            "confirmation_rate_14d": a["rate"], "good_days_in_a_row": a["streak_days"]}
