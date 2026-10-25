# VYBE Production Database Migration & Rollback Guide

This guide details the PostgreSQL database architecture, Supabase schema setup, Row Level Security (RLS) policies, and rollback procedures for VYBE.

---

## 1. Database Connection Architecture

VYBE uses **SQLAlchemy 2.x** with **Psycopg 3** (`psycopg[binary]>=3.2.0`) to interface with Supabase Managed PostgreSQL.

### Connection String Formats
Supabase provides two connection types in **Project Settings -> Database**:

1. **Transaction Pooler (Port 6543) — Recommended for Render / Serverless Web Apps**:
   ```
   postgresql+psycopg://postgres.[project-ref]:[password]@aws-0-[region].pooler.supabase.com:6543/postgres?sslmode=require
   ```
2. **Direct Connection (Port 5432) — Recommended for Migrations & Admin Tasks**:
   ```
   postgresql+psycopg://postgres:[password]@db.[project-ref].supabase.co:5432/postgres?sslmode=require
   ```

> [!NOTE]
> VYBE's `_normalize_db_uri()` in `config.py` automatically rewrites `postgres://` or `postgresql://` provided by hosting platforms into `postgresql+psycopg://`.

---

## 2. Running Schema Setup & RLS on Supabase

1. Open your **Supabase Dashboard** -> **SQL Editor**.
2. Create a new query and paste the contents of [`migrations/001_supabase_schema_and_rls.sql`](file:///d:/Projects/VYBE/migrations/001_supabase_schema_and_rls.sql).
3. Click **Run**.
4. Verify all tables in **Table Editor** and check that Row Level Security is enabled on all tables.

---

## 3. Row Level Security (RLS) Policy Verification

All tables enforce **Deny by default**. Only explicit permissions are permitted:

| Table | Policy | Access Target | Permitted Role / Condition |
| :--- | :--- | :--- | :--- |
| `travel_packages` | SELECT | Public / Anon | `status = 'active' AND is_active = TRUE AND is_deleted = FALSE` |
| `travel_packages` | ALL | Operator | `operator_id = own_company_id` |
| `travel_companies`| SELECT | Public / Anon | `status = 'approved'` |
| `travel_companies`| ALL | Operator | `user_id = auth.uid()` |
| `interests` | ALL | Traveler | `traveler_id = auth.uid()` |
| `enquiries` | ALL | Traveler | `traveler_id = auth.uid()` |
| `enquiries` | SELECT | Operator | `company_id = own_company_id` |
| `bookings` | SELECT | Traveler | `traveler_id = auth.uid()` |
| `bookings` | SELECT | Operator | `company_id = own_company_id` |
| `notifications` | ALL | Recipient | `user_id = auth.uid()` |
| `audit_events` | NONE | Public / Anon | Deny all client access (Backend only via `service_role`) |

---

## 4. Migrating Existing Data from SQLite to Supabase

To copy data from your local development database (`instance/vybe.db`) to Supabase without dropping existing records:

```bash
# 1. Test inspection without modifying target
python scripts/migrate_to_supabase.py --dry-run

# 2. Execute migration to target Supabase database
python scripts/migrate_to_supabase.py --target "postgresql+psycopg://postgres.[ref]:[password]@aws-0-[region].pooler.supabase.com:6543/postgres"
```

The script:
1. Validates connectivity and initializes missing tables.
2. Migrates records table-by-table in relational order (`users` -> `companies` -> `packages` -> `bookings`).
3. Resets auto-increment sequences (`pg_get_serial_sequence`) so subsequent insertions never produce primary key collisions.

---

## 5. Rollback Strategy

If a migration requires reversal:
1. Ensure a recent backup or snapshot exists in the **Supabase Dashboard -> Database -> Backups**.
2. Run [`migrations/001_supabase_schema_rollback.sql`](file:///d:/Projects/VYBE/migrations/001_supabase_schema_rollback.sql) in the Supabase SQL Editor.
3. Switch `DATABASE_URL` in your `.env` or Render environment back to your previous database URI.
