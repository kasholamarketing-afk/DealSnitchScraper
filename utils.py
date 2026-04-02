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