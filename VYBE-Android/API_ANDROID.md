# VYBE Android — API usage

Base URL is user-configurable (login screen → Server settings). Default
`http://10.0.2.2:5000/` (emulator → laptop). Physical phone: `http://<laptop-LAN-ip>:5000`.
ngrok `https://…` URL also works — paste it as the base URL. No code change needed.

All calls are same-origin relative paths on the backend; the app only
prepends the configured base URL. Auth = session cookie (no CSRF token
needed for JSON: the backend only enforces CSRF on HTML forms).

## Endpoints used (all exist in the Flask backend, unchanged)

| Call | Purpose |
|---|---|
| `POST api/auth/register {name,email,password,role}` | signup (201) / 409 duplicate / 400 invalid |
| `POST api/auth/login {email,password}` | login (401 bad, 403 suspended) |
| `POST api/auth/logout` | logout |
| `GET api/profile` | session restore + prefs gate + profile screen (401 logged out) |
| `PUT api/profile {fields incl. name,start_city}` | save prefs + name edit |
| `GET api/packages` | explore list (active only) |
| `GET api/packages/{id}` | detail (404 unknown) |
| `GET api/packages/recommended[?max_price,destination,min_duration,min_score]` | ranked deck + scores/reasons |
| `POST api/packages/{id}/swipe {action: like\|pass}` | record decision |
| `POST|DELETE api/packages/{id}/like` | favourite toggle |
| `POST|DELETE api/packages/{id}/save` | bookmark toggle |
| `GET api/interests[?action=]` | saved/interests list |
| `GET api/enquiries` | My Trips enquiries (exact server statuses) |
| `GET api/bookings` | My Trips bookings (never invented) |
| `GET api/conversations` | chat list (role-scoped by server) |
| `GET api/conversations/{id}/messages` | messages (polled) |
| `POST api/conversations/{id}/messages {body}` | send (201) |

## Planned (backend already supports, app not yet wired)

Operator (`/api/packages` POST/PUT, `/api/companies/verification`,
`/api/enquiries/<id>/quote`), admin (`/api/admin/*`), packing
(`/api/packing*`), companion (`/api/companion/ask`), reports
(`/api/reports`). No new backend endpoints are required for any of them.
