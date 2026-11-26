"""Start SilverCare with EVERYTHING:   python run_pro.py
Old files (app.py, extensions.py, clinic/, run.py, run_all.py) stay exactly as they are.
Folders `growth/` and `messenger/` are optional: each is loaded only if it exists.
For hosting with gunicorn use ONE worker with threads:   gunicorn -w 1 --threads 8 run_pro:app"""
import os

from app import app                    # original app (unchanged)

try:
    from growth import init_growth
except ModuleNotFoundError as e:
    if e.name != "growth":
        raise
else:
    init_growth(app)

try:
    from messenger import init_messenger
except ModuleNotFoundError as e:
    if e.name != "messenger":
        raise
else:
    init_messenger(app)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)),
            debug=os.environ.get("FLASK_DEBUG", "0") == "1", threaded=True)
