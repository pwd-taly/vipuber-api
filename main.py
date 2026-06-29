"""
VipUber Booking API — Finalized, AI-agent-ready REST layer.

A reverse-engineered REST API for the VipUber transfer booking platform.
Translates modern JSON API calls into legacy PHP form POSTs with automatic
captcha solving, session management, and HTML→JSON response parsing.

Usage:
    # Set credentials in .env or environment, then:
    uvicorn main:app --host 0.0.0.0 --port 8222 --reload
"""

from __future__ import annotations
import re
import time
import hashlib
import threading
from contextlib import asynccontextmanager
from collections import defaultdict

from fastapi import FastAPI, HTTPException, Request, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import secrets

from config import get_settings, setup_logging
from session import SessionError, VipUberSession, get_session, login as do_login
from models import (
    LoginRequest,
    CalculateRequest,
    ConfirmRequest,
    BookTransferRequest,
    ApprovalDetailRequest,
    PasswordChangeRequest,
    ProxyPostRequest,
    LOCATION_IDS,
    LOCATION_NAMES,
)
import parsers

# ── Double-booking prevention ─────────────────────────

# Cache of recently submitted booking hashes to prevent duplicates
_booking_dedup: dict[str, float] = {}
_booking_dedup_lock = threading.Lock()
_DEDUP_WINDOW_SECONDS = 300  # 5-minute window
_MAX_DEDUP_ENTRIES = 1000

def _is_duplicate_booking(pickup: str, dest: str, date: str, time: str,
                          first_name: str, last_name: str, phone: str) -> bool:
    """Check if an identical booking was submitted recently.

    Thread-safe: all access to _booking_dedup is serialized.
    """
    fingerprint = hashlib.sha256(
        f"{pickup}|{dest}|{date}|{time}|{first_name}|{last_name}|{phone}".encode()
    ).hexdigest()
    now = time.time()

    with _booking_dedup_lock:
        # Purge expired entries
        stale = [k for k, ts in _booking_dedup.items() if now - ts > _DEDUP_WINDOW_SECONDS]
        for k in stale:
            _booking_dedup.pop(k, None)

        if fingerprint in _booking_dedup:
            return True

        # Enforce max size
        if len(_booking_dedup) >= _MAX_DEDUP_ENTRIES:
            oldest = min(_booking_dedup, key=_booking_dedup.get)
            _booking_dedup.pop(oldest, None)

        _booking_dedup[fingerprint] = now
        return False

# ── Turkish-aware uppercase ─────────────────────────────

def turkish_upper(s: str) -> str:
    """Turkish-aware uppercase: maps 'i' → 'İ' before standard upper()."""
    return s.replace("i", "İ").upper()


# ── Setup ─────────────────────────────────────────────

log = setup_logging()
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.validate()
    log.info("VipUber Booking API starting — %d locations mapped", len(LOCATION_IDS))
    yield
    log.info("VipUber Booking API shutting down")


app = FastAPI(
    title="VipUber Booking API",
    description="""
An intelligent REST layer for the VipUber transfer platform —
reverse-engineered, captcha-aware, and ready for AI integration.

## AI Agent Quick Start

```python
import requests

API = "http://localhost:8222"

# 1. Login (captcha solved automatically)
r = requests.post(f"{API}/login", json={"email": "...", "password": "..."})
print(r.json())

# 2. Book a transfer in one call
booking = {
    "pickup": "İSTANBUL HAVALİMANI",
    "destination": "BEŞİKTAŞ",
    "date": "25.06.2026",
    "time": "04:30",
    "first_name": "Leo",
    "last_name": "Batista",
    "phone": "+905551234567",
    "passenger_count": 1,
    "payment_method": "1"
}
r = requests.post(f"{API}/book-transfer", json=booking)
print(r.json())
```

Full docs at /docs (Swagger) or /redoc.
    """,
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    contact={
        "name": "VipUber API",
        "url": "https://github.com/your-org/vipuber-api",
    },
)

# ── CORS — restricted; native apps don't need it, browsers do ──
# If a web client needs access, add its origin here.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://vipuber-api.onrender.com",  # Swagger docs
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["X-API-Key", "Content-Type"],
)

_rate_limits: dict[str, list[float]] = defaultdict(list)
_RATE_WINDOW = 60     # seconds
_RATE_MAX = 30        # requests per window

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    window = _rate_limits[client_ip]
    # Purge old entries
    _rate_limits[client_ip] = [t for t in window if now - t < _RATE_WINDOW]
    if len(_rate_limits[client_ip]) >= _RATE_MAX:
        return JSONResponse(
            status_code=429,
            content={"detail": "Too many requests. Slow down."},
        )
    _rate_limits[client_ip].append(now)
    return await call_next(request)

# ── API key auth ─────────────────────────────────────

PUBLIC_PATHS = {
    "/health",
    "/docs",
    "/openapi.json",
    "/redoc",
}


def _is_public_path(path: str) -> bool:
    return path in PUBLIC_PATHS or path.startswith("/docs/") or path.startswith("/redoc/")


async def verify_api_key(request: Request):
    """Require the configured API key for every protected endpoint."""
    if not settings.api_key:
        raise HTTPException(
            status_code=503,
            detail="API_KEY is not configured on the server",
        )
    key = request.headers.get("X-API-Key", "")
    if secrets.compare_digest(key, settings.api_key):
        return True
    raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key header")


@app.middleware("http")
async def enforce_api_key(request: Request, call_next):
    if request.method == "OPTIONS" or _is_public_path(request.url.path):
        return await call_next(request)

    try:
        await verify_api_key(request)
    except HTTPException as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
        )
    return await call_next(request)


def _get_session_or_raise(email: str = None, password: str = None) -> VipUberSession:
    """Get the session; auto-login if needed."""
    try:
        s = get_session(email, password)
        s.ensure_login()
        return s
    except SessionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


# ── Global exception handler ─────────────────────────


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    log.error("Unhandled error on %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(
        status_code=500,
        content={"status": "error", "message": f"Internal server error: {exc}"},
    )


# ===================================================================
#  HEALTH & INFO
# ===================================================================


@app.get("/health", tags=["System"])
def health_check():
    """Verify the API is running and configured."""
    cfg_ok = bool(settings.email and settings.password)
    return {
        "status": "ok" if cfg_ok else "degraded",
        "version": "2.0.0",
        "configured": cfg_ok,
        "locations_count": len(LOCATION_IDS),
        "server": settings.base_url,
    }


@app.get("/locations", tags=["System"])
def list_locations():
    """List all available location zones with their IDs."""
    return {
        "status": "ok",
        "locations": [
            {"id": vid, "name": vname}
            for vname, vid in sorted(LOCATION_IDS.items(), key=lambda x: int(x[1]))
        ],
    }


# ===================================================================
#  AUTH
# ===================================================================


@app.post(
    "/login",
    tags=["Auth"],
    summary="Login with captcha solving",
    description="Authenticate with email/password. The captcha is solved automatically via OCR. "
    "Session is maintained server-side — no tokens needed for subsequent calls.",
)
def login(req: LoginRequest):
    try:
        result = do_login(req.email, req.password)
        return result
    except SessionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


# ===================================================================
#  BOOKING — The Main Event
# ===================================================================


@app.get(
    "/reservation/search-customer",
    tags=["Booking"],
    summary="Search customers",
)
def search_customer(q: str = ""):
    s = _get_session_or_raise()
    html = s.post("/modul/rezer/ara.php?cari=447", {"kelime": q})
    customers = parsers.parse_customer_search(html)
    return {"status": "ok", "customers": customers, "html": html if not customers else None}


@app.post(
    "/reservation/calculate",
    tags=["Booking"],
    summary="Calculate route pricing",
    description="Get vehicle options and pricing for a route. Returns available vehicles with prices.",
)
def calculate_reservation(req: CalculateRequest):
    s = _get_session_or_raise()
    html = s.post("/modul/rezer/ajax.php", {
        "alis": req.pickup_id,
        "varis": req.destination_id,
        "hizmeti": req.service_type,
        "cari": req.customer_id,
        "kur": req.currency,
        "yolcu": str(req.passenger_count),
    })
    vehicles = parsers.parse_vehicle_options(html)
    return {
        "status": "ok",
        "vehicles": vehicles,
        "vehicle_count": len(vehicles),
        "pickup_name": LOCATION_NAMES.get(req.pickup_id, req.pickup_id),
        "destination_name": LOCATION_NAMES.get(req.destination_id, req.destination_id),
    }


@app.post(
    "/reservation/confirm",
    tags=["Booking"],
    summary="Confirm reservation and begin finalization",
)
def confirm_reservation(req: ConfirmRequest):
    s = _get_session_or_raise()
    html = s.post("/modul/rezer/tamamla.php", {"yolcu": str(req.passenger_count)})
    return {"status": "ok", "message": "Reservation confirmed, ready for finalization"}


@app.post(
    "/reservation/finalize",
    tags=["Booking"],
    summary="Final submit with all reservation fields",
    description="Send the complete payload to create the reservation. "
    "This is the final step after calculate → confirm.",
)
def finalize_reservation(data: dict):
    s = _get_session_or_raise()
    # Ensure extra services defaults are present
    for i in range(50):
        data.setdefault(f"eki{i}", "")
        data.setdefault(f"ekiucret{i}", "0")
        data.setdefault(f"ekiadet{i}", "0")
    html = s.post("/modul/rezer/ajaxislem.php", data)
    result = parsers.parse_booking_message(html)
    return result


@app.get(
    "/reservation/passenger-form",
    tags=["Booking"],
    summary="Get passenger form HTML",
)
def passenger_form(yolcu: str = "1"):
    s = _get_session_or_raise()
    html = s.post("/modul/rezer/ajaxyolcu.php", {"yolcu": yolcu})
    return {"status": "ok", "html": html}


@app.get(
    "/reservation/search-company",
    tags=["Booking"],
    summary="Search external companies",
)
def search_company(q: str = ""):
    s = _get_session_or_raise()
    html = s.post("/modul/rezer/aradis.php", {"kelime": q})
    return {"status": "ok", "options": parsers.parse_customer_search(html), "html": html}


@app.get(
    "/reservation/search-plate",
    tags=["Booking"],
    summary="Search license plates",
)
def search_plate(q: str = ""):
    s = _get_session_or_raise()
    html = s.post("/modul/rezer/aradisplaka.php", {"kelime": q})
    return {"status": "ok", "html": html}


# ── ONE-CALL BOOKING ─────────────────────────────────


@app.post(
    "/book-transfer",
    tags=["Booking"],
    summary="One-call booking (login → price → confirm → submit)",
    description="Complete the entire booking pipeline in a single API call. "
    "This is the primary endpoint for AI agents — pass all details at once and "
    "the API handles login (if needed), pricing, vehicle selection, confirmation, and final submission.",
)
def book_transfer(req: BookTransferRequest):
    """Complete the entire booking pipeline in a single API call.

    Includes double-booking prevention: identical bookings within 5 minutes are rejected.
    """
    s = _get_session_or_raise()
    settings = get_settings()

    # ── Double-booking guard ──────────────────────────
    if _is_duplicate_booking(
        req.pickup, req.destination, req.date, req.time,
        req.first_name, req.last_name, req.phone,
    ):
        raise HTTPException(
            status_code=409,
            detail="Duplicate booking detected. An identical booking was submitted "
                   f"within the last {_DEDUP_WINDOW_SECONDS // 60} minutes. "
                   "If this is intentional, change a field (e.g. passenger name) "
                   "or wait before retrying.",
        )

    # ── Required-field validation ─────────────────────
    missing = []
    if not req.date:
        missing.append("date (DD.MM.YYYY)")
    if not req.time:
        missing.append("time (HH:MM)")
    if not req.first_name:
        missing.append("first_name")
    if not req.last_name:
        missing.append("last_name")
    if not req.phone:
        missing.append("phone")
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"Missing required fields: {', '.join(missing)}",
        )

    # Resolve location IDs
    pickup_id = LOCATION_IDS.get(turkish_upper(req.pickup), req.pickup)
    dest_id = LOCATION_IDS.get(turkish_upper(req.destination), req.destination)

    cid = settings.customer_id

    # Step 1: Calculate pricing → get vehicle options (optional - uses defaults if unavailable)
    calc_html = s.post("/modul/rezer/ajax.php", {
        "alis": pickup_id,
        "varis": dest_id,
        "hizmeti": "tek",
        "cari": cid,
        "kur": req.currency,
        "yolcu": str(req.passenger_count),
    })
    vehicles = parsers.parse_vehicle_options(calc_html)

    # Select vehicle (user-specified, auto-selected, or error)
    selected_vehicle = None
    if req.vehicle_id:
        selected_vehicle = next((v for v in vehicles if v["id"] == req.vehicle_id), None)
        if not selected_vehicle:
            # User requested a specific vehicle not in pricing response —
            # use it directly with a placeholder; price will come from the server
            selected_vehicle = {
                "id": req.vehicle_id,
                "name": f"Vehicle {req.vehicle_id}",
                "price": None,
                "currency": req.currency or "1",
            }
    if not selected_vehicle and vehicles:
        selected_vehicle = next(
            (v for v in vehicles if v["is_selected"]),
            vehicles[0],
        )
    if not selected_vehicle:
        raise HTTPException(
            status_code=502,
            detail="No vehicles available for this route. The pricing endpoint "
                   "returned no vehicle options. Try specifying a vehicle_id directly "
                   "or verify the pickup/destination IDs.",
        )

    vid = selected_vehicle["id"]
    vname = selected_vehicle["name"]
    vprice = selected_vehicle.get("price")  # None until server confirms

    # Step 2: Confirm (tamamla → triggers baslattir on the JS side)
    tamamla_html = s.post("/modul/rezer/tamamla.php", {
        "yolcu": str(req.passenger_count),
    })

    # Step 3: Build the massive final payload
    hotel_id = req.hotel_id or cid
    payload = {
        # Date/Time
        "alistarihi": req.date,
        "alissaati": req.time,
        "donus": "1" if req.return_trip else "0",
        "donustarihi": req.return_date if req.return_trip else "",
        "donussaati": req.return_time if req.return_trip else "",
        "bitistarih": req.return_date if req.return_trip else "",
        "bitissaat": req.return_time if req.return_trip else "",
        # Flight
        "ucusno": req.flight,
        "ducusno": req.return_flight if req.return_trip else "",
        "havayolu": "",
        # Route
        "anokta": str(pickup_id),
        "bnokta": str(dest_id),
        "alisyeri": turkish_upper(req.pickup),
        "varisyeri": turkish_upper(req.destination),
        "nereden": req.pickup_address,
        "nereye": req.destination_address,
        # Passenger
        "adsoyad": req.first_name,
        "soyad": req.last_name,
        "tcno": req.tc_no or "",
        "gsm": req.phone or "",
        "mail": req.email or "",
        "ulke": req.nationality or "TR",
        "odano": req.room_no or "",
        "cepulke": "90",
        # Vehicle & Pricing (let server auto-calculate)
        "aracid": vid,
        "aracadi": vname,
        "kur": req.currency,
        "yetiskin": str(req.passenger_count),
        "cocuk": "0",
        "etsucret": "0",
        # Notes
        "not": req.notes,
        # Customer
        "cari": cid,
        "musteri": cid,
        "otel": hotel_id,
        "hizmeti": "tek",
        "hizmetturu": "TEK YON",
        # Payment
        "odeme": req.payment_method,
        "odemesekli": req.payment_method,
        "odemetur": req.payment_method,
        # Status
        "durumu": "1",
        "uetdsle": "2",
        "sofor": "",
        "plaka": "",
        "koruma": "",
        "komisyon": "",
        "yolcu": str(req.passenger_count),
    }

    # Extra services (50 slots, all empty)
    for i in range(50):
        payload[f"eki{i}"] = ""
        payload[f"ekiucret{i}"] = "0"
        payload[f"ekiadet{i}"] = "0"

    # Step 4: Final submit
    result_html = s.post("/modul/rezer/ajaxislem.php", payload)

    # Parse result
    result = parsers.parse_booking_message(result_html)

    # Try to fetch real price from reservation detail
    tracking = result.get("tracking_code")
    display_price = None
    display_price_source = None
    if tracking:
        try:
            detail_html = s.post(
                f"/modul/index/detay.php?islem=ajax&i=onayBekleyen",
                {"musteriId": tracking},
            )
            detail = parsers.parse_reservation_detail(detail_html)
            for key, val in detail.items():
                kl = key.lower()
                if "grand total" in kl or "toplam" in kl or "vehicle price" in kl:
                    raw = re.sub(r'[^\d.,]', '', val)
                    if raw and float(raw.replace(",", ".")) > 0:
                        display_price = val
                        display_price_source = "server"
                        break
        except Exception:
            pass

    # No fake pricing: if the server didn't return a price, report it honestly
    if not display_price:
        display_price = "Price unavailable — check reservation detail"
        display_price_source = "unavailable"

    return {
        "status": result.get("status", "submitted"),
        "message": result.get("message", "Booking submitted"),
        "tracking_code": result.get("tracking_code"),
        "booking": {
            "pickup": req.pickup,
            "destination": req.destination,
            "date": req.date,
            "time": req.time,
            "vehicle": vname,
            "price": display_price,
            "passenger": f"{req.first_name} {req.last_name}".strip(),
            "passenger_count": req.passenger_count,
        },
    }


# ===================================================================
#  APPROVALS
# ===================================================================


@app.get(
    "/approvals/pending",
    tags=["Approvals"],
    summary="List pending reservations",
)
def pending_approvals(ilkt: str = "", sont: str = "", odeme: str = ""):
    s = _get_session_or_raise()
    params = {"i": "onayBekleyen"}
    if ilkt: params["ilkt"] = ilkt
    if sont: params["sont"] = sont
    if odeme: params["odeme"] = odeme
    html = s.get("/", params)
    reservations = parsers.parse_reservation_list(html)
    return {
        "status": "ok",
        "count": len(reservations),
        "reservations": reservations,
    }


@app.get(
    "/approvals/approved",
    tags=["Approvals"],
    summary="List approved reservations",
)
def approved_list(ilkt: str = "", sont: str = "", odeme: str = ""):
    s = _get_session_or_raise()
    params = {"i": "onayLi"}
    if ilkt: params["ilkt"] = ilkt
    if sont: params["sont"] = sont
    if odeme: params["odeme"] = odeme
    html = s.get("/", params)
    reservations = parsers.parse_reservation_list(html)
    return {
        "status": "ok",
        "count": len(reservations),
        "reservations": reservations,
    }


@app.post(
    "/approvals/detail",
    tags=["Approvals"],
    summary="View reservation details",
)
def approval_detail(req: ApprovalDetailRequest):
    s = _get_session_or_raise()
    html = s.post(
        f"/modul/index/detay.php?islem=ajax&i={req.status}",
        {"musteriId": req.musteriId},
    )
    detail = parsers.parse_reservation_detail(html)
    return {"status": "ok", "detail": detail, "reservation_id": req.musteriId}


@app.post(
    "/approvals/distance-detail",
    tags=["Approvals"],
    summary="View route distance details",
)
def approval_distance_detail(req: ApprovalDetailRequest):
    s = _get_session_or_raise()
    html = s.post(
        f"/modul/index/disteday.php?islem=ajax&i={req.status}",
        {"musteriId": req.musteriId},
    )
    return {"status": "ok", "html": html}


# ===================================================================
#  REPORTS
# ===================================================================


@app.get(
    "/reports/search",
    tags=["Reports"],
    summary="Search all reservations",
)
def search_report(ilkt: str = "", sont: str = "", odeme: str = "", fkul: str = ""):
    s = _get_session_or_raise()
    params = {"i": "trapor"}
    if ilkt: params["ilkt"] = ilkt
    if sont: params["sont"] = sont
    if odeme: params["odeme"] = odeme
    if fkul: params["fkul"] = fkul
    html = s.get("/", params)
    reservations = parsers.parse_reservation_list(html)
    return {
        "status": "ok",
        "count": len(reservations),
        "reservations": reservations,
    }


@app.get(
    "/reports/search-ajax",
    tags=["Reports"],
    summary="Search via AJAX endpoint",
)
def search_report_ajax(firma: str = ""):
    s = _get_session_or_raise()
    html = s.post("/modul/rapor/ara.php", {"i": "trapor", "firma": firma})
    return {"status": "ok", "html": html}


@app.get(
    "/reports/export-excel",
    tags=["Reports"],
    summary="Export reservations to Excel",
)
def export_excel(
    ilkt: str = "",
    sont: str = "",
    musteri: str = "",
    plaka: str = "",
    sofor: str = "",
    odeme: str = "",
    aracsahip: str = "",
    baslangic: str = "",
):
    s = _get_session_or_raise()
    html = s.get("/modul/rapor/excelldegis.php", {
        "ilkt": ilkt,
        "sont": sont,
        "musteri": musteri,
        "plaka": plaka,
        "sofor": sofor,
        "odeme": odeme,
        "aracsahip": aracsahip,
        "baslangic": baslangic,
    })
    return {"status": "ok", "html": html}


@app.post(
    "/reports/detail",
    tags=["Reports"],
    summary="View report detail",
)
def report_detail(data: dict):
    musteriId = data.get("musteriId", "")
    if not musteriId:
        raise HTTPException(422, "musteriId is required")
    s = _get_session_or_raise()
    html = s.post(
        "/modul/index/detay.php?islem=ajax&i=trapor",
        {"musteriId": musteriId},
    )
    detail = parsers.parse_reservation_detail(html)
    return {"status": "ok", "detail": detail, "reservation_id": musteriId}


# ===================================================================
#  COMMERCIAL
# ===================================================================


@app.post(
    "/commercial/transaction-detail",
    tags=["Commercial"],
    summary="View transaction details",
)
def transaction_detail(data: dict):
    musteriId = data.get("musteriId", "")
    if not musteriId:
        raise HTTPException(422, "musteriId is required")
    s = _get_session_or_raise()
    html = s.post(
        "/modul/ajax/islemler.php?islem=cariharekettEdit",
        {"musteriId": musteriId},
    )
    return {"status": "ok", "html": html}


@app.post(
    "/commercial/user-edit",
    tags=["Commercial"],
    summary="Edit firm user",
)
def user_edit(data: dict):
    musteriId = data.get("musteriId", "")
    if not musteriId:
        raise HTTPException(422, "musteriId is required")
    s = _get_session_or_raise()
    html = s.post(
        "/modul/ajax/islemler.php?islem=firmakullaniciEdit",
        {"musteriId": musteriId},
    )
    return {"status": "ok", "html": html}


@app.post(
    "/commercial/date-query",
    tags=["Commercial"],
    summary="Date-based account query",
)
def date_query(data: dict):
    s = _get_session_or_raise()
    html = s.post(
        "/modul/tmusteri/cari_tarih_sorgu.php?GiT=447",
        data,
    )
    return {"status": "ok", "html": html}


@app.get(
    "/commercial/balances",
    tags=["Commercial"],
    summary="View account balances",
)
def balances(kur: str = "1"):
    s = _get_session_or_raise()
    cid = get_settings().customer_id
    html = s.get(
        "/modul/tmusteri/hesaplar_ajax.php",
        {"id": cid, "kur": kur},
    )
    parsed = parsers.parse_balance_info(html)
    return {
        "status": "ok",
        "currency": kur,
        "balances": parsed,
    }


# ===================================================================
#  ACCOUNT
# ===================================================================


@app.post(
    "/account/change-password",
    tags=["Account"],
    summary="Change account password",
)
def change_password(req: PasswordChangeRequest):
    if req.new_password != req.confirm_password:
        raise HTTPException(400, "New passwords do not match")
    s = _get_session_or_raise()
    html = s.post("/", {
        "i": "sifre",
        "GiT": "degistir",
        "mevcut": req.current_password,
        "yeni": req.new_password,
        "tekrar": req.confirm_password,
    })
    return {"status": "ok", "html": html}


# ===================================================================
#  LANGUAGE
# ===================================================================


@app.post(
    "/language",
    tags=["System"],
    summary="Switch interface language",
)
def set_lang(lang: str = Body("en", embed=True)):
    s = _get_session_or_raise()
    html = s.get("/lang.php", {"settings": lang})
    return {"status": "ok", "language": lang}


# ===================================================================
#  RAW PROXY (for unexposed functionality)
# ===================================================================


@app.get(
    "/page",
    tags=["Raw Proxy"],
    summary="Access any VipUber page by module name",
)
def get_page(i: str = ""):
    s = _get_session_or_raise()
    html = s.get("/", {"i": i})
    return {"html": html}


@app.post(
    "/proxy-post",
    tags=["Raw Proxy"],
    summary="Generic POST proxy to any VipUber path",
)
def proxy_post(req: ProxyPostRequest):
    s = _get_session_or_raise()
    html = s.post(req.path, req.data)
    return {"html": html}


@app.get(
    "/proxy-get",
    tags=["Raw Proxy"],
    summary="Generic GET proxy to any VipUber path",
)
def proxy_get(path: str, params: str = ""):
    s = _get_session_or_raise()
    import urllib.parse
    parsed = urllib.parse.parse_qs(params)
    flat = {k: v[0] for k, v in parsed.items()}
    html = s.get(path, flat)
    return {"html": html}


# ===================================================================
#  ENTRY POINT
# ===================================================================

if __name__ == "__main__":
    import uvicorn
    settings.validate()
    log.info("Starting VipUber Booking API on %s:%s", settings.host, settings.port)
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
        log_level=settings.log_level.lower(),
    )
