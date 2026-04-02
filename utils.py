import re
import statistics


def build_output_bundle(property_address: str, condition: str, subject: dict, comps: list, source_results: list, best_source: dict):
    subject["property_address"] = property_address

    return {
        "subject": subject,
        "comps": comps[:15],
        "meta": {
            "condition": condition,
            "best_source": best_source.get("source", ""),
            "best_source_url": best_source.get("resolved_url", ""),
            "sources_checked": [s.get("source") for s in source_results],
            "sources_with_data": [s.get("source") for s in source_results if s.get("raw_found")],
            "used_browser_sources": [s.get("source") for s in source_results if s.get("used_browser")],
            "status_codes": {
                s.get("source"): s.get("status_code") for s in source_results
            },
            "scraper_status": "ok" if subject and any(v not in ("", None, False, []) for v in subject.values()) else "partial"
        }
    }


def _normalize_text(value) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split()).strip()


def _normalize_address(value) -> str:
    return _normalize_text(value).lower()


def _to_clean_number_string(value) -> str:
    if value in (None, ""):
        return ""
    text = str(value).strip()
    cleaned = re.sub(r"[^0-9.]", "", text)
    if not cleaned:
        return ""
    try:
        number = float(cleaned)
        if number.is_integer():
            return str(int(number))
        return str(number)
    except Exception:
        return ""


def _to_bool_string(value: bool) -> str:
    return "true" if value else "false"


def _format_property_type(value: str) -> str:
    normalized = _normalize_text(value).lower().replace("_", " ")
    mapping = {
        "single family": "Single Family",
        "singlefamily": "Single Family",
        "condo": "Condo",
        "townhome": "Townhome",
        "town house": "Townhome",
        "multi family": "Multi Family",
    }
    if normalized in mapping:
        return mapping[normalized]
    return normalized.title() if normalized else ""


def _condition_multiplier(condition: str) -> float:
    lookup = {
        "poor": 0.90,
        "fair": 0.95,
        "good": 1.00,
        "great": 1.05,
        "perfect": 1.08,
    }
    return lookup.get(_normalize_text(condition).lower(), 1.00)


def _estimate_price(subject: dict, comps: list, condition: str) -> str:
    subject_price = _to_clean_number_string(subject.get("price"))
    if subject_price:
        return subject_price

    comp_prices = []
    for comp in comps:
        raw = _to_clean_number_string(comp.get("price"))
        if raw:
            try:
                comp_prices.append(float(raw))
            except Exception:
                continue

    if not comp_prices:
        return ""

    base = statistics.median(comp_prices)
    adjusted = int(round(base * _condition_multiplier(condition)))
    return str(adjusted)


def build_flat_response(bundle: dict, condition: str) -> dict:
    subject = bundle.get("subject", {})
    comps = bundle.get("comps", [])

    response = {
        "property_address": _normalize_address(subject.get("property_address")),
        "property_type": _format_property_type(subject.get("property_type", "")),
        "beds": _to_clean_number_string(subject.get("beds")),
        "baths": _to_clean_number_string(subject.get("baths")),
        "sqft": _to_clean_number_string(subject.get("sqft")),
        "price": _estimate_price(subject, comps, condition),
        "year_built": _to_clean_number_string(subject.get("year_built")),
        "neighborhood": _normalize_text(subject.get("neighborhood")),
        "hoa_name": _normalize_text(subject.get("hoa_name")),
        "building_name": _normalize_text(subject.get("building_name")),
        "condition": _normalize_text(condition) or "Good",
    }

    subject_neighborhood = _normalize_text(subject.get("neighborhood")).lower()
    subject_hoa = _normalize_text(subject.get("hoa_name")).lower()
    subject_building = _normalize_text(subject.get("building_name")).lower()

    for idx in range(1, 6):
        comp = comps[idx - 1] if idx <= len(comps) else {}
        has_comp = bool(comp)
        comp_neighborhood = _normalize_text(comp.get("neighborhood")).lower() if has_comp else ""
        comp_hoa = _normalize_text(comp.get("hoa_name")).lower() if has_comp else ""
        comp_building = _normalize_text(comp.get("building_name")).lower() if has_comp else ""
        status = _normalize_text(comp.get("status")).lower() if has_comp else ""
        is_active = status in {"active", "new", "for_sale", "for sale", "pending"}

        response[f"comp_{idx}_address"] = _normalize_address(comp.get("address")) if has_comp else ""
        response[f"comp_{idx}_price"] = _to_clean_number_string(comp.get("price")) if has_comp else ""
        response[f"comp_{idx}_type"] = _format_property_type(comp.get("property_type", "")) if has_comp else ""
        response[f"comp_{idx}_same_neighborhood"] = (
            _to_bool_string(bool(subject_neighborhood and comp_neighborhood and subject_neighborhood == comp_neighborhood))
            if has_comp else ""
        )
        response[f"comp_{idx}_same_complex"] = (
            _to_bool_string(bool(subject_hoa and comp_hoa and subject_hoa == comp_hoa))
            if has_comp else ""
        )
        response[f"comp_{idx}_same_building"] = (
            _to_bool_string(bool(subject_building and comp_building and subject_building == comp_building))
            if has_comp else ""
        )
        response[f"comp_{idx}_is_active"] = _to_bool_string(is_active) if has_comp else ""
        response[f"comp_{idx}_dom"] = _to_clean_number_string(comp.get("dom")) if has_comp else ""

    return response