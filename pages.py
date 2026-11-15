"""The two new pages: /clinic-hub (care team) and /my-care (patient)."""
from flask import render_template

from .core import bp, page_guard


@bp.get("/clinic-hub")
@page_guard(("admin", "caregiver"))
def clinic_hub(u):
    return render_template("clinic_hub.html", user=u)


@bp.get("/my-care")
@page_guard(("user",))
def my_care(u):
    return render_template("patient_hub.html", user=u)
