from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
from typing import Optional
from scraper import scrape_property_bundle
import os

app = FastAPI()

SCRAPER_API_KEY = os.getenv("SCRAPER_API_KEY", "dsc_live_key_7a3f2e1b9c4d8e5f6a2b1c3d4e5f6a7b")

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

    return scrape_property_bundle(
        property_address=payload.property_address,
        condition=payload.condition or "Good"
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)