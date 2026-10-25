-- Migration 002: Booking Request Workflow, Concurrency & Snapshots
-- Supports Prompt 6 reliable booking state machine

-- Allow direct booking requests without requiring prior enquiry
ALTER TABLE bookings ALTER COLUMN enquiry_id DROP NOT NULL;

-- Workflow identifiers and concurrency control
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS booking_reference VARCHAR(36) UNIQUE;
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS idempotency_key VARCHAR(100) UNIQUE;
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS num_travellers INTEGER DEFAULT 1;

-- Snapshots of terms and pricing
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS agreed_price_snapshot INTEGER;
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS price_breakdown_snapshot JSONB DEFAULT '{}'::jsonb;
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS terms_snapshot TEXT;

-- Capacity reservation & lifecycle tracking
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS capacity_reserved BOOLEAN DEFAULT FALSE;
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS cancellation_reason TEXT;
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS cancelled_by BIGINT REFERENCES users(id) ON DELETE SET NULL;
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS cancelled_at TIMESTAMPTZ;
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS accepted_at TIMESTAMPTZ;

-- Performance and lookup indexes
CREATE INDEX IF NOT EXISTS idx_bookings_reference ON bookings(booking_reference);
CREATE INDEX IF NOT EXISTS idx_bookings_idempotency ON bookings(idempotency_key);
CREATE INDEX IF NOT EXISTS idx_bookings_status ON bookings(status);
