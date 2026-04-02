import requests
from bs4 import BeautifulSoup
import json
import time
import re
from scraper import get_session_manager

url = "https://www.realtor.com/realestateandhomes-detail/1623-E-Carson-Rd_Phoenix_AZ_85042_M15073-87002"

print("Fetching Realtor page with session manager...")
session_mgr = get_session_manager()
resp_text = session_mgr.get(url, max_retries=5)

if resp_text is None:
    print("Failed to fetch page after retries")
else:
    print(f"Status: Success (received {len(resp_text)} characters)")
    
    # Look for __NEXT_DATA__
    match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', resp_text, re.DOTALL)
    
    if match:
        print("\n✓ Found __NEXT_DATA__!")
        json_str = match.group(1)
        print(f"Length: {len(json_str)} characters")
        
        # Save to file for inspection
        with open("realtor_next_data.json", "w") as f:
            f.write(json_str)
        print("Saved to realtor_next_data.json")
        
        # Try to parse and show snippet
        try:
            data = json.loads(json_str)
            print("\nFirst 2000 characters of __NEXT_DATA__:")
            print(json.dumps(data, indent=2)[:2000])
        except Exception as e:
            print(f"Error parsing JSON: {e}")
    else:
        print("\n✗ __NEXT_DATA__ not found")
        
        # Check for property data indicators
        indicators = [
            ("'props'", "'props'" in resp_text),
            ("'pageProps'", "'pageProps'" in resp_text),
            ("'property'", "'property'" in resp_text.lower()),
            ("'beds'", "'beds'" in resp_text.lower()),
            ("'baths'", "'baths'" in resp_text.lower()),
        ]
        
        print("\nPage content indicators:")
        for name, found in indicators:
            print(f"  {'✓' if found else '✗'} {name}")
