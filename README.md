# Property Scraper API

A FastAPI-based web scraper for analyzing property addresses.

## Installation

1. Install dependencies:
   ```bash
   python3 -m pip install -r requirements.txt
   ```

## Usage

Run the server:
```bash
python3 app.py
```

The server will start on http://0.0.0.0:8000

Endpoints:
- GET / : Health check
- POST /scrape : Analyze a property address

Example request to /scrape:
```json
{
  "property_address": "123 Main St, City, State",
  "condition": "good"
}
```

## Files

- app.py: FastAPI application
- scraper.py: Analysis logic
- parsers.py: HTML parsing utilities
- utils.py: Utility functions
- requirements.txt: Dependencies

## Customization

Update the analyze_address function in scraper.py to implement actual property analysis or scraping.