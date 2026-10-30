// location.js – Lấy vị trí GPS hiện tại của người dùng.
// Chỉ làm đúng một việc: trả về { latitude, longitude, accuracy } hoặc báo lỗi rõ ràng.
// Vị trí KHÔNG được lưu ở đâu cả và KHÔNG gửi tới server riêng.

import { CONFIG } from "../config/config.js";

// Các mã lỗi mà app.js có thể kiểm tra: error.code === "DENIED", ...
export const LOCATION_ERROR = {
  UNSUPPORTED: "UNSUPPORTED", // trình duyệt không hỗ trợ (hoặc trang không chạy qua https/localhost)
  DENIED: "DENIED",           // người dùng không cho phép
  UNAVAILABLE: "UNAVAILABLE", // thiết bị không xác định được vị trí
  TIMEOUT: "TIMEOUT",         // chờ quá lâu
};

// Thông báo tiếng Việt hiển thị cho người dùng
const ERROR_MESSAGES = {
  UNSUPPORTED: "Trình duyệt của bạn không hỗ trợ định vị, hoặc trang chưa chạy trên https/localhost.",
  DENIED: "Không thể truy cập vị trí. Vui lòng cho phép trình duyệt sử dụng vị trí.",
  UNAVAILABLE: "Thiết bị chưa xác định được vị trí. Hãy bật GPS/Wi-Fi rồi thử lại.",
  TIMEOUT: "Xác định vị trí mất quá nhiều thời gian. Vui lòng thử lại.",
};

// Tạo một Error có thêm thuộc tính "code" để nơi khác biết loại lỗi
function makeLocationError(code) {
  const error = new Error(ERROR_MESSAGES[code]);
  error.code = code;
  return error;
}

// Đổi lỗi gốc của trình duyệt (GeolocationPositionError.code: 1, 2, 3) sang mã của mình
function convertBrowserError(browserError) {
  switch (browserError.code) {
    case 1: return makeLocationError(LOCATION_ERROR.DENIED);
    case 3: return makeLocationError(LOCATION_ERROR.TIMEOUT);
    default: return makeLocationError(LOCATION_ERROR.UNAVAILABLE); // code 2 và mọi trường hợp khác
  }
}

/**
 * Xin quyền và lấy vị trí hiện tại.
 * @returns {Promise<{latitude: number, longitude: number, accuracy: number}>} accuracy tính bằng mét
 * @throws Error có thuộc tính code thuộc LOCATION_ERROR
 */
export function getCurrentLocation() {
  return new Promise((resolve, reject) => {
    const supported = "geolocation" in navigator && window.isSecureContext;
    if (!supported) {
      reject(makeLocationError(LOCATION_ERROR.UNSUPPORTED));
      return;
    }

    navigator.geolocation.getCurrentPosition(
      (position) => {
        resolve({
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
          accuracy: position.coords.accuracy,
        });
      },
      (browserError) => reject(convertBrowserError(browserError)),
      CONFIG.GEOLOCATION_OPTIONS
    );
  });
}
