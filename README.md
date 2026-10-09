# VYBE — Your mood. Your trip. Your VYBE.

AI-powered travel marketplace with swipe-based trip discovery. Travelers set preferences + mood, swipe packages, and connect with verified travel companies.

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

Open http://127.0.0.1:5000

Demo logins (seeded sample data):
- Traveler: `traveler@vybe.demo` / `traveler123`
- Operator: `operator@vybe.demo` / `operator123`
- Admin: `admin@vybe.demo` / `admin123`

## What works (Phase 1 base)

- Landing page with VYBE branding + featured trips
- Auth (traveler/operator) — pages + `/api/auth/*`
- Onboarding / preferences — page + `POST /api/preferences`
- Package list + detail + map (Leaflet/OpenStreetMap)
- Swipe deck skeleton (`/discover`) + `POST /api/packages/<id>/swipe|save`
- Recommendation scoring (`services/recommendation.py`, 25/20/20/15/10/10)
- Operator dashboard, package CRUD, verification submit
- Messaging (polling) + admin verification queue
- Seed data: 2 demo companies, 5 trips (Munnar, Wayanad, Goa, Ooty, Jaipur)
- No AI key required — `services/vybe_ai.py` falls back to keyword rules

## API contract (agreed for parallel work)

Auth: `POST /api/auth/register|login|logout`
Traveler: `GET|PUT /api/profile`, `POST /api/preferences`, `GET /api/packages/recommended`
Packages: `GET /api/packages`, `GET|POST /api/packages[/<id>]`, `PUT /api/packages/<id>`
Discovery: `POST /api/packages/<id>/swipe {action: like|pass}`, `POST .../save`, `GET /api/interests`
Chat: `GET|POST /api/conversations`, `GET|POST /api/conversations/<id>/messages`
Verify: `POST /api/companies/verification`, `GET /api/admin/verifications`, `POST /api/admin/verifications/<id>/decision {decision: approve|reject}`

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
app.py  config.py  seed.py  requirements.txt  .env.example
models/  services/  routes/  templates/  static/  data/sample_packages.json  tests/
```

Hackathon order: Phase 1 ✅ foundation → Phase 2 swipe+tuning → Phase 3 operator/chat → Phase 4 AI/adaptation → Phase 5 map/verify/polish.
