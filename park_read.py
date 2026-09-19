"""ЧИТАТЕЛЬ ПАРКА — отдельная точка входа: секрет живёт в ЭТОМ процессе (20.09.2026).

ОБРАЗЕЦ ВЗЯТ У ПОЛОСЫ ПК. Там запись в мозг идёт единственным легальным каналом — посредником
`brain_writer.py` (`docs/ENV_PLAYBOOK.md:18,25`), и свойство у него ровно одно: **секреты Bridge
берёт САМ ПРОЦЕСС ПИСАТЕЛЯ**, а агентский скрипт их не видит и в нём живёт только строковая
логика. Для ЧТЕНИЯ парка на сервере такого посредника не было вовсе: клиент моста окружение сам
не наполняет и падает на пустых переменных (`bridge_client.py:341-342`), а его собственный
запуск — фиксированная демонстрация `ping`+`daily_pulse` без аргументов и без парка
(`bridge_client.py:1475-1497`). Значит всякий, кому нужен был парк, читал `.env` своим кодом.
Этот модуль закрывает класс: окружение он поднимает СЕБЕ, наружу отдаёт ТОЛЬКО JSON.

ЗАЩИТА СЕКРЕТА — ДВА СЛОЯ, И ВТОРОЙ НУЖЕН ИМЕННО ПОТОМУ, ЧТО ПЕРВЫЙ НЕ ПОЛНЫЙ.
  (1) РАЗДЕЛЕНИЕ ПРОЦЕССОВ. Вызывающий зовёт этот файл подпроцессом и получает его stdout.
      Переменные окружения живут здесь и сюда же и умирают; в JSON их не кладёт ни одна ветка.
  (2) ЗАМАЗЫВАНИЕ НА ВЫХОДЕ. Одного разделения МАЛО, и это не осторожность, а факт из кода:
      транспортный отказ клиента возвращает `str(e)` requests-исключения
      (`bridge_client.py:532`), а оно несёт URL целиком. Поэтому наружу нет ни одной прямой
      печати: ВСЁ идёт через `_emit`, который прогоняет готовую строку через `_scrub`.
      Что считать специфичным значением, решает ГОТОВЫЙ [[env_out]] (`passing`/`mask`) — там это
      число выведено замером на живом окружении, и второго такого правила здесь не заводится.
      Сверх него замазываются по ИМЕНИ переменные, которые этот читатель реально использует:
      «значение слишком короткое, чтобы его узнать» — не причина его печатать.

ЧТО ОН НЕ МОЖЕТ ПО УСТРОЙСТВУ. Все обращения к мосту идут через ОДНУ дверь `_Gate`, и она
пропускает РОВНО `ALLOWED_ACTIONS` — три читающих действия. Незнакомое действие не «логируется
и выполняется», а БРОСАЕТ: fail-closed. Поэтому «пишущих действий внутри нет» — не обещание в
докстринге, а перечень, который сам читатель печатает в поле `actions_called` каждым запуском.

ВОЗРАСТ ПЕРЕД СОДЕРЖИМЫМ. Ответ начинается временем снятия снимка. И отдельно сказано вслух то,
о чём легко промолчать: **у клеток Лист1 штампа времени нет вовсе** — когда менялось масло,
из самой клетки не следует; возраст регистра = возраст этого снимка и не меньше. У СВОЕГО
одометра (Bot Data «обслуживание») штамп есть, и он называется отдельным полем — разница между
«знаем, когда подтвердили» и «не знаем никогда» не должна пропадать в общей строке.

ПРАВИЛА НЕ СВОИ. Текущий пробег даёт живой `splinter._odo_current` (единый источник правды,
класс-фикс 4957), тождество байка — `splinter._same_bike`, интервалы — `splinter._service_interval`
(книга знаний с фоллбэком). Своей копии ни одного из этих правил здесь нет: две копии разошлись
бы молча, и читатель показывал бы не то, что видит бот. Суждение «норма/просрочка/НЕИЗВЕСТНО» —
чистый [[park_verdict]], разметка клетки — [[fleet_cell]].

ЗАПУСК:
    venv/bin/python3 park_read.py <имя или номер байка>
    venv/bin/python3 park_read.py "весь парк"
    venv/bin/python3 park_read.py "весь парк" --no-cells   # спросить мост БЕЗ разметки клеток
"""
import json
import logging
import os
import sys
import time
import urllib.parse

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import env_out        # готовое правило «какое значение специфично» + замазывание
import fleet_cell     # контракт клетки: значение / пусто / не-число / не прочитано
import park_verdict   # чистое решение: в норме / просрочено / НЕИЗВЕСТНО

# Слово, по которому читают весь парк (а не один байк).
WHOLE_PARK = "весь парк"

# ЕДИНСТВЕННЫЕ действия моста, которые этот читатель вправе позвать. Все три — читающие:
#   fleet       — Лист1 «Байки», отдаёт строки парка (+ разметку клеток по cells=1);
#   service_list — Bot Data «обслуживание», свой одометр и история; читающее по имени и по сути;
#   read_doc    — узел мозга `knowledge_base`, оттуда берутся интервалы ТО.
# Список ЗАКРЫТЫЙ: незнакомое действие → отказ, а не «как-нибудь пройдёт».
ALLOWED_ACTIONS = frozenset(("fleet", "service_list", "read_doc"))

# Имена переменных, чьи значения не выходят наружу НИКОГДА — даже если короткие (слой 2).
_SECRET_NAMES = ("BRIDGE_URL", "BRIDGE_TOKEN")
_MIN_MASKABLE = 8          # короче — замазывать опасно: съест куски чужого текста
HIDDEN = env_out.HIDDEN    # маркер тоже готовый: двух разных «скрыто» в одном выводе не бывает

_NO_STAMP = ("у клеток Лист1 (кол. I/J/K/L) штампа времени НЕТ ВОВСЕ: когда менялся регистр — "
             "из клетки не следует. Возраст регистра равен возрасту ЭТОГО снимка и не меньше")


class Refused(Exception):
    """Читателя попросили о том, чего он делать не вправе."""


class Unread(Exception):
    """Источник НЕ ПРОЧИТАН. Отдельный исход, а не пустой список.

    Мост не бросает на транспортном отказе — он ВОЗВРАЩАЕТ `{"ok": false, ...}`
    (`bridge_client.py:532`). Прочитать такой ответ одним `.get("bikes") or []` значит сказать
    «в парке ноль байков» там, где правда — «парка мы не видели»: тот же нуль по неразбору,
    против которого написан [[fleet_cell]], только этажом выше. Поймано голденом
    `test_dead_bridge_is_unread_not_empty_park`."""


# ── ЗАМАЗЫВАНИЕ (единственная дверь наружу) ───────────────────────────────────────────────────
def _variants(value):
    """Все формы, в которых значение может ВЫЙТИ наружу, — не только оно само.

    Голден поймал живьём: текст транспортного отказа несёт не весь URL, а его ПУТЬ
    (`/macros/s/<идентификатор выкладки>/exec`), поэтому замена целого значения его не узнаёт.
    Поэтому замазывается и путь, и каждый его сегмент, достаточно длинный, чтобы быть
    опознавательным: секретна в адресе моста именно выкладка, а не имя хоста."""
    out = [value, urllib.parse.quote(value, safe="")]
    try:
        path = urllib.parse.urlsplit(value).path
    except ValueError:
        return out
    if len(path) >= _MIN_MASKABLE:
        out.append(path)
    out.extend(seg for seg in path.split("/") if len(seg) >= _MIN_MASKABLE)
    return out


def _mask_names(env):
    """Значения, которые замазываются ПО ИМЕНИ (сверх правила специфичности `env_out`)."""
    out = []
    for name in _SECRET_NAMES:
        v = (env or {}).get(name) or ""
        if len(v) >= _MIN_MASKABLE:
            out.append(v)
    return out


def _scrub(text, env=None):
    """Текст без значений секретов. Сначала готовое правило `env_out`, затем — по имени.

    Замазывается и ПРОЦЕНТНАЯ форма значения: токен едет GET-параметром, и в тексте
    транспортного отказа он может оказаться уже закодированным — literal-replace его бы
    не узнал, а секрет от этого секретом быть не перестал."""
    env = os.environ if env is None else env
    out = env_out.mask(text or "", env)
    for v in _mask_names(env):
        for form in sorted(set(_variants(v)), key=len, reverse=True):
            if form and form in out:
                out = out.replace(form, HIDDEN)
    return out


def _emit(obj):
    """ЕДИНСТВЕННАЯ печать наружу. Мимо неё в stdout не уходит ничего."""
    sys.stdout.write(_scrub(json.dumps(obj, ensure_ascii=False, indent=2)) + "\n")
    sys.stdout.flush()


class _ScrubFilter(logging.Filter):
    """Замазывание НА ПУТИ ЗАПИСИ ЖУРНАЛА — самый важный из трёх заслонов, и вот почему.

    Клиент моста печатает транспортный отказ сам: `log.error(f"Bridge request error ({action}):
    {e}")` (`bridge_client.py:531`). Токен едет GET-параметром, поэтому `str(e)` requests-
    исключения несёт URL С ТОКЕНОМ ЦЕЛИКОМ — и уходит в журнал МИМО `_emit`, то есть мимо
    единственной двери, которую легко счесть единственной. Голден
    `test_no_secret_in_output_of_broken_run_subprocess` поймал ровно это."""

    def filter(self, record):
        try:
            record.msg = _scrub(record.getMessage())
            record.args = ()
        except Exception:                       # замазать не вышло — не говорим ВООБЩЕ ничего
            record.msg = "‹запись журнала скрыта целиком: замазывание не удалось›"
            record.args = ()
        return True


def _install_scrubbing_logging():
    """Единственный обработчик журнала — со замазыванием, и он ставится ДО клиента моста.

    Без этого записи ушли бы в `logging.lastResort` (stderr без единого фильтра): корень без
    обработчиков — это не «журнала нет», это «журнал без охраны»."""
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    handler.addFilter(_ScrubFilter())
    root = logging.root
    for old in list(root.handlers):
        root.removeHandler(old)
    root.addHandler(handler)
    root.setLevel(logging.INFO)


def _install_scrubbing_excepthook():
    """Даже сорвавшееся исключение не выносит секрет: трассировка идёт через `_scrub`."""
    import traceback

    def hook(exc_type, exc, tb):
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        sys.stderr.write(_scrub(text))
        sys.stderr.flush()

    sys.excepthook = hook


# ── ДВЕРЬ К МОСТУ: перечень действий и запрет всего остального ─────────────────────────────────
class _Gate:
    """Обёртка клиента: записывает КАЖДОЕ действие и пропускает только читающие.

    ПЕРЕХВАТ СТОИТ НА `_durable_request`, И ЭТО НЕ ДЕТАЛЬ. У клиента ДВЕ двери наружу, а не
    одна: `_call` — это GET (`bridge_client.py:659`), `_post` — POST (`bridge_client.py:789`), и
    ВСЕ пишущие действия идут через вторую. Забор на `_call` закрыл бы ровно безобидную
    половину и при этом выглядел бы полным. Обе двери сходятся в `_durable_request`
    (`bridge_client.py:589`) — единственном месте, мимо которого наружу не уходит ни один
    запрос; поэтому список `called` полон ПО ПОСТРОЕНИЮ, а не по обещанию.

    Найдено живым прогоном: `service_list` идёт POST'ом и в перечне не появлялся вовсе."""

    def __init__(self, client, allowed=ALLOWED_ACTIONS):
        self._client = client
        self._allowed = frozenset(allowed)
        self.called = []
        self._orig = client._durable_request
        client._durable_request = self._guarded    # noqa: SLF001 — в этом и смысл двери

    def _guarded(self, method, action, *a, **kw):
        name = str(action or "")
        self.called.append(name)
        if name not in self._allowed:
            raise Refused(f"действие «{name}» ({method}) читателю парка не разрешено "
                          f"(разрешены только: {', '.join(sorted(self._allowed))})")
        return self._orig(method, action, *a, **kw)

    @property
    def actions(self):
        """Перечень вызванных действий без повторов, в порядке первого вызова."""
        seen, out = set(), []
        for a in self.called:
            if a not in seen:
                seen.add(a)
                out.append(a)
        return out

    def all_read_only(self):
        return all(a in self._allowed for a in self.called)


# ── СБОР ФАКТОВ ───────────────────────────────────────────────────────────────────────────────
def _utc(ts=None):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


def _bike_cells(row):
    """{поле: ScanResult} по четырём регистрам одной строки парка."""
    return {f: fleet_cell.read(row, f) for f in park_verdict.REGISTERS}


def _odo_stamp(rows):
    """Штамп СВОЕГО одометра (он у него есть, в отличие от клеток листа)."""
    stamps = [str(r.get("updated_at") or "") for r in (rows or []) if r.get("updated_at")]
    return max(stamps) if stamps else ""


def read_park(client, gate, query, cells=True):
    """Собрать ответ. Ничего не печатает и ничего не пишет — только читает и считает."""
    import splinter      # живые правила: пробег, тождество байка, интервалы ТО

    snapshot = _utc()
    reply = client.fleet(cells=cells) or {}
    if not reply.get("ok"):
        raise Unread("парк НЕ ПРОЧИТАН: мост не отдал Лист1 "
                     f"({_scrub(str(reply.get('error') or reply.get('message') or reply))}). "
                     "Это НЕ «в парке ноль байков»")
    rows = (reply.get("data") or {}).get("bikes") or []

    whole = str(query or "").strip().lower() == WHOLE_PARK
    if whole:
        targets = list(rows)
    else:
        targets = [r for r in rows if splinter._same_bike(r.get("name"), query)]

    # Свой одометр — источник НЕ фатальный: у него есть честный фоллбэк (max по I/J/K/L), и его
    # отсутствие делает регистры НЕИЗВЕСТНЫМИ, а не ложно-нормальными. Но молчать о провале
    # нельзя: «пробег не прочитан» и «пробега нет» — разные вещи, и первая называется вслух.
    snapshot_note = ""
    svc = []
    try:
        got = client.service_list() or {}
        if got.get("ok"):
            svc = got.get("items") or []
        else:
            snapshot_note = ("свой одометр НЕ ПРОЧИТАН: "
                             f"{_scrub(str(got.get('error') or got.get('message') or got))} — "
                             "пробег взят фоллбэком Лист1 либо неизвестен")
    except Exception as e:
        snapshot_note = f"свой одометр НЕ ПРОЧИТАН: {_scrub(str(e))}"

    bikes = []
    for row in targets:
        name = row.get("name") or ""
        mine = [r for r in svc if splinter._same_bike(r.get("bike"), name)]
        cur = splinter._odo_current(client, name, recs=mine, fleet_row=row)
        intervals = {park_verdict.kind_of(f): splinter._service_interval(
            park_verdict.kind_of(f), name, client) for f in park_verdict.REGISTERS}
        b = park_verdict.bike(name, _bike_cells(row), cur, intervals)
        b["odometer_confirmed_utc"] = _odo_stamp(mine) or "штампа нет — число не подтверждалось"
        bikes.append(b)

    return {
        # ── ВОЗРАСТ ПЕРЕД СОДЕРЖИМЫМ ──
        "snapshot_utc": snapshot,
        "registers_have_no_timestamp": _NO_STAMP,
        "odometer_timestamp_note": ("у СВОЕГО одометра (Bot Data «обслуживание») штамп ЕСТЬ — "
                                    "поле odometer_confirmed_utc у каждого байка"),
        "service_list_problem": snapshot_note,
        # ── ЧТО СПРАШИВАЛИ ──
        "query": query,
        "whole_park": whole,
        "cells_requested": bool(cells),
        # ── ЧЕМ ПОЛЬЗОВАЛИСЬ (доказательство «только чтение») ──
        "actions_called": gate.actions,
        "all_read_only": gate.all_read_only(),
        "rows_in_park": len(rows),
        # ── СОДЕРЖИМОЕ ──
        "summary": park_verdict.park_tally(bikes),
        "bikes": bikes,
    }


def main(argv=None):
    _install_scrubbing_excepthook()
    _install_scrubbing_logging()
    argv = list(sys.argv[1:] if argv is None else argv)
    cells = True
    if "--no-cells" in argv:
        cells = False
        argv.remove("--no-cells")
    query = argv[0] if argv else ""

    if not query:
        _emit({"ok": False, "error": "нужен аргумент: имя/номер байка или «весь парк»",
               "usage": f'park_read.py <байк> | "{WHOLE_PARK}" [--no-cells]'})
        return 2

    from dotenv import load_dotenv           # окружение читатель поднимает СЕБЕ (см. шапку)
    load_dotenv(os.path.join(ROOT, ".env"))

    import bridge_client

    gate = None
    try:
        client = bridge_client.BridgeClient()
        gate = _Gate(client)
        out = read_park(client, gate, query, cells=cells)
    except Refused as e:
        _emit({"ok": False, "error": "refused", "message": _scrub(str(e)),
               "actions_called": gate.actions if gate else []})
        return 3
    except Unread as e:
        _emit({"ok": False, "error": "unread", "message": _scrub(str(e)),
               "snapshot_utc": _utc(), "bikes": None,
               "actions_called": gate.actions if gate else [],
               "note": "источник не прочитан — это НЕ пустой парк"})
        return 4
    except Exception as e:                    # текст отказа тоже идёт через замазывание
        _emit({"ok": False, "error": type(e).__name__, "message": _scrub(str(e)),
               "actions_called": gate.actions if gate else [],
               "note": "секретов в этом сообщении нет: текст прошёл через _scrub"})
        return 1

    out["ok"] = True
    _emit(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
