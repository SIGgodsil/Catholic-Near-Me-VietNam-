// Bản đồ Leaflet: tile OpenStreetMap, marker người dùng, vòng bán kính, ghim nhà thờ.
/* global L */
import { popupHtml } from "./popup.js";

const TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';
const INITIAL_VIEW = { center: [10.7769, 106.7009], zoom: 13 }; // trung tâm TP.HCM, nơi có dữ liệu

const PIN_SVG = `
  <svg viewBox="0 0 32 42" aria-hidden="true">
    <path class="pin-body" d="M16 1C7.7 1 1 7.6 1 15.8 1 27 16 41 16 41s15-14 15-25.2C31 7.6 24.3 1 16 1z"/>
    <path class="pin-cross" d="M14.5 7h3v5h5v3h-5v10h-3V15h-5v-3h5z"/>
  </svg>`;

function churchIcon(upcoming) {
  return L.divIcon({
    className: `pin${upcoming ? " pin--upcoming" : ""}`,
    html: PIN_SVG,
    iconSize: [32, 42],
    iconAnchor: [16, 41],
    popupAnchor: [0, -36],
  });
}

const USER_ICON = L.divIcon({ className: "user-dot", html: "<span></span>", iconSize: [24, 24], iconAnchor: [12, 12] });

export function createMap(element, { onChurchSelect } = {}) {
  const map = L.map(element, { zoomControl: false }).setView(INITIAL_VIEW.center, INITIAL_VIEW.zoom);
  L.control.zoom({ position: "topright", zoomInTitle: "Phóng to", zoomOutTitle: "Thu nhỏ" }).addTo(map);
  L.tileLayer(TILE_URL, { maxZoom: 19, attribution: ATTRIBUTION }).addTo(map);

  const userLayer = L.layerGroup().addTo(map);
  const churchLayer = L.layerGroup().addTo(map);
  const markers = new Map();
  let origin = null;
  let radiusCircle = null;

  function showUser(lat, lon, { radiusKm, accuracyM, label }) {
    userLayer.clearLayers();
    origin = { lat, lon };
    if (accuracyM && accuracyM > 30) {
      L.circle([lat, lon], { radius: accuracyM, color: "#1d6fe0", weight: 1, fillOpacity: 0.08, interactive: false })
        .addTo(userLayer);
    }
    radiusCircle = L.circle([lat, lon], {
      radius: radiusKm * 1000, color: "#7a5410", weight: 2, dashArray: "6 6", fillColor: "#c9a13b", fillOpacity: 0.07,
      interactive: false,
    }).addTo(userLayer);
    L.marker([lat, lon], { icon: USER_ICON, title: "Vị trí của bạn", keyboard: false, zIndexOffset: 1000 })
      .bindTooltip(label || "Vị trí của bạn", { direction: "top", offset: [0, -10] })
      .addTo(userLayer);
    map.fitBounds(radiusCircle.getBounds(), { padding: [20, 20] });
  }

  function showChurches(churches) {
    churchLayer.clearLayers();
    markers.clear();
    for (const c of churches) {
      const marker = L.marker([c.lat, c.lon], {
        icon: churchIcon(Boolean(c.next_mass)),
        title: c.name,
        alt: c.name,
        riseOnHover: true,
        zIndexOffset: c.next_mass ? 500 : 0,
      })
        .bindPopup(() => popupHtml(c, origin), { maxWidth: 340, autoPanPaddingTopLeft: [20, 20] })
        .on("popupopen", () => onChurchSelect?.(c.id))
        .on("popupclose", () => onChurchSelect?.(null))
        .addTo(churchLayer);
      markers.set(c.id, marker);
    }
  }

  function openChurch(id) {
    const marker = markers.get(id);
    if (!marker) return;
    map.setView(marker.getLatLng(), Math.max(map.getZoom(), 15));
    marker.openPopup();
  }

  return { showUser, showChurches, openChurch, invalidateSize: () => map.invalidateSize() };
}
