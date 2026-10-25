# VYBE Deployment and Rollback Instructions

## Migration: 003 — Package Lifecycle, Expiry & Automatic Cleanup
**Branch**: `production/vybe-migration`  
**Target Database**: Supabase PostgreSQL 15+  
**Hosting**: Vercel / Managed Flask  

---

## Pre-Deployment Checklist

1. [x] Branch confirmed: `production/vybe-migration`
2. [x] Automated test suite passing 100% (including `test_package_cleanup_and_lifecycle.py`)
3. [x] No secrets committed to git or logs
4. [x] Migration scripts are idempotent (`IF NOT EXISTS` guards)
5. [x] Rollback plan documented and verified

---

## 1. Production Deployment Procedure

### Step 1: Apply Database Migration on Supabase
1. Open the [Supabase Dashboard](https://supabase.com/dashboard).
2. Navigate to your project -> **SQL Editor**.
3. Open [`migrations/003_package_lifecycle_and_cleanup.sql`](file:///migrations/003_package_lifecycle_and_cleanup.sql).
4. Run the script. It will:
   - Add `auth_user_id` to `users` table with unique index.
   - Ensure `travel_packages` lifecycle columns (`trip_start_date`, `trip_end_date`, `booking_deadline`, `valid_until`, `status`, `is_deleted`, `deleted_at`) and performance indexes exist.
   - Create `package_images` table with foreign key cascades and RLS policies.
   - Add `audit_events` indexes for cleanup monitoring.

### Step 2: Configure Production Environment Variables
On Vercel (or your managed hosting provider), set the following environment variables:

| Variable | Description | Example / Note |
| :--- | :--- | :--- |
| `DATABASE_URL` | Supabase IPv4 Transaction Pooler connection string | `postgresql+psycopg://postgres.[ref]:[pass]@aws-0-[region].pooler.supabase.com:6543/postgres?sslmode=require` |
| `CRON_SECRET` | 32+ character random secret for cron endpoint security | Set in Vercel Environment Variables & Supabase vault |
| `CLEANUP_RETENTION_DAYS` | Days to retain expired packages before pruning | `90` |
| `SUPABASE_URL` | Supabase project URL | `https://[ref].supabase.co` |
| `SUPABASE_ANON_KEY` | Client-safe public key | Public key from API settings |
| `SUPABASE_SERVICE_ROLE_KEY` | Server-only admin key | Secret key for background jobs (Server only) |
| `SUPABASE_STORAGE_BUCKET` | Storage bucket for package photos | `vybe-packages` |

### Step 3: Configure Scheduled Cleanup Job
Choose one of the following methods (see [`docs/automatic_cleanup_guide.md`](file:///docs/automatic_cleanup_guide.md) for detailed configuration):
- **Vercel Cron**: Configured via `vercel.json` hitting `/api/cron/cleanup` daily.
- **Supabase pg_cron**: Scheduled via `cron.schedule()` in SQL Editor.
- **External Cron**: Hitting `POST https://vybe-travel-marketplace.vercel.app/api/cron/cleanup` with header `X-Cron-Secret: [CRON_SECRET]`.

### Step 4: Verification and Smoke Testing
1. Check the production health check endpoint:
   ```bash
   curl https://vybe-travel-marketplace.vercel.app/api/health
   ```
   Must return `{"status": "ok", "app": "VYBE", "database": "connected"}`.
2. Test a dry-run cleanup:
   ```bash
   curl "https://vybe-travel-marketplace.vercel.app/api/cron/cleanup?dry_run=true&token=[CRON_SECRET]"
   ```
   Must return `{"status": "success", "dry_run": true, ...}`.

---

## 2. Rollback Procedure

If any issue arises during or after deployment:

### Step 1: Revert Code Deployment
On Vercel or Git hosting:
- Redeploy the previous stable build commit from the Vercel dashboard with 1 click.

### Step 2: Revert Database Schema (If Necessary)
1. Open the Supabase SQL Editor.
2. Run [`migrations/003_package_lifecycle_and_cleanup_rollback.sql`](file:///migrations/003_package_lifecycle_and_cleanup_rollback.sql).
3. The script will safely:
   - Drop RLS policies on `package_images`
   - Drop `package_images` table
   - Remove newly created indexes
   - Preserve all `travel_packages` rows and core `users` data to prevent destructive data loss.

### Step 3: Verify Post-Rollback Health
```bash
curl https://vybe-travel-marketplace.vercel.app/api/health
```
Verify the application returns 200 OK and database connectivity is operational.
