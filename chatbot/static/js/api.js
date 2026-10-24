// Gọi API của backend. Lỗi được chuyển thành Error có message tiếng Việt để hiện thẳng cho người dùng.

async function getJson(url, fallbackMessage) {
  let res;
  try {
    res = await fetch(url, { headers: { Accept: "application/json" } });
  } catch {
    throw new Error("Không kết nối được máy chủ. Kiểm tra server còn chạy không.");
  }
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(typeof body?.detail === "string" ? body.detail : fallbackMessage);
  }
  return res.json();
}

// Thử giao diện ở thời điểm khác: mở trang với ?at=2026-10-25T16:30
const SIMULATED_AT = new URLSearchParams(location.search).get("at");

export function fetchNearby(lat, lon, radiusKm) {
  const qs = new URLSearchParams({ lat, lon, radius_km: radiusKm });
  if (SIMULATED_AT) qs.set("at", SIMULATED_AT);
  return getJson(`/api/churches/nearby?${qs}`, "Không tải được danh sách nhà thờ.");
}

export async function geocode(query) {
  const qs = new URLSearchParams({ q: query });
  const data = await getJson(`/api/geocode?${qs}`, "Không tìm được địa chỉ.");
  return data.results;
}
