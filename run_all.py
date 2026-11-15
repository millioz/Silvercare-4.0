"""Start SilverCare with EVERYTHING:   python run_all.py
(original app.py + Care Tools add-on + Clinic add-on). Nothing in your old files is modified."""
import os

from app import app                    # your original app (unchanged)
from clinic import init_clinic         # also loads extensions.py automatically

init_clinic(app)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)),
            debug=os.environ.get("FLASK_DEBUG", "0") == "1")
