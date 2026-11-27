// Lấy latitude/longitude cho từng nhà thờ trong data/interim/tgpsg_missing_coords.csv bằng Google Maps,
// điều khiển một trình duyệt Chrome (hoặc profile GPM Login) qua cổng debug.
//
// Với mỗi nhà thờ (mỗi church_id), lần lượt thử:
//   1. "<display_name>, <số nhà + đường>"   2. "<display_name>, <quận/phường>"   3. "<display_name>"
// Nhiều kết quả -> chọn kết quả có tên và địa chỉ khớp dataset. Chỉ nhận khi tên Google khớp tên nhà thờ
// VÀ địa chỉ Google khớp đường / phường / quận trong dataset. Không khớp -> để trống lat/lng, ghi chú để kiểm tra tay.
// Khi đã chọn được: kéo marker ra vùng bản đồ nhìn thấy, chuột phải vào marker, đọc tọa độ ở dòng đầu menu
// (lệch thì tự bù rồi chuột phải lại, tối đa 3 lần).
//
// Cài một lần (trong thư mục scripts/gpm):   npm install
// Chạy (từ thư mục gốc dự án):
//   node scripts/gpm/gmaps_coords.mjs --cdp http://127.0.0.1:9222 --limit 3   # chạy thử 3 nhà thờ
//   node scripts/gpm/gmaps_coords.mjs --cdp http://127.0.0.1:9222             # chạy hết, chạy lại sẽ bỏ qua cái đã xong
//   node scripts/gpm/gmaps_coords.mjs --cdp http://127.0.0.1:9222 --only "Bình Thuận"  # chỉ chạy tên/church_id chứa chuỗi này
//   node scripts/gpm/gmaps_coords.mjs --profile <GPM_PROFILE_ID>             # mở profile GPM Login qua API cục bộ
//   node scripts/gpm/gmaps_coords.mjs --write-only                           # chỉ ghi lại CSV từ cache
//
// Kết quả từng nhà thờ được lưu ngay vào data/interim/gmaps_coords_cache.json (dừng giữa chừng không mất).
// Cuối cùng ghi latitude, longitude + các cột gmaps_* vào chính file CSV (có bản sao .bak trước lần ghi đầu).
// Lưu ý: điều khoản Google Maps không cho phép thu thập dữ liệu tự động; dùng ít, chậm, và tự chịu trách nhiệm.

import { copyFileSync, existsSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";
import {
  haversineM, locationMatches, nameMatches, norm, parseAddress, parseCameraFromUrl, parseCoordText, parseCsv,
  parsePinFromUrl, pixelOffset, toCsv,
} from "./lib.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const { values: args } = parseArgs({
  options: {
    csv: { type: "string", default: path.join(ROOT, "data", "interim", "tgpsg_missing_coords.csv") },
    cache: { type: "string", default: path.join(ROOT, "data", "interim", "gmaps_coords_cache.json") },
    profile: { type: "string" },
    "gpm-api": { type: "string", default: "http://127.0.0.1:19995" },
    cdp: { type: "string" },
    limit: { type: "string" },
    only: { type: "string" },
    retry: { type: "boolean", default: false }, // chạy lại cả những nhà thờ trước đó chưa khớp / lỗi
    "write-only": { type: "boolean", default: false },
    "min-delay": { type: "string", default: "4" },
    "max-delay": { type: "string", default: "9" },
  },
});

const MAX_RIGHTCLICK_DRIFT_M = 30; // chuột phải vẫn lệch marker quá mức này thì dùng tọa độ marker trong URL
const GOOD_DRIFT_M = 5;
const NEW_COLS = [
  "gmaps_status", "gmaps_match", "gmaps_query", "gmaps_place_name", "gmaps_place_address",
  "gmaps_rightclick", "gmaps_pin", "gmaps_drift_m", "gmaps_note",
];
const MATCH_RANK = { khop: 3, chi_ten: 2, chi_dia_chi: 1, khong_khop: 0 };

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const between = (lo, hi) => (lo + Math.random() * (hi - lo)) * 1000;
const jitter = () => between(Number(args["min-delay"]), Number(args["max-delay"]));

function loadCache() {
  if (!existsSync(args.cache)) return {};
  const raw = JSON.parse(readFileSync(args.cache, "utf8"));
  // Bản cũ lưu theo display_name; bản này lưu theo church_id ("tgpsg:...") nên bỏ các khóa cũ.
  return Object.fromEntries(Object.entries(raw).filter(([k]) => k.includes(":")));
}
function saveCache(cache) {
  writeFileSync(args.cache, JSON.stringify(cache, null, 2), "utf8");
}

// ---------- GPM Login ----------

async function openGpmProfile(profileId) {
  const url = `${args["gpm-api"]}/api/v3/profiles/start/${encodeURIComponent(profileId)}`;
  const res = await fetch(url);
  const body = await res.json().catch(() => ({}));
  const addr = body?.data?.remote_debugging_address;
  if (!res.ok || !addr) throw new Error(`GPM không mở được profile (${url}): ${JSON.stringify(body)}`);
  return addr.startsWith("http") ? addr : `http://${addr}`;
}

// ---------- Google Maps ----------

class StopError extends Error {} // lỗi phải dừng cả lượt (captcha, trang đồng ý cookie...)

async function waitFor(fn, timeoutMs, stepMs = 300) {
  const end = Date.now() + timeoutMs;
  while (Date.now() < end) {
    const v = await fn();
    if (v) return v;
    await sleep(stepMs);
  }
  return null;
}

function guardBlocked(url) {
  if (url.includes("consent.google.")) throw new StopError("Google đang hỏi đồng ý cookie. Hãy tự bấm chọn trong cửa sổ trình duyệt rồi chạy lại.");
  if (url.includes("/sorry/")) throw new StopError("Google chặn tạm thời (captcha). Dừng lại, đợi một lúc rồi chạy lại.");
}

/** Chờ URL camera @lat,lng,zoom đứng yên (map đã bay / kéo xong). */
async function waitCameraStable(page) {
  let last = "";
  let stableSince = 0;
  await waitFor(async () => {
    const cam = /@[^/]+/.exec(page.url())?.[0] ?? "";
    if (cam !== last) { last = cam; stableSince = Date.now(); return false; }
    return Date.now() - stableSince > 1200;
  }, 10000, 200);
}

async function placeInfo(page) {
  await waitCameraStable(page);
  // Bảng thông tin có thể tải sau camera: chờ có tên địa điểm.
  await waitFor(() => page.evaluate(() => (document.querySelector("h1")?.innerText ?? "").trim().length > 0), 8000);
  await sleep(500);
  const { name, address } = await page.evaluate(() => ({
    name: document.querySelector("h1")?.innerText?.trim() ?? "",
    address: (document.querySelector('button[data-item-id="address"]')?.getAttribute("aria-label") ?? "").replace(/^[^:]*:\s*/, "").trim(),
  }));
  return { url: page.url(), pin: parsePinFromUrl(page.url()), name, address };
}

function judge(church, place) {
  const nameOk = nameMatches(church.display_name, place.name);
  const loc = locationMatches(church.parts, place.address);
  const match = nameOk && loc ? "khop" : nameOk ? "chi_ten" : loc ? "chi_dia_chi" : "khong_khop";
  return { ...place, match, loc };
}

/** Một lần tìm. Trả về địa điểm tốt nhất của lần tìm này, hoặc {missing: "not_found"|"timeout"}. */
async function runQuery(page, church, query) {
  await page.goto(`https://www.google.com/maps/search/${encodeURIComponent(query)}?hl=vi`, { waitUntil: "domcontentloaded", timeout: 45000 });
  guardBlocked(page.url());

  const state = await waitFor(async () => {
    guardBlocked(page.url());
    if (parsePinFromUrl(page.url())) return "place";
    return page.evaluate(() => {
      if (document.querySelector('div[role="feed"] a[href*="/maps/place/"]')) return "list";
      if (/không tìm thấy|can't find|did not match/i.test(document.body.innerText)) return "none";
      return null;
    });
  }, 20000);
  if (!state || state === "none") return { missing: state ? "not_found" : "timeout" };

  if (state === "list") {
    await sleep(1000); // để danh sách tải đủ vài kết quả đầu
    const cards = await page.evaluate(() =>
      [...document.querySelectorAll('div[role="feed"] a[href*="/maps/place/"]')].slice(0, 10).map((a) => ({
        href: a.href,
        name: a.getAttribute("aria-label") ?? "",
        text: (a.closest('div[role="article"]') ?? a.parentElement)?.innerText ?? "",
      })),
    );
    const scored = cards.map((c, i) => {
      const nameOk = nameMatches(church.display_name, c.name);
      const loc = locationMatches(church.parts, c.text);
      return { ...c, i, score: (nameOk ? 1 : 0) + (loc ? 2 : 0) };
    });
    scored.sort((a, b) => b.score - a.score || a.i - b.i);
    await page.goto(scored[0].href, { waitUntil: "domcontentloaded", timeout: 45000 });
    guardBlocked(page.url());
    if (!(await waitFor(() => parsePinFromUrl(page.url()), 15000))) return { missing: "timeout" };
    const place = judge(church, await placeInfo(page));
    place.note = `chon_ket_qua_${scored[0].i + 1}_trong_${cards.length}`;
    return place;
  }
  return judge(church, await placeInfo(page));
}

async function mapGeometry(page) {
  return page.evaluate(() => {
    const cs = [...document.querySelectorAll("canvas")].map((c) => c.getBoundingClientRect()).sort((a, b) => b.width * b.height - a.width * a.height);
    const r = cs[0];
    const panelRight = Math.max(0, ...[...document.querySelectorAll('div[role="main"]')].map((e) => e.getBoundingClientRect().right));
    return r ? { x: r.x, y: r.y, w: r.width, h: r.height, panelRight } : null;
  });
}

/** Chuột phải tại (x, y), đọc dòng tọa độ trong menu rồi đóng menu. */
async function rightClickRead(page, x, y) {
  await page.mouse.move(x, y);
  await sleep(200);
  await page.mouse.click(x, y, { button: "right" });
  const text = await waitFor(
    () => page.evaluate(() => {
      for (const el of document.querySelectorAll('[role="menu"] [role^="menuitem"]')) {
        const t = el.innerText.trim();
        if (/^-?\d{1,2}\.\d+,\s*-?\d{1,3}\.\d+$/.test(t)) return t;
      }
      return null;
    }),
    3000,
    150,
  );
  await page.keyboard.press("Escape");
  await sleep(200);
  return parseCoordText(text);
}

/** Đưa marker vào vùng bản đồ nhìn thấy rồi chuột phải vào nó. Trả về {coord, drift} tốt nhất hoặc null. */
async function rightClickMarker(page, pin) {
  let g = await mapGeometry(page);
  let cam = parseCameraFromUrl(page.url());
  if (!g || cam?.zoom == null) return null;
  const targetFrom = (c) => {
    const { dx, dy } = pixelOffset(c, pin, c.zoom);
    return { x: g.x + g.w / 2 + dx, y: g.y + g.h / 2 + dy };
  };
  let t = targetFrom(cam);

  // Vùng nhìn thấy: bên phải bảng thông tin, chừa thanh nút phía trên và ảnh/nút zoom phía dưới.
  const vis = { l: g.panelRight + 40, r: g.x + g.w - 90, t: g.y + 100, b: g.y + g.h - 160 };
  if (vis.r - vis.l < 80 || vis.b - vis.t < 80) return null;
  if (t.x < vis.l || t.x > vis.r || t.y < vis.t || t.y > vis.b) {
    const cx = (vis.l + vis.r) / 2;
    const cy = (vis.t + vis.b) / 2;
    const d = { x: cx - t.x, y: cy - t.y };
    const s = { x: cx - d.x / 2, y: cy - d.y / 2 }; // kéo đối xứng quanh tâm vùng nhìn thấy
    await page.mouse.move(s.x, s.y);
    await page.mouse.down();
    for (let k = 1; k <= 12; k++) { await page.mouse.move(s.x + (d.x * k) / 12, s.y + (d.y * k) / 12); await sleep(25); }
    await page.mouse.up();
    await waitCameraStable(page);
    const cam2 = parseCameraFromUrl(page.url());
    g = (await mapGeometry(page)) ?? g;
    if (cam2?.zoom != null && (cam2.lat !== cam.lat || cam2.lng !== cam.lng)) { cam = cam2; t = targetFrom(cam); }
    else t = { x: t.x + d.x, y: t.y + d.y };
  }

  let best = null;
  for (let attempt = 0; attempt < 3; attempt++) {
    const coord = await rightClickRead(page, t.x, t.y);
    if (!coord) break;
    const drift = haversineM(coord, pin);
    if (!best || drift < best.drift) best = { coord, drift };
    if (drift <= GOOD_DRIFT_M) break;
    // Bù: điểm vừa bấm lệch so với marker bao nhiêu pixel thì dời bấy nhiêu.
    const off = pixelOffset(coord, pin, cam.zoom);
    t = { x: t.x + off.dx, y: t.y + off.dy };
  }
  return best;
}

function queriesFor(church) {
  const { streetPart, street, district, ward } = church.parts;
  const name = church.display_name;
  const qs = [];
  if (street && norm(street).length >= 3) qs.push(`${name}, ${streetPart}`);
  if (district || ward) qs.push(`${name}, ${district || ward}`);
  qs.push(name);
  return [...new Set(qs)];
}

async function geocodeChurch(page, church) {
  let best = null;
  let missing = "not_found";
  const tried = [];
  for (const [qi, query] of queriesFor(church).entries()) {
    if (qi) await sleep(between(2, 4));
    tried.push(query);
    const r = await runQuery(page, church, query);
    if (r.missing) { if (r.missing === "timeout") missing = "timeout"; continue; }
    r.query = query;
    if (!best || MATCH_RANK[r.match] > MATCH_RANK[best.match]) best = r;
    if (r.match === "khop") break;
  }
  if (!best) return { gmaps_status: missing, gmaps_match: "", gmaps_query: tried.join(" | ") };

  const out = {
    gmaps_match: best.match,
    gmaps_query: best.query,
    gmaps_place_name: best.name,
    gmaps_place_address: best.address,
    gmaps_pin: `${best.pin.lat}, ${best.pin.lng}`,
    gmaps_rightclick: "",
    gmaps_drift_m: "",
    gmaps_note: best.note ?? "",
  };
  if (best.match !== "khop") return { ...out, gmaps_status: "can_kiem_tra" }; // không điền lat/lng khi chưa chắc

  if (page.url() !== best.url) {
    await page.goto(best.url, { waitUntil: "domcontentloaded", timeout: 45000 });
    await waitFor(() => parsePinFromUrl(page.url()), 15000);
    await waitCameraStable(page);
  }
  const rc = await rightClickMarker(page, best.pin);
  const addNote = (n) => [out.gmaps_note, n].filter(Boolean).join(";");
  if (rc) {
    out.gmaps_rightclick = `${rc.coord.lat}, ${rc.coord.lng}`;
    out.gmaps_drift_m = rc.drift.toFixed(1);
    if (rc.drift <= MAX_RIGHTCLICK_DRIFT_M) return { ...out, gmaps_status: "ok", lat: rc.coord.lat, lng: rc.coord.lng };
    out.gmaps_note = addNote("chuot_phai_lech_dung_toa_do_marker");
  } else {
    out.gmaps_note = addNote("khong_doc_duoc_menu_chuot_phai_dung_toa_do_marker");
  }
  return { ...out, gmaps_status: "ok_pin", lat: best.pin.lat, lng: best.pin.lng };
}

// ---------- Ghi CSV ----------

function writeCsv(header, records, cache) {
  const fullHeader = [...header, ...NEW_COLS.filter((c) => !header.includes(c))];
  for (const r of records) {
    const hit = cache[r.church_id];
    if (!hit) continue;
    for (const c of NEW_COLS) r[c] = hit[c] ?? "";
    r.latitude = hit.lat != null ? String(hit.lat) : "";
    r.longitude = hit.lng != null ? String(hit.lng) : "";
  }
  const text = toCsv(fullHeader, records);
  const bak = args.csv + ".bak";
  try {
    if (!existsSync(bak)) copyFileSync(args.csv, bak);
    writeFileSync(args.csv, text, "utf8");
    console.log(`Đã ghi ${args.csv}`);
  } catch (e) {
    const alt = args.csv.replace(/\.csv$/i, "_gmaps.csv");
    writeFileSync(alt, text, "utf8");
    console.warn(`Không ghi đè được ${args.csv} (${e.code}; file đang mở trong Excel?). Đã ghi sang ${alt}`);
  }
}

// ---------- main ----------

async function main() {
  const { header, records } = parseCsv(readFileSync(args.csv, "utf8"));

  const churches = new Map(); // church_id -> {church_id, display_name, address, parts}
  for (const r of records) {
    if (r.church_id && !churches.has(r.church_id)) {
      churches.set(r.church_id, { church_id: r.church_id, display_name: r.display_name, parts: parseAddress(r.tgpsg_parish_address) });
    }
  }

  const cache = loadCache();
  if (args["write-only"]) return writeCsv(header, records, cache);

  const done = (id) => cache[id] && (!args.retry || ["ok", "ok_pin"].includes(cache[id].gmaps_status));
  let todo = [...churches.values()].filter((c) => !done(c.church_id));
  if (args.only) {
    const o = norm(args.only);
    todo = todo.filter((c) => norm(c.display_name).includes(o) || norm(c.church_id).includes(o));
  }
  if (args.limit) todo = todo.slice(0, Number(args.limit));
  console.log(`${churches.size} nhà thờ, cần chạy: ${todo.length}`);
  if (!todo.length) return writeCsv(header, records, cache);

  if (!args.cdp && !args.profile) throw new Error("Cần --cdp <http://127.0.0.1:port> hoặc --profile <GPM_PROFILE_ID>");
  const browserURL = args.cdp ?? (await openGpmProfile(args.profile));
  const { default: puppeteer } = await import("puppeteer-core");
  const browser = await puppeteer.connect({ browserURL, defaultViewport: null });
  const page = await browser.newPage();

  let stopped = false;
  process.on("SIGINT", () => { stopped = true; console.log("\nDừng sau nhà thờ hiện tại..."); });

  try {
    for (const [i, church] of todo.entries()) {
      if (stopped) break;
      let res;
      try {
        res = await geocodeChurch(page, church);
      } catch (e) {
        if (e instanceof StopError) { console.error(e.message); break; }
        res = { gmaps_status: "error", gmaps_note: String(e.message).slice(0, 200) };
      }
      cache[church.church_id] = { display_name: church.display_name, ...res, at: new Date().toISOString() };
      saveCache(cache);
      const where = res.lat != null ? `${res.lat}, ${res.lng}` : "-";
      console.log(`[${i + 1}/${todo.length}] ${res.gmaps_status.padEnd(12)} ${church.display_name} -> ${where} | ${res.gmaps_place_name ?? ""} | ${res.gmaps_place_address ?? ""} ${res.gmaps_note ? "| " + res.gmaps_note : ""}`);
      if (i < todo.length - 1) await sleep(jitter());
    }
  } finally {
    await page.close().catch(() => {});
    browser.disconnect();
  }
  writeCsv(header, records, cache);
}

main().catch((e) => { console.error(e.message ?? e); process.exit(1); });
