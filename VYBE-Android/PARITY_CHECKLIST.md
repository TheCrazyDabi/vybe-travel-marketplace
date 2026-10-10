# VYBE Feature Inventory & Android Parity Checklist

Source of truth: the Flask web app in this repo (verified from `routes/`, `models/`, templates). Status legend: ✅ in Android · 🟡 partial · ⬜ planned.

## Traveler

| VYBE web feature | Route / backend | Android screen | API | Status |
|---|---|---|---|---|
| Register (traveler/operator, no admin self-register) | `POST /register`, `POST /api/auth/register` | Register | `POST api/auth/register` | ✅ |
| Login, role dashboard redirect | `POST /login`, `POST /api/auth/login` | Login, Splash restore | `POST api/auth/login`, `GET api/profile` | ✅ |
| Logout | `GET /logout`, `POST /api/auth/logout` | Top-bar button | `POST api/auth/logout` | ✅ |
| 5-step onboarding questionnaire | `/onboarding` + `TravelerProfile` fields | PrefsEditor (compact subset) | `PUT api/profile` | 🟡 (subset of fields) |
| Discover gating (prefs required) | `GET /discover` + `onboarding_completed` | DeckUi.NeedsPrefs | `GET api/profile` | ✅ |
| Ranked recommendations + scores/reasons | `GET /api/packages/recommended` | Discover deck | same | ✅ |
| Swipe right = interested (enquiry intent) | `POST /api/packages/<id>/swipe{like}` | gesture + button | same | ✅ |
| Swipe left = pass | `.../swipe{pass}` | gesture + button | same | ✅ |
| Like favourite / Save bookmark + undo | `POST|DELETE .../like`, `.../save` | buttons | same | ✅ |
| Explore list + filters | `/packages`, `GET /api/packages` | Explore | same | ✅ (list; web filter UI not ported) |
| Package detail + match explanation | `/packages/<id>` | Detail | `GET api/packages/{id}` | ✅ |
| Saved / interests | `/saved`, `GET /api/interests` | Saved | same | ✅ |
| My Trips (interests/enquiries/bookings) | `/dashboard` | — | — | ⬜ |
| Map (`/map`, Leaflet) | hidden in web scope | — | n/a (coords in API) | ⬜ (matches web: hidden) |
| Chats + messaging (polling) | `/chats`, `/api/conversations*` | — | — | ⬜ |
| Profile page + name edit | `/profile`, `PUT /api/profile{name}` | — | — | ⬜ |
| Packing checklist | `/packing`, `/api/packing*` | — | — | ⬜ |
| AI Guide chat | `/companion`, `/api/companion/ask` | — | — | ⬜ |
| Itinerary UI (`/trips`) | hidden in web scope | — | — | ⬜ (matches web: hidden) |

## Operator

| Feature | Backend | Android | Status |
|---|---|---|---|
| Company + verification submit, status gate | `/operator/company`, `POST /api/companies/verification` | — | ⬜ |
| Package CRUD (approved only) | `/api/packages`, `PUT /api/packages/<id>` | — | ⬜ |
| Incoming interests, conversations, quotes | `/operator`, `/api/enquiries/<id>/quote` | — | ⬜ |

## Admin

| Feature | Backend | Android | Status |
|---|---|---|---|
| Overview, users, suspend, verifications, reports | `/admin`, `/api/admin/*`, `/api/reports` | — | ⬜ |

## Auth/session rules (apply everywhere)

- Session cookie via OkHttp jar; no tokens in code; no secrets persisted (only display name/role cached).
- Role comes from server (`GET /api/profile`); UI role gating mirrors, backend enforces.
- 401/403 → logout → login screen. Suspended → 403 message.
- Pending operators cannot publish (server 403); app surfaces the message.
