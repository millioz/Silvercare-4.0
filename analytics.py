"""Read-only summary of SilverCare's SQLite event history.
Run: python python/analytics.py [path/to/silvercare.db]
"""
import sqlite3
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path

DB = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "silvercare.db"
if not DB.exists():
    raise SystemExit(f"Database not found: {DB}. Start app.py and create some demo events first.")
con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
since = (datetime.now(ZoneInfo("Asia/Seoul")).replace(tzinfo=None) - timedelta(days=7)).isoformat(timespec="seconds")
rows = con.execute("""
    SELECT u.name, COUNT(*) AS decided,
           SUM(CASE WHEN e.status='taken' THEN 1 ELSE 0 END) AS confirmed,
           SUM(CASE WHEN e.status='missed' THEN 1 ELSE 0 END) AS missed_window
    FROM dose_events e JOIN users u ON u.id=e.user_id
    WHERE e.status IN ('taken','missed') AND e.scheduled_for >= ?
    GROUP BY u.id ORDER BY u.name
""", (since,)).fetchall()
print("SILVERCARE · LAST 7 DAYS · CONFIRMATION SUMMARY")
if not rows:
    print("No decided events yet.")
for row in rows:
    pct = round(row['confirmed'] / row['decided'] * 100) if row['decided'] else 0
    print(f"{row['name']}: {row['confirmed']} confirmed / {row['missed_window']} missed-window / {row['decided']} decided ({pct}% user-confirmation rate)")
print("Note: records reflect user/device confirmations, not proof of medication ingestion.")
con.close()
