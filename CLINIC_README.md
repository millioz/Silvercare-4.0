# SilverCare CLINIC — doctor ↔ patient add-on (adds files only)

Needs the first add-on (extensions.py etc.) already in your project. Nothing old is edited.

## Install
Copy into your project (merge folders):
```
clinic/            (whole folder, next to app.py)
run_all.py         (next to app.py)
templates/         clinic_hub.html, patient_hub.html, report.html
static/            clinic.js, patient_hub.js, clinic_enhance.js, clinic.css
```
Run with:  `python run_all.py`   (loads original app + Care Tools + Clinic)

## Problems it solves
| Real problem | Feature |
|---|---|
| Doctor only knows what patient remembers | Printable **doctor report** + expiring **share link** (outside doctor needs no account) |
| Staff can't tell who needs attention | **Triage board** ranked by simple counted rules, with the reasons shown |
| Side effects never reported | Patient **symptom diary** → staff review queue; red-flag words trigger urgent alert |
| Patient forgets what doctor said | **Visit notes** with a plain-language summary the patient sees |
| Patient forgets to ask questions | **Questions for my doctor** list, staff answer inside the app |
| Phone-tag | Secure **messages** between patient and care team |
| Running out of medicine | **Refill requests** → approve → stock estimate updates |
| Emergencies | **SOS / "call me"** button on every patient page, staff alert with emergency contact |
| Missed visits | **Appointments** shown to the patient |
| Allergy / duplicate mistakes | **Safety scan** (simple text check — not a drug-interaction database) |
| Elderly users | Large-text mode, read-schedule-aloud |

## Optional AI (works fine without it)
```bash
export ANTHROPIC_API_KEY="your key"      # optional: export ANTHROPIC_MODEL=...
export EMERGENCY_NUMBER="119"            # set your country's number
```
AI only runs when staff press ✨ buttons, sees de-identified text (names/emails/phones stripped), outputs are labelled DRAFT, and it is told never to diagnose or suggest dose changes. Without a key, rule-based text is used.

## Safety / privacy
- Insights are counts of confirmations; they are not diagnoses.
- Share links: random token (only its hash is stored), 1–336 h expiry, revocable, every view is audit-logged. Anyone holding a live link can read the report.
- Red-flag word scan is a safety net, not a medical triage tool.
- Before real patients: HTTPS, backups, privacy/legal review, real medical-device/regulatory review where required.
