#!/usr/bin/env python3
"""Добавить alias logdone в /root/.bashrc (однократно, без дублей)."""
ALIAS = "alias logdone='/root/turbobaby-manager-bot/venv/bin/python3 /root/turbobaby-manager-bot/cclog.py --raw'"
BASHRC = "/root/.bashrc"
with open(BASHRC, "r") as f:
    content = f.read()
if "alias logdone=" in content:
    print(f"alias logdone уже есть в {BASHRC}")
else:
    with open(BASHRC, "a") as f:
        f.write(f"\n{ALIAS}\n")
    print(f"alias logdone добавлен в {BASHRC}")
