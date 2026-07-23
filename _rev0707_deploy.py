#!/usr/bin/env python3
"""Ревизия 07.07: write_doc index + roadmap_master (POST) с post-write verify."""
import sys
sys.path.insert(0, "/root/turbobaby-manager-bot")
from bridge_client import BridgeClient

DOCS = {
    "index": {
        "file": "/root/turbobaby-manager-bot/_rev0707_index.new.md",
        "must": ["ЛЕСТНИЦА СТ1–СТ4\n  ЗАВЕРШЕНА НА VPS-ПОЛОСЕ", "МЕТА-ДИРИЖЁР КУСОК 2 — АДАПТАЦИЯ ПЛАНА (8ffbf7f",
                 "ПЕРВОЕ ЖИВОЕ РАСХОЖДЕНИЕ РЕЕСТРА (цепь 113, шаг 2)", "9b0a496",
                 "🧭 НОВЫЙ ГОРИЗОНТ ОСИ (кандидаты — ВЫБИРАЕТ ВЛАДЕЛЕЦ, решения на 07.07 НЕТ)",
                 "[✅ ЗАКРЫТ 06.07 ВЛАДЕЛЬЦЕМ] ФИНЗАПИСИ", "ФУНКЦИОНАЛЬНАЯ ОБКАТКА ДУМАТЕЛЯ (мета-дирижёр ст4"],
        "gone": ["[🔴 НОВЫЙ ХВОСТ 06.07]", "СЛЕДУЮЩИЕ КУСКИ: адаптация плана после шага"],
    },
    "roadmap_master": {
        "file": "/root/turbobaby-manager-bot/_rev0707_roadmap_master.new.md",
        "must": ["АКТУАЛИЗАЦИЯ 07.07.2026 ВЕЧЕР", "9b0a496", "FOREIGN_REPO_MARK",
                 "НОВЫЙ ГОРИЗОНТ ОСИ (кандидаты, ВЫБИРАЕТ ВЛАДЕЛЕЦ)"],
        "gone": [],
    },
}

c = BridgeClient(timeout=180)
fails = 0
for key, spec in DOCS.items():
    text = open(spec["file"]).read()
    r = c.write_doc(text, name=key)
    if not r.get("ok"):
        print(f"{key}: WRITE FAIL {r}"); fails += 1; continue
    back = c._call("read_doc", name=key)
    got = (back.get("text") or back.get("content") or "") if back.get("ok") else ""
    ok_len = len(got) == len(text)
    missing = [m for m in spec["must"] if m not in got]
    lingering = [g for g in spec["gone"] if g in got]
    verdict = "VERIFY OK" if (ok_len and not missing and not lingering) else "VERIFY FAIL"
    if verdict != "VERIFY OK":
        fails += 1
    print(f"{key}: write ok, sent={len(text)} readback={len(got)} len_match={ok_len} "
          f"missing={missing} lingering={lingering} → {verdict}")
sys.exit(1 if fails else 0)
