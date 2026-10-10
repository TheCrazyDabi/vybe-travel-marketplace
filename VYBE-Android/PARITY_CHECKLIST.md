# VYBE Feature Inventory & Android Parity Checklist

Source of truth: the Flask web app in this repo (verified from `routes/`, `models/`, templates). Status legend: ✅ in Android · 🟡 partial · ⬜ planned.

## Traveler

| VYBE web feature | Route / backend | Android screen | API | Status |
|---|---|---|---|---|
| Register (traveler/operator, no admin self-register) | `POST /register`, `POST /api/auth/register` | Register + Show/Hide password | `POST api/auth/register` | ✅ |
| Login, role dashboard redirect | `POST /login`, `POST /api/auth/login` | Login + Show/Hide, Splash restore | `POST api/auth/login`, `GET api/profile` | ✅ |
| Logout | `GET /logout`, `POST /api/auth/logout` | Top-bar + Profile buttons | `POST api/auth/logout` | ✅ |
| 5-step onboarding questionnaire | `/onboarding` + `TravelerProfile` fields | PrefsEditor (compact subset) | `PUT api/profile` | 🟡 (subset of fields) |
| Discover gating (prefs required) | `GET /discover` + completeness rule | DeckUi.NeedsPrefs | `GET api/profile` | ✅ |
| Ranked recommendations + scores/reasons | `GET /api/packages/recommended` | Discover deck | same | ✅ |
| Swipe right = interested (enquiry intent) | `POST /api/packages/<id>/swipe{like}` | gesture + button | same | ✅ |
| Swipe left = pass | `.../swipe{pass}` | gesture + button | same | ✅ |
| Like favourite / Save bookmark + undo | `POST|DELETE .../like`, `.../save` | buttons | same | ✅ |
| Explore list + filters | `/packages`, `GET /api/packages` | Explore | same | ✅ (list; web filter UI not ported) |
| Package detail + match explanation | `/packages/<id>` | Detail | `GET api/packages/{id}` | ✅ |
| Saved / interests | `/saved`, `GET /api/interests` | Saved | same | ✅ |
| My Trips (enquiries + bookings, exact statuses) | `/dashboard` | Trips (5th bottom tab) | `GET api/enquiries`, `GET api/bookings` | ✅ |
| Chats + polling messages | `/chats`, `/api/conversations*` | Chats list + detail (8s poll) | `GET api/conversations`, `GET/POST .../messages` | ✅ |
| Profile (info only) + name/city edit | `/profile`, `PUT /api/profile{name,start_city}` | Profile (phone/bio demo-local) | same | ✅ |
| Map (`/map`, Leaflet) | hidden in web scope | — | n/a (coords in API) | ⬜ (matches web: hidden) |
| Packing checklist | `/packing`, `/api/packing*` | — | — | ⬜ |
| AI Guide chat | `/companion`, `/api/companion/ask` | — | — | ⬜ |
| Itinerary UI (`/trips`) | hidden in web scope | — | — | ⬜ (matches web: hidden) |

## Operator

| Feature | Backend | Android | Status |
|---|---|---|---|
| Company + verification submit, status gate | `/operator/company`, `POST /api/companies/verification` | — | ⬜ |
| Package CRUD (approved only) | `/api/packages`, `PUT /api/packages/<id>` | — | ⬜ |
| Incoming interests, quotes, conversations | `/operator`, `/api/enquiries/<id>/quote` | — | ⬜ |

## Admin

| Feature | Backend | Android | Status |
|---|---|---|---|
| Overview, users, suspend, verifications, reports | `/admin`, `/api/admin/*`, `/api/reports` | — | ⬜ |

## Auth/session rules (apply everywhere)

- Session cookie via OkHttp jar; no tokens in code; no secrets persisted (only display name/role cached).
- Role comes from server (`GET /api/profile`); UI role gating mirrors, backend enforces.
- 401/403 → logout → login screen. Suspended → 403 message.
- Pending operators cannot publish (server 403); app surfaces the message.
