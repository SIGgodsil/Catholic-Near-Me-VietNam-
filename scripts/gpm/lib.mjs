// Hàm thuần (không đụng trình duyệt) cho gmaps_coords.mjs — tách ra để test được.

/** Đọc CSV theo RFC 4180 (ô có ngoặc kép, dấu phẩy và xuống dòng trong ô). Bỏ BOM nếu có. */
export function parseCsv(text) {
  if (text.charCodeAt(0) === 0xfeff) text = text.slice(1);
  const rows = [];
  let row = [];
  let field = "";
  let inQuotes = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (inQuotes) {
      if (c === '"') {
        if (text[i + 1] === '"') { field += '"'; i++; } else inQuotes = false;
      } else field += c;
    } else if (c === '"') inQuotes = true;
    else if (c === ",") { row.push(field); field = ""; }
    else if (c === "\n" || c === "\r") {
      if (c === "\r" && text[i + 1] === "\n") i++;
      row.push(field); rows.push(row); row = []; field = "";
    } else field += c;
  }
  if (field !== "" || row.length) { row.push(field); rows.push(row); }
  const [header, ...body] = rows;
  return { header, records: body.filter((r) => r.length > 1 || r[0] !== "").map((r) => Object.fromEntries(header.map((h, j) => [h, r[j] ?? ""]))) };
}

export function toCsv(header, records) {
  const esc = (v) => {
    const s = v == null ? "" : String(v);
    return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  return "﻿" + [header.map(esc).join(","), ...records.map((r) => header.map((h) => esc(r[h])).join(","))].join("\r\n") + "\r\n";
}

const COORD_RE = /^\s*(-?\d{1,2}\.\d+)\s*,\s*(-?\d{1,3}\.\d+)\s*$/;

/** "10.7512, 106.6634" -> {lat, lng}; không khớp -> null. Dòng đầu menu chuột phải của Google Maps có dạng này. */
export function parseCoordText(s) {
  const m = COORD_RE.exec(s ?? "");
  return m ? { lat: Number(m[1]), lng: Number(m[2]) } : null;
}

/** Tọa độ marker của địa điểm trong URL /maps/place/...!3d<lat>!4d<lng> (lấy cặp cuối cùng). */
export function parsePinFromUrl(url) {
  const all = [...(url ?? "").matchAll(/!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)/g)];
  if (!all.length) return null;
  const m = all[all.length - 1];
  return { lat: Number(m[1]), lng: Number(m[2]) };
}

/** Tâm camera trong URL: /@lat,lng,17z (hoặc 17.5z). Chế độ vệ tinh dạng "1234m" thì zoom = null. */
export function parseCameraFromUrl(url) {
  const m = /@(-?\d+\.\d+),(-?\d+\.\d+),(\d+(?:\.\d+)?)(z|m)/.exec(url ?? "");
  if (!m) return null;
  return { lat: Number(m[1]), lng: Number(m[2]), zoom: m[4] === "z" ? Number(m[3]) : null };
}

/** Vị trí pixel (CSS px) của điểm `pt` so với tâm camera, theo phép chiếu Web Mercator ô 256px. */
export function pixelOffset(center, pt, zoom) {
  const ws = 256 * 2 ** zoom;
  const proj = ({ lat, lng }) => {
    const s = Math.sin((lat * Math.PI) / 180);
    return { x: ((lng + 180) / 360) * ws, y: (0.5 - Math.log((1 + s) / (1 - s)) / (4 * Math.PI)) * ws };
  };
  const a = proj(center);
  const b = proj(pt);
  return { dx: b.x - a.x, dy: b.y - a.y };
}

// ---------- So khớp tên / địa chỉ ----------

/** Bỏ dấu, chữ thường, chỉ giữ chữ-số và khoảng trắng. "Đ" -> "d". */
export function norm(s) {
  return (s ?? "")
    .normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[đĐ]/g, "d")
    .toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
}

const tokens = (s) => norm(s).split(" ").filter(Boolean);

/** Tỉ lệ token của `needle` có mặt trong `hay`. */
export function tokenCover(needle, hay) {
  const n = tokens(needle);
  if (!n.length) return 0;
  const h = new Set(tokens(hay));
  return n.filter((t) => h.has(t)).length / n.length;
}

const NAME_PREFIX = /^(nha tho|giao xu|giao ho|gx)\s+/;

/** "Nhà thờ Giáo họ Giuse - Vĩnh Lộc B" -> "giuse vinh loc b" */
export function coreName(s) {
  let n = norm(s);
  for (let t; (t = n.replace(NAME_PREFIX, "")) !== n; ) n = t;
  return n;
}

/** Tên Google có chứa đủ tên lõi của nhà thờ không (cho phép thiếu 1/4 token với tên dài). */
export function nameMatches(displayName, googleName) {
  // "Thánh" hay bị Google bỏ ("Thánh Martinô" -> "Martino de Porres") nên không bắt buộc.
  const core = coreName(displayName).split(" ").filter((t) => t !== "thanh").join(" ") || coreName(displayName);
  if (!core) return false;
  // Viết liền / tách khác nhau: "Antôn" vs "An Tôn".
  const joined = core.replace(/ /g, "");
  const g = tokens(googleName);
  for (let i = 0; i < g.length; i++) {
    let w = "";
    for (let j = i; j < g.length && w.length < joined.length; j++) w += g[j];
    if (w === joined) return true;
  }
  const n = core.split(" ").length;
  return tokenCover(core, googleName) >= (n >= 4 ? 0.75 : 1);
}

const WARD_RE = /^(?:p\.|phường|phuong|xã|xa)\s*(.+)$/i;
const DISTRICT_RE = /^(?:q\.|quận|quan|h\.|huyện|huyen)\s*(.+)$/i;

/**
 * Tách địa chỉ dataset thành các phần dùng để tìm và để đối chiếu.
 * "3131 Phạm Thế Hiển, phường Bình Đông, TP. Hồ Chí Minh (3131 Phạm Thế Hiển, P.7, Q.8)"
 *   -> { streetPart: "3131 Phạm Thế Hiển", street: "Phạm Thế Hiển", ward: "Bình Đông", district: "Quận 8" }
 */
export function parseAddress(addr) {
  const s = (addr ?? "").trim();
  const i = s.search(/\((?!\s*số cũ)/i); // "(số cũ 3A62)" là một phần số nhà, không phải địa chỉ cũ
  const main = (i >= 0 ? s.slice(0, i) : s).trim();
  const old = (i >= 0 ? s.slice(i + 1).replace(/\)\s*$/, "") : "").replace(/^Địa chỉ cũ:\s*/i, "");
  const seg = (x) => x.split(/[,;]/).map((t) => t.trim().replace(/\.$/, "")).filter(Boolean);
  const mainSeg = seg(main);

  // Phần số nhà + đường: nếu đoạn đầu chỉ là "Số 62" thì ghép thêm đoạn sau.
  let streetPart = mainSeg[0] ?? "";
  if (mainSeg[1] && norm(streetPart.replace(/\d+/g, "")).replace(/\bso\b/, "").trim().length < 3) streetPart += ", " + mainSeg[1];
  const street = streetPart
    .replace(/\(số cũ[^)]*\)/gi, " ")
    .replace(/^(?:số\s*)?[0-9A-Za-z/\-.]*\d[0-9A-Za-z/\-.]*[,\s]+/i, "")
    .replace(/^đường\s+/i, "")
    .trim();

  const ward = mainSeg.map((t) => WARD_RE.exec(t)?.[1]).find(Boolean) ?? "";
  // Quận/huyện cũ: "Q.8", "Q. Tân Bình", "Quận 12", "Huyện Cần Giờ", "Q12"
  let district = "";
  for (const t of seg(old).flatMap((x) => x.split(/\.\s+(?=Q)/))) {
    const m = DISTRICT_RE.exec(t) ?? /^Q\s*(\d+)$/i.exec(t);
    if (m) {
      const d = m[1].replace(/\.\s.*$/, "").trim(); // "Bình Chánh. TP.HCM" -> "Bình Chánh"
      district = /^\d+$/.test(d) ? `Quận ${d}` : d;
    }
  }
  return { streetPart, street, ward, district };
}

/** Địa chỉ Google có khớp nơi trong dataset không: tên đường (≥ 2/3 token) hoặc phường mới hoặc quận cũ. */
export function locationMatches(parts, googleAddr) {
  const g = ` ${norm(googleAddr)} `;
  if (parts.street && tokenCover(parts.street, googleAddr) >= 0.66 && tokens(parts.street).length >= 2) return "duong";
  if (parts.ward && g.includes(` ${norm(parts.ward)} `)) return "phuong";
  if (parts.district && g.includes(` ${norm(parts.district)} `)) return "quan";
  return "";
}

export function haversineM(a, b) {
  const R = 6371000;
  const rad = (d) => (d * Math.PI) / 180;
  const dLat = rad(b.lat - a.lat);
  const dLng = rad(b.lng - a.lng);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(rad(a.lat)) * Math.cos(rad(b.lat)) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}
