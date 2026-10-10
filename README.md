# VYBE — Your mood. Your trip. Your VYBE.

AI-powered travel marketplace with swipe-based trip discovery. Travelers set preferences + mood, swipe packages, and connect with verified travel companies. Operators publish packages after admin verification; admins monitor users, verifications, bookings, and safety reports.

## Quick start

```bash
git switch main
git pull origin main
git switch -c feature/short-task-name   # never build directly on main

python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
# source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env        # Windows: copy .env.example .env
python app.py               # seeds demo data on first run
```

Windows shortcut: double-click `run.bat` (creates `.venv`, installs deps, starts the app).

Open http://127.0.0.1:5000

Demo logins (seeded sample data):
- Traveler: `traveler@vybe.demo` / `traveler123`
- Operator: `operator@vybe.demo` / `operator123`
- Admin: `admin@vybe.demo` / `admin123`

## What works

- Landing page with VYBE branding (logo, hero, how-it-works, demo accounts)
- Auth with role-based redirects — pages + `/api/auth/*` (traveler/operator self-register; no admin self-register; suspendable accounts)
- Traveler: 5-step onboarding + free-text AI preference extraction, swipe deck (`/discover`) with like/pass/save + undo, filters, detail modal, ranked recommendations with scores + reasons, saved trips, map (Leaflet/OpenStreetMap)
- Roamly companion (offline, no key): 5-day Singapore itinerary with day tabs, stop checkoffs and non-destructive departure checks (`/trips`), categorized packing checklist + document guides + emergency numbers (`/packing`), deterministic AI travel guide with suggestion chips (`/companion`)
- Operator: company profile + verification submit, publish gated on approval, package CRUD, incoming interests, conversations, enquiry → quotation → booking workflow
- Admin: overview counts, user search/suspend/reactivate, verification queue + decision history, safety-report moderation
- Messaging (polling) between travelers and operators
- Seed data: 2 demo companies, 5 trips (Munnar, Wayanad, Goa, Ooty, Jaipur), 1 like, 1 save, 1 demo report
- No AI key required — `services/vybe_ai.py` falls back to keyword rules

## API contract (agreed for parallel work)

Auth: `POST /api/auth/register|login|logout`
Traveler: `GET|PUT /api/profile`, `POST /api/preferences`, `GET /api/packages/recommended`
Packages: `GET /api/packages`, `GET|POST /api/packages[/<id>]`, `PUT /api/packages/<id>`
Discovery: `POST /api/packages/<id>/swipe {action: like|pass}`, `POST .../like|unlike|save|unsave`, `GET /api/interests`
Bookings: `GET|POST /api/enquiries`, enquiry → quotation → confirm flow
Chat: `GET|POST /api/conversations`, `GET|POST /api/conversations/<id>/messages`
Verify: `POST /api/companies/verification`, `GET /api/admin/verifications`, `POST /api/admin/verifications/<id>/decision {decision: approve|reject}`
Admin: `GET /api/admin/overview|users|reports`, `POST /api/admin/users/<id>/status`, `POST /api/admin/reports/<id>/review`
Reports: `POST /api/reports`

JSON shapes match `models/*.py::to_dict()`.

## Team workflow

- `main` stays runnable. Feature branches + PRs only.
- Suggested: `feature/swipe-ui` (Teammate A), `feature/flask-backend` (Teammate B).
- Before a task: `git switch main && git pull origin main && git switch -c feature/<name>`
- After testing: push + open PR, review, merge.
- Never commit `.env`, real keys, passwords, or customer docs. Use `.env.example` placeholders.

## Tests

```bash
pytest -q
```

## Structure

```
app.py  config.py  seed.py  requirements.txt  run.bat  .env.example
models/ (user, company, package, interaction, messaging, moderation, booking)
services/ (recommendation, vybe_ai)
routes/ (main, auth, traveler, packages, operator, bookings, messaging, admin, reports)
templates/  static/ (css, js, images)  data/sample_packages.json  tests/
```

Hackathon order: Phase 1 ✅ foundation → Phase 2 ✅ discovery + matching → Phase 3 ✅ operator/chat/booking → Phase 4 ✅ AI/adaptation + roles → Phase 5 ✅ map/verify/polish + admin.
