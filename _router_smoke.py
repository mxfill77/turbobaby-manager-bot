"""Разовый smoke живого слоя 2 роутера (haiku через claude -p): один pc-текст, один vps-текст."""
import sys
sys.path.insert(0, "/root/turbobaby-manager-bot")
import os
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
import devbot as DB

print("pc-текст  →", DB._classify_theater("поправь тексты приветствий, которые бот шлёт новым клиентам"))
print("vps-текст →", DB._classify_theater("проверь, что утренняя сводка приходит вовремя"))
