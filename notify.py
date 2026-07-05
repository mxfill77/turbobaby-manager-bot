#!/usr/bin/env python3
"""Пуш-уведомление Филиппу в личку Telegram + автоудаление накопленных 🔔 Claude Code.

Зачем: Филипп отошёл от телефона — пуш сообщает, что задача готова или нужно его решение.
Пункт 1 «лестницы фундамента» (см. docs/project_state.md → «ФУНДАМЕНТ ПЕРЕД АВТОНОМИЕЙ»).

АВТОЧИСТКА 🔔 (30.06, вектор а+б): уведомления Claude Code «🔔 needs permission / waiting» копились в личке.
Теперь висит МАКСИМУМ ОДНО: на каждом новом 🔔 (track=True) и на --done/--need (clear_first=True) предыдущие
🔔 удаляются через deleteMessage (тот же бот/чат). Хук UserPromptSubmit чистит при новом задании владельца.
Чистятся ТОЛЬКО трекнутые 🔔 (их message_id в сторе); ✅ --done / 🔧 --need / health-алерты НЕ трекаются и не
удаляются. Рабочие сообщения Splinter идут в ГРУППЫ, не в личку → чистка их не задевает.

Использование:
  venv/bin/python3 notify.py --done "<задача>"   → «✅ <задача> готова» (+ убирает висящий 🔔)
  venv/bin/python3 notify.py --need "<задача>"   → «🔧 <задача> — нужно решение» (+ убирает висящий 🔔)
  venv/bin/python3 notify.py "<текст>"           → шлёт текст как есть (🔔 не трогает)
  from notify import notify; notify(text, track=True)   → 🔔-хук (трек+чистка предыдущих)
  from notify import clear_notifications                → удалить накопленные 🔔 (UserPromptSubmit-хук)

Токен из .env (BOT_TOKEN), В ЛОГИ/ВЫВОД НЕ ПОПАДАЕТ (только в URL). chat_id = личка Филиппа.
Exit 0 = доставлено, 1 = ошибка (текст ошибки без токена).
"""
import os
import sys
import json
import fcntl
import urllib.request
import urllib.error

CHAT_ID = 504608015  # личный аккаунт Филиппа (написал боту Start → бот может инициировать личку)
_STORE = "/root/.claude/cc_notif_ids.json"   # message_id висящих 🔔 (для автоудаления)


def _get_token():
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
    return os.getenv("BOT_TOKEN")


class _Lock:
    """Сериализация параллельных хуков (flock на lock-файле) — чтобы стор не побили."""
    def __enter__(self):
        try:
            os.makedirs(os.path.dirname(_STORE), exist_ok=True)
            self.f = open(_STORE + ".lock", "w")
            fcntl.flock(self.f, fcntl.LOCK_EX)
        except Exception:
            self.f = None
        return self

    def __exit__(self, *a):
        try:
            if self.f:
                fcntl.flock(self.f, fcntl.LOCK_UN); self.f.close()
        except Exception:
            pass


def _load_ids():
    try:
        with open(_STORE) as f:
            data = json.load(f)
        return [int(x) for x in data] if isinstance(data, list) else []
    except Exception:
        return []


def _save_ids(ids):
    """Атомарная перезапись (tmp + rename) — параллельный хук не увидит полу-файл."""
    try:
        os.makedirs(os.path.dirname(_STORE), exist_ok=True)
        tmp = _STORE + ".tmp"
        with open(tmp, "w") as f:
            json.dump([int(x) for x in ids], f)
        os.replace(tmp, _STORE)
    except Exception:
        pass


def _send_message(token, text):
    """Низкоуровневая отправка. → (ok, message_id|None). Токен только в URL, не печатается."""
    url = "https://api.telegram.org/bot" + token + "/sendMessage"
    data = json.dumps({"chat_id": CHAT_ID, "text": text}).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            resp = json.load(r)
        if resp.get("ok"):
            return True, (resp.get("result") or {}).get("message_id")
        return False, None
    except urllib.error.HTTPError as e:
        print("notify: HTTP " + str(e.code) + " " + e.read().decode(), file=sys.stderr)
        return False, None
    except Exception as e:
        print("notify: " + type(e).__name__ + " " + str(e), file=sys.stderr)
        return False, None


def _delete_message(token, mid):
    """Удалить сообщение бота (≤48ч). Best-effort: id уже нет / старше 48ч → молча False, НЕ кидает."""
    try:
        url = "https://api.telegram.org/bot" + token + "/deleteMessage"
        data = json.dumps({"chat_id": CHAT_ID, "message_id": int(mid)}).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            json.load(r)
        return True
    except Exception:
        return False


def _delete_stored(token):
    """Удалить ВСЕ висящие 🔔 (по сохранённым id) и очистить стор. Зовётся под _Lock."""
    for mid in _load_ids():
        _delete_message(token, mid)
    _save_ids([])


def _test_mode():
    """Тест-контур (фикс утечек 01–05.07: тестовые карточки летели в личку).
    → 'count' | 'mute' | None. Проверяется ДО токена и ДО сети:
    - NOTIFY_COUNT_FILE=<путь> — мок-счётчик регресса: попытка пуша = строка в файл, сеть НЕ дёргаем
      (первым: регресс считает ПОПЫТКИ, даже те, что дальше замутил бы PRETOOL_NOPUSH);
    - PRETOOL_NOPUSH=1 — мут тестовых прогонов (gate.py ставит его подпроцессам тестов; та же
      переменная, что чтит pretool_guard._push)."""
    if os.environ.get("NOTIFY_COUNT_FILE"):
        return "count"
    if os.environ.get("PRETOOL_NOPUSH") == "1":
        return "mute"
    return None


def _count_attempt(text):
    try:
        with open(os.environ["NOTIFY_COUNT_FILE"], "a", encoding="utf-8") as f:
            f.write(text.replace("\n", " ")[:200] + "\n")
    except Exception:
        pass


def notify(text, track=False, clear_first=False) -> bool:
    """Отправить пуш Филиппу. track=True → это 🔔-уведомление: удалить прошлые 🔔, отправить, СОХРАНИТЬ id
    (чтобы следующее его убрало). clear_first=True → удалить висящие 🔔 перед отправкой, но НЕ трекать (для
    --done/--need: задача разрешена). По умолчанию (оба False) — просто отправить, висящий 🔔 НЕ трогать
    (health/эскалации/произвольный текст)."""
    mode = _test_mode()
    if mode == "count":
        _count_attempt(text)
        return True
    if mode == "mute":
        print("notify: muted (PRETOOL_NOPUSH=1, тест-режим — пуш не отправлен)", file=sys.stderr)
        return True
    token = _get_token()
    if not token:
        print("notify: NO BOT_TOKEN in env", file=sys.stderr)
        return False
    with _Lock():
        if track or clear_first:
            _delete_stored(token)
        ok, mid = _send_message(token, text)
        if track and ok and mid:
            ids = _load_ids()
            ids.append(int(mid))
            _save_ids(ids)
    return ok


def clear_notifications() -> None:
    """Удалить все накопленные 🔔 (хук UserPromptSubmit — при новом задании владельца). Тихо, без stdout."""
    if _test_mode():
        return   # тест-контур: сеть не дёргаем
    token = _get_token()
    if not token:
        return
    with _Lock():
        _delete_stored(token)


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
    # --done/--need разрешают задачу → убираем висящий 🔔 (но сами не трекаются, владелец их читает)
    _clear = bool(args and args[0] in ("--done", "--need"))
    ok = notify(_build_text(args), clear_first=_clear)
    print("ok" if ok else "FAILED")
    raise SystemExit(0 if ok else 1)
