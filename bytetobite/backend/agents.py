"""Six autonomous agents that power both grids.

  1. forecast_agent   — predicts tomorrow's headcount (Node 01)
  2. prep_agent       — recommends cooking count    (Node 02)
  3. waste_risk_agent — 0–100 risk score            (Node 01 + 02)
  4. thermal_agent    — freshness gate              (Node 04)
  5. dispatch_agent   — NGO ranking                 (Node 05)
  6. savings_agent    — ESG impact rollup           (Node 06)

Also exports `suggest_menu` and `anomaly_agent` helpers.
"""

from datetime import datetime, date
from typing import Optional
import math


# ═════════════════════════════════════════════
# CONSTANTS (shared with frontend mirrors)
# ═════════════════════════════════════════════
DAY_WEIGHTS = {0: -0.06, 1: 0.00, 2: 0.00, 3: 0.01, 4: 0.01, 5: 0.08, 6: 0.06}
MEAL_BASE = {"breakfast": 0.62, "lunch": 1.00, "dinner": 0.88}

MENU_LIBRARY = [
    {"name": "Dal Tadka + Rice",     "category": "staple",    "perishability": 0.35, "kcal": 520, "cost_inr": 22},
    {"name": "Veg Pulao",            "category": "staple",    "perishability": 0.40, "kcal": 610, "cost_inr": 28},
    {"name": "Roti + Mixed Veg",     "category": "staple",    "perishability": 0.30, "kcal": 480, "cost_inr": 20},
    {"name": "Rajma Chawal",         "category": "protein",   "perishability": 0.45, "kcal": 640, "cost_inr": 32},
    {"name": "Chole Bhature",        "category": "festive",   "perishability": 0.55, "kcal": 780, "cost_inr": 42},
    {"name": "Paneer Butter Masala", "category": "protein",   "perishability": 0.60, "kcal": 700, "cost_inr": 55},
    {"name": "Idli + Sambar",        "category": "south",     "perishability": 0.25, "kcal": 380, "cost_inr": 18},
    {"name": "Poha + Sev",           "category": "breakfast", "perishability": 0.20, "kcal": 350, "cost_inr": 15},
    {"name": "Upma",                 "category": "breakfast", "perishability": 0.22, "kcal": 320, "cost_inr": 14},
    {"name": "Curd Rice",            "category": "light",     "perishability": 0.65, "kcal": 300, "cost_inr": 16},
    {"name": "Khichdi",              "category": "light",     "perishability": 0.30, "kcal": 420, "cost_inr": 19},
    {"name": "Chicken Curry + Rice", "category": "nonveg",    "perishability": 0.75, "kcal": 720, "cost_inr": 62},
    {"name": "Egg Curry + Rice",     "category": "nonveg",    "perishability": 0.70, "kcal": 560, "cost_inr": 38},
    {"name": "Fruit Bowl",           "category": "dessert",   "perishability": 0.85, "kcal": 180, "cost_inr": 24},
    {"name": "Kheer",                "category": "dessert",   "perishability": 0.72, "kcal": 340, "cost_inr": 26},
]


# ═════════════════════════════════════════════
# SMALL UTILITIES
# ═════════════════════════════════════════════
def _stdev(arr: list[float]) -> float:
    if len(arr) < 2:
        return 0.0
    mean = sum(arr) / len(arr)
    return math.sqrt(sum((v - mean) ** 2 for v in arr) / len(arr))


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _dow_short(dow: int) -> str:
    return ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][dow]


# ═════════════════════════════════════════════
# 1. FORECAST AGENT
# ═════════════════════════════════════════════
def forecast_agent(
    historical_plans: list[dict],
    plan_date: str,
    meal_slot: str,
    weather_factor: float = 0.0,
    exam_window: bool = False,
    event: bool = False,
) -> dict:
    """Predict tomorrow's headcount from history + context signals."""
    base = 1000
    if historical_plans:
        base = int(
            sum(p.get("predicted_demand") or 0 for p in historical_plans)
            / len(historical_plans)
        )

    try:
        d = datetime.fromisoformat(plan_date)
        dow = d.weekday()
    except Exception:
        dow = 1  # Tuesday fallback

    day_factor = DAY_WEIGHTS.get(dow, 0.0)
    meal_factor = MEAL_BASE.get(meal_slot, 1.0)
    exam_factor = -0.12 if exam_window else 0.0
    event_factor = 0.25 if event else 0.0

    total_mult = (
        (1 + day_factor)
        * meal_factor
        * (1 + weather_factor)
        * (1 + exam_factor)
        * (1 + event_factor)
    )
    suggested = max(50, int(base * total_mult))

    variance = 0.18
    if len(historical_plans) > 1:
        variance = _stdev([p.get("predicted_demand") or 0 for p in historical_plans]) / (base or 1)
    confidence = _clamp(1 - variance, 0.55, 0.96)

    factors = []
    if day_factor:
        factors.append({"label": _dow_short(dow), "delta_pct": round(day_factor * 100)})
    if meal_factor != 1:
        factors.append({"label": f"{meal_slot} baseline", "delta_pct": round((meal_factor - 1) * 100)})
    if weather_factor:
        factors.append({"label": "Weather", "delta_pct": round(weather_factor * 100)})
    if exam_factor:
        factors.append({"label": "Exam window", "delta_pct": round(exam_factor * 100)})
    if event_factor:
        factors.append({"label": "Campus event", "delta_pct": round(event_factor * 100)})
    if not factors:
        factors.append({"label": "Rolling 7-day avg", "delta_pct": 0})

    return {
        "suggested_headcount": suggested,
        "base_headcount": base,
        "confidence": round(confidence, 2),
        "factors": factors,
    }


# ═════════════════════════════════════════════
# 2. PREP AGENT
# ═════════════════════════════════════════════
def prep_agent(plans: list[dict], plan: dict) -> dict:
    """Recommend how many plates to actually cook."""
    planned = plan.get("predicted_demand") or 0
    completed = [
        p for p in plans
        if p.get("status") == "COMPLETED" and p.get("prepared_count")
    ]
    factors = []
    factor = 1.0

    if len(completed) >= 2:
        ratios = [
            (p.get("prepared_count") or 0) / max(1, p.get("predicted_demand") or 1)
            for p in completed[:10]
        ]
        avg_ratio = sum(ratios) / len(ratios)
        drift = avg_ratio - 1
        factors.append({"label": "Historic prep drift", "delta_pct": round(drift * 100)})
        factor *= (1 + drift * 0.5)

    try:
        d = datetime.fromisoformat(
            plan.get("plan_date") or plan.get("date") or date.today().isoformat()
        )
        dow = d.weekday()
        dow_adj = {0: -0.04, 1: 0.0, 2: 0.0, 3: 0.01, 4: 0.01, 5: 0.05, 6: 0.03}.get(dow, 0)
        if dow_adj:
            factor *= (1 + dow_adj)
            factors.append({"label": _dow_short(dow), "delta_pct": round(dow_adj * 100)})
    except Exception:
        pass

    items = plan.get("menu_items") or []
    if items:
        perish_avg = sum(it.get("perishability", 0.4) for it in items) / len(items)
        perish_adj = -(perish_avg - 0.4) * 0.15
        if abs(perish_adj) > 0.005:
            factor *= (1 + perish_adj)
            factors.append({"label": "Menu perishability", "delta_pct": round(perish_adj * 100)})

    suggested = max(10, int(planned * factor))
    return {"suggested": suggested, "planned": planned, "factors": factors}


# ═════════════════════════════════════════════
# 3. WASTE RISK AGENT
# ═════════════════════════════════════════════
def waste_risk_agent(
    plans: list[dict],
    planned_headcount: int,
    menu_items: list[dict],
) -> int:
    """Score 0–100. Higher = more likely to waste food."""
    with_prep = [p for p in plans if p.get("prepared_count")]
    if with_prep:
        prep_avg = sum(p.get("prepared_count") or 0 for p in with_prep) / len(with_prep)
    else:
        prep_avg = planned_headcount

    delta = abs(planned_headcount - prep_avg) / max(1, prep_avg)

    if menu_items:
        perish_avg = sum(it.get("perishability", 0.4) for it in menu_items) / len(menu_items)
    else:
        perish_avg = 0.4

    historic = [
        max(0, p.get("variance_pct", 0))
        for p in plans
        if p.get("variance_pct") is not None
    ][:7]
    waste_rate = (sum(historic) / len(historic) / 100) if historic else 0.12

    score = _clamp(delta * 45 + perish_avg * 35 + waste_rate * 100 * 0.20, 0, 100)
    return round(score)


# ═════════════════════════════════════════════
# 4. MENU SUGGESTION
# ═════════════════════════════════════════════
def suggest_menu(inventory: list[dict], count: int = 4) -> list[dict]:
    """Rank MENU_LIBRARY by reuse + cost + shelf-stability."""
    inv_map = {i.get("name", "").lower(): i for i in inventory}
    scored = []
    for item in MENU_LIBRARY:
        have = inv_map.get(item["name"].lower())
        reuse_score = 1 if have else 0
        cost_score = 1 - _clamp(item["cost_inr"] / 80, 0, 1)
        perf_score = 1 - item["perishability"]
        score = reuse_score * 0.5 + cost_score * 0.3 + perf_score * 0.2
        scored.append({**item, "score": round(score, 2), "reuse": bool(have)})
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:count]


# ═════════════════════════════════════════════
# 5. ANOMALY DETECTOR
# ═════════════════════════════════════════════
def anomaly_agent(planned: int, suggested: int) -> Optional[dict]:
    """Flag if the operator's plan is far from the agent's suggestion."""
    if not suggested:
        return None
    delta = (planned - suggested) / suggested
    if abs(delta) < 0.15:
        return None
    severity = "high" if abs(delta) > 0.35 else "medium"
    return {
        "severity": severity,
        "delta_pct": round(delta * 100),
        "message": (
            f"Planning {round(delta * 100)}% above agent suggestion — likely surplus."
            if delta > 0 else
            f"Planning {abs(round(delta * 100))}% below agent suggestion — possible shortage."
        ),
    }


# ═════════════════════════════════════════════
# 6. THERMAL AGENT
# ═════════════════════════════════════════════
def thermal_agent(
    hold_minutes: float,
    shelf_life: float,
    ambient_temp_c: float,
    surplus: int,
    unit_cost: float = 45.0,
    co2_per_meal: float = 0.42,
) -> dict:
    """Node 04 freshness gate: is this batch still safe to donate?"""
    thermal_mult = 1.0 + max(0, (ambient_temp_c - 25) / 10) * 0.25
    effective_hold = hold_minutes * thermal_mult
    remaining = max(0, shelf_life - effective_hold)
    freshness = _clamp(remaining / shelf_life, 0, 1) if shelf_life > 0 else 0

    if freshness < 0.20 or remaining <= 0:
        quality = {"code": "EXPIRED", "label": "Cold / Unsafe — send to compost", "color": "#ef4444"}
    elif freshness < 0.60:
        quality = {"code": "URGENT", "label": "Send Immediately", "color": "#f59e0b"}
    else:
        quality = {"code": "FRESH", "label": "Fresh & Good", "color": "#10b981"}

    is_rescuable = freshness >= 0.20 and remaining > 0
    meals_rescued = surplus if is_rescuable else 0

    return {
        "thermal_multiplier": round(thermal_mult, 3),
        "effective_hold": round(effective_hold, 1),
        "remaining_minutes": round(remaining, 1),
        "freshness_index": round(freshness, 3),
        "freshness_percent": round(freshness * 100),
        "quality": quality,
        "meals_rescued": meals_rescued,
        "value_inr": meals_rescued * unit_cost,
        "co2_kg": round(meals_rescued * co2_per_meal, 2),
        "can_mark_ready": quality["code"] != "EXPIRED" and surplus > 0,
    }


# ═════════════════════════════════════════════
# 7. DISPATCH AGENT
# ═════════════════════════════════════════════
def dispatch_agent(ngos: list[dict], plates: int, max_safe_minutes: int) -> list[dict]:
    """Rank NGOs by feasibility + capacity + distance."""
    scored = []
    for n in ngos:
        eta = n.get("base_eta_min", 15)
        if eta > max_safe_minutes:
            status = "INFEASIBLE"
        elif eta > max_safe_minutes * 0.6:
            status = "URGENT"
        else:
            status = "OPTIMAL"

        capacity_match = n.get("capacity", 0) >= plates
        score = (
            (100 if status == "OPTIMAL" else 60 if status == "URGENT" else 0)
            + (40 if capacity_match else 0)
            - n.get("distance_km", 0) * 2
        )
        scored.append({
            **n,
            "status": status,
            "capacity_match": capacity_match,
            "score": round(score, 1),
        })
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored


# ═════════════════════════════════════════════
# 8. SAVINGS AGENT
# ═════════════════════════════════════════════
def savings_agent(dispatches: list[dict], esg_entries: list[dict]) -> dict:
    """Node 06 rollup: kg rescued, CO₂e, water, ₹, diversion %."""
    if esg_entries:
        rescued = sum(e.get("meals_rescued", 0) for e in esg_entries)
        co2 = sum(e.get("co2e_kg", 0) for e in esg_entries)
        water = sum(e.get("water_l", 0) for e in esg_entries)
        value = sum(e.get("cost_inr", 0) for e in esg_entries)
        baseline = rescued * 1.08
    else:
        rescued = sum(d.get("meals_sent", 0) for d in dispatches)
        co2 = rescued * 1.05
        water = rescued * 180
        value = rescued * 45
        baseline = rescued * 1.08

    diversion = (
        round((rescued / baseline) * 100, 1)
        if baseline > 0
        else (100.0 if rescued > 0 else 0.0)
    )

    return {
        "rescuedMeals": rescued,
        "unoptimizedSurplus": int(baseline),
        "divertedMassKg": round(rescued * 0.4, 1),
        "costRecoveredINR": value,
        "scope3CO2eAvertedKg": round(co2, 2),
        "waterPreservedLiters": water,
        "diversionRate": diversion,
    }