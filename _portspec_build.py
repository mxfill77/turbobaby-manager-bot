#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Шаг 1/7 родитель 185: собрать docs/dec_port_spec.md из двух DONE-записей cc_log (дословно) + самопроверка."""
import sys

RAW = "/tmp/cclog_raw_185.txt"
OUT = "/root/turbobaby-manager-bot/docs/dec_port_spec.md"

with open(RAW, encoding="utf-8") as f:
    lines = f.read().split("\n")

# строки файла 1-based: 10..44 = запись 16:43 (часть 2/2), 45..93 = запись 16:38 (часть 1/2)
part2 = "\n".join(lines[9:44]).strip("\n")
part1 = "\n".join(lines[44:93]).strip("\n")

if not part2.startswith("DONE 2026-07-11 16:43 UTC"):
    sys.exit("ГРАНИЦА part2 сбита: " + part2[:80])
if not part1.startswith("DONE 2026-07-11 16:38 UTC"):
    sys.exit("ГРАНИЦА part1 сбита: " + part1[:80])
for nxt in ("DONE 2026-07-11 17:", "PLAN 2026-07-11 17:", "DONE 2026-07-11 16:26"):
    if nxt in part1 or nxt in part2:
        sys.exit("В извлечённое попала соседняя запись: " + nxt)

header = (
    "# ПОРТ-СПЕКА локального дирижёра (мозг декомпозера)\n"
    "\n"
    "Эталон для порта дирижёра-декомпозера в ПК-репо (D:\\turbobaby-bot).\n"
    "Источник: Brain cc_log (KB_claude_code_log, id 1464zaINaLnOwXMsHNaEyy-4FpuQCVTYF),\n"
    "записи DONE 2026-07-11 16:38 UTC (часть 1/2) и 16:43 UTC (часть 2/2) — ниже ДОСЛОВНО.\n"
    "Сохранено шагом 1/7 родителя 185 (скачано через Bridge read_doc name=cc_log).\n"
)

body = header + "\n---\n\n" + part1 + "\n\n---\n\n" + part2 + "\n"
with open(OUT, "w", encoding="utf-8") as f:
    f.write(body)

# самопроверка: обе записи в файле ЦЕЛИКОМ, посимвольно
with open(OUT, encoding="utf-8") as f:
    saved = f.read()
ok1 = part1 in saved
ok2 = part2 in saved
print(f"part1 (16:38): {len(part1)} chars, в файле целиком: {ok1}")
print(f"part2 (16:43): {len(part2)} chars, в файле целиком: {ok2}")
print(f"итог файл: {len(saved)} chars -> {OUT}")
if not (ok1 and ok2):
    sys.exit(1)
