# Chatbot hỏi đáp nhà thờ & giờ lễ (chạy local bằng Ollama)

Chatbot tiếng Việt tra cứu nhà thờ và giờ lễ từ `data/processed/dataset_fork2/catholic_churches_complete.csv`
(80 nhà thờ, 1.287 giờ lễ, Tổng Giáo phận Sài Gòn). Chạy hoàn toàn trên máy, không gọi dịch vụ ngoài.

## Cách hoạt động

```
Câu hỏi
  → qwen2.5:7b (Ollama, structured output theo JSON schema, temperature 0, few-shot)  [src/extract.py]
      trích: ý định, tên nhà thờ, quận, phường, địa điểm, giáo phận, thứ, buổi, giờ
  → luật cố định kiểm tra lại                                                         [src/extract.py]
      - thứ / buổi / giờ cụ thể lấy bằng regex (chịu được không dấu); LLM chỉ là phương án phụ
      - tên/địa điểm LLM trích ra phải xuất hiện (gần đúng) trong câu hỏi, nếu không thì bỏ
  → truy vấn SQLite có tham số + so khớp không dấu / sai nhẹ (rapidfuzz)              [src/db.py]
  → câu trả lời: giờ lễ, địa chỉ, link nguồn lấy thẳng từ DB                           [src/answer.py, src/bot.py]
      không tìm thấy → nói rõ "Không tìm thấy …", có thể gợi ý tên gần giống
```

LLM không bao giờ viết SQL và không tự đưa ra giờ lễ. Không dùng embedding vì dữ liệu không có cột văn bản dài.

## Hỏi nối tiếp (ngữ cảnh câu trước) — `src/context.py`

Không đưa lịch sử chat cho LLM. Model 7B trên CPU sẽ chậm hơn và hay trộn nhầm điều kiện cũ với mới.
Thay vào đó, app lưu **bộ lọc và danh sách nhà thờ của câu trước**, rồi ghép với bộ lọc của câu mới theo luật:

| Câu mới | Xử lý | Ví dụ |
|---|---|---|
| Không nhắc tên/địa điểm | Lấy tên/địa điểm của câu trước | "lễ chiều thứ 7?" |
| Có từ tham chiếu ("nhà thờ đó", "trong đó", "ở đó", "các nhà thờ trên") | Chỉ tìm trong các nhà thờ của câu trả lời trước | "trong đó nhà thờ nào có lễ thứ 7?" |
| "còn …", "… thì sao", "… nữa" kèm tên/địa điểm mới | Thay tên/địa điểm, giữ thứ/giờ của câu trước | "quận Phú Nhuận thì sao?" |
| Thiếu thứ hoặc giờ | Lấy thứ/giờ của câu trước (trừ câu hỏi địa chỉ/thông tin) | "còn buổi tối thì sao?" giữ Chúa Nhật |
| Có tên/địa điểm mới, không có từ nối | Câu hỏi mới, không kế thừa | "Các nhà thờ ở quận 1" |
| Có "tất cả", "toàn bộ" | Không kế thừa | |

Khi kế thừa, câu trả lời mở đầu bằng dòng _"Hiểu theo câu trước: …"_ để người dùng biết bot đã ghép điều kiện gì.
Câu hỏi lại (thiếu thông tin) hoặc ngoài phạm vi không xóa ngữ cảnh. Nút "Xóa hội thoại" xóa cả ngữ cảnh.

## Cài đặt

Cần: Python 3.13, Ollama đang chạy tại `http://localhost:11434` và đã có model `qwen2.5:7b`.

```powershell
cd "C:\Users\ADMIN\OneDrive\Desktop\Personel Project\CatholicNearMe project\chatbot"
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe scripts\build_db.py
```

## Chạy app

```powershell
.venv\Scripts\streamlit.exe run app.py
```

Mở http://localhost:8501. Sau khi sửa code trong `src/`, tắt app (Ctrl+C) rồi chạy lại. Streamlit chỉ tự nạp lại
`app.py`, có thể vẫn giữ bản cũ của các module trong `src/` và báo lỗi kiểu `unexpected keyword argument`.

Sidebar có:
- **Model Ollama**: đổi model ngay trong giao diện.
- **LLM viết câu mở đầu**: mặc định tắt (câu mở đầu do code tạo). Bật thì LLM viết lại câu mở đầu cho tự nhiên hơn,
  chậm thêm khoảng 6 giây/câu; câu nào chứa con số không có trong câu gốc sẽ bị loại.
- **Hiện bộ lọc đã trích**: xem JSON LLM trả về và bộ lọc cuối cùng (để gỡ lỗi).

## Kiểm thử

```powershell
.venv\Scripts\python.exe tests\eval.py
```

`tests/questions.json` có 18 câu: có dấu, không dấu, gõ sai, nơi không có trong dữ liệu, câu mơ hồ, câu ngoài phạm vi.
`tests/conversations.json` có 4 hội thoại, tổng cộng 13 lượt, để kiểm tra câu hỏi nối tiếp.
Đáp án kỳ vọng được tính bằng SQL viết tay. Nếu đổi dataset thì phải cập nhật lại đáp án.

## Cập nhật dataset mới

File gốc chỉ được đọc, không bị ghi. CSV mới cần các cột: `church_id, display_name, tgpsg_parish_name,
tgpsg_parish_address, day_of_week` (Monday…Sunday), `mass_time` (H:MM, 24h). Các cột `latitude, longitude,
tgpsg_parish_url, parish_mass_time_url` là tùy chọn.

```powershell
# dùng đường dẫn mặc định
.venv\Scripts\python.exe scripts\build_db.py
# hoặc chỉ định file khác
.venv\Scripts\python.exe scripts\build_db.py "D:\du_lieu\churches_moi.csv"
```

Script tạo lại `data/churches.db` (ghi file tạm rồi thay thế). Sau đó khởi động lại app.
Có thể đặt biến môi trường `CHURCH_CSV` / `CHURCH_DB` để đổi đường dẫn mặc định.

Nếu dataset mới có nhiều giáo phận, hoặc có cột liên hệ hay ghi chú, cần thêm cột vào `SCHEMA` trong `scripts/build_db.py`
và thêm điều kiện lọc tương ứng trong `src/db.py`. Hiện tại giáo phận khác "Sài Gòn" luôn trả lời "không có".

## Đổi model

```powershell
ollama pull <model>              # ví dụ qwen2.5:14b; cần hỏi trước khi tải model mới
$env:OLLAMA_MODEL = "<model>"
.venv\Scripts\streamlit.exe run app.py
.venv\Scripts\python.exe tests\eval.py --model <model>   # chạy lại kiểm thử với model mới
```

Hoặc gõ tên model vào sidebar. `OLLAMA_HOST` dùng để trỏ tới server Ollama khác.

## Quy ước đã chọn

| Vấn đề | Quy ước |
|---|---|
| Buổi | sáng 0:00–10:59, trưa 11:00–12:59, chiều 13:00–17:59 (lễ 17:30 tính là chiều), tối 18:00–23:59 |
| "khoảng 6h", "lúc 6h" | ±30 phút |
| "6h tối/chiều" | cộng 12 giờ |
| "ngày thường" | Thứ Hai – Thứ Bảy |
| "hôm nay", "ngày mai" | theo ngày của máy |
| Tên gần đúng | rapidfuzz ratio ≥ 85 **và** so khớp từng âm tiết: âm tiết ≤ 3 ký tự phải đúng hẳn ("Tân An" không khớp "Tân Dân"), âm tiết dài được sai 1 chữ ("Đinhh"), gõ lặp phím luôn được chấp nhận ("hòaa", "vapp"). Hoặc khớp phần đầu tên ("Vinh Sơn" → 2 nhà thờ). Khớp gần đúng thì câu trả lời ghi rõ |
| Không tìm thấy | Nói rõ điều kiện nào không có. Chỉ gợi ý tên gần giống khi lý do là tên nhà thờ, và ghi rõ "chưa chắc là nơi bạn hỏi" |
| "gần đây", "gần tôi", "quanh đây" (không kèm khu vực) | Hỏi lại quận/phường, không đoán |
| Quận/phường | tách từ địa chỉ bằng regex. 18/80 địa chỉ ghi theo địa giới mới (không có quận) nên không lọc được theo quận cũ |
| Quận/phường dạng số | phải khớp tuyệt đối ("quận 1" không khớp "quận 11") |

## Cấu trúc

```
chatbot/
  app.py               giao diện Streamlit
  scripts/build_db.py  CSV → data/churches.db
  src/config.py        đường dẫn, model (đọc từ biến môi trường)
  src/normalize.py     bỏ dấu, tách quận/phường
  src/extract.py       LLM + luật → bộ lọc
  src/context.py       ghép ngữ cảnh câu trước cho câu hỏi nối tiếp
  src/db.py            tìm kiếm có cấu trúc
  src/answer.py        định dạng câu trả lời
  src/bot.py           điều phối
  tests/               câu hỏi đơn, hội thoại nhiều lượt, eval.py
```
