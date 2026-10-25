-- ==============================================================================
-- VYBE Travel Marketplace — Complete Supabase PostgreSQL Schema & RLS Policies
-- ==============================================================================
-- Migration Version: 001_initial_schema_and_rls.sql
-- Compatible with: Supabase Managed PostgreSQL (15+) / SQLAlchemy 2.x / Psycopg 3
-- Security: Row Level Security (RLS) enabled on all tables, Deny by default.

BEGIN;

-- 1. EXTENSIONS
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- 2. ENUMS & DOMAINS
DO $$ BEGIN
    CREATE TYPE user_role AS ENUM ('traveler', 'operator', 'admin');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE company_status AS ENUM ('pending', 'approved', 'rejected');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE package_status AS ENUM ('draft', 'active', 'inactive', 'expired', 'archived');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- 3. ENSURE ALL COLUMNS EXIST IF TABLES WERE PREVIOUSLY CREATED
ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'active';
ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS status_reason TEXT;
ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS is_email_verified BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMPTZ;

ALTER TABLE IF EXISTS travel_companies ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'pending';
ALTER TABLE IF EXISTS travel_companies ADD COLUMN IF NOT EXISTS operating_regions JSONB DEFAULT '[]'::jsonb;
ALTER TABLE IF EXISTS travel_companies ADD COLUMN IF NOT EXISTS is_demo BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE IF EXISTS travel_packages ADD COLUMN IF NOT EXISTS status VARCHAR(30) NOT NULL DEFAULT 'active';
ALTER TABLE IF EXISTS travel_packages ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE IF EXISTS travel_packages ADD COLUMN IF NOT EXISTS is_demo BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE IF EXISTS travel_packages ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE IF EXISTS travel_packages ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE IF EXISTS travel_packages ADD COLUMN IF NOT EXISTS price_confirmed_at TIMESTAMPTZ;
ALTER TABLE IF EXISTS travel_packages ADD COLUMN IF NOT EXISTS trip_start_date TIMESTAMPTZ;
ALTER TABLE IF EXISTS travel_packages ADD COLUMN IF NOT EXISTS trip_end_date TIMESTAMPTZ;
ALTER TABLE IF EXISTS travel_packages ADD COLUMN IF NOT EXISTS booking_deadline TIMESTAMPTZ;
ALTER TABLE IF EXISTS travel_packages ADD COLUMN IF NOT EXISTS valid_until TIMESTAMPTZ;

ALTER TABLE IF EXISTS bookings ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'confirmed';
ALTER TABLE IF EXISTS bookings ADD COLUMN IF NOT EXISTS booking_reference VARCHAR(36);
ALTER TABLE IF EXISTS bookings ADD COLUMN IF NOT EXISTS idempotency_key VARCHAR(100);
ALTER TABLE IF EXISTS bookings ADD COLUMN IF NOT EXISTS num_travellers INTEGER DEFAULT 1;
ALTER TABLE IF EXISTS bookings ADD COLUMN IF NOT EXISTS agreed_price_snapshot INTEGER;
ALTER TABLE IF EXISTS bookings ADD COLUMN IF NOT EXISTS price_breakdown_snapshot JSONB DEFAULT '{}'::jsonb;
ALTER TABLE IF EXISTS bookings ADD COLUMN IF NOT EXISTS terms_snapshot TEXT;
ALTER TABLE IF EXISTS bookings ADD COLUMN IF NOT EXISTS capacity_reserved BOOLEAN DEFAULT FALSE;
ALTER TABLE IF EXISTS bookings ADD COLUMN IF NOT EXISTS cancellation_reason TEXT;
ALTER TABLE IF EXISTS bookings ADD COLUMN IF NOT EXISTS cancelled_by BIGINT;
ALTER TABLE IF EXISTS bookings ADD COLUMN IF NOT EXISTS cancelled_at TIMESTAMPTZ;
ALTER TABLE IF EXISTS bookings ADD COLUMN IF NOT EXISTS accepted_at TIMESTAMPTZ;
ALTER TABLE IF EXISTS bookings ADD COLUMN IF NOT EXISTS razorpay_order_id VARCHAR(100);
ALTER TABLE IF EXISTS bookings ADD COLUMN IF NOT EXISTS razorpay_payment_id VARCHAR(100);
ALTER TABLE IF EXISTS bookings ADD COLUMN IF NOT EXISTS razorpay_signature VARCHAR(255);
ALTER TABLE IF EXISTS bookings ADD COLUMN IF NOT EXISTS currency VARCHAR(10) DEFAULT 'INR';
ALTER TABLE IF EXISTS bookings ADD COLUMN IF NOT EXISTS amount_paid INTEGER;
ALTER TABLE IF EXISTS bookings ADD COLUMN IF NOT EXISTS payment_method VARCHAR(50);

-- 4. CORE USERS & PROFILES
CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(120) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'traveler',
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    status_reason TEXT,
    is_email_verified BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_login_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
CREATE INDEX IF NOT EXISTS idx_users_status ON users(status);

CREATE TABLE IF NOT EXISTS traveler_profiles (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    phone VARCHAR(30),
    bio TEXT,
    avatar_url VARCHAR(512),
    home_city VARCHAR(100),
    travel_moods JSONB DEFAULT '[]'::jsonb,
    travel_pace VARCHAR(20),
    trip_desires JSONB DEFAULT '[]'::jsonb,
    destination_prefs JSONB DEFAULT '[]'::jsonb,
    activity_prefs JSONB DEFAULT '[]'::jsonb,
    preferred_destinations JSONB DEFAULT '[]'::jsonb,
    avoid_destinations JSONB DEFAULT '[]'::jsonb,
    preferred_region_text VARCHAR(200),
    start_city VARCHAR(120),
    destination_text VARCHAR(200),
    budget_per_person INTEGER,
    budget_flex_pct INTEGER DEFAULT 20,
    travel_start_date VARCHAR(20),
    travel_end_date VARCHAR(20),
    date_flexible BOOLEAN DEFAULT TRUE,
    num_travellers INTEGER DEFAULT 2,
    accommodation_prefs JSONB DEFAULT '[]'::jsonb,
    transport_prefs JSONB DEFAULT '[]'::jsonb,
    trip_mode VARCHAR(20),
    travel_style VARCHAR(20),
    group_size_pref VARCHAR(30),
    itinerary_pref VARCHAR(20),
    priority VARCHAR(20),
    disliked_activities JSONB DEFAULT '[]'::jsonb,
    accessibility_notes TEXT,
    dietary_notes TEXT,
    other_notes TEXT,
    ideal_trip_text TEXT,
    onboarding_completed BOOLEAN DEFAULT FALSE,
    onboarding_step INTEGER DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_preferences (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    destinations JSONB DEFAULT '[]'::jsonb,
    styles JSONB DEFAULT '[]'::jsonb,
    interests JSONB DEFAULT '[]'::jsonb,
    budget_range JSONB DEFAULT '{}'::jsonb,
    email_notifications BOOLEAN DEFAULT TRUE,
    push_notifications BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 5. OPERATOR COMPANIES & VERIFICATION
CREATE TABLE IF NOT EXISTS travel_companies (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    company_name VARCHAR(160) NOT NULL,
    business_email VARCHAR(255) NOT NULL,
    contact_details VARCHAR(255),
    description TEXT,
    licence_info VARCHAR(255),
    document_path VARCHAR(512),
    service_regions JSONB DEFAULT '[]'::jsonb,
    operating_regions JSONB DEFAULT '[]'::jsonb,
    logo VARCHAR(512),
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    is_verified BOOLEAN NOT NULL DEFAULT FALSE,
    contact_person VARCHAR(120),
    business_type VARCHAR(80),
    phone VARCHAR(50),
    is_demo BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_travel_companies_user ON travel_companies(user_id);
CREATE INDEX IF NOT EXISTS idx_travel_companies_status ON travel_companies(status);

CREATE TABLE IF NOT EXISTS verification_records (
    id BIGSERIAL PRIMARY KEY,
    company_id BIGINT NOT NULL REFERENCES travel_companies(id) ON DELETE CASCADE,
    submitted_by BIGINT REFERENCES users(id) ON DELETE SET NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    reviewer_note TEXT,
    reviewed_by BIGINT REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reviewed_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_verification_records_company ON verification_records(company_id);
CREATE INDEX IF NOT EXISTS idx_verification_records_status ON verification_records(status);

-- 6. TRAVEL PACKAGES
CREATE TABLE IF NOT EXISTS travel_packages (
    id BIGSERIAL PRIMARY KEY,
    operator_id BIGINT REFERENCES travel_companies(id) ON DELETE CASCADE,
    title VARCHAR(180) NOT NULL,
    destination VARCHAR(140) NOT NULL,
    short_desc VARCHAR(280),
    itinerary TEXT,
    price INTEGER NOT NULL DEFAULT 0 CHECK (price >= 0),
    duration_days INTEGER NOT NULL DEFAULT 1 CHECK (duration_days >= 1 AND duration_days <= 365),
    nights INTEGER,
    min_group_size INTEGER,
    max_group_size INTEGER,
    capacity INTEGER,
    seats_remaining INTEGER,
    cover_image VARCHAR(512),
    images JSONB DEFAULT '[]'::jsonb,
    photos JSONB DEFAULT '[]'::jsonb,
    inclusions JSONB DEFAULT '[]'::jsonb,
    exclusions JSONB DEFAULT '[]'::jsonb,
    suitable_travel_styles JSONB DEFAULT '[]'::jsonb,
    suitable_groups JSONB DEFAULT '[]'::jsonb,
    departure_dates_list JSONB DEFAULT '[]'::jsonb,
    price_breakdown JSONB DEFAULT '{}'::jsonb,
    price_kind VARCHAR(20),
    group_size VARCHAR(60),
    accommodation VARCHAR(200),
    transportation VARCHAR(200),
    available_dates JSONB DEFAULT '[]'::jsonb,
    trip_start_date TIMESTAMPTZ,
    trip_end_date TIMESTAMPTZ,
    booking_deadline TIMESTAMPTZ,
    valid_until TIMESTAMPTZ,
    cancellation_terms TEXT,
    customization_options TEXT,
    status VARCHAR(30) NOT NULL DEFAULT 'active',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_demo BOOLEAN NOT NULL DEFAULT FALSE,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMPTZ,
    price_confirmed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_travel_packages_operator ON travel_packages(operator_id);
CREATE INDEX IF NOT EXISTS idx_travel_packages_destination ON travel_packages(destination);
CREATE INDEX IF NOT EXISTS idx_travel_packages_status ON travel_packages(status, is_active, is_deleted);
CREATE INDEX IF NOT EXISTS idx_travel_packages_price ON travel_packages(price);

-- 7. SWIPES / INTERESTS / FAVORITES
CREATE TABLE IF NOT EXISTS interests (
    id BIGSERIAL PRIMARY KEY,
    traveler_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    package_id BIGINT NOT NULL REFERENCES travel_packages(id) ON DELETE CASCADE,
    action VARCHAR(10) NOT NULL, -- like | pass | save
    reason VARCHAR(50),
    comment TEXT,
    feedback_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_traveler_package_action UNIQUE(traveler_id, package_id, action)
);
CREATE INDEX IF NOT EXISTS idx_interests_traveler ON interests(traveler_id);
CREATE INDEX IF NOT EXISTS idx_interests_package ON interests(package_id);

-- 8. ENQUIRIES, QUOTATIONS & BOOKINGS
CREATE TABLE IF NOT EXISTS enquiries (
    id BIGSERIAL PRIMARY KEY,
    traveler_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    package_id BIGINT NOT NULL REFERENCES travel_packages(id) ON DELETE CASCADE,
    company_id BIGINT NOT NULL REFERENCES travel_companies(id) ON DELETE CASCADE,
    status VARCHAR(30) NOT NULL DEFAULT 'interested',
    num_travellers INTEGER DEFAULT 1 CHECK (num_travellers >= 1),
    travel_date VARCHAR(30),
    message TEXT,
    total_cost INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_enquiries_traveler ON enquiries(traveler_id);
CREATE INDEX IF NOT EXISTS idx_enquiries_company ON enquiries(company_id);
CREATE INDEX IF NOT EXISTS idx_enquiries_status ON enquiries(status);

CREATE TABLE IF NOT EXISTS quotations (
    id BIGSERIAL PRIMARY KEY,
    enquiry_id BIGINT NOT NULL REFERENCES enquiries(id) ON DELETE CASCADE,
    operator_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    price_per_person INTEGER NOT NULL DEFAULT 0,
    total_price INTEGER,
    availability_note TEXT,
    valid_until VARCHAR(30),
    message TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'sent',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_quotations_enquiry ON quotations(enquiry_id);

CREATE TABLE IF NOT EXISTS bookings (
    id BIGSERIAL PRIMARY KEY,
    booking_reference VARCHAR(36) UNIQUE,
    idempotency_key VARCHAR(100) UNIQUE,
    enquiry_id BIGINT REFERENCES enquiries(id) ON DELETE CASCADE,
    traveler_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    package_id BIGINT NOT NULL REFERENCES travel_packages(id) ON DELETE CASCADE,
    company_id BIGINT NOT NULL REFERENCES travel_companies(id) ON DELETE CASCADE,
    status VARCHAR(20) NOT NULL DEFAULT 'confirmed',
    num_travellers INTEGER DEFAULT 1,
    agreed_price_snapshot INTEGER,
    price_breakdown_snapshot JSONB DEFAULT '{}'::jsonb,
    terms_snapshot TEXT,
    capacity_reserved BOOLEAN DEFAULT FALSE,
    cancellation_reason TEXT,
    cancelled_by BIGINT REFERENCES users(id) ON DELETE SET NULL,
    cancelled_at TIMESTAMPTZ,
    accepted_at TIMESTAMPTZ,
    traveller_details JSONB DEFAULT '{}'::jsonb,
    total_cost INTEGER,
    itinerary_snapshot TEXT,
    terms TEXT,
    payment_status VARCHAR(30) NOT NULL DEFAULT 'simulated_pending',
    razorpay_order_id VARCHAR(100),
    razorpay_payment_id VARCHAR(100),
    razorpay_signature VARCHAR(255),
    currency VARCHAR(10) DEFAULT 'INR',
    amount_paid INTEGER,
    payment_method VARCHAR(50),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    confirmed_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_bookings_traveler ON bookings(traveler_id);
CREATE INDEX IF NOT EXISTS idx_bookings_company ON bookings(company_id);
CREATE INDEX IF NOT EXISTS idx_bookings_status ON bookings(status);
CREATE INDEX IF NOT EXISTS idx_bookings_reference ON bookings(booking_reference);
CREATE INDEX IF NOT EXISTS idx_bookings_idempotency ON bookings(idempotency_key);
CREATE INDEX IF NOT EXISTS idx_bookings_razorpay_order ON bookings(razorpay_order_id);

-- 9. NOTIFICATIONS & DEVICE TOKENS
CREATE TABLE IF NOT EXISTS notifications (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(200) NOT NULL,
    body TEXT NOT NULL,
    type VARCHAR(50) DEFAULT 'info',
    data JSONB DEFAULT '{}'::jsonb,
    is_read BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_notifications_user_unread ON notifications(user_id, is_read);

CREATE TABLE IF NOT EXISTS device_tokens (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token VARCHAR(500) NOT NULL UNIQUE,
    platform VARCHAR(30) DEFAULT 'android',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_device_tokens_user ON device_tokens(user_id);

-- 10. AUDIT EVENTS
CREATE TABLE IF NOT EXISTS audit_events (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
    action VARCHAR(100) NOT NULL,
    target_type VARCHAR(50),
    target_id VARCHAR(100),
    ip_address VARCHAR(45),
    user_agent VARCHAR(255),
    details JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_audit_events_action ON audit_events(action);
CREATE INDEX IF NOT EXISTS idx_audit_events_created ON audit_events(created_at);

-- ==============================================================================
-- 11. ROW LEVEL SECURITY (RLS) POLICIES
-- ==============================================================================

ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE traveler_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_preferences ENABLE ROW LEVEL SECURITY;
ALTER TABLE travel_companies ENABLE ROW LEVEL SECURITY;
ALTER TABLE verification_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE travel_packages ENABLE ROW LEVEL SECURITY;
ALTER TABLE interests ENABLE ROW LEVEL SECURITY;
ALTER TABLE enquiries ENABLE ROW LEVEL SECURITY;
ALTER TABLE quotations ENABLE ROW LEVEL SECURITY;
ALTER TABLE bookings ENABLE ROW LEVEL SECURITY;
ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE device_tokens ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_events ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can view own profile" ON users;
CREATE POLICY "Users can view own profile"
    ON users FOR SELECT
    USING (id = (SELECT NULLIF(current_setting('request.jwt.claim.sub', true), '')::bigint));

DROP POLICY IF EXISTS "Users can update own profile" ON users;
CREATE POLICY "Users can update own profile"
    ON users FOR UPDATE
    USING (id = (SELECT NULLIF(current_setting('request.jwt.claim.sub', true), '')::bigint));

DROP POLICY IF EXISTS "Public can view active packages" ON travel_packages;
CREATE POLICY "Public can view active packages"
    ON travel_packages FOR SELECT
    USING (is_active = TRUE AND is_deleted = FALSE AND status = 'active');

DROP POLICY IF EXISTS "Operators manage owned packages" ON travel_packages;
CREATE POLICY "Operators manage owned packages"
    ON travel_packages FOR ALL
    USING (operator_id IN (SELECT id FROM travel_companies WHERE user_id = (SELECT NULLIF(current_setting('request.jwt.claim.sub', true), '')::bigint)));

DROP POLICY IF EXISTS "Public can view approved companies" ON travel_companies;
CREATE POLICY "Public can view approved companies"
    ON travel_companies FOR SELECT
    USING (status = 'approved');

DROP POLICY IF EXISTS "Operators can view and update own company" ON travel_companies;
CREATE POLICY "Operators can view and update own company"
    ON travel_companies FOR ALL
    USING (user_id = (SELECT NULLIF(current_setting('request.jwt.claim.sub', true), '')::bigint));

DROP POLICY IF EXISTS "Users manage own interests" ON interests;
CREATE POLICY "Users manage own interests"
    ON interests FOR ALL
    USING (traveler_id = (SELECT NULLIF(current_setting('request.jwt.claim.sub', true), '')::bigint));

DROP POLICY IF EXISTS "Travelers view own enquiries" ON enquiries;
CREATE POLICY "Travelers view own enquiries"
    ON enquiries FOR ALL
    USING (traveler_id = (SELECT NULLIF(current_setting('request.jwt.claim.sub', true), '')::bigint));

DROP POLICY IF EXISTS "Operators view company enquiries" ON enquiries;
CREATE POLICY "Operators view company enquiries"
    ON enquiries FOR SELECT
    USING (company_id IN (SELECT id FROM travel_companies WHERE user_id = (SELECT NULLIF(current_setting('request.jwt.claim.sub', true), '')::bigint)));

DROP POLICY IF EXISTS "Travelers view own bookings" ON bookings;
CREATE POLICY "Travelers view own bookings"
    ON bookings FOR SELECT
    USING (traveler_id = (SELECT NULLIF(current_setting('request.jwt.claim.sub', true), '')::bigint));

DROP POLICY IF EXISTS "Operators view company bookings" ON bookings;
CREATE POLICY "Operators view company bookings"
    ON bookings FOR SELECT
    USING (company_id IN (SELECT id FROM travel_companies WHERE user_id = (SELECT NULLIF(current_setting('request.jwt.claim.sub', true), '')::bigint)));

DROP POLICY IF EXISTS "Users access own notifications" ON notifications;
CREATE POLICY "Users access own notifications"
    ON notifications FOR ALL
    USING (user_id = (SELECT NULLIF(current_setting('request.jwt.claim.sub', true), '')::bigint));

COMMIT;
