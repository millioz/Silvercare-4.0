"""API routes for the triage board and per-patient insights."""
from flask import g, jsonify, request

from .core import bp, db, staff, patient_only, now_local, clamp_int, target_user, refresh_events
from .insights import analyze, cohort, plain_brief


@bp.get("/api/clinic/cohort")
@staff
def triage():
    con, now = db(), now_local()
    refresh_events(con, now)
    return jsonify(cohort(con, now))


@bp.get("/api/clinic/patients/<int:uid>/insights")
@staff
def patient_insights(uid):
    row, err = target_user(uid)
    if err:
        return err
    a = analyze(db(), uid, now_local(), clamp_int(request.args.get("days"), 7, 90, 30))
    a["brief"] = plain_brief(a)
    return jsonify(a)


@bp.get("/api/clinic/me/insights")
@patient_only
def my_insights():
    """Gentle, patient-friendly view: no risk labels, just encouragement and facts."""
    a = analyze(db(), g.me["id"], now_local(), 14)
    if not a["decided"]:
        msg = "Your weekly summary will appear after your first reminders are recorded."
    elif a["rate"] >= 90:
        msg = "Wonderful consistency. Keep following your prescribed routine."
    elif a["rate"] >= 70:
        msg = "You are doing well. A few reminders passed without a tap — tell your care team if the times are hard for you."
    else:
        msg = "Several reminders were not confirmed. Please talk to your care team — they can help make your routine easier. Never take extra doses to catch up."
    return jsonify({"rate": a["rate"], "taken": a["taken"], "decided": a["decided"], "streak_days": a["streak_days"],
                    "this_week": a["this_week"], "prev_week": a["prev_week"], "message": msg,
                    "good_notes": [n["text"] for n in a["notes"] if n["level"] == "good"]})
