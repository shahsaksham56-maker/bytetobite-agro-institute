-- ═══════════════════════════════════════════════════════════════
-- ByteToBite — Institutional Schema
-- PostgreSQL 14+  ·  PostGIS 3+
-- Auto-loaded by docker-compose on first boot.
-- ═══════════════════════════════════════════════════════════════

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ───────────────────────────────────────────────
-- INSTITUTES
-- ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS institutes (
    id                BIGSERIAL PRIMARY KEY,
    code              TEXT UNIQUE NOT NULL,
    name              TEXT NOT NULL,
    type              TEXT NOT NULL DEFAULT 'university',
    established_year  INTEGER,
    aishe_code        TEXT,
    recognition       TEXT,
    naac_grade        TEXT,
    city              TEXT,
    state             TEXT,
    pin_code          TEXT,
    student_count     INTEGER,
    mess_name         TEXT,
    admin_designation TEXT,
    admin_name        TEXT,
    admin_email       TEXT,
    admin_mobile      TEXT,
    password_hash     TEXT,
    location          GEOGRAPHY(POINT, 4326),
    verified          BOOLEAN NOT NULL DEFAULT FALSE,
    verified_at       TIMESTAMPTZ,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_institutes_code     ON institutes(code);
CREATE INDEX IF NOT EXISTS idx_institutes_aishe    ON institutes(aishe_code);
CREATE INDEX IF NOT EXISTS idx_institutes_city     ON institutes(city);
CREATE INDEX IF NOT EXISTS idx_institutes_location ON institutes USING GIST(location);

-- ───────────────────────────────────────────────
-- SESSIONS
-- ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sessions (
    id            TEXT PRIMARY KEY,
    institute_id  BIGINT NOT NULL REFERENCES institutes(id) ON DELETE CASCADE,
    code          TEXT,
    name          TEXT,
    role          TEXT,
    jwt_hash      TEXT,
    expires_at    TIMESTAMPTZ NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sessions_institute ON sessions(institute_id);
CREATE INDEX IF NOT EXISTS idx_sessions_expires   ON sessions(expires_at);

-- ───────────────────────────────────────────────
-- OTP REQUESTS
-- ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS otp_requests (
    id          TEXT PRIMARY KEY,
    mobile      TEXT NOT NULL,
    code_hash   TEXT NOT NULL,
    verified    BOOLEAN NOT NULL DEFAULT FALSE,
    expires_at  TIMESTAMPTZ NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_otp_mobile  ON otp_requests(mobile);
CREATE INDEX IF NOT EXISTS idx_otp_expires ON otp_requests(expires_at);

-- ───────────────────────────────────────────────
-- NGOS
-- ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ngos (
    id           BIGSERIAL PRIMARY KEY,
    name         TEXT NOT NULL,
    contact      TEXT,
    phone        TEXT,
    email        TEXT,
    city         TEXT,
    address      TEXT,
    capacity     INTEGER NOT NULL DEFAULT 0,
    base_eta_min INTEGER NOT NULL DEFAULT 15,
    distance_km  NUMERIC(8,2),
    location     GEOGRAPHY(POINT, 4326),
    verified     BOOLEAN NOT NULL DEFAULT TRUE,
    verified_at  TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ngos_city     ON ngos(city);
CREATE INDEX IF NOT EXISTS idx_ngos_verified ON ngos(verified);
CREATE INDEX IF NOT EXISTS idx_ngos_location ON ngos USING GIST(location);

-- ───────────────────────────────────────────────
-- MEAL PLANS (Node 01)
-- ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS meal_plans (
    id                BIGSERIAL PRIMARY KEY,
    institute_id      BIGINT NOT NULL REFERENCES institutes(id) ON DELETE CASCADE,
    plan_date         DATE NOT NULL,
    meal_slot         TEXT NOT NULL,
    predicted_demand  INTEGER,
    prepared_count    INTEGER,
    expected_waste_kg NUMERIC(10,2),
    waste_risk_score  SMALLINT,
    variance_pct      NUMERIC(6,2),
    menu_items        JSONB NOT NULL DEFAULT '[]'::jsonb,
    weather_snapshot  JSONB,
    weather_used      TEXT,
    menu_category     TEXT,
    agent_suggested   BOOLEAN DEFAULT FALSE,
    agent_headcount   INTEGER,
    agent_factors     JSONB,
    status            TEXT NOT NULL DEFAULT 'DRAFT'
                      CHECK (status IN ('DRAFT','PUBLISHED','IN_SERVICE','COMPLETED','CANCELLED')),
    dispatch_ready    BOOLEAN NOT NULL DEFAULT FALSE,
    dispatch_ready_at TIMESTAMPTZ,
    created_by        TEXT,
    published_at      TIMESTAMPTZ,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (institute_id, plan_date, meal_slot)
);

CREATE INDEX IF NOT EXISTS idx_plans_institute    ON meal_plans(institute_id);
CREATE INDEX IF NOT EXISTS idx_plans_date         ON meal_plans(plan_date);
CREATE INDEX IF NOT EXISTS idx_plans_status       ON meal_plans(status);
CREATE INDEX IF NOT EXISTS idx_plans_dispatch_rdy ON meal_plans(dispatch_ready)
                                                  WHERE dispatch_ready = TRUE;

-- ───────────────────────────────────────────────
-- MEAL PREPS (Node 02)
-- ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS meal_preps (
    id                    BIGSERIAL PRIMARY KEY,
    institute_id          BIGINT NOT NULL REFERENCES institutes(id) ON DELETE CASCADE,
    plan_id               TEXT,
    prepared_count        INTEGER NOT NULL,
    agent_suggested_count INTEGER,
    agent_factors         JSONB,
    variance_pct          NUMERIC(6,2),
    notes                 TEXT,
    chef_verified_at      TIMESTAMPTZ,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_preps_institute ON meal_preps(institute_id);
CREATE INDEX IF NOT EXISTS idx_preps_plan      ON meal_preps(plan_id);

-- ───────────────────────────────────────────────
-- PLATE TALLIES (Node 03)
-- ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS plate_tallies (
    id            BIGSERIAL PRIMARY KEY,
    prep_id       TEXT,
    institute_id  BIGINT NOT NULL REFERENCES institutes(id) ON DELETE CASCADE,
    served_count  INTEGER NOT NULL DEFAULT 0,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tallies_prep      ON plate_tallies(prep_id);
CREATE INDEX IF NOT EXISTS idx_tallies_institute ON plate_tallies(institute_id);

-- ───────────────────────────────────────────────
-- THERMAL CHECKS (Node 04)
-- ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS thermal_checks (
    id                  BIGSERIAL PRIMARY KEY,
    prep_id             TEXT,
    institute_id        BIGINT REFERENCES institutes(id) ON DELETE CASCADE,
    temp_c              NUMERIC(5,2),
    state               TEXT,
    hold_minutes        NUMERIC(8,2),
    remaining_minutes   NUMERIC(8,2),
    freshness_index     NUMERIC(5,3),
    ready_for_dispatch  BOOLEAN NOT NULL DEFAULT FALSE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_thermal_prep      ON thermal_checks(prep_id);
CREATE INDEX IF NOT EXISTS idx_thermal_institute ON thermal_checks(institute_id);
CREATE INDEX IF NOT EXISTS idx_thermal_ready     ON thermal_checks(ready_for_dispatch)
                                                  WHERE ready_for_dispatch = TRUE;

-- ───────────────────────────────────────────────
-- NGO DISPATCHES (Node 05)
-- ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ngo_dispatches (
    id                 BIGSERIAL PRIMARY KEY,
    dispatch_code      TEXT UNIQUE,
    institute_id       BIGINT NOT NULL REFERENCES institutes(id) ON DELETE CASCADE,
    prep_id            TEXT,
    plan_id            TEXT,
    ngo_id             BIGINT REFERENCES ngos(id) ON DELETE SET NULL,
    ngo_name           TEXT,
    ngo_distance_km    NUMERIC(8,2),
    ngo_contact        TEXT,
    ngo_phone          TEXT,
    ngo_email          TEXT,
    meals_sent         INTEGER NOT NULL,
    eta_minutes        INTEGER,
    category           TEXT,
    temp_c             NUMERIC(5,2),
    custody_officer    TEXT,
    verified_at        TIMESTAMPTZ,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_disp_institute ON ngo_dispatches(institute_id);
CREATE INDEX IF NOT EXISTS idx_disp_prep      ON ngo_dispatches(prep_id);
CREATE INDEX IF NOT EXISTS idx_disp_plan      ON ngo_dispatches(plan_id);
CREATE INDEX IF NOT EXISTS idx_disp_ngo       ON ngo_dispatches(ngo_id);
CREATE INDEX IF NOT EXISTS idx_disp_created   ON ngo_dispatches(created_at DESC);

-- ───────────────────────────────────────────────
-- ESG LEDGER (Node 06)
-- ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS esg_ledger (
    id             BIGSERIAL PRIMARY KEY,
    institute_id   BIGINT NOT NULL REFERENCES institutes(id) ON DELETE CASCADE,
    dispatch_id    TEXT,
    plan_id        TEXT,
    meals_rescued  INTEGER NOT NULL DEFAULT 0,
    co2e_kg        NUMERIC(10,3) NOT NULL DEFAULT 0,
    water_l        INTEGER NOT NULL DEFAULT 0,
    cost_inr       NUMERIC(12,2) NOT NULL DEFAULT 0,
    manual_entry   BOOLEAN NOT NULL DEFAULT FALSE,
    recipient      TEXT,
    notes          TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_esg_institute ON esg_ledger(institute_id);
CREATE INDEX IF NOT EXISTS idx_esg_dispatch  ON esg_ledger(dispatch_id);
CREATE INDEX IF NOT EXISTS idx_esg_plan      ON esg_ledger(plan_id);
CREATE INDEX IF NOT EXISTS idx_esg_created   ON esg_ledger(created_at DESC);

-- ───────────────────────────────────────────────
-- TRIGGER: auto-update updated_at
-- ───────────────────────────────────────────────
CREATE OR REPLACE FUNCTION touch_updated_at() RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$
DECLARE
    t text;
BEGIN
    FOR t IN
        SELECT unnest(ARRAY[
            'institutes',
            'ngos',
            'meal_plans',
            'meal_preps',
            'plate_tallies'
        ])
    LOOP
        EXECUTE format(
            'DROP TRIGGER IF EXISTS trg_%1$s_updated ON %1$s;
             CREATE TRIGGER trg_%1$s_updated
             BEFORE UPDATE ON %1$s
             FOR EACH ROW EXECUTE FUNCTION touch_updated_at();',
            t
        );
    END LOOP;
END $$;

-- ───────────────────────────────────────────────
-- USEFUL VIEWS
-- ───────────────────────────────────────────────
CREATE OR REPLACE VIEW active_plans AS
SELECT p.*,
       i.name        AS institute_name,
       i.mess_name   AS mess_name,
       i.city        AS city
FROM meal_plans p
JOIN institutes i ON i.id = p.institute_id
WHERE p.status IN ('PUBLISHED', 'IN_SERVICE');

CREATE OR REPLACE VIEW dispatch_impact AS
SELECT d.id                AS dispatch_id,
       d.dispatch_code,
       d.institute_id,
       d.ngo_name,
       d.meals_sent,
       d.created_at,
       COALESCE(e.co2e_kg,    d.meals_sent * 1.05) AS co2e_kg,
       COALESCE(e.water_l,    d.meals_sent * 180)  AS water_l,
       COALESCE(e.cost_inr,   d.meals_sent * 45)   AS cost_inr
FROM ngo_dispatches d
LEFT JOIN esg_ledger e ON e.dispatch_id = d.id::text;

-- ───────────────────────────────────────────────
-- SEED DEMO INSTITUTE
-- (Password hash is intentionally a placeholder —
--  use institutional.html?dev=1 to auto-create a fresh one.)
-- ───────────────────────────────────────────────
INSERT INTO institutes (
    code, name, type, established_year, aishe_code, recognition, naac_grade,
    city, state, pin_code, student_count, mess_name,
    admin_designation, admin_name, admin_email, admin_mobile,
    location, verified, verified_at
)
VALUES (
    'ITER-BBSR-DEMO',
    'ITER SOA University',
    'university',
    2006,
    'C-45678',
    'multiple',
    'A',
    'Bhubaneswar',
    'Odisha',
    '751024',
    4500,
    'Central Mess ITER',
    'registrar',
    'Campus Registrar',
    'registrar@iter.soa.ac.in',
    '9876543210',
    ST_SetSRID(ST_MakePoint(85.8245, 20.2961), 4326)::geography,
    TRUE,
    NOW()
)
ON CONFLICT (code) DO NOTHING;

-- ───────────────────────────────────────────────
-- SEED DEMO NGOs
-- ───────────────────────────────────────────────
INSERT INTO ngos (name, contact, phone, email, city, address, capacity,
                  base_eta_min, distance_km, location, verified, verified_at)
VALUES
  ('Aahar Center Khandagiri',
   'Rajesh Mohapatra', '+91 94370 12345', 'aahar.khandagiri@odisha.gov.in',
   'Bhubaneswar', 'Khandagiri, Bhubaneswar', 250, 9, 2.8,
   ST_SetSRID(ST_MakePoint(85.7895, 20.2612), 4326)::geography,
   TRUE, NOW()),

  ('Mission Ashra Shelter',
   'Dr. Sunita Nayak', '+91 98610 54321', 'dispatch@missionashra.org',
   'Bhubaneswar', 'Patia, Bhubaneswar', 180, 14, 4.6,
   ST_SetSRID(ST_MakePoint(85.7920, 20.2310), 4326)::geography,
   TRUE, NOW()),

  ('Jeevan Jyoti Destitute Home',
   'Sister Teresa', '+91 94380 98765', 'contact@jeevanjyoti-odisha.org',
   'Bhubaneswar', 'Chandrasekharpur, Bhubaneswar', 120, 22, 8.2,
   ST_SetSRID(ST_MakePoint(85.8150, 20.2850), 4326)::geography,
   TRUE, NOW()),

  ('Bhubaneswar Urban Food Bank',
   'Alok Jena', '+91 99370 11223', 'ops@bbsrfoodbank.org',
   'Bhubaneswar', 'Rasulgarh, Bhubaneswar', 500, 36, 13.5,
   ST_SetSRID(ST_MakePoint(85.8450, 20.2980), 4326)::geography,
   TRUE, NOW())
ON CONFLICT DO NOTHING;