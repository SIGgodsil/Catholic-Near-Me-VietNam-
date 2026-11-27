import assert from "node:assert/strict";
import { test } from "node:test";
import {
  haversineM, locationMatches, nameMatches, parseAddress, parseCameraFromUrl, parseCoordText, parseCsv, parsePinFromUrl,
  pixelOffset, toCsv,
} from "./lib.mjs";

test("CSV đọc/ghi giữ nguyên ô có dấu phẩy, ngoặc kép và BOM", () => {
  const src = '﻿a,b\r\n1,"x, ""y"""\r\n';
  const { header, records } = parseCsv(src);
  assert.deepEqual(header, ["a", "b"]);
  assert.deepEqual(records, [{ a: "1", b: 'x, "y"' }]);
  assert.equal(toCsv(header, records), src);
});

test("đọc tọa độ từ menu chuột phải", () => {
  assert.deepEqual(parseCoordText("10.75123, 106.66345"), { lat: 10.75123, lng: 106.66345 });
  assert.equal(parseCoordText("Chỉ đường từ đây"), null);
});

test("đọc marker và camera trong URL Google Maps", () => {
  const url = "https://www.google.com/maps/place/Nha+tho/@10.7512,106.6601,17z/data=!3m1!4b1!4m6!3m5!1s0x0:0x1!8m2!3d10.7513!4d106.6634!16s";
  assert.deepEqual(parsePinFromUrl(url), { lat: 10.7513, lng: 106.6634 });
  assert.deepEqual(parseCameraFromUrl(url), { lat: 10.7512, lng: 106.6601, zoom: 17 });
  assert.equal(parseCameraFromUrl("https://www.google.com/maps/@10.7,106.6,512m/data=!3m1!1e3").zoom, null);
});

test("chiếu pixel: lệch 1 ô 256px ở zoom 0 bằng 360 độ kinh", () => {
  const { dx, dy } = pixelOffset({ lat: 0, lng: 0 }, { lat: 0, lng: 90 }, 0);
  assert.ok(Math.abs(dx - 64) < 1e-9);
  assert.ok(Math.abs(dy) < 1e-9);
  assert.ok(pixelOffset({ lat: 10, lng: 106 }, { lat: 10.001, lng: 106 }, 17).dy < 0); // lên bắc = lên trên
});

test("tách địa chỉ dataset", () => {
  assert.deepEqual(parseAddress("3131 Phạm Thế Hiển, phường Bình Đông, TP. Hồ Chí Minh (3131 Phạm Thế Hiển, P.7, Q.8)"),
    { streetPart: "3131 Phạm Thế Hiển", street: "Phạm Thế Hiển", ward: "Bình Đông", district: "Quận 8" });
  assert.equal(parseAddress("Số 62, Đường số 5, Khu dân cư Him Lam, Phường Tân Hưng (Số 62 Đường số 5, P. Tân Hưng, Q. 7)").streetPart, "Số 62, Đường số 5");
  assert.equal(parseAddress("2838 (số cũ 3A62) Trần Văn Giàu, xã Tân Vĩnh Lộc, Tp.HCM").street, "Trần Văn Giàu");
  assert.equal(parseAddress("111 Đường 6B, xã Vĩnh Lộc (111 Đường 6B, Xã Vĩnh Lộc B, Huyện Bình Chánh. TP.HCM)").district, "Bình Chánh");
  assert.equal(parseAddress("947/13/3 Cách Mạng Tháng Tám, phường Tân Sơn Nhất (947/13/3 CMT8, P.7. Q. Tân Bình)").district, "Tân Bình");
});

test("so tên: bỏ tiền tố, tên ngắn phải đủ token", () => {
  assert.ok(nameMatches("Nhà thờ Bình Thuận", "Nhà thờ Giáo xứ Bình Thuận (Đức Mẹ Mân Côi)"));
  assert.ok(!nameMatches("Nhà thờ Bình An Thượng", "Giáo Xứ Bình An"));
  assert.ok(nameMatches("Nhà thờ Giáo họ Giuse - Vĩnh Lộc B", "Giáo họ Thánh Giuse Vĩnh Lộc B"));
  assert.ok(nameMatches("Nhà thờ Antôn", "Giáo xứ An Tôn"));
  assert.ok(nameMatches("Nhà thờ Thánh Martinô", "Nhà Thờ Giáo Xứ Martino de Porres"));
  assert.ok(!nameMatches("Nhà thờ Thánh Giuse", "Nhà thờ Thánh Phaolô"));
  assert.ok(!nameMatches("Nhà thờ An Phú", "Nhà thờ Giáo xứ Xuân Phú"));
});

test("so địa chỉ: đúng đường / phường, sai quận thì không khớp", () => {
  const p = parseAddress("119 Bến Mễ Cốc, P. Phú Định (119 Bến Mễ Cốc, Phường 15, Quận 8, TP. Hồ Chí Minh)");
  assert.equal(locationMatches(p, "119 Mễ Cốc, Phú Định, Hồ Chí Minh, Việt Nam"), "duong");
  const q = parseAddress("3131 Phạm Thế Hiển, phường Bình Đông, TP. Hồ Chí Minh (3131 Phạm Thế Hiển, P.7, Q.8)");
  assert.equal(locationMatches(q, "722 Tân Kỳ Tân Quý, Bình Hưng Hoà, Bình Tân, Hồ Chí Minh"), "");
  const r = parseAddress("1C Khu phố 1, phường Tân Thới Hiệp (1C Khu phố I, P.Tân Thới Hiệp, Q12)");
  assert.equal(locationMatches(r, "1C KP1, Tân Thới Hiệp, Quận 12, Hồ Chí Minh"), "phuong");
  assert.equal(locationMatches({ street: "", ward: "", district: "Quận 1" }, "26A Nguyễn Thái Bình, Quận 12"), "");
});

test("khoảng cách haversine", () => {
  const d = haversineM({ lat: 10.7513, lng: 106.6634 }, { lat: 10.7513, lng: 106.6644 });
  assert.ok(d > 105 && d < 112);
});
