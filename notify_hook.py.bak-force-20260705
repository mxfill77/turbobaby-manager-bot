#!/usr/bin/env python3
"""Хук Claude Code (событие Notification) → пуш Филиппу в Telegram.

Зовётся штатным механизмом хуков Claude Code, когда агент ОСТАНОВИЛСЯ И ЖДЁТ пользователя:
(а) запрос разрешения на инструмент (ask-лист), (б) простой в ожидании ввода (~60с).
Хук передаёт JSON в stdin (поле message). Переиспользуем notify.py как канал (личка Филиппа).
Штатная замена ненадёжного echo BEL. Зона 🟢 (конфиг агента, прод/Splinter/таблицы не трогает).
"""
import sys, json
sys.path.insert(0, "/root/turbobaby-manager-bot")
from notify import notify

try:
    data = json.load(sys.stdin)
except Exception:
    data = {}
msg = (data.get("message") or "ждёт тебя в Termux")
# track=True: удалить ПРЕДЫДУЩИЕ 🔔 и сохранить id нового → в личке висит максимум ОДНО уведомление.
notify("🔔 Claude Code: " + msg, track=True)
