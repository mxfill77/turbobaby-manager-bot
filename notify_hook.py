#!/usr/bin/env python3
"""Хук Claude Code (событие Notification) → пуш Филиппу в Telegram (+ termux-notification, если есть).

Зовётся штатным механизмом хуков Claude Code, когда агент ОСТАНОВИЛСЯ И ЖДЁТ пользователя:
(а) запрос разрешения на инструмент (ask-лист / дефолт-prompt), (б) простой в ожидании ввода (~60с).
Хук передаёт JSON в stdin (message, transcript_path). Переиспользуем notify.py как канал (личка Филиппа).

UX-фикс 08.07.2026 (висящий промпт): «🔔 needs your permission» не говорил, ЧТО именно висит —
Филипп открывал Termux вслепую. Теперь на permission-ожидании хук достаёт из транскрипта сессии
ПОСЛЕДНИЙ tool_use (команду Bash / файл Edit-Write) и шлёт
    «⏳ Termux ждёт подтверждения: <команда>»
— владелец из пуша видит, что дакать, ДО открытия терминала. Извлечение best-effort: транскрипт
нечитаем/формат иной → прежний текст события (не хуже старого поведения). Вторым каналом, если на
хосте стоит Termux:API (termux-notification в PATH), дублируем локальным уведомлением — на VPS
бинаря нет, ветка молча пропускается. Зона 🟢 (конфиг агента, прод/Splinter/таблицы не трогает).
Регресс: tests/test_notify_hook_prompt.py (в гейте).
"""
import sys, os, json, shutil, subprocess
sys.path.insert(0, "/root/turbobaby-manager-bot")
from notify import notify

_CMD_MAX = 160          # длиннее в пуше не нужно — команда узнаваема по началу
_TAIL_BYTES = 262144    # транскрипт читаем хвостом, последние 256КБ — хватает на десятки записей


def _last_tool_use(transcript_path):
    """Последний tool_use из JSONL-транскрипта сессии → человекочитаемая строка (или None).
    Bash → команда; Edit/Write → имя файла; прочее → имя инструмента. Любой сбой → None."""
    try:
        with open(transcript_path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - _TAIL_BYTES))
            tail = f.read().decode("utf-8", "replace")
    except Exception:
        return None
    for line in reversed(tail.splitlines()):
        try:
            rec = json.loads(line)
        except Exception:
            continue
        msg = rec.get("message") if isinstance(rec, dict) else None
        content = msg.get("content") if isinstance(msg, dict) else None
        if not isinstance(content, list):
            continue
        for block in reversed(content):
            if not (isinstance(block, dict) and block.get("type") == "tool_use"):
                continue
            name = block.get("name") or "?"
            inp = block.get("input") or {}
            if name == "Bash" and inp.get("command"):
                return str(inp["command"])[:_CMD_MAX]
            if name in ("Edit", "Write", "NotebookEdit") and inp.get("file_path"):
                return (name + " " + str(inp["file_path"]))[:_CMD_MAX]
            return name
    return None


def _termux_notification(text):
    """Дубль в локальное уведомление Termux:API — ТОЛЬКО если бинарь есть (на VPS нет → скип)."""
    exe = shutil.which("termux-notification")
    if not exe:
        return
    try:
        subprocess.run([exe, "--title", "Claude Code", "--content", text],
                       timeout=10, capture_output=True)
    except Exception:
        pass


def build_text(data):
    """Текст пуша из события Notification (вынесено для регресс-теста)."""
    msg = (data.get("message") or "ждёт тебя в Termux")
    if "permission" in msg.lower():   # событие «needs your permission to use <tool>»
        cmd = _last_tool_use(data.get("transcript_path") or "")
        if cmd:
            return "⏳ Termux ждёт подтверждения: " + cmd
        return "⏳ Termux ждёт подтверждения: " + msg
    return "🔔 Claude Code: " + msg


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
    except Exception:
        data = {}
    text = build_text(data if isinstance(data, dict) else {})
    # track=True: удалить ПРЕДЫДУЩИЕ 🔔/⏳ и сохранить id нового → в личке висит максимум ОДНО уведомление.
    # force=True: это БОЕВОЕ Termux-уведомление (CC реально ждёт Филиппа) — тест-мут PRETOOL_NOPUSH его
    # НЕ глушит (регресс 05.07: широкий мут заглушил живые уведомления Termux).
    notify(text, track=True, force=True)
    _termux_notification(text)
