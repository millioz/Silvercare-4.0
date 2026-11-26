"""Refill requests: patient taps a button, staff approves and the stock estimate updates automatically."""
from flask import g, jsonify, request

from .core import bp, db, staff, patient_only, iso, now_local, audit, text_arg, clamp_int, stock_info


@bp.get("/api/clinic/me/refills")
@patient_only
def my_refills():
    rows = db().execute("SELECT id,med_name,note,status,decision_note,created_at,decided_at FROM refill_requests WHERE user_id=? ORDER BY id DESC LIMIT 15", (g.me["id"],)).fetchall()
    return jsonify([dict(r) for r in rows])


@bp.post("/api/clinic/me/refills")
@patient_only
def request_refill():
    d = request.get_json(silent=True) or {}
    con = db()
    m = con.execute("SELECT id,name FROM medications WHERE id=? AND user_id=? AND active=1", (clamp_int(d.get("medication_id"), 0, 10**9, 0), g.me["id"])).fetchone()
    if not m:
        return jsonify(error="Choose one of your medicines."), 404
    if con.execute("SELECT 1 FROM refill_requests WHERE user_id=? AND medication_id=? AND status='pending'", (g.me["id"], m["id"])).fetchone():
        return jsonify(error="You already asked for a refill of this medicine. Your care team will answer soon."), 409
    con.execute("INSERT INTO refill_requests(user_id,medication_id,med_name,note,created_at) VALUES(?,?,?,?,?)",
                (g.me["id"], m["id"], m["name"], text_arg(d, "note", 200), iso(now_local())))
    con.commit()
    return jsonify(ok=True), 201


@bp.get("/api/clinic/refills")
@staff
def list_refills():
    status = request.args.get("status", "pending")
    rows = db().execute(
        """SELECT r.id,r.user_id,u.name AS patient,r.medication_id,r.med_name,r.note,r.status,r.created_at,r.decided_by,r.decision_note
           FROM refill_requests r JOIN users u ON u.id=r.user_id WHERE r.status=? ORDER BY r.id DESC LIMIT 60""", (status,)).fetchall()
    return jsonify([dict(r) for r in rows])


@bp.post("/api/clinic/refills/<int:rid>/decide")
@staff
def decide_refill(rid):
    d = request.get_json(silent=True) or {}
    decision = d.get("decision")
    if decision not in ("approved", "denied"):
        return jsonify(error="Decision must be approved or denied."), 400
    con = db()
    r = con.execute("SELECT * FROM refill_requests WHERE id=? AND status='pending'", (rid,)).fetchone()
    if not r:
        return jsonify(error="Pending request not found."), 404
    con.execute("UPDATE refill_requests SET status=?,decided_by=?,decided_at=?,decision_note=? WHERE id=?",
                (decision, g.me["name"], iso(now_local()), text_arg(d, "note", 300), rid))
    add = clamp_int(d.get("add_quantity"), 0, 100000, 0)
    if decision == "approved" and add and r["medication_id"]:
        med = con.execute("SELECT id FROM medications WHERE id=?", (r["medication_id"],)).fetchone()
        info = stock_info(con, med) if med else None
        base = info["remaining"] if info else 0
        ppd = info["pills_per_dose"] if info else 1
        low = info["low_days"] if info else 5
        con.execute(
            """INSERT INTO med_stock(medication_id,quantity,pills_per_dose,low_days,as_of) VALUES(?,?,?,?,?)
               ON CONFLICT(medication_id) DO UPDATE SET quantity=excluded.quantity,as_of=excluded.as_of""",
            (med["id"], base + add, ppd, low, iso(now_local())))
    con.commit()
    audit("refill." + decision, f"refill:{rid}", f"{r['med_name']} +{add}" if add else r["med_name"])
    return jsonify(ok=True)
