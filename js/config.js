// Tất cả cấu hình nằm ở đây. Muốn đổi endpoint, bản đồ nền, bán kính... chỉ cần sửa file này.

export const CONFIG = {
  // Danh sách server Overpass. Server đầu tiên được thử trước; nếu lỗi sẽ thử server kế tiếp.
  OVERPASS_ENDPOINTS: [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
  ],
  OVERPASS_TIMEOUT_SECONDS: 90, // dùng trong query: [timeout:90]
  OVERPASS_TURBO_URL: "https://overpass-turbo.eu/",

  // Bán kính tìm kiếm (km). Thêm giá trị vào đây thì <select> trong index.html cũng cần thêm tương ứng.
  RADIUS_OPTIONS_KM: [1, 3, 5, 10],
  DEFAULT_RADIUS_KM: 3,

  // Bản đồ nền CARTO Voyager: không cần API key.
  // Chỉ dùng cho dự án học tập/phi thương mại và phải giữ dòng ghi nguồn (attribution).
  MAP_TILE_URL:
    "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png",
  MAP_TILE_SUBDOMAINS: "abcd",
  MAP_ATTRIBUTION:
    '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
  MAP_MAX_ZOOM: 19,

  // Chỉ là góc nhìn ban đầu của bản đồ (toàn Việt Nam) trước khi có GPS.
  MAP_INITIAL_VIEW: { latitude: 16.0, longitude: 106.0, zoom: 5 },

  // Tùy chọn cho navigator.geolocation
  GEOLOCATION_OPTIONS: { enableHighAccuracy: true, timeout: 15000, maximumAge: 60000 },

  // Chờ người dùng ngừng gõ bao lâu (ms) rồi mới lọc danh sách
  SEARCH_DEBOUNCE_MS: 250,

  // Bước lọc bằng JavaScript sau Overpass: bỏ những tên rất có thể không phải nhà thờ Công giáo
  EXCLUDED_NAME_PATTERNS: ["tin lành", "nhà thờ họ", "từ đường", "cao đài", "baptist", "protestant"],
};
