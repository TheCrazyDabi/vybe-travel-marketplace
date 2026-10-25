# VYBE Storage and Security Architecture

## 1. Storage Architecture Overview

VYBE implements a hybrid media and document storage model supporting:
- **Supabase Storage** (Production primary for package photos and operator media)
- **Cloudflare R2** (S3-compatible alternative)
- **Local Filesystem** (Seamless offline development and automated testing fallback)

### Storage Buckets & Directory Structure

```text
vybe-packages/
└── packages/
    └── {operator_id}/
        └── {uuid4}_{safe_filename}.webp
```

1. **Path Isolation**: Package media files are organized by operator company ID (`packages/{operator_id}/`).
2. **Collision-Proof Naming**: Every uploaded asset is prefixed with a cryptographically generated UUID4 hex string.
3. **MIME & Extension Sanitization**:
   - Permitted image formats: `image/jpeg` (`.jpg`, `.jpeg`), `image/png` (`.png`), `image/webp` (`.webp`).
   - File size limit: Strict 5MB limit enforced at request boundary.

---

## 2. Row Level Security (RLS) & Access Policies

All application tables and storage objects enforce Row Level Security:

### `package_images` Table RLS

1. **Public Discovery Policy**:
   ```sql
   CREATE POLICY "Public can view package images of active packages"
       ON package_images FOR SELECT
       USING (
           EXISTS (
               SELECT 1 FROM travel_packages tp
               WHERE tp.id = package_images.package_id
                 AND tp.is_active = TRUE
                 AND tp.is_deleted = FALSE
           )
       );
   ```

2. **Operator Isolation Policy**:
   ```sql
   CREATE POLICY "Operators can manage images of their own packages"
       ON package_images FOR ALL
       USING (
           EXISTS (
               SELECT 1 FROM travel_packages tp
               JOIN travel_companies tc ON tp.operator_id = tc.id
               JOIN users u ON tc.user_id = u.id
               WHERE tp.id = package_images.package_id
                 AND (u.auth_user_id = auth.uid()::text OR u.email = auth.jwt()->>'email')
           )
       );
   ```

3. **Backend Service Role Bypass**:
   Server-side operations authenticate with `SUPABASE_SERVICE_ROLE_KEY` to execute authorized batch actions (such as scheduled cleanup).

---

## 3. Credential Security & Non-Negotiables

1. **Server-Side Only**:
   - `DATABASE_URL` (with password)
   - `SUPABASE_SERVICE_ROLE_KEY`
   - `CRON_SECRET`
   - `RAZORPAY_KEY_SECRET`
   
   These credentials **MUST NEVER** be embedded in JavaScript bundles, Android APKs, version control, or public health endpoints.

2. **Client-Safe Public Key**:
   - `SUPABASE_ANON_KEY`: Safe for frontend client and mobile app read operations restricted by RLS.

3. **Sanitized Error Reporting**:
   Production health check (`/api/health`) scrubs database URIs and sensitive connection substrings (`re.sub(r"://[^@]+@", "://***:***@", err_msg)`) to guarantee zero secret leakage even during network outages.

---

## 4. Endpoints & Rate Limiting

- `POST /api/packages/<id>/images`: Requires authenticated operator role; ownership checked.
- `DELETE /api/packages/<id>/images`: Requires authenticated operator role; checks orphan status before physical disk/bucket deletion.
- `POST /api/cron/cleanup`: Protected by `CRON_SECRET` Bearer token or Admin session.
