# Catholic Near Me — tìm nhà thờ gần bạn & hỏi đáp giờ lễ

Trang web chạy trên máy này: bản đồ OpenStreetMap hiển thị các nhà thờ trong bán kính 3 km quanh vị trí của bạn,
đánh dấu nơi có lễ trong 2 giờ tới, kèm chatbot tiếng Việt (Ollama, chạy local) trả lời từ dataset.

Dữ liệu: `data/processed/dataset_fork2/catholic_churches_complete.csv`, gồm 80 nhà thờ và 1.287 giờ lễ thuộc Tổng Giáo phận
Sài Gòn. Ngoài TP.HCM sẽ không có kết quả.

## Cài đặt (một lần)

Cần Python 3.13, cùng Ollama đang chạy tại `http://localhost:11434` và đã có model `qwen2.5:7b`.

```powershell
cd "C:\Users\ADMIN\OneDrive\Desktop\Personel Project\CatholicNearMe project\chatbot"
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe scripts\build_db.py
```

`requirements.txt` có `tzdata` vì Windows không có sẵn múi giờ `Asia/Ho_Chi_Minh` cho Python.

## Chạy

```powershell
cd "C:\Users\ADMIN\OneDrive\Desktop\Personel Project\CatholicNearMe project\chatbot"
.\run.ps1
```

Nếu PowerShell báo không được chạy script (ExecutionPolicy), dùng `powershell -ExecutionPolicy Bypass -File .\run.ps1`
hoặc chạy trực tiếp:

```powershell
.venv\Scripts\python.exe -m uvicorn server.main:app --host 127.0.0.1 --port 8000
```

Mở **http://localhost:8000**. Muốn dừng thì bấm Ctrl+C. Sau khi sửa code Python thì phải chạy lại server; file trong `static/` chỉ cần tải lại trang.
Không nên dùng `--reload`, vì trên Windows chế độ này đôi khi bị treo khi nạp lại.

- **Chỉ chạy trên máy này.** Server nghe ở `127.0.0.1`, máy khác trong mạng không truy cập được.
  Trình duyệt coi `http://localhost` là ngữ cảnh an toàn nên định vị vẫn chạy mà không cần HTTPS.
- **Ollama chỉ nghe ở localhost.** Chỉ backend gọi Ollama, trình duyệt không gọi thẳng tới Ollama.
- Cần Internet cho tile bản đồ OSM, thư viện Leaflet (unpkg), font Google và chức năng tìm địa chỉ (Nominatim).
  Chatbot và dữ liệu nhà thờ chạy offline.

## Chức năng

| Chức năng | Cách hoạt động |
|---|---|
| Định vị | Chỉ xin quyền khi bấm “Tìm nhà thờ gần tôi”. Nếu bị từ chối, gặp lỗi hoặc sai số trên 500 m thì gợi ý nhập địa chỉ |
| Tìm địa chỉ | Nominatim gọi qua backend: User-Agent riêng, tối đa 1 request/giây, cache 7 ngày, `countrycodes=vn`, ưu tiên vùng TP.HCM. Chỉ tìm khi bấm “Tìm”, không gợi ý theo từng phím gõ (Nominatim cấm điều này) |
| Bán kính 3 km | Tính bằng Haversine ở backend, vẽ vòng tròn trên bản đồ. Không có nhà thờ nào trong bán kính thì báo rõ |
| Popup | Tên, giáo xứ, địa chỉ, khoảng cách, giờ lễ gộp theo ngày, liên hệ, link nguồn, chỉ đường (OSM). Trường trống bị ẩn |
| Lễ sắp diễn ra | Ghim đỏ khi có lễ bắt đầu trong [bây giờ, bây giờ + 120 phút] theo giờ Asia/Ho_Chi_Minh, tính cả trường hợp qua nửa đêm. Trang tự làm mới mỗi phút |
| Chatbot | Nút góc phải dưới. Đã định vị thì câu hỏi “gần tôi” tìm trong 3 km quanh vị trí đó. Chatbot không điều khiển bản đồ. Khi Ollama tắt sẽ hiện thông báo lỗi thân thiện |

**Thử giao diện ở giờ khác:** mở `http://localhost:8000/?at=2026-10-25T16:30` để giả lập thời điểm (giờ VN) khi tính lễ sắp diễn ra.

## API

| Endpoint | Mô tả |
|---|---|
| `GET /api/health` | Số nhà thờ, trạng thái Ollama (`ok` / `no_model` / `down`) |
| `GET /api/churches/nearby?lat=&lon=&radius_km=3[&at=]` | Nhà thờ trong bán kính (tối đa 20 km), gần nhất trước, kèm `next_mass` nếu có lễ trong 2 giờ tới |
| `GET /api/geocode?q=` | Tìm tọa độ từ địa chỉ (Nominatim) |
| `POST /api/chat` | `{message, session_id?, lat?, lon?}` → `{reply, status, session_id, table}` |
| `POST /api/chat/reset` | `{session_id}`: xóa ngữ cảnh hội thoại |

Tài liệu tự sinh xem tại http://localhost:8000/docs.

## Biến môi trường (tùy chọn)

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `OLLAMA_HOST` | `http://localhost:11434` | Server Ollama |
| `OLLAMA_MODEL` | `qwen2.5:7b` | Model dùng cho chatbot |
| `OLLAMA_TIMEOUT` | `120` | Giây chờ tối đa. Lần gọi đầu phải nạp model nên chậm |
| `CHURCH_CSV` / `CHURCH_DB` | xem `src/config.py` | Dataset nguồn / file SQLite |
| `NOMINATIM_CONTACT` | trống | Email liên hệ gắn vào User-Agent (Nominatim khuyến khích) |
| `NOMINATIM_VIEWBOX` | vùng TP.HCM | Vùng ưu tiên khi tìm địa chỉ |

## Cập nhật dataset

File gốc chỉ được đọc, không bao giờ bị ghi. CSV mới cần có các cột `church_id, display_name, tgpsg_parish_name,
tgpsg_parish_address, day_of_week` (Monday…Sunday) và `mass_time` (H:MM, 24h).

Các cột tùy chọn:
- `latitude, longitude`: không có tọa độ thì nhà thờ không hiện trên bản đồ.
- `tgpsg_parish_url, parish_mass_time_url`.
- `phone, email, website`: popup tự hiện mục “Liên hệ” khi các cột này có giá trị.

```powershell
.venv\Scripts\python.exe scripts\build_db.py                          # dùng đường dẫn mặc định
.venv\Scripts\python.exe scripts\build_db.py "D:\du_lieu\churches_moi.csv"
```

Script tạo lại `data/churches.db` (ghi ra file tạm rồi thay thế), sau đó khởi động lại server. Còn hai việc cần làm tay:
1. Sửa số nhà thờ trong `SCOPE_NOTE` (`src/bot.py`). Test `test_church_count_matches_scope_note` sẽ báo nếu bạn quên.
2. Đáp án kỳ vọng trong `tests/questions.json` và `tests/conversations.json` được viết theo dataset hiện tại, nên phải cập nhật lại.

Nếu dataset mới có nhiều giáo phận, cần thêm điều kiện lọc trong `src/db.py`. Hiện tại, hỏi giáo phận khác "Sài Gòn" luôn nhận câu trả lời "không có".

## Kiểm thử

```powershell
.venv\Scripts\python.exe -m pytest              # 51 test, không cần Ollama, không gọi mạng
.venv\Scripts\python.exe tests\eval.py          # chatbot với Ollama thật: 27 câu đơn + 13 lượt hội thoại
```

`pytest` kiểm tra:
- khoảng cách Haversine và lọc bán kính 3 km, gồm cả biên và vĩ độ cao;
- lễ trong 2 giờ tới, gồm biên 120 phút, lễ vừa bắt đầu, qua nửa đêm (Thứ Bảy → Chúa Nhật, Chúa Nhật → Thứ Hai), Chúa Nhật và đổi múi giờ;
- các API, proxy Nominatim (giả lập HTTP) và chatbot (giả lập LLM).

Test chạy trên một bản DB tạm build từ CSV, không đụng tới `data/churches.db`.

## Chatbot hoạt động thế nào

```
Câu hỏi
  → qwen2.5:7b (Ollama, structured output theo JSON schema, temperature 0, few-shot)  [src/extract.py]
  → luật cố định kiểm tra lại: thứ/buổi/giờ lấy bằng regex; tên/địa điểm phải xuất hiện trong câu hỏi
  → "gần tôi" + có vị trí → giới hạn trong các nhà thờ cách ≤ 3 km                       [src/bot.py]
  → truy vấn SQLite có tham số + so khớp không dấu / sai nhẹ (rapidfuzz)                 [src/db.py]
  → câu trả lời: giờ lễ, địa chỉ, link lấy thẳng từ DB                                   [src/answer.py]
```

LLM không bao giờ viết SQL và không tự đưa ra giờ lễ. Câu hỏi nối tiếp được xử lý bằng luật ghép bộ lọc
(`src/context.py`), không đưa lịch sử chat cho LLM. Ngữ cảnh lưu trên server theo `session_id`, trong RAM, hết hạn sau 2 giờ.

### Quy ước

| Vấn đề | Quy ước |
|---|---|
| Buổi | sáng 0:00–10:59, trưa 11:00–12:59, chiều 13:00–17:59 (lễ 17:30 tính là chiều), tối 18:00–23:59 |
| "khoảng 6h", "lúc 6h" | ±30 phút |
| "6h tối/chiều" | cộng 12 giờ |
| "ngày thường" | Thứ Hai – Thứ Bảy |
| "hôm nay", "tối nay", "ngày mai" | theo ngày của máy |
| "gần đây", "gần tôi" | Đã định vị thì tìm trong 3 km, gần nhất trước; chưa định vị thì hỏi lại |
| Tên gần đúng | rapidfuzz ratio ≥ 85 và so khớp từng âm tiết (âm tiết ≤ 3 ký tự phải đúng hẳn). Khớp gần đúng thì câu trả lời ghi rõ |
| Quận/phường dạng số | phải khớp tuyệt đối ("quận 1" không khớp "quận 11") |
| Lễ sắp diễn ra | bắt đầu trong 0–120 phút tới, tính cả biên; lễ đã bắt đầu thì không tính; "còn X phút" làm tròn xuống |
| Khoảng cách | Haversine, bán kính Trái Đất 6371,0088 km; dưới 1 km ghi theo mét, làm tròn 10 m |

### Giới hạn đã biết

- Dataset chỉ có lịch lễ theo tuần, không có lễ trọng hay lễ theo mùa, cũng chưa có điện thoại/email/website.
- Nominatim thường không nhận tên quận cũ (ví dụ "Quận 3") sau khi sáp nhập hành chính. Nên nhập tên địa danh hoặc phường mới.
- 18/80 địa chỉ ghi theo địa giới mới nên chatbot không lọc được các nhà thờ này theo quận cũ.

## Cấu trúc

```
chatbot/
  run.ps1              chạy server
  server/main.py       FastAPI: API + phục vụ static/
  server/nominatim.py  proxy Nominatim (rate limit, cache)
  server/sessions.py   ngữ cảnh hội thoại theo phiên
  static/              index.html, css/style.css, js/ (app, map, popup, chat, api, format, state)
  scripts/build_db.py  CSV → data/churches.db
  src/                 logic dùng chung (chatbot, tìm kiếm, khoảng cách, lịch lễ)
    config.py, normalize.py, extract.py, context.py, db.py, answer.py, bot.py
    geo.py             Haversine, lọc bán kính
    nearby.py          dữ liệu nhà thờ cho bản đồ
    schedule.py        lễ sắp diễn ra (Asia/Ho_Chi_Minh)
  tests/               pytest + eval.py (Ollama thật)
  app.py               giao diện Streamlit cũ (sẽ bỏ)
```

## Ghi chú kỹ thuật

- Leaflet 1.9.4 tải từ unpkg, có kiểm tra SRI (integrity). Kế hoạch ban đầu là lưu sẵn trong `static/vendor`, nhưng
  bản đồ vẫn cần Internet để tải tile nên tải từ CDN cũng không làm mất thêm gì.
- Màu: vàng đồng `#C9A13B` chỉ dùng để trang trí (độ tương phản 2,4:1); chữ và nút dùng đồng đậm `#7A5410`
  (6,8:1 trên nền trắng, đạt WCAG AA).
- Ghim đỏ `#B42318` dành cho nhà thờ có lễ sắp diễn ra; marker người dùng là chấm xanh.
