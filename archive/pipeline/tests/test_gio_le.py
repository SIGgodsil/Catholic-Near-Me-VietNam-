from playwright.sync_api import sync_playwright


URL = "https://tgpsaigon.net/gio-le/"
WEEKDAYS = ("Chúa Nhật", "Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy")


def main():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(URL, wait_until="networkidle", timeout=60000)
            page.wait_for_load_state("domcontentloaded")
            print(f"Tiêu đề: {page.title()}")
            print(f"URL: {page.url}")
            print(f"Số bảng: {page.locator('table').count()}")
            print(f"Số hàng tr: {page.locator('tr').count()}")

            weekday_table = None
            for i in range(page.locator("table").count()):
                table = page.locator("table").nth(i)
                headers = table.locator("th").all_inner_texts()
                if all(day in " ".join(headers) for day in WEEKDAYS):
                    weekday_table = table
                    print(f"Bảng giờ lễ: table thứ {i + 1}; tiêu đề cột: {headers}")
                    break
            if weekday_table:
                for i in range(min(3, weekday_table.locator("tbody tr").count())):
                    print(f"HTML hàng dữ liệu {i + 1}: {weekday_table.locator('tbody tr').nth(i).evaluate('(el) => el.outerHTML')}")
            else:
                print("Không tìm thấy bảng có đủ tiêu đề các ngày trong tuần.")

            for label, selector in (
                ("Tìm giáo xứ", "input"),
                ("Lọc giáo hạt", "select"),
                ("Nút tìm kiếm", "button, input[type='submit'], input[type='button']"),
            ):
                for element in page.locator(selector).all():
                    name = element.get_attribute("name")
                    element_id = element.get_attribute("id")
                    element_type = element.get_attribute("type")
                    text = (element.inner_text() if element.evaluate("el => el.tagName === 'BUTTON'") else "").strip()
                    if (label == "Tìm giáo xứ" and element_type in (None, "text", "search")) or (
                        label == "Lọc giáo hạt" and element.evaluate("el => el.tagName === 'SELECT'")
                    ) or (label == "Nút tìm kiếm" and (text or element_type in ("submit", "button"))):
                        print(f"{label}: text={text!r}, name={name!r}, id={element_id!r}, type={element_type!r}")

            print(f"Giờ lễ có sẵn trong HTML sau tải: {'có' if weekday_table else 'chưa xác định; cần thử tìm kiếm'}")
        finally:
            browser.close()


if __name__ == "__main__":
    main()
