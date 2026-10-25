-- ==============================================================================
-- VYBE Migration 003 Rollback: Revert Package Lifecycle & Storage Changes
-- ==============================================================================
-- Version: 003_package_lifecycle_and_cleanup_rollback.sql
-- Safe rollback script: Preserves travel packages and core user data.

BEGIN;

-- 1. Drop RLS policies on package_images
DROP POLICY IF EXISTS "Service role bypass for package images" ON package_images;
DROP POLICY IF EXISTS "Operators can manage images of their own packages" ON package_images;
DROP POLICY IF EXISTS "Public can view package images of active packages" ON package_images;

-- 2. Drop package_images table
DROP TABLE IF EXISTS package_images CASCADE;

-- 3. Drop indexes created in migration 003
DROP INDEX IF EXISTS idx_travel_packages_valid_until;
DROP INDEX IF EXISTS idx_travel_packages_booking_deadline;
DROP INDEX IF EXISTS idx_travel_packages_trip_dates;
DROP INDEX IF EXISTS idx_travel_packages_status_active;
DROP INDEX IF EXISTS idx_travel_packages_operator;
DROP INDEX IF EXISTS idx_users_auth_user_id;
DROP INDEX IF EXISTS idx_audit_events_action;
DROP INDEX IF EXISTS idx_audit_events_created_at;

-- 4. Note: Columns on users and travel_packages are left in place to avoid
-- destructive data loss of existing values in production. If full removal
-- is desired, uncomment the following:
-- ALTER TABLE users DROP COLUMN IF EXISTS auth_user_id;

COMMIT;
