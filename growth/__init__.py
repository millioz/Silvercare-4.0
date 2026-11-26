"""SilverCare GROWTH add-on (adds files only). Call init_growth(app) once — run_pro.py does it.

Needs the earlier add-ons (extensions.py + clinic/) which it loads automatically."""
from clinic import init_clinic
from extensions import open_db

from . import routes

_TAG = (b'<link rel="stylesheet" href="/static/growth.css">'
        b'<script defer src="/static/growth.js"></script></body>')


def init_growth(app):
    if app.extensions.get("silvercare_growth"):
        return app
    app.extensions["silvercare_growth"] = True
    init_clinic(app)                                   # idempotent: loads extensions + clinic first
    con = open_db(app.config["DATABASE"])
    con.executescript(routes.SCHEMA)
    con.commit()
    con.close()
    app.register_blueprint(routes.gbp)

    @app.after_request
    def _inject_growth_assets(resp):
        from flask import request
        if (resp.status_code == 200 and resp.mimetype == "text/html" and not resp.direct_passthrough
                and request.endpoint not in (None, "static", "clinic.shared_report")):
            body = resp.get_data()
            if b"</body>" in body and b"growth.js" not in body:
                resp.set_data(body.replace(b"</body>", _TAG, 1))
        return resp
    return app
