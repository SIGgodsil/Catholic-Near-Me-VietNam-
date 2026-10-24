// Nội dung popup của một nhà thờ. Trường nào không có trong dữ liệu thì không hiện.
import { esc, formatDistance, safeUrl, telHref } from "./format.js";

function link(href, text, external = true) {
  if (!href) return "";
  const ext = external ? ' target="_blank" rel="noopener noreferrer"' : "";
  return `<a href="${esc(href)}"${ext}>${esc(text)}</a>`;
}

function scheduleHtml(schedule) {
  if (!schedule?.length) return "";
  const rows = schedule
    .map((g) => `<dt>${esc(g.days)}</dt><dd>${g.times.map(esc).join(" · ")}</dd>`)
    .join("");
  return `<h4>Giờ lễ</h4><dl class="pp-schedule">${rows}</dl>`;
}

function contactHtml(c) {
  const items = [];
  const tel = c.phone && telHref(c.phone);
  if (tel) items.push(`<li>Điện thoại: ${link(tel, c.phone, false)}</li>`);
  if (c.email) items.push(`<li>Email: ${link(`mailto:${c.email}`, c.email, false)}</li>`);
  const web = c.website && safeUrl(c.website);
  if (web) items.push(`<li>Website: ${link(web, new URL(web).hostname)}</li>`);
  return items.length ? `<h4>Liên hệ</h4><ul>${items.join("")}</ul>` : "";
}

export function nextMassHtml(c) {
  if (!c.next_mass) return "";
  const m = c.next_mass;
  const when = m.minutes_until === 0 ? "bắt đầu ngay bây giờ" : `còn ${m.minutes_until} phút`;
  return `<p class="pp-next">Lễ lúc ${esc(m.time)}${m.day_label ? ` (${esc(m.day_label)})` : ""}, ${when}</p>`;
}

export function popupHtml(c, from) {
  const directions = from
    ? `https://www.openstreetmap.org/directions?engine=fossgis_osrm_car&route=${from.lat},${from.lon};${c.lat},${c.lon}`
    : null;
  const links = [
    link(safeUrl(c.parish_url), "Trang giáo xứ"),
    link(safeUrl(c.mass_url), "Nguồn giờ lễ"),
    link(directions, "Chỉ đường"),
  ].filter(Boolean);

  return `
    <div class="pp">
      <h3>${esc(c.name || c.parish_name)}</h3>
      ${c.parish_name ? `<p class="pp-parish">Giáo xứ ${esc(c.parish_name)}</p>` : ""}
      <p class="pp-meta">
        ${c.address ? `${esc(c.address)}<br>` : ""}
        <span class="pp-dist">Cách ${formatDistance(c.distance_km)}</span>
      </p>
      ${nextMassHtml(c)}
      ${scheduleHtml(c.schedule)}
      ${contactHtml(c)}
      ${links.length ? `<div class="pp-links">${links.join("")}</div>` : ""}
    </div>`;
}
