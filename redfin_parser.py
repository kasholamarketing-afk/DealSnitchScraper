from bs4 import BeautifulSoup
import re
from typing import Any, List

from parser_common import (
    BEDS_RE,
    BATHS_RE,
    SQFT_RE,
    YEAR_BUILT_RE,
    clean_float,
    clean_number,
    normalize_text,
    extract_structured_json_objects,
    extract_embedded_state_objects,
    extract_json_api_endpoints,
    extract_text_by_selectors,
    extract_zip,
)


def walk_json_for_keys(obj: Any, keys: set[str], found: List[dict]):
    if isinstance(obj, dict):
        lowered = {str(k).lower(): v for k, v in obj.items()}
        if keys.intersection(lowered.keys()):
            found.append(obj)
        for v in obj.values():
            walk_json_for_keys(v, keys, found)
    elif isinstance(obj, list):
        for item in obj:
            walk_json_for_keys(item, keys, found)


def find_property_candidate_from_json(json_blocks: list[Any]) -> dict:
    property_data = {
        "property_type": "",
        "beds": None,
        "baths": None,
        "sqft": None,
        "year_built": None,
        "neighborhood": "",
        "hoa_name": "",
        "building_name": "",
    }

    candidates: List[dict] = []
    for block in json_blocks:
        walk_json_for_keys(
            block,
            {
                "numberofrooms",
                "floorsize",
                "address",
                "yearbuilt",
                "@type",
                "numberofbathroomstotal",
            },
            candidates,
        )

    for candidate in candidates:
        lowered = {str(k).lower(): v for k, v in candidate.items()}

        if not property_data["property_type"]:
            atype = lowered.get("@type")
            if isinstance(atype, str):
                property_data["property_type"] = normalize_text(atype)

        if property_data["beds"] is None:
            property_data["beds"] = clean_float(lowered.get("numberofrooms"))

        if property_data["baths"] is None:
            baths_val = lowered.get("numberofbathroomstotal") or lowered.get("numberofbathrooms")
            property_data["baths"] = clean_float(baths_val)

        if property_data["sqft"] is None:
            floor_size = lowered.get("floorsize")
            if isinstance(floor_size, dict):
                property_data["sqft"] = clean_number(floor_size.get("value"))
            elif floor_size is not None:
                property_data["sqft"] = clean_number(floor_size)

        if property_data["year_built"] is None:
            property_data["year_built"] = clean_number(lowered.get("yearbuilt"))

        address = lowered.get("address")
        if isinstance(address, dict):
            property_data["neighborhood"] = normalize_text(
                address.get("addressLocality") or address.get("addressRegion") or ""
            )

    return property_data


def parse_property_from_text(page_text: str, property_data: dict) -> dict:
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
        if "multi-family property type" in lowered or "multi family property type" in lowered:
            property_data["property_type"] = "multi_family"
        elif "single-family property type" in lowered or "single family property type" in lowered:
            property_data["property_type"] = "single_family"
        elif "condo property type" in lowered:
            property_data["property_type"] = "condo"
        elif "townhouse property type" in lowered or "townhome property type" in lowered:
            property_data["property_type"] = "townhome"

    return property_data


def extract_redfin_comp_blocks(page_text: str) -> List[dict]:
    comps: list[dict] = []

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
        re.IGNORECASE | re.DOTALL | re.VERBOSE,
    )

    for match in sold_pattern.finditer(page_text):
        address = normalize_text(match.group("address"))
        price = clean_number(match.group("price"))
        beds = clean_float(match.group("beds"))
        baths = clean_float(match.group("baths"))
        sqft = clean_number(match.group("sqft"))

        if not address or price is None:
            continue

        comps.append(
            {
                "address": address,
                "price": price,
                "property_type": "",
                "status": "sold",
                "beds": beds,
                "baths": baths,
                "sqft": sqft,
                "year_built": None,
                "neighborhood": "",
                "hoa_name": "",
                "building_name": "",
                "street_name": "",
                "city": "",
                "state": "",
                "zip_code": extract_zip(address),
                "lat": None,
                "lng": None,
                "dom": None,
                "superior_features": "",
                "inferior_features": "",
                "notes": f"Redfin visible-text sold comp, sold {normalize_text(match.group('sold_date'))}",
            }
        )

    return dedupe_comps(comps)


def extract_redfin_active_blocks(page_text: str) -> List[dict]:
    comps: list[dict] = []

    active_pattern = re.compile(
        r"""
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
        re.IGNORECASE | re.DOTALL | re.VERBOSE,
    )

    for match in active_pattern.finditer(page_text):
        address = normalize_text(match.group("address"))
        price = clean_number(match.group("price"))

        if not address or price is None:
            continue

        context_window = page_text[max(0, match.start() - 50) : match.end() + 50].lower()
        if "sold" in context_window:
            continue

        comps.append(
            {
                "address": address,
                "price": price,
                "property_type": "",
                "status": "active",
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
                "zip_code": extract_zip(address),
                "lat": None,
                "lng": None,
                "dom": None,
                "superior_features": "",
                "inferior_features": "",
                "notes": "Redfin visible-text active candidate comp",
            }
        )

    return dedupe_comps(comps)


def dedupe_comps(comps: List[dict]) -> List[dict]:
    seen = set()
    output = []

    for comp in comps:
        key = (normalize_text(comp.get("address")), comp.get("price"), comp.get("status"))
        if key in seen:
            continue
        seen.add(key)
        output.append(comp)

    return output


def infer_neighborhood_from_title(soup: BeautifulSoup) -> str:
    title = normalize_text(soup.title.get_text()) if soup.title else ""
    if "|" in title:
        left = title.split("|")[0].strip()
        return left
    return ""


def parse_redfin(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    page_text = normalize_text(soup.get_text(" ", strip=True))

    property_data = {
        "property_type": "",
        "beds": None,
        "baths": None,
        "sqft": None,
        "year_built": None,
        "neighborhood": "",
        "hoa_name": "",
        "building_name": "",
    }

    # 1) Structured JSON extraction: ld+json + __NEXT_DATA__.
    property_from_json = find_property_candidate_from_json(extract_structured_json_objects(soup))

    for key, value in property_from_json.items():
        if value not in (None, "", []):
            property_data[key] = value

    # 2) Embedded script extraction: state objects from script assignments.
    embedded_property = find_property_candidate_from_json(extract_embedded_state_objects(soup))
    for key, value in embedded_property.items():
        if value not in (None, "", []) and not property_data.get(key):
            property_data[key] = value

    # JSON APIs called/referenced by the page (discovery stage).
    _json_api_endpoints = extract_json_api_endpoints(soup)

    # 3) Visible DOM selectors after render.
    rendered_text = extract_text_by_selectors(
        soup,
        [
            "main",
            "[data-rf-test-id='abp-beds']",
            "[data-rf-test-id='abp-baths']",
            "[data-rf-test-id='abp-sqFt']",
            "[class*='KeyDetails']",
        ],
    )
    if rendered_text:
        property_data = parse_property_from_text(rendered_text, property_data)

    # 4) Regex fallback from full page text.
    property_data = parse_property_from_text(page_text, property_data)

    if not property_data["neighborhood"]:
        property_data["neighborhood"] = infer_neighborhood_from_title(soup)

    sold_comps = extract_redfin_comp_blocks(page_text)
    active_comps = extract_redfin_active_blocks(page_text)

    all_comps = sold_comps + [
        comp
        for comp in active_comps
        if (normalize_text(comp["address"]), comp["price"], comp["status"])
        not in {(normalize_text(c["address"]), c["price"], c["status"]) for c in sold_comps}
    ]

    return {
        "property": property_data,
        "comps": all_comps[:10],
        "json_api_endpoints": _json_api_endpoints,
    }
