import requests
from bs4 import BeautifulSoup
import json
import re

url = "https://www.realtor.com/realestateandhomes-detail/1623-E-Carson-Rd_Phoenix_AZ_85042_M15073-87002"
headers = {"User-Agent": "Mozilla/5.0"}

try:
    resp = requests.get(url, headers=headers, timeout=15)
    print("Status:", resp.status_code)
    
    soup = BeautifulSoup(resp.text, "html.parser")
    
    # Look for JSON-LD structured data
    json_scripts = soup.find_all("script", attrs={"type": "application/ld+json"})
    print(f"\nFound {len(json_scripts)} JSON-LD scripts")
    
    if json_scripts:
        for i, script in enumerate(json_scripts[:1]):  # Show first one
            try:
                data = json.loads(script.string)
                print(f"\nJSON-LD Block {i}:")
                print(json.dumps(data, indent=2)[:1000])
            except Exception as e:
                print(f"Failed to parse JSON-LD block {i}: {e}")
    
    # Look for key property data in page text
    page_text = soup.get_text()
    
    # Search for beds/baths/sqft patterns
    beds_match = re.search(r'(\d+)\s*beds?', page_text, re.IGNORECASE)
    baths_match = re.search(r'(\d+(?:\.\d+)?)\s*baths?', page_text, re.IGNORECASE)
    sqft_match = re.search(r'([\d,]+)\s*sq\s*ft', page_text, re.IGNORECASE)
    
    print("\n--- Pattern Matches ---")
    print(f"Beds: {beds_match.group(1) if beds_match else 'Not found'}")
    print(f"Baths: {baths_match.group(1) if baths_match else 'Not found'}")
    print(f"Sqft: {sqft_match.group(1) if sqft_match else 'Not found'}")
    
    # Print a sample of the page text
    print("\n--- Page Text Sample (first 1000 chars) ---")
    print(page_text[:1000])
    
except Exception as e:
    print(f"Error: {e}")
