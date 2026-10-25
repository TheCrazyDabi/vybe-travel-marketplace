-- ==============================================================================
-- VYBE Migration 003: Package Lifecycle, Validity Expiry & Storage Management
-- ==============================================================================
-- Version: 003_package_lifecycle_and_cleanup.sql
-- Compatible with: PostgreSQL 15+ / Supabase Managed Database
-- Idempotent: Can be safely re-run without errors or data duplication.

BEGIN;

-- 1. USERS: Link to Authentication Provider (Supabase Auth / OAuth)
ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS auth_user_id VARCHAR(64);
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_auth_user_id ON users(auth_user_id);

-- 2. TRAVEL PACKAGES: Ensure Lifecycle, Validity & Expiry Columns Exist
ALTER TABLE IF EXISTS travel_packages ADD COLUMN IF NOT EXISTS status VARCHAR(30) NOT NULL DEFAULT 'active';
ALTER TABLE IF EXISTS travel_packages ADD COLUMN IF NOT EXISTS trip_start_date TIMESTAMPTZ;
ALTER TABLE IF EXISTS travel_packages ADD COLUMN IF NOT EXISTS trip_end_date TIMESTAMPTZ;
ALTER TABLE IF EXISTS travel_packages ADD COLUMN IF NOT EXISTS booking_deadline TIMESTAMPTZ;
ALTER TABLE IF EXISTS travel_packages ADD COLUMN IF NOT EXISTS valid_until TIMESTAMPTZ;
ALTER TABLE IF EXISTS travel_packages ADD COLUMN IF NOT EXISTS is_demo BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE IF EXISTS travel_packages ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE IF EXISTS travel_packages ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;

-- Performance & Real-time Discovery Indexes
CREATE INDEX IF NOT EXISTS idx_travel_packages_valid_until ON travel_packages(valid_until);
CREATE INDEX IF NOT EXISTS idx_travel_packages_booking_deadline ON travel_packages(booking_deadline);
CREATE INDEX IF NOT EXISTS idx_travel_packages_trip_dates ON travel_packages(trip_start_date, trip_end_date);
CREATE INDEX IF NOT EXISTS idx_travel_packages_status_active ON travel_packages(status, is_active, is_deleted);
CREATE INDEX IF NOT EXISTS idx_travel_packages_operator ON travel_packages(operator_id);

-- 3. PACKAGE IMAGES: Structured Storage Path Tracking & Metadata
CREATE TABLE IF NOT EXISTS package_images (
    id BIGSERIAL PRIMARY KEY,
    package_id BIGINT NOT NULL REFERENCES travel_packages(id) ON DELETE CASCADE,
    storage_path VARCHAR(1024) NOT NULL,
    url VARCHAR(1024),
    is_cover BOOLEAN NOT NULL DEFAULT FALSE,
    file_size INTEGER,
    mime_type VARCHAR(100),
    uploaded_by BIGINT REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_package_images_package_id ON package_images(package_id);
CREATE INDEX IF NOT EXISTS idx_package_images_storage_path ON package_images(storage_path);

-- 4. ROW LEVEL SECURITY (RLS) POLICIES FOR PACKAGE IMAGES
ALTER TABLE package_images ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    DROP POLICY IF EXISTS "Public can view package images of active packages" ON package_images;
EXCEPTION
    WHEN undefined_object THEN null;
END $$;

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

DO $$ BEGIN
    DROP POLICY IF EXISTS "Operators can manage images of their own packages" ON package_images;
EXCEPTION
    WHEN undefined_object THEN null;
END $$;

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

DO $$ BEGIN
    DROP POLICY IF EXISTS "Service role bypass for package images" ON package_images;
EXCEPTION
    WHEN undefined_object THEN null;
END $$;

CREATE POLICY "Service role bypass for package images"
    ON package_images FOR ALL
    USING (auth.jwt()->>'role' = 'service_role');

-- 5. AUDIT EVENTS: Ensure Indices for Cleanup Monitoring
CREATE INDEX IF NOT EXISTS idx_audit_events_action ON audit_events(action);
CREATE INDEX IF NOT EXISTS idx_audit_events_created_at ON audit_events(created_at);

COMMIT;
