from bs4 import BeautifulSoup

from parser_common import (
    clean_float,
    clean_number,
    normalize_text,
    extract_structured_json_objects,
    extract_embedded_state_objects,
    extract_json_api_endpoints,
    extract_text_by_selectors,
    walk_json,
    deep_get,
    parse_property_from_text_generic,
)


def _apply_property_from_json_blocks(property_data: dict, json_blocks: list) -> dict:
    for block in json_blocks:
        all_nodes = []
        walk_json(block, all_nodes)

        for node in all_nodes:
            if not isinstance(node, dict):
                continue

            lowered = {str(k).lower(): v for k, v in node.items()}

            if property_data["beds"] is None:
                beds = lowered.get("beds") or lowered.get("numberofbedrooms")
                property_data["beds"] = clean_float(beds)

            if property_data["baths"] is None:
                baths = lowered.get("baths") or lowered.get("numberofbathrooms")
                property_data["baths"] = clean_float(baths)

            if property_data["sqft"] is None:
                sqft = lowered.get("sqft") or lowered.get("livingarea")
                property_data["sqft"] = clean_number(sqft)

            if property_data["year_built"] is None:
                year = lowered.get("yearbuilt") or lowered.get("year_built")
                property_data["year_built"] = clean_number(year)

            if not property_data["property_type"]:
                ptype = lowered.get("propertytype") or lowered.get("hometype")
                if isinstance(ptype, str):
                    property_data["property_type"] = normalize_text(ptype)

    return property_data


def parse_zillow(html: str) -> dict:
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
    structured_objects = extract_structured_json_objects(soup)

    # Explicit Next.js path extraction when present:
    # props.pageProps.property.details
    for obj in structured_objects:
        details = deep_get(obj, ["props", "pageProps", "property", "details"])
        if not isinstance(details, dict):
            continue

        if property_data["beds"] is None:
            property_data["beds"] = clean_float(details.get("bedrooms") or details.get("beds"))

        if property_data["baths"] is None:
            property_data["baths"] = clean_float(details.get("bathrooms") or details.get("baths"))

        if property_data["sqft"] is None:
            property_data["sqft"] = clean_number(
                details.get("livingArea")
                or details.get("livingAreaValue")
                or details.get("sqft")
            )

        if property_data["year_built"] is None:
            property_data["year_built"] = clean_number(details.get("yearBuilt") or details.get("year_built"))

        if not property_data["property_type"]:
            ptype = details.get("homeType") or details.get("propertyType")
            if isinstance(ptype, str):
                property_data["property_type"] = normalize_text(ptype)

    property_data = _apply_property_from_json_blocks(
        property_data,
        structured_objects,
    )

    # 2) Embedded script extraction: state objects from script assignments.
    property_data = _apply_property_from_json_blocks(
        property_data,
        extract_embedded_state_objects(soup),
    )

    # JSON APIs called/referenced by the page (discovery stage).
    _json_api_endpoints = extract_json_api_endpoints(soup)

    # 3) Visible DOM selectors after render.
    rendered_text = extract_text_by_selectors(
        soup,
        [
            "[data-testid='bed-bath-beyond']",
            "[data-testid='facts-and-features']",
            "[class*='fact']",
            "main",
        ],
    )
    if rendered_text:
        property_data = parse_property_from_text_generic(rendered_text, property_data)

    # 4) Regex fallback from full page text.
    property_data = parse_property_from_text_generic(page_text, property_data)

    return {
        "property": property_data,
        "comps": [],
        "json_api_endpoints": _json_api_endpoints,
    }
