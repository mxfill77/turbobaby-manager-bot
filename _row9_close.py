#!/usr/bin/env python3
"""Закрыть row9 аудит-листа (Bot Data, вкладка аудит — своя таблица бота, зелёная зона):
фикс задеплоен (beaadc4 + restart splinter), тайский блок квитанций несёт список работ."""
from bridge_client import BridgeClient

b = BridgeClient()
r = b.audit_update(row=9, status="resolved")
print("audit_update row=9:", r)
chk = b.audit_list()
for it in chk.get("items") or []:
    if it.get("_row") == 9:
        print("verify row9 status:", repr(it.get("status")))
