# VYBE Automatic Package Expiry & Idempotent Cleanup Guide

## Overview

The VYBE platform implements a two-tier validity and expiry architecture:
1. **Real-time Request-Level Evaluation**: On every package discovery, listing, detail view, or booking request, the backend immediately evaluates package validity timestamps (`valid_until`, `booking_deadline`, and `trip_start_date`). If expired, it immediately hides the package from discovery and rejects booking attempts without waiting for scheduled jobs.
2. **Scheduled Background Cleanup**: An automated job processes expired listings, enforces customer support retention periods, and safely prunes unreferenced records and orphan media assets.

---

## Expiry & Booking Deadline Semantics

| Timestamp Field | Business Purpose | Action on Expiration |
| :--- | :--- | :--- |
| `booking_deadline` | Cutoff moment after which travelers cannot submit new bookings or enquiries | Prevents booking creation immediately (`is_booking_allowed` returns `False`). Listing may remain visible until `valid_until`. |
| `valid_until` | Listing publication validity timestamp | Package is immediately removed from public search and discovery feed (`/discover`, `/api/packages`). |
| `trip_start_date` | Trip execution / departure date | When passed, automatically prevents new bookings and marks status as `expired`. |

---

## Retention and Non-Destructive Cleanup Safeguards

Permanent deletion is subject to strict non-negotiable retention safeguards:

1. **Protected Reference Guarantee**:
   A package is **NEVER** permanently deleted if it has any associated:
   - `Booking` records (confirmed, requested, completed, or cancelled)
   - `Enquiry` records
   - `CustomOffer` / quotation records
   - `Review` records
   - Active `Report` / dispute records
   
   These records are retained indefinitely for customer support, accounting, and legal compliance. Such packages remain safely preserved in `status = 'archived'` or `status = 'expired'`.

2. **Retention Threshold**:
   Only expired or archived packages with **ZERO** protected references that have been inactive for longer than `CLEANUP_RETENTION_DAYS` (default 90 days) are eligible for hard deletion.

3. **Safe Orphan Image Pruning**:
   Before an eligible package record is deleted, the system inspects every associated image (`cover_image`, `images` list, `PackageImage` records). If an image is referenced by *any* other package (shared asset), it is preserved. Only truly unreferenced orphan images are deleted from storage.

4. **Idempotency Guarantee**:
   The cleanup process is fully idempotent. Retrying the cleanup multiple times produces identical outcomes without generating duplicate work, database corruption, or errors.

5. **Security Audit Logging**:
   Every cleanup execution records an entry in the `audit_events` table detailing:
   - `newly_expired_count`
   - `purged_count`
   - `retained_protected_count`
   - `images_purged_count`
   - `duration_ms`
   No personal data, authentication tokens, or credentials are logged.

---

## Scheduling Instructions

### Option 1: Supabase `pg_cron` (Database-Native)

If using Supabase Pro/Team with `pg_cron` and `pg_net` enabled:

```sql
-- Enable necessary extensions in Supabase SQL Editor
CREATE EXTENSION IF NOT EXISTS pg_cron;
CREATE EXTENSION IF NOT EXISTS pg_net;

-- Schedule daily cleanup at 02:00 UTC
SELECT cron.schedule(
    'vybe-daily-package-cleanup',
    '0 2 * * *',
    $$
    SELECT net.http_post(
        url := 'https://vybe-travel-marketplace.vercel.app/api/cron/cleanup?retention_days=90',
        headers := jsonb_build_object(
            'Content-Type', 'application/json',
            'X-Cron-Secret', 'YOUR_CRON_SECRET_HERE'
        )
    );
    $$
);
```

### Option 2: Vercel Cron (`vercel.json`)

Add the cron job to `vercel.json`:

```json
{
  "crons": [
    {
      "path": "/api/cron/cleanup",
      "schedule": "0 2 * * *"
    }
  ]
}
```

Vercel will send `Authorization: Bearer <CRON_SECRET>` automatically if configured in Vercel environment variables.

### Option 3: External Cron or GitHub Actions

A simple scheduled curl request:

```bash
curl -X POST "https://vybe-travel-marketplace.vercel.app/api/cron/cleanup?retention_days=90" \
     -H "X-Cron-Secret: YOUR_CRON_SECRET_HERE"
```

---

## Testing Cleanup Locally

Dry run mode allows inspecting what would be cleaned without modifying the database:

```bash
curl "http://localhost:5000/api/cron/cleanup?dry_run=true&token=dev-cron-secret-change-me"
```

Response format:
```json
{
  "duration_ms": 14,
  "dry_run": true,
  "images_purged_count": 0,
  "newly_expired_count": 2,
  "protected_retained_count": 5,
  "purged_count": 0,
  "purged_package_ids": [],
  "retention_days": 90,
  "status": "success"
}
```
