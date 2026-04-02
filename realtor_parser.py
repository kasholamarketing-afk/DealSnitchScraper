from bs4 import BeautifulSoup
import json
import re
from typing import Any, List

from parser_common import (
    clean_float,
    clean_number,
    normalize_text,
    extract_structured_json_objects,
    extract_embedded_state_objects,
    extract_json_api_endpoints,
    extract_text_by_selectors,
    walk_json,
    parse_property_from_text_generic,
    extract_zip,
)


def find_realtor_property_data(json_blocks: List[Any]) -> dict:
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

    all_nodes = []
    for block in json_blocks:
        walk_json(block, all_nodes)

    for node in all_nodes:
        if not isinstance(node, dict):
            continue

        lowered = {str(k).lower(): v for k, v in node.items()}

        if not property_data["property_type"]:
            atype = lowered.get("@type") or lowered.get("propertytype") or lowered.get("hometype")
            if isinstance(atype, str):
                property_data["property_type"] = normalize_text(atype)

        if property_data["beds"] is None:
            beds = lowered.get("numberofrooms") or lowered.get("numberofbedrooms") or lowered.get("beds")
            property_data["beds"] = clean_float(beds)

        if property_data["baths"] is None:
            baths = (
                lowered.get("numberofbathrooms")
                or lowered.get("bathstotal")
                or lowered.get("baths")
                or lowered.get("bathsfull")
            )
            property_data["baths"] = clean_float(baths)

        if property_data["sqft"] is None:
            sqft = lowered.get("floorsize") or lowered.get("sqft") or lowered.get("livingareasize")
            if isinstance(sqft, dict):
                property_data["sqft"] = clean_number(sqft.get("value"))
            else:
                property_data["sqft"] = clean_number(sqft)

        if property_data["year_built"] is None:
            year = lowered.get("yearbuilt") or lowered.get("year_built")
            property_data["year_built"] = clean_number(year)

        address = lowered.get("address")
        if isinstance(address, dict) and not property_data["neighborhood"]:
            property_data["neighborhood"] = normalize_text(
                address.get("addressLocality") or address.get("addressRegion") or ""
            )

    return property_data


def parse_realtor_comp_blocks(page_text: str) -> List[dict]:
    comps = []

    sold_pattern = re.compile(
        r"""
        \$?(?P<price>[\d,]{3,10})
        .*?
        (?P<beds>\d+(?:\.\d+)?)\s*bed[s]?
        .*?
        (?P<baths>\d+(?:\.\d+)?)\s*bath[s]?
        .*?
        (?P<sqft>[\d,]{3,7})\s*sq\s*ft
        .*?
        (?P<address>\d{1,6}\s+[A-Za-z0-9#.\-'\s]+,\s*[A-Za-z.\-\s]+,\s*[A-Z]{2}\s+\d{5})
        """,
        re.IGNORECASE | re.DOTALL | re.VERBOSE,
    )

    for match in sold_pattern.finditer(page_text):
        address = normalize_text(match.group("address"))
        price = clean_number(match.group("price"))

        if not address or price is None:
            continue

        comps.append(
            {
                "address": address,
                "price": price,
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
                "zip_code": extract_zip(address),
                "lat": None,
                "lng": None,
                "dom": None,
                "superior_features": "",
                "inferior_features": "",
                "notes": "Realtor visible-text candidate comp",
            }
        )

    deduped = []
    seen = set()

    for comp in comps:
        key = (comp["address"], comp["price"], comp["status"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(comp)

    return deduped


def parse_realtor(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    script = soup.find("script", id="__NEXT_DATA__")
    if script:
        try:
            data = json.loads(script.string)
            prop = data["props"]["pageProps"]["property"]
            details = prop.get("details", {})

            property_data = {
                "property_type": details.get("propertyType"),
                "beds": details.get("beds"),
                "baths": details.get("baths"),
                "sqft": details.get("sqft"),
                "year_built": details.get("yearBuilt"),
                "neighborhood": prop.get("address", {}).get("city", ""),
                "hoa_name": "",
                "building_name": "",
            }

            return {
                "property": property_data,
                "comps": [],
                "json_api_endpoints": extract_json_api_endpoints(soup),
            }
        except Exception:
            pass

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
    property_from_json = find_realtor_property_data(extract_structured_json_objects(soup))

    for key, value in property_from_json.items():
        if value not in (None, "", []):
            property_data[key] = value

    # 2) Embedded script extraction: state objects from script assignments.
    embedded_property = find_realtor_property_data(extract_embedded_state_objects(soup))
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
            "[data-testid='property-meta-bed-bath']",
            "[data-testid='property-meta']",
            "[class*='listing-detail']",
        ],
    )
    if rendered_text:
        property_data = parse_property_from_text_generic(rendered_text, property_data)

    # 4) Regex fallback from full page text.
    property_data = parse_property_from_text_generic(page_text, property_data)
    comps = parse_realtor_comp_blocks(page_text)

    return {
        "property": property_data,
        "comps": comps[:10],
        "json_api_endpoints": _json_api_endpoints,
    }
