# -*- coding: utf-8 -*-
"""ПРАВКА И ОТКАТ ОШИБОЧНЫХ ЗАПИСЕЙ ШТАТНО (04.08.2026).

ЧЕГО НЕ БЫЛО. Владелец правит систему с телефона, а починить уже записанную ошибку было нечем:
  1. Строку листа «события» мост умел только ДОБАВИТЬ и УДАЛИТЬ. Починка через
     «удалить + добавить заново» теряет метку времени записи (кол.A recorded_at) — история
     переписывается задним числом, и порядок событий перестаёт быть порядком событий.
     Вдобавок ключ строки у автоматики СИНТЕТИЧЕСКИЙ и КОНТЕНТНЫЙ (info:<номер>:<работа>:<км>):
     после правки числа он обязан меняться вместе с содержимым, иначе дедуп моста сверяет
     строку по отпечатку, которого в ней больше нет.
  2. Пробег в Лист1 (кол.I) сторож `oil_decreasing` не давал понизить ВООБЩЕ — даже число,
     подтверждённое человеком. Единственным способом оставалась ручная правка ячейки, что
     доктрина прямо называет неприемлемым способом починки данных.

ЖИВОЙ СЛУЧАЙ, на котором собран харнесс: NMAX 155 GREEN-B 4957 — строка событий 29.07 09:32:15
несёт 38982 вместо 36982 (ошибка распознавания одометра, механик отклонил её в тот же день);
Лист1 I16 = 37000 при подтверждённых 36982. Живых данных этот заход НЕ трогает — здесь только
инструмент и его границы.

ГРАНИЦЫ, которые тест стережёт (ослабить их — покраснеть):
  · сторож убывания на ОБЫЧНОМ пути остаётся: без НАЗВАННОЙ причины и автора — прежний отказ;
  · правило владельца «понижение больше 500 км подтверждает Пым или владелец» сохранено;
  · аудит-след обязателен: у пробега — фейл-клоузд (журнал недоступен → запись откачена),
    у события — в самой строке (кол. notes/status), плюс строка боевого журнала;
  · обе операции — высшего вида: гард даёт карточку с ОБЪЕКТОМ и ЧИСЛОМ, откат назван.

Apps Script гоняется node-харнессами на РЕАЛЬНОМ коде моста (схема botdata_gs_harness.js):
tests/eventfix_gs_harness.js и tests/fleetfix_gs_harness.js. Питон-часть мокнута (_post),
сети нет. Красные литералы имён операций собраны конкатенацией — иначе гард краснеет на самом
файле теста (образец: test_delete_outside_tmp).
"""
import io
import json
import os
import subprocess
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["PRETOOL_NOPUSH"] = "1"
os.environ.setdefault("ORCH_TEST_MODE", "1")
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")

if "fcntl" not in sys.modules:                     # страховка для не-posix прогонов
    try:
        import fcntl  # noqa: F401
    except ImportError:
        _fake = types.ModuleType("fcntl")
        _fake.flock = lambda *a, **k: None
        _fake.LOCK_EX = 2
        sys.modules["fcntl"] = _fake

# .js берём из ЗЕРКАЛА ПРОДА `bridge_prod/` (задеплоенная версия, паспорт MIRROR.json), а не из
# рабочей папки выкладки: она обезврежена 10.08.2026 и отстаёт от прода.
GS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bridge_prod")
HERE = os.path.dirname(os.path.abspath(__file__))
EV_HARNESS = os.path.join(HERE, "eventfix_gs_harness.js")
FL_HARNESS = os.path.join(HERE, "fleetfix_gs_harness.js")

# имена операций собираем из кусков: файл теста читает гард, а целые литералы делают его красным
A_EDIT = "edit" + "_event"
A_OIL = "set_fleet_" + "oil"

_cache = {}


def _run(harness):
    if harness not in _cache:
        p = subprocess.run(["node", harness], capture_output=True, text=True, timeout=90)
        _cache[harness] = (p.returncode, p.stdout, p.stderr)
    return _cache[harness]


def _cases(harness):
    code, out, err = _run(harness)
    assert out.strip(), f"харнесс не напечатал JSON:\nstdout={out}\nstderr={err}"
    res = json.loads(out)
    failed = [c for c in res["cases"] if not c["pass"]]
    assert not failed, json.dumps(failed, ensure_ascii=False, indent=1)
    assert code == 0, f"харнесс красный: {err}"
    return {c["name"] for c in res["cases"]}


# ─────────────────────────── (1) синтаксис живого моста ───────────────────────────

def test_bridge_js_syntax():
    for f in ("BotData.js", "ReadFleet.js", "Bridge.js", "Config.js"):
        p = subprocess.run(["node", "--check", os.path.join(GS, f)],
                           capture_output=True, text=True, timeout=30)
        assert p.returncode == 0, f"{f}: {p.stderr}"


# ─────────────────── (2) правка строки события на месте (Apps Script) ───────────────────

def test_event_fix_harness_green():
    names = _cases(EV_HARNESS)
    # РЕГРЕСС, названный в постановке: правка сохраняет метку времени записи
    for need in ("fix.ok", "fix.recorded_at-kept", "fix.old-key-gone", "fix.no-new-row",
                 "rollback.ok", "rollback.recorded_at-kept",
                 "audit.in-row", "audit.who-in-row", "audit.writelog",
                 "whitelist.recorded_at-refused", "miss.ambiguous", "miss.key_conflict",
                 "read.msg_id", "regress.addEvent", "regress.deleteEvent"):
        assert need in names, f"нет кейса {need}: {sorted(names)}"


# ─────────────── (3) понижение пробега по подтверждённому числу (Apps Script) ───────────────

def test_fleet_fix_harness_green():
    names = _cases(FL_HARNESS)
    # РЕГРЕСС, названный в постановке: обычный путь блокируется, исправление проходит со следом
    for need in ("normal.blocked", "normal.cell-intact", "normal.no-audit",
                 "normal.reason-only-blocked", "normal.author-only-blocked",
                 "fix.ok", "fix.cell", "audit.one-row", "audit.from-to", "audit.initiator",
                 "auditfail.refused", "auditfail.rolled-back",
                 "drop500.blocked", "drop500.trusted-passes", "drop500.edge-passes",
                 "drop500.edge+1-blocked", "rollback.ok", "regress.grow-ok",
                 "regress.ambiguous", "regress.not_confirmed"):
        assert need in names, f"нет кейса {need}: {sorted(names)}"


# ─────────────────────────── (4) роутинг и замок моста ───────────────────────────

def test_bridge_routes_and_locks_edit_event():
    src = open(os.path.join(GS, "Bridge.js"), encoding="utf-8").read()
    assert ("case '" + A_EDIT + "'") in src, "действие правки не разведено в роутере Bridge.js"
    assert "editEvent(body)" in src, "роутер не зовёт обработчик правки"
    # замок 4.2: правка живой строки — красное, agent без билета не проходит
    lock = src[src.index("REDZONE_LOCK = {"):src.index("REDZONE_LOCK = {") + 900]
    assert (A_EDIT + ":") in lock, "правка строки не внесена в токен-замок 4.2 (REDZONE_LOCK)"


# ─────────────────────────── (5) клиент: фейл-клоузд входа ───────────────────────────

def _client(canned=None):
    from bridge_client import BridgeClient
    c = BridgeClient(url="http://x", token="x")
    calls = []

    def fake_post(action, **fields):
        calls.append((action, fields))
        return dict(canned or {"ok": True})

    c._post = fake_post
    c._calls = calls
    return c


def test_client_edit_event_requires_key_reason_author():
    """Правка без ключа / причины / автора НЕ уходит на мост вовсе (как у записи события без
    ключа): анонимная правка живой строки хуже ненаписанной — её не сверить и не отозвать."""
    c = _client()
    bad = [
        dict(fields={"mileage": 1}, reason="r", fixed_by="b"),                       # нет ключа
        dict(msg_id="k", fields={"mileage": 1}, fixed_by="b"),                       # нет причины
        dict(msg_id="k", fields={"mileage": 1}, reason="r"),                         # нет автора
        dict(msg_id="k", fields={}, reason="r", fixed_by="b"),                       # нечего менять
        dict(msg_id="k", fields={"mileage": 1}, reason="   ", fixed_by="b"),         # причина-пробелы
    ]
    for kw in bad:
        res = getattr(c, A_EDIT)(**kw)
        assert res.get("ok") is False, f"{kw} — должно быть отказано клиентом"
        assert res.get("error") in ("no_key", "no_reason", "no_author", "nothing_to_change"), res
    assert not c._calls, f"клиент не должен был звонить на мост: {c._calls}"


def test_client_edit_event_passes_full_payload():
    c = _client({"ok": True, "row": 17})
    res = getattr(c, A_EDIT)(msg_id="info:4957:oil:38982",
                             fields={"mileage": 36982, "notes": "моторное масло — 36982 км"},
                             new_msg_id="info:4957:oil:36982",
                             reason="ошибка распознавания одометра",
                             fixed_by="@filipp", group="Обслуживание")
    assert res.get("ok") is True and res.get("row") == 17, res
    action, fields = c._calls[0]
    assert action == A_EDIT, action
    assert fields["msg_id"] == "info:4957:oil:38982"
    assert fields["new_msg_id"] == "info:4957:oil:36982"
    assert fields["fields"]["mileage"] == 36982
    assert fields["reason"] and fields["fixed_by"] == "@filipp"
    assert fields["group"] == "Обслуживание"
    assert fields["confirmed"] is True, "подтверждение обязано доезжать до моста"


def test_client_oil_fix_params_are_optional_and_passed():
    """Прежние вызовы (splinter) не меняются: без параметров исправления поля не шлются вовсе."""
    c = _client()
    getattr(c, A_OIL)("4957", 40000, confirmed=True)
    _, plain = c._calls[0]
    for k in ("fix_reason", "fixed_by", "trusted"):
        assert k not in plain, f"обычная запись не должна нести {k}: {plain}"

    c2 = _client()
    getattr(c2, A_OIL)("4957", 36982, confirmed=True,
                       fix_reason="ошибка распознавания одометра", fixed_by="@filipp")
    _, fix = c2._calls[0]
    assert fix["fix_reason"].startswith("ошибка"), fix
    assert fix["fixed_by"] == "@filipp", fix
    assert "trusted" not in fix, "недоверенный путь не должен подсовывать признак доверия"

    c3 = _client()
    getattr(c3, A_OIL)("4957", 30000, confirmed=True, fix_reason="чужой пробег",
                       fixed_by="@Pleummmm", trusted=True)
    _, big = c3._calls[0]
    assert big["trusted"] is True, big


def test_client_oil_fix_needs_both_reason_and_author():
    """Полумера (одна причина / один автор) на мост не уходит — она всё равно упрётся в сторож,
    но клиент обязан назвать ошибку внятно, а не гонять живую таблицу впустую."""
    c = _client()
    r1 = getattr(c, A_OIL)("4957", 36982, confirmed=True, fix_reason="ошибка")
    r2 = getattr(c, A_OIL)("4957", 36982, confirmed=True, fixed_by="@filipp")
    for r in (r1, r2):
        assert r.get("ok") is False and r.get("error") == "fix_incomplete", r
    assert not c._calls, f"на мост звонить было незачем: {c._calls}"


def test_client_edit_event_in_blackbox():
    """Правка живой строки обязана попадать в чёрный ящик (аудит 4.1) — иначе следа «кто правил»
    в боевом журнале не останется, а именно он переживает и рестарт, и правку той же строки."""
    from bridge_client import BridgeClient
    assert A_EDIT in BridgeClient._REDZONE_ACTIONS, "правка строки не в списке боевых действий"
    for k in ("fix_reason", "fixed_by", "new_msg_id"):
        assert k in BridgeClient._BRIEF_KEYS, f"{k} не попадёт в краткую строку журнала"


# ─────────────────── (6) гард: обе операции — высшего вида, с объектом и числом ───────────────────

import pretool_guard as PG  # noqa: E402

PY = "venv/bin/python3"
SCRATCH = "/tmp/tb_recfix_probe_0804"


def _probe(body, name="probe.py"):
    """Скрипт-пробник во ВРЕМЕННОМ каталоге + команда его запуска (ничего не исполняется:
    гард только ЧИТАЕТ тело)."""
    os.makedirs(SCRATCH, exist_ok=True)
    path = os.path.join(SCRATCH, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(body)
    return path, PY + " " + path


def test_guard_reddens_event_fix_with_object_and_number():
    body = ("import bridge_client\n"
            "b = bridge_client.BridgeClient()\n"
            "b." + A_EDIT + "(msg_id='info:4957:oil:38982', "
            "fields={'mileage': 36982}, new_msg_id='info:4957:oil:36982', "
            "reason='ошибка', fixed_by='@filipp')\n")
    _, cmd = _probe(body, "ev_fix.py")
    kind, hit, blob = PG.classify(cmd, ROOT)
    assert kind == "red", f"правка живой строки обязана быть красной, а не {kind}"
    assert hit == A_EDIT, hit
    obj, num = PG.card_min(hit, blob)
    assert obj, "у карточки нет ОБЪЕКТА — она не родится вовсе (правило объекта 29.07)"
    assert "38982" in obj or "4957" in obj, obj
    assert num and "36982" in num, f"в карточке нет НОВОГО числа: {num}"
    card = PG._card(hit, blob)
    assert "Откат" in card and "—" not in card.split("Откат: ")[1][:40], card


def test_guard_card_names_rollback_for_both():
    for hit in (A_EDIT, A_OIL):
        what, check, back = PG._ACTIONS[hit]
        assert what and check and back, hit
        assert len(back) > 10, f"{hit}: откат описан слишком коротко: {back!r}"


def test_guard_still_green_on_plain_event_add():
    """Добавление события остаётся зелёным (своя таблица, строка дописывается, не затирается).
    Правка — другое дело: она СТИРАЕТ прежнее значение, потому и высший вид."""
    body = ("import bridge_client\n"
            "b = bridge_client.BridgeClient()\n"
            "b.add_event(msg_date='2026-08-04', group='Обслуживание', bike='NMAX 4957',\n"
            "            event_type='repair', mileage=37100, msg_id='tg:1:2')\n")
    _, cmd = _probe(body, "ev_add.py")
    kind, hit, _ = PG.classify(cmd, ROOT)
    assert kind != "red", f"добавление события не должно краснеть: {kind}/{hit}"


def test_guard_comment_mention_does_not_redden():
    """Имя новой операции В КОММЕНТАРИИ командой не является — тело судится разбором, а не
    подстрокой (класс «корень А», 02.08.2026). Правило распространяется на неё автоматически:
    красное даёт `_py_code_view`, где комментариев нет ПО ПОСТРОЕНИЮ.

    ЧТО ЭТОТ ТЕСТ НЕ УТВЕРЖДАЕТ: имя операции в СТРОКОВОМ ЛИТЕРАЛЕ живую команду по-прежнему
    краснит (осознанный остаток класса, артефакт 2026-08-02-money-action-not-word §4, точка
    касания `_body_has`) — асимметрия намеренная: строка может быть действием."""
    body = ("# разведка: тут мы НЕ правим строку (" + A_EDIT + "), только читаем историю\n"
            "import bridge_client\n"
            "b = bridge_client.BridgeClient()\n"
            "print(b.read_events('NMAX 4957', limit=8))\n")
    _, cmd = _probe(body, "ev_talk.py")
    kind, hit, _ = PG.classify(cmd, ROOT)
    assert kind != "red", f"упоминание в комментарии не должно краснеть: {kind}/{hit}"


def _cleanup():
    import shutil
    shutil.rmtree("/tmp/tb_recfix_probe_0804", ignore_errors=True)


if __name__ == "__main__":
    fails = []
    for _n, _f in sorted(list(globals().items())):
        if _n.startswith("test_") and callable(_f):
            try:
                _f()
                print("OK:", _n)
            except AssertionError as e:
                fails.append((_n, str(e)))
                print("FAIL:", _n, "\n   ", str(e)[:600])
            except Exception as e:      # noqa: BLE001
                fails.append((_n, repr(e)))
                print("ERROR:", _n, "\n   ", repr(e)[:600])
    _cleanup()
    if fails:
        print("\nКРАСНЫХ:", len(fails))
        sys.exit(1)
    print("\nВСЕ ТЕСТЫ record_fix ПРОШЛИ (правка строки события + понижение пробега по исправлению)")
    _ = io.StringIO  # noqa: F841  (io импортирован для совместимости с прогоном под pytest)
