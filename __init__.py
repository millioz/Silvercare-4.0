"""SilverCare CLINIC add-on: doctor–patient tools. Call init_clinic(app) once (run_all.py does it)."""
from extensions import init_extensions, open_db

from . import (appointments, clinical, core, diary, insights_routes, messaging, pages, refills,  # noqa: F401  (imports register the routes)
               reports, visits)

_TAG = (b'<link rel="stylesheet" href="/static/clinic.css">'
        b'<script defer src="/static/clinic_enhance.js"></script></body>')


def init_clinic(app):
    if app.extensions.get("silvercare_clinic"):
        return app
    app.extensions["silvercare_clinic"] = True
    init_extensions(app)                     # part 1 (idempotent): scheduler, login protection, Care Tools

    con = open_db(app.config["DATABASE"])
    con.executescript(core.SCHEMA)
    con.commit()
    con.close()
    app.register_blueprint(core.bp)

    @app.after_request
    def _inject_clinic_assets(resp):
        from flask import request
        if (resp.status_code == 200 and resp.mimetype == "text/html" and not resp.direct_passthrough
                and request.endpoint not in (None, "static", "clinic.shared_report")):
            body = resp.get_data()
            if b"</body>" in body and b"clinic_enhance.js" not in body:
                resp.set_data(body.replace(b"</body>", _TAG, 1))
        return resp
    return app
