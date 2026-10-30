import csv
from pathlib import Path
from collections import Counter

files = [
    "osm_churches.csv",
    "tgpsaigon_parishes.csv",
    "tgpsaigon_mass_times.csv",
]

for filename in files:
    path = Path(filename)

    print("\n" + "=" * 65)
    print("FILE:", filename)

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        columns = reader.fieldnames or []
        rows = list(reader)

    print("Columns:", columns)
    print("Data rows:", len(rows))

    name_column = next(
        (
            c for c in columns
            if c.strip().lower().replace(" ", "_") == "parish_name"
        ),
        None
    )

    if name_column is None:
        name_column = next(
            (
                c for c in columns
                if c.strip().lower() in ("name", "church_name")
            ),
            None
        )

    if name_column is None:
        print("Name column: NOT FOUND")
        continue

    names = [(row.get(name_column) or "").strip() for row in rows]
    nonempty = [name for name in names if name]
    counts = Counter(nonempty)

    print("Name column:", name_column)
    print("Missing/blank names:", len(names) - len(nonempty))
    print("Unique exact names:", len(counts))
    print("Duplicate name groups:", sum(n > 1 for n in counts.values()))

    print("Sample names:")
    for name in list(dict.fromkeys(nonempty))[:15]:
        print(" -", name)

    duplicates = [(name, count) for name, count in counts.items() if count > 1]
    if duplicates:
        print("Duplicate examples:")
        for name, count in duplicates[:10]:
            print(" -", repr(name), "(count:", count, ")")

