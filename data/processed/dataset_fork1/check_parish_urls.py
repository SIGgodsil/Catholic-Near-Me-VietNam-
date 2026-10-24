
import csv
import os
from collections import Counter
from urllib.parse import urlsplit, urlunsplit

# Thay bằng tên file CSV thực tế của bạn
DATASET_1 = "tgpsaigon_parishes.csv"
DATASET_3 = "tgpsaigon_mass_times.csv"


def normalize_url(url):
    url = (url or "").strip()

    if not url:
        return ""

    # Chuẩn hóa URL để so sánh, không sửa dữ liệu gốc
    parts = urlsplit(url)

    scheme = parts.scheme.lower()
    netloc = parts.netloc.lower()
    path = parts.path.rstrip("/")

    return urlunsplit((
        scheme,
        netloc,
        path,
        parts.query,
        parts.fragment
    ))


def inspect_csv(filename):
    if not os.path.isfile(filename):
        print("\nKHONG TIM THAY FILE:", filename)
        return None

    with open(filename, "r", encoding="utf-8-sig",
              newline="") as file:
        reader = csv.DictReader(file)

        if not reader.fieldnames:
            print("\nFILE KHONG CO HEADER:", filename)
            return None

        if "parish_url" not in reader.fieldnames:
            print("\nTHIEU COT parish_url:", filename)
            print("Cac cot hien co:", reader.fieldnames)
            return None

        rows = list(reader)

    urls = [
        normalize_url(row.get("parish_url", ""))
        for row in rows
    ]

    nonempty = [url for url in urls if url]
    counts = Counter(nonempty)

    missing = sum(1 for url in urls if not url)
    duplicate_groups = {
        url: count
        for url, count in counts.items()
        if count > 1
    }

    print("\n" + "=" * 55)
    print("FILE:", filename)
    print("Tong so ban ghi:", len(rows))
    print("URL thieu:", missing)
    print("URL co gia tri:", len(nonempty))
    print("So URL duy nhat:", len(counts))
    print("So nhom URL bi trung:", len(duplicate_groups))

    if duplicate_groups:
        print("\nCac URL bi trung:")
        for url, count in duplicate_groups.items():
            print(count, "lan:", url)

    return {
        "rows": rows,
        "urls": set(nonempty),
        "counts": counts,
        "missing": missing
    }


data1 = inspect_csv(DATASET_1)
data3 = inspect_csv(DATASET_3)

if data1 is not None and data3 is not None:
    common = data1["urls"] & data3["urls"]
    only1 = data1["urls"] - data3["urls"]
    only3 = data3["urls"] - data1["urls"]

    print("\n" + "=" * 55)
    print("SO SANH HAI DATASET")
    print("URL duy nhat co o ca hai file:", len(common))
    print("URL chi co trong Dataset 1:", len(only1))
    print("URL chi co trong Dataset 3:", len(only3))

    print("\nMot so URL chi co trong Dataset 1:")
    for url in sorted(only1)[:10]:
        print("-", url)

    print("\nMot so URL chi co trong Dataset 3:")
    for url in sorted(only3)[:10]:
        print("-", url)
