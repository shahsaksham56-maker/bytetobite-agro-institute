-- ═══════════════════════════════════════════════════════════════
-- ByteToBite — Agro Schema
-- PostgreSQL 14+  ·  PostGIS 3+
-- Auto-loaded by docker-compose on first boot.
-- ═══════════════════════════════════════════════════════════════

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ───────────────────────────────────────────────
-- PROFILES
-- ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS profiles (
  id                 BIGSERIAL PRIMARY KEY,
  role               TEXT NOT NULL,
  display_name       TEXT NOT NULL,
  mobile             TEXT NOT NULL,
  email              TEXT,
  pincode            TEXT,
  location           GEOGRAPHY(POINT, 4326),
  aadhaar_hash       TEXT,
  farmer_id          TEXT,
  land_record_no     TEXT,
  company_name       TEXT,
  gst_number         TEXT,
  udyam_number       TEXT,
  signatory_name     TEXT,
  driver_license     TEXT,
  vehicle_type       TEXT,
  capacity_kg        NUMERIC(10,2),
  fleet_size         INTEGER,
  darpan_id          TEXT,
  species_under_care TEXT[],
  animal_count       INTEGER,
  zoo_license        TEXT,
  facility_name      TEXT,
  cpcb_id            TEXT,
  badge_id           TEXT,
  agency             TEXT,
  shop_name          TEXT,
  shop_verified      BOOLEAN DEFAULT FALSE,
  kyc_verified       BOOLEAN DEFAULT FALSE,
  kyc_verified_at    TIMESTAMPTZ,
  meta               JSONB DEFAULT '{}'::jsonb,
  created_at         TIMESTAMPTZ DEFAULT NOW(),
  updated_at         TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_profiles_role     ON profiles (role);
CREATE INDEX IF NOT EXISTS idx_profiles_mobile   ON profiles (mobile);
CREATE INDEX IF NOT EXISTS idx_profiles_location ON profiles USING GIST (location);

-- ───────────────────────────────────────────────
-- BUYERS
-- ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS buyers (
  id                  BIGSERIAL PRIMARY KEY,
  profile_id          BIGINT REFERENCES profiles(id) ON DELETE SET NULL,
  role                TEXT NOT NULL DEFAULT 'industry',
  name                TEXT NOT NULL,
  contact_mobile      TEXT,
  contact_email       TEXT,
  location            GEOGRAPHY(POINT, 4326) NOT NULL,
  address             TEXT,
  accepted_categories TEXT[] NOT NULL DEFAULT '{}',
  weekly_capacity_kg  NUMERIC(12,2),
  max_rate_per_kg     NUMERIC(8,2),
  max_moisture_pct    NUMERIC(5,2),
  max_radius_km       NUMERIC(6,2) DEFAULT 50,
  demand_note         TEXT,
  verified            BOOLEAN DEFAULT FALSE,
  created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_buyers_role       ON buyers (role);
CREATE INDEX IF NOT EXISTS idx_buyers_location   ON buyers USING GIST (location);
CREATE INDEX IF NOT EXISTS idx_buyers_categories ON buyers USING GIN (accepted_categories);

-- ───────────────────────────────────────────────
-- LISTINGS
-- ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS listings (
  id                   BIGSERIAL PRIMARY KEY,
  lot_code             TEXT NOT NULL UNIQUE,
  farmer_id            BIGINT REFERENCES profiles(id) ON DELETE SET NULL,
  category             TEXT NOT NULL,
  other_text           TEXT,
  sub_type             TEXT,
  mass_kg              NUMERIC(10,2) NOT NULL,
  moisture_pct         NUMERIC(5,2),
  rate_per_kg          NUMERIC(8,2) NOT NULL,
  total_value          NUMERIC(12,2) GENERATED ALWAYS AS (mass_kg * rate_per_kg) STORED,
  location             GEOGRAPHY(POINT, 4326) NOT NULL,
  origin_label         TEXT,
  photo_url            TEXT,
  ocr_raw_text         TEXT,
  ocr_confidence       NUMERIC(5,2),
  status               TEXT NOT NULL DEFAULT 'OPEN'
                       CHECK (status IN (
                         'OPEN','MATCHED','ESCROW LOCKED','IN_TRANSIT','DELIVERED',
                         'DIVERTED','DIGESTING','CANCELLED','COMPOST_FINISHED'
                       )),
  matched_buyer_id     BIGINT REFERENCES buyers(id) ON DELETE SET NULL,
  matched_at           TIMESTAMPTZ,
  transporter          TEXT,
  trip_status          TEXT,
  digester_tank        TEXT,
  digestion_started_at TIMESTAMPTZ,
  open_for_barter      BOOLEAN DEFAULT FALSE,
  wanted_category      TEXT,
  wanted_mass_kg       NUMERIC(10,2),
  divert_reason        TEXT,
  diverted_at          TIMESTAMPTZ,
  transport_mode       TEXT CHECK (transport_mode IN ('fleet','self')),
  vehicle_no           TEXT,
  driver_info          TEXT,
  payment_method       TEXT CHECK (payment_method IN ('neft','upi','credit','razorpay')),
  pickup_date          DATE,
  temp_qc_required     BOOLEAN DEFAULT FALSE,
  created_at           TIMESTAMPTZ DEFAULT NOW(),
  updated_at           TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_listings_location   ON listings USING GIST (location);
CREATE INDEX IF NOT EXISTS idx_listings_status     ON listings (status);
CREATE INDEX IF NOT EXISTS idx_listings_category   ON listings (category);
CREATE INDEX IF NOT EXISTS idx_listings_created_at ON listings (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_listings_barter     ON listings (open_for_barter)
                                                    WHERE open_for_barter = TRUE;

-- ───────────────────────────────────────────────
-- ESCROW LEDGER (append-only)
-- ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS escrow_ledger (
  id           BIGSERIAL PRIMARY KEY,
  listing_id   BIGINT REFERENCES listings(id) ON DELETE CASCADE,
  milestone    TEXT NOT NULL,
  amount       NUMERIC(12,2) NOT NULL,
  currency     TEXT DEFAULT 'INR',
  released_by  TEXT,
  released_at  TIMESTAMPTZ DEFAULT NOW(),
  notes        TEXT,
  meta         JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_escrow_listing   ON escrow_ledger (listing_id);
CREATE INDEX IF NOT EXISTS idx_escrow_milestone ON escrow_ledger (milestone);
CREATE INDEX IF NOT EXISTS idx_escrow_released  ON escrow_ledger (released_at DESC);

-- ───────────────────────────────────────────────
-- BARTER PROPOSALS
-- ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS barter_proposals (
  id                 BIGSERIAL PRIMARY KEY,
  from_profile_id    BIGINT REFERENCES profiles(id) ON DELETE SET NULL,
  target_listing_id  BIGINT REFERENCES listings(id) ON DELETE CASCADE,
  offering_category  TEXT NOT NULL,
  offering_mass_kg   NUMERIC(10,2) NOT NULL,
  offering_moisture  NUMERIC(5,2),
  note               TEXT,
  status             TEXT DEFAULT 'PENDING'
                     CHECK (status IN ('PENDING','ACCEPTED','DECLINED','COMPLETED')),
  created_at         TIMESTAMPTZ DEFAULT NOW(),
  responded_at       TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_barter_target ON barter_proposals (target_listing_id);
CREATE INDEX IF NOT EXISTS idx_barter_from   ON barter_proposals (from_profile_id);

-- ───────────────────────────────────────────────
-- COMPOST BATCHES
-- ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS compost_batches (
  id                 BIGSERIAL PRIMARY KEY,
  batch_code         TEXT NOT NULL UNIQUE,
  source_listing_id  BIGINT REFERENCES listings(id) ON DELETE SET NULL,
  tank_id            TEXT,
  input_mass_kg      NUMERIC(10,2) NOT NULL,
  output_mass_kg     NUMERIC(10,2),
  biomethane_m3      NUMERIC(10,2),
  carbon_avoided_t   NUMERIC(10,4),
  compost_grade      TEXT CHECK (compost_grade IN ('A','B','C')),
  retention_days     INTEGER,
  sha256_hash        TEXT,
  started_at         TIMESTAMPTZ DEFAULT NOW(),
  completed_at       TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_compost_batch_code ON compost_batches (batch_code);

-- ───────────────────────────────────────────────
-- PRODUCTS (Eco-Store)
-- ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS products (
  id                     BIGSERIAL PRIMARY KEY,
  product_code           TEXT NOT NULL UNIQUE,
  seller_profile_id      BIGINT REFERENCES profiles(id) ON DELETE SET NULL,
  seller_name            TEXT,
  seller_verified        BOOLEAN DEFAULT FALSE,
  title                  TEXT NOT NULL,
  description            TEXT,
  category               TEXT NOT NULL,
  price                  NUMERIC(10,2) NOT NULL,
  mrp                    NUMERIC(10,2),
  stock_quantity         INTEGER NOT NULL DEFAULT 0,
  image_url              TEXT,
  rating                 NUMERIC(3,2) DEFAULT 0,
  reviews                INTEGER DEFAULT 0,
  bestseller             BOOLEAN DEFAULT FALSE,
  carbon_saved_kgco2e    NUMERIC(10,2),
  raw_biomass_used_kg    NUMERIC(10,2),
  raw_waste_listing_code TEXT,
  source_mandi           TEXT,
  origin_location        GEOGRAPHY(POINT, 4326),
  artisan_name           TEXT,
  artisan_location       GEOGRAPHY(POINT, 4326),
  created_at             TIMESTAMPTZ DEFAULT NOW(),
  updated_at             TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_products_seller   ON products (seller_profile_id);
CREATE INDEX IF NOT EXISTS idx_products_category ON products (category);
CREATE INDEX IF NOT EXISTS idx_products_origin   ON products USING GIST (origin_location);
CREATE INDEX IF NOT EXISTS idx_products_artisan  ON products USING GIST (artisan_location);
CREATE INDEX IF NOT EXISTS idx_products_created  ON products (created_at DESC);

-- ───────────────────────────────────────────────
-- STORE USERS
-- ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS store_users (
  id                BIGSERIAL PRIMARY KEY,
  profile_id        BIGINT REFERENCES profiles(id) ON DELETE SET NULL,
  role              TEXT NOT NULL CHECK (role IN ('customer','seller')),
  name              TEXT NOT NULL,
  mobile            TEXT NOT NULL,
  email             TEXT,
  pincode           TEXT,
  shop_name         TEXT,
  gst_number        TEXT,
  seller_verified   BOOLEAN DEFAULT FALSE,
  created_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_store_users_role   ON store_users (role);
CREATE INDEX IF NOT EXISTS idx_store_users_mobile ON store_users (mobile);

-- ───────────────────────────────────────────────
-- STORE ORDERS
-- ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS store_orders (
  id                    BIGSERIAL PRIMARY KEY,
  order_code            TEXT NOT NULL UNIQUE,
  product_id            BIGINT REFERENCES products(id) ON DELETE SET NULL,
  product_title         TEXT,
  product_image         TEXT,
  seller_profile_id     BIGINT REFERENCES profiles(id) ON DELETE SET NULL,
  seller_name           TEXT,
  customer_profile_id   BIGINT REFERENCES profiles(id) ON DELETE SET NULL,
  customer_name         TEXT,
  qty                   INTEGER NOT NULL,
  unit_price            NUMERIC(10,2) NOT NULL,
  total                 NUMERIC(12,2) NOT NULL,
  status                TEXT DEFAULT 'CONFIRMED'
                        CHECK (status IN ('CONFIRMED','PACKED','SHIPPED','DELIVERED','CANCELLED')),
  created_at            TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_store_orders_seller   ON store_orders (seller_profile_id);
CREATE INDEX IF NOT EXISTS idx_store_orders_customer ON store_orders (customer_profile_id);
CREATE INDEX IF NOT EXISTS idx_store_orders_status   ON store_orders (status);
CREATE INDEX IF NOT EXISTS idx_store_orders_created  ON store_orders (created_at DESC);

-- ───────────────────────────────────────────────
-- STORE CART
-- ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS store_cart (
  id                BIGSERIAL PRIMARY KEY,
  user_profile_id   BIGINT REFERENCES profiles(id) ON DELETE CASCADE,
  product_id        BIGINT REFERENCES products(id) ON DELETE CASCADE,
  qty               INTEGER NOT NULL DEFAULT 1,
  added_at          TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE (user_profile_id, product_id)
);

-- ───────────────────────────────────────────────
-- STORE WISHLIST
-- ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS store_wishlist (
  id                BIGSERIAL PRIMARY KEY,
  user_profile_id   BIGINT REFERENCES profiles(id) ON DELETE CASCADE,
  product_id        BIGINT REFERENCES products(id) ON DELETE CASCADE,
  added_at          TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE (user_profile_id, product_id)
);

-- ───────────────────────────────────────────────
-- AUDIT LOG
-- ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS audit_log (
  id           BIGSERIAL PRIMARY KEY,
  actor_type   TEXT,
  actor_id     BIGINT,
  action       TEXT NOT NULL,
  entity_type  TEXT,
  entity_id    BIGINT,
  payload      JSONB,
  created_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log (created_at DESC);

-- ───────────────────────────────────────────────
-- USEFUL VIEWS
-- ───────────────────────────────────────────────
CREATE OR REPLACE VIEW open_listings_with_distance AS
SELECT l.*,
       b.id   AS buyer_id,
       b.name AS buyer_name,
       ST_Distance(b.location, l.location) / 1000 AS distance_km
FROM listings l
LEFT JOIN LATERAL (
  SELECT * FROM buyers b2
  WHERE b2.verified = TRUE
    AND l.category = ANY(b2.accepted_categories)
    AND ST_DWithin(b2.location, l.location, 50000)
  ORDER BY b2.location <-> l.location
  LIMIT 1
) b ON TRUE
WHERE l.status = 'OPEN';

CREATE OR REPLACE VIEW listing_escrow_summary AS
SELECT l.id           AS listing_id,
       l.lot_code,
       l.status,
       l.total_value,
       l.transport_mode,
       l.payment_method,
       COALESCE(SUM(CASE WHEN e.milestone = 'ADVANCE_30' THEN e.amount END), 0) AS advance_paid,
       COALESCE(SUM(CASE WHEN e.milestone = 'BALANCE_70' THEN e.amount END), 0) AS balance_paid,
       COALESCE(SUM(CASE WHEN e.milestone = 'CARBON_CREDIT' THEN e.amount END), 0) AS carbon_credited,
       MAX(e.released_at) AS last_activity
FROM listings l
LEFT JOIN escrow_ledger e ON e.listing_id = l.id
GROUP BY l.id, l.lot_code, l.status, l.total_value, l.transport_mode, l.payment_method;

-- ───────────────────────────────────────────────
-- SEED BUYERS
-- ───────────────────────────────────────────────
INSERT INTO buyers (role, name, location, accepted_categories, weekly_capacity_kg, verified, address) VALUES
  ('industry',  'Punjab Bio-Pectin Extraction Ltd',
   ST_SetSRID(ST_MakePoint(74.0333, 29.8963), 4326)::geography,
   ARRAY['CITRUS_POMACE','PLANT_FIBER']::text[], 40000, TRUE, 'Abohar Road, Punjab'),

  ('industry',  'Malwa Mycelium Packaging Unit',
   ST_SetSRID(ST_MakePoint(74.3316, 30.2597), 4326)::geography,
   ARRAY['MUSHROOM_SUBSTRATE','BIO_MASS']::text[], 18000, TRUE, 'Malwa, Punjab'),

  ('industry',  'Sriganganagar Composting Co.',
   ST_SetSRID(ST_MakePoint(73.8800, 29.9200), 4326)::geography,
   ARRAY['BIO_MASS','COOKED_SURPLUS']::text[], 25000, TRUE, 'Sriganganagar, Rajasthan'),

  ('sanctuary', 'Wildlife SOS India',
   ST_SetSRID(ST_MakePoint(77.2090, 28.6139), 4326)::geography,
   ARRAY['CROP_RESIDUE','VEGETABLE_WASTE','FRUIT_POMACE','COCONUT_HUSK','PLANT_FIBER']::text[],
   12000, TRUE, 'Delhi NCR'),

  ('zoo',       'National Zoological Park',
   ST_SetSRID(ST_MakePoint(77.2455, 28.6097), 4326)::geography,
   ARRAY['CROP_RESIDUE','VEGETABLE_WASTE','FRUIT_POMACE','SPOILED_GRAIN']::text[],
   30000, TRUE, 'Delhi')
ON CONFLICT DO NOTHING;

-- ───────────────────────────────────────────────
-- SEED DEMO FARMER PROFILE
-- ───────────────────────────────────────────────
INSERT INTO profiles (role, display_name, mobile, location, pincode,
                      farmer_id, land_record_no, kyc_verified)
VALUES (
  'farmer', 'Demo Kisan', '9876543210',
  ST_SetSRID(ST_MakePoint(74.1994, 30.1453), 4326)::geography,
  '152116', 'PMK-DEMO-001', 'LR-DEMO-001', TRUE
)
ON CONFLICT DO NOTHING;