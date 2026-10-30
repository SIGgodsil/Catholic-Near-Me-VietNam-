// Hàm định dạng và an toàn HTML dùng chung.

const HTML_ESCAPES = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };

export function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => HTML_ESCAPES[ch]);
}

// 0.758 -> "760 m", 1.32 -> "1,3 km"
export function formatDistance(km) {
  if (km < 1) return `${Math.max(10, Math.round((km * 1000) / 10) * 10)} m`;
  return `${km.toLocaleString("vi-VN", { maximumFractionDigits: 1 })} km`;
}

// Chỉ nhận link http(s) để dữ liệu không thể chèn "javascript:".
export function safeUrl(url) {
  try {
    const u = new URL(url);
    return u.protocol === "http:" || u.protocol === "https:" ? u.href : null;
  } catch {
    return null;
  }
}

export function telHref(phone) {
  const digits = String(phone).replace(/[^\d+]/g, "");
  return digits.length >= 6 ? `tel:${digits}` : null;
}
