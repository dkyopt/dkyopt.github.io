from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
import yaml
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "_config.yml"
OUTPUT_PATH = ROOT / "assets" / "data" / "visitor-map.json"
IP2MAP_REPORT_URL = "https://www.ip2map.com/"


def load_site_url() -> str:
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    site_url = str(config.get("url", "")).strip()
    baseurl = str(config.get("baseurl", "")).strip()

    if not site_url:
        raise RuntimeError("Missing `url` in _config.yml")

    site_url = site_url.rstrip("/")
    if baseurl:
        site_url = f"{site_url}/{baseurl.strip('/')}"
    return f"{site_url}/"


def parse_host(site_url: str) -> str:
    return urlparse(site_url).netloc


def fetch_report(site_url: str) -> str:
    headers = {
        "Referer": site_url,
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
        ),
    }
    response = requests.get(IP2MAP_REPORT_URL, headers=headers, timeout=30)
    response.raise_for_status()
    return response.text


def extract_locations(html: str) -> list[dict]:
    match = re.search(r"var visitors = (\[[\s\S]*?\]);", html)
    if not match:
        return []

    raw_locations = json.loads(match.group(1))
    locations = []
    for location in raw_locations:
        locations.append(
            {
                "lat": float(location["lat"]),
                "long": float(location["long"]),
                "city_name": location.get("city_name"),
                "country_name": location.get("country_name"),
                "visits": int(location.get("ip2map_visits", 0)),
            }
        )
    return locations


def parse_timestamp(value: str) -> str | None:
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d %I:%M:%S %p")
    except ValueError:
        return None

    return parsed.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def extract_recent_visits(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if table is None:
        return []

    recent = []
    rows = table.find_all("tr")[1:]
    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 5:
            continue

        timestamp = cells[0].get_text(" ", strip=True)
        location = cells[2].get_text(" ", strip=True)
        usage_type = cells[3].get_text(" ", strip=True)
        proxy = cells[4].get_text(" ", strip=True)

        recent.append(
            {
                "timestamp_utc": parse_timestamp(timestamp),
                "location": location,
                "usage_type": usage_type,
                "proxy": proxy,
            }
        )

    return recent


def extract_reported_host(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    heading = soup.find("h1")
    if heading is None:
        return None

    match = re.search(r"20 Most Recent Visitors to (.+)", heading.get_text(" ", strip=True))
    if not match:
        return None

    return match.group(1).strip()


def build_payload(site_url: str, html: str) -> dict:
    locations = extract_locations(html)
    recent_visits = extract_recent_visits(html)

    return {
        "site": parse_host(site_url),
        "source": "IP2Map",
        "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "has_data": bool(locations or recent_visits),
        "visitors": locations,
        "recent_visitors": recent_visits,
    }


def main() -> None:
    site_url = load_site_url()
    html = fetch_report(site_url)
    expected_host = parse_host(site_url)
    reported_host = extract_reported_host(html)

    if reported_host and reported_host != expected_host:
        raise RuntimeError(
            f"IP2Map returned data for {reported_host!r}, expected {expected_host!r}"
        )

    payload = build_payload(site_url, html)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
