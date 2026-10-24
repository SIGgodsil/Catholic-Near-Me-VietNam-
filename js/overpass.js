// overpass.js – Tạo truy vấn Overpass QL, gửi tới Overpass API và nhận dữ liệu thô từ OpenStreetMap.
// File này KHÔNG chuẩn hóa hay lọc dữ liệu (việc đó của church.js).

import { CONFIG } from "../config/config.js";

// Mã lỗi trùng tên với trạng thái giao diện để app.js dùng trực tiếp
const ERROR_MESSAGES = {
  OVERPASS_ERROR: "Không thể kết nối tới dịch vụ dữ liệu bản đồ.",
  NETWORK_ERROR: "Kiểm tra kết nối Internet và thử lại.",
};

function makeOverpassError(code) {
  const error = new Error(ERROR_MESSAGES[code]);
  error.code = code;
  return error;
}

// Kiểm tra đầu vào để không bao giờ tạo query sai (vd: NaN, bán kính âm)
function assertValidInput(latitude, longitude, radius) {
  const validLatitude = Number.isFinite(latitude) && latitude >= -90 && latitude <= 90;
  const validLongitude = Number.isFinite(longitude) && longitude >= -180 && longitude <= 180;
  const validRadius = Number.isFinite(radius) && radius > 0;
  if (!validLatitude || !validLongitude || !validRadius) {
    throw new TypeError("Tọa độ hoặc bán kính không hợp lệ.");
  }
}

/**
 * Tạo câu truy vấn Overpass QL.
 * @param {number} latitude  vĩ độ của người dùng
 * @param {number} longitude kinh độ của người dùng
 * @param {number} radius    bán kính, đơn vị MÉT
 * @returns {string} nội dung query
 */
export function buildChurchQuery(latitude, longitude, radius) {
  assertValidInput(latitude, longitude, radius);

  const around = `(around:${Math.round(radius)},${latitude.toFixed(6)},${longitude.toFixed(6)})`;

  return `[out:json][timeout:${CONFIG.OVERPASS_TIMEOUT_SECONDS}];
(
  // === Nhóm 1: Thẻ chuẩn (độ chính xác cao nhất) ===
  nwr["amenity"="place_of_worship"]
     ["religion"="christian"]
     ["denomination"~"^(roman_catholic|catholic)$"]
     ${around};

  // === Nhóm 2: Thiếu thẻ denomination -> lọc theo tên ===
  nwr["amenity"="place_of_worship"]
     ["religion"!~"^(buddhist|muslim|hindu|jewish|sikh|taoist|shinto|caodaism|hoahaoism|folk)$"]
     [!"denomination"]
     ["name"~"nhà thờ|giáo xứ|công giáo|catholic|church|chapel",i]
     ${around};
);
out center tags;`;
}

// Gửi query tới MỘT endpoint. Ném lỗi nếu HTTP lỗi, hết giờ hoặc dữ liệu không hợp lệ.
async function postQuery(endpoint, query) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), (CONFIG.OVERPASS_TIMEOUT_SECONDS + 5) * 1000);

  try {
    const response = await fetch(endpoint, {
      method: "POST",
      body: new URLSearchParams({ data: query }), // Overpass nhận query trong trường "data"
      signal: controller.signal,
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`); // vd: 429 quá tải, 504 hết giờ

    const data = await response.json();
    // Overpass đôi khi trả HTTP 200 nhưng kèm "remark" báo lỗi, dữ liệu có thể thiếu
    if (data.remark && /runtime error/i.test(data.remark)) throw new Error(data.remark);
    if (!Array.isArray(data.elements)) throw new Error("Phản hồi không đúng định dạng.");
    return data.elements;
  } finally {
    clearTimeout(timeoutId);
  }
}

/**
 * Tạo query rồi gửi tới Overpass. Thử lần lượt từng endpoint trong config.
 * Trả về cả query để nút "Overpass Turbo" dùng đúng query này.
 * @returns {Promise<{query: string, elements: object[], endpoint: string}>}
 * @throws Error có code "NETWORK_ERROR" hoặc "OVERPASS_ERROR"
 */
export async function fetchChurches(latitude, longitude, radius) {
  const query = buildChurchQuery(latitude, longitude, radius);

  for (const endpoint of CONFIG.OVERPASS_ENDPOINTS) {
    try {
      const elements = await postQuery(endpoint, query);
      return { query, elements, endpoint };
    } catch (error) {
      console.warn(`Overpass lỗi tại ${endpoint}:`, error); // thử endpoint kế tiếp
    }
  }

  // Tất cả endpoint đều lỗi: KHÔNG dùng dữ liệu giả, báo lỗi thật cho người dùng.
  const isOffline = typeof navigator !== "undefined" && navigator.onLine === false;
  throw makeOverpassError(isOffline ? "NETWORK_ERROR" : "OVERPASS_ERROR");
}

// Link mở đúng query này trên Overpass Turbo (&R = tự chạy ngay)
export function buildOverpassTurboUrl(query) {
  return `${CONFIG.OVERPASS_TURBO_URL}?Q=${encodeURIComponent(query)}&R`;
}
