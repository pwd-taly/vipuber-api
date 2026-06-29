"""Pydantic models for the VipUber Booking API."""

import re
from typing import Optional
from pydantic import BaseModel, Field, field_validator


# ── Location lookup ─────────────────────────────────

LOCATION_IDS: dict[str, str] = {
    "TAKSİM": "1",
    "BEYLİKDÜZÜ": "4",
    "NİŞANTAŞI": "9",
    "SABİHA GÖKÇEN HAVALİMANI": "11",
    "ŞİŞLİ": "12",
    "İSTANBUL HAVALİMANI": "13",
    "BEŞİKTAŞ": "18",
    "ETİLER": "26",
    "ÜMRANİYE": "30",
    "KÜÇÜKÇEKMECE": "34",
    "ZEYTİNBURNU": "39",
    "BEBEK": "59",
    "ATAŞEHİR": "64",
    "SARIYER": "70",
    "BAHÇEŞEHİR": "82",
    "ÜSKÜDAR": "88",
    "BEYKOZ": "89",
    "FATİH": "94",
    "BAHÇELİEVLER": "97",
    "KARTAL": "108",
    "PENDİK": "170",
    "BEYOĞLU": "242",
    "FULYA": "307",
    "SUADİYE": "570",
    "ALTUNİZADE": "698",
}

LOCATION_NAMES: dict[str, str] = {v: k for k, v in LOCATION_IDS.items()}

PAYMENT_METHODS = {"1": "Cash", "2": "Current Account"}
CURRENCIES = {"1": "TL", "2": "USD", "3": "EUR", "4": "GBP"}


# ── Request models ──────────────────────────────────


class LoginRequest(BaseModel):
    email: str = Field(..., description="VipUber account email")
    password: str = Field(..., description="VipUber account password")


class CalculateRequest(BaseModel):
    pickup_id: str = Field(..., description="Pickup location ID (e.g. '13' for İstanbul Havalimanı)")
    destination_id: str = Field(..., description="Destination location ID")
    service_type: str = Field("tek", description="Service type: tek (one-way)")
    customer_id: str = Field("447", description="Customer/company ID")
    currency: str = Field("1", description="Currency: 1=TL, 2=USD, 3=EUR, 4=GBP")
    passenger_count: int = Field(1, ge=1, le=50, description="Number of passengers")


class ConfirmRequest(BaseModel):
    passenger_count: int = Field(1, ge=1, le=50, description="Number of passengers")


class BookTransferRequest(BaseModel):
    pickup: str = Field(
        "İSTANBUL HAVALİMANI",
        description="Pickup zone/location name (e.g. 'BEŞİKTAŞ', 'İSTANBUL HAVALİMANI')",
    )
    destination: str = Field(
        "BEŞİKTAŞ",
        description="Destination zone/location name",
    )
    pickup_address: str = Field("", description="Specific pickup address or landmark")
    destination_address: str = Field("", description="Specific dropoff address or landmark")
    date: str = Field("", description="Pickup date (DD.MM.YYYY)")
    time: str = Field("", description="Pickup time (HH:MM)")
    flight: str = Field("", description="Flight number")
    first_name: str = Field("", description="Passenger first name")
    last_name: str = Field("", description="Passenger last name")
    phone: str = Field("", description="Passenger phone number")
    email: str = Field("", description="Passenger email")
    tc_no: str = Field("", description="TC ID or Passport number")
    nationality: str = Field("TR", description="Nationality code (e.g. TR, DE, RU)")
    room_no: str = Field("", description="Hotel room number")
    notes: str = Field("", description="Special notes / driver instructions")
    passenger_count: int = Field(1, ge=1, le=50, description="Number of passengers")
    payment_method: str = Field("1", description="Payment: 1=Cash, 2=Current Account")
    currency: str = Field("1", description="Currency: 1=TL, 2=USD, 3=EUR, 4=GBP")
    return_trip: bool = Field(False, description="Is this a return trip?")
    return_date: str = Field("", description="Return date (DD.MM.YYYY)")
    return_time: str = Field("", description="Return time (HH:MM)")
    return_flight: str = Field("", description="Return flight number")
    vehicle_id: Optional[str] = Field(None, description="Specific vehicle ID (auto-selected if empty)")
    hotel_id: Optional[str] = Field(None, description="Hotel/company ID (defaults to customer ID)")

    @field_validator("date", "return_date")
    @classmethod
    def validate_date_format(cls, v: str) -> str:
        """Validate date format DD.MM.YYYY when provided."""
        if v and not re.match(r"^\d{2}\.\d{2}\.\d{4}$", v):
            raise ValueError(f"Date '{v}' must be in DD.MM.YYYY format (e.g. 25.06.2026)")
        return v

    @field_validator("time", "return_time")
    @classmethod
    def validate_time_format(cls, v: str) -> str:
        """Validate time format HH:MM when provided."""
        if v and not re.match(r"^\d{2}:\d{2}$", v):
            raise ValueError(f"Time '{v}' must be in HH:MM format (e.g. 14:30)")
        return v

    @field_validator("payment_method")
    @classmethod
    def validate_payment_method(cls, v: str) -> str:
        if v not in ("1", "2"):
            raise ValueError(f"payment_method must be '1' (Cash) or '2' (Current Account), got '{v}'")
        return v

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v: str) -> str:
        if v not in ("1", "2", "3", "4"):
            raise ValueError(f"currency must be one of '1'=TL, '2'=USD, '3'=EUR, '4'=GBP, got '{v}'")
        return v

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        """Validate phone number is reasonable when provided."""
        if v:
            # Strip common formatting
            cleaned = v.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
            if not re.match(r"^\+?\d{7,15}$", cleaned):
                raise ValueError(f"Phone '{v}' does not look like a valid phone number")
        return v

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        """Basic email format validation when provided."""
        if v and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", v):
            raise ValueError(f"Email '{v}' is not a valid email address")
        return v


class DateRangeParams(BaseModel):
    ilkt: str = Field("", description="Start date (DD.MM.YYYY)")
    sont: str = Field("", description="End date (DD.MM.YYYY)")
    odeme: Optional[str] = Field(None, description="Payment method filter: 1=Cash, 2=Current Account")


class ApprovalDetailRequest(BaseModel):
    musteriId: str = Field(..., description="Reservation/customer ID")
    status: str = Field("onayBekleyen", description="Status page: onayBekleyen, onayLi, trapor")


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(..., description="Current password")
    new_password: str = Field(..., description="New password")
    confirm_password: str = Field(..., description="Confirm new password")


class ReportSearchRequest(DateRangeParams):
    fkul: Optional[str] = Field(None, description="User ID filter")


class ExcelExportRequest(BaseModel):
    ilkt: str = Field("", description="Start date (DD.MM.YYYY)")
    sont: str = Field("", description="End date (DD.MM.YYYY)")
    musteri: Optional[str] = Field(None, description="Customer filter")
    plaka: Optional[str] = Field(None, description="License plate filter")
    sofor: Optional[str] = Field(None, description="Driver filter")
    odeme: Optional[str] = Field(None, description="Payment method filter")
    aracsahip: Optional[str] = Field(None, description="Vehicle owner filter")
    baslangic: Optional[str] = Field(None, description="Starting point filter")


class ProxyPostRequest(BaseModel):
    path: str = Field(..., description="Relative path on the VipUber server")
    data: dict = Field({}, description="Form data to POST")


class ProxyGetRequest(BaseModel):
    path: str = Field(..., description="Relative path on the VipUber server")
    params: str = Field("", description="Query string parameters")


# ── Response models ─────────────────────────────────


class ApiResponse(BaseModel):
    """Standard API response wrapper."""
    status: str = "ok"
    message: str = ""
    data: Optional[dict] = None


class VehicleOption(BaseModel):
    id: str
    name: str
    price: str
    currency: str = "TL"
    passenger_capacity: str = ""
    is_selected: bool = False


class BookingResult(BaseModel):
    status: str
    message: str
    tracking_code: Optional[str] = None
    vehicle: Optional[str] = None
    price: Optional[str] = None
    currency: str = "TL"
    pickup: Optional[str] = None
    destination: Optional[str] = None
    passenger: Optional[str] = None
    date: Optional[str] = None
    time: Optional[str] = None


class ReservationSummary(BaseModel):
    id: str
    customer: str = ""
    pickup: str = ""
    destination: str = ""
    date: str = ""
    time: str = ""
    vehicle: str = ""
    price: str = ""
    status: str = ""
    payment: str = ""


class BalanceInfo(BaseModel):
    currency: str
    balance: str = "0"
    customer_id: str = ""
