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


def _is_test_entrypoint() -> bool:
    """§12 корень 2 (06.07.2026): процесс запущен как ТЕСТ? Активный pytest ИЛИ entry-point
    tests/test_*.py. gate.py (сам не test_*) и notify.py-CLI детектором НЕ считаются боевыми —
    их force-пуши остаются живыми (auto-set через setdefault, force это не глушит)."""
    if "pytest" in sys.modules or os.environ.get("PYTEST_CURRENT_TEST"):
        return True
    ep = os.path.basename((sys.argv[0] if sys.argv else "") or "")
    return ep.startswith("test_") and ep.endswith(".py")


# §12 корень 2: PRETOOL_NOPUSH раньше ставил ТОЛЬКО gate.py подпроцессам тестов (20762b6) — прямой
# прогон `venv/bin/python3 tests/test_*.py` МИМО гейта флага не получал → тестовые карточки текли в
# личку. Теперь любой тест-entry-point (прямой прогон ИЛИ pytest) поднимает флаг на СТАРТЕ импортом
# notify — физически, не только под гейтом. setdefault: тест может явно снять флаг (test_notify_force
# проверяет боевой путь, снимая PRETOOL_NOPUSH перед проверкой отправки) → его force-путь цел.
if _is_test_entrypoint():
    os.environ.setdefault("PRETOOL_NOPUSH", "1")


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


def _edit_message(token, mid, text):
    """editMessageText того же сообщения (дедуп карточек pretool_guard 08.07: повтор → ×N в ТОЙ ЖЕ
    карточке). Best-effort: сообщения нет/текст идентичен/сеть → False, НЕ кидает."""
    try:
        url = "https://api.telegram.org/bot" + token + "/editMessageText"
        data = json.dumps({"chat_id": CHAT_ID, "message_id": int(mid), "text": text}).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            resp = json.load(r)
        return bool(resp.get("ok"))
    except Exception:
        return False


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


def notify(text, track=False, clear_first=False, force=False) -> bool:
    """Отправить пуш Филиппу. track=True → это 🔔-уведомление: удалить прошлые 🔔, отправить, СОХРАНИТЬ id
    (чтобы следующее его убрало). clear_first=True → удалить висящие 🔔 перед отправкой, но НЕ трекать (для
    --done/--need: задача разрешена). По умолчанию (оба False) — просто отправить, висящий 🔔 НЕ трогать
    (health/эскалации/произвольный текст).

    force=True → ЛЕГИТИМНЫЙ БОЕВОЙ пуш (CLI notify.py, хук Notification=Termux-уведомление, health/gate/
    splinter-алерты). Мут по PRETOOL_NOPUSH его НЕ глушит, даже если флаг протёк в окружение сессии
    (регресс 05.07: боевые Termux-уведомления заглохли, т.к. мут был слишком широким). Мут PRETOOL_NOPUSH
    оставлен ТОЛЬКО тестовому коду/фикстурам (force=False по умолчанию); pretool_guard._push тоже НЕ форсит
    (его красные фикстуры-карточки остаются замьюченными). Мок-счётчик NOTIFY_COUNT_FILE (регресс) действует
    ВСЕГДА, включая force — сеть в тестах не дёргаем ни при каких условиях."""
    mode = _test_mode()
    if mode == "count":
        _count_attempt(text)
        return True
    if mode == "mute" and not force:
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


def send_card(text):
    """Отправить карточку с ВОЗВРАТОМ message_id (дедуп pretool_guard, 08.07.2026: повтор той же
    нераспознанной команды правит ЭТУ карточку через edit_card, а не шлёт новую — спам-инцидент 163).
    Тест-контур как в notify(): NOTIFY_COUNT_FILE → попытка в счётчик, сети нет (псевдо-id -1);
    PRETOOL_NOPUSH → мут (None). force не нужен: единственный вызыватель — pretool_guard, его
    карточки в тест-прогонах ДОЛЖНЫ мутиться (как раньше)."""
    mode = _test_mode()
    if mode == "count":
        _count_attempt(text)
        return -1
    if mode == "mute":
        print("notify: muted (PRETOOL_NOPUSH=1, тест-режим — пуш не отправлен)", file=sys.stderr)
        return None
    token = _get_token()
    if not token:
        print("notify: NO BOT_TOKEN in env", file=sys.stderr)
        return None
    ok, mid = _send_message(token, text)
    return mid if ok and mid else None


def edit_card(mid, text) -> bool:
    """Правка ранее отправленной send_card-карточки (счётчик ×N). Тест-контур: count → строка с
    префиксом `EDIT ` в мок-счётчик (регресс различает «новое сообщение» и «правка той же карточки»);
    mute → тихо True. Сеть/нет сообщения → False, не кидает."""
    mode = _test_mode()
    if mode == "count":
        _count_attempt("EDIT " + text)
        return True
    if mode == "mute":
        return True
    if not mid:
        return False
    token = _get_token()
    if not token:
        return False
    return _edit_message(token, mid, text)


def clear_notifications(force=False) -> None:
    """Удалить все накопленные 🔔 (хук UserPromptSubmit — при новом задании владельца). Тихо, без stdout.
    force=True (зовётся из notify_clear_hook) → чистка проходит даже под PRETOOL_NOPUSH (боевая сессия);
    мок-счётчик NOTIFY_COUNT_FILE всё равно блокирует сеть в тестах."""
    mode = _test_mode()
    if mode == "count":
        return   # тест-контур (мок-счётчик): сеть не дёргаем
    if mode == "mute" and not force:
        return   # тест-мут PRETOOL_NOPUSH: сеть не дёргаем
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


def _cli(argv) -> bool:
    """Обёртка CLI (тестируемая): явный запуск notify.py владельцем/CC — ВСЕГДА боевой (force=True),
    тест-мут PRETOOL_NOPUSH его не глушит."""
    # --done/--need разрешают задачу → убираем висящий 🔔 (но сами не трекаются, владелец их читает)
    _clear = bool(argv and argv[0] in ("--done", "--need"))
    return notify(_build_text(argv), clear_first=_clear, force=True)


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print("usage: notify.py [--done|--need] <текст>", file=sys.stderr)
        raise SystemExit(2)
    ok = _cli(args)
    print("ok" if ok else "FAILED")
    raise SystemExit(0 if ok else 1)
