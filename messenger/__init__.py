"""SilverCare MESSENGER add-on (adds files only). init_messenger(app) is called by run_pro.py when this folder exists."""
import os

from clinic import init_clinic
from extensions import open_db

from . import routes

_TAG = (b'<link rel="stylesheet" href="/static/messenger.css">'
        b'<script defer src="/static/messenger.js"></script></body>')


def init_messenger(app):
    if app.extensions.get("silvercare_messenger"):
        return app
    app.extensions["silvercare_messenger"] = True
    init_clinic(app)                                           # messages/users tables first
    app.config.setdefault("CHAT_UPLOAD_DIR", os.environ.get("CHAT_UPLOAD_DIR") or os.path.join(app.root_path, "chat_uploads"))
    con = open_db(app.config["DATABASE"])
    con.executescript(routes.SCHEMA)
    con.commit()
    con.close()
    app.register_blueprint(routes.mbp)

    @app.after_request
    def _inject_messenger_assets(resp):
        from flask import request
        if (resp.status_code == 200 and resp.mimetype == "text/html" and not resp.direct_passthrough
                and request.endpoint not in (None, "static", "clinic.shared_report")):
            body = resp.get_data()
            if b"</body>" in body and b"messenger.js" not in body:
                resp.set_data(body.replace(b"</body>", _TAG, 1))
        return resp
    return app
