"""Chạy bộ câu hỏi kiểm thử. Đáp án kỳ vọng tính bằng SQL viết tay trên DB hiện tại.

Chạy từ thư mục gốc dự án: python tests\\eval\\eval.py [--model qwen2.5:7b] [--llm-intro]
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.stdout.reconfigure(encoding="utf-8")

from src.bot import answer
from src.config import OLLAMA_MODEL


def check(case: dict, r) -> list[str]:
    errs = []
    if r.status != case["status"]:
        errs.append(f"status {r.status} != {case['status']}")
    if "churches" in case:
        got = sorted(h.parish_name for h in r.hits)
        if got != sorted(case["churches"]):
            errs.append(f"nhà thờ {got} != {sorted(case['churches'])}")
    for s in case.get("contains", []):
        if s not in r.text:
            errs.append(f"thiếu “{s}”")
    for s in case.get("not_contains", []):
        if s in r.text:
            errs.append(f"không được có “{s}”")
    return errs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=OLLAMA_MODEL)
    ap.add_argument("--llm-intro", action="store_true")
    args = ap.parse_args()

    cases = json.loads((Path(__file__).parent / "questions.json").read_text(encoding="utf-8"))
    passed, times = 0, []
    for i, case in enumerate(cases, 1):
        r = answer(case["q"], use_llm_intro=args.llm_intro, model=args.model)
        errs = check(case, r)
        passed += not errs
        times.append(r.debug.get("t_total", 0))
        print(f"[{'PASS' if not errs else 'FAIL'}] {i:2}. {case['q']}  ({r.debug.get('t_total')}s)")
        if errs:
            print("       ", "; ".join(errs))
            print("        bộ lọc:", json.dumps(r.debug.get("final"), ensure_ascii=False))
    print(f"\nCâu đơn: đúng {passed}/{len(cases)} ({passed / len(cases):.0%}); "
          f"thời gian trung bình {sum(times) / len(times):.1f}s/câu, model {args.model}")

    convs = json.loads((Path(__file__).parent / "conversations.json").read_text(encoding="utf-8"))
    t_pass = t_total = 0
    for conv in convs:
        print(f"\n# {conv['name']}")
        ctx = None
        for case in conv["turns"]:
            r = answer(case["q"], use_llm_intro=args.llm_intro, model=args.model, context=ctx)
            ctx = r.context
            errs = check(case, r)
            t_pass += not errs
            t_total += 1
            print(f"[{'PASS' if not errs else 'FAIL'}]   {case['q']}")
            if errs:
                print("       ", "; ".join(errs))
                print("        bộ lọc:", json.dumps(r.debug.get("final"), ensure_ascii=False, default=str))
    print(f"\nHội thoại nhiều lượt: đúng {t_pass}/{t_total} lượt ({t_pass / t_total:.0%})")


if __name__ == "__main__":
    main()
