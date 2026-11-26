"""Transparent, rule-based pattern analysis of dose events (no black box, no diagnosis).
Every sentence it produces comes from a simple counted rule, so staff can verify it."""
from __future__ import annotations

from datetime import datetime, timedelta
from statistics import median

BUCKETS = [("Morning", 5, 11), ("Afternoon", 12, 16), ("Evening", 17, 21), ("Night", 22, 4)]
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def bucket_of(hour):
    for name, a, b in BUCKETS:
        if (a <= b and a <= hour <= b) or (a > b and (hour >= a or hour <= b)):
            return name
    return "Morning"


def _rate(taken, decided):
    return round(taken / decided * 100) if decided else None


def analyze(con, uid, now, days=30):
    since = (now.date() - timedelta(days=days - 1)).isoformat()
    rows = con.execute(
        """SELECT e.scheduled_for,e.status,e.confirmed_at,m.name AS med FROM dose_events e
           JOIN medications m ON m.id=e.medication_id
           WHERE e.user_id=? AND substr(e.scheduled_for,1,10)>=? ORDER BY e.scheduled_for""", (uid, since)).fetchall()
    taken = missed = pending = 0
    by_bucket, by_day, by_med, daily, delays = {}, {}, {}, {}, []
    decided_seq = []
    for r in rows:
        if r["status"] == "pending":
            pending += 1
            continue
        dt = datetime.fromisoformat(r["scheduled_for"])
        ok = r["status"] == "taken"
        taken += ok
        missed += (not ok)
        decided_seq.append(ok)
        for store, key in ((by_bucket, bucket_of(dt.hour)), (by_day, WEEKDAYS[dt.weekday()]), (by_med, r["med"])):
            s = store.setdefault(key, [0, 0])  # [taken, decided]
            s[0] += ok
            s[1] += 1
        d = daily.setdefault(dt.date().isoformat(), [0, 0])  # [taken, missed]
        d[0 if ok else 1] += 1
        if ok and r["confirmed_at"]:
            try:
                delays.append((datetime.fromisoformat(r["confirmed_at"]) - dt).total_seconds() / 60)
            except ValueError:
                pass
    decided = taken + missed
    rate = _rate(taken, decided)

    # consecutive missed reminders, newest first
    run = 0
    for ok in reversed(decided_seq):
        if ok:
            break
        run += 1
    # streak of clean days
    streak = 0
    for i in range(days):
        day = (now.date() - timedelta(days=i)).isoformat()
        t, m = daily.get(day, [0, 0])
        if t + m == 0:
            if i == 0:
                continue
            break
        if m:
            break
        streak += 1

    def week_rate(offset):
        t = d = 0
        for i in range(offset, offset + 7):
            day = (now.date() - timedelta(days=i)).isoformat()
            tt, mm = daily.get(day, [0, 0])
            t += tt
            d += tt + mm
        return _rate(t, d)
    this_week, prev_week = week_rate(0), week_rate(7)
    trend = (this_week - prev_week) if (this_week is not None and prev_week is not None) else None
    med_delay = round(median(delays)) if delays else None

    def table(store):
        return [{"name": k, "taken": v[0], "decided": v[1], "rate": _rate(v[0], v[1])}
                for k, v in store.items()]
    buckets = [b for b in table(by_bucket)]
    buckets.sort(key=lambda x: [n for n, _, _ in BUCKETS].index(x["name"]))
    weekdays = table(by_day)
    weekdays.sort(key=lambda x: WEEKDAYS.index(x["name"]))
    meds = table(by_med)

    notes, score, reasons = [], 0, []
    if decided == 0:
        notes.append({"level": "info", "text": "Not enough data yet — insights appear after the first decided reminders."})
    else:
        if rate < 60:
            score += 3; reasons.append(f"Only {rate}% of reminders confirmed over {days} days")
        elif rate < 80:
            score += 1; reasons.append(f"{rate}% of reminders confirmed over {days} days")
        if run >= 3:
            score += 2; reasons.append(f"Last {run} reminders in a row were missed")
            notes.append({"level": "warn", "text": f"The last {run} reminders in a row passed without confirmation."})
        worst = [b for b in buckets if b["decided"] >= 5 and (1 - b["taken"] / b["decided"]) >= 0.4]
        if worst:
            w = min(worst, key=lambda x: x["rate"])
            notes.append({"level": "warn", "text": f"{w['name']} reminders are missed most often ({w['decided'] - w['taken']} of {w['decided']}). "
                                                    "Consider asking the care team whether a different reminder time would suit the patient's routine."})
        wd = [d for d in weekdays if d["decided"] >= 4 and (1 - d["taken"] / d["decided"]) >= 0.5]
        if wd:
            w = min(wd, key=lambda x: x["rate"])
            notes.append({"level": "warn", "text": f"{w['name']}s have the most missed reminders ({w['decided'] - w['taken']} of {w['decided']})."})
        md = [m for m in meds if len(meds) > 1 and m["decided"] >= 4 and (1 - m["taken"] / m["decided"]) >= 0.5]
        if md:
            w = min(md, key=lambda x: x["rate"])
            notes.append({"level": "warn", "text": f"{w['name']} is confirmed less often than the others ({w['taken']} of {w['decided']})."})
        if med_delay is not None and med_delay >= 30:
            notes.append({"level": "info", "text": f"Doses are usually confirmed about {med_delay} minutes after the reminder time."})
        if trend is not None and trend <= -15:
            score += 1; reasons.append(f"Confirmation fell {abs(trend)} points vs the previous week")
            notes.append({"level": "warn", "text": f"This week's confirmation rate ({this_week}%) is lower than last week's ({prev_week}%)."})
        elif trend is not None and trend >= 15:
            notes.append({"level": "good", "text": f"Improving: {this_week}% this week vs {prev_week}% last week."})
        if streak >= 3:
            notes.append({"level": "good", "text": f"{streak} days in a row with every decided reminder confirmed."})
    level = "unknown" if decided == 0 else "high" if score >= 3 else "medium" if score >= 1 else "low"
    return {
        "days": days, "taken": taken, "missed": missed, "pending": pending, "decided": decided, "rate": rate,
        "streak_days": streak, "missed_in_a_row": run, "this_week": this_week, "prev_week": prev_week, "trend": trend,
        "median_confirm_delay_min": med_delay, "by_time_of_day": buckets, "by_weekday": weekdays, "by_medication": meds,
        "notes": notes, "priority": level, "priority_score": score, "reasons": reasons,
        "disclaimer": "Counts of user/device confirmations only. They do not prove medication was taken and are not a clinical assessment.",
    }


def plain_brief(a):
    """Rule-based one-paragraph summary used in reports and as the AI fallback."""
    if not a["decided"]:
        return "No decided reminder events are recorded for this period yet."
    s = (f"Over the last {a['days']} days, {a['taken']} of {a['decided']} reminders were confirmed ({a['rate']}%) "
         f"and {a['missed']} passed without confirmation.")
    warns = [n["text"] for n in a["notes"] if n["level"] == "warn"][:2]
    return " ".join([s] + warns)


def cohort(con, now):
    """Triage board: who may need a check-in today, with the exact reasons."""
    out = []
    for p in con.execute("SELECT id,name FROM users WHERE role='user' AND active=1 ORDER BY name").fetchall():
        a = analyze(con, p["id"], now, 14)
        score, reasons = a["priority_score"], list(a["reasons"])
        helps = con.execute("SELECT COUNT(*) FROM help_requests WHERE user_id=? AND status='open'", (p["id"],)).fetchone()[0]
        flagged = con.execute("SELECT COUNT(*) FROM symptom_logs WHERE user_id=? AND flagged=1 AND reviewed_at IS NULL", (p["id"],)).fetchone()[0]
        overdue = con.execute("SELECT COUNT(*) FROM dose_events WHERE user_id=? AND status='pending' AND scheduled_for<=?",
                              (p["id"], now.isoformat(timespec="seconds"))).fetchone()[0]
        refills = con.execute("SELECT COUNT(*) FROM refill_requests WHERE user_id=? AND status='pending'", (p["id"],)).fetchone()[0]
        unread = con.execute("SELECT COUNT(*) FROM messages WHERE patient_id=? AND sender_role='user' AND read_by_staff=0", (p["id"],)).fetchone()[0]
        if helps:
            score += 5; reasons.insert(0, f"{helps} open help request(s)")
        if flagged:
            score += 3; reasons.append(f"{flagged} unreviewed flagged symptom report(s)")
        if overdue:
            score += 1; reasons.append(f"{overdue} reminder(s) overdue right now")
        if refills:
            reasons.append(f"{refills} refill request(s) waiting")
        if unread:
            reasons.append(f"{unread} unread message(s)")
        level = "high" if score >= 3 else "medium" if score >= 1 else ("unknown" if a["priority"] == "unknown" and not reasons else "low")
        out.append({"id": p["id"], "name": p["name"], "priority": level, "score": score, "reasons": reasons,
                    "rate": a["rate"], "streak_days": a["streak_days"]})
    out.sort(key=lambda x: -x["score"])
    return out
