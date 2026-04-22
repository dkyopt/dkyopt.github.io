from __future__ import annotations

import argparse
import json
import re
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
import yaml
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "_config.yml"
OUTPUT_PATH = ROOT / "local" / "visitor-map.html"
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
    return [
        {
            "lat": float(location["lat"]),
            "long": float(location["long"]),
            "city_name": location.get("city_name"),
            "country_name": location.get("country_name"),
            "visits": int(location.get("ip2map_visits", 0)),
        }
        for location in raw_locations
    ]


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

        recent.append(
            {
                "timestamp_utc": parse_timestamp(cells[0].get_text(" ", strip=True)),
                "location": cells[2].get_text(" ", strip=True),
                "usage_type": cells[3].get_text(" ", strip=True),
                "proxy": cells[4].get_text(" ", strip=True),
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
    return {
        "site": parse_host(site_url),
        "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "visitors": extract_locations(html),
        "recent_visitors": extract_recent_visits(html),
    }


def render_html(payload: dict) -> str:
    title = f"Private Visitor Map for {payload['site']}"
    data_json = json.dumps(payload)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.css">
  <style>
    :root {{
      color-scheme: light;
      --bg: #f3f6fb;
      --panel: #ffffff;
      --line: #d9e0ea;
      --text: #1d2735;
      --muted: #5c6675;
      --accent: #0d5bd7;
      --marker: #b3261e;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--text);
    }}
    .page {{
      max-width: 1200px;
      margin: 0 auto;
      padding: 24px;
    }}
    .header {{
      margin-bottom: 20px;
    }}
    .header h1 {{
      margin: 0;
      font-size: 28px;
    }}
    .header p {{
      margin: 8px 0 0;
      color: var(--muted);
    }}
    .layout {{
      display: grid;
      grid-template-columns: minmax(0, 2fr) minmax(280px, 1fr);
      gap: 20px;
    }}
    .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 14px;
      overflow: hidden;
    }}
    #map {{
      height: 560px;
      width: 100%;
    }}
    .panel-body {{
      padding: 18px 20px;
    }}
    .stats {{
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      margin-top: 12px;
    }}
    .pill {{
      display: inline-flex;
      align-items: center;
      padding: 6px 10px;
      border: 1px solid var(--line);
      border-radius: 999px;
      background: #f9fbff;
      font-size: 13px;
      color: var(--muted);
    }}
    .list {{
      list-style: none;
      margin: 0;
      padding: 0;
    }}
    .list li {{
      padding: 14px 0;
      border-bottom: 1px solid var(--line);
    }}
    .list li:last-child {{
      border-bottom: 0;
    }}
    .place {{
      display: block;
      font-weight: 600;
    }}
    .meta {{
      display: block;
      margin-top: 4px;
      color: var(--muted);
      font-size: 14px;
    }}
    .empty {{
      color: var(--muted);
    }}
    @media (max-width: 900px) {{
      .layout {{
        grid-template-columns: 1fr;
      }}
      #map {{
        height: 380px;
      }}
    }}
  </style>
</head>
<body>
  <div class="page">
    <div class="header">
      <h1>{title}</h1>
      <p>This file is generated locally and is not published to GitHub Pages.</p>
      <div class="stats">
        <span class="pill">{len(payload["visitors"])} locations</span>
        <span class="pill">{len(payload["recent_visitors"])} recent visits</span>
        <span class="pill">Updated {payload["updated_at"]}</span>
      </div>
    </div>
    <div class="layout">
      <div class="panel"><div id="map"></div></div>
      <div class="panel">
        <div class="panel-body">
          <h2 style="margin-top:0;font-size:20px;">Recent Visits</h2>
          <ul class="list" id="recent-visits"></ul>
        </div>
      </div>
    </div>
  </div>

  <script src="https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.js"></script>
  <script>
    const data = {data_json};
    const map = L.map("map", {{
      scrollWheelZoom: false,
      worldCopyJump: true
    }}).setView([20, 0], 2);

    L.tileLayer("https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png", {{
      minZoom: 1,
      maxZoom: 6,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
    }}).addTo(map);

    const bounds = [];
    for (const visitor of data.visitors) {{
      if (typeof visitor.lat !== "number" || typeof visitor.long !== "number") continue;
      const visits = Number(visitor.visits || 1);
      const marker = L.circleMarker([visitor.lat, visitor.long], {{
        radius: Math.max(5, Math.min(16, 4 + Math.sqrt(visits) * 2)),
        color: "#fff",
        weight: 1,
        fillColor: "#b3261e",
        fillOpacity: 0.6
      }});
      const place = [visitor.city_name, visitor.country_name].filter(Boolean).join(", ") || "Unknown location";
      marker.bindPopup(`<strong>${{place}}</strong><br>${{visits}} visit${{visits === 1 ? "" : "s"}}`);
      marker.addTo(map);
      bounds.push([visitor.lat, visitor.long]);
    }}

    if (bounds.length === 1) {{
      map.setView(bounds[0], 3);
    }} else if (bounds.length > 1) {{
      map.fitBounds(bounds, {{ padding: [24, 24] }});
    }}

    const list = document.getElementById("recent-visits");
    if (!data.recent_visitors.length) {{
      list.innerHTML = '<li class="empty">No visitor data yet.</li>';
    }} else {{
      list.innerHTML = data.recent_visitors.slice(0, 20).map((entry) => {{
        const details = [entry.timestamp_utc || "Unknown time", entry.usage_type].filter(Boolean).join(" · ");
        return `
          <li>
            <span class="place">${{entry.location || "Unknown location"}}</span>
            <span class="meta">${{details}}</span>
          </li>
        `;
      }}).join("");
    }}
  </script>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a private visitor map HTML file.")
    parser.add_argument("--open", action="store_true", help="Open the generated HTML in a browser.")
    args = parser.parse_args()

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
    OUTPUT_PATH.write_text(render_html(payload), encoding="utf-8")
    print(f"Wrote private visitor map to {OUTPUT_PATH}")

    if args.open:
        webbrowser.open(OUTPUT_PATH.as_uri())


if __name__ == "__main__":
    main()
