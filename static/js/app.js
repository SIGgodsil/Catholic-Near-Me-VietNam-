// Điều phối trang: định vị, tìm địa chỉ, gọi API và hiển thị kết quả.
import { fetchHealth, fetchNearby, geocode } from "./api.js";
import { esc, formatDistance } from "./format.js";
import { createMap } from "./map.js";
import { nextMassText } from "./popup.js";
import { state } from "./state.js";

const RADIUS_KM = 3;
const POOR_ACCURACY_M = 500; // sai số GPS lớn hơn mức này thì gợi ý nhập địa chỉ
const GEO_OPTIONS = { enableHighAccuracy: true, timeout: 15000, maximumAge: 60000 };
const REFRESH_MS = 60_000; // cập nhật "còn X phút" và ghim lễ sắp diễn ra

const els = {
  locateBtn: document.getElementById("locate-btn"),
  form: document.getElementById("search-form"),
  input: document.getElementById("search-input"),
  results: document.getElementById("search-results"),
  status: document.getElementById("status"),
  list: document.getElementById("church-list"),
};

const map = createMap(document.getElementById("map"), { onChurchSelect: highlightListItem });


// ---------- Trạng thái ----------

function setStatus(kind, title, ...notes) {
  els.status.className = `status${kind ? ` is-${kind}` : ""}`;
  els.status.innerHTML =
    `<p class="status-title">${esc(title)}</p>` + notes.filter(Boolean).map((n) => `<p class="note">${esc(n)}</p>`).join("");
}

async function showIntro() {
  const intro = ["", "Tìm nhà thờ trong bán kính 3 km", "Bấm “Tìm nhà thờ gần tôi” để dùng vị trí hiện tại, hoặc nhập địa chỉ vào ô tìm kiếm."];
  setStatus(...intro);
  try {
    const health = await fetchHealth();
    if (!state.location) setStatus(...intro, health.scope_note);
  } catch (err) {
    setStatus("error", "Không kết nối được máy chủ.", "Kiểm tra server còn chạy không rồi tải lại trang.");
  }
}

// ---------- Danh sách kết quả ----------

function renderList(churches) {
  els.list.innerHTML = churches
    .map(
      (c) => `
      <li>
        <button class="church-item" type="button" data-id="${c.id}">
          <span class="ci-name">${esc(c.name)}</span>
          <span class="ci-dist">${formatDistance(c.distance_km)}</span>
          ${c.address ? `<span class="ci-addr">${esc(c.address)}</span>` : ""}
          ${c.next_mass ? `<span class="ci-next">${esc(nextMassText(c.next_mass))}</span>` : ""}
        </button>
      </li>`,
    )
    .join("");
}

function highlightListItem(id) {
  for (const btn of els.list.querySelectorAll(".church-item")) {
    btn.classList.toggle("is-active", Number(btn.dataset.id) === id);
  }
}

els.list.addEventListener("click", (e) => {
  const btn = e.target.closest(".church-item");
  if (btn) map.openChurch(Number(btn.dataset.id));
});

// ---------- Tìm quanh một vị trí ----------

let refreshTimer = null;

function upcomingNote(churches) {
  const n = churches.filter((c) => c.next_mass).length;
  return n ? `${n} nhà thờ có lễ trong 2 giờ tới (ghim đỏ).` : "Không có nhà thờ nào có lễ trong 2 giờ tới.";
}

// Lấy lại dữ liệu im lặng, không đổi khung nhìn, giữ popup đang mở.
async function refresh() {
  if (!state.location || document.hidden) return;
  try {
    const data = await fetchNearby(state.location.lat, state.location.lon, RADIUS_KM);
    map.showChurches(data.churches, { keepOpen: true });
    renderList(data.churches);
    const note = els.status.querySelector(".upcoming-note");
    if (note) note.textContent = upcomingNote(data.churches);
  } catch {
    // Lần sau thử lại; không làm phiền người dùng vì dữ liệu cũ vẫn đang hiển thị.
  }
}

async function searchAround(lat, lon, { label, accuracyM, warning } = {}) {
  clearInterval(refreshTimer);
  state.location = { lat, lon, label };
  map.showUser(lat, lon, { radiusKm: RADIUS_KM, accuracyM, label });
  map.showChurches([]);
  els.list.innerHTML = "";
  setStatus("loading", "Đang tìm nhà thờ…");
  try {
    const data = await fetchNearby(lat, lon, RADIUS_KM);
    map.showChurches(data.churches);
    renderList(data.churches);
    const where = label ? `quanh ${label}` : "quanh vị trí của bạn";
    if (data.count === 0) {
      setStatus(
        "warn",
        `Không có nhà thờ nào trong bán kính ${RADIUS_KM} km.`,
        `Không tìm thấy nhà thờ ${where}.`,
        `${data.scope_note} Bạn thử nhập một địa chỉ khác ở TP.HCM.`,
        warning,
      );
    } else {
      setStatus(warning ? "warn" : "", `Có ${data.count} nhà thờ trong bán kính ${RADIUS_KM} km`, `Tìm ${where}. Bấm vào ghim hoặc tên nhà thờ để xem giờ lễ.`, warning);
      const note = document.createElement("p");
      note.className = "note upcoming-note";
      note.textContent = upcomingNote(data.churches);
      els.status.append(note);
      refreshTimer = setInterval(refresh, REFRESH_MS);
    }
  } catch (err) {
    setStatus("error", "Không tải được danh sách nhà thờ.", err.message);
  }
}

// ---------- Định vị bằng trình duyệt (chỉ khi người dùng bấm nút) ----------

const GEO_ERRORS = {
  1: "Bạn đã từ chối quyền truy cập vị trí. Hãy nhập địa chỉ vào ô tìm kiếm, hoặc cho phép lại quyền vị trí trong cài đặt trình duyệt.",
  2: "Không xác định được vị trí của bạn. Hãy nhập địa chỉ vào ô tìm kiếm.",
  3: "Lấy vị trí quá lâu. Hãy thử lại hoặc nhập địa chỉ vào ô tìm kiếm.",
};

function locate() {
  if (!("geolocation" in navigator) || !window.isSecureContext) {
    setStatus("error", "Trình duyệt không hỗ trợ định vị trên trang này.", "Hãy nhập địa chỉ vào ô tìm kiếm.");
    els.input.focus();
    return;
  }
  els.locateBtn.disabled = true;
  setStatus("loading", "Đang lấy vị trí của bạn…", "Trình duyệt có thể hỏi bạn cho phép truy cập vị trí.");
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      els.locateBtn.disabled = false;
      const { latitude, longitude, accuracy } = pos.coords;
      const warning =
        accuracy > POOR_ACCURACY_M
          ? `Vị trí có thể lệch khoảng ${formatDistance(accuracy / 1000)}. Nếu không đúng, hãy nhập địa chỉ vào ô tìm kiếm.`
          : null;
      searchAround(latitude, longitude, { accuracyM: accuracy, warning });
    },
    (err) => {
      els.locateBtn.disabled = false;
      setStatus("error", "Chưa lấy được vị trí", GEO_ERRORS[err.code] || GEO_ERRORS[2]);
      els.input.focus();
    },
    GEO_OPTIONS,
  );
}

els.locateBtn.addEventListener("click", locate);

// ---------- Tìm theo địa chỉ (Nominatim qua backend, chỉ khi bấm Tìm) ----------

function hideResults() {
  els.results.hidden = true;
  els.results.innerHTML = "";
}

function chooseResult(r) {
  hideResults();
  const shortLabel = r.label.split(",").slice(0, 3).join(",");
  els.input.value = shortLabel;
  searchAround(r.lat, r.lon, { label: shortLabel });
}

els.form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const q = els.input.value.trim();
  hideResults();
  if (q.length < 3) {
    setStatus("warn", "Địa chỉ quá ngắn", "Hãy nhập ít nhất 3 ký tự, ví dụ “Nhà thờ Tân Định” hoặc “Quận 3”.");
    return;
  }
  const submit = els.form.querySelector("button[type=submit]");
  submit.disabled = true;
  setStatus("loading", "Đang tìm địa chỉ…");
  try {
    const results = await geocode(q);
    if (results.length === 0) {
      setStatus(
        "warn",
        "Không tìm thấy địa chỉ này ở Việt Nam.",
        "Hãy thử tên địa danh (chợ, trường, nhà thờ) hoặc tên đường kèm phường theo địa giới mới, ví dụ “Hai Bà Trưng, Phường Xuân Hòa”. Tên quận cũ có thể không được nhận ra.",
      );
    } else if (results.length === 1) {
      chooseResult(results[0]);
    } else {
      setStatus("", "Có nhiều địa điểm trùng tên", "Hãy chọn địa điểm đúng trong danh sách bên dưới ô tìm kiếm.");
      els.results.innerHTML = results.map((r, i) => `<li><button type="button" data-i="${i}">${esc(r.label)}</button></li>`).join("");
      els.results.hidden = false;
      els.results.onclick = (ev) => {
        const btn = ev.target.closest("button");
        if (btn) chooseResult(results[Number(btn.dataset.i)]);
      };
      els.results.querySelector("button").focus();
    }
  } catch (err) {
    setStatus("error", "Không tìm được địa chỉ", err.message);
  } finally {
    submit.disabled = false;
  }
});

document.addEventListener("click", (e) => {
  if (!els.form.contains(e.target)) hideResults();
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !els.results.hidden) {
    hideResults();
    els.input.focus();
  }
});

showIntro();
