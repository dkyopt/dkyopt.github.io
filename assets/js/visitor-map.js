(function () {
  const WIDGET_SELECTOR = "[data-visitor-map]";
  const LEAFLET_CSS_ID = "visitor-map-leaflet-css";
  const LEAFLET_SCRIPT_ID = "visitor-map-leaflet-script";

  function ensureLeafletCss() {
    if (document.getElementById(LEAFLET_CSS_ID)) {
      return;
    }

    const link = document.createElement("link");
    link.id = LEAFLET_CSS_ID;
    link.rel = "stylesheet";
    link.href = "https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.css";
    document.head.appendChild(link);
  }

  function ensureLeafletScript() {
    if (window.L) {
      return Promise.resolve(window.L);
    }

    const existing = document.getElementById(LEAFLET_SCRIPT_ID);
    if (existing) {
      return new Promise((resolve, reject) => {
        existing.addEventListener("load", () => resolve(window.L), { once: true });
        existing.addEventListener("error", reject, { once: true });
      });
    }

    return new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.id = LEAFLET_SCRIPT_ID;
      script.src = "https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.js";
      script.defer = true;
      script.onload = () => resolve(window.L);
      script.onerror = reject;
      document.body.appendChild(script);
    });
  }

  function formatDate(isoString) {
    if (!isoString) {
      return "Unknown time";
    }

    const parsed = new Date(isoString);
    if (Number.isNaN(parsed.getTime())) {
      return isoString;
    }

    return new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(parsed);
  }

  function setStatus(container, message) {
    const status = container.querySelector("[data-visitor-status]");
    if (status) {
      status.textContent = message;
    }
  }

  function updateSummary(container, data) {
    const locationCount = container.querySelector("[data-visitor-locations]");
    const eventCount = container.querySelector("[data-visitor-events]");
    const updated = container.querySelector("[data-visitor-updated]");

    if (locationCount) {
      locationCount.textContent = `${data.visitors.length} locations`;
    }

    if (eventCount) {
      eventCount.textContent = `${data.recent_visitors.length} recent visits`;
    }

    if (updated) {
      updated.textContent = data.updated_at
        ? `Updated ${formatDate(data.updated_at)}`
        : "Waiting for first sync";
    }
  }

  function renderRecentVisitors(container, recentVisitors) {
    const list = container.querySelector("[data-visitor-list]");
    if (!list) {
      return;
    }

    if (!recentVisitors.length) {
      list.innerHTML = '<li class="visitor-map__empty">No visitor data yet. The map will populate after a few visits.</li>';
      return;
    }

    list.innerHTML = recentVisitors
      .slice(0, 8)
      .map((entry) => {
        const location = entry.location || "Unknown location";
        const time = formatDate(entry.timestamp_utc);
        const details = [time, entry.usage_type].filter(Boolean).join(" · ");

        return `
          <li class="visitor-map__list-item">
            <span class="visitor-map__list-place">${location}</span>
            <span class="visitor-map__list-meta">${details}</span>
          </li>
        `;
      })
      .join("");
  }

  function renderMap(container, data) {
    const canvas = container.querySelector("[data-visitor-map-canvas]");
    if (!canvas) {
      return;
    }

    const map = window.L.map(canvas, {
      scrollWheelZoom: false,
      worldCopyJump: true,
    }).setView([20, 0], 2);

    window.L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 6,
      minZoom: 1,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    }).addTo(map);

    if (!data.visitors.length) {
      return;
    }

    const bounds = [];

    data.visitors.forEach((visitor) => {
      if (typeof visitor.lat !== "number" || typeof visitor.long !== "number") {
        return;
      }

      const position = [visitor.lat, visitor.long];
      const visitCount = Number(visitor.visits || 1);
      const marker = window.L.circleMarker(position, {
        radius: Math.max(5, Math.min(16, 4 + Math.sqrt(visitCount) * 2)),
        color: "#ffffff",
        weight: 1,
        fillColor: "#b22d2d",
        fillOpacity: 0.55,
      });

      const place = [visitor.city_name, visitor.country_name].filter(Boolean).join(", ");
      marker.bindPopup(
        `<span class="visitor-map__popup-title">${place || "Unknown location"}</span>` +
          `<span class="visitor-map__popup-meta">${visitCount} visit${visitCount === 1 ? "" : "s"}</span>`
      );
      marker.addTo(map);
      bounds.push(position);
    });

    if (!bounds.length) {
      return;
    }

    if (bounds.length === 1) {
      map.setView(bounds[0], 3);
      return;
    }

    map.fitBounds(bounds, { padding: [24, 24] });
  }

  async function buildWidget(container) {
    const source = container.getAttribute("data-source");
    if (!source) {
      setStatus(container, "Visitor map data source is missing.");
      return;
    }

    try {
      const response = await fetch(source, { cache: "no-store" });
      if (!response.ok) {
        throw new Error(`Failed to fetch ${source}`);
      }

      const data = await response.json();
      updateSummary(container, data);
      renderRecentVisitors(container, data.recent_visitors || []);

      if (!(data.visitors || []).length) {
        setStatus(container, "No visitor data yet. The map will update automatically after a few visits.");
        return;
      }

      await ensureLeafletScript();
      renderMap(container, {
        visitors: data.visitors || [],
        recent_visitors: data.recent_visitors || [],
      });

      const status = container.querySelector("[data-visitor-status]");
      if (status) {
        status.remove();
      }
    } catch (error) {
      setStatus(container, "Unable to load visitor map data right now.");
    }
  }

  async function init() {
    const widgets = Array.from(document.querySelectorAll(WIDGET_SELECTOR));
    if (!widgets.length) {
      return;
    }

    ensureLeafletCss();
    await Promise.all(widgets.map((widget) => buildWidget(widget)));
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();
