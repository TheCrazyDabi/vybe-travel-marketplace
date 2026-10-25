-- ==============================================================================
-- VYBE Travel Marketplace — Supabase PostgreSQL Schema Rollback Script
-- ==============================================================================
-- Warning: This script removes created tables and RLS policies.
-- In production, always backup your database prior to running rollback scripts!

BEGIN;

DROP TABLE IF EXISTS audit_events CASCADE;
DROP TABLE IF EXISTS device_tokens CASCADE;
DROP TABLE IF EXISTS notifications CASCADE;
DROP TABLE IF EXISTS bookings CASCADE;
DROP TABLE IF EXISTS quotations CASCADE;
DROP TABLE IF EXISTS enquiries CASCADE;
DROP TABLE IF EXISTS interests CASCADE;
DROP TABLE IF EXISTS travel_packages CASCADE;
DROP TABLE IF EXISTS verification_records CASCADE;
DROP TABLE IF EXISTS travel_companies CASCADE;
DROP TABLE IF EXISTS user_preferences CASCADE;
DROP TABLE IF EXISTS traveler_profiles CASCADE;
DROP TABLE IF EXISTS users CASCADE;

DROP TYPE IF EXISTS package_status CASCADE;
DROP TYPE IF EXISTS company_status CASCADE;
DROP TYPE IF EXISTS user_role CASCADE;

COMMIT;
