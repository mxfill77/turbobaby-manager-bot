# -*- coding: utf-8 -*-
"""ОБЯЗАТЕЛЬНЫЙ МИНИМУМ красной карточки (28.07.2026).

Доктрина: карточка красной зоны читается за ТРИ СЕКУНДЫ и несёт ЧЕТЫРЕ вещи — ЧТО меняется,
у какого ОБЪЕКТА, какое ЧИСЛО и одну строку ОТКАТА. Нет ОБЪЕКТА → карточки НЕТ ВОВСЕ: вместо неё
строка `card_skipped` в журнале гарда (ни пуша владельцу, ни маркер-конверта демону).
Решение хука при этом НЕ слабеет — ask остаётся, без «да» команда не исполняется.
ЖЁСТКИЙ БЛОК и ДЕНЬГИ — ИСКЛЮЧЕНИЯ: приходят всегда, минимум им не указ.

ПРАВИЛО 29.07.2026 (секция 9) — ЧИСЛО БОЛЬШЕ НЕ ГЕЙТ. Было «нет объекта ИЛИ числа → карточки нет»,
и это молча съело ЧЕТЫРЕ операции, которые числа не несут ПО СВОЕЙ ПРИРОДЕ: отмену последней
проводки (ДЕНЬГИ), стоп сервиса по имени, pkill по имени, SQL в чужую БД. Гард не слабел (ask
оставался), но владелец о них не узнавал — а первая из них денежная. Теперь гейт один и общий с
полосой ПК — `card_gate()`: объект обязателен всегда, число живёт там, где операция его несёт,
и честным прочерком там, где не несёт.

КОРЕНЬ, который здесь и закрыт (секция 3): «есть ли объект» решала цифра в ТЕКСТЕ ГОТОВОЙ
карточки (marker_has_object → \\d), а шаблон операций с парком несёт «Лист1» — цифра там есть
ВСЕГДА. Само же извлечение объекта искало plate=/client=/wallet=/\\bkm=, тогда как ЖИВОЙ Bridge
зовётся number=/name=/group=/oil_km= — то есть не срабатывало НИ РАЗУ. Чинится ИЗВЛЕЧЕНИЕ
(_detail_parts/card_min), а не вторая линия.

ТЕСТ НИЧЕГО НЕ ИСПОЛНЯЕТ: чистые функции + main() в ЭТОМ процессе (stdin/stdout/_push подменены).
Ни одна проверяемая строка не уходит в shell, сеть не дёргается (_push замещён счётчиком).
Красные литералы собраны КОНКАТЕНАЦИЕЙ (образец — test_pretool_hardblock): иначе гард краснеет
на САМОМ файле теста и правка файла становится невозможной.
"""
import atexit
import io
import json
import os
import shutil
import sys
import tempfile
import types

# ROOT от файла, а не константой /root/… — тест обязан идти и на VPS, и в клоне на ПК.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["PRETOOL_NOPUSH"] = "1"       # страховка: ни одна карточка не уйдёт в Telegram

# pretool_guard тянет fcntl (POSIX-локи дедупа). Карточка от него не зависит: на ПК (Windows-клон)
# подставляем пустышку, на VPS импортируется настоящий модуль.
if "fcntl" not in sys.modules:
    try:
        import fcntl  # noqa: F401
    except ImportError:
        _fake = types.ModuleType("fcntl")
        _fake.flock = lambda *a, **k: None
        _fake.LOCK_EX = 2
        sys.modules["fcntl"] = _fake

import pretool_guard as PG  # noqa: E402

# ── красные литералы по кускам ────────────────────────────────────────────────
SFO = "set_fleet_" + "oil"
SFS = "set_fleet_" + "service"
AT = "add_" + "transaction"
VL = "void_" + "last"
CB = "create_" + "booking"
AB = "activate_" + "booking"
CU = "closing_" + "upsert"
DE = "delete_" + "event"
CONF = "confirmed" + "=" + "True"
ENVF = "." + "env"
PK = "p" + "kill"
SPL = "spl" + "inter"

TMP = tempfile.mkdtemp(prefix="pt_cm_").replace(os.sep, "/")   # forward slashes: shlex ест бэкслэши
atexit.register(shutil.rmtree, TMP, ignore_errors=True)
PY = "venv/bin/python3"

# ЖИВЫЕ формы вызова Bridge (bridge_client): именно их гард обязан разбирать.
LIVE_OIL = "bridge." + SFO + "(number='6789', oil_km=27000, " + CONF + ")"
LIVE_SERVICE = "bridge." + SFS + "(number='4255', kind='gear', km=31000, " + CONF + ")"
LIVE_MONEY = "bridge." + AT + "(group='Наличка', amount=-500, category='fuel')"
LIVE_BOOKING = "bridge." + CB + "(bike='6334', name='Jack', date_start='01.08.2026')"
LIVE_DELETE = "bridge." + DE + "(msg_id='-100123:456', group='Наличка')"
# Красное БЕЗ названного объекта. С 05.08.2026 это ВЫЗОВ, а не печатаемое слово: имя операции в
# строковом литерале красного больше не даёт (правило исполняющей позиции распространено на все
# имена, tests/test_literal_position.py), и прежняя фикстура `print('…')` перестала бы задевать
# ветку, ради которой заведена. Предмет теста не изменился — объекта у вызова по-прежнему нет.
BARE_WORD = "bridge." + SFO + "()"        # красный ВЫЗОВ БЕЗ объекта операции


def ok(c, label):
    print(("  PASS " if c else "  FAIL ") + label)
    return bool(c)


def fixture(name, body):
    path = TMP + "/" + name
    with open(path, "w", encoding="utf-8") as f:
        f.write("# фикстура\n" + body + "\n")
    return path


FX_LIVE = fixture("fx_fleet_live.py", LIVE_OIL)      # объект+число есть
FX_BARE = fixture("fx_bare_word.py", BARE_WORD)      # объекта нет
FX_ENTITY = fixture("fx_live_entity.py", "bridge." + CB + '(client="Jack", ' + CONF + ")")
FX_MONEY = fixture("fx_money_live.py", LIVE_MONEY)   # объект+число есть, ужесточению не подлежит

res = []


def run_main(cmd, task_id=""):
    """main() В ЭТОМ процессе (подпроцесс с /root/… на ПК-клоне не поднять) →
    (решение-JSON, [карточки в пуше], [события журнала])."""
    logp = TMP + "/guard_%d.log" % len(res)
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": ROOT})
    pushed, out = [], io.StringIO()
    saved = (sys.stdin, sys.stdout, PG._push, os.environ.get("CC_TASK_ID"))
    sys.stdin, sys.stdout, PG._push = io.StringIO(payload), out, pushed.append
    os.environ["PRETOOL_GUARD_LOG"] = logp
    os.environ["PRETOOL_BLOCK_DIR"] = TMP
    os.environ["CC_TASK_ID"] = task_id
    try:
        PG.main()
    except SystemExit:
        pass
    finally:
        sys.stdin, sys.stdout, PG._push = saved[0], saved[1], saved[2]
        os.environ.pop("PRETOOL_GUARD_LOG", None)
        os.environ.pop("PRETOOL_BLOCK_DIR", None)
        if saved[3] is None:
            os.environ.pop("CC_TASK_ID", None)
        else:
            os.environ["CC_TASK_ID"] = saved[3]
    events = []
    try:
        with open(logp, encoding="utf-8") as f:
            events = [json.loads(ln)["event"] for ln in f.read().splitlines() if ln.strip()]
    except OSError:
        pass
    return out.getvalue(), pushed, events


print("(1) минимум карточки: четыре подписанные строки, читается за три секунды:")
card = PG._card(SFO, LIVE_OIL)
for label in ("Что: ", "Объект: ", "Число: ", "Откат: "):
    res.append(ok(label in card, "в карточке есть строка «" + label.strip() + "»"))
res.append(ok("Объект: байк 6789" in card, "ОБЪЕКТ подписан и извлечён: байк 6789"))
res.append(ok("Число: пробег 27000" in card, "ЧИСЛО подписано и извлечено: пробег 27000"))
res.append(ok(len([b for b in card.split("Откат: ")[1].splitlines() if b.strip()][:1][0]) > 10
              and card.split("Откат: ")[1].splitlines()[0].strip() != "",
              "ОТКАТ — ровно одна непустая строка"))
body = [ln for ln in card.splitlines() if ln.strip()]
res.append(ok(len(body) <= 6, "карточка ≤6 строк (получили %d)" % len(body)))
res.append(ok(max(len(ln) for ln in body) <= 90,
              "самая длинная строка ≤90 символов (получили %d)" % max(len(ln) for ln in body)))
res.append(ok("Последствия" not in card, "абзац «Последствия» из карточки убран (три секунды)"))

print("(2) ЖИВОЙ формат Bridge разбирается (number=/name=/group=/oil_km=, а не идеализированный):")
for label, hit, blob, want_obj, want_num in (
        ("ТО масло", SFO, LIVE_OIL, "байк 6789", "пробег 27000"),
        ("ТО регламент", SFS, LIVE_SERVICE, "байк 4255", "пробег 31000"),
        ("касса", AT, LIVE_MONEY, "кошелёк Наличка", "сумма -500"),
        ("бронь", CB, LIVE_BOOKING, "байк 6334", "дата 01.08.2026"),
        ("удаление", DE, LIVE_DELETE, "событие -100123:456", "ключ -100123:456")):
    o, n = PG.card_min(hit, blob)
    res.append(ok(want_obj in o and want_num in n,
                  "%s: объект=%r число=%r" % (label, o, n)))
res.append(ok("вид ТО gear" in PG.card_min(SFS, LIVE_SERVICE)[0],
              "вид ТО (kind=) попал в объект регламентного ТО"))

print("(2б) обратная совместимость: прежние идеализированные имена полей тоже разбираются:")
old = "bridge." + SFO + "(plate='AB-5580', km=12345, " + CONF + ")"
o, n = PG.card_min(SFO, old)
res.append(ok(o == "байк AB-5580" and n == "пробег 12345", "plate=/km= → %r / %r" % (o, n)))

print("(3) КОРЕНЬ: объект больше НЕ «найден всегда» из-за номера листа в шаблоне:")
bare_card = PG._card(SFO, BARE_WORD)
res.append(ok("Лист1" in bare_card, "шаблон операции с парком по-прежнему несёт «Лист1» (цифра)"))
res.append(ok(PG.marker_has_object(SFO, bare_card) is False,
              "близорукость снята: проверка маркера смотрит строку «Объект:», а не «есть цифра»"))
res.append(ok(PG.card_min(SFO, BARE_WORD) == ("", ""),
              "новое ИЗВЛЕЧЕНИЕ честно говорит «объекта и числа нет»"))
res.append(ok(PG.card_min(SFO, "лист 1 строка 2 колонка I") == ("", ""),
              "цифры в тексте объектом не становятся — объект только из полей операции"))
res.append(ok(PG._card(SFO, BARE_WORD).count("—") >= 2, "прочерк в «Объект»/«Число» виден глазом"))

print("(4) нет объекта/числа → карточки НЕТ: строка в журнал, ask остаётся, пуша нет:")
out, pushed, events = run_main(PY + " " + FX_BARE)
res.append(ok('"ask"' in out, "решение хука по-прежнему ask (гард не ослаблен)"))
res.append(ok(pushed == [], "владельцу НЕ ушло ничего (ноль пушей)"))
res.append(ok(events == ["card_skipped"], "в журнале ровно строка card_skipped: %r" % events))
res.append(ok("Объект:" not in out and "Откат:" not in out, "карточка не собрана (нет её строк)"))
res.append(ok(SFO in out, "операция названа — владелец видит, ЧТО было отказано"))

print("(5) объект и число есть → карточка живёт: пуш ровно один, минимум в решении:")
# ВЕХА СМЕНЫ ВЕЗУЩЕЙ ФИКСТУРЫ (01.08.2026). Раньше правило «объект+число → карточка» проверялось
# на FX_LIVE (`set_fleet_oil(number='6789', oil_km=27000)`). Эта фикстура БОЛЬШЕ НЕ ДАЁТ КАРТОЧКУ
# и не должна: она — дословный носитель инцидента 142/143 (запись в живые таблицы по сущности без
# пометки ТЕСТ), и теперь это жёсткий блок, см. (5б). Правило само по себе живо и проверяется на
# денежной операции — у неё есть и объект, и число, а ужесточению деньги намеренно не подлежат.
out, pushed, events = run_main(PY + " " + FX_MONEY)
res.append(ok('"ask"' in out, "решение ask"))
res.append(ok(len(pushed) == 1, "ровно один пуш владельцу (получили %d)" % len(pushed)))
res.append(ok(pushed and "Объект: кошелёк Наличка" in pushed[0] and "Число: сумма -500" in pushed[0],
              "в пуше подписанные ОБЪЕКТ и ЧИСЛО"))
res.append(ok("card_skipped" not in events, "строки card_skipped нет: %r" % events))

print("(5б) ИНЦИДЕНТ 142/143: та же фикстура в живые таблицы — карточки владельцу БОЛЬШЕ НЕТ:")
# Пять заходов подряд умерли на том, что ЭТА строка рождала владельцу боевую красную карточку
# «ТО масло, Лист1 Байки колонка I, байк 6789, пробег 27000». Байка 6789 в парке нет — это
# фикстура. Корень: правило 23.07 искало поле `plate=`, которого у живого Bridge не существует
# (там `number=`), поэтому сущность не извлекалась и запись уезжала в МЯГКУЮ ветку — к владельцу.
out, pushed, events = run_main(PY + " " + FX_LIVE, task_id="142")
res.append(ok('"deny"' in out, "живая сущность по ЖИВОМУ полю number= → deny, а не карточка"))
res.append(ok(pushed == [], "владельцу НЕ ушло ничего (было: ровно этот пуш и убивал пять заходов)"))
res.append(ok(PG._extract_first_entity(SFO, LIVE_OIL) == "6789",
              "живое имя поля Bridge извлекается (регресс класса «мок ≠ живой формат»)"))

print("(6) ЖЁСТКИЙ БЛОК — исключение: приходит всегда, минимум ему не указ:")
out, pushed, events = run_main("cat " + ENVF)
res.append(ok('"deny"' in out and pushed == [] and "🔴 КРАСНОЕ" not in out,
              "файл секретов → deny без карточки и без пуша (как было)"))
out, pushed, events = run_main(PK + " -9 " + SPL)
res.append(ok('"deny"' in out and pushed == [], "гашение боевого процесса → deny без карточки"))
out, pushed, events = run_main(PY + " " + FX_ENTITY, task_id="4242")
marker = os.path.join(TMP, PG.marker_name("4242"))
res.append(ok('"deny"' in out, "ЖИВАЯ сущность → deny (approve невозможен)"))
res.append(ok(os.path.exists(marker), "hard-маркер демону записан ДАЖЕ без числа (исключение)"))
if os.path.exists(marker):
    with open(marker, encoding="utf-8") as f:
        res.append(ok(json.load(f).get("blocktype") == "hard", "в маркере blocktype=hard"))

print("(7) ОТКАТ есть у КАЖДОГО действия и он одной строкой:")
for hit in sorted(PG._ACTIONS):
    c = PG._card(hit, "")
    line = c.split("Откат: ")[1].splitlines()[0] if "Откат: " in c else ""
    res.append(ok(len(line.strip()) > 10 and len(line) <= 90, hit + " → откат: " + line[:60]))

print("(8) регресс: контракт карточки и классификация целы:")
c = PG._card("proc_ctl", "proc_target=systemctl stop nginx")
res.append(ok(c.startswith("🔴 КРАСНОЕ") and "жду твоё «да»" in c, "заголовок и «жду твоё «да»» на месте"))
res.append(ok("nginx" in c, "цель попала в карточку"))
res.append(ok(PG._card(SFO, LIVE_OIL, True).startswith("🧪"), "🧪-пометка dry-run цела"))
res.append(ok(PG.classify("grep -n def " + ROOT.replace(os.sep, "/") + "/bot.py")[0] == "green",
              "зелёная рутина осталась зелёной"))
kind, hit, _b = PG.classify('python3 -c "' + AT + '(amount=500)"')
res.append(ok(kind == "red" and hit == AT, "инлайн денежная операция → красное"))

print("(9) ЧИСЛО БОЛЬШЕ НЕ ГЕЙТ: четыре операции, у которых числа НЕТ ПО ПРИРОДЕ:")
# Живые формы. Красное и SQL — кусками: иначе гард краснеет на САМОМ файле теста.
LIVE_VOID = "bridge." + VL + "(group='Наличка')"
SQL_FOREIGN = ("con=connect('/var/lib/other/app.db'); "
               "con.execute('DELETE " + "FROM sessions WHERE id=5')")
FOUR = (
    ("отмена последней проводки (ДЕНЬГИ)", PY + ' -c "' + LIVE_VOID + '"', VL, "кошелёк Наличка"),
    ("стоп сервиса по имени", "systemctl stop nginx", "proc_ctl", "nginx"),
    ("pkill по имени", PK + " ngrok", "proc_ctl", "ngrok"),
    ("SQL в чужую БД", PY + ' -c "' + SQL_FOREIGN + '"', "sqlite", "app.db"),
)
for label, cmd, want_hit, want_obj in FOUR:
    kind, hit, blob = PG.classify(cmd)
    o, n = PG.card_min(hit, blob)
    card = PG._card(hit, blob)
    res.append(ok(kind == "red" and hit == want_hit, label + ": красное, hit=%s" % hit))
    res.append(ok(PG.card_gate(hit, o, n) is True, label + ": КАРТОЧКА выписана"))
    res.append(ok(want_obj in o, label + ": ОБЪЕКТ виден — %r" % o))
    res.append(ok(n == "", label + ": ЧИСЛА нет по природе операции — %r" % n))
    res.append(ok("Число: —" in card, label + ": поле «Число» честно пустое (прочерк)"))
    res.append(ok(PG.marker_has_object(hit, card) is True, label + ": маркер демону УХОДИТ"))

print("(9б) ДЕНЬГИ спрашивают всегда — даже когда объекта нет физически:")
out, pushed, events = run_main(PY + ' -c "bridge.' + VL + '()"')
res.append(ok('"ask"' in out, "решение ask"))
res.append(ok(len(pushed) == 1, "пуш владельцу ЕСТЬ (получили %d)" % len(pushed)))
res.append(ok("card_skipped" not in events, "в журнал как пропуск НЕ ушла: %r" % events))

print("(9в) само правило card_gate — объект гейт, число нет:")
res.append(ok(PG.card_gate(SFO, "байк 6789", "") is True, "объект без числа → карточка"))
res.append(ok(PG.card_gate(SFO, "", "пробег 27000") is False,
              "ЧИСЛО БЕЗ ОБЪЕКТА карточку НЕ рождает (закрыта дыра полосы ПК)"))
res.append(ok(PG.card_gate(SFO, "", "") is False, "ни объекта, ни числа → журнал"))
# 02.08.2026: денежного исключения больше нет — правило объекта ОДНО для всех классов. Пять карточек
# «проводка ДЕНЕГ · Объект: — · Число: —» (117/135/140/181/208) рождались именно через него, и ни за
# одной проводки не стояло. У НАСТОЯЩЕЙ проводки цель есть всегда (кошелёк, сумма либо сам
# разобранный вызов), поэтому она спрашивает как прежде — см. tests/test_money_action.py.
res.append(ok(PG.card_gate(VL, "", "") is False, "деньги без названной цели → журнал (исключение снято)"))
res.append(ok(PG.card_gate(AT, "", "") is False, "касса без названной цели → журнал"))
res.append(ok(PG.card_gate(AT, "кошелёк Наличка", "") is True, "касса с кошельком → карточка"))
res.append(ok(PG.card_gate(VL, "вызов " + VL + "()", "") is True, "отмена: сам вызов — тоже цель"))

print("(9г) ядро красной зоны карточку СОХРАНИЛО:")
for label, hit, blob in (("парк", SFO, LIVE_OIL), ("CRM", CB, LIVE_BOOKING),
                         ("деньги", AT, LIVE_MONEY), ("удаление", DE, LIVE_DELETE),
                         ("kill по PID", "proc_ctl", "proc_target=kill 12345")):
    o, n = PG.card_min(hit, blob)
    res.append(ok(PG.card_gate(hit, o, n) is True, "%s: карточка на месте (объект=%r)" % (label, o)))

print("\nИТОГ:", "ВСЕ PASS" if all(res) else "ЕСТЬ FAIL (%d/%d)" % (sum(res), len(res)))
sys.exit(0 if all(res) else 1)
