// Cửa sổ chat. Chỉ hỏi đáp trên dataset; gửi kèm vị trí nếu người dùng đã định vị, không điều khiển bản đồ.
import { esc, safeUrl } from "./format.js";
import { state } from "./state.js";

const SESSION_KEY = "cnm-chat-session";
const REQUEST_TIMEOUT_MS = 150_000;
const SLOW_HINT_MS = 12_000;
const EXAMPLES = [
  "Giờ lễ nhà thờ Tân Định?",
  "Nhà thờ nào gần tôi có lễ tối nay?",
  "Lễ sáng Chúa Nhật ở Gò Vấp",
  "Nhà thờ trên đường Lê Văn Sỹ",
];

const els = {
  fab: document.getElementById("chat-fab"),
  panel: document.getElementById("chat-panel"),
  log: document.getElementById("chat-log"),
  form: document.getElementById("chat-form"),
  input: document.getElementById("chat-input"),
  send: document.getElementById("chat-send"),
  subtitle: document.getElementById("chat-subtitle"),
  minimize: document.getElementById("chat-minimize"),
  close: document.getElementById("chat-close"),
  reset: document.getElementById("chat-reset"),
};

let busy = false;

// ---------- Phiên (ngữ cảnh câu hỏi nối tiếp nằm ở server) ----------

function loadSession() {
  try {
    return sessionStorage.getItem(SESSION_KEY);
  } catch {
    return null;
  }
}

let sessionId = loadSession();

function saveSession(id) {
  sessionId = id;
  try {
    if (id) sessionStorage.setItem(SESSION_KEY, id);
    else sessionStorage.removeItem(SESSION_KEY);
  } catch {
    // Trình duyệt chặn storage: vẫn chat được, chỉ mất ngữ cảnh khi tải lại trang.
  }
}

// ---------- Hiển thị markdown đơn giản do bot sinh ra (đã escape trước) ----------

function inline(text) {
  return esc(text)
    .replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (_, label, href) => {
      const url = safeUrl(href.replace(/&amp;/g, "&"));
      if (!url) return label;
      const shown = label.startsWith("http") ? new URL(url).hostname : label;
      return `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${shown}</a>`;
    })
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[\s(])_(.+?)_(?=$|[\s.,:;)])/g, "$1<em>$2</em>");
}

function renderMarkdown(text) {
  return text
    .split(/\n{2,}/)
    .map((block) => {
      let html = "";
      let list = [];
      const flush = () => {
        if (list.length) html += `<ul>${list.map((li) => `<li>${inline(li)}</li>`).join("")}</ul>`;
        list = [];
      };
      for (const line of block.split("\n")) {
        if (line.startsWith("- ")) list.push(line.slice(2));
        else {
          flush();
          html += `<p>${inline(line)}</p>`;
        }
      }
      flush();
      return html;
    })
    .join("");
}

function renderTable(rows) {
  if (!rows?.length) return "";
  const items = rows
    .map((r) => {
      const src = safeUrl(r["Nguồn"]);
      return `<li>
        <strong>${esc(r["Nhà thờ"])}</strong>${r["Khoảng cách"] ? ` <span class="chat-dist">${esc(r["Khoảng cách"])}</span>` : ""}
        ${r["Địa chỉ"] ? `<div class="chat-muted">${esc(r["Địa chỉ"])}</div>` : ""}
        ${r["Giờ lễ"] ? `<div>${esc(r["Giờ lễ"])}</div>` : ""}
        ${src ? `<a href="${esc(src)}" target="_blank" rel="noopener noreferrer">Nguồn</a>` : ""}
      </li>`;
    })
    .join("");
  return `<ol class="chat-table">${items}</ol>`;
}

// ---------- Tin nhắn ----------

function addMessage(role, html, extraClass = "") {
  const div = document.createElement("div");
  div.className = `msg msg-${role}${extraClass ? ` ${extraClass}` : ""}`;
  div.innerHTML = html;
  els.log.append(div);
  els.log.scrollTop = els.log.scrollHeight;
  return div;
}

function welcome() {
  const chips = EXAMPLES.map((q) => `<button type="button" class="chat-chip">${esc(q)}</button>`).join("");
  addMessage(
    "bot",
    `<p>Xin chào! Mình giúp tra cứu nhà thờ và giờ lễ ở TP.HCM. Câu trả lời chỉ dựa trên dữ liệu có sẵn.</p>
     <p>Bạn có thể hỏi:</p><div class="chat-chips">${chips}</div>`,
  );
}

els.log.addEventListener("click", (e) => {
  const chip = e.target.closest(".chat-chip");
  if (chip && !busy) ask(chip.textContent);
});

function updateSubtitle() {
  const loc = state.location;
  els.subtitle.textContent = loc
    ? `Đang dùng vị trí: ${loc.label || "vị trí của bạn"}`
    : "Trả lời dựa trên dữ liệu 80 nhà thờ";
}

// ---------- Gửi câu hỏi ----------

function setBusy(value) {
  busy = value;
  els.send.disabled = value;
  els.input.setAttribute("aria-busy", String(value));
}

async function ask(question) {
  const text = question.trim();
  if (!text || busy) return;
  addMessage("user", `<p>${esc(text)}</p>`);
  els.input.value = "";
  autosize();
  setBusy(true);
  updateSubtitle();

  const typing = addMessage(
    "bot",
    `<span class="typing-dots" aria-hidden="true"><i></i><i></i><i></i></span><span class="typing-text">Đang trả lời…</span>`,
    "is-typing",
  );
  const slowHint = setTimeout(() => {
    typing.querySelector(".typing-text").textContent = "Đang trả lời… (lần đầu có thể mất vài chục giây)";
  }, SLOW_HINT_MS);
  const ctrl = new AbortController();
  const timeout = setTimeout(() => ctrl.abort(), REQUEST_TIMEOUT_MS);

  const body = { message: text, session_id: sessionId };
  if (state.location) Object.assign(body, { lat: state.location.lat, lon: state.location.lon });

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: ctrl.signal,
    });
    const data = await res.json().catch(() => null);
    typing.remove();
    if (!res.ok) {
      const detail = typeof data?.detail === "string" ? data.detail : "Trợ lý đang gặp sự cố. Bạn thử lại sau nhé.";
      addMessage("bot", `<p>${esc(detail)}</p>`, "is-error");
      return;
    }
    saveSession(data.session_id);
    addMessage("bot", renderMarkdown(data.reply) + renderTable(data.table));
  } catch (err) {
    typing.remove();
    const msg =
      err.name === "AbortError"
        ? "Trợ lý trả lời quá lâu. Có thể máy đang bận, bạn thử hỏi lại sau ít phút nhé."
        : "Không kết nối được máy chủ. Kiểm tra server còn chạy không rồi thử lại.";
    addMessage("bot", `<p>${esc(msg)}</p>`, "is-error");
  } finally {
    clearTimeout(slowHint);
    clearTimeout(timeout);
    setBusy(false);
    els.input.focus();
  }
}

els.form.addEventListener("submit", (e) => {
  e.preventDefault();
  ask(els.input.value);
});

els.input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
    e.preventDefault();
    ask(els.input.value);
  }
});

function autosize() {
  els.input.style.height = "auto";
  els.input.style.height = `${Math.min(els.input.scrollHeight, 120)}px`;
  els.input.style.overflowY = els.input.scrollHeight > 120 ? "auto" : "hidden";
}
els.input.addEventListener("input", autosize);

// ---------- Mở / thu nhỏ / đóng ----------

function open() {
  els.panel.hidden = false;
  els.panel.classList.remove("is-minimized");
  els.fab.hidden = true;
  els.fab.setAttribute("aria-expanded", "true");
  updateSubtitle();
  if (!els.log.children.length) welcome();
  els.input.focus();
}

function close() {
  els.panel.hidden = true;
  els.fab.hidden = false;
  els.fab.setAttribute("aria-expanded", "false");
  els.fab.focus();
}

function toggleMinimize() {
  const minimized = els.panel.classList.toggle("is-minimized");
  els.minimize.setAttribute("aria-label", minimized ? "Mở rộng cửa sổ chat" : "Thu nhỏ cửa sổ chat");
  els.minimize.title = minimized ? "Mở rộng" : "Thu nhỏ";
  if (!minimized) els.input.focus();
}

async function resetConversation() {
  if (busy) return;
  if (sessionId) {
    fetch("/api/chat/reset", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId }),
    }).catch(() => {});
  }
  saveSession(null);
  els.log.innerHTML = "";
  welcome();
  els.input.focus();
}

els.fab.addEventListener("click", open);
els.close.addEventListener("click", close);
els.minimize.addEventListener("click", toggleMinimize);
els.reset.addEventListener("click", resetConversation);
els.panel.querySelector(".chat-header").addEventListener("dblclick", toggleMinimize);
els.panel.addEventListener("keydown", (e) => {
  if (e.key === "Escape") close();
});
