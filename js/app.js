// app.js – BẢN TẠM cho Phase 4: chỉ thử lấy GPS và hiện kết quả lên thanh trạng thái.
// Phase 9 sẽ viết lại để điều phối toàn bộ ứng dụng.

import { getCurrentLocation } from "./location.js";

const locateButton = document.getElementById("btn-locate");
const statusText = document.getElementById("status-text");

function setStatus(state, message) {
  document.body.dataset.state = state; // CSS đổi màu/spinner theo data-state
  statusText.textContent = message;
}

locateButton.addEventListener("click", async () => {
  locateButton.disabled = true;
  setStatus("REQUESTING_LOCATION", "Đang xác định vị trí...");

  try {
    const { latitude, longitude, accuracy } = await getCurrentLocation();
    setStatus(
      "SUCCESS",
      `Đã lấy vị trí: ${latitude.toFixed(5)}, ${longitude.toFixed(5)} (sai số khoảng ${Math.round(accuracy)} m)`
    );
  } catch (error) {
    setStatus("LOCATION_DENIED", error.message); // trạng thái lỗi (nền đỏ) dùng chung cho mọi lỗi vị trí
  } finally {
    locateButton.disabled = false;
  }
});
