from playwright.sync_api import sync_playwright


URL = "https://tgpsaigon.net/gioi-thieu-giao-xu/"


def main():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        try:
            page = browser.new_page()
            page.goto(URL, wait_until="domcontentloaded", timeout=60000)

            deanery = page.locator("a#deaneryName").filter(has_text="Bình An").first
            if deanery.count() == 0:
                raise RuntimeError("Không tìm thấy liên kết giáo hạt Bình An")
            deanery_name = deanery.inner_text().strip()
            rows = page.locator("table tbody tr")
            old_rows = rows.all_inner_texts()
            deanery.click(timeout=10000)
            page.wait_for_function(
                "old => { const rows = [...document.querySelectorAll('table tbody tr')]; "
                "return rows.length > 0 && JSON.stringify(rows.map(r => r.innerText)) !== JSON.stringify(old); }",
                arg=old_rows,
                timeout=15000,
            )

            parish_cells = page.locator("td.parishname")
            print(f"Giáo hạt: {deanery_name}")
            for index in range(min(3, parish_cells.count())):
                cell = parish_cells.nth(index)
                link = cell.locator("a")
                if link.count() == 0:
                    print(f"Hàng {index + 1}: không có liên kết tên giáo xứ")
                    continue
                parish_name = link.first.inner_text().strip()
                href = link.first.get_attribute("href")
                row = cell.locator("xpath=ancestor::tr[1]")
                cells = row.locator("td")
                address = cells.nth(2).inner_text().strip() if cells.count() > 2 else ""
                print(f"Tên giáo xứ: {parish_name} | Địa chỉ: {address} | href: {href}")
        finally:
            browser.close()


if __name__ == "__main__":
    main()
