#!/usr/bin/env python3
"""Хук Claude Code (событие UserPromptSubmit) → удалить накопленные 🔔-уведомления Claude Code из Telegram.

При НОВОМ задании владельца висящее «🔔 needs permission / waiting» убирается из личной переписки —
чат не зарастает. Чистит ТОЛЬКО трекнутые 🔔 (их id в сторе); ✅/🔧/рабочие сообщения не трогает.
ВАЖНО: НИЧЕГО не печатает в stdout (иначе Claude Code добавит это в контекст промпта). Exit 0, не блокирует.
Зона 🟢 (конфиг агента; прод/Splinter/таблицы не трогает).
"""
import sys
sys.path.insert(0, "/root/turbobaby-manager-bot")

try:
    from notify import clear_notifications
    clear_notifications()
except Exception:
    pass   # хук не должен ронять отправку промпта ни при каких условиях
