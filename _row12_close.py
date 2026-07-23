#!/usr/bin/env python3
"""Закрыть row12 аудита (contradiction: Инфо не показывал редуктор после «Принято») — фикс 211f34a.
Bot Data «аудит» = своя таблица бота, зелёная зона."""
import sys
sys.path.insert(0, "/root/turbobaby-manager-bot")
from bridge_client import BridgeClient

b = BridgeClient()
r = b.audit_update(row=12, status="resolved")
print("audit_update row=12:", r)
