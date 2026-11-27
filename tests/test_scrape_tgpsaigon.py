"""Phần parse của scraper tgpsaigon.net, chạy trên HTML mẫu rút gọn theo cấu trúc trang thật. Không gọi mạng."""
from scrapling.parser import Selector

from scripts import scrape_tgpsaigon as st

LIST_HTML = """
<div class="deaneryName">
  <a id="deaneryName" data-id="13" name="B&#236;nh An" href="#parishes">Bình An</a>
  <a id="deaneryName" data-id="4" name="Ch%C3%AD%20Ho%C3%A0" href="#parishes">Chí Hoà</a>
</div>"""

DEANERY_HTML = """
<table><tbody>
  <tr><td>1</td><td class="parishname"><a href="/gioi-thieu-giao-xu/giao-xu-binh-an-1">B&#236;nh An</a></td>
      <td>2287 Phạm Thế Hiển, P. B&#236;nh Đ&#244;ng (2287 Phạm Thế Hiển, Phường 6, Quận 8)</td></tr>
  <tr><td>2</td><td class="parishname"><a href="/gioi-thieu-giao-xu/giao-xu-binh-an-thuong-2">Bình An Thượng</a></td>
      <td>2903 Phạm Thế Hiển</td></tr>
  <tr><td>3</td><td class="parishname">Không có link</td><td>x</td></tr>
</tbody></table>"""

DETAIL_HTML = """
<div class="parish-content-detail-modal"><ul>
  <li><b>Địa chỉ: </b>2287 Phạm Thế Hiển, P. B&#236;nh Đ&#244;ng</li>
  <li><b>Bổn mạng: </b>Đức Mẹ M&#226;n C&#244;i</li>
  <li><b>Điện thoại: </b>39812896 - 3856 9139</li>
  <li><b>Năm thành lập: </b>1955 - 1972</li>
  <li><b>Giờ lễ: </b></li>
  <li><table><thead><tr>
      <th>Chúa Nhật</th><th>Thứ Hai</th><th>Thứ Ba</th><th>Thứ Tư</th><th>Thứ Năm</th><th>Thứ Sáu</th><th>Thứ Bảy</th>
    </tr></thead><tbody><tr class="mass-time-detail">
      <td><p>16:00</p><p>04:30</p><p>06:00</p></td><td><p>04:30</p></td><td></td><td></td><td></td><td></td>
      <td><p>18:00</p><p>18:00</p><p>ghi chú</p><p>16:30 tiếng Anh</p><p>`17:30</p></td>
  </tr></tbody></table></li>
  <li class="priest-list"><table><thead><tr><th>#</th><th>Linh mục</th><th>Vai trò</th></tr></thead>
    <tbody><tr><td>1</td><td>Giuse X</td><td>Chánh xứ</td></tr></tbody></table></li>
</ul></div>"""


def test_parse_deaneries():
    assert st.parse_deaneries(Selector(LIST_HTML)) == [
        {"deanery_id": "13", "deanery_name": "Bình An"},
        {"deanery_id": "4", "deanery_name": "Chí Hoà"},
    ]


def test_parse_deanery_parishes_skips_rows_without_link():
    rows = st.parse_deanery_parishes(Selector(DEANERY_HTML))
    assert [r["parish_name"] for r in rows] == ["Bình An", "Bình An Thượng"]
    assert rows[0]["parish_url"] == "https://tgpsaigon.net/gioi-thieu-giao-xu/giao-xu-binh-an-1"
    assert rows[0]["list_address"].startswith("2287 Phạm Thế Hiển, P. Bình Đông (")


def test_parse_detail_info_and_masses():
    info, masses = st.parse_parish_detail(Selector(DETAIL_HTML))
    assert {k: v for k, v in info.items() if k != "unparsed"} == {"address": "2287 Phạm Thế Hiển, P. Bình Đông", "patron": "Đức Mẹ Mân Côi",
                    "phone": "39812896 - 3856 9139", "founded": "1955 - 1972"}
    # Sắp theo ngày rồi giờ, bỏ trùng, giữ ghi chú, bỏ ký tự rác, không lấy bảng linh mục.
    assert masses == [("Sunday", "4:30", ""), ("Sunday", "6:00", ""), ("Sunday", "16:00", ""),
                      ("Monday", "4:30", ""), ("Saturday", "16:30", "tiếng Anh"), ("Saturday", "17:30", ""),
                      ("Saturday", "18:00", "")]
    assert info["unparsed"] == "Saturday: ghi chú"


def test_parse_mass_cell():
    assert st.parse_mass_cell("16:30 tiếng Anh") == ("16:30", "tiếng Anh")
    assert st.parse_mass_cell("`17:30") == ("17:30", "")
    assert st.parse_mass_cell("05g15") == ("5:15", "")
    assert st.parse_mass_cell("19.00") == ("19:00", "")
    assert st.parse_mass_cell("25:00") is None and st.parse_mass_cell("Lễ trọng") is None


def test_detail_without_mass_table():
    info, masses = st.parse_parish_detail(Selector('<div class="parish-content-detail-modal"><ul>'
                                                   '<li><b>Địa chỉ: </b>abc</li></ul></div>'))
    assert info == {"address": "abc"} and masses == []


def test_slug():
    assert st.slug("https://tgpsaigon.net/gioi-thieu-giao-xu/giao-xu-binh-an-1") == "giao-xu-binh-an-1"
