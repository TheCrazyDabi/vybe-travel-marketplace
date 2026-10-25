# VYBE: Supabase Database Setup & Vercel Deployment Guide

This guide explains the current status of Supabase and how to deploy the VYBE Flask application to Vercel with managed Supabase PostgreSQL.

---

## 1. Supabase Database Status: Ready to Connect

All database architecture and migration scripts are fully built and committed to `main`:
- **Complete PostgreSQL & RLS Schema**: [`migrations/001_supabase_schema_and_rls.sql`](../migrations/001_supabase_schema_and_rls.sql)
- **Booking Workflow Schema**: [`migrations/002_booking_workflow.sql`](../migrations/002_booking_workflow.sql)
- **Automated Data Migration Script**: [`scripts/migrate_to_supabase.py`](../scripts/migrate_to_supabase.py)

### Why it is not live yet:
Your project currently connects to local SQLite (`DATABASE_URL=sqlite:///vybe.db`) because connecting to a live Supabase database requires your personal Supabase project URL and database password.

### Step 1: Create Your Supabase Project (2 Minutes)
1. Go to [supabase.com](https://supabase.com) and sign in.
2. Click **New Project** and name it `vybe-production` (choose a region close to your users, e.g., `ap-south-1` Mumbai).
3. Set a strong database password and save it securely.

### Step 2: Apply the Schema
1. In your Supabase Dashboard, click on **SQL Editor** on the left menu.
2. Click **New query**, paste the entire contents of [`migrations/001_supabase_schema_and_rls.sql`](../migrations/001_supabase_schema_and_rls.sql), and click **Run**.
3. Create a second query, paste [`migrations/002_booking_workflow.sql`](../migrations/002_booking_workflow.sql), and click **Run**.
4. All tables, indexes, constraints, and Row Level Security (RLS) policies are now live in PostgreSQL!

### Step 3: Get Your Connection String
1. In the Supabase Dashboard, go to **Project Settings** (gear icon) -> **Database**.
2. Scroll to **Connection string** and select **URI**.
3. Choose **Session mode** or **Transaction pooler** (recommended for serverless Vercel: port `6543`).
4. Replace `[YOUR-PASSWORD]` with your actual database password.
   Example format:
   ```text
   postgresql+psycopg://postgres.[PROJECT_REF]:[PASSWORD]@aws-0-ap-south-1.pooler.supabase.com:6543/postgres?sslmode=require
   ```

### Step 4: Migrate Local Data to Supabase (Optional)
Run the automated migration script with your connection string:
```bash
python scripts/migrate_to_supabase.py "postgresql+psycopg://postgres.[PROJECT_REF]:[PASSWORD]@aws-0-ap-south-1.pooler.supabase.com:6543/postgres?sslmode=require"
```
This transfers all users, travel operators, packages, and bookings into Supabase.

---

## 2. Deploying VYBE on Vercel

Vercel natively runs Python Flask applications via serverless functions. The following entrypoint and configuration files are now set up:
- [`api/index.py`](../api/index.py): Vercel serverless WSGI entrypoint.
- [`vercel.json`](../vercel.json): Rewrites all requests to `api/index.py` while serving `/static` directly.
- [`.vercelignore`](../.vercelignore): Excludes unnecessary files (Android build, tests, docs) to keep serverless deployment fast and lightweight.

> [!IMPORTANT]
> **Vercel Serverless Requirement**:
> Because Vercel serverless functions are stateless, local SQLite files will reset between requests. **You must set `DATABASE_URL` pointing to your Supabase PostgreSQL** in the Vercel Dashboard so all data persists.

### Step 1: Connect Your GitHub Repository on Vercel
1. Log in to [vercel.com](https://vercel.com).
2. Click **Add New...** -> **Project**.
3. Select your GitHub repository: `TheCrazyDabi/vybe-travel-marketplace`.
4. Framework Preset: Leave as **Other** (Vercel automatically detects `api/index.py` and `requirements.txt`).

### Step 2: Configure Environment Variables in Vercel
In the Vercel project setup screen, expand **Environment Variables** and add:

| Variable Name | Value | Description |
|---|---|---|
| `FLASK_ENV` | `production` | Enables production mode and security headers |
| `SECRET_KEY` | *(Generate a 32+ character random string)* | Used for session encryption and CSRF |
| `DATABASE_URL` | *(Your Supabase connection string from above)* | PostgreSQL connection URI |
| `R2_ACCOUNT_ID` | *(Optional - Cloudflare R2 Account ID)* | For cloud file storage |
| `R2_ACCESS_KEY_ID` | *(Optional - R2 Access Key)* | R2 credential |
| `R2_SECRET_ACCESS_KEY` | *(Optional - R2 Secret Key)* | R2 credential |
| `R2_BUCKET_NAME` | `vybe-uploads` | S3 bucket name |
| `RAZORPAY_KEY_ID` | *(Optional - Razorpay Key ID)* | For online INR payments |
| `RAZORPAY_KEY_SECRET` | *(Optional - Razorpay Secret)* | Payment signature verification |
| `SESSION_COOKIE_SECURE` | `true` | Enforces HTTPS-only cookies on Vercel |

### Step 3: Deploy
Click **Deploy**. Vercel will install `requirements.txt`, bundle `api/index.py`, and give you a live production URL (e.g., `https://vybe-travel-marketplace.vercel.app`).

### Step 4: Update Android App Production URL
Once Vercel gives you your live URL, update `PRODUCTION_URL` in [`android/app/src/main/java/com/vybe/travel/MainActivity.java`](../android/app/src/main/java/com/vybe/travel/MainActivity.java):
```java
public static final String PRODUCTION_URL = "https://your-vybe-domain.vercel.app";
```
Re-build the release APK (`./gradlew assembleRelease`), and your Android app will point directly to your live Vercel production deployment!
