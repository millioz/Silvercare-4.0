"""Start SilverCare WITH the new features:   python run.py
Your original app.py is untouched; this file just loads it and adds extensions.py on top.
For hosting with gunicorn use:   gunicorn run:app
"""
import os

from app import app            # your original app (unchanged)
from extensions import init_extensions

init_extensions(app)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)),
            debug=os.environ.get("FLASK_DEBUG", "0") == "1")
