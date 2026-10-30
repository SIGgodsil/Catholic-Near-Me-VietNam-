# archive/

Mã nguồn cũ được giữ lại để tham khảo. **Không còn được bảo trì**: đường dẫn trong code là đường dẫn trước khi sắp xếp
lại thư mục, và một số file cần thư viện không có trong `requirements.txt` (vd. Playwright).

| Thư mục | Nội dung |
|---|---|
| `legacy-frontend/` | Frontend thử nghiệm đầu tiên, lấy dữ liệu trực tiếp từ Overpass API |
| `pipeline/` | Script thu thập và đối chiếu dữ liệu: cào tgpsaigon.net, chuyển GeoJSON OSM sang CSV, ghép và kiểm tra dữ liệu |
| `pipeline/tests/` | Test và script thử của các công cụ trên |

Dữ liệu các script này tạo ra nằm trong `data/raw`, `data/interim` và `data/reports`.
