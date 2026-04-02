from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
from typing import Optional
from scraper import scrape_property_bundle, scrape_property_bundle_lite
import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

app = FastAPI()

SCRAPER_API_KEY = os.getenv("SCRAPER_API_KEY", "dsc_live_key_7a3f2e1b9c4d8e5f6a2b1c3d4e5f6a7b")
SCRAPE_REQUEST_TIMEOUT_SECONDS = int(os.getenv("SCRAPE_REQUEST_TIMEOUT_SECONDS", "25"))
SCRAPE_LITE_TIMEOUT_SECONDS = int(os.getenv("SCRAPE_LITE_TIMEOUT_SECONDS", "10"))

class ScrapeRequest(BaseModel):
    property_address: str
    condition: Optional[str] = None

@app.get("/")
def health():
    return {"status": "ok"}

@app.post("/scrape")
def scrape(payload: ScrapeRequest, x_api_key: str = Header(default="")):
    if SCRAPER_API_KEY and x_api_key != SCRAPER_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

    if not payload.property_address:
        raise HTTPException(status_code=400, detail="property_address is required")

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            scrape_property_bundle,
            payload.property_address,
            payload.condition or "Good",
        )
        try:
            return future.result(timeout=SCRAPE_REQUEST_TIMEOUT_SECONDS)
        except FutureTimeoutError:
            # Fail-soft for webhook callers: return any data we can get quickly.
            fallback = scrape_property_bundle_lite(
                property_address=payload.property_address,
                condition=payload.condition or "Good",
            )
            fallback.setdefault("meta", {})
            fallback["meta"]["scraper_status"] = "partial_timeout_fallback"
            return fallback


@app.post("/scrape-lite")
def scrape_lite(payload: ScrapeRequest, x_api_key: str = Header(default="")):
    if SCRAPER_API_KEY and x_api_key != SCRAPER_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

    if not payload.property_address:
        raise HTTPException(status_code=400, detail="property_address is required")

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            scrape_property_bundle_lite,
            payload.property_address,
            payload.condition or "Good",
        )
        try:
            result = future.result(timeout=SCRAPE_LITE_TIMEOUT_SECONDS)
            result.setdefault("meta", {})
            result["meta"]["mode"] = "lite"
            return result
        except FutureTimeoutError:
            return {
                "subject": {
                    "property_address": payload.property_address,
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
                    "is_unique_property": False,
                },
                "comps": [],
                "meta": {
                    "condition": payload.condition or "Good",
                    "scraper_status": "timeout_no_data",
                    "mode": "lite",
                    "sources_checked": [],
                    "sources_with_data": [],
                },
            }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)