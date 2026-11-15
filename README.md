# SilverCare — Smart Medication Support System

A full-stack learning prototype that keeps the original SilverCare visual identity (deep navy, cyan/blue glow, grid background) and adds a real Python + SQLite application.

## Included

- Flask backend and SQLite database
- Secure password hashing and role-based login (admin/caregiver/patient)
- Care console to create patient accounts and daily reminder schedules
- Patient dashboard with pending, user-confirmed and missed-window events
- Seven-day user-confirmation trend (not a medical adherence diagnosis)
- REST API for the web dashboard and ESP32 button integration
- Responsive dark navy/cyan interface

## Run in GitHub Codespaces (iPad-friendly)

1. Create a GitHub repository named `SilverCare` and upload this whole folder (keep the folder structure).
2. Open the repository in **Codespaces**.
3. In the terminal, run:

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   python app.py
   ```

4. Open the **Ports** tab, find port `5000`, and choose **Open in Browser**.
5. Sign in with the first-run local admin credentials below.
6. Open **PASSWORD** in the header and change the default admin password immediately. The default is for local development only.

### First-run admin login

- Email: `admin@silvercare.local`
- Password: `ChangeMe123!`

Set a stable secret key and a unique admin password before the first run using environment variables (the app otherwise generates an ephemeral session key):

```bash
export ADMIN_EMAIL="your-admin@example.com"
export ADMIN_PASSWORD="a-long-unique-password"
export SECRET_KEY="a-long-random-secret"
export COOKIE_SECURE=1  # use when accessing over HTTPS
python app.py
```

The database is created automatically as `silvercare.db` in this folder. Keep this file private; it contains account and medication schedule data.

## First use

1. Sign in as admin.
2. Create a patient account (use a unique email and a temporary password of at least 8 characters).
3. Add a medication reminder for that patient. The label and dosage text should match the patient's actual prescription; the app does not decide doses.
4. Give the patient their login credentials securely.
5. The patient dashboard creates today's scheduled events automatically. They can confirm an event after taking the medication.
6. Events still pending after the configured confirmation window are marked `MISSED` by the next dashboard/API refresh.

## ESP32 integration

Each patient account has a unique device token. The admin console displays it once after account creation. Store it securely in the ESP32 firmware; do not publish it in a public repository.

- `GET /api/device/next` with header `X-Device-Token: YOUR_TOKEN` returns currently due event IDs separately from upcoming events.
- `POST /api/device/confirm` with the same header and JSON body `{"event_id": 123}` records a physical-button confirmation.

See `esp32/silvercare_device_example.ino` for a starter sketch. Update the Wi-Fi details and server URL. The computer running Flask and the ESP32 must be able to reach one another over the network. For a hosted Codespaces deployment, the device must be able to reach the forwarded app URL; a local LAN deployment is usually easier for a first hardware test.

## API quick reference

| Method | Route | Purpose |
|---|---|---|
| GET | `/api/health` | Service health check |
| GET | `/api/me` | Current signed-in account |
| GET/POST | `/api/users` | List/create patient accounts (staff only) |
| GET/POST | `/api/medications` | List/create medication reminder |
| GET | `/api/events` | Event history |
| POST | `/api/events/<id>/confirm` | Patient dashboard confirmation |
| GET | `/api/summary` | Today counts and seven-day trend |
| GET | `/api/device/next` | ESP32 pending event IDs (device token) |
| POST | `/api/device/confirm` | ESP32 button confirmation (device token) |

## Important safety and privacy limits

- A `TAKEN` record means a person or device confirmed the reminder. It does **not** prove that medication was swallowed.
- `MISSED` means the configured response window passed without a confirmation. It does not establish what happened clinically.
- The app does not recommend medication, calculate doses, change prescriptions, or advise users to repeat a dose. If a dose is missed or uncertain, follow the prescription's official instructions or contact a pharmacist/clinician.
- Do not use this prototype as a certified medical device or sole clinical monitoring system. It has not undergone medical-device validation, security review, or clinical testing.
- Before real patient use, add HTTPS, CSRF protection, account recovery, audit/retention controls, backups, access reviews, and a privacy/legal review appropriate to your jurisdiction. Do not store real patient information in a public demo repository.

## Technology

- Frontend: HTML, CSS, JavaScript
- Backend: Python / Flask
- Database: SQLite / SQL
- Device: ESP32 HTTP + JSON starter integration
