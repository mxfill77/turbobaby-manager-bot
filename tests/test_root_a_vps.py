# -*- coding: utf-8 -*-
"""КОРЕНЬ А НА СЕРВЕРНОЙ ПОЛОСЕ: три места, где решение про РАЗРЕШЕНИЕ принималось по совпадению
слова в тексте, который этому месту никто не обещал (02.08.2026).

Разбор пришёл с ПК-полосы (артефакт `docs/artifacts/2026-08-02-root-a-five-coincidences.md`,
задача 180): из пяти совпадений два починены там (A-30 — разобранный вызов вместо подстроки,
A-36 — совет владельцу по данным ряда), три оставлены остатками с адресами — они в файлах VPS.

(B-5) `orchestrator_daemon._is_headless_impossible` в `_convert_other_approved`
      ЧЕЙ ТЕКСТ: заявка исполнителя (`what`) И **ПРОЗА ТЗ ВЛАДЕЛЬЦА** (`orig`).
      ЧТО ЛОМАЛОСЬ: любое из 15 слов в прозе владельца — «разберись, почему add_transaction не
      логируется» — закрывало УЖЕ ОДОБРЕННУЮ им заявку терминальной картой «сделай руками», не
      попробовав ни разу. Его «да» съедало совпадение слова в его же формулировке.
      ПОЧИНЕНО: судим по ЗАЯВКЕ, которую владелец и подтверждал. Слой 2 — экономия перерождения,
      а не запрет: несработавший стоит РОВНО одно перерождение (слой 1 закроет петлю).

(B-1) `pretool_guard._analyze`, скан RED_TOKENS
      ЧЕЙ ТЕКСТ: исходник скрипта, сочинённый моделью, вместе с комментариями и докстрингами.
      ЧТО ЛОМАЛОСЬ, ОБА КОНЦА: имя операции в КОММЕНТАРИИ давало красное с ЧУЖИМ классом
      (карточка «проводка ДЕНЕГ в кассу» об операции, которой в скрипте нет); а `confirmed=true`
      проверялся ПЯТЬЮ написаниями списком — `confirmed  =  True` не совпадал ни с одним из
      пяти, и БОЕВАЯ запись в Лист1 проходила МОЛЧА.
      ПОЧИНЕНО: тело судится каноническим разбором (ast). Комментарий кодом не является;
      `confirmed` со значением истина опознаётся как РАЗОБРАННЫЙ аргумент/ключ/присваивание.
      Разбор не удался → прежняя подстрока, байт-в-байт (fail-closed).

(B-3) `pretool_guard._detail_parts` — ОБЪЕКТ карточки
      ЧЕЙ ТЕКСТ: тот же исходник модели; извлечение видело только ЛИТЕРАЛ.
      ЧТО ЛОМАЛОСЬ: `set_fleet_oil(number=plate, oil_km=km)` — объект не извлекался, `card_gate`
      гасил карточку, и владелец о НАСТОЯЩЕЙ записи в Лист1 не узнавал вовсе.
      ПОЧИНЕНО: разобранный вызов различает «аргумента НЕТ» (голое упоминание) и «аргумент ЕСТЬ,
      значение вычисляется». ДЕНЬГИ НЕ ТРОНУТЫ: add_transaction/void_last ∈ _ALWAYS_CARD, их
      карточка не гасилась никогда — чинить там нечего (секция 4 показывает это чтением кода).

ТЕСТ НИЧЕГО НЕ ИСПОЛНЯЕТ И НИЧЕГО НЕ ШЛЁТ: зовутся ЧИСТЫЕ функции (classify/card_min/card_gate)
и `_convert_other_approved` с подставным мостом. Ни одна строка не уходит в shell, сети нет.
Красные литералы собраны КОНКАТЕНАЦИЕЙ — иначе гард краснеет на самом файле теста.
Денежных путей тест не касается ВООБЩЕ: все фикстуры — парк/CRM.
"""
import atexit
import os
import shutil
import sys
import tempfile
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["PRETOOL_NOPUSH"] = "1"          # ни одна карточка не уйдёт в Telegram
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ.setdefault("PLAN_ADAPT", "0")
os.environ["CURATOR"] = "0"
os.environ["STEP_SELFHEAL"] = "0"

if "fcntl" not in sys.modules:               # клон на ПК: POSIX-локов нет, карточка от них не зависит
    try:
        import fcntl  # noqa: F401
    except ImportError:
        _fake = types.ModuleType("fcntl")
        _fake.flock = lambda *a, **k: None
        _fake.LOCK_EX = 2
        sys.modules["fcntl"] = _fake

import pretool_guard as PG          # noqa: E402
import orchestrator_daemon as OD    # noqa: E402

res = []


def ok(c, label):
    print(("  PASS " if c else "  FAIL ") + label)
    res.append(bool(c))
    return bool(c)


# ── красные литералы по кускам ────────────────────────────────────────────────
SFO = "set_fleet_" + "oil"
CB = "create_" + "booking"
AT = "add_" + "transaction"
DOW = "DO" + "WRITE"
CONF_TIGHT = "confirmed" + "=" + "true"
CONF_WIDE = "confirmed" + "  =  " + "True"        # ДВА пробела — мимо всех пяти написаний
PY = "venv/bin/python3"

TMP = tempfile.mkdtemp(prefix="roota_").replace(os.sep, "/")
atexit.register(shutil.rmtree, TMP, ignore_errors=True)


def fixture(name, body):
    """Untracked .py вне git-индекса → гард читает ТЕЛО (trust-by-origin на него не действует)."""
    p = os.path.join(TMP, name)
    with open(p, "w", encoding="utf-8") as f:
        f.write(body)
    return p


def classify(path_or_cmd):
    """Живой порядок: classify() взводит разбор тела, card_min() его читает (как в main())."""
    cmd = path_or_cmd if path_or_cmd.startswith(PY) else PY + " " + path_or_cmd
    return PG.classify(cmd, ROOT)


# ══ (1) B-1: имя операции в КОММЕНТАРИИ — не операция ═════════════════════════
print("(1) B-1 · тело судится разбором, а не подстрокой:")

fx_comment = fixture("fx_comment.py",
                     "# запись в парк тут НЕ делается: " + SFO + "(number='6789') оставлено на потом\n"
                     '"""Разведка пробега. Ничего не пишет."""\n'
                     "print('report only')\n")
kind, hit, _ = classify(fx_comment)
ok(kind == "green" and hit == "", "имя операции ТОЛЬКО в комментарии → не красное (было: red " + SFO + ")")

fx_call = fixture("fx_call.py", "import bridge_client as bc\nbc." + SFO + "(number='6789', oil_km=27000)\n")
kind, hit, _ = classify(fx_call)
ok(kind == "red" and hit == SFO, "настоящий вызов → красное как было")

fx_string = fixture("fx_string.py", "import bridge_client as bc\nbc._call('" + SFO + "', number='6789')\n")
kind, hit, _ = classify(fx_string)
ok(kind == "red" and hit == SFO, "имя в СТРОКЕ (может быть действием) → красное, сомнение в сторону красного")

fx_docstring = fixture("fx_doc.py", '"""Модуль про ' + AT + ' — только описание."""\nprint(1)\n')
kind, hit, _ = classify(fx_docstring)
ok(kind == "red" and hit == AT, "докстринг остаётся красным намеренно (строка = возможное действие)")

fx_broken = fixture("fx_broken.py", "# " + SFO + " упомянут в комментарии\ndef (:\n")
kind, hit, _ = classify(fx_broken)
ok(kind == "red" and hit == SFO, "тело не разобралось → ПРЕЖНЯЯ подстрока (fail-closed)")

fx_dowrite = fixture("fx_dowrite.py", "# " + DOW + "=1 — этот скрипт реально пишет\nprint(1)\n")
kind, hit, _ = classify(fx_dowrite)
ok(kind == "red" and hit == DOW, DOW + " в комментарии-шапке остаётся красным (это самообъявление автора)")

# ══ (2) B-1: confirmed судится по разобранному значению, а не по написанию ════
print("(2) B-1 · confirmed=ИСТИНА в любом написании:")

fx_wide = fixture("fx_wide.py", "import bridge_client as bc\nbc._call('sheet_write', " + CONF_WIDE + ")\n")
kind, hit, _ = classify(fx_wide)
ok(kind == "red" and hit == "confirmed",
   "`confirmed  =  True` (два пробела) в теле → красное (было: молча проходило)")

kind, hit, _ = PG.classify(PY + ' -c "bc._call(\'sheet_write\', ' + CONF_WIDE + ')"', ROOT)
ok(kind == "red" and hit == "confirmed", "то же в САМОЙ команде → красное (было: молча проходило)")

fx_json = fixture("fx_json.py", "p = {'" + "confirmed" + "'  :  True}\nprint(p)\n")
kind, hit, _ = classify(fx_json)
ok(kind == "red" and hit == "confirmed", "ключ словаря `'confirmed' : True` → красное")

fx_false = fixture("fx_false.py", "import bridge_client as bc\nbc._call('x', confirmed=False)\n")
kind, hit, _ = classify(fx_false)
ok(kind == "green", "confirmed=False красным не становится (значение читается, а не имя)")

fx_conf_comment = fixture("fx_conf_comment.py",
                          "# гейт требует " + CONF_TIGHT + " на каждую запись — тут записи нет\nprint(1)\n")
kind, hit, _ = classify(fx_conf_comment)
ok(kind == "green", "`" + CONF_TIGHT + "` ТОЛЬКО в комментарии → не красное (было: red confirmed)")

fx_unconf = fixture("fx_unconf.py", "unconfirmed = True\nprint(unconfirmed)\n")
kind, _hit, _ = classify(fx_unconf)
ok(kind == "green", "`unconfirmed = True` — не confirmed (граница слова цела)")

# ══ (3) B-3: объект вызова, чьё значение вычисляется ══════════════════════════
print("(3) B-3 · «аргумента нет» и «значение вычисляется» — разные вещи:")

fx_var = fixture("fx_var.py",
                 "import bridge_client as bc\nplate = input()\nkm = 27000\n"
                 "bc." + SFO + "(number=plate, oil_km=km)\n")
kind, hit, blob = classify(fx_var)
obj, num = PG.card_min(hit, blob)
ok(kind == "red" and hit == SFO, "вызов с переменными → красное (как было)")
ok("вычисляется" in obj, "ОБЪЕКТ назван: «" + (obj or "—") + "» (было: пусто)")
ok(PG.card_gate(hit, obj, num) is True, "карточка РОЖДАЕТСЯ (было: card_skipped, владелец не знал)")

fx_bare = fixture("fx_bare.py", "print('" + SFO + "')\n")
kind, hit, blob = classify(fx_bare)
obj, num = PG.card_min(hit, blob)
ok(kind == "red" and hit == SFO and not obj.strip(),
   "голое упоминание в строке → объекта НЕТ, карточки нет (правило минимума цело)")
ok(PG.card_gate(hit, obj, num) is False, "card_gate на безобъектном упоминании — прежний False")

fx_crm = fixture("fx_crm.py",
                 "import bridge_client as bc\nwho = 'x'\nbc." + CB + "(bike='6334', name=who)\n")
kind, hit, blob = classify(fx_crm)
obj, _n = PG.card_min(hit, blob)
ok(kind == "red" and hit == CB and "байк 6334" in obj and "вычисляется" in obj,
   "CRM: литеральный байк + вычисляемый клиент — названы оба («" + obj + "»)")

fx_lit = fixture("fx_lit.py", "import bridge_client as bc\nbc." + SFO + "(number='6789', oil_km=27000)\n")
kind, hit, blob = classify(fx_lit)
obj, num = PG.card_min(hit, blob)
ok(obj == "байк 6789" and num == "пробег 27000", "литеральный вызов извлекается ровно как раньше (регресс)")

# ══ (4) ГРАНИЦЫ: денежный гейт и изоляция проб не ослаблены ═══════════════════
print("(4) границы — денежный гейт и правило минимума на месте:")
ok(PG._ALWAYS_CARD == ("void_last", "add_transaction"),
   "_ALWAYS_CARD как был: деньги спрашивают всегда, объект им не гейт")
ok(PG.card_gate("void_" + "last", "", "") is True and PG.card_gate(AT, "", "") is True,
   "денежная карточка рождается и БЕЗ объекта (гейт денег не тронут)")
ok(PG.card_gate(SFO, "", "") is False, "не-деньги без объекта — прежний журнал")
ok(PG._carried_bit(AT, "bike") == "" and PG._carried_bit("void_" + "last", "client") == "",
   "разбор объекта к деньгам не применяется вовсе (ветка _detail_parts не тронута)")
ok(PG.is_probe("PRETOOL_TEST_RUN=1 " + PY + " x.py", env={}) is True
   and PG.is_probe(PY + " x.py", env={}) is False,
   "признак пробы не тронут (регресс изоляции; env явный — иначе мерили бы своё окружение)")

# ══ (5) B-5: слой 2 судит заявку, а не прозу ТЗ владельца ═════════════════════
print("(5) B-5 · «да» владельца не съедается словом в его же формулировке:")


class _FakeBridge:
    """Мост-пустышка: ничего не сети, только запоминает, что демон решил сделать."""

    def __init__(self):
        self.completed = []
        self.enqueued = []

    def complete_task(self, tid, status, result=""):
        self.completed.append((str(tid), status, result))
        return {"ok": True}

    def enqueue_task(self, frm, text):
        self.enqueued.append((frm, text))
        return {"ok": True, "id": 777}


def convert(what, orig):
    fake = _FakeBridge()
    real = OD.bc
    OD.bc = fake
    try:
        OD._convert_other_approved("500", {"task_text": orig}, what)
    finally:
        OD.bc = real
    return fake


CARD_CLEAN = "op=other | нужно подтверждение на правку конфига темы 328"
PROSE_WITH_WORD = ("разберись, почему проводка " + AT + " не попадает в журнал, и почини логирование")

f = convert(CARD_CLEAN, PROSE_WITH_WORD)
ok(bool(f.enqueued) and "конверт одобренной заявки" in f.enqueued[0][1],
   "слово из прозы ТЗ владельца больше не хоронит одобренную заявку → конверт поставлен")
ok(f.completed and f.completed[0][1] == "done", "исходная заявка закрыта done со ссылкой на конверт")

f = convert("op=other | " + AT + " на 500 в кассу", "почини логирование")
ok(not f.enqueued and f.completed and f.completed[0][1] == "failed"
   and "РУЧНОЕ ДЕЙСТВИЕ" in f.completed[0][2],
   "заведомо невозможное В САМОЙ ЗАЯВКЕ → терминальная ручная карта (слой 2 цел)")

f = convert("op=other | выложи изменения через clasp redeploy", "почини логирование")
ok(not f.enqueued and f.completed and f.completed[0][1] == "failed",
   "clasp в заявке → терминальная карта (защита не ослаблена)")

ok(OD._is_headless_impossible("op=other | " + AT + " 500") is True
   and OD._is_headless_impossible("op=other | правка конфига") is False,
   "сам предикат не тронут — изменилось ТОЛЬКО что ему подают")

print("\nИТОГ:", "ВСЕ PASS" if all(res) else "ЕСТЬ FAIL (%d/%d)" % (sum(res), len(res)))
sys.exit(0 if all(res) else 1)
