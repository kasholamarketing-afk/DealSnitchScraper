import requests
import json
import re
from urllib.parse import quote

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "*/*",
    "Referer": "https://www.google.com/"
}

def fetch_text(url: str) -> str:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        if resp.status_code == 200:
            return resp.text
    except Exception:
        pass
    return ""

def normalize_address_query(address: str) -> str:
    return " ".join(str(address).strip().split())

def strip_jsonp_prefix(text: str) -> str:
    text = text.strip()
    if text.startswith("{}&&"):
        text = text[4:].strip()
    match = re.match(r"^[a-zA-Z0-9_]+\((.*)\)\s*;?$", text, re.DOTALL)
    if match:
        text = match.group(1).strip()
    return text

def safe_json_loads(text: str):
    try:
        return json.loads(text)
    except Exception:
        return None

def walk_for_urls(obj, urls: list, domain_hint: str = ""):
    if isinstance(obj, dict):
        for _, v in obj.items():
            if isinstance(v, str):
                if domain_hint == "redfin":
                    if (v.startswith("/") or v.startswith("https://www.redfin.com/")) and "/home/" in v:
                        urls.append(v)
                elif domain_hint == "realtor":
                    if "realtor.com/realestateandhomes-detail/" in v:
                        urls.append(v)
                elif domain_hint == "zillow":
                    if "zillow.com/homedetails/" in v:
                        urls.append(v)
            walk_for_urls(v, urls, domain_hint)
    elif isinstance(obj, list):
        for item in obj:
            walk_for_urls(item, urls, domain_hint)

def score_candidate_url(candidate_url: str, address: str) -> int:
    score = 0
    address_l = address.lower()
    path_l = candidate_url.lower()

    house_num_match = re.match(r"^\s*(\d+)", address_l)
    if house_num_match and house_num_match.group(1) in path_l:
        score += 30

    zip_match = re.search(r"\b(\d{5})\b", address_l)
    if zip_match and zip_match.group(1) in path_l:
        score += 20

    street_part = re.sub(r"^\s*\d+\s+", "", address_l)
    street_part = re.sub(r"[^a-z0-9\s]", " ", street_part)
    tokens = [t for t in street_part.split() if len(t) > 2]

    token_hits = 0
    for token in tokens[:5]:
        if token in path_l:
            token_hits += 1
    score += token_hits * 8

    return score

def build_full_redfin_url(path_or_url: str) -> str:
    if not path_or_url:
        return ""
    if path_or_url.startswith("http"):
        return path_or_url
    return f"https://www.redfin.com{path_or_url}"

def find_redfin_property_url(address: str) -> str:
    normalized = normalize_address_query(address)
    encoded = quote(normalized)

    urls = []
    for endpoint in [
        f"https://www.redfin.com/stingray/do/location-autocomplete?location={encoded}&start=0&count=10&v=2&market=losangeles&al=1&iss=false&ooa=true",
        f"https://www.redfin.com/stingray/do/location-autocomplete?location={encoded}"
    ]:
        raw = fetch_text(endpoint)
        if not raw:
            continue
        data = safe_json_loads(strip_jsonp_prefix(raw))
        if data is None:
            continue
        walk_for_urls(data, urls, "redfin")

    if not urls:
        return ""

    urls = list(dict.fromkeys(urls))
    best = sorted(urls, key=lambda u: score_candidate_url(u, normalized), reverse=True)[0]
    return build_full_redfin_url(best)

def find_realtor_property_url(address: str) -> str:
    normalized = normalize_address_query(address)
    slug = normalized.replace(" ", "-")
    # Simple V1 direct search pattern.
    # Replace later with actual search-page parsing if needed.
    return f"https://www.realtor.com/realestateandhomes-search/{slug}"

def find_zillow_property_url(address: str) -> str:
    normalized = normalize_address_query(address)
    slug = normalized.replace(" ", "-")
    # Simple V1 direct search pattern.
    # Replace later with actual search-page parsing if needed.
    return f"https://www.zillow.com/homes/{slug}_rb/"
