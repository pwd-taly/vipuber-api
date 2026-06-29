"""HTML → JSON response parsers for the VipUber PHP backend."""

import re
import logging
from typing import Optional

log = logging.getLogger("vipuber.parsers")


# ── Shared helpers ─────────────────────────────────


def strip_html_tags(text: str) -> str:
    """Remove HTML tags, decode entities, and collapse whitespace."""
    import html as _html
    text = _html.unescape(text)  # decode &#x20BA; → ₺, &amp; → &, etc.
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_input_value(html: str, name: str) -> Optional[str]:
    """Extract the value attribute of an <input> by its name."""
    m = re.search(
        r'<input[^>]*name=[\'"]' + re.escape(name) + r'[\'"][^>]*value=[\'"]([^\'"]*)[\'"]',
        html,
        re.IGNORECASE | re.DOTALL,
    )
    if m:
        return m.group(1)
    # Try reversed attribute order
    m = re.search(
        r'<input[^>]*value=[\'"]([^\'"]*)[\'"][^>]*name=[\'"]' + re.escape(name) + r'[\'"]',
        html,
        re.IGNORECASE | re.DOTALL,
    )
    if m:
        return m.group(1)
    return None


def extract_table_rows(html: str) -> list[dict]:
    """Extract data rows from an HTML table into dicts."""
    rows = []
    # Find all <tr> elements
    tr_pattern = re.compile(r"<tr[^>]*>(.*?)</tr>", re.DOTALL | re.IGNORECASE)
    # Find header row
    thead_pattern = re.compile(r"<thead[^>]*>(.*?)</thead>", re.DOTALL | re.IGNORECASE)
    thead_m = thead_pattern.search(html)
    headers = []
    if thead_m:
        headers = [
            strip_html_tags(th).strip()
            for th in re.findall(r"<th[^>]*>(.*?)</th>", thead_m.group(1), re.DOTALL)
        ]

    for tr in tr_pattern.finditer(html):
        cells = [
            strip_html_tags(td).strip()
            for td in re.findall(r"<td[^>]*>(.*?)</td>", tr.group(1), re.DOTALL)
        ]
        if not cells:
            continue
        if headers and len(cells) == len(headers):
            rows.append(dict(zip(headers, cells)))
        else:
            rows.append({"cells": cells})
    return rows


# ── Booking parsers ─────────────────────────────────


def parse_vehicle_options(html: str) -> list[dict]:
    """Extract vehicle options from the SepetGuncel / ajax.php response.

    Returns list of {id, name, price, currency, passenger_capacity, is_selected}.
    """
    vehicles = []
    # Find vehicle radio inputs
    for m in re.finditer(
        r'<input[^>]*name=[\'"]aracid[\'"][^>]*value=[\'"]([^\'"]+)[\'"]([^>]*)>',
        html,
        re.IGNORECASE,
    ):
        vid = m.group(1)
        is_checked = "checked" in m.group(2).lower()
        # Get vehicle name
        vname = ""
        nm = re.search(
            r'<label[^>]*for=[\'"]aracid' + re.escape(vid) + r'[\'"]>(.*?)</label>',
            html,
            re.DOTALL | re.IGNORECASE,
        )
        if nm:
            vname = strip_html_tags(nm.group(1))
        # Get price
        price = extract_input_value(html, f"fiyatal{vid}") or ""
        cap = extract_input_value(html, f"baslikal{vid}") or ""
        vehicles.append({
            "id": vid,
            "name": vname or cap,
            "price": price,
            "currency": "TL",
            "passenger_capacity": cap,
            "is_selected": is_checked,
        })
    return vehicles


def parse_booking_message(html: str) -> dict:
    """Extract success/error message from a booking result page.

    Returns {status, message, tracking_code}.
    """
    result = {"status": "unknown", "message": "", "tracking_code": None}

    # Look for success div (tamam_div)
    m = re.search(
        r'<div[^>]*class=[\'"][^\'"]*tamam_div[^\'"]*[\'"][^>]*>(.*?)</div>',
        html,
        re.DOTALL | re.IGNORECASE,
    )
    if m:
        text = strip_html_tags(m.group(1))
        result["message"] = text
        result["status"] = "success"

    # Look for success icon + heading (fa-check-circle + Reservation saved)
    if result["status"] == "unknown":
        m = re.search(
            r'fa-check-circle.*?<h3[^>]*>(.*?)</h3>',
            html,
            re.DOTALL | re.IGNORECASE,
        )
        if m:
            text = strip_html_tags(m.group(1))
            result["message"] = text
            result["status"] = "success"

    # Look for error
    if result["status"] == "unknown":
        m = re.search(
            r'<div[^>]*class=[\'"][^\'"]*hata[^\'"]*[\'"][^>]*>(.*?)</div>',
            html,
            re.DOTALL | re.IGNORECASE,
        )
        if m:
            text = strip_html_tags(m.group(1))
            result["message"] = text
            result["status"] = "error"

    # Extract reservation/tracking ID from edit link
    if not result["tracking_code"]:
        m = re.search(r'[?&]r=(\d+)', html)
        if m:
            result["tracking_code"] = m.group(1)

    # Fallback: check title
    if not result["message"]:
        m = re.search(r"<title>(.*?)</title>", html, re.DOTALL | re.IGNORECASE)
        if m:
            result["message"] = strip_html_tags(m.group(1))

    return result


# ── Approval / Report parsers ───────────────────────


def parse_reservation_list(html: str) -> list[dict]:
    """Parse a list of reservations from the onayBekleyen / onayLi / trapor pages."""
    reservations = []
    
    # Find reservation rows via the .detay class with musteriId attribute
    # The VipUber UI uses <a class="detay" musteriId="12345"> inside table cells
    detay_pattern = re.compile(
        r'<a[^>]*class=[\'"][^\'"]*\bdetay\b[^\'"]*[\'"][^>]*musteriId=[\'"](\d+)[\'"][^>]*>',
        re.IGNORECASE
    )
    
    for m in detay_pattern.finditer(html):
        musteri_id = m.group(1)
        # Deduplicate by musteri_id
        if any(r.get("id") == musteri_id for r in reservations):
            continue
        # Find the containing <tr>
        pos = m.start()
        tr_start = html.rfind("<tr", 0, pos)
        tr_end = html.find("</tr>", pos)
        if tr_start == -1 or tr_end == -1:
            continue
        row_html = html[tr_start:tr_end + 5]
        
        cells = [
            strip_html_tags(td).strip()
            for td in re.findall(r"<td[^>]*>(.*?)</td>", row_html, re.DOTALL)
        ]
        if cells:
            reservations.append({
                "id": musteri_id,
                "cells": cells,
            })
    
    # Fallback: generic table parsing, exclude balance summaries
    if not reservations:
        rows = extract_table_rows(html)
        for row in rows:
            cells = row.get("cells", [])
            if len(cells) >= 13:
                reservations.append(row)
            # Also accept 5-cell balance rows but don't include them
            # Only include rows that look like reservation data (13+ cells)
    
    return reservations


def parse_customer_search(html: str) -> list[dict]:
    """Parse customer search results from ara.php."""
    customers = []
    for m in re.finditer(
        r'<option[^>]*value=[\'"]([^\'"]+)[\'"](.*?)>(.*?)</option>',
        html,
        re.DOTALL | re.IGNORECASE,
    ):
        val = m.group(1)
        text = strip_html_tags(m.group(3))
        if val and text:
            customers.append({"id": val, "name": text, "selected": "selected" in m.group(2).lower()})
    return customers


def parse_balance_info(html: str) -> list[dict]:
    """Parse balance information from hesaplar_ajax.php."""
    balances = []
    for m in re.finditer(
        r'<td[^>]*>(.*?)</td>\s*<td[^>]*>(.*?)</td>',
        html,
        re.DOTALL | re.IGNORECASE,
    ):
        label = strip_html_tags(m.group(1))
        value = strip_html_tags(m.group(2))
        if label and value:
            balances.append({"label": label, "value": value})
    return balances


def parse_reservation_detail(html: str) -> dict:
    """Parse reservation detail from detay.php response."""
    detail = {}
    # Find label-value pairs: <td style="font-weight: bold..."> or <td><b>Key</b></td><td>Value</td>
    # Also handles class="label" / class="baslik" patterns
    for m in re.finditer(
        r'<td[^>]*(?:style="[^"]*font-weight\s*:\s*bold[^"]*"|class=["\'][^\'"]*(?:label|baslik)[^\'"]*["\'])'
        r'[^>]*>([\s\S]*?)</td>\s*<td[^>]*>([\s\S]*?)</td>',
        html,
        re.DOTALL | re.IGNORECASE,
    ):
        key = strip_html_tags(m.group(1)).strip().rstrip(":")
        val = strip_html_tags(m.group(2)).strip()
        if key and val:
            detail[key] = val

    # Also catch <td><b>Key</b></td> patterns (e.g., Vehicle Price, Grand total)
    for m in re.finditer(
            r'<td[^>]*>\s*<b>([^<]+)</b>\s*</td>\s*<td[^>]*>([\s\S]*?)</td>',
            html,
            re.DOTALL | re.IGNORECASE,
        ):
            key = strip_html_tags(m.group(1)).strip().rstrip(":")
            val = strip_html_tags(m.group(2)).strip()
            if key and val and key not in detail:
                detail[key] = val

    return detail
