"""ByteToBite — Complete FastAPI backend for Agro + Institutional grids.
Run:  uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""
import os
import json
from datetime import datetime, date
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from db import get_pool, close_pool, fetch, fetchrow, fetchval, execute, serialize_row
from ws import agro_hub, institutional_hub
from otp import generate_otp, hash_otp
from payment import create_order, verify_signature
from agents import (
    forecast_agent, prep_agent, waste_risk_agent, suggest_menu,
    anomaly_agent, thermal_agent, dispatch_agent, savings_agent,
)
from models import (
    ListingIn, BuyerIn, ProfileIn, EscrowIn, BarterIn, ProductIn,
    StoreUserIn, StoreOrderIn,
    InstituteIn, SessionIn, NGOIn, MealPlanIn, MealPrepIn, TallyIn,
    ThermalIn, DispatchIn, ESGIn, PaymentOrderIn, PaymentVerifyIn,
)


# ─────────────────────────────────────────────
# LIFESPAN
# ─────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    await get_pool()
    yield
    await close_pool()


app = FastAPI(title="ByteToBite API", version="2.0.0", lifespan=lifespan)

raw_origins = os.getenv("ALLOWED_ORIGINS", "*").strip()
if raw_origins == "*":
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=".*",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in raw_origins.split(",") if o.strip()],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def _now_ms() -> int:
    return int(datetime.utcnow().timestamp() * 1000)


def _gen_id(prefix: str) -> str:
    return f"{prefix}-{datetime.utcnow().strftime('%y%m%d%H%M%S')}-{os.urandom(2).hex().upper()}"


def _geog_point(lat: float, lng: float) -> str:
    return f"SRID=4326;POINT({lng} {lat})"


def _listing_to_wire(r: Optional[dict]) -> Optional[dict]:
    if not r:
        return None
    s = serialize_row(r)
    return {
        "id": s.get("lot_code") or s.get("id"),
        "lot_code": s.get("lot_code"),
        "category": s.get("category"),
        "otherText": s.get("other_text"),
        "subType": s.get("sub_type"),
        "massKg": float(s.get("mass_kg") or 0),
        "moisture": float(s.get("moisture_pct") or 0),
        "rate": float(s.get("rate_per_kg") or 0),
        "totalValue": float(s.get("total_value") or 0),
        "lat": s.get("lat"),
        "lng": s.get("lng"),
        "origin": s.get("origin_label"),
        "photo_url": s.get("photo_url"),
        "ocr_raw_text": s.get("ocr_raw_text"),
        "ocr_confidence": s.get("ocr_confidence"),
        "status": s.get("status"),
        "matchedBuyer": s.get("transporter"),
        "transporter": s.get("transporter"),
        "tripStatus": s.get("trip_status"),
        "transportMode": s.get("transport_mode"),
        "vehicleNo": s.get("vehicle_no"),
        "driverInfo": s.get("driver_info"),
        "paymentMethod": s.get("payment_method"),
        "pickupDate": str(s.get("pickup_date") or ""),
        "tempQC": s.get("temp_qc_required"),
        "openForBarter": s.get("open_for_barter"),
        "wantedCategory": s.get("wanted_category"),
        "wantedMassKg": float(s.get("wanted_mass_kg") or 0),
        "divertReason": s.get("divert_reason"),
        "digesterTank": s.get("digester_tank"),
        "digestionStartedAt": s.get("digestion_started_at"),
        "createdAt": s.get("created_at"),
        "updatedAt": s.get("updated_at"),
    }


def _plan_to_wire(r: Optional[dict]) -> Optional[dict]:
    if not r:
        return None
    s = serialize_row(r)
    return {
        "id": s.get("id"),
        "institute_id": s.get("institute_id"),
        "date": str(s.get("plan_date") or ""),
        "plan_date": str(s.get("plan_date") or ""),
        "meal_slot": s.get("meal_slot"),
        "predicted_demand": s.get("predicted_demand"),
        "prepared_count": s.get("prepared_count"),
        "expected_waste_kg": float(s.get("expected_waste_kg") or 0),
        "waste_risk_score": s.get("waste_risk_score"),
        "variance_pct": float(s.get("variance_pct") or 0),
        "menu_items": s.get("menu_items") or [],
        "weather_snapshot": s.get("weather_snapshot"),
        "agent_suggested": s.get("agent_suggested"),
        "agent_headcount": s.get("agent_headcount"),
        "agent_factors": s.get("agent_factors") or [],
        "status": s.get("status"),
        "dispatch_ready": s.get("dispatch_ready"),
        "dispatch_ready_at": s.get("dispatch_ready_at"),
        "published_at": s.get("published_at"),
        "created_at": s.get("created_at"),
        "updated_at": s.get("updated_at"),
    }


def _product_to_wire(r: Optional[dict]) -> Optional[dict]:
    if not r:
        return None
    s = serialize_row(r)
    return {
        "id": s.get("id"),
        "title": s.get("title"),
        "description": s.get("description"),
        "category": s.get("category"),
        "price": float(s.get("price") or 0),
        "mrp": float(s.get("mrp") or 0),
        "stockQuantity": s.get("stock_quantity") or 0,
        "image": s.get("image_url") or "",
        "rating": float(s.get("rating") or 0),
        "reviews": s.get("reviews") or 0,
        "bestseller": s.get("bestseller") or False,
        "carbonSavedKgCO2e": float(s.get("carbon_saved_kgco2e") or 0),
        "rawBiomassUsedKg": float(s.get("raw_biomass_used_kg") or 0),
        "rawWasteListingId": s.get("raw_waste_listing_code"),
        "sourceFarmerOrMandi": s.get("source_mandi"),
        "sellerName": s.get("seller_name"),
        "sellerVerified": s.get("seller_verified"),
        "createdAt": s.get("created_at"),
    }


# ═════════════════════════════════════════════
# HEALTH
# ═════════════════════════════════════════════
@app.get("/health")
async def health():
    try:
        await fetchval("SELECT 1")
        return {"ok": True, "db": "up", "ts": _now_ms()}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ═════════════════════════════════════════════
# AGRO — LISTINGS
# ═════════════════════════════════════════════
@app.post("/api/listings")
async def create_listing(payload: ListingIn):
    data = payload.model_dump()
    lot_code = data.get("lot_code") or _gen_id("LOT")
    cat = data["category"]
    mass = data.get("mass_kg") or data.get("massKg") or 0
    rate = data.get("rate_per_kg") or data.get("rate") or 0
    moisture = data.get("moisture_pct") or data.get("moisture")
    lat = data.get("lat") or (data.get("location") or {}).get("lat") or 30.1453
    lng = data.get("lng") or (data.get("location") or {}).get("lng") or 74.1994
    origin = data.get("origin_label") or data.get("origin") or "Farm"
    status = data.get("status") or "OPEN"

    existing = await fetchrow("SELECT id FROM listings WHERE lot_code = $1", lot_code)
    if existing:
        await execute(
            """UPDATE listings SET
                category=$2, mass_kg=$3, moisture_pct=$4, rate_per_kg=$5,
                location=ST_GeogFromText($6), origin_label=$7, status=$8,
                matched_at=CASE WHEN $8 IN ('ESCROW LOCKED','MATCHED') THEN NOW() ELSE matched_at END,
                transporter=$9, trip_status=$10, transport_mode=$11, vehicle_no=$12,
                driver_info=$13, payment_method=$14, pickup_date=$15, temp_qc_required=$16,
                open_for_barter=$17, wanted_category=$18, wanted_mass_kg=$19,
                divert_reason=$20, digester_tank=$21,
                digestion_started_at=TO_TIMESTAMP($22/1000.0),
                updated_at=NOW()
            WHERE lot_code=$1""",
            lot_code, cat, mass, moisture, rate, _geog_point(lat, lng), origin, status,
            data.get("transporter"), data.get("tripStatus"),
            data.get("transport_mode") or data.get("transportMode"),
            data.get("vehicleNo"), data.get("driverInfo"),
            data.get("payment_method") or data.get("paymentMethod"),
            data.get("pickupDate"),
            bool(data.get("temp_qc_required") or data.get("tempQC")),
            bool(data.get("openForBarter")),
            data.get("wantedCategory"), data.get("wantedMassKg"),
            data.get("divertReason"),
            data.get("digesterTank"),
            data.get("digestionStartedAt") or _now_ms(),
        )
    else:
        await execute(
            """INSERT INTO listings
                (lot_code, category, other_text, sub_type, mass_kg, moisture_pct,
                 rate_per_kg, location, origin_label, photo_url, ocr_raw_text,
                 ocr_confidence, status, matched_at, transporter, trip_status,
                 transport_mode, vehicle_no, driver_info, payment_method,
                 pickup_date, temp_qc_required, open_for_barter, wanted_category,
                 wanted_mass_kg, divert_reason, digester_tank, digestion_started_at)
               VALUES ($1,$2,$3,$4,$5,$6,$7,ST_GeogFromText($8),$9,$10,$11,$12,$13,
                       CASE WHEN $13 IN ('ESCROW LOCKED','MATCHED') THEN NOW() END,
                       $14,$15,$16,$17,$18,$19,$20,$21,$22,$23,$24,$25,$26,
                       TO_TIMESTAMP($27/1000.0))""",
            lot_code, cat, data.get("other_text"), data.get("sub_type"),
            mass, moisture, rate, _geog_point(lat, lng), origin,
            data.get("photo_url"), data.get("ocr_raw_text"), data.get("ocr_confidence"),
            status,
            data.get("transporter"), data.get("tripStatus"),
            data.get("transport_mode") or data.get("transportMode"),
            data.get("vehicleNo"), data.get("driverInfo"),
            data.get("payment_method") or data.get("paymentMethod"),
            data.get("pickupDate"),
            bool(data.get("temp_qc_required") or data.get("tempQC")),
            bool(data.get("openForBarter")),
            data.get("wantedCategory"), data.get("wantedMassKg"),
            data.get("divertReason"),
            data.get("digesterTank"),
            data.get("digestionStartedAt") or _now_ms(),
        )

    row = await fetchrow("""
        SELECT id, lot_code, category, other_text, sub_type,
               mass_kg, moisture_pct, rate_per_kg, total_value,
               ST_Y(location::geometry) AS lat, ST_X(location::geometry) AS lng,
               origin_label, photo_url, ocr_raw_text, ocr_confidence, status,
               matched_at, transporter, trip_status, transport_mode, vehicle_no,
               driver_info, payment_method, pickup_date, temp_qc_required,
               open_for_barter, wanted_category, wanted_mass_kg, divert_reason,
               digester_tank, digestion_started_at, created_at, updated_at
        FROM listings WHERE lot_code=$1""", lot_code)

    await agro_hub.emit("listings-changed", {"lot_code": lot_code})
    return _listing_to_wire(row)


@app.get("/api/listings")
async def list_listings(status: Optional[str] = None, category: Optional[str] = None):
    q = "SELECT * FROM listings WHERE 1=1"
    args = []
    if status:
        args.append(status); q += f" AND status = ${len(args)}"
    if category:
        args.append(category); q += f" AND category = ${len(args)}"
    q += " ORDER BY created_at DESC LIMIT 500"
    rows = await fetch(q, *args)
    return [_listing_to_wire(r) for r in rows]


@app.get("/api/listings/{lot_id}")
async def get_listing(lot_id: str):
    row = await fetchrow("SELECT * FROM listings WHERE lot_code=$1 OR id::text=$1", lot_id)
    if not row:
        raise HTTPException(404, "Listing not found")
    return _listing_to_wire(row)


@app.delete("/api/listings/{lot_id}")
async def delete_listing(lot_id: str):
    await execute("DELETE FROM listings WHERE lot_code=$1 OR id::text=$1", lot_id)
    await agro_hub.emit("listings-changed")
    return {"ok": True}


@app.get("/api/listings/{lot_id}/matches")
async def match_buyers(lot_id: str, radius: float = 50):
    rows = await fetch("""
        SELECT b.id, b.name, b.role, b.accepted_categories, b.weekly_capacity_kg,
               b.max_rate_per_kg, b.contact_mobile,
               ST_Distance(b.location, l.location)/1000 AS distance_km,
               ST_Y(b.location::geometry) AS lat,
               ST_X(b.location::geometry) AS lng
        FROM buyers b, listings l
        WHERE (l.lot_code = $1 OR l.id::text = $1)
          AND b.verified = TRUE
          AND (l.category = ANY(b.accepted_categories) OR array_length(b.accepted_categories,1) IS NULL)
          AND ST_DWithin(b.location, l.location, $2 * 1000)
        ORDER BY b.location <-> l.location
        LIMIT 20
    """, lot_id, radius)
    return [serialize_row(r) for r in rows]


# ═════════════════════════════════════════════
# AGRO — BUYERS
# ═════════════════════════════════════════════
@app.post("/api/buyers")
async def create_buyer(payload: BuyerIn):
    data = payload.model_dump()
    lat = data.get("lat") or (data.get("location") or {}).get("lat") or 28.6139
    lng = data.get("lng") or (data.get("location") or {}).get("lng") or 77.2090
    cats = data.get("accepted_categories") or data.get("accepts") or []
    if not isinstance(cats, list):
        cats = []
    bid = await fetchval(
        """INSERT INTO buyers (role, name, contact_mobile, contact_email,
                location, address, accepted_categories, weekly_capacity_kg,
                max_rate_per_kg, max_moisture_pct, max_radius_km, demand_note, verified)
           VALUES ($1,$2,$3,$4,ST_GeogFromText($5),$6,$7,$8,$9,$10,$11,$12,$13)
           RETURNING id""",
        data.get("role", "industry"), data["name"],
        data.get("contact_mobile"), data.get("contact_email"),
        _geog_point(lat, lng), data.get("address"),
        cats, data.get("weekly_capacity_kg"),
        data.get("max_rate_per_kg"), data.get("max_moisture_pct"),
        data.get("max_radius_km") or 50, data.get("demand"),
        data.get("verified", True),
    )
    await agro_hub.emit("buyers-changed")
    row = await fetchrow("SELECT * FROM buyers WHERE id=$1", bid)
    return serialize_row(row)


@app.get("/api/buyers")
async def list_buyers(role: Optional[str] = None):
    if role:
        rows = await fetch("SELECT * FROM buyers WHERE role=$1 AND verified=TRUE ORDER BY created_at DESC", role)
    else:
        rows = await fetch("SELECT * FROM buyers WHERE verified=TRUE ORDER BY created_at DESC")
    geo = await fetch("""
        SELECT id, ST_Y(location::geometry) AS lat, ST_X(location::geometry) AS lng
        FROM buyers WHERE verified=TRUE
    """)
    gmap = {r["id"]: r for r in geo}
    out = []
    for r in rows:
        s = serialize_row(r)
        s["accepts"] = s.get("accepted_categories") or []
        if s["id"] in gmap:
            s["lat"] = gmap[s["id"]]["lat"]
            s["lng"] = gmap[s["id"]]["lng"]
        out.append(s)
    return out


# ═════════════════════════════════════════════
# AGRO — PROFILES
# ═════════════════════════════════════════════
@app.post("/api/profiles")
async def save_profile(payload: ProfileIn):
    data = payload.model_dump()
    name = data.get("display_name") or data.get("name") or "User"
    lat = data.get("lat") or (data.get("location") or {}).get("lat") or 28.6139
    lng = data.get("lng") or (data.get("location") or {}).get("lng") or 77.2090
    meta = {k: v for k, v in data.items() if k not in
            ("role", "name", "display_name", "mobile", "email", "lat", "lng", "location", "pincode")}

    await execute("""
        INSERT INTO profiles (role, display_name, mobile, email, pincode, location, meta)
        VALUES ($1,$2,$3,$4,$5,ST_GeogFromText($6),$7::jsonb)
    """, data["role"], name, data.get("mobile") or "",
        data.get("email"), data.get("pincode"), _geog_point(lat, lng), json.dumps(meta))

    await execute("""
        UPDATE profiles SET display_name=$2, mobile=$3, email=$4, pincode=$5,
            location=ST_GeogFromText($6), meta=$7::jsonb, updated_at=NOW()
        WHERE id = (SELECT id FROM profiles WHERE role=$1 ORDER BY updated_at DESC LIMIT 1)
    """, data["role"], name, data.get("mobile") or "",
        data.get("email"), data.get("pincode"), _geog_point(lat, lng), json.dumps(meta))

    await agro_hub.emit("profiles-changed")
    row = await fetchrow("SELECT * FROM profiles WHERE role=$1 ORDER BY updated_at DESC LIMIT 1", data["role"])
    return serialize_row(row)


@app.get("/api/profiles")
async def get_profiles(role: Optional[str] = None):
    if role:
        rows = await fetch("SELECT * FROM profiles WHERE role=$1 ORDER BY updated_at DESC LIMIT 1", role)
    else:
        rows = await fetch("SELECT * FROM profiles ORDER BY updated_at DESC LIMIT 100")
    return [serialize_row(r) for r in rows]


@app.delete("/api/profiles")
async def clear_profiles():
    await execute("DELETE FROM profiles")
    await agro_hub.emit("profiles-changed")
    return {"ok": True}


# ═════════════════════════════════════════════
# AGRO — ESCROW
# ═════════════════════════════════════════════
@app.post("/api/escrow")
async def record_escrow(payload: EscrowIn):
    data = payload.model_dump()
    code = data.get("listing_code") or data.get("listingId") or data.get("listing_id")
    listing_id = None
    if code:
        listing_id = await fetchval("SELECT id FROM listings WHERE lot_code=$1 OR id::text=$1", code)
    await execute("""
        INSERT INTO escrow_ledger (listing_id, milestone, amount, released_by, notes)
        VALUES ($1,$2,$3,$4,$5)
    """, listing_id, data["milestone"], data["amount"],
        data.get("released_by") or data.get("releasedBy"), data.get("notes"))
    await agro_hub.emit("escrow-changed")
    return {"ok": True}


@app.get("/api/escrow")
async def list_escrow(listing: Optional[str] = None):
    if listing:
        rows = await fetch("""
            SELECT e.*, l.lot_code FROM escrow_ledger e
            LEFT JOIN listings l ON l.id = e.listing_id
            WHERE l.lot_code=$1 OR l.id::text=$1 ORDER BY e.released_at DESC
        """, listing)
    else:
        rows = await fetch("""
            SELECT e.*, l.lot_code FROM escrow_ledger e
            LEFT JOIN listings l ON l.id = e.listing_id
            ORDER BY e.released_at DESC LIMIT 500
        """)
    return [serialize_row(r) for r in rows]


# ═════════════════════════════════════════════
# AGRO — BARTER
# ═════════════════════════════════════════════
@app.post("/api/barter")
async def create_barter(payload: BarterIn):
    data = payload.model_dump()
    tid = None
    if data.get("targetLotId") or data.get("target_listing_id"):
        tid = await fetchval("SELECT id FROM listings WHERE lot_code=$1 OR id::text=$1",
                             data.get("targetLotId") or data.get("target_listing_id"))
    bid = await fetchval("""
        INSERT INTO barter_proposals (from_profile_id, target_listing_id, offering_category,
            offering_mass_kg, offering_moisture, note)
        VALUES ($1,$2,$3,$4,$5,$6) RETURNING id
    """, None, tid,
        data.get("offeringCategory") or data.get("offering_category") or "OTHER",
        data.get("offeringMassKg") or data.get("offering_mass_kg") or 0,
        data.get("offeringMoisture"), data.get("note"))
    await agro_hub.emit("barter-changed")
    row = await fetchrow("SELECT * FROM barter_proposals WHERE id=$1", bid)
    return serialize_row(row)


@app.get("/api/barter")
async def list_barter():
    rows = await fetch("SELECT * FROM barter_proposals ORDER BY created_at DESC LIMIT 200")
    return [serialize_row(r) for r in rows]


# ═════════════════════════════════════════════
# AGRO — STORE PRODUCTS
# ═════════════════════════════════════════════
@app.post("/api/store/products")
async def save_product(payload: ProductIn):
    data = payload.model_dump()
    pid = data.get("id")
    title = data["title"]
    stock = data.get("stock_quantity") or data.get("stockQuantity") or 0
    img = data.get("image_url") or data.get("image") or ""
    carbon = data.get("carbon_saved_kgco2e") or data.get("carbonSavedKgCO2e") or 0
    biomass = data.get("raw_biomass_used_kg") or data.get("rawBiomassUsedKg") or 0
    seller_name = data.get("seller_name") or data.get("sellerName")

    if pid:
        await execute("""
            UPDATE products SET title=$2, description=$3, category=$4, price=$5, mrp=$6,
                stock_quantity=$7, image_url=$8, carbon_saved_kgco2e=$9, raw_biomass_used_kg=$10,
                seller_name=$11, updated_at=NOW()
            WHERE id::text=$1
        """, pid, title, data.get("description"), data["category"], data["price"],
            data.get("mrp"), stock, img, carbon, biomass, seller_name)
        row_id = pid
    else:
        row_id = await fetchval("""
            INSERT INTO products (product_code, title, description, category, price, mrp,
                stock_quantity, image_url, carbon_saved_kgco2e, raw_biomass_used_kg,
                seller_name, source_mandi, origin_location, artisan_location,
                artisan_name, seller_verified)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,
                ST_GeogFromText($13),ST_GeogFromText($14),$15,$16)
            RETURNING id
        """, _gen_id("PRD"), title, data.get("description"), data["category"],
            data["price"], data.get("mrp"), stock, img, carbon, biomass,
            seller_name, data.get("source_mandi") or data.get("sourceFarmerOrMandi"),
            _geog_point(data.get("originLat") or 30.1453, data.get("originLng") or 74.1994),
            _geog_point(data.get("artisanLat") or 30.9010, data.get("artisanLng") or 75.8573),
            data.get("artisanName"),
            data.get("seller_verified") if data.get("seller_verified") is not None else data.get("sellerVerified"))
    await agro_hub.emit("products-changed")
    row = await fetchrow("SELECT * FROM products WHERE id::text=$1", str(row_id))
    return _product_to_wire(row)


@app.get("/api/store/products")
async def list_products(seller: Optional[str] = None):
    if seller:
        rows = await fetch("SELECT * FROM products WHERE seller_name ILIKE $1 ORDER BY created_at DESC", f"%{seller}%")
    else:
        rows = await fetch("SELECT * FROM products ORDER BY created_at DESC LIMIT 500")
    return [_product_to_wire(r) for r in rows]


@app.get("/api/store/products/{pid}")
async def get_product(pid: str):
    row = await fetchrow("SELECT * FROM products WHERE id::text=$1 OR product_code=$1", pid)
    if not row:
        raise HTTPException(404, "Not found")
    return _product_to_wire(row)


@app.put("/api/store/products/{pid}")
async def update_product(pid: str, payload: ProductIn):
    payload.id = pid
    return await save_product(payload)


@app.delete("/api/store/products/{pid}")
async def delete_product(pid: str):
    await execute("DELETE FROM products WHERE id::text=$1 OR product_code=$1", pid)
    await agro_hub.emit("products-changed")
    return {"ok": True}


# ═════════════════════════════════════════════
# AGRO — STORE USERS
# ═════════════════════════════════════════════
@app.post("/api/store/users")
async def save_store_user(payload: StoreUserIn):
    data = payload.model_dump()
    uid = data.get("id")
    if uid:
        await execute("""
            UPDATE store_users SET role=$2, name=$3, mobile=$4, email=$5, pincode=$6,
                shop_name=$7, gst_number=$8, seller_verified=$9
            WHERE id::text=$1
        """, uid, data["role"], data["name"], data["mobile"], data.get("email"),
            data.get("pincode"), data.get("shop_name"), data.get("gst_number"),
            data.get("seller_verified"))
        row_id = uid
    else:
        row_id = await fetchval("""
            INSERT INTO store_users (role, name, mobile, email, pincode, shop_name,
                gst_number, seller_verified)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8) RETURNING id
        """, data["role"], data["name"], data["mobile"], data.get("email"),
            data.get("pincode"), data.get("shop_name"), data.get("gst_number"),
            data.get("seller_verified"))
    await agro_hub.emit("store-users-changed")
    row = await fetchrow("SELECT * FROM store_users WHERE id::text=$1", str(row_id))
    return serialize_row(row)


@app.get("/api/store/users")
async def list_store_users(role: Optional[str] = None):
    if role:
        rows = await fetch("SELECT * FROM store_users WHERE role=$1 ORDER BY created_at DESC LIMIT 1", role)
    else:
        rows = await fetch("SELECT * FROM store_users ORDER BY created_at DESC LIMIT 100")
    return [serialize_row(r) for r in rows]


@app.delete("/api/store/users")
async def clear_store_users():
    await execute("DELETE FROM store_users")
    await agro_hub.emit("store-users-changed")
    return {"ok": True}


# ═════════════════════════════════════════════
# AGRO — STORE ORDERS
# ═════════════════════════════════════════════
@app.post("/api/store/orders")
async def create_store_order(payload: StoreOrderIn):
    data = payload.model_dump()
    pid = data.get("product_id") or data.get("productId")
    qty = data["qty"]

    async with (await get_pool()).acquire() as conn:
        async with conn.transaction():
            stock = await conn.fetchval(
                "SELECT stock_quantity FROM products WHERE id::text=$1 OR product_code=$1 FOR UPDATE", pid)
            if stock is None:
                raise HTTPException(404, "Product not found")
            if stock < qty:
                raise HTTPException(409, f"Only {stock} units available")
            await conn.execute(
                "UPDATE products SET stock_quantity = stock_quantity - $2 WHERE id::text=$1 OR product_code=$1",
                pid, qty)
            oid = await conn.fetchval("""
                INSERT INTO store_orders (order_code, product_title, product_image,
                    seller_name, customer_name, qty, unit_price, total, status)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9) RETURNING id
            """, data.get("order_code") or _gen_id("ORD"),
                data.get("product_title") or data.get("productTitle"),
                data.get("product_image") or data.get("productImage"),
                data.get("seller_name") or data.get("sellerName"),
                data.get("customer_name") or data.get("customerName"),
                qty,
                data.get("unit_price") or data.get("unitPrice") or 0,
                data["total"], data.get("status", "CONFIRMED"))

    await agro_hub.emit("orders-changed")
    await agro_hub.emit("products-changed")
    row = await fetchrow("SELECT * FROM store_orders WHERE id::text=$1", str(oid))
    return serialize_row(row)


@app.get("/api/store/orders")
async def list_orders(seller: Optional[str] = None, customer: Optional[str] = None):
    q = "SELECT * FROM store_orders WHERE 1=1"
    args = []
    if seller:
        args.append(f"%{seller}%"); q += f" AND seller_name ILIKE ${len(args)}"
    if customer:
        args.append(f"%{customer}%"); q += f" AND customer_name ILIKE ${len(args)}"
    q += " ORDER BY created_at DESC LIMIT 500"
    rows = await fetch(q, *args)
    return [serialize_row(r) for r in rows]


# ═════════════════════════════════════════════
# AGRO — CART / WISHLIST (stubs, sessionless)
# ═════════════════════════════════════════════
@app.put("/api/store/cart")
async def save_cart(body: list = None):
    return {"ok": True, "cart": body or []}


@app.get("/api/store/cart")
async def get_cart():
    return []


@app.put("/api/store/wishlist")
async def save_wishlist(body: dict = None):
    return {"ok": True, "list": (body or {}).get("list", [])}


@app.get("/api/store/wishlist")
async def get_wishlist(user: Optional[str] = None):
    return []


# ═════════════════════════════════════════════
# AGRO — PAYMENTS
# ═════════════════════════════════════════════
@app.post("/api/payments/create-order")
async def create_payment_order(payload: PaymentOrderIn):
    amount_paise = int(round(payload.amount * 100))
    if amount_paise < 100:
        raise HTTPException(400, "Amount must be at least ₹1")
    receipt = payload.receipt or _gen_id("RCPT")
    try:
        order = create_order(amount_paise, receipt, payload.notes)
    except Exception as e:
        raise HTTPException(500, f"Razorpay error: {e}")
    return {"id": order["id"], "amount": order["amount"], "currency": order["currency"],
            "key_id": os.getenv("RAZORPAY_KEY_ID", "")}


@app.post("/api/payments/verify")
async def verify_payment(payload: PaymentVerifyIn):
    ok = verify_signature(payload.razorpay_order_id, payload.razorpay_payment_id,
                          payload.razorpay_signature)
    return {"ok": ok}


@app.post("/api/payments")
async def save_payment(body: dict):
    return {"ok": True, "stored": body.get("id")}


@app.get("/api/payments")
async def list_payments():
    return []


# ═════════════════════════════════════════════
# INSTITUTIONAL — INSTITUTES
# ═════════════════════════════════════════════
@app.post("/api/institutional/institutes")
async def create_institute(payload: InstituteIn):
    data = payload.model_dump()
    code = data.get("code") or _gen_id("INST")
    loc = data.get("location") or {}
    lat = loc.get("lat") or 20.2961
    lng = loc.get("lng") or 85.8245

    iid = await fetchval("""
        INSERT INTO institutes (code, name, type, established_year, aishe_code,
            recognition, naac_grade, city, state, pin_code, student_count,
            mess_name, admin_designation, admin_name, admin_email, admin_mobile,
            password_hash, location, verified, verified_at)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,
                ST_GeogFromText($18),$19,
                CASE WHEN $19 THEN NOW() END)
        RETURNING id
    """, code, data["name"], data.get("type", "university"), data.get("established_year"),
        data.get("aishe_code"), data.get("recognition"), data.get("naac_grade"),
        data.get("city"), data.get("state"), data.get("pin_code"),
        data.get("student_count"), data.get("mess_name"), data.get("admin_designation"),
        data.get("admin_name"), data.get("admin_email"), data.get("admin_mobile"),
        data.get("password_hash"), _geog_point(lat, lng), data.get("verified", True))

    await institutional_hub.emit("institutes-changed")
    row = await fetchrow("SELECT * FROM institutes WHERE id=$1", iid)
    return serialize_row(row)


@app.get("/api/institutional/institutes")
async def list_institutes(code: Optional[str] = None, aishe: Optional[str] = None):
    if code:
        row = await fetchrow("SELECT * FROM institutes WHERE code=$1", code)
        return serialize_row(row) if row else None
    if aishe:
        row = await fetchrow("SELECT * FROM institutes WHERE aishe_code=$1", aishe)
        return serialize_row(row) if row else None
    rows = await fetch("SELECT * FROM institutes ORDER BY created_at DESC LIMIT 200")
    return [serialize_row(r) for r in rows]


@app.get("/api/institutional/institutes/{iid}")
async def get_institute(iid: str):
    row = await fetchrow("SELECT * FROM institutes WHERE id::text=$1 OR code=$1", iid)
    if not row:
        raise HTTPException(404, "Not found")
    return serialize_row(row)


@app.get("/api/institutional/institutes/{iid}/summary")
async def institute_summary(iid: str):
    iid_int = await fetchval("SELECT id FROM institutes WHERE id::text=$1 OR code=$1", iid)
    if not iid_int:
        raise HTTPException(404, "Institute not found")
    plans = await fetch("SELECT * FROM meal_plans WHERE institute_id=$1", iid_int)
    preps = await fetch("SELECT * FROM meal_preps WHERE institute_id=$1", iid_int)
    disp = await fetch("SELECT * FROM ngo_dispatches WHERE institute_id=$1", iid_int)
    esg = await fetch("SELECT * FROM esg_ledger WHERE institute_id=$1", iid_int)
    return {
        "total_plans": len(plans),
        "total_preps": len(preps),
        "total_dispatches": len(disp),
        "total_meals_rescued": sum(d.get("meals_sent", 0) for d in disp),
        "total_co2e_saved": float(sum(e.get("co2e_kg", 0) for e in esg)),
        "total_water_saved": sum(e.get("water_l", 0) for e in esg),
        "total_value_saved": float(sum(e.get("cost_inr", 0) for e in esg)),
        "last_activity": (serialize_row(disp[0]).get("created_at") if disp else None),
    }


@app.post("/api/institutional/institutes/{iid}/seed")
async def seed_institute(iid: str):
    return {"ok": True}


# ═════════════════════════════════════════════
# INSTITUTIONAL — SESSIONS
# ═════════════════════════════════════════════
@app.post("/api/institutional/session")
async def save_session(payload: SessionIn):
    iid = await fetchval("SELECT id FROM institutes WHERE id::text=$1 OR code=$1", payload.institute_id)
    if not iid:
        raise HTTPException(404, "Institute not found")
    sid = _gen_id("SESS")
    await execute("""
        INSERT INTO sessions (id, institute_id, code, name, role, expires_at)
        VALUES ($1,$2,$3,$4,$5,NOW() + INTERVAL '7 days')
    """, sid, iid, payload.code, payload.name, payload.role)
    await institutional_hub.emit("session-changed")
    return {"id": sid, "institute_id": str(iid), "code": payload.code,
            "name": payload.name, "jwt": "demo-" + sid}


@app.get("/api/institutional/session")
async def get_session():
    row = await fetchrow("SELECT * FROM sessions ORDER BY created_at DESC LIMIT 1")
    return serialize_row(row) if row else None


@app.delete("/api/institutional/session")
async def clear_session():
    await execute("DELETE FROM sessions")
    await institutional_hub.emit("session-changed")
    return {"ok": True}


# ═════════════════════════════════════════════
# INSTITUTIONAL — OTP
# ═════════════════════════════════════════════
@app.post("/api/institutional/otp")
async def create_otp(body: dict):
    mobile = body.get("mobile")
    if not mobile:
        raise HTTPException(400, "mobile required")
    code = generate_otp()
    await execute("""
        INSERT INTO otp_requests (id, mobile, code_hash, expires_at)
        VALUES ($1,$2,$3,NOW() + INTERVAL '10 minutes')
    """, _gen_id("OTP"), mobile, hash_otp(code, mobile))
    return {"mobile": mobile, "expires_in": 600, "demo_code": code}


@app.post("/api/institutional/otp/verify")
async def verify_otp(body: dict):
    mobile = body.get("mobile"); code = body.get("code")
    row = await fetchrow("""
        SELECT * FROM otp_requests
        WHERE mobile=$1 AND code_hash=$2 AND verified=FALSE AND expires_at > NOW()
        ORDER BY created_at DESC LIMIT 1
    """, mobile, hash_otp(code, mobile))
    if not row:
        return {"ok": False}
    await execute("UPDATE otp_requests SET verified=TRUE WHERE id=$1", row["id"])
    return {"ok": True}


# ═════════════════════════════════════════════
# INSTITUTIONAL — NGOS
# ═════════════════════════════════════════════
@app.post("/api/institutional/ngos")
async def create_ngo(payload: NGOIn):
    data = payload.model_dump()
    coords = data.get("coords") or {}
    lat = coords.get("lat") or 20.2612
    lng = coords.get("lng") or 85.7895
    nid = await fetchval("""
        INSERT INTO ngos (name, contact, phone, email, city, address, capacity,
            base_eta_min, distance_km, location, verified, verified_at)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,ST_GeogFromText($10),$11,
            CASE WHEN $11 THEN NOW() END)
        RETURNING id
    """, data["name"], data.get("contact"), data.get("phone"), data.get("email"),
        data.get("city"), data.get("address"), data.get("capacity", 0),
        data.get("base_eta_min", 15), data.get("distance_km"),
        _geog_point(lat, lng), data.get("verified", True))
    await institutional_hub.emit("ngos-changed")
    row = await fetchrow("SELECT * FROM ngos WHERE id=$1", nid)
    return serialize_row(row)


@app.get("/api/institutional/ngos")
async def list_ngos():
    rows = await fetch("SELECT * FROM ngos WHERE verified=TRUE ORDER BY distance_km NULLS LAST")
    geo = await fetch("""
        SELECT id, ST_Y(location::geometry) AS lat, ST_X(location::geometry) AS lng
        FROM ngos WHERE verified=TRUE
    """)
    gmap = {r["id"]: r for r in geo}
    out = []
    for r in rows:
        s = serialize_row(r)
        if s["id"] in gmap:
            s["coords"] = {"lat": gmap[s["id"]]["lat"], "lng": gmap[s["id"]]["lng"]}
        else:
            s["coords"] = {"lat": None, "lng": None}
        out.append(s)
    return out


@app.get("/api/institutional/ngos/{nid}")
async def get_ngo(nid: str):
    row = await fetchrow("SELECT * FROM ngos WHERE id::text=$1", nid)
    if not row:
        raise HTTPException(404, "Not found")
    return serialize_row(row)


@app.put("/api/institutional/ngos/{nid}")
async def update_ngo(nid: str, payload: NGOIn):
    data = payload.model_dump()
    await execute("""
        UPDATE ngos SET name=$2, contact=$3, phone=$4, email=$5, city=$6, address=$7,
            capacity=$8, base_eta_min=$9, distance_km=$10, verified=$11, updated_at=NOW()
        WHERE id::text=$1
    """, nid, data["name"], data.get("contact"), data.get("phone"), data.get("email"),
        data.get("city"), data.get("address"), data.get("capacity", 0),
        data.get("base_eta_min", 15), data.get("distance_km"), data.get("verified", True))
    await institutional_hub.emit("ngos-changed")
    row = await fetchrow("SELECT * FROM ngos WHERE id::text=$1", nid)
    return serialize_row(row)


@app.delete("/api/institutional/ngos/{nid}")
async def delete_ngo(nid: str):
    await execute("DELETE FROM ngos WHERE id::text=$1", nid)
    await institutional_hub.emit("ngos-changed")
    return {"ok": True}


# ═════════════════════════════════════════════
# INSTITUTIONAL — MEAL PLANS
# ═════════════════════════════════════════════
@app.post("/api/institutional/meal-plans")
async def create_meal_plan(payload: MealPlanIn):
    data = payload.model_dump()
    pd = data.get("plan_date") or data.get("date") or date.today().isoformat()
    iid = await fetchval("SELECT id FROM institutes WHERE id::text=$1 OR code=$1", data["institute_id"])
    if not iid:
        raise HTTPException(404, "Institute not found")
    pid = await fetchval("""
        INSERT INTO meal_plans (institute_id, plan_date, meal_slot, predicted_demand,
            prepared_count, expected_waste_kg, waste_risk_score, variance_pct,
            menu_items, weather_snapshot, agent_suggested, agent_headcount,
            agent_factors, status, dispatch_ready, dispatch_ready_at, published_at)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb,$10::jsonb,$11,$12,$13::jsonb,$14,$15,
            CASE WHEN $16::bigint IS NOT NULL THEN TO_TIMESTAMP($16/1000.0) END,
            CASE WHEN $14='PUBLISHED' THEN NOW() END)
        RETURNING id
    """, iid, pd, data["meal_slot"], data.get("predicted_demand"),
        data.get("prepared_count"), data.get("expected_waste_kg"),
        data.get("waste_risk_score"), data.get("variance_pct"),
        json.dumps(data.get("menu_items") or []),
        json.dumps(data.get("weather_snapshot")) if data.get("weather_snapshot") else None,
        data.get("agent_suggested", False), data.get("agent_headcount"),
        json.dumps(data.get("agent_factors") or []),
        data.get("status", "DRAFT"), data.get("dispatch_ready", False),
        int(data["dispatch_ready_at"]) if data.get("dispatch_ready_at") else None)
    await institutional_hub.emit("meal-plans-changed")
    row = await fetchrow("SELECT * FROM meal_plans WHERE id=$1", pid)
    return _plan_to_wire(row)


@app.get("/api/institutional/meal-plans")
async def list_meal_plans(institute: Optional[str] = None, date: Optional[str] = None,
                          slot: Optional[str] = None):
    iid = await fetchval("SELECT id FROM institutes WHERE id::text=$1 OR code=$1", institute) if institute else None
    q = "SELECT * FROM meal_plans WHERE 1=1"
    args = []
    if iid:
        args.append(iid); q += f" AND institute_id=${len(args)}"
    if date:
        args.append(date); q += f" AND plan_date=${len(args)}"
    if slot:
        args.append(slot); q += f" AND meal_slot=${len(args)}"
    q += " ORDER BY created_at DESC LIMIT 500"
    rows = await fetch(q, *args)
    out = [_plan_to_wire(r) for r in rows]
    if date and slot and institute:
        return out[0] if out else None
    return out


@app.get("/api/institutional/meal-plans/{pid}")
async def get_meal_plan(pid: str):
    row = await fetchrow("SELECT * FROM meal_plans WHERE id::text=$1", pid)
    if not row:
        raise HTTPException(404, "Not found")
    return _plan_to_wire(row)


@app.put("/api/institutional/meal-plans/{pid}")
async def update_meal_plan(pid: str, payload: MealPlanIn):
    data = payload.model_dump()
    await execute("""
        UPDATE meal_plans SET predicted_demand=$2, prepared_count=$3,
            expected_waste_kg=$4, waste_risk_score=$5, variance_pct=$6,
            menu_items=$7::jsonb, weather_snapshot=$8::jsonb, agent_suggested=$9,
            agent_headcount=$10, agent_factors=$11::jsonb, status=$12,
            dispatch_ready=$13, updated_at=NOW()
        WHERE id::text=$1
    """, pid, data.get("predicted_demand"), data.get("prepared_count"),
        data.get("expected_waste_kg"), data.get("waste_risk_score"),
        data.get("variance_pct"),
        json.dumps(data.get("menu_items") or []),
        json.dumps(data.get("weather_snapshot")) if data.get("weather_snapshot") else None,
        data.get("agent_suggested", False), data.get("agent_headcount"),
        json.dumps(data.get("agent_factors") or []),
        data.get("status", "DRAFT"), data.get("dispatch_ready", False))
    await institutional_hub.emit("meal-plans-changed")
    row = await fetchrow("SELECT * FROM meal_plans WHERE id::text=$1", pid)
    return _plan_to_wire(row)


@app.post("/api/institutional/meal-plans/{pid}/publish")
async def publish_meal_plan(pid: str):
    await execute("""
        UPDATE meal_plans SET status='PUBLISHED', published_at=NOW(), updated_at=NOW()
        WHERE id::text=$1
    """, pid)
    await institutional_hub.emit("meal-plans-changed")
    row = await fetchrow("SELECT * FROM meal_plans WHERE id::text=$1", pid)
    return _plan_to_wire(row)


@app.get("/api/institutional/meal-plans/variance")
async def plan_variance(institute: str, days: int = 7):
    iid = await fetchval("SELECT id FROM institutes WHERE id::text=$1 OR code=$1", institute)
    if not iid:
        return []
    rows = await fetch("""
        SELECT p.id, p.plan_date, p.meal_slot, p.predicted_demand, p.status,
               COALESCE((SELECT served_count FROM plate_tallies
                         WHERE prep_id IN (SELECT id::text FROM meal_preps WHERE plan_id=p.id::text)
                         ORDER BY created_at DESC LIMIT 1),0) AS served
        FROM meal_plans p WHERE p.institute_id=$1
        ORDER BY p.plan_date DESC LIMIT $2
    """, iid, days * 4)
    out = []
    for r in rows:
        s = serialize_row(r)
        planned = s.get("predicted_demand") or 0
        served = s.get("served") or 0
        waste = round(max(0, (planned - served) / planned * 100)) if planned and served else None
        out.append({
            "id": s["id"], "date": str(s.get("plan_date") or ""),
            "meal_slot": s.get("meal_slot"), "planned": planned,
            "served": served, "waste_pct": waste, "status": s.get("status"),
        })
    return out


# ═════════════════════════════════════════════
# INSTITUTIONAL — PREPS
# ═════════════════════════════════════════════
@app.post("/api/institutional/meal-preps")
async def create_prep(payload: MealPrepIn):
    data = payload.model_dump()
    pid = await fetchval("""
        INSERT INTO meal_preps (institute_id, plan_id, prepared_count,
            agent_suggested_count, agent_factors, variance_pct, notes, chef_verified_at)
        VALUES ($1,$2,$3,$4,$5::jsonb,$6,$7,
            CASE WHEN $8::bigint IS NOT NULL THEN TO_TIMESTAMP($8/1000.0) END)
        RETURNING id
    """, data["institute_id"], data.get("plan_id"), data["prepared_count"],
        data.get("agent_suggested_count"), json.dumps(data.get("agent_factors") or []),
        data.get("variance_pct"), data.get("notes", ""),
        int(data["chef_verified_at"]) if data.get("chef_verified_at") else None)
    await institutional_hub.emit("meal-preps-changed")
    row = await fetchrow("SELECT * FROM meal_preps WHERE id=$1", pid)
    return serialize_row(row)


@app.put("/api/institutional/meal-preps/{pid}")
async def update_prep(pid: str, payload: MealPrepIn):
    data = payload.model_dump()
    await execute("""
        UPDATE meal_preps SET prepared_count=$2, agent_suggested_count=$3,
            agent_factors=$4::jsonb, variance_pct=$5, notes=$6,
            chef_verified_at=CASE WHEN $7::bigint IS NOT NULL THEN TO_TIMESTAMP($7/1000.0) ELSE chef_verified_at END,
            updated_at=NOW()
        WHERE id::text=$1
    """, pid, data["prepared_count"], data.get("agent_suggested_count"),
        json.dumps(data.get("agent_factors") or []), data.get("variance_pct"),
        data.get("notes", ""),
        int(data["chef_verified_at"]) if data.get("chef_verified_at") else None)
    await institutional_hub.emit("meal-preps-changed")
    row = await fetchrow("SELECT * FROM meal_preps WHERE id::text=$1", pid)
    return serialize_row(row)


@app.get("/api/institutional/meal-preps")
async def list_preps(institute: Optional[str] = None, plan: Optional[str] = None,
                     latest: int = 0):
    q = "SELECT * FROM meal_preps WHERE 1=1"; args = []
    if institute:
        args.append(institute); q += f" AND institute_id=${len(args)}"
    if plan:
        args.append(plan); q += f" AND plan_id=${len(args)}"
    q += " ORDER BY created_at DESC LIMIT 500"
    rows = await fetch(q, *args)
    out = [serialize_row(r) for r in rows]
    if latest:
        return out[0] if out else None
    return out


# ═════════════════════════════════════════════
# INSTITUTIONAL — TALLIES
# ═════════════════════════════════════════════
@app.post("/api/institutional/plate-tallies")
async def create_tally(payload: TallyIn):
    data = payload.model_dump()
    tid = await fetchval("""
        INSERT INTO plate_tallies (prep_id, institute_id, served_count)
        VALUES ($1,$2,$3) RETURNING id
    """, data["prep_id"], data["institute_id"], data.get("served_count", 0))
    await institutional_hub.emit("tallies-changed")
    row = await fetchrow("SELECT * FROM plate_tallies WHERE id=$1", tid)
    return serialize_row(row)


@app.put("/api/institutional/plate-tallies/{tid}")
async def update_tally(tid: str, payload: TallyIn):
    data = payload.model_dump()
    await execute("""
        UPDATE plate_tallies SET served_count=$2, updated_at=NOW() WHERE id::text=$1
    """, tid, data.get("served_count", 0))
    await institutional_hub.emit("tallies-changed")
    row = await fetchrow("SELECT * FROM plate_tallies WHERE id::text=$1", tid)
    return serialize_row(row)


@app.get("/api/institutional/plate-tallies")
async def list_tallies(prep: Optional[str] = None, institute: Optional[str] = None,
                       latest: int = 0):
    q = "SELECT * FROM plate_tallies WHERE 1=1"; args = []
    if prep:
        args.append(prep); q += f" AND prep_id=${len(args)}"
    if institute:
        args.append(institute); q += f" AND institute_id=${len(args)}"
    q += " ORDER BY created_at DESC LIMIT 500"
    rows = await fetch(q, *args)
    out = [serialize_row(r) for r in rows]
    if latest:
        return out[0] if out else None
    return out


# ═════════════════════════════════════════════
# INSTITUTIONAL — THERMAL
# ═════════════════════════════════════════════
@app.post("/api/institutional/thermal-checks")
async def create_thermal(payload: ThermalIn):
    data = payload.model_dump()
    tid = await fetchval("""
        INSERT INTO thermal_checks (prep_id, institute_id, temp_c, state, hold_minutes,
            remaining_minutes, freshness_index, ready_for_dispatch)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8) RETURNING id
    """, data["prep_id"], data.get("institute_id"), data.get("temp_c"),
        data.get("state"), data.get("hold_minutes"), data.get("remaining_minutes"),
        data.get("freshness_index"), data.get("ready_for_dispatch", False))
    await institutional_hub.emit("thermal-changed")
    row = await fetchrow("SELECT * FROM thermal_checks WHERE id=$1", tid)
    return serialize_row(row)


@app.get("/api/institutional/thermal-checks")
async def list_thermal(prep: Optional[str] = None, latest: int = 0):
    q = "SELECT * FROM thermal_checks WHERE 1=1"; args = []
    if prep:
        args.append(prep); q += f" AND prep_id=${len(args)}"
    q += " ORDER BY created_at DESC LIMIT 500"
    rows = await fetch(q, *args)
    out = [serialize_row(r) for r in rows]
    if latest:
        return out[0] if out else None
    return out


# ═════════════════════════════════════════════
# INSTITUTIONAL — DISPATCHES
# ═════════════════════════════════════════════
@app.post("/api/institutional/dispatches")
async def create_dispatch(payload: DispatchIn):
    data = payload.model_dump()
    dcode = _gen_id("D")
    did = await fetchval("""
        INSERT INTO ngo_dispatches (dispatch_code, institute_id, prep_id, plan_id,
            ngo_id, ngo_name, ngo_distance_km, ngo_contact, ngo_phone, ngo_email,
            meals_sent, eta_minutes, category, temp_c, custody_officer, verified_at)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,
            CASE WHEN $16::bigint IS NOT NULL THEN TO_TIMESTAMP($16/1000.0) ELSE NOW() END)
        RETURNING id
    """, dcode, data["institute_id"], data.get("prep_id"), data.get("plan_id"),
        data.get("ngo_id"), data["ngo_name"], data.get("ngo_distance_km"),
        data.get("ngo_contact"), data.get("ngo_phone"), data.get("ngo_email"),
        data["meals_sent"], data.get("eta_minutes"), data.get("category"),
        data.get("temp_c"), data.get("custody_officer"),
        int(data["verified_at"]) if data.get("verified_at") else None)
    await institutional_hub.emit("dispatches-changed")
    row = await fetchrow("SELECT * FROM ngo_dispatches WHERE id=$1", did)
    return serialize_row(row)


@app.get("/api/institutional/dispatches")
async def list_dispatches(institute: Optional[str] = None):
    q = "SELECT * FROM ngo_dispatches WHERE 1=1"; args = []
    if institute:
        iid = await fetchval("SELECT id FROM institutes WHERE id::text=$1 OR code=$1", institute)
        if iid:
            args.append(iid); q += f" AND institute_id=${len(args)}"
    q += " ORDER BY created_at DESC LIMIT 500"
    rows = await fetch(q, *args)
    return [serialize_row(r) for r in rows]


@app.get("/api/institutional/dispatches/{did}")
async def get_dispatch(did: str):
    row = await fetchrow("SELECT * FROM ngo_dispatches WHERE id::text=$1 OR dispatch_code=$1", did)
    if not row:
        raise HTTPException(404, "Not found")
    return serialize_row(row)


# ═════════════════════════════════════════════
# INSTITUTIONAL — ESG
# ═════════════════════════════════════════════
@app.post("/api/institutional/esg-ledger")
async def create_esg(payload: ESGIn):
    data = payload.model_dump()
    eid = await fetchval("""
        INSERT INTO esg_ledger (institute_id, dispatch_id, plan_id, meals_rescued,
            co2e_kg, water_l, cost_inr, manual_entry, recipient, notes)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10) RETURNING id
    """, data["institute_id"], data.get("dispatch_id"), data.get("plan_id"),
        data.get("meals_rescued", 0), data.get("co2e_kg", 0), data.get("water_l", 0),
        data.get("cost_inr", 0), data.get("manual_entry", False),
        data.get("recipient"), data.get("notes"))
    await institutional_hub.emit("esg-changed")
    row = await fetchrow("SELECT * FROM esg_ledger WHERE id=$1", eid)
    return serialize_row(row)


@app.get("/api/institutional/esg-ledger")
async def list_esg(institute: Optional[str] = None):
    q = "SELECT * FROM esg_ledger WHERE 1=1"; args = []
    if institute:
        iid = await fetchval("SELECT id FROM institutes WHERE id::text=$1 OR code=$1", institute)
        if iid:
            args.append(iid); q += f" AND institute_id=${len(args)}"
    q += " ORDER BY created_at DESC LIMIT 500"
    rows = await fetch(q, *args)
    return [serialize_row(r) for r in rows]


# ═════════════════════════════════════════════
# AGENT ENDPOINTS (optional HTTP access)
# ═════════════════════════════════════════════
@app.get("/api/agents/forecast")
async def agent_forecast(institute: str, date: str, slot: str,
                         weather_factor: float = 0.0, exam_window: bool = False,
                         event: bool = False):
    iid = await fetchval("SELECT id FROM institutes WHERE id::text=$1 OR code=$1", institute)
    plans = await fetch("SELECT * FROM meal_plans WHERE institute_id=$1 AND status='COMPLETED'", iid)
    return forecast_agent([serialize_row(p) for p in plans], date, slot, weather_factor, exam_window, event)


@app.post("/api/agents/menu-suggest")
async def agent_menu(body: dict):
    return suggest_menu(body.get("inventory") or [], body.get("count") or 4)


@app.get("/api/agents/thermal")
async def agent_thermal(hold_minutes: float, shelf_life: float, ambient_temp_c: float,
                        surplus: int):
    return thermal_agent(hold_minutes, shelf_life, ambient_temp_c, surplus)


@app.post("/api/agents/dispatch")
async def agent_dispatch(body: dict):
    return dispatch_agent(body.get("ngos") or [], body.get("plates", 0),
                          body.get("max_safe_minutes", 45))


# ═════════════════════════════════════════════
# WEBSOCKETS
# ═════════════════════════════════════════════
@app.websocket("/ws")
async def ws_agro(ws: WebSocket):
    await agro_hub.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        agro_hub.disconnect(ws)
    except Exception:
        agro_hub.disconnect(ws)


@app.websocket("/ws/institutional")
async def ws_institutional(ws: WebSocket):
    await institutional_hub.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        institutional_hub.disconnect(ws)
    except Exception:
        institutional_hub.disconnect(ws)


# ═════════════════════════════════════════════
# KYC STUBS
# ═════════════════════════════════════════════
@app.post("/api/kyc/aadhaar")
async def kyc_aadhaar(body: dict):
    return {"ok": True, "aadhaar_hash": hash_otp(body.get("aadhaar", ""), body.get("mobile", ""))}


@app.post("/api/kyc/farmer-id")
async def kyc_farmer(body: dict):
    return {"ok": True}


@app.post("/api/kyc/land")
async def kyc_land(body: dict):
    return {"ok": True}


@app.post("/api/kyc/gst")
async def kyc_gst(body: dict):
    return {"ok": True}


@app.post("/api/kyc/darpan")
async def kyc_darpan(body: dict):
    return {"ok": True}


@app.post("/api/kyc/otp")
async def kyc_otp(body: dict):
    mobile = body.get("mobile")
    code = generate_otp()
    return {"ok": True, "mobile": mobile, "demo_code": code}