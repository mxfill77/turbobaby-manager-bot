#!/usr/bin/env python3
"""Читаю KB_MASTER §3-§5 и полный KB_review."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
from bridge_client import BridgeClient

c = BridgeClient(timeout=60)

r = c._call("read_doc", name="index")
txt = r.get("text", "") or ""

# Найти §3, §4, §5 и напечатать
lines = txt.split("\n")
in_section = False
section_count = 0
buf = []
for i, line in enumerate(lines):
    if "РАЗДЕЛ 3" in line or "═" * 10 in line and in_section:
        if "РАЗДЕЛ 3" in line:
            in_section = True
            section_count = 3
        elif in_section and "═" * 10 in line and section_count < 6:
            # Новая секция начинается?
            next_lines = lines[i:i+3]
            for nl in next_lines:
                for s in [4, 5, 6]:
                    if f"РАЗДЕЛ {s}" in nl:
                        section_count = s
                        break
        buf.append(line)
    elif "РАЗДЕЛ 4" in line or "РАЗДЕЛ 5" in line or "РАЗДЕЛ 6" in line:
        in_section = True
        buf.append(line)
        for s in [4, 5, 6]:
            if f"РАЗДЕЛ {s}" in line:
                section_count = s
    elif in_section:
        if section_count == 6:
            break
        buf.append(line)

# Проще: найти начало §3 и конец §6
start3 = None
start6 = None
for i, line in enumerate(lines):
    if "РАЗДЕЛ 3" in line and start3 is None:
        start3 = i
    if "РАЗДЕЛ 6" in line and start6 is None:
        start6 = i
        break

if start3 is not None and start6 is not None:
    section_text = "\n".join(lines[start3:start6])
    print(f"KB_MASTER §3–§5 (lines {start3}–{start6}):\n")
    print(section_text[:12000])
else:
    # fallback: найти по контексту
    for i, line in enumerate(lines):
        if "РАЗДЕЛ 3" in line:
            print(f"\n--- Строка {i}: {line}")
        if "РАЗДЕЛ 4" in line:
            print(f"--- Строка {i}: {line}")
        if "РАЗДЕЛ 5" in line:
            print(f"--- Строка {i}: {line}")
        if "РАЗДЕЛ 6" in line:
            print(f"--- Строка {i}: {line}")
    print("Общая длина:", len(lines), "строк")

print("\n\n=== ПОЛНЫЙ KB_review ===")
r2 = c._call("read_doc", name="review")
print(r2.get("text", ""))
