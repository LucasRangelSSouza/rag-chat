"""Fixed 60-question evaluation of the live chat: 20 SIOPE (SQL), 20 PNCP contracts (SQL), 20 PNCP notices (retrieval).

  python qa60.py ask   questions.json answers.json         # calls the public API, one question at a time
  python qa60.py grade questions.json answers.json truth.json records.json report.json

The expected answers (truth.json) come from SQL written before the run (truth_sql in questions.json); records.json holds the
state and object of every notice the chat cited, read from the database after the run. Grading is mechanical:
- number: some number in the answer is within 0.5% of the truth (counts must match exactly);
- name: the expected name appears in the answer, compared without accents and case;
- records: at least one notice is cited and every cited notice matches the state and the terms of the question.
"""
from __future__ import annotations

import json
import re
import sys
import time
import unicodedata
import urllib.request

API = "https://rag.rangeltech.net/api/answer"


def fold(text: str) -> str:
    return unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode().upper()


def ask(questions_path: str, out_path: str) -> None:
    out = []
    for q in json.load(open(questions_path, encoding="utf-8")):
        body = json.dumps({"question": q["question"], "corpora": q["bases"]}).encode()
        start = time.perf_counter()
        try:
            req = urllib.request.Request(API, data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=300) as resp:
                answer = json.load(resp)
        except Exception as exc:  # recorded as a failure, the run goes on
            answer = {"status": "error", "answer": str(exc), "citations": []}
        answer["seconds"] = round(time.perf_counter() - start, 1)
        out.append({"id": q["id"], **answer})
        print(q["id"], answer["status"], answer["seconds"], "s", flush=True)
        json.dump(out, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def numbers(text: str) -> list[float]:
    """Numbers as Brazilian or English text writes them: 5.565 / 1.234,56 / 12,5% / 1,234.56 / 3.2 million."""
    found = []
    for raw in re.findall(r"\d[\d.,]*", text):
        raw = raw.rstrip(".,")
        candidates = {raw.replace(".", "").replace(",", "."), raw.replace(",", "")}
        for c in candidates:
            try:
                found.append(float(c))
            except ValueError:
                pass
    for value, unit in re.findall(r"(\d[\d.,]*)\s*(mil|milh[oõ]es|milh[aã]o|bilh[oõ]es|bilh[aã]o|thousand|million|billion)", text, re.I):
        scale = {"mil": 1e3, "thousand": 1e3}.get(unit.lower(), 1e6 if unit.lower().startswith(("milh", "mill")) else 1e9)
        for c in {value.replace(".", "").replace(",", "."), value.replace(",", "")}:
            try:
                found.append(float(c) * scale)
            except ValueError:
                pass
    return found


def grade(questions_path, answers_path, truth_path, records_path, out_path) -> None:
    questions = {q["id"]: q for q in json.load(open(questions_path, encoding="utf-8"))}
    answers = {a["id"]: a for a in json.load(open(answers_path, encoding="utf-8"))}
    truth = json.load(open(truth_path, encoding="utf-8"))
    records = json.load(open(records_path, encoding="utf-8"))
    rows = []
    for qid, q in questions.items():
        a = answers.get(qid, {"status": "missing", "answer": "", "citations": []})
        text, ok, why = a.get("answer", ""), False, ""
        if q["kind"] == "number":
            t = float(truth[qid])
            exact = float(t).is_integer() and "count" in q["truth_sql"].lower()
            hits = [n for n in numbers(text) if (n == t if exact else abs(n - t) <= max(abs(t) * 0.005, 0.01))]
            ok, why = bool(hits), f"truth {t}"
        elif q["kind"] == "name":
            ok, why = fold(truth[qid]) in fold(text), f"truth {truth[qid]}"
        else:
            ids = [rid for c in a.get("citations", []) for rid in c.get("record_ids", [])]
            check = q["check"]
            bad = []
            for rid in ids:
                rec = records.get(rid)
                if not rec:
                    bad.append(rid); continue
                obj = fold(rec["objeto"])
                if check.get("uf") and rec["uf"] != check["uf"]:
                    bad.append(rid); continue
                if check.get("terms") and not all(t in obj for t in check["terms"]):
                    bad.append(rid); continue
                if check.get("terms_any") and not any(t in obj for t in check["terms_any"]):
                    bad.append(rid); continue
                if check.get("terms_any2") and not any(t in obj for t in check["terms_any2"]):
                    bad.append(rid)
            ok = bool(ids) and not bad
            why = f"{len(ids)} cited, {len(bad)} off target"
        rows.append({"id": qid, "base": q["bases"][0], "kind": q["kind"], "status": a.get("status"), "ok": ok, "why": why,
                     "seconds": a.get("seconds"), "cached": a.get("cached", False)})
    summary = {}
    for r in rows:
        s = summary.setdefault(r["base"], {"n": 0, "ok": 0})
        s["n"] += 1
        s["ok"] += r["ok"]
    json.dump({"summary": summary, "rows": rows}, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for base, s in summary.items():
        print(f"{base}: {s['ok']}/{s['n']}")
    for r in rows:
        if not r["ok"]:
            print("  miss", r["id"], r["status"], r["why"])


if __name__ == "__main__":
    {"ask": ask, "grade": grade}[sys.argv[1]](*sys.argv[2:])
