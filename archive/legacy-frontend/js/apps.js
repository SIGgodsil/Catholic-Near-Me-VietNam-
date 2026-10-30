// app.js – BẢN TẠM cho Phase 5: GPS -> Overpass -> hiện số kết quả thô + thử nút Overpass Turbo.
// Phase 9 sẽ viết lại đầy đủ (chuẩn hóa, danh sách, bản đồ...).

import { getCurrentLocation, LOCATION_ERROR } from "./location.js";
import { fetchChurches, buildOverpassTurboUrl } from "./overpass.js";
import { kmToMeters } from "./utils.js";

const locateButton = document.getElementById("btn-locate");
const turboButton = document.getElementById("btn-turbo");
const radiusSelect = document.getElementById("radius-select");
const statusText = document.getElementById("status-text");

let lastQuery = null; // query vừa dùng, để nút Turbo mở đúng query này

function setStatus(state, message) {
  document.body.dataset.state = state;
  statusText.textContent = message;
}

// Đổi lỗi thành trạng thái giao diện
function showError(error) {
  const isLocationError = Object.values(LOCATION_ERROR).includes(error.code);
  if (isLocationError) return setStatus("LOCATION_DENIED", error.message);
  if (error.code === "NETWORK_ERROR" || error.code === "OVERPASS_ERROR") return setStatus(error.code, error.message);
  console.error(error);
  setStatus("OVERPASS_ERROR", "Đã xảy ra lỗi không mong muốn.");
}

locateButton.addEventListener("click", async () => {
  locateButton.disabled = true;
  setStatus("REQUESTING_LOCATION", "Đang xác định vị trí...");
  try {
    const { latitude, longitude } = await getCurrentLocation();

    setStatus("FETCHING_DATA", "Đang tìm nhà thờ gần bạn...");
    const radiusKm = Number(radiusSelect.value);
    const { query, elements } = await fetchChurches(latitude, longitude, kmToMeters(radiusKm));

    lastQuery = query;
    turboButton.disabled = false;
    console.log("Query đã dùng:\n" + query);
    console.log("Dữ liệu thô từ Overpass:", elements);

    if (elements.length === 0) {
      setStatus("NO_RESULTS", "Không tìm thấy nhà thờ trong bán kính này.");
    } else {
      setStatus("SUCCESS", `Overpass trả về ${elements.length} địa điểm (chưa lọc). Xem chi tiết trong Console (F12).`);
    }
  } catch (error) {
    showError(error);
  } finally {
    locateButton.disabled = false;
  }
});

turboButton.addEventListener("click", () => {
  if (lastQuery) window.open(buildOverpassTurboUrl(lastQuery), "_blank", "noopener");
});
