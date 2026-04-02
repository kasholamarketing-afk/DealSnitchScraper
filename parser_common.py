from bs4 import BeautifulSoup
import json
import re
from typing import Any, Optional, List

PRICE_RE = re.compile(r"\$([\d,]+)")
BEDS_RE = re.compile(r"(\d+(?:\.\d+)?)\s+beds?", re.IGNORECASE)
BATHS_RE = re.compile(r"(\d+(?:\.\d+)?)\s+baths?", re.IGNORECASE)
SQFT_RE = re.compile(r"([\d,]{3,7})\s+sq\s*ft", re.IGNORECASE)
YEAR_BUILT_RE = re.compile(r"(?:year built|built in)\s*:?\s*(\d{4})", re.IGNORECASE)


def clean_number(value: Any) -> Optional[int]:
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


def clean_float(value: Any) -> Optional[float]:
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


def extract_script_json_blocks(soup: BeautifulSoup) -> List[Any]:
    blocks = []

    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text()
        if not raw:
            continue
        try:
            blocks.append(json.loads(raw))
        except Exception:
            continue

    return blocks


def extract_structured_json_objects(soup: BeautifulSoup) -> List[Any]:
    """Stage 1: extract clearly structured JSON payloads."""
    objects: List[Any] = []

    # Standard schema blocks.
    objects.extend(extract_script_json_blocks(soup))

    # Next.js payloads commonly used on JS-rendered pages.
    next_data = extract_json_from_script_id(soup, "__NEXT_DATA__")
    if next_data is not None:
        objects.append(next_data)

    return objects


def extract_inline_script_texts(soup: BeautifulSoup, min_length: int = 40) -> List[str]:
    scripts: List[str] = []
    for script in soup.find_all("script"):
        raw = script.string or script.get_text() or ""
        text = raw.strip()
        if len(text) >= min_length:
            scripts.append(text)
    return scripts


def extract_embedded_state_objects(soup: BeautifulSoup) -> List[Any]:
    """Stage 2: extract embedded state objects assigned in script tags."""
    objects: List[Any] = []

    assign_patterns = [
        re.compile(r"(?:window\.)?__INITIAL_STATE__\s*=\s*(\{.*?\})\s*;", re.DOTALL),
        re.compile(r"(?:window\.)?__PRELOADED_STATE__\s*=\s*(\{.*?\})\s*;", re.DOTALL),
        re.compile(r"(?:window\.)?__APOLLO_STATE__\s*=\s*(\{.*?\})\s*;", re.DOTALL),
        re.compile(r"(?:window\.)?__STATE__\s*=\s*(\{.*?\})\s*;", re.DOTALL),
    ]

    for script_text in extract_inline_script_texts(soup):
        text = script_text.strip()

        # Full-object scripts.
        if text.startswith("{") and text.endswith("}"):
            try:
                objects.append(json.loads(text))
            except Exception:
                pass

        # Assigned state objects.
        for pattern in assign_patterns:
            for match in pattern.finditer(text):
                raw = match.group(1).strip()
                try:
                    objects.append(json.loads(raw))
                except Exception:
                    continue

    return objects


def extract_json_api_endpoints(soup: BeautifulSoup) -> List[str]:
    """Find JSON API endpoints referenced by page scripts or HTML attributes."""
    endpoints: List[str] = []

    text = soup.get_text(" ", strip=True)
    for script_text in extract_inline_script_texts(soup, min_length=10):
        text += " " + script_text

    patterns = [
        re.compile(r"https?://[^\s\"'<>]+(?:/api/|\.json\b)[^\s\"'<>]*", re.IGNORECASE),
        re.compile(r"/api/[^\s\"'<>]+", re.IGNORECASE),
        re.compile(r"/_next/data/[^\s\"'<>]+\.json", re.IGNORECASE),
    ]

    for pattern in patterns:
        for match in pattern.finditer(text):
            endpoints.append(match.group(0))

    deduped = []
    seen = set()
    for endpoint in endpoints:
        clean = endpoint.strip().rstrip(",")
        if clean in seen:
            continue
        seen.add(clean)
        deduped.append(clean)

    return deduped


def extract_json_from_script_id(soup: BeautifulSoup, script_id: str) -> Optional[Any]:
    script = soup.find("script", attrs={"id": script_id})
    if not script:
        return None

    raw = script.string or script.get_text() or ""
    raw = raw.strip()
    if not raw:
        return None

    try:
        return json.loads(raw)
    except Exception:
        return None


def extract_text_by_selectors(soup: BeautifulSoup, selectors: List[str]) -> str:
    chunks: List[str] = []
    for selector in selectors:
        node = soup.select_one(selector)
        if node:
            chunks.append(normalize_text(node.get_text(" ", strip=True)))
    return normalize_text(" ".join(chunks))


def walk_json(obj: Any, found: List[Any]):
    if isinstance(obj, dict):
        found.append(obj)
        for v in obj.values():
            walk_json(v, found)
    elif isinstance(obj, list):
        for item in obj:
            walk_json(item, found)


def deep_get(obj: Any, path: List[str], default: Any = None) -> Any:
    current = obj
    for key in path:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
        if current is None:
            return default
    return current


def parse_property_from_text_generic(page_text: str, property_data: dict) -> dict:
    if property_data["beds"] is None:
        match = BEDS_RE.search(page_text)
        if match:
            property_data["beds"] = clean_float(match.group(1))

    if property_data["baths"] is None:
        match = BATHS_RE.search(page_text)
        if match:
            property_data["baths"] = clean_float(match.group(1))

    if property_data["sqft"] is None:
        match = SQFT_RE.search(page_text)
        if match:
            property_data["sqft"] = clean_number(match.group(1))

    if property_data["year_built"] is None:
        match = YEAR_BUILT_RE.search(page_text)
        if match:
            property_data["year_built"] = clean_number(match.group(1))

    if not property_data["property_type"]:
        lowered = page_text.lower()
        if "single family" in lowered:
            property_data["property_type"] = "single_family"
        elif "multi-family" in lowered or "multi family" in lowered or "duplex" in lowered or "triplex" in lowered:
            property_data["property_type"] = "multi_family"
        elif "condo" in lowered or "condominium" in lowered:
            property_data["property_type"] = "condo"
        elif "townhome" in lowered or "townhouse" in lowered:
            property_data["property_type"] = "townhome"

    return property_data


def extract_zip(address: str) -> str:
    match = re.search(r"\b(\d{5})\b", address)
    return match.group(1) if match else ""
