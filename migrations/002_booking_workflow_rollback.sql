-- Migration 002 Rollback: Revert Booking Request Workflow Columns
-- CAUTION: Drops newly added workflow columns and indexes

DROP INDEX IF EXISTS idx_bookings_status;
DROP INDEX IF EXISTS idx_bookings_idempotency;
DROP INDEX IF EXISTS idx_bookings_reference;

ALTER TABLE bookings DROP COLUMN IF EXISTS accepted_at;
ALTER TABLE bookings DROP COLUMN IF EXISTS cancelled_at;
ALTER TABLE bookings DROP COLUMN IF EXISTS cancelled_by;
ALTER TABLE bookings DROP COLUMN IF EXISTS cancellation_reason;
ALTER TABLE bookings DROP COLUMN IF EXISTS capacity_reserved;
ALTER TABLE bookings DROP COLUMN IF EXISTS terms_snapshot;
ALTER TABLE bookings DROP COLUMN IF EXISTS price_breakdown_snapshot;
ALTER TABLE bookings DROP COLUMN IF EXISTS agreed_price_snapshot;
ALTER TABLE bookings DROP COLUMN IF EXISTS num_travellers;
ALTER TABLE bookings DROP COLUMN IF EXISTS idempotency_key;
ALTER TABLE bookings DROP COLUMN IF EXISTS booking_reference;
