# VipUber Booking API - Complete Map

## Authentication

### Login
`POST /giris/giris_kontrol.php`
| Param | Value |
|---|---|
| `kadi` | email |
| `sifre` | password |
| `security` | captcha (solved via OCR) |
| `git` | `https://booking.vipuber.net/` |

Returns: 302 redirect to `/` on success. Session stored in PHPSESSID cookie.

### Logout
`GET /giris/cikis.php`

### Password Change
`POST ?i=sifre&GiT=degistir`
| Param | Description |
|---|---|
| `mevcut` | Current password |
| `yeni` | New password |
| `tekrar` | Confirm new password |

---

## 1. Make a Reservation (`?i=rezerEkle`)

Location IDs: `1`=TAKSIM, `4`=BEYLIKDUZU, `11`=SABIHA GOKCEN, `13`=ISTANBUL HAVALIMANI, etc.
Customer ID (cari): `447` (your account)
Service type (hizmeti): `tek` (one-way)

### 1a. Calculate Price (SepetGuncel)
`POST /modul/rezer/ajax.php`
| Param | Example | Description |
|---|---|---|
| `alis` | `1` | Pickup location ID |
| `varis` | `11` | Destination ID |
| `hizmeti` | `tek` | Service type |
| `cari` | `447` | Customer ID |
| `kur` | `1` | Currency ID (1=TL) |
| `yolcu` | `1` | Passenger count |

Returns: HTML with vehicle selection, pricing, extra services, and **defines `tamamla()` function**.

### 1b. Select Vehicle & Payment (done via form fields before 1c)
After 1a, the following hidden fields are set in the page by JS (`jislem()`):
| Field | Description |
|---|---|
| `aracid` | Vehicle ID (e.g. `1` = MERCEDES VITO) |
| `aracadi` | Vehicle name |
| `totalucret` | Total price |
| `odeme` / `odemetur` | Payment method (`1`=Cash, `2`=Current account) |

Extra services (up to 50): `eki0`-`eki49` (name), `ekiucret0-49` (price), `ekiadet0-49` (quantity)

### 1c. Confirm Reservation (tamamla)
`POST /modul/rezer/tamamla.php`
| Param | Description |
|---|---|
| `yolcu` | Passenger count |

Returns: Script that **auto-executes `baslattir()`** which submits to Step 1d.

### 1d. Final Submit (baslattir → auto-called)
`POST /modul/rezer/ajaxislem.php`
Sends ALL form fields:

**Date/Time:**
| Field | Description |
|---|---|
| `alistarihi` | Receipt date (format: YYYY-MM-DD) |
| `alissaati` | Pickup time (HH:MM) |
| `donus` | Return trip: `0`=no, `1`=yes |
| `donustarihi` | Return date (if donus=1) |
| `donussaati` | Return time (if donus=1) |
| `bitistarih` | End date |
| `bitissaat` | End time |

**Flight Info:**
| Field | Description |
|---|---|
| `ucusno` | Flight number |
| `ducusno` | Return flight number |
| `havayolu` | Airline |

**Route:**
| Field | Description |
|---|---|
| `anokta` | Pickup point ID |
| `bnokta` | Destination point ID |
| `alisyeri` | Pickup location name |
| `varisyeri` | Destination name |
| `nereden` | Where from (text) |
| `nereye` | Where to (text) |

**Passenger Info:**
| Field | Description |
|---|---|
| `adsoyad` | First name |
| `soyad` | Last name |
| `tcno` | TC ID / Passport No |
| `gsm` | Phone number |
| `mail` | Email |
| `ulke` | Country (e.g. `TR` for Turkey) |
| `odano` | Room number |
| `cepulke` | Country dial code |

**Vehicle & Pricing:**
| Field | Description |
|---|---|
| `aracid` | Vehicle ID |
| `aracadi` | Vehicle name |
| `totalucret` / `ucret` | Total price |
| `kur` | Currency (`1`=TL) |
| `yetiskin` | Adult count (same as `yolcu`) |
| `cocuk` | Child count |
| `etsucret` | Additional fee |

**Customer/Company:**
| Field | Description |
|---|---|
| `cari` / `musteri` | Customer ID (`447`) |
| `otel` | Hotel/Company ID |
| `hizmeti` | Service type (`tek`) |
| `hizmetturu` | Service type description |

**Driver & Status:**
| Field | Description |
|---|---|
| `sofor` | Driver ID/name |
| `plaka` | License plate |
| `durumu` | Status (`1`) |
| `odeme` / `odemesekli` / `odemetur` | Payment method ID |
| `uetdsle` | UETDS setting (`2`) |
| `koruma` | Protection |
| `komisyon` | Commission |

**Extra Services (50x):**
| Pattern | Example |
|---|---|
| `eki0`..`eki49` | Service name (e.g. "Bebek Koltugu") |
| `ekiucret0`..`ekiucret49` | Service unit price |
| `ekiadet0`..`ekiadet49` | Service quantity |

### 1e. Search Customer
`POST /modul/rezer/ara.php?cari=447`
| Param | Description |
|---|---|
| `kelime` | Search term |
| `cari` | Customer ID (in URL) |

Returns: HTML select options of locations/customers.

### 1f. Passenger Form
`POST /modul/rezer/ajaxyolcu.php`
| Param | Description |
|---|---|
| `yolcu` | Number of passengers |

Returns: HTML form with passenger detail fields.

### 1g. Search External Company
`POST /modul/rezer/aradis.php`
| Param | Description |
|---|---|
| `kelime` | Company search term |

### 1h. Search License Plate
`POST /modul/rezer/aradisplaka.php`
| Param | Description |
|---|---|
| `kelime` | Plate search term |

---

## 2. Pending Approvals (`?i=onayBekleyen`)

### 2a. Search Pending
`GET ?i=onayBekleyen`
| Param | Description |
|---|---|
| `ilkt` | Start date (DD.MM.YYYY) |
| `sont` | End date (DD.MM.YYYY) |
| `odeme` | Payment method (1=Cash, 2=Current account) |

Quick date links:
- Today: `?i=onayBekleyen&ilkt=24.06.2026&sont=24.06.2026`
- Tomorrow: `?i=onayBekleyen&ilkt=25.06.2026&sont=25.06.2026`
- This week: `?i=onayBekleyen&ilkt=18.06.2026&sont=24.06.2026`
- This month: `?i=onayBekleyen&ilkt=01.06.2026&sont=24.06.2026`
- This year: `?i=onayBekleyen&ilkt=01.01.2026&sont=24.06.2026`

### 2b. View Reservation Detail
`POST /modul/index/detay.php?islem=ajax&i=onayBekleyen`
| Param | Description |
|---|---|
| `musteriId` | Reservation/customer ID |

### 2c. View Distance Detail
`POST /modul/index/disteday.php?islem=ajax&i=onayBekleyen`
| Param | Description |
|---|---|
| `musteriId` | Reservation/customer ID |

---

## 3. Approved Reservations (`?i=onayLi`)

Same endpoints as Pending but with `i=onayLi`:

### 3a. Search Approved
`GET ?i=onayLi` with `ilkt`, `sont`, `odeme` (same format as 2a)

### 3b. View Approved Detail
`POST /modul/index/detay.php?islem=ajax&i=onayLi`
| Param | Description |
|---|---|
| `musteriId` | Reservation ID |

### 3c. View Distance Detail
`POST /modul/index/disteday.php?islem=ajax&i=onayLi`
| Param | Description |
|---|---|
| `musteriId` | Reservation ID |

---

## 4. All Reservations / Reports (`?i=trapor`)

### 4a. Search Reservations
`GET ?i=trapor`
| Param | Description |
|---|---|
| `ilkt` | Start date |
| `sont` | End date |
| `odeme` | Payment method |
| `fkul` | User ID (e.g. `260`=SINAN, `263`=seymanur) |

### 4b. Search Report
`POST /modul/rapor/ara.php?i=trapor&firma=`
| Param | Description |
|---|---|
| `firma` | Company filter |

Returns: HTML table rows

### 4c. Export to Excel
`GET /modul/rapor/excelldegis.php`
| Param | Description |
|---|---|
| `ilkt` | Start date |
| `sont` | End date |
| `musteri` | Customer filter |
| `plaka` | License plate filter |
| `sofor` | Driver filter |
| `odeme` | Payment method |
| `aracsahip` | Vehicle owner |
| `baslangic` | Starting point |

Returns: Excel file download

### 4d. View Reservation Detail
`POST /modul/index/detay.php?islem=ajax&i=trapor`
| Param | Description |
|---|---|
| `musteriId` | Reservation ID |

### 4e. View Distance Detail
`POST /modul/index/disteday.php?islem=ajax&i=trapor`
| Param | Description |
|---|---|
| `musteriId` | Reservation ID |

---

## 5. Account Activities / Commercial (`?i=tcari`)

Customer ID appears to be `447` (your company).

### 5a. Transaction Detail
`POST /modul/ajax/islemler.php?islem=cariharekettEdit`
| Param | Description |
|---|---|
| `musteriId` | Customer ID |

### 5b. User Edit
`POST /modul/ajax/islemler.php?islem=firmakullaniciEdit`
| Param | Description |
|---|---|
| `musteriId` | Customer ID |

### 5c. Reservation Detail
`POST /modul/index/detay.php?islem=ajax`
| Param | Description |
|---|---|
| `musteriId` | Reservation ID |

### 5d. Account Date Query
`POST /modul/tmusteri/cari_tarih_sorgu.php?GiT=447`
| Param | Description |
|---|---|
| (form data) | Date range and account filters |

### 5e. Account Balances by Currency
`GET /modul/tmusteri/hesaplar_ajax.php?id=447&kur=N`
| Param | Description |
|---|---|
| `id` | Customer ID (`447`) |
| `kur` | Currency: `1`=TL, `2`=USD, `3`=EUR, `4`=GBP |

---

## 6. Price List (`?i=yonler`)

Read-only view. No AJAX/form submission endpoints found. Displays pricing table via DataTable (client-side).

---

## 7. Language Settings

`GET /lang.php?settings=tr|en|de|ru`

---

## System Info

| Detail | Value |
|---|---|
| Server | nginx |
| PHP | 7.4.33 |
| Session | PHPSESSID cookie |
| Charset | iso-8859-9 (Turkish) / UTF-8 |
| JS Libs | jQuery, DataTables, Select2, Sweetalert, intlTelInput |
