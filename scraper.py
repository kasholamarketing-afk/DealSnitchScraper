import json
import time
import random
import requests
import os

from parsers import parse_redfin, parse_realtor, parse_zillow
from url_finders import find_redfin_property_url, find_realtor_property_url, find_zillow_property_url
from utils import build_output_bundle

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except Exception:
    PLAYWRIGHT_AVAILABLE = False

FAST_MODE = os.getenv("SCRAPER_FAST_MODE", "1") == "1"
ENABLE_BROWSER_FALLBACK = os.getenv("SCRAPER_ENABLE_BROWSER", "0") == "1"
HTTP_TIMEOUT_SECONDS = int(os.getenv("SCRAPER_HTTP_TIMEOUT", "8" if FAST_MODE else "20"))
BROWSER_TIMEOUT_MS = int(os.getenv("SCRAPER_BROWSER_TIMEOUT_MS", "12000" if FAST_MODE else "45000"))
DELAY_MIN = float(os.getenv("SCRAPER_DELAY_MIN", "0.1" if FAST_MODE else "1.2"))
DELAY_MAX = float(os.getenv("SCRAPER_DELAY_MAX", "0.4" if FAST_MODE else "2.8"))

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
]

def get_proxy():
    import os
    proxy = os.getenv("SCRAPER_PROXY", "").strip()
    if not proxy:
        return None
    return {
        "http": proxy,
        "https": proxy
    }

def fetch_html(url: str, timeout_seconds: int = None, allow_browser_fallback: bool = None):
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.google.com/",
        "Connection": "keep-alive",
    }

    proxy = get_proxy()
    used_browser = False
    status_code = None
    html = ""

    if DELAY_MAX > 0:
        time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

    request_timeout = timeout_seconds or HTTP_TIMEOUT_SECONDS
    browser_fallback_enabled = ENABLE_BROWSER_FALLBACK if allow_browser_fallback is None else allow_browser_fallback

    try:
        resp = requests.get(url, headers=headers, timeout=request_timeout, proxies=proxy)
        status_code = resp.status_code
        if resp.status_code == 200:
            html = resp.text
        elif resp.status_code in (403, 429):
            html = ""
    except Exception:
        html = ""

    if (
        (not html or "captcha" in html.lower() or "rate limited" in html.lower())
        and PLAYWRIGHT_AVAILABLE
        and browser_fallback_enabled
    ):
        html = fetch_with_browser(url, proxy_url=proxy["http"] if proxy else None)
        used_browser = bool(html)

    return {
        "html": html,
        "status_code": status_code,
        "used_browser": used_browser
    }

def fetch_with_browser(url: str, proxy_url: str = None):
    if not PLAYWRIGHT_AVAILABLE:
        return ""

    try:
        with sync_playwright() as p:
            launch_args = {"headless": True}
            if proxy_url:
                launch_args["proxy"] = {"server": proxy_url}

            browser = p.chromium.launch(**launch_args)
            page = browser.new_page(
                user_agent=random.choice(USER_AGENTS),
                locale="en-US"
            )
            page.goto(url, timeout=BROWSER_TIMEOUT_MS, wait_until="domcontentloaded")
            page.wait_for_timeout(1200 if FAST_MODE else 3000)
            html = page.content()
            browser.close()
            return html
    except Exception:
        return ""

def try_redfin(address: str):
    url = find_redfin_property_url(address)
    if not url:
        return {
            "source": "redfin",
            "resolved_url": "",
            "property": {},
            "comps": [],
            "raw_found": False,
            "status_code": None,
            "used_browser": False
        }

    result = fetch_html(url)
    if not result["html"]:
        return {
            "source": "redfin",
            "resolved_url": url,
            "property": {},
            "comps": [],
            "raw_found": False,
            "status_code": result["status_code"],
            "used_browser": result["used_browser"]
        }

    parsed = parse_redfin(result["html"])
    return {
        "source": "redfin",
        "resolved_url": url,
        "property": parsed.get("property", {}),
        "comps": parsed.get("comps", []),
        "raw_found": True,
        "status_code": result["status_code"],
        "used_browser": result["used_browser"]
    }

def try_realtor(address: str):
    url = find_realtor_property_url(address)
    if not url:
        return {
            "source": "realtor",
            "resolved_url": "",
            "property": {},
            "comps": [],
            "raw_found": False,
            "status_code": None,
            "used_browser": False
        }

    result = fetch_html(url)
    if not result["html"]:
        return {
            "source": "realtor",
            "resolved_url": url,
            "property": {},
            "comps": [],
            "raw_found": False,
            "status_code": result["status_code"],
            "used_browser": result["used_browser"]
        }

    parsed = parse_realtor(result["html"])
    return {
        "source": "realtor",
        "resolved_url": url,
        "property": parsed.get("property", {}),
        "comps": parsed.get("comps", []),
        "raw_found": True,
        "status_code": result["status_code"],
        "used_browser": result["used_browser"]
    }

def try_zillow(address: str):
    url = find_zillow_property_url(address)
    if not url:
        return {
            "source": "zillow",
            "resolved_url": "",
            "property": {},
            "comps": [],
            "raw_found": False,
            "status_code": None,
            "used_browser": False
        }

    result = fetch_html(url)
    if not result["html"]:
        return {
            "source": "zillow",
            "resolved_url": url,
            "property": {},
            "comps": [],
            "raw_found": False,
            "status_code": result["status_code"],
            "used_browser": result["used_browser"]
        }

    parsed = parse_zillow(result["html"])
    return {
        "source": "zillow",
        "resolved_url": url,
        "property": parsed.get("property", {}),
        "comps": parsed.get("comps", []),
        "raw_found": True,
        "status_code": result["status_code"],
        "used_browser": result["used_browser"]
    }

def rank_sources(source_results: list):
    def source_score(item):
        prop = item.get("property", {})
        comp_count = len(item.get("comps", []))
        fields = sum(
            1 for key in ["property_type", "beds", "baths", "sqft", "year_built", "neighborhood"]
            if prop.get(key) not in (None, "", [])
        )
        return fields * 10 + comp_count * 3

    ranked = sorted(source_results, key=source_score, reverse=True)
    return ranked


def _empty_result(source: str):
    return {
        "source": source,
        "resolved_url": "",
        "property": {},
        "comps": [],
        "raw_found": False,
        "status_code": None,
        "used_browser": False,
    }


def try_redfin_lite(address: str):
    url = find_redfin_property_url(address)
    if not url:
        return _empty_result("redfin")

    result = fetch_html(url, timeout_seconds=4, allow_browser_fallback=False)
    if not result["html"]:
        out = _empty_result("redfin")
        out["resolved_url"] = url
        out["status_code"] = result.get("status_code")
        return out

    parsed = parse_redfin(result["html"])
    return {
        "source": "redfin",
        "resolved_url": url,
        "property": parsed.get("property", {}),
        "comps": parsed.get("comps", []),
        "raw_found": bool(parsed.get("property")),
        "status_code": result.get("status_code"),
        "used_browser": False,
    }


def try_realtor_lite(address: str):
    url = find_realtor_property_url(address)
    if not url:
        return _empty_result("realtor")

    result = fetch_html(url, timeout_seconds=4, allow_browser_fallback=False)
    if not result["html"]:
        out = _empty_result("realtor")
        out["resolved_url"] = url
        out["status_code"] = result.get("status_code")
        return out

    parsed = parse_realtor(result["html"])
    return {
        "source": "realtor",
        "resolved_url": url,
        "property": parsed.get("property", {}),
        "comps": parsed.get("comps", []),
        "raw_found": bool(parsed.get("property")),
        "status_code": result.get("status_code"),
        "used_browser": False,
    }


def _run_sources(property_address: str, condition: str, source_functions: list):
    sources = []

    for source_fn in source_functions:
        try:
            result = source_fn(property_address)
        except Exception:
            result = _empty_result(source_fn.__name__.replace("try_", ""))

        sources.append(result)

        if result.get("property"):
            best_source, subject, comps = merge_best_data(sources)
            return build_output_bundle(
                property_address=property_address,
                condition=condition,
                subject=subject,
                comps=comps,
                source_results=sources,
                best_source=best_source,
            )

    best_source, subject, comps = merge_best_data(sources)
    return build_output_bundle(
        property_address=property_address,
        condition=condition,
        subject=subject,
        comps=comps,
        source_results=sources,
        best_source=best_source,
    )

def merge_best_data(source_results: list):
    ranked = rank_sources(source_results)
    best = ranked[0] if ranked else {}

    subject = {
        "property_address": "",
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

    for source in ranked:
        prop = source.get("property", {})
        for key in subject.keys():
            if subject[key] in ("", None, False) and prop.get(key) not in ("", None, False, []):
                subject[key] = prop.get(key)

    all_comps = []
    seen = set()
    for source in ranked:
        for comp in source.get("comps", []):
            key = (comp.get("address"), comp.get("price"), comp.get("status"))
            if key in seen:
                continue
            seen.add(key)
            all_comps.append(comp)

    return best, subject, all_comps

def scrape_property_bundle(property_address: str, condition: str = "Good"):
    return _run_sources(property_address, condition, [try_redfin, try_realtor, try_zillow])


def scrape_property_bundle_lite(property_address: str, condition: str = "Good"):
    # Zapier-focused fast path: no browser fallback and only two fast sources.
    return _run_sources(property_address, condition, [try_redfin_lite, try_realtor_lite])
