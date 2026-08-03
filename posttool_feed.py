#!/usr/bin/env python3
"""ЛЕНТА — канал заметок «третьего состояния», ШАГ 1: ТОЛЬКО МЕХАНИКА (03.08.2026).

Основание: docs/artifacts/2026-08-03-third-state-notify-design.md (устройство утверждено
владельцем). Здесь собран ПРОВОД и ничего кроме провода: список событий мира подключает ШАГ 2,
таблица классов ниже намеренно ПУСТА.

ЗАЧЕМ ВООБЩЕ. У гарда было два состояния: «выполнить молча» и «спросить разрешения». Клетка
«выполнить и СКАЗАТЬ» физически пуста, поэтому значимые изменения мира (рестарт клиентского бота,
отброс рабочего дерева, вынос теста из гейта) проходили молча — доктрина запрещает по ним карточку,
и это верно: разрешения там не нужно. Но из «не спрашивать» система вывела «не говорить».

ПОЧЕМУ ЭТО ЖИВЁТ В PostToolUse, А НЕ В ГАРДЕ. У события `PostToolUse` НЕТ поля `permissionDecision`
вовсе — команда уже выполнена, разрешать нечего. Заметка, живущая в этой фазе, не может выдать
право ФИЗИЧЕСКИ, а не потому что мы аккуратно написали код. Следствия:
  1. `pretool_guard.py` не меняется НИ НА ОДНУ строку — ни один красный класс измениться не может.
  2. Заблокированное в ленту не попадает: PostToolUse на невыполненной команде не срабатывает.
     Красное остаётся при своём адресе (инбокс 1160), лента говорит только о случившемся.
  3. Исход известен (`tool_response`) — заметка отличает «сделал» от «упало».
Сверх фазы этот файл держит СОБСТВЕННЫЙ обет: он НЕ ПЕЧАТАЕТ В stdout НИЧЕГО ни при каком входе
(включая мусорный и враждебный) — движок не получает от ленты ни решения, ни контекста, ни текста.
Регресс: tests/test_feed_channel.py, секция (1).

ТРИ ВЕЩИ ШАГА 1:
  * канал на PostToolUse — этот файл (провод в `.claude/settings.json`, matcher Bash; headless в
    `.claude/` писать не может → владелец применяет `cp _feed_new_settings.json .claude/settings.json`
    + рестарт сессии; прецеденты `_restarts_new_settings.json`, `_claspsplit_new_settings.json`);
  * СВОЙ каталог состояния `/tmp/cc_feed_seen` — НЕ `/tmp/cc_guard_block`: монитор демона открывает
    ровно `GUARD_BLOCK_DIR/<tid>.json` (orchestrator_daemon: _guard_marker_path, _guard_monitor_loop)
    и гасит claude-подпроцесс, увидев файл. Файл ленты в чужом каталоге задачу убить не может;
  * отдельный адрес — СВОЯ ТЕМА того же HQ-форума, «ПК-дев» (решение владельца 03.08.2026, см.
    notify._feed_dest: тема инертна — Splinter в ней молчит рано, devbot слышит только владельца
    по префиксам, свои сообщения бот назад не получает). В тему-инбокс не шлём ничего: у неё
    РОВНО одно свойство «всё здесь ждёт меня», и заметка его размывает.

ФОРМА ЗАМЕТКИ: одна строка `🔔 <класс> · <полоса> · <кто> · <команда ≤120> · <исход>`. Кнопок нет,
номера карточки нет, слова «да» нет — отвечать не на что и нечем.

МЕТКА ПОЛОСЫ (03.08.2026, вместе с адресом). Заметки ОБЕИХ полос сходятся в ОДНУ тему, а номера
задач VPS и ПК идут по РАЗНЫМ счётчикам и пересекаются: «задача 45» без метки — половина правды,
читатель не знает, чья она. Метку даёт исполнитель через `CC_LANE`, а если не назвал — константа
`LANE_DEFAULT` ЭТОЙ копии файла. Честный предел назван прямо: копия VPS-репо говорит «VPS» за
всякого, кто её запустил, — на VPS это правда всегда (headless-задачи демона и сессии Termux
живут на этом же хосте), но ПК-зеркало обязано либо сменить константу, либо ставить `CC_LANE`,
иначе оно будет честно врать чужой меткой.

ЧЕСТНЫЙ ПРЕДЕЛ: точную схему `tool_response` для Bash проверить нечем, пока хук не подключён
владельцем. Поэтому исход читается защитно: нашли код возврата/признак ошибки — говорим о нём,
не нашли — говорим «выполнено», БЕЗ утверждения об успехе (fail-honest, не выдумываем).
"""
import hashlib
import json
import os
import shlex
import sys

PROJECT = os.path.dirname(os.path.abspath(__file__))

# ─────────────────────────── КАТАЛОГ СОСТОЯНИЯ (потолок и дедуп) ───────────────────────────
# Зеркало дисциплины гарда (block_dir/PRETOOL_BLOCK_DIR), но каталог ДРУГОЙ — это и есть вторая
# из трёх вещей шага 1. Путь берётся В МОМЕНТ ЗАПИСИ, чтобы подмена работала для хука-подпроцесса.
FEED_SEEN_DIR = "/tmp/cc_feed_seen"            # БОЕВОЙ каталог ленты
FEED_SEEN_TEST_DIR = "/tmp/cc_feed_seen_test"  # безопасное умолчание тест-прогона
SEEN_DIR_ENV = "CC_FEED_SEEN_DIR"              # явная подмена каталога тестом (ставить ВСЕГДА)

CAP = 6            # потолок заметок на задачу; дальше одна строка «молчу» и тишина
SEEN_KEEP = 64     # сколько отпечатков команд держим для дедупа

# ─────────────────────────── МЕТКА ПОЛОСЫ (чья это задача) ───────────────────────────
LANE_ENV = "CC_LANE"       # исполнитель называет полосу сам (демон / pc_orchestrator), если хочет
LANE_DEFAULT = "VPS"       # эта копия файла живёт в репозитории VPS-полосы; ПК-зеркало ставит «ПК»
LANE_MAX = 12              # метка — короткая; длинное значение режем, чтобы не съесть команду

# ─────────────────────────── ТАБЛИЦА КЛАССОВ: ПУСТА ДО ШАГА 2 ───────────────────────────
# Сюда шаг 2 положит список фазы 1 (рестарт клиентского бота, вынос теста из гейта, отброс рабочего
# дерева, стирание незакрытых маркеров гарда, git push) — §3 артефакта, голдены на ДОСЛОВНЫХ
# командах транскриптов. Пока пусто: шаг 1 доказывает провод, а не детект.
_CLASSES = ()      # ((имя класса, предикат(cmd) -> bool), …)

# Единственная запись, которая работает уже сейчас, — ПРОБА САМОГО КАНАЛА, а не класс событий мира:
# ведущий env-префикс `CC_FEED_PROBE=1 <команда>`. Почему префикс, а не отдельный ключ запуска: проба
# идёт ТЕМ ЖЕ путём, что пойдёт настоящее событие (разбор → класс → изоляция проб → дедуп → потолок →
# отправка), значит проверяет провод целиком, а не его половину. Имя в середине строки объявлением
# НЕ является (иначе пометкой стал бы любой пересказ) — читаем ровно ведущие присваивания, как это
# делает pretool_guard._cmd_declares_probe.
PROBE_PREFIX = "CC_FEED_PROBE"
PROBE_CLASS = "проба канала"


def _leading_env(cmd):
    """Ведущие присваивания `VAR=val` до первого не-присваивания. Сбой разбора → пусто."""
    out = {}
    try:
        for t in shlex.split(cmd or ""):
            name, sep, val = t.partition("=")
            if not sep or not name or not name.replace("_", "").isalnum() or name[0].isdigit():
                break
            out[name] = val
    except Exception:
        return {}
    return out


def classify(cmd):
    """Класс события → имя | None. ШАГ 1: только проба канала, список событий пуст."""
    if (_leading_env(cmd).get(PROBE_PREFIX) or "").strip():
        return PROBE_CLASS
    for name, pred in _CLASSES:                       # шаг 2 наполнит
        try:
            if pred(cmd):
                return name
        except Exception:
            continue
    return None


def is_probe(cmd):
    """Изоляция проб — ЕДИНЫЙ признак гарда, а не свой собственный. Свой второй признак и породил
    класс «наполовину изолированной пробы» (01.08.2026): у каждого канала владельца был СВОЙ список,
    и каждый закрывал ровно то, что другой оставлял открытым. Лента — третий канал к владельцу,
    поэтому спрашивает ту же ручку: pretool_guard.is_probe (env-имена + env-префикс в команде +
    тест-скрипт по имени/пути). Гард при этом НЕ меняется: мы его ЧИТАЕМ.
    FAIL-SAFE: импорт не удался → считаем пробой, то есть МОЛЧИМ. Направление безопасное: заметка
    не даёт прав, её отсутствие возвращает ровно сегодняшнее поведение."""
    try:
        from pretool_guard import is_probe as _guard_is_probe
        return bool(_guard_is_probe(cmd))
    except Exception:
        return True


def seen_dir(env=None):
    """Каталог состояния ленты: явная подмена → тест-умолчание → боевой."""
    e = os.environ if env is None else env
    explicit = (e.get(SEEN_DIR_ENV) or "").strip()
    if explicit:
        return explicit
    try:
        from pretool_guard import is_test_run
        testing = is_test_run(e)
    except Exception:
        testing = True
    return FEED_SEEN_TEST_DIR if testing else FEED_SEEN_DIR


def state_key(data):
    """Ключ ленты = задача демона (CC_TASK_ID) или сессия Termux (session_id). Не опознали → 'orphan'.
    Ключ живёт в ИМЕНИ ФАЙЛА, поэтому чистим всё, кроме букв/цифр/дефиса."""
    tid = (os.environ.get("CC_TASK_ID") or "").strip()
    raw = tid or str((data or {}).get("session_id") or "").strip() or "orphan"
    safe = "".join(c for c in raw if c.isalnum() or c in "-_")[:64]
    return safe or "orphan"


def lane():
    """Метка полосы: `CC_LANE` исполнителя → константа этой копии. Значение плющим в одну строку
    и режем: метка идёт в текст заметки, и длинный/многострочный мусор из окружения не должен ни
    ломать форму, ни вытеснять команду."""
    v = " ".join((os.environ.get(LANE_ENV) or "").split())[:LANE_MAX]
    return v or LANE_DEFAULT


def who(data):
    """Кто сделал: полоса + задача демона (CC_TASK_ID) либо ручная сессия Termux. Полоса стоит
    ВСЕГДА — номера задач VPS и ПК пересекаются, без метки заметка врёт о принадлежности."""
    tid = (os.environ.get("CC_TASK_ID") or "").strip()
    return lane() + " · " + (("задача " + tid) if tid else "Termux")


def _state_path(key, env=None):
    return os.path.join(seen_dir(env), key + ".json")


def _load_state(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            data.setdefault("n", 0)
            data.setdefault("seen", [])
            data.setdefault("capped", False)
            return data
    except Exception:
        pass
    return {"n": 0, "seen": [], "capped": False}


def _save_state(path, st):
    """Best-effort: каталог/диск недоступен → молча пропускаем. Состояние ленты не критично —
    хуже дедупа не бывает ничего страшнее повторной заметки."""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(st, f)
        os.replace(tmp, path)
    except Exception:
        pass


def _fingerprint(cls, cmd):
    return hashlib.sha1((cls + "\x00" + " ".join((cmd or "").split())).encode("utf-8",
                                                                              "replace")).hexdigest()[:16]


def short_cmd(cmd, limit=120):
    flat = " ".join((cmd or "").split())
    return flat if len(flat) <= limit else flat[:limit - 1] + "…"


def outcome(resp):
    """Исход из `tool_response` — ЗАЩИТНО (схема не проверена живьём, см. честный предел в шапке).
    Нашли код возврата / признак ошибки / прерывание — говорим о них; иначе «выполнено» БЕЗ
    утверждения об успехе. Строковый ответ и мусор → «выполнено»."""
    if not isinstance(resp, dict):
        return "выполнено"
    for k in ("exit_code", "exitCode", "returncode", "returnCode", "code"):
        v = resp.get(k)
        if isinstance(v, bool):
            continue
        if isinstance(v, int):
            return "ok" if v == 0 else ("ошибка (код %d)" % v)
        if isinstance(v, str) and v.strip().lstrip("-").isdigit():
            return "ok" if int(v) == 0 else ("ошибка (код %d)" % int(v))
    if resp.get("interrupted"):
        return "прервано"
    if resp.get("is_error") or resp.get("isError") or resp.get("error"):
        return "ошибка"
    return "выполнено"


def render(cls, subject, cmd, resp):
    """Одна строка. Кнопок нет, номера карточки нет, слова «да» нет — отвечать не на что."""
    return "🔔 %s · %s · %s · %s" % (cls, subject, short_cmd(cmd), outcome(resp))


def render_cap(subject):
    return ("🔔 потолок ленты (%d заметки) · %s · дальше по этой задаче молчу — "
            "смотри журнал гарда и cc_log" % (CAP, subject))


def send(text):
    """Отправка в ленту. Мут/мок-счётчик — ОБЩИЕ с боевым пушем (notify._test_mode), поэтому полный
    гейт по-прежнему даёт ноль исходящих. Адреса нет (тема не задана) → False, МОЛЧА:
    фолбэка в личку у ленты нет намеренно (личка — канал алармов)."""
    try:
        from notify import send_feed
        return bool(send_feed(text))
    except Exception:
        return False


def handle(data):
    """Ядро без ввода-вывода процесса. → отправленный текст | None (для теста и для читаемости)."""
    if (data.get("tool_name") or "") != "Bash":
        return None
    ti = data.get("tool_input")
    cmd = (ti.get("command") or "") if isinstance(ti, dict) else ""
    if not cmd:
        return None
    cls = classify(cmd)
    if not cls:
        return None                      # ШАГ 1: список пуст → настоящие команды заметок не родят
    if is_probe(cmd):
        return None                      # гейт, фикстуры, разведка из /tmp/tb_scratch — не лента
    key = state_key(data)
    path = _state_path(key)
    st = _load_state(path)
    if st.get("capped"):
        return None
    fp = _fingerprint(cls, cmd)
    if fp in (st.get("seen") or []):
        return None                      # дедуп: тот же класс+команда в той же задаче — молча
    if int(st.get("n") or 0) >= CAP:
        text = render_cap(who(data))
        if not send(text):
            return None
        st["capped"] = True
        _save_state(path, st)
        return text
    text = render(cls, who(data), cmd, data.get("tool_response"))
    if not send(text):
        return None                      # канал не заведён/сеть — состояние не трогаем
    st["n"] = int(st.get("n") or 0) + 1
    st["seen"] = ([fp] + list(st.get("seen") or []))[:SEEN_KEEP]
    _save_state(path, st)
    return text


def main():
    """НИЧЕГО НЕ ПЕЧАТАЕТ. Любой вход, любая ошибка → тихий exit 0: у ленты нет и не может быть
    голоса в диалоге движка (ни решения, ни контекста)."""
    try:
        data = json.load(sys.stdin)
        if isinstance(data, dict):
            handle(data)
    except Exception:
        pass


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
