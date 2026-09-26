"""WebSocket hubs — one per grid.

Two independent broadcasters:
  agro_hub          →  /ws                 (listings, buyers, profiles, escrow, barter,
                                             products, orders, cart, wishlist, payments)
  institutional_hub →  /ws/institutional   (institutes, sessions, ngos, meal_plans,
                                             meal_preps, tallies, thermal, dispatches, esg)

Any backend file can `await agro_hub.emit("listings-changed")` and every
connected client (browser or mobile) receives the event instantly.
"""

from typing import Optional
from fastapi import WebSocket


# ═════════════════════════════════════════════
# HUB
# ═════════════════════════════════════════════
class Hub:
    """A simple fan-out broadcaster. No auth, no rooms — one grid per hub."""

    def __init__(self, name: str = "hub"):
        self.name = name
        self.clients: list[WebSocket] = []
        self.last_event: Optional[dict] = None

    # ─────────────────────────────────────────
    # LIFECYCLE
    # ─────────────────────────────────────────
    async def connect(self, ws: WebSocket) -> None:
        """Accept a socket and add it to the fan-out list."""
        await ws.accept()
        self.clients.append(ws)
        # Replay the last event so a late-joining client catches up.
        if self.last_event is not None:
            try:
                await ws.send_json(self.last_event)
            except Exception:
                self.disconnect(ws)

    def disconnect(self, ws: WebSocket) -> None:
        """Remove a socket from the list (idempotent)."""
        if ws in self.clients:
            self.clients.remove(ws)

    # ─────────────────────────────────────────
    # BROADCAST
    # ─────────────────────────────────────────
    async def emit(self, event: str, payload: Optional[dict] = None) -> None:
        """Fan out `{type, payload}` to every client. Prunes dead sockets."""
        message = {"type": event, "payload": payload or {}}
        self.last_event = message

        dead: list[WebSocket] = []
        for client in self.clients:
            try:
                await client.send_json(message)
            except Exception:
                dead.append(client)

        for d in dead:
            self.disconnect(d)

    # ─────────────────────────────────────────
    # INTROSPECTION
    # ─────────────────────────────────────────
    def size(self) -> int:
        """How many clients are currently connected."""
        return len(self.clients)

    def snapshot(self) -> dict:
        """Debug helper — returns hub state for /health or admin endpoints."""
        return {
            "name": self.name,
            "clients": len(self.clients),
            "last_event": (self.last_event or {}).get("type"),
        }


# ═════════════════════════════════════════════
# TWO HUBS — ONE PER GRID
# ═════════════════════════════════════════════
agro_hub = Hub(name="agro")
institutional_hub = Hub(name="institutional")


# ═════════════════════════════════════════════
# EVENT NAME CONSTANTS
# ═════════════════════════════════════════════
# Agro grid
AGRO_LISTINGS_CHANGED   = "listings-changed"
AGRO_BUYERS_CHANGED     = "buyers-changed"
AGRO_PROFILES_CHANGED   = "profiles-changed"
AGRO_ESCROW_CHANGED     = "escrow-changed"
AGRO_BARTER_CHANGED     = "barter-changed"
AGRO_PRODUCTS_CHANGED   = "products-changed"
AGRO_USERS_CHANGED      = "store-users-changed"
AGRO_ORDERS_CHANGED     = "orders-changed"
AGRO_CART_CHANGED       = "cart-changed"
AGRO_WISHLIST_CHANGED   = "wishlist-changed"
AGRO_PAYMENTS_CHANGED   = "payments-changed"

# Institutional grid
INST_INSTITUTES_CHANGED = "institutes-changed"
INST_SESSION_CHANGED    = "session-changed"
INST_NGOS_CHANGED       = "ngos-changed"
INST_PLANS_CHANGED      = "meal-plans-changed"
INST_PREPS_CHANGED      = "meal-preps-changed"
INST_TALLIES_CHANGED    = "tallies-changed"
INST_THERMAL_CHANGED    = "thermal-changed"
INST_DISPATCHES_CHANGED = "dispatches-changed"
INST_ESG_CHANGED        = "esg-changed"
