from bs4 import BeautifulSoup
import json
import re
from typing import Any

BEDS_RE = re.compile(r"(\d+(?:\.\d+)?)\s+beds?", re.IGNORECASE)
BATHS_RE = re.compile(r"(\d+(?:\.\d+)?)\s+baths?", re.IGNORECASE)
SQFT_RE = re.compile(r"([\d,]{3,7})\s+sq\s*ft", re.IGNORECASE)
YEAR_BUILT_RE = re.compile(r"(?:year built|built in)\s*:?\s*(\d{4})", re.IGNORECASE)

def clean_number(value: Any):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).replace(",", "").replace("$", "").strip()
    if not text:
        return None
    try:
        return int(float(text))
    except Exception:
        return None

def clean_float(value: Any):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace(",", "").replace("$", "").strip()
    if not text:
        return None
    try:
        return float(text)
    except Exception:
        return None

def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split()).strip()

def extract_zip(address: str) -> str:
    match = re.search(r"\b(\d{5})\b", address)
    return match.group(1) if match else ""

def blank_property():
    return {
        "property_type": "",
        "beds": None,
        "baths": None,
        "sqft": None,
        "year_built": None,
        "neighborhood": "",
        "hoa_name": "",
        "building_name": "",
        "is_condo": False,
        "is_townhome": False,
        "is_multi_family": False,
        "is_unique_property": False
    }

def infer_flags(property_data: dict) -> dict:
    ptype = normalize_text(property_data.get("property_type")).lower()

    property_data["is_condo"] = "condo" in ptype
    property_data["is_townhome"] = "town" in ptype
    property_data["is_multi_family"] = any(term in ptype for term in ["multi", "duplex", "triplex", "fourplex"])
    property_data["is_unique_property"] = False

    if ptype == "single family":
        property_data["property_type"] = "single_family"
    elif "condo" in ptype:
        property_data["property_type"] = "condo"
    elif "town" in ptype:
        property_data["property_type"] = "townhome"
    elif property_data["is_multi_family"]:
        property_data["property_type"] = "multi_family"

    return property_data

def parse_property_from_text(page_text: str, property_data: dict) -> dict:
    if property_data["beds"] is None:
        m = BEDS_RE.search(page_text)
        if m:
            property_data["beds"] = clean_float(m.group(1))

    if property_data["baths"] is None:
        m = BATHS_RE.search(page_text)
        if m:
            property_data["baths"] = clean_float(m.group(1))

    if property_data["sqft"] is None:
        m = SQFT_RE.search(page_text)
        if m:
            property_data["sqft"] = clean_number(m.group(1))

    if property_data["year_built"] is None:
        m = YEAR_BUILT_RE.search(page_text)
        if m:
            property_data["year_built"] = clean_number(m.group(1))

    return infer_flags(property_data)

def parse_redfin(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    text = normalize_text(soup.get_text(" ", strip=True))

    property_data = blank_property()
    property_data = parse_property_from_text(text, property_data)

    comps = []
    sold_pattern = re.compile(
        r"""
        SOLD\s+
        (?P<sold_date>[A-Z]{3}\s+\d{1,2},\s+\d{4})
        .*?
        \$(?P<price>[\d,]+)
        .*?
        (?P<beds>\d+(?:\.\d+)?)\s+beds?
        .*?
        (?P<baths>\d+(?:\.\d+)?)\s+baths?
        .*?
        (?P<sqft>[\d,]{3,7})\s+sq\s*ft
        .*?
        (?P<address>\d{1,6}\s+[A-Za-z0-9#.\-'\s]+,\s*[A-Za-z.\-\s]+,\s*[A-Z]{2}\s+\d{5})
        """,
        re.IGNORECASE | re.DOTALL | re.VERBOSE
    )

    for match in sold_pattern.finditer(text):
        comps.append({
            "address": normalize_text(match.group("address")),
            "price": clean_number(match.group("price")),
            "property_type": "",
            "status": "sold",
            "beds": clean_float(match.group("beds")),
            "baths": clean_float(match.group("baths")),
            "sqft": clean_number(match.group("sqft")),
            "year_built": None,
            "neighborhood": "",
            "hoa_name": "",
            "building_name": "",
            "street_name": "",
            "city": "",
            "state": "",
            "zip_code": extract_zip(match.group("address")),
            "lat": None,
            "lng": None,
            "dom": None,
            "superior_features": "",
            "inferior_features": "",
            "notes": f"Redfin visible-text sold comp, sold {normalize_text(match.group('sold_date'))}"
        })

    return {
        "property": property_data,
        "comps": comps[:10]
    }

def parse_realtor(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    property_data = blank_property()
    comps = []

    script = soup.find("script", id="__NEXT_DATA__")
    if script and script.string:
        try:
            data = json.loads(script.string)
            prop = data.get("props", {}).get("pageProps", {}).get("property", {})
            details = prop.get("details", {})
            address = prop.get("address", {})

            property_data["property_type"] = normalize_text(details.get("propertyType"))
            property_data["beds"] = clean_float(details.get("beds"))
            property_data["baths"] = clean_float(details.get("baths"))
            property_data["sqft"] = clean_number(details.get("sqft"))
            property_data["year_built"] = clean_number(details.get("yearBuilt"))
            property_data["neighborhood"] = normalize_text(address.get("city"))
            property_data = infer_flags(property_data)
        except Exception:
            pass

    text = normalize_text(soup.get_text(" ", strip=True))
    property_data = parse_property_from_text(text, property_data)

    return {
        "property": property_data,
        "comps": comps
    }

def parse_zillow(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    text = normalize_text(soup.get_text(" ", strip=True))

    property_data = blank_property()
    property_data = parse_property_from_text(text, property_data)

    return {
        "property": property_data,
        "comps": []
    }
