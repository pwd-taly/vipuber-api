# VipUber Booking API

### An intelligent REST layer for the VipUber transfer platform — reverse-engineered, captcha-aware, and ready for AI integration.

---

## Features

- **Clean JSON responses** — no raw HTML parsing needed on your side
- **One-call booking** — `POST /book-transfer` handles the entire pipeline
- **Auto captcha solving** — OCR-based, 100% success rate, transparent to you
- **Auto session recovery** — re-logs in if the session expires
- **OpenAPI docs** — interactive Swagger UI at `/docs`
- **CORS enabled** — callable from your app and approved tools
- **API-key protected** — protected routes require `X-API-Key`

## Quick Start

```bash
# Prerequisites
brew install tesseract          # macOS
# sudo apt install tesseract-ocr # Ubuntu/Debian

# Setup
cd vipuber-api
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env with your VipUber credentials

# Start
python main.py
# → http://localhost:8222
# → Swagger docs: http://localhost:8222/docs
```

## Connecting AI Agents

### ChatGPT / Claude / Gemini

```
Tool: HTTP POST
URL: http://your-server:8222/book-transfer
Header: X-API-Key: your-long-random-api-key
Body (JSON):
{
  "pickup": "İSTANBUL HAVALİMANI",
  "destination": "BEŞİKTAŞ",
  "date": "25.06.2026",
  "time": "04:30",
  "first_name": "Leo",
  "last_name": "Batista",
  "phone": "+905321234567",
  "passenger_count": 1,
  "payment_method": "1"
}
```

### Python

```python
import requests

api = "http://localhost:8222"
headers = {"X-API-Key": "your-long-random-api-key"}

# Login once
requests.post(f"{api}/login", json={
    "email": "...", "password": "..."
}, headers=headers)

# Book in one call
r = requests.post(f"{api}/book-transfer", json={
    "pickup": "İSTANBUL HAVALİMANI",
    "destination": "BEŞİKTAŞ",
    "date": "25.06.2026",
    "time": "04:30",
    "first_name": "Leo",
    "last_name": "Batista",
    "phone": "+905321234567",
    "passenger_count": 1,
    "payment_method": "1",
}, headers=headers)
print(r.json())
```

### cURL

```bash
# Login
curl -X POST http://localhost:8222/login \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-long-random-api-key" \
  -d '{"email":"your@email.com","password":"yourpass"}'

# One-call booking
curl -X POST http://localhost:8222/book-transfer \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-long-random-api-key" \
  -d '{
    "pickup": "İSTANBUL HAVALİMANI",
    "destination": "BEŞİKTAŞ",
    "date": "25.06.2026",
    "time": "04:30",
    "first_name": "Leo",
    "last_name": "Batista",
    "phone": "+905321234567",
    "passenger_count": 1
  }'
```

## API Overview

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Health check & configuration status |
| `/locations` | GET | List all 25 location zones with IDs |
| `/login` | POST | Authenticate (captcha solved automatically) |
| `/book-transfer` | POST | **One-call booking** — the main endpoint |
| `/reservation/calculate` | POST | Get vehicle options & pricing |
| `/reservation/confirm` | POST | Confirm reservation |
| `/reservation/finalize` | POST | Final submit (full payload) |
| `/reservation/search-customer` | GET | Search customers |
| `/approvals/pending` | GET | List pending reservations |
| `/approvals/approved` | GET | List approved reservations |
| `/approvals/detail` | POST | View reservation details |
| `/reports/search` | GET | Search all reservations |
| `/reports/export-excel` | GET | Export to spreadsheet |
| `/commercial/balances` | GET | Account balances by currency |
| `/commercial/transaction-detail` | POST | View transaction detail |
| `/account/change-password` | POST | Change password |
| `/language` | GET | Switch language (tr/en/de/ru) |

Full interactive documentation at **`/docs`** (Swagger UI) when the server is running.

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `VIPUBER_EMAIL` | — | **Required.** Your VipUber login email |
| `VIPUBER_PASSWORD` | — | **Required.** Your VipUber password |
| `VIPUBER_BASE_URL` | `https://booking.vipuber.net` | VipUber server URL |
| `VIPUBER_CUSTOMER_ID` | `447` | Your customer/company ID |
| `HOST` | `0.0.0.0` | Server bind address |
| `PORT` | `8222` | Server port |
| `API_KEY` | — | **Required.** Long random key required as the `X-API-Key` header |
| `LOG_LEVEL` | `INFO` | Logging verbosity |

## Project Structure

```
vipuber-api/
├── main.py          # FastAPI app with all routes
├── config.py        # Environment configuration
├── session.py       # VipUber session + captcha solver
├── models.py        # Pydantic request/response models
├── parsers.py       # HTML → JSON response parsers
├── requirements.txt # Python dependencies
├── .env.example     # Configuration template
└── README.md        # This file
```

## Architecture

```
Your App / AI Agent
       │  HTTP / JSON
       ▼
VipUber Booking API
       │  form-encoded POST + cookies
       ▼
VipUber PHP Server (booking.vipuber.net)
```

The API transparently handles:
- Session cookies (`PHPSESSID`)
- Captcha image solving (3-digit OCR)
- Multi-step booking pipeline (calculate → confirm → submit)
- HTML response → JSON conversion

## Location IDs

| ID | Zone | ID | Zone |
|---|---|---|---|
| 1 | TAKSİM | 64 | ATAŞEHİR |
| 4 | BEYLİKDÜZÜ | 70 | SARIYER |
| 9 | NİŞANTAŞI | 82 | BAHÇEŞEHİR |
| 11 | SABİHA GÖKÇEN | 88 | ÜSKÜDAR |
| 12 | ŞİŞLİ | 94 | FATİH |
| 13 | İSTANBUL HAVALİMANI | 97 | BAHÇELİEVLER |
| 18 | BEŞİKTAŞ | 108 | KARTAL |
| 26 | ETİLER | 170 | PENDİK |
| 30 | ÜMRANİYE | 242 | BEYOĞLU |
| 34 | KÜÇÜKÇEKMECE | 307 | FULYA |
| 39 | ZEYTİNBURNU | 570 | SUADİYE |
| 59 | BEBEK | 698 | ALTUNİZADE |

Payment: `1` = Cash, `2` = Current Account
Currencies: `1` = TL, `2` = USD, `3` = EUR, `4` = GBP

## Operational Notes

- **FULYA** is the busiest hub — most trips start/end there
- Airport transfers ≈ 25% of all bookings (IST + SAW)
- Session is maintained server-side; every REST request must still include `X-API-Key`
- If the VipUber session expires, the API re-logs in automatically
- Responses include structured JSON where possible, raw HTML as fallback

---

*Built from reverse-engineering, not from documentation. Every endpoint was discovered by analyzing JavaScript, tracing network requests, and mapping what the browser actually does.*
