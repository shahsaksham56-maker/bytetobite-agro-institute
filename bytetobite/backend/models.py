"""Pydantic schemas for every request body across agro + institutional."""
from typing import Optional
from pydantic import BaseModel


# ═════════════════════════════════════════════
# AGRO — LISTINGS
# ═════════════════════════════════════════════
class ListingIn(BaseModel):
    id: Optional[str] = None
    lot_code: Optional[str] = None
    category: str
    other_text: Optional[str] = None
    sub_type: Optional[str] = None
    massKg: Optional[float] = None
    mass_kg: Optional[float] = None
    moisture: Optional[float] = None
    moisture_pct: Optional[float] = None
    rate: Optional[float] = None
    rate_per_kg: Optional[float] = None
    location: Optional[dict] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    origin: Optional[str] = None
    origin_label: Optional[str] = None
    photo_url: Optional[str] = None
    ocr_raw_text: Optional[str] = None
    ocr_confidence: Optional[float] = None
    status: Optional[str] = "OPEN"
    matchedBuyer: Optional[str] = None
    matched_buyer_id: Optional[int] = None
    transporter: Optional[str] = None
    tripStatus: Optional[str] = None
    transportMode: Optional[str] = None
    transport_mode: Optional[str] = None
    vehicleNo: Optional[str] = None
    driverInfo: Optional[str] = None
    paymentMethod: Optional[str] = None
    payment_method: Optional[str] = None
    pickupDate: Optional[str] = None
    tempQC: Optional[bool] = None
    temp_qc_required: Optional[bool] = None
    openForBarter: Optional[bool] = None
    wantedCategory: Optional[str] = None
    wantedMassKg: Optional[float] = None
    divertReason: Optional[str] = None
    cancelReason: Optional[str] = None
    digesterTank: Optional[str] = None
    digestionStartedAt: Optional[float] = None
    createdAt: Optional[float] = None


# ═════════════════════════════════════════════
# AGRO — BUYERS
# ═════════════════════════════════════════════
class BuyerIn(BaseModel):
    id: Optional[str] = None
    role: Optional[str] = "industry"
    name: str
    contact_mobile: Optional[str] = None
    contact_email: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    location: Optional[dict] = None
    address: Optional[str] = None
    accepts: Optional[list[str]] = None
    accepted_categories: Optional[list[str]] = None
    weekly_capacity_kg: Optional[float] = None
    max_rate_per_kg: Optional[float] = None
    max_moisture_pct: Optional[float] = None
    max_radius_km: Optional[float] = None
    demand: Optional[str] = None
    verified: bool = True


# ═════════════════════════════════════════════
# AGRO — PROFILES
# ═════════════════════════════════════════════
class ProfileIn(BaseModel):
    role: str
    name: Optional[str] = None
    display_name: Optional[str] = None
    mobile: Optional[str] = None
    email: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    location: Optional[dict] = None
    pincode: Optional[str] = None


# ═════════════════════════════════════════════
# AGRO — ESCROW
# ═════════════════════════════════════════════
class EscrowIn(BaseModel):
    listing_code: Optional[str] = None
    listingId: Optional[str] = None
    listing_id: Optional[str] = None
    milestone: str
    amount: float
    released_by: Optional[str] = None
    releasedBy: Optional[str] = None
    notes: Optional[str] = None


# ═════════════════════════════════════════════
# AGRO — BARTER
# ═════════════════════════════════════════════
class BarterIn(BaseModel):
    id: Optional[str] = None
    offeringCategory: Optional[str] = None
    offering_category: Optional[str] = None
    offeringMassKg: Optional[float] = None
    offering_mass_kg: Optional[float] = None
    offeringMoisture: Optional[float] = None
    targetLotId: Optional[str] = None
    target_listing_id: Optional[str] = None
    note: Optional[str] = None
    fromProfileId: Optional[str] = None
    fromName: Optional[str] = None


# ═════════════════════════════════════════════
# AGRO — PRODUCTS
# ═════════════════════════════════════════════
class ProductIn(BaseModel):
    id: Optional[str] = None
    title: str
    description: Optional[str] = None
    category: str
    price: float
    mrp: Optional[float] = None
    stockQuantity: Optional[int] = None
    stock_quantity: Optional[int] = None
    image: Optional[str] = None
    image_url: Optional[str] = None
    rating: Optional[float] = 0
    reviews: Optional[int] = 0
    bestseller: Optional[bool] = False
    carbonSavedKgCO2e: Optional[float] = None
    carbon_saved_kgco2e: Optional[float] = None
    rawBiomassUsedKg: Optional[float] = None
    raw_biomass_used_kg: Optional[float] = None
    rawWasteListingId: Optional[str] = None
    sourceFarmerOrMandi: Optional[str] = None
    source_mandi: Optional[str] = None
    originPickupAddress: Optional[str] = None
    originLat: Optional[float] = None
    originLng: Optional[float] = None
    artisanName: Optional[str] = None
    artisanLat: Optional[float] = None
    artisanLng: Optional[float] = None
    sellerId: Optional[str] = None
    seller_id: Optional[str] = None
    sellerName: Optional[str] = None
    seller_name: Optional[str] = None
    sellerVerified: Optional[bool] = None
    seller_verified: Optional[bool] = None


# ═════════════════════════════════════════════
# AGRO — STORE USERS
# ═════════════════════════════════════════════
class StoreUserIn(BaseModel):
    id: Optional[str] = None
    role: str
    name: str
    mobile: str
    email: Optional[str] = None
    pincode: Optional[str] = None
    shop_name: Optional[str] = None
    gst_number: Optional[str] = None
    seller_verified: Optional[bool] = None


# ═════════════════════════════════════════════
# AGRO — STORE ORDERS
# ═════════════════════════════════════════════
class StoreOrderIn(BaseModel):
    id: Optional[str] = None
    order_code: Optional[str] = None
    product_id: Optional[str] = None
    productId: Optional[str] = None
    product_title: Optional[str] = None
    productTitle: Optional[str] = None
    product_image: Optional[str] = None
    productImage: Optional[str] = None
    seller_id: Optional[str] = None
    sellerId: Optional[str] = None
    seller_name: Optional[str] = None
    sellerName: Optional[str] = None
    customer_id: Optional[str] = None
    customerId: Optional[str] = None
    customer_name: Optional[str] = None
    customerName: Optional[str] = None
    qty: int
    unit_price: Optional[float] = None
    unitPrice: Optional[float] = None
    total: float
    status: Optional[str] = "CONFIRMED"


# ═════════════════════════════════════════════
# INSTITUTIONAL — INSTITUTES
# ═════════════════════════════════════════════
class InstituteIn(BaseModel):
    id: Optional[str] = None
    code: Optional[str] = None
    name: str
    type: Optional[str] = "university"
    established_year: Optional[int] = None
    aishe_code: Optional[str] = None
    recognition: Optional[str] = None
    naac_grade: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pin_code: Optional[str] = None
    student_count: Optional[int] = None
    mess_name: Optional[str] = None
    admin_designation: Optional[str] = None
    admin_name: Optional[str] = None
    admin_email: Optional[str] = None
    admin_mobile: Optional[str] = None
    password_hash: Optional[str] = None
    location: Optional[dict] = None
    verified: bool = True


# ═════════════════════════════════════════════
# INSTITUTIONAL — SESSIONS
# ═════════════════════════════════════════════
class SessionIn(BaseModel):
    institute_id: str
    code: Optional[str] = None
    name: Optional[str] = None
    role: Optional[str] = None


# ═════════════════════════════════════════════
# INSTITUTIONAL — NGOS
# ═════════════════════════════════════════════
class NGOIn(BaseModel):
    id: Optional[str] = None
    name: str
    contact: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    city: Optional[str] = None
    address: Optional[str] = None
    capacity: int = 0
    base_eta_min: int = 15
    distance_km: Optional[float] = None
    coords: Optional[dict] = None
    verified: bool = True


# ═════════════════════════════════════════════
# INSTITUTIONAL — MEAL PLANS
# ═════════════════════════════════════════════
class MealPlanIn(BaseModel):
    id: Optional[str] = None
    institute_id: str
    date: Optional[str] = None
    plan_date: Optional[str] = None
    meal_slot: str
    predicted_demand: Optional[int] = None
    prepared_count: Optional[int] = None
    expected_waste_kg: Optional[float] = None
    waste_risk_score: Optional[int] = None
    variance_pct: Optional[float] = None
    menu_items: list[dict] = []
    weather_snapshot: Optional[dict] = None
    agent_suggested: Optional[bool] = False
    agent_headcount: Optional[int] = None
    agent_factors: Optional[list[dict]] = []
    status: Optional[str] = "DRAFT"
    dispatch_ready: Optional[bool] = False
    dispatch_ready_at: Optional[float] = None
    published_at: Optional[float] = None


# ═════════════════════════════════════════════
# INSTITUTIONAL — MEAL PREPS
# ═════════════════════════════════════════════
class MealPrepIn(BaseModel):
    id: Optional[str] = None
    institute_id: str
    plan_id: Optional[str] = None
    prepared_count: int
    agent_suggested_count: Optional[int] = None
    agent_factors: Optional[list[dict]] = []
    variance_pct: Optional[float] = None
    notes: Optional[str] = ""
    chef_verified_at: Optional[float] = None


# ═════════════════════════════════════════════
# INSTITUTIONAL — TALLIES
# ═════════════════════════════════════════════
class TallyIn(BaseModel):
    id: Optional[str] = None
    prep_id: str
    institute_id: str
    served_count: int = 0


# ═════════════════════════════════════════════
# INSTITUTIONAL — THERMAL
# ═════════════════════════════════════════════
class ThermalIn(BaseModel):
    prep_id: str
    institute_id: Optional[str] = None
    temp_c: Optional[float] = None
    state: Optional[str] = None
    hold_minutes: Optional[float] = None
    remaining_minutes: Optional[float] = None
    freshness_index: Optional[float] = None
    ready_for_dispatch: bool = False


# ═════════════════════════════════════════════
# INSTITUTIONAL — DISPATCHES
# ═════════════════════════════════════════════
class DispatchIn(BaseModel):
    institute_id: str
    prep_id: Optional[str] = None
    plan_id: Optional[str] = None
    ngo_id: Optional[str] = None
    ngo_name: str
    ngo_distance_km: Optional[float] = None
    ngo_contact: Optional[str] = None
    ngo_phone: Optional[str] = None
    ngo_email: Optional[str] = None
    meals_sent: int
    eta_minutes: Optional[int] = None
    category: Optional[str] = None
    temp_c: Optional[float] = None
    custody_officer: Optional[str] = None
    verified_at: Optional[float] = None


# ═════════════════════════════════════════════
# INSTITUTIONAL — ESG
# ═════════════════════════════════════════════
class ESGIn(BaseModel):
    institute_id: str
    dispatch_id: Optional[str] = None
    plan_id: Optional[str] = None
    meals_rescued: int = 0
    co2e_kg: float = 0
    water_l: int = 0
    cost_inr: float = 0
    manual_entry: bool = False
    recipient: Optional[str] = None
    notes: Optional[str] = None


# ═════════════════════════════════════════════
# PAYMENTS
# ═════════════════════════════════════════════
class PaymentOrderIn(BaseModel):
    amount: float
    currency: Optional[str] = "INR"
    receipt: Optional[str] = None
    notes: Optional[dict] = None


class PaymentVerifyIn(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str