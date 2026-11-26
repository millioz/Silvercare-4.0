"""Doctor / allergy / condition details and a simple medication safety scan."""
import re

from flask import g, jsonify, request

from .core import bp, db, staff, patient_only, iso, now_local, audit, text_arg, target_user, low_stock_list


def get_profile(con, uid):
    r = con.execute("SELECT doctor_name,doctor_contact,pharmacy,allergies,conditions,updated_at FROM clinical_profiles WHERE user_id=?", (uid,)).fetchone()
    return dict(r) if r else {"doctor_name": "", "doctor_contact": "", "pharmacy": "", "allergies": "", "conditions": "", "updated_at": None}


@bp.route("/api/clinic/patients/<int:uid>/clinical", methods=["GET", "PUT"])
@staff
def clinical(uid):
    row, err = target_user(uid)
    if err:
        return err
    if request.method == "PUT":
        d = request.get_json(silent=True) or {}
        db().execute(
            """INSERT INTO clinical_profiles(user_id,doctor_name,doctor_contact,pharmacy,allergies,conditions,updated_at) VALUES(?,?,?,?,?,?,?)
               ON CONFLICT(user_id) DO UPDATE SET doctor_name=excluded.doctor_name,doctor_contact=excluded.doctor_contact,
               pharmacy=excluded.pharmacy,allergies=excluded.allergies,conditions=excluded.conditions,updated_at=excluded.updated_at""",
            (uid, text_arg(d, "doctor_name", 100), text_arg(d, "doctor_contact", 100), text_arg(d, "pharmacy", 120),
             text_arg(d, "allergies", 500), text_arg(d, "conditions", 500), iso(now_local())))
        db().commit()
        audit("clinical.update", f"user:{uid}")
    return jsonify(get_profile(db(), uid))


@bp.get("/api/clinic/me/clinical")
@patient_only
def my_clinical():
    p = get_profile(db(), g.me["id"])
    return jsonify({k: p[k] for k in ("doctor_name", "doctor_contact", "pharmacy")})


def safety_scan(con, uid):
    prof = get_profile(con, uid)
    allergies = [a.strip().lower() for a in re.split(r"[,;\n]", prof["allergies"]) if len(a.strip()) >= 3]
    meds = con.execute(
        """SELECT m.id,m.name,m.dosage,m.instructions,(SELECT COUNT(*) FROM schedules s WHERE s.medication_id=m.id AND s.active=1) AS times
           FROM medications m WHERE m.user_id=? AND m.active=1""", (uid,)).fetchall()
    items, seen = [], {}
    for m in meds:
        hay = f"{m['name']} {m['instructions']}".lower()
        for a in allergies:
            if a in hay:
                items.append({"level": "danger", "text": f"Possible allergy match: “{m['name']}” matches the recorded allergy “{a}”. Verify with the prescriber or a pharmacist."})
        key = m["name"].strip().lower()
        if key in seen:
            items.append({"level": "warn", "text": f"“{m['name']}” appears more than once in the active list — check for an accidental duplicate."})
        seen[key] = True
        if not m["dosage"].strip():
            items.append({"level": "info", "text": f"“{m['name']}” has no dosage/label text recorded."})
        if m["times"] == 0:
            items.append({"level": "warn", "text": f"“{m['name']}” has no active reminder time."})
    if not allergies:
        items.append({"level": "info", "text": "No allergies recorded. Ask the patient and record them (or write “none known”)."})
    for s in low_stock_list(con, uid):
        items.append({"level": "warn", "text": f"{s['medication']} may run out in about {s['days_left']} days."})
    items.append({"level": "info", "text": "This is a simple text check, NOT a drug-interaction check. Ask a pharmacist or prescriber to review the full medicine list."})
    return items


@bp.get("/api/clinic/patients/<int:uid>/safety-scan")
@staff
def scan_route(uid):
    row, err = target_user(uid)
    if err:
        return err
    return jsonify(safety_scan(db(), uid))
