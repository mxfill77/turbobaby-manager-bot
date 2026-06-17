#!/usr/bin/env python3
"""Пуш-уведомление Филиппу в личку Telegram по завершении блока работы Claude Code.

Зачем: Филипп отошёл от телефона — пуш сообщает, что задача готова или нужно его решение.
Пункт 1 «лестницы фундамента» (см. docs/project_state.md → «ФУНДАМЕНТ ПЕРЕД АВТОНОМИЕЙ»).

Использование (Claude Code зовёт в КОНЦЕ блока, вместе с DONE в cc_log):
  venv/bin/python3 notify.py --done "<задача>"   → «✅ <задача> готова»
  venv/bin/python3 notify.py --need "<задача>"   → «🔧 <задача> — нужно решение»
  venv/bin/python3 notify.py "<произвольный текст>"  → шлёт текст как есть

Токен берётся из .env (BOT_TOKEN), В ЛОГИ/ВЫВОД НЕ ПОПАДАЕТ. chat_id = личка Филиппа.
Ограничение (честно): момент «застрял на встроенном guard-вопросе» программно НЕ
перехватывается — пуш идёт по ЗАВЕРШЕНИЮ блока (покрывает «отошёл, не знаю — готово ли»).
Exit 0 = доставлено, 1 = ошибка (текст ошибки без токена).
"""
import os
import sys
import json
import urllib.request
import urllib.error

CHAT_ID = 504608015  # личный аккаунт Филиппа (написал боту Start → бот может инициировать личку)


def notify(text: str) -> bool:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
    token = os.getenv("BOT_TOKEN")
    if not token:
        print("notify: NO BOT_TOKEN in env", file=sys.stderr)
        return False
    url = "https://api.telegram.org/bot" + token + "/sendMessage"
    data = json.dumps({"chat_id": CHAT_ID, "text": text}).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            resp = json.load(r)
        return bool(resp.get("ok"))
    except urllib.error.HTTPError as e:
        # тело ответа TG не содержит токен (токен только в URL, его не печатаем)
        print("notify: HTTP " + str(e.code) + " " + e.read().decode(), file=sys.stderr)
        return False
    except Exception as e:
        print("notify: " + type(e).__name__ + " " + str(e), file=sys.stderr)
        return False


def _build_text(argv) -> str:
    if argv and argv[0] == "--done":
        return "✅ " + " ".join(argv[1:]) + " готова"
    if argv and argv[0] == "--need":
        return "🔧 " + " ".join(argv[1:]) + " — нужно решение"
    return " ".join(argv)


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print("usage: notify.py [--done|--need] <текст>", file=sys.stderr)
        raise SystemExit(2)
    ok = notify(_build_text(args))
    print("ok" if ok else "FAILED")
    raise SystemExit(0 if ok else 1)
