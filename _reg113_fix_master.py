#!/usr/bin/env python3
"""Родитель 113 шаг 2, часть Б: точность KB_MASTER — переатрибуция f926733.
Было: «ПК-полоса — кондуктор pc_orchestrator (f926733, ПК-репо).»
Факт (сверка с cowork_log): f926733 = коммит USERBOT-репо (suggest на Fable 5 + кондуктор,
Dispatch 07.07 05:30), а кондуктор pc_orchestrator заложен при стройке 05.07 без отдельного коммита.
Снимок ДО правки: /tmp/kb_master_snapshot_113.txt (уже снят). Точечная замена + post-write verify.
Зона: живой свод Brain через write_doc (KB_MASTER ведёт CC по правилу гигиены мозга)."""
import sys
sys.path.insert(0, "/root/turbobaby-manager-bot")
from dotenv import load_dotenv
load_dotenv("/root/turbobaby-manager-bot/.env")
from bridge_client import BridgeClient

OLD = ("CLI сам фолбэчит внутри одного вызова, без двойного исполнения (0bc9187); ПК-полоса — кондуктор\n"
       "    pc_orchestrator (f926733, ПК-репо).")
NEW = ("CLI сам фолбэчит внутри одного вызова, без двойного исполнения (0bc9187); ПК-полоса — кондуктор\n"
       "    pc_orchestrator (Fable5→Opus4.8 заложен при стройке 05.07, отдельного коммита в manager-bot нет);\n"
       "    userbot suggest на Fable 5 + кондуктор — f926733 (клиентский контур, ПК-репо userbot, Dispatch 07.07 05:30).")

c = BridgeClient(timeout=45)
r = c._call("read_doc", name="index")
if not r.get("ok"):
    print("READ FAIL:", r); sys.exit(1)
txt = r.get("text", "") or ""

# сверка со снимком (защита от гонки: карта не менялась с разведки)
snap = open("/tmp/kb_master_snapshot_113.txt", encoding="utf-8").read()
if txt != snap:
    print(f"WARN: карта изменилась после снимка (snap={len(snap)}, now={len(txt)}) — проверяю фрагмент")

n = txt.count(OLD)
if n != 1:
    print(f"ABORT: старый фрагмент найден {n} раз (ждали ровно 1) — вслепую не пишем"); sys.exit(1)

new_txt = txt.replace(OLD, NEW, 1)
w = c.write_doc(text=new_txt, name="index")
if not w.get("ok"):
    print("WRITE FAIL:", w); sys.exit(1)
print(f"write ok: {len(txt)} -> {len(new_txt)} code points (delta {len(new_txt)-len(txt)})")

# post-write verify: перечитать, старого нет, новое есть, длина сходится
v = c._call("read_doc", name="index")
if not v.get("ok"):
    print("VERIFY READ FAIL:", v); sys.exit(1)
vt = v.get("text", "") or ""
ok_old = OLD not in vt
ok_new = ("pc_orchestrator (Fable5" in vt) and ("f926733 (клиентский контур, ПК-репо userbot" in vt)
ok_len = len(vt) == len(new_txt)
print(f"verify: old_gone={ok_old} new_present={ok_new} len_match={ok_len} (live={len(vt)})")
sys.exit(0 if (ok_old and ok_new and ok_len) else 1)
