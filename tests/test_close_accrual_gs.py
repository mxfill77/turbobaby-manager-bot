# -*- coding: utf-8 -*-
"""CLOSEACCRUAL1910 (19.10.2026) — сторона МОСТА: начисление доплат листа закрытия в K формулой и расшифровка
примечанием к A (решение владельца 19.10 23:3x; условия Codex TB-REVIEW-1910-2400 (1)–(5)).

Сборка `bridge_build_close_accrual/` (Booking.js, Closing.js) поверх зеркала прода `bridge_prod/` @88; реальный код
гоняется node-харнессом tests/close_accrual_gs_harness.js (правило srcOf). Покрытие:
  * синтаксис файлов сборки; харнесс зелёный и несёт ключевые случаи (части и привязка closing_upsert; основа K
    число / формула / пусто / текст / ошибка; стоп до записей на нечисловой части, чужой брони, чужом id; та же
    операция дважды; повтор после сбоя между K и примечанием; сбой записи K; правка листа между записями; замок
    занят / снят; paid_total только opt-in; ВЕРСИЯ листа закрытия — замечание приёмки 20.10: часть добавлена /
    уменьшена / снята, строки этой брони нет, строка переехала → отказ closing_changed целиком до записей с листом
    в ответе; тот же состав при новом штампе — начисляем; лист правят после плана — partial без записи K);
  * паспорт сборки — правило ТРЁХ состояний `tests/build_states.py` (состояние «а», база == зеркало @88);
  * прежний набор tests/booking_gs_harness.js на СБОРКЕ: всё прежнее зелёное, кроме ровно одного случая
    close.paid-written — запись итога в K без opt-in снята намеренно (условие (5));
  * всё, кроме closeBooking (и нового блока CLOSEACCRUAL), в Booking.js — побайтно зеркало; в Closing.js поиск строки
    (closingFind_), closingGet_, closingList_ — побайтно зеркало (фоллбэк по байку не расширен и не сужен);
  * в коде начисления у ячейки A — только getNote/setNote (статус A пишет лишь прежняя строка «Завершена»); замок
    назван не атомарностью.
Данные синтетические, сети нет; node — без файлов на диске (stdin)."""
import hashlib
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_states                                                    # noqa: E402  (правило трёх состояний)

BUILD = os.path.join(ROOT, "bridge_build_close_accrual")
MIRROR = os.path.join(ROOT, "bridge_prod")
HARNESS = os.path.join(ROOT, "tests", "close_accrual_gs_harness.js")
OLD_HARNESS = os.path.join(ROOT, "tests", "booking_gs_harness.js")

_cache = {}


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _node(args, env=None, stdin=None):
    p = subprocess.run(["node"] + args, input=stdin, capture_output=True, text=True, timeout=60, encoding="utf-8",
                       env=env)
    return p.returncode, p.stdout, p.stderr


def harness():
    if "res" not in _cache:
        _cache["res"] = _node([HARNESS])
    return _cache["res"]


def _top_chunks(src):
    """Верхнеуровневые куски файла: имя функции/переменной → текст до следующего куска."""
    out, name, buf = {}, None, []
    for line in src.splitlines(keepends=True):
        m = re.match(r"(?:function\s+([A-Za-z0-9_]+)\s*\(|var\s+([A-Za-z0-9_]+)\s*=)", line)
        if m:
            if name is not None:
                out[name] = "".join(buf)
            name, buf = (m.group(1) or m.group(2)), []
        if name is not None:
            buf.append(line)
    if name is not None:
        out[name] = "".join(buf)
    return out


def _strip_trailing_comment(chunk):
    """Хвост куска — комментарий-шапка СЛЕДУЮЩЕЙ функции: для сравнения тел его отрезаем."""
    lines = chunk.rstrip("\n").split("\n")
    while lines and (lines[-1].strip() == "" or lines[-1].lstrip().startswith(("/**", "*", "//", "*/"))):
        lines.pop()
    return "\n".join(lines)


def test_build_js_syntax():
    for name in ("Booking.js", "Closing.js"):
        code, out, err = _node(["--check", os.path.join(BUILD, name)])
        assert code == 0, f"{name}: {err}"


def test_harness_all_green():
    code, out, err = harness()
    assert code == 0, f"харнесс красный:\nstdout={out[-3000:]}\nstderr={err[-2000:]}"
    res = json.loads(out)
    failed = [c for c in res["cases"] if not c["pass"]]
    assert not failed, json.dumps(failed, ensure_ascii=False, indent=1)
    assert len(res["cases"]) >= 80, len(res["cases"])


def test_harness_covers_key_cases():
    code, out, err = harness()
    names = {c["name"] for c in json.loads(out)["cases"]}
    for need in (
            # (1) части и привязка
            "closing.components-raw", "closing.match-booking-id", "closing.booking-of-id", "closing.match-new",
            "closing.match-bike-fallback", "closing.match-new-no-id", "closing.booking-ambiguous",
            "closing.booking-not-found", "closing.crm-read-only", "closing.headers-mirror",
            # (3)(4) основа K и примечание
            "acc.number.k-formula", "acc.number.note-prev-kept", "acc.number.note-done-line", "acc.number.order",
            "acc.number.a-value-is-status", "acc.formula.grouped", "acc.empty.k-untouched", "acc.empty.note-only",
            "acc.text.k-untouched", "acc.fraction.k-untouched", "acc.error.k-untouched",
            # (1)(2) стоп до записей
            'acc.bad-component."=1+1"', 'acc.bad-component."half"', 'acc.bad-component."-5"',
            'acc.bad-component."NaN"', 'acc.bad-component."Infinity"', 'acc.bad-component."1e3"',
            'acc.bad-component."12.5"', "acc.binding.wrong-booking-id", "acc.binding.wrong-row",
            "acc.binding.wrong-day", "acc.payload-mismatch.id", "acc.payload-mismatch.closing-row",
            "acc.marker-other-addends", "acc.other-op-recorded",
            # (2) та же операция, повтор, частичный исход
            "acc.twice.second-not-found", "acc.reopened-done.no-double-add", "acc.partial.k-then-note-fail",
            "acc.partial.recover-done", "acc.k-write-fail.unknown", "acc.k-write-fail.retry-partial-no-write",
            "acc.note-fail.unknown-no-k", "acc.prestate-changed", "acc.prestate-row-identity",
            "acc.k-readback-mismatch",
            # замок
            "lock.busy-no-writes", "lock.not-taken-without-accrual", "lock.released-on-write-failed",
            "acc.lock.taken-released", "acc.partial.lock-released",
            # (5) paid_total
            "paid.ignored-without-opt-in", "paid.written-with-opt-in", "paid.opt-in-only-boolean",
            "paid.ignored-with-accrual",
            "opid.independent", "opid.lits",
            # ВЕРСИЯ записи листа закрытия (замечание приёмки 20.10): часть добавлена / уменьшена / снята, строки нет,
            # строка переехала — отказ целиком до записей и лист в ответе; тот же состав — начисляем; правка листа
            # после плана — partial без записи K; лист не прочитан — стоп начисления
            "ver.added.refused-no-writes", "ver.added.receipt-stopped", "ver.added.closing-now",
            "ver.added.new-op-differs", "ver.added.new-op-done", "ver.reduced.refused-no-writes",
            "ver.reduced.new-op-done", "ver.waived.refused", "ver.row-gone.refused", "ver.row-gone.no-bike-fallback",
            "ver.row-moved.refused", "ver.same-parts.reupsert-done", "ver.number-cell-same-lit",
            "ver.closing-unread.stop", "ver.changed-at-prestate.partial", "ver.reply-of-same-shape",
            "ver.reply-of-not-found"):
        assert need in names, f"нет кейса {need}"


def test_build_passport():
    """Паспорт сборки против зеркала — состояние «а» (не выложена, база == зеркало @88)."""
    passport = json.loads(_read(os.path.join(BUILD, "BUILD.json")))
    assert sorted(passport["changed"]) == ["Booking.js", "Closing.js"]
    assert passport["added"] == [] and passport.get("delivered_as_version") is None
    res = build_states.judge(BUILD, MIRROR)
    assert not res["problems"], res
    assert res["state"] == "a", res
    assert not os.path.exists(os.path.join(BUILD, ".clasp.json"))


def test_old_harness_on_build_only_paid_written_differs():
    """Прежний набор closeBooking/createBooking/activateBooking на СБОРКЕ: ровно один случай другой — K без opt-in."""
    env = dict(os.environ, BOOKING_JS_UNDER_TEST=os.path.join(BUILD, "Booking.js"))
    code, out, err = _node([OLD_HARNESS], env=env)
    res = json.loads(out)
    failed = sorted(c["name"] for c in res["cases"] if not c["pass"])
    assert failed == ["close.paid-written"], failed
    code_m, out_m, _ = _node([OLD_HARNESS])
    assert code_m == 0 and json.loads(out_m)["failed"] == 0, "на зеркале прежний набор обязан быть зелёным"
    assert json.loads(out_m)["total"] == res["total"]


def test_build_rest_of_booking_is_mirror():
    """Booking.js: всё, кроме closeBooking и нового блока CLOSEACCRUAL, — побайтно зеркало."""
    old = _top_chunks(_read(os.path.join(MIRROR, "Booking.js")))
    new = _top_chunks(_read(os.path.join(BUILD, "Booking.js")))
    added = set(new) - set(old)
    assert added == {"CLOSE_ACCRUAL", "closeAccrualLit_", "closeAccrualDay_", "closeAccrualOpId_",
                     "closeAccrualMarks_", "closeAccrualNorm_", "closeAccrualIdent_", "closeAccrualK_",
                     "closeAccrualKText_", "closeAccrualJoin_", "closeAccrualSameClosing_", "closeAccrualLine_",
                     "closeAccrualPlan_", "closeAccrualApply_", "closeBookingRun_"}, sorted(added)
    assert set(old) - set(new) == set()
    for name in old:
        if name == "closeBooking":
            continue
        assert _strip_trailing_comment(new[name]) == _strip_trailing_comment(old[name]), f"Booking.js: {name} изменён"


def test_build_rest_of_closing_is_mirror():
    """Closing.js: поиск строки (фоллбэк по байку) и чтения — побайтно зеркало; добавлены только чтения начисления:
    closingBookingOf_ (бронь CRM строки), closingRowById_ и closingReplyOf_ (строка по ТОЧНОМУ booking_id и её ответ
    вида closing_upsert — для сверки версии под замком closeBooking)."""
    old = _top_chunks(_read(os.path.join(MIRROR, "Closing.js")))
    new = _top_chunks(_read(os.path.join(BUILD, "Closing.js")))
    assert set(new) - set(old) == {"closingBookingOf_", "closingRowById_", "closingReplyOf_"}, \
        sorted(set(new) - set(old))
    for name in ("closingNum_", "CLOSING_CLOSED", "closingFind_", "closingGet_", "closingList_"):
        assert _strip_trailing_comment(new[name]) == _strip_trailing_comment(old[name]), f"Closing.js: {name} изменён"


def test_accrual_code_shape():
    """Ячейка A в начислении — только примечание; формула K — только setFormula; замок не назван атомарностью."""
    src = _read(os.path.join(BUILD, "Booking.js"))
    ch = _top_chunks(src)
    acc_code = "".join(ch[n] for n in ch if n.startswith("closeAccrual"))
    assert "setValue(" not in acc_code, "начисление не пишет значения ячеек — только setNote/setFormula"
    assert "setNote(" in acc_code and "getNote(" in acc_code and "setFormula(" in acc_code
    run = ch["closeBookingRun_"]
    assert run.count("setValue('Завершена')") == 1 and run.count("BOOKING.COL.STATUS).setValue") == 1
    assert "p.paid_total_opt_in === true && !hasAcc" in run
    assert "ЗАМОК — НЕ АТОМАРНОСТЬ" in src
    assert "LockService.getScriptLock()" in ch["closeBooking"] and "releaseLock()" in ch["closeBooking"]
    assert "finally" in ch["closeBooking"]


# МУТАНТЫ: каждый — порча одного условия Codex 2400; харнесс обязан её поймать (исходник — через stdin, файлов нет)
MUTANTS = [
    ("binding-skip", "Booking.js", "    return stop('binding_mismatch');", "    ;"),
    ("opid-skip", "Booking.js", "if (op !== a.close_op_id) return stop('payload_mismatch');",
     "if (false) return stop('payload_mismatch');"),
    ("done-before-k", "Booking.js", "var line = closeAccrualLine_(pl, 'IN_PROGRESS');",
     "var line = closeAccrualLine_(pl, 'DONE');"),
    ("no-prestate", "Booking.js", "var same = id1.bid === pl.id0.bid", "var same = true || id1.bid === pl.id0.bid"),
    ("no-grouping", "Booking.js", "pl.formula = '=(' + k0.f.replace(/^=/, '') + ')' + pl.adds;",
     "pl.formula = k0.f + pl.adds;"),
    ("empty-is-zero", "Booking.js", "pl.base = 'empty'; pl.act = 'note_only';",
     "pl.base = 'number'; pl.act = 'write'; pl.formula = '=0' + pl.adds;"),
    ("paid-no-opt-in", "Booking.js", "if (p.paid_total_opt_in === true && !hasAcc) {", "if (!hasAcc) {"),
    ("same-op-forgotten", "Booking.js", "var mine = marks.filter(function (m) { return m.op === op; });",
     "var mine = [];"),
    ("lit-fraction", "Booking.js", "if (!isFinite(v) || Math.floor(v) !== v) return null;",
     "if (!isFinite(v)) return null;"),
    ("lit-formula-text", "Booking.js", "/^\\d{1,9}$/.test(v)", "/^[\\d=+]{1,9}$/.test(v)"),
    ("lock-not-released", "Booking.js", "    lock.releaseLock();", "    ;"),
    ("prev-note-dropped", "Booking.js", "return prev ? prev + '\\n' + line : line;", "return line;"),
    ("closing-bike-as-booking", "Closing.js", "binding(found.row, bid ? 'booking_id' : 'bike')",
     "binding(found.row, 'booking_id')"),
    ("closing-parts-from-total", "Closing.js", "damage: rec.damage, other: rec.other };",
     "damage: total, other: rec.other };"),
    # ВЕРСИЯ записи листа закрытия (замечание приёмки 20.10); пятое поле — кейс харнесса, который ОБЯЗАН покраснеть
    # (мутант пойман именно сверкой версии, а не побочным эффектом)
    ("version-skip", "Booking.js", "if (!closeAccrualSameClosing_(cl, crow, lits)) {", "if (false) {",
     "ver.reduced.refused-no-writes"),
    ("version-parts-not-compared", "Booking.js",
     "    if (closeAccrualLit_(cl.cur[CLOSE_ACCRUAL.PARTS[i]]) !== lits[i]) return false;", "    ;",
     "ver.added.refused-no-writes"),
    ("version-row-not-compared", "Booking.js", "if (!cl || cl.row !== crow) return false;", "if (!cl) return false;",
     "ver.row-moved.refused"),
    ("version-changed-close-runs", "Booking.js",
     "if (plan && plan.act === 'stop' && plan.reason === 'closing_changed') {", "if (false) {",
     "ver.added.refused-no-writes"),
    ("version-prestate-skip", "Booking.js",
     "var sameCl = same && closeAccrualSameClosing_(closingRowById_(pl.id0.bid), pl.crow, pl.lits);",
     "var sameCl = true;", "ver.changed-at-prestate.partial"),
    ("version-row-by-bike", "Closing.js",
     "return closingFind_(getBotTab_(BOTDATA.TABS.CLOSING), BOTDATA.CLOSING_HEADERS, bid, '', '');",
     "return closingFind_(getBotTab_(BOTDATA.TABS.CLOSING), BOTDATA.CLOSING_HEADERS, '', 'CB 300CC R 9011', '');",
     "ver.row-gone.refused"),
]


def test_mutants_killed():
    assert len(MUTANTS) >= 18
    alive, wrong = [], []
    for name, fname, old, new, *want in MUTANTS:
        src = _read(os.path.join(BUILD, fname))
        assert src.count(old) == 1, f"мутант {name}: «было» встречается {src.count(old)} раз — мутант не о том"
        code, out, err = _node([HARNESS, "--mutant"], stdin=json.dumps({fname: src.replace(old, new)}))
        if code == 0:
            alive.append(name)
        elif want:
            try:
                red = {c["name"] for c in json.loads(out)["cases"] if not c["pass"]}
            except (ValueError, KeyError):
                red = set()                       # харнесс упал целиком — нужный кейс не назван
            if want[0] not in red:
                wrong.append((name, want[0], sorted(red)[:5]))
    assert not alive, f"мутанты выжили (харнесс их не видит): {alive}"
    assert not wrong, f"мутант пойман не тем кейсом: {wrong}"


def test_mirror_untouched():
    """Зеркало прода не правилось: стройка — только в каталоге сборки."""
    m = json.loads(_read(os.path.join(MIRROR, "MIRROR.json")))["files_sha256"]
    for name in ("Booking.js", "Closing.js", "Bridge.js"):
        assert _sha(os.path.join(MIRROR, name)) == m[name], name


if __name__ == "__main__":
    tests = [(k, v) for k, v in list(globals().items()) if k.startswith("test_") and callable(v)]
    bad = 0
    for k, fn in tests:
        try:
            fn()
            print(f"OK   {k}")
        except Exception as e:   # noqa: BLE001 — печатаем и считаем
            bad += 1
            print(f"FAIL {k}: {e}")
    print(f"close_accrual_gs: {len(tests) - bad}/{len(tests)} зелёных")
    sys.exit(1 if bad else 0)
