from __future__ import annotations

import csv
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent
DATA = BASE / "dataset"
OUT = BASE / "reports" / "osm_match_audit"
INPUTS = {
    "osm": DATA / "osm_churches.csv",
    "parishes": DATA / "tgpsaigon_parishes.csv",
    "mass": DATA / "tgpsaigon_mass_times.csv",
}


def read_rows(path: Path) -> tuple[list[str], list[list[str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            return [], []
        return header, list(reader)


def norm(value: str, strip_church_prefix: bool = False) -> str:
    value = value.strip().casefold()
    if strip_church_prefix:
        value = re.sub(r"^nhà\s+thờ\s+", "", value, flags=re.IGNORECASE)
    value = re.sub(r"[\s\.,;:!?()\[\]{}'’\"`´/\\_-]+", " ", value)
    return " ".join(value.split())


def write_csv(path: Path, header: list[str], rows: list[list[object]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def issue(rows: list[list[object]], file: str, line: object, column: object, severity: str, description: str, recommendation: str) -> None:
    rows.append([file, line, column, severity, description, recommendation])


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    missing = [str(p.relative_to(BASE)) for p in INPUTS.values() if not p.is_file()]
    if missing:
        raise SystemExit("Không tìm thấy file đầu vào: " + ", ".join(missing))
    OUT.mkdir(parents=True, exist_ok=True)
    issues: list[list[object]] = []
    headers: dict[str, list[str]] = {}
    data: dict[str, list[list[str]]] = {}
    for key, path in INPUTS.items():
        try:
            headers[key], data[key] = read_rows(path)
        except (OSError, UnicodeError, csv.Error) as exc:
            raise SystemExit(f"Không đọc được {path.relative_to(BASE)}: {exc}") from exc
        if not headers[key]:
            raise SystemExit(f"File không có header: {path.relative_to(BASE)}")
        if len(set(headers[key])) != len(headers[key]):
            repeated = [name for name, count in Counter(headers[key]).items() if count > 1]
            for name in repeated:
                positions = [str(i + 1) for i, h in enumerate(headers[key]) if h == name]
                issue(issues, path.name, 1, ",".join(positions), "high", f"Header trùng tên {name!r} ở các cột 1-based {', '.join(positions)}; đọc bằng vị trí cột.", "Xác nhận ý nghĩa từng vị trí và đổi tên cột trong giai đoạn xử lý riêng.")
        widths = Counter(map(len, data[key]))
        for width, count in widths.items():
            if width != len(headers[key]):
                issue(issues, path.name, "multiple", "row_width", "high", f"{count} dòng có {width} cột, header có {len(headers[key])} cột.", "Kiểm tra các dòng CSV lỗi cấu trúc trước khi dùng.")

    def indexes(key: str, names: list[str]) -> dict[str, int]:
        h = headers[key]
        missing_names = [n for n in names if n not in h]
        if missing_names:
            raise SystemExit(f"Thiếu cột trong {INPUTS[key].name}: {', '.join(missing_names)}")
        return {n: h.index(n) for n in names}

    oi = indexes("osm", ["parish_name", "osm_id", "latitude", "longitude"])
    pi = indexes("parishes", ["deanery_name", "parish_name", "parish_address", "parish_url", "verification_status"])
    mh = headers["mass"]
    if mh.count("parish_url") != 2:
        issue(issues, INPUTS["mass"].name, 1, "header", "high", f"Kỳ vọng có 2 cột parish_url, thực tế có {mh.count('parish_url')}.", "Xác minh cấu trúc nguồn; không gán ngữ nghĩa URL theo tên header.")
    expected_mass = ["parish_name", "day_of_week", "mass_time", "verification_status"]
    if any(n not in mh for n in expected_mass):
        raise SystemExit("Thiếu một trong các cột cần thiết của file lịch lễ.")
    mi = {n: mh.index(n) for n in expected_mass}
    url_positions = [i for i, name in enumerate(mh) if name == "parish_url"]
    url_values = {i: Counter(r[i] for r in data["mass"] if len(r) > i and r[i].strip()) for i in url_positions}
    # Raw values are preserved by position, but duplicate headers do not establish semantic roles.
    # Do not infer which URL is the source URL from URL shape or frequency alone.
    source_col: int | None = None
    if len(url_positions) == 2:
        issue(issues, INPUTS["mass"].name, 1, "parish_url columns " + ",".join(str(i + 1) for i in url_positions), "high", "Không xác định được cột nào là URL nguồn lịch lễ chỉ từ header trùng và giá trị; hai vị trí được giữ nguyên, không chọn đoán.", "Xác nhận ý nghĩa theo nguồn tạo dữ liệu; sau đó đổi cột URL nguồn thành parish_mass_time_url ở bước riêng.")

    # Basic input checks and indexes.
    def col_counts(key: str, col: int, label: str, file: str) -> tuple[int, int, int]:
        vals = [r[col].strip() if len(r) > col else "" for r in data[key]]
        missing_count = sum(not v for v in vals)
        counts = Counter(v for v in vals if v)
        duplicate_groups = sum(1 for c in counts.values() if c > 1)
        duplicate_rows = sum(c - 1 for c in counts.values() if c > 1)
        if missing_count:
            issue(issues, file, "multiple", label, "medium", f"{missing_count} dòng có {label} trống.", "Bổ sung/chốt từ nguồn ở bước dữ liệu riêng; không suy diễn.")
        if duplicate_groups:
            issue(issues, file, "multiple", label, "low", f"{duplicate_groups} nhóm tên trùng ({duplicate_rows} dòng dư so với tên duy nhất).", "Kiểm tra khả năng tên hợp lệ dùng chung; không tự gộp.")
        return missing_count, len(counts), duplicate_groups

    name_stats = {}
    name_stats["osm"] = col_counts("osm", oi["parish_name"], "parish_name", INPUTS["osm"].name)
    name_stats["parishes"] = col_counts("parishes", pi["parish_name"], "parish_name", INPUTS["parishes"].name)
    name_stats["mass"] = col_counts("mass", mi["parish_name"], "parish_name", INPUTS["mass"].name)

    osm = data["osm"]
    parishes = data["parishes"]
    masses = data["mass"]
    for label, idx in [("osm_id", oi["osm_id"]), ("latitude", oi["latitude"]), ("longitude", oi["longitude"])]:
        for n, row in enumerate(osm, start=2):
            v = row[idx].strip() if len(row) > idx else ""
            bad = not v
            if label in ("latitude", "longitude") and v:
                try:
                    x = float(v)
                    bad = not (-90 <= x <= 90 if label == "latitude" else -180 <= x <= 180)
                except ValueError:
                    bad = True
            if bad:
                issue(issues, INPUTS["osm"].name, n, label, "high", f"Giá trị {label} thiếu hoặc không hợp lệ: {v!r}.", "Đối chiếu nguồn OSM; không tự điền hoặc sửa.")
    osm_id_values = [r[oi["osm_id"]].strip() for r in osm if len(r) > oi["osm_id"] and r[oi["osm_id"]].strip()]
    for val, count in Counter(osm_id_values).items():
        if count > 1:
            issue(issues, INPUTS["osm"].name, "multiple", "osm_id", "high", f"osm_id {val!r} xuất hiện {count} lần.", "Kiểm tra tính duy nhất của ID nguồn.")

    p_by_norm: dict[str, list[int]] = defaultdict(list)
    p_by_prefix: dict[str, list[int]] = defaultdict(list)
    for i, r in enumerate(parishes):
        name = r[pi["parish_name"]].strip() if len(r) > pi["parish_name"] else ""
        if name:
            p_by_norm[norm(name)].append(i)
            p_by_prefix[norm(name, True)].append(i)
    o_by_key: dict[str, list[int]] = defaultdict(list)
    for i, r in enumerate(osm):
        name = r[oi["parish_name"]].strip() if len(r) > oi["parish_name"] else ""
        if name:
            o_by_key[norm(name)].append(i)
            o_by_key[norm(name, True)].append(i)

    # Candidate relationships, including safe normalized and prefix suggestions.
    candidates: dict[int, list[tuple[int, str]]] = {}
    for oirow, r in enumerate(osm):
        name = r[oi["parish_name"]].strip() if len(r) > oi["parish_name"] else ""
        key, prefix_key = norm(name), norm(name, True)
        cand: dict[int, str] = {}
        for j in p_by_norm.get(key, []):
            cand[j] = "exact" if name == parishes[j][pi["parish_name"]].strip() else "normalized"
        for j in p_by_prefix.get(prefix_key, []):
            cand.setdefault(j, "prefix")
        candidates[oirow] = sorted(cand.items())

    # Reverse candidate count means a seemingly unique parish can still be shared by OSM records.
    reverse_osm: dict[int, set[int]] = defaultdict(set)
    for oirow, cands in candidates.items():
        for j, _ in cands:
            reverse_osm[j].add(oirow)

    osm_status: dict[int, str] = {}
    chosen: dict[int, int] = {}
    reasons: dict[int, str] = {}
    manual_rows: list[list[object]] = []
    match_rows: list[list[object]] = []
    for i, r in enumerate(osm):
        name = r[oi["parish_name"]].strip() if len(r) > oi["parish_name"] else ""
        cands = candidates[i]
        possible_multi = len(cands) > 1 or any(len(reverse_osm[j]) > 1 for j, _ in cands)
        if not cands:
            status, reason = "no_match", "Không tìm thấy ứng viên theo tên chính xác, chuẩn hóa an toàn hoặc bỏ tiền tố Nhà thờ."
        elif possible_multi:
            status, reason = "needs_manual_review", "Quan hệ tên không duy nhất: nhiều ứng viên TGPSG hoặc một ứng viên chia sẻ với nhiều nhà thờ OSM."
        else:
            j, kind = cands[0]
            if kind == "prefix":
                status, reason = "normalized_match", "Tên khớp sau khi bỏ tiền tố Nhà thờ và chuẩn hóa chữ hoa/thường, khoảng trắng, dấu câu; ứng viên duy nhất theo dữ liệu tên."
            elif kind == "normalized":
                status, reason = "normalized_match", "Tên khớp sau chuẩn hóa chữ hoa/thường, khoảng trắng và dấu câu; ứng viên duy nhất theo dữ liệu tên."
            else:
                status, reason = "exact_match", "Tên khớp nguyên văn; ứng viên duy nhất theo dữ liệu tên."
            chosen[i] = j
        osm_status[i], reasons[i] = status, reason
        if status == "needs_manual_review":
            related = []
            for j, kind in cands:
                pr = parishes[j]
                related.append(f"{pr[pi['parish_name']]} (deanery={pr[pi['deanery_name']]}; address={pr[pi['parish_address']]}; candidate={kind}; linked_OSM_count={len(reverse_osm[j])})")
            manual_rows.append([name, " | ".join(x.split(" (", 1)[0] for x in related), " | ".join(parishes[j][pi["parish_address"]] for j, _ in cands), " | ".join(parishes[j][pi["deanery_name"]] for j, _ in cands), r[oi["osm_id"]], r[oi["latitude"]], r[oi["longitude"]], reason, " || ".join(related)])
        j = chosen.get(i)
        mass_rows = [mr for mr in masses if j is not None and len(mr) > mi["parish_name"] and norm(mr[mi["parish_name"]]) == norm(parishes[j][pi["parish_name"]])]
        days = sorted({mr[mi["day_of_week"]].strip() for mr in mass_rows if mr[mi["day_of_week"]].strip()})
        mass_status = "not_linked_unresolved_parish" if status in ("needs_manual_review", "no_match") else ("has_mass_times" if mass_rows else "no_mass_time_record")
        if j is None:
            tname = deanery = address = ""
        else:
            tname, deanery, address = (parishes[j][pi[k]] for k in ("parish_name", "deanery_name", "parish_address"))
        match_rows.append([r[oi["osm_id"]] if len(r)>oi["osm_id"] else "", name, r[oi["latitude"]] if len(r)>oi["latitude"] else "", r[oi["longitude"]] if len(r)>oi["longitude"] else "", status, tname, deanery, address, reason, mass_status, len(mass_rows), reason if status == "needs_manual_review" else ""])

    # TGPSG status: exact/normalized confident links only; unresolved candidates remain review.
    parish_to_osm: dict[int, list[int]] = defaultdict(list)
    for oirow, j in chosen.items():
        parish_to_osm[j].append(oirow)
    unmatched_rows = []
    tgpsg_unmatched_count = 0
    for j, r in enumerate(parishes):
        name = r[pi["parish_name"]].strip() if len(r) > pi["parish_name"] else ""
        potential = sorted({oirow for oirow, cands in candidates.items() if any(j2 == j for j2, _ in cands)})
        if parish_to_osm.get(j):
            continue
        tgpsg_unmatched_count += 1
        status = "needs_manual_review" if potential else "no_match"
        reason = "Có quan hệ tên ứng viên chưa thể chốt do mơ hồ." if potential else "Không tìm thấy ứng viên OSM theo tên chính xác, chuẩn hóa an toàn hoặc bỏ tiền tố Nhà thờ."
        related = " | ".join(f"{osm[k][oi['parish_name']]} [{osm[k][oi['osm_id']]}]" for k in potential)
        unmatched_rows.append([name, r[pi["deanery_name"]], r[pi["parish_address"]], r[pi["parish_url"]], status, reason, related])
        if potential:
            for k in potential:
                issue(issues, INPUTS["parishes"].name, j+2, "parish_name", "medium", f"Tên TGPSG {name!r} có ứng viên OSM chưa chốt: {related}.", "Đối chiếu thủ công bằng địa chỉ/giáo hạt/tọa độ nếu có.")

    # Audit schedule by linked OSM only; mass parish names must uniquely identify the linked TGPSG row.
    mass_audit = []
    for i, r in enumerate(osm):
        j = chosen.get(i)
        linked_mass = [mr for mr in masses if j is not None and len(mr) > mi["parish_name"] and norm(mr[mi["parish_name"]]) == norm(parishes[j][pi["parish_name"]])]
        mass_status = "not_linked_unresolved_parish" if j is None else ("has_mass_times" if linked_mass else "no_mass_time_record")
        days = sorted({mr[mi["day_of_week"]].strip() for mr in linked_mass if mr[mi["day_of_week"]].strip()})
        urls = sorted({mr[source_col].strip() for mr in linked_mass if source_col is not None and len(mr) > source_col and mr[source_col].strip()})
        source_url = urls[0] if len(urls) == 1 else ("UNRESOLVED: duplicate parish_url header; source URL position not established" if source_col is None else ("UNRESOLVED: multiple source URLs" if urls else ""))
        mass_audit.append([r[oi["osm_id"]], r[oi["parish_name"]], mass_status, len(linked_mass), ";".join(days), source_url, reasons[i]])

    # Duplicate names and potential collisions are explicit quality issues.
    for key, idx, file in [("osm", oi["parish_name"], INPUTS["osm"].name), ("parishes", pi["parish_name"], INPUTS["parishes"].name)]:
        groups: dict[str, list[int]] = defaultdict(list)
        for n, r in enumerate(data[key], start=2):
            val = r[idx].strip() if len(r) > idx else ""
            if val: groups[val].append(n)
        for val, lines in groups.items():
            if len(lines) > 1:
                issue(issues, file, ",".join(map(str, lines)), "parish_name", "medium", f"Tên trùng {val!r} xuất hiện {len(lines)} lần; không tự gộp.", "Đánh giá địa chỉ/tọa độ và danh tính riêng từng bản ghi.")
    for i, cands in candidates.items():
        if len(cands) > 1 or any(len(reverse_osm[j]) > 1 for j, _ in cands):
            issue(issues, INPUTS["osm"].name, i+2, "parish_name", "high", f"Quan hệ ghép tên mơ hồ cho {osm[i][oi['parish_name']]!r}; candidates: " + " | ".join(parishes[j][pi['parish_name']] for j, _ in cands), "Xem manual_review.csv; quyết định bằng thông tin địa chỉ/giáo hạt/vị trí.")

    write_csv(OUT / "osm_match_report.csv", ["osm_id","osm_parish_name","latitude","longitude","match_status","tgpsg_parish_name","tgpsg_deanery_name","tgpsg_parish_address","match_reason","mass_time_status","mass_time_row_count","manual_review_reason"], match_rows)
    write_csv(OUT / "unmatched_tgpsg_parishes.csv", ["tgpsg_parish_name","deanery_name","parish_address","parish_url","match_status","match_reason","related_osm_candidates"], unmatched_rows)
    write_csv(OUT / "manual_review.csv", ["osm_parish_name","tgpsg_candidate_names","tgpsg_candidate_addresses","tgpsg_candidate_deaneries","osm_id","latitude","longitude","review_reason","related_candidates"], manual_rows)
    write_csv(OUT / "mass_time_audit.csv", ["osm_id","osm_parish_name","mass_time_status","mass_time_row_count","days_with_mass_times","source_url","match_reason"], mass_audit)
    write_csv(OUT / "data_quality_issues.csv", ["file_name","line_number_or_scope","column_or_index","severity","description","recommended_action"], issues)

    exact = sum(s == "exact_match" for s in osm_status.values())
    normalized = sum(s == "normalized_match" for s in osm_status.values())
    review = sum(s == "needs_manual_review" for s in osm_status.values())
    no_match = sum(s == "no_match" for s in osm_status.values())
    linked_no_mass = sum(1 for i in chosen if not any(len(mr)>mi["parish_name"] and norm(mr[mi["parish_name"]]) == norm(parishes[chosen[i]][pi["parish_name"]]) for mr in masses))
    summary = [
        "CatholicNearMe — Báo cáo audit đối chiếu OSM/TGPSG",
        "Phạm vi: chỉ kiểm tra tên và trường dữ liệu; chưa xác minh thực tế địa điểm/giờ lễ.",
        "",
        "Đầu vào (encoding đọc: utf-8-sig):",
        f"- {INPUTS['osm'].relative_to(BASE)}: {len(osm)} dòng; {name_stats['osm'][1]} tên không trống duy nhất; {name_stats['osm'][0]} tên trống; {name_stats['osm'][2]} nhóm tên trùng.",
        f"- {INPUTS['parishes'].relative_to(BASE)}: {len(parishes)} dòng; {name_stats['parishes'][1]} tên không trống duy nhất; {name_stats['parishes'][0]} tên trống; {name_stats['parishes'][2]} nhóm tên trùng.",
        f"- {INPUTS['mass'].relative_to(BASE)}: {len(masses)} dòng; {name_stats['mass'][1]} tên không trống duy nhất; {name_stats['mass'][0]} tên trống; {name_stats['mass'][2]} nhóm tên trùng.",
        f"- Header lịch lễ thô: {mh!r}; parish_url ở cột 2 và 5 (1-based). URL cột 2 có {len(url_values[url_positions[0]]) if url_positions else 0} giá trị duy nhất; cột 5 có {len(url_values[url_positions[1]]) if len(url_positions)>1 else 0}. Không gán vai trò URL nguồn cho vị trí nào do header trùng.",
        "",
        "Kết quả ghép từ góc nhìn danh sách chuẩn OSM:",
        f"- exact_match: {exact}", f"- normalized_match: {normalized}", f"- needs_manual_review: {review}", f"- no_match: {no_match}",
        f"- Nhà thờ ghép chắc chắn với danh mục nhưng không có dòng lịch lễ tương ứng theo tên: {linked_no_mass}",
        f"- Bản ghi danh mục TGPSG chưa ghép chắc chắn với OSM: {tgpsg_unmatched_count} (xem unmatched_tgpsg_parishes.csv; gồm cả needs_manual_review và no_match).",
        f"- Vấn đề dữ liệu được ghi nhận: {len(issues)} dòng trong data_quality_issues.csv; trường hợp cần xem thủ công: {len(manual_rows)} dòng OSM trong manual_review.csv.",
        "",
        "Hạn chế và lưu ý:",
        "- Match tự động chỉ dựa trên tên nguyên văn hoặc chuẩn hóa chữ hoa/thường, khoảng trắng, dấu câu; thử bỏ tiền tố Nhà thờ chỉ tạo match khi quan hệ là duy nhất.",
        "- Không dùng so sánh không dấu hoặc fuzzy để tự xác nhận; địa chỉ/tọa độ không được dùng để suy diễn khi thiếu.",
        "- Lịch lễ chỉ được liên kết qua bản ghi danh mục TGPSG đã ghép chắc chắn. Tên trùng trong lịch là nhiều dòng giờ lễ, không được coi là lỗi.",
        "- Header parish_url bị trùng. Phân bố URL thô khác nhau giữa hai vị trí nhưng không đủ để xác nhận ngữ nghĩa; source_url được ghi unresolved và không đoán cột. Cần chủ dữ liệu xác nhận cột sẽ mang tên parish_mass_time_url.",
        "- Không có tuyên bố xác minh thực tế nhà thờ hoặc giờ lễ. File nguồn không bị sửa.",
    ]
    (OUT / "summary.txt").write_text("\n".join(summary) + "\n", encoding="utf-8")
    print("\n".join(summary))
    print(f"\nĐã tạo 6 báo cáo trong {OUT.relative_to(BASE)}")


if __name__ == "__main__":
    main()

