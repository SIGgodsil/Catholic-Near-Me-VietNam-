// utils.js – Các hàm nhỏ dùng chung. (Các phase sau sẽ thêm Haversine, bỏ dấu tiếng Việt, debounce.)

// Đổi km sang mét vì Overpass dùng đơn vị mét: 3 km -> 3000
export function kmToMeters(km) {
  return Math.round(km * 1000);
}
