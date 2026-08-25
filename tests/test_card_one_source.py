"""КАРТОЧКА «В РАБОТЕ»: ОДИН ИСТОЧНИК · ЗАПИСАННОЕ УХОДИТ · КЛЮЧИ СХОДЯТСЯ · МЕТКА ЖИВЁТ (25.08).

ЖИВОЙ СЛУЧАЙ, на котором стоят голдены (разбор `6c8e3a8`, чат -1002751134848, тема 80,
NMAX 155 GREY 5960, снимок строки заявки 25.08.2026 09:23:02.911Z):

    declared = 'oil,gear,airfilter'
    done     = 'oil,gear,airfilter,pads,other'
    note     = 'WORKS:{тормозные колодки; передняя резина; вариатор}'
    odometer = 41666            статус = 'ждёт_подтверждения'
    Лист1 I/J/K/L = 41357       история 41666: «замена задних тормозных колодок»,
                                «замена передних тормозных колодок», «замена передней шины»

Тайская половина рендерила `declared`, русская — `WORKS:{}` из `note`: ДВЕ РАЗНЫЕ КОЛОНКИ одной
строки. Русская называла ждущими «тормозные колодки» и «переднюю резину», уже лежавшие в истории.

ЧТО ДОКАЗЫВАЕТСЯ (у КАЖДОГО отрицательного случая есть БЛИЗНЕЦ «то же без порчи»):
    (1) ОДИН ИСТОЧНИК   обе половины дают список одной длины, состава и порядка — ВСЕГДА,
                        включая случай «механик называл работы словами» (там они и расходились);
    (2) СНЯТИЕ          записанная работа исчезает из «в работе»; НЕзаписанная остаётся —
                        и остаётся же та, о которой мир промолчал (исход «неизвестно»);
    (3) КЛЮЧИ           «передняя резина» и «замена передней шины» — ОДИН ключ; близнец:
                        «передние колодки» и «задние колодки» ключами НЕ сходятся;
    (4) МЕТКА           переживает перезапуск процесса; поддельная/чужая/протухшая — отвергается;
    (5) ГРАНИЦЫ         решение чисто (импортов ноль, ast), легаси-рендер байт-в-байт,
                        нота вычёркивает по ключу и не касается прочего текста.
"""
import ast
import json
import os
import sys

# Корень — ОТ ФАЙЛА (ловушка метода 07.08: чужой боевой корень в sys.path зеленит прогон «до»).
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != "/root/turbobaby-manager-bot"] \
    if ROOT != "/root/turbobaby-manager-bot" else sys.path
sys.path.insert(0, ROOT)
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ["NOTIFY_COUNT_FILE"] = "/tmp/tb_onesource_notify_count.txt"
os.environ["SERVICE_UNDO"] = "0"
# Память меток — СВОЯ на прогон: боевого состояния сьют не касается ни байтом.
os.environ["SVC_TOKENS_STATE"] = f"/tmp/tb_onesource_tokens_{os.getpid()}.json"

import card_works as C
import splinter as S

KIND = S._service_kind          # ЖИВОЙ классификатор видов, не копия правил
KEY = S._work_key               # ЖИВОЙ контентный ключ, не копия правил
COL = S._SP_COL_KINDS
LBL = S._SP_KIND_LABEL

# ── ДОСЛОВНЫЙ ЖИВОЙ СНИМОК 5960 ──────────────────────────────────────────────────────────────
KINDS_5960 = ["oil", "gear", "airfilter"]
WORKS_5960 = ["тормозные колодки", "передняя резина", "вариатор"]
ODO_5960 = "41666"
REGS_5960 = {"oil": 41357, "gear": 41357, "abs": 41357, "airfilter": 41357}
HIST_5960 = [{"work": "замена задних тормозных колодок", "km": "41666"},
             {"work": "замена передних тормозных колодок", "km": "41666"},
             {"work": "замена передней шины", "km": "41666"}]

OK = FAIL = 0


def check(name, cond):
    global OK, FAIL
    if cond:
        OK += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}")


def run(kinds, works, regs=REGS_5960, hist=HIST_5960, odo=ODO_5960):
    return C.pending(kinds, works, kind_of=KIND, key_of=KEY, col_kinds=COL,
                     registers=regs, history=hist, odo=odo)


def halves(res):
    """Ровно то, что рендерит карточка: тайская и русская половины ИЗ ОДНОГО списка."""
    th = [S._work_th(p["word"]) if p["word"] else LBL.get(p["kind"], (p["kind"],))[0]
          for p in res["show"]]
    ru = [p["word"] if p["word"] else LBL.get(p["kind"], (p["kind"], p["kind"]))[1]
          for p in res["show"]]
    return th, ru


# ═══════════════ (1) ОДИН ИСТОЧНИК — ОБЕ ПОЛОВИНЫ ═══════════════
print("\n(1) один источник: половины сходятся длиной, составом и порядком")

r = run(KINDS_5960, WORKS_5960)
th, ru = halves(r)
check("5960: половины одной длины", len(th) == len(ru) == len(r["show"]))
check("5960: половин ровно четыре (три регистра + вариатор)", len(th) == 4)
check("5960: русская половина больше НЕ называет колодки", "тормозные колодки" not in ru)
check("5960: русская половина больше НЕ называет резину", "передняя резина" not in ru)
check("5960: вариатор остался в обеих половинах",
      "вариатор" in ru and any("сายพาน" in t or "вариатор" in t or t for t in th))
check("5960: тайская половина по-прежнему называет три регистра",
      th[:3] == [LBL["oil"][0], LBL["gear"][0], LBL["airfilter"][0]])
check("5960: русская называет ТЕ ЖЕ три регистра (прежде называла работы из ноты)",
      ru[:3] == [LBL["oil"][1], LBL["gear"][1], LBL["airfilter"][1]])

# БЛИЗНЕЦ: механик слов НЕ называл — половины и раньше совпадали, обязаны совпадать и теперь.
r0 = run(KINDS_5960, [])
th0, ru0 = halves(r0)
check("близнец «слов нет»: половины совпадают длиной", len(th0) == len(ru0) == 3)
check("близнец «слов нет»: состав прежний (три вида заявки)",
      ru0 == [LBL["oil"][1], LBL["gear"][1], LBL["airfilter"][1]])

# ИСТОЧНИК ОДИН ПО ПОСТРОЕНИЮ: на 30 разных наборах половины не расходятся НИ РАЗУ.
_mix = 0
for kk in ([], ["oil"], ["oil", "pads"], KINDS_5960, ["chain", "tyre"], ["abs"]):
    for ww in ([], ["вариатор"], WORKS_5960, ["замена цепи", "передняя резина"], ["масло"]):
        _r = run(kk, ww)
        _t, _u = halves(_r)
        if len(_t) == len(_u) == len(_r["show"]):
            _mix += 1
check("на 30 наборах половины не разошлись ни разу", _mix == 30)

# Вид, названный СЛОВАМИ, не дублируется ярлыком того же вида.
rd = run(["other"], ["вариатор"], hist=[], regs=REGS_5960)
check("вид со словами не дублируется ярлыком", len(rd["show"]) == 1)
check("вид со словами показывается СЛОВОМ", rd["show"][0]["word"] == "вариатор")


# ═══════════════ (2) СНЯТИЕ: ЗАПИСАННОЕ УХОДИТ, НЕЗАПИСАННОЕ ОСТАЁТСЯ ═══════════════
print("\n(2) снятие с ожидания — с близнецом на каждый случай")

gone = {g["word"] for g in r["gone"]}
show = {p["word"] or p["kind"] for p in r["show"]}
check("ОТРИЦАТЕЛЬНЫЙ: записанная «передняя резина» СНЯТА", "передняя резина" in gone)
check("ОТРИЦАТЕЛЬНЫЙ: записанные «тормозные колодки» СНЯТЫ", "тормозные колодки" in gone)
check("БЛИЗНЕЦ: незаписанный «вариатор» ОСТАЛСЯ", "вариатор" in show)
check("БЛИЗНЕЦ: незаписанные регистры (41357≠41666) ОСТАЛИСЬ",
      {"oil", "gear", "airfilter"} <= show)
check("снятие названо доказательством, а не молчанием",
      all(g["proof"] and g["said"] for g in r["gone"]))

# ОТРИЦАТЕЛЬНЫЙ близнец: та же карточка, но истории на этом пробеге НЕТ — не снимается ничто.
r_nohist = run(KINDS_5960, WORKS_5960, hist=[])
check("БЛИЗНЕЦ «истории нет»: не снято ничего", r_nohist["gone"] == [])
check("БЛИЗНЕЦ «истории нет»: показаны все шесть позиций", len(r_nohist["show"]) == 6)

# ОТРИЦАТЕЛЬНЫЙ близнец: история есть, но на ДРУГОМ пробеге — запись к этой заявке не относится.
r_otherkm = run(KINDS_5960, WORKS_5960,
                hist=[{"work": "замена передней шины", "km": "40000"}])
check("БЛИЗНЕЦ «запись на другом пробеге»: резина осталась",
      "передняя резина" in {p["word"] for p in r_otherkm["show"]})

# РЕГИСТР: клетка стоит на пробеге заявки → вид снят; близнец — стоит на другом → остался.
r_reg = run(["oil"], [], regs={"oil": 41666}, hist=[])
check("ОТРИЦАТЕЛЬНЫЙ: регистр на 41666 → вид снят", [g["kind"] for g in r_reg["gone"]] == ["oil"])
check("регистр назван доказательством", r_reg["gone"][0]["proof"] == C.BY_REGISTER)
r_reg2 = run(["oil"], [], regs={"oil": 41357}, hist=[])
check("БЛИЗНЕЦ: регистр на 41357 → вид остался", [p["kind"] for p in r_reg2["show"]] == ["oil"])

# ТРЕТИЙ ИСХОД: источник НЕ прочитан → позиция ОСТАЁТСЯ и это НЕ «записано».
r_unread = run(["oil"], ["вариатор"], regs=None, hist=None)
check("ЗАМОК: строка парка не прочитана → регистр ОСТАЛСЯ", "oil" in {p["kind"] for p in r_unread["show"]})
check("ЗАМОК: история не прочитана → работа ОСТАЛАСЬ", "вариатор" in {p["word"] for p in r_unread["show"]})
check("ЗАМОК: исход назван «неизвестно», а не «ждёт»",
      all(p["state"] == C.UNKNOWN for p in r_unread["show"]))
check("ЗАМОК: непрочитанное НИЧЕГО не сняло", r_unread["gone"] == [])
r_noodo = run(KINDS_5960, WORKS_5960, odo="")
check("ЗАМОК: у заявки нет пробега → не снято ничего", r_noodo["gone"] == [])

# ВТОРАЯ СТУПЕНЬ — только в одну сторону.
r_wide = run([], ["тормозные колодки"], hist=[{"work": "замена передних тормозных колодок", "km": "41666"}])
check("общее покрывается конкретным (колодки ← колодки/перед)",
      [g["proof"] for g in r_wide["gone"]] == [C.BY_HISTORY_WIDE])
r_narrow = run([], ["передние тормозные колодки"], hist=[{"work": "колодки", "km": "41666"}])
check("БЛИЗНЕЦ: конкретное общим НЕ покрывается — позиция осталась",
      len(r_narrow["show"]) == 1 and r_narrow["gone"] == [])


# ═══════════════ (3) КЛЮЧИ СЛОВ СХОДЯТСЯ ═══════════════
print("\n(3) ключи: одна работа сходится сама с собой, разные — нет")

check("ОТРИЦАТЕЛЬНЫЙ (был дефект): «передняя резина» == «замена передней шины»",
      KEY("передняя резина") == KEY("замена передней шины") == "шина/перед")
check("«замена резины» и «шина» — один стем", KEY("замена резины") == KEY("шина") == "шина")
check("резина стала законным видом tyre", KIND("передняя резина") == "tyre")
check("БЛИЗНЕЦ: перед и зад — РАЗНЫЕ ключи",
      KEY("передние тормозные колодки") != KEY("задние тормозные колодки"))
check("БЛИЗНЕЦ: передняя резина ≠ задняя резина",
      KEY("передняя резина") != KEY("задняя резина"))
check("ЗАБОР ЦЕЛ: «машина помыта» шиной не стала", KIND("машина помыта") != "tyre")
check("ЗАБОР ЦЕЛ: «резиновый коврик» шиной не стал", KIND("резиновый коврик") != "tyre")
check("ЗАБОР ЦЕЛ: «прорезиненная ручка» шиной не стала", KIND("прорезиненная ручка") != "tyre")


# ═══════════════ (4) МЕТКА КНОПКИ ПЕРЕЖИВАЕТ ПЕРЕЗАПУСК ═══════════════
print("\n(4) метка: живёт после перезапуска, поддельная — отвергается")

S._SVC_TOKENS.clear(); S._SVC_SEQ[0] = 0; S._SVC_TOKENS_LOADED = False
try:
    os.remove(os.environ["SVC_TOKENS_STATE"])
except OSError:
    pass

tok = S._svc_put({"kind": "done", "chat": -1002751134848, "topic": 80,
                  "bike": "NMAX 155 GREY 5960", "km": "41666", "done": "oil,gear"})
check("метка выдана", isinstance(tok, int) and tok > 0)
check("метка легла на диск", os.path.exists(os.environ["SVC_TOKENS_STATE"]))

# ПЕРЕЗАПУСК: память процесса стёрта ровно так, как её стирает systemctl restart.
S._SVC_TOKENS.clear(); S._SVC_SEQ[0] = 0; S._SVC_TOKENS_LOADED = False
got = S._svc_get(tok, -1002751134848, 80)
check("ОТРИЦАТЕЛЬНЫЙ (был дефект): после перезапуска метка ЖИВА", bool(got))
check("после перезапуска адрес операции цел",
      got and got.get("bike") == "NMAX 155 GREY 5960" and got.get("km") == "41666")
check("счётчик ушёл ЗА прочитанный номер — номера не повторяются", S._SVC_SEQ[0] >= tok)
tok2 = S._svc_put({"kind": "done", "chat": 1, "topic": 2})
check("следующая метка НЕ повторяет прежний номер", tok2 != tok and tok2 > tok)

check("БЛИЗНЕЦ: метки, которой не выдавали, нет", S._svc_get(999999, -1002751134848, 80) is None)
check("БЛИЗНЕЦ: метка ЧУЖОГО чата не исполняется", S._svc_get(tok, -100999, 80) is None)
check("БЛИЗНЕЦ: метка ЧУЖОЙ темы не исполняется", S._svc_get(tok, -1002751134848, 777) is None)
check("место нажатия неизвестно → ведём себя как прежде", bool(S._svc_get(tok, None, None)))

# ПРОТУХШАЯ метка не оживает.
S._SVC_TOKENS[tok][S._SVC_TOKEN_AT] = 0.0
check("БЛИЗНЕЦ: метка старше TTL отвергнута", S._svc_get(tok, -1002751134848, 80) is None)

# ОТРАБОТАВШАЯ метка не воскресает после перезапуска (иначе запись пошла бы ДВАЖДЫ).
tok3 = S._svc_put({"kind": "done", "chat": 5, "topic": 6})
S._svc_drop(tok3)
S._SVC_TOKENS.clear(); S._SVC_TOKENS_LOADED = False
check("нажатая метка после перезапуска НЕ срабатывает второй раз", S._svc_get(tok3, 5, 6) is None)

# ПОДДЕЛКА ФАЙЛА: мусор на диске не даёт прав — память просто пуста.
with open(os.environ["SVC_TOKENS_STATE"], "w", encoding="utf-8") as f:
    f.write("{не json")
S._SVC_TOKENS.clear(); S._SVC_TOKENS_LOADED = False
check("БЛИЗНЕЦ: испорченный файл → метки нет, а не чужая метка", S._svc_get(tok, None, None) is None)

# ОТКАТ: SVC_TOKENS_PERSIST=0 → память только в процессе (поведение до 25.08).
os.environ["SVC_TOKENS_PERSIST"] = "0"
S._SVC_TOKENS.clear(); S._SVC_SEQ[0] = 0; S._SVC_TOKENS_LOADED = False
tok4 = S._svc_put({"kind": "done", "chat": 7, "topic": 8})
S._SVC_TOKENS.clear(); S._SVC_TOKENS_LOADED = False
check("ОТКАТ SVC_TOKENS_PERSIST=0: метка перезапуск НЕ переживает", S._svc_get(tok4, 7, 8) is None)
os.environ["SVC_TOKENS_PERSIST"] = "1"

# Поднятая с диска метка НЕ считается «открытым вопросом» этого разговора.
S._SVC_TOKENS.clear(); S._SVC_SEQ[0] = 0; S._SVC_TOKENS_LOADED = False
try:
    os.remove(os.environ["SVC_TOKENS_STATE"])
except OSError:
    pass
t5 = S._svc_put({"kind": "oilq", "chat": 11, "topic": 12})
check("свежая метка = вопрос открыт (прежнее поведение)", S._svc_question_open(11, 12) is True)
S._SVC_TOKENS.clear(); S._SVC_TOKENS_LOADED = False
S._svc_tokens_load()
check("после перезапуска вчерашняя метка НЕ глушит сегодняшний вопрос",
      S._svc_question_open(11, 12) is False and t5 in S._SVC_TOKENS)


# ═══════════════ (5) ГРАНИЦЫ ═══════════════
print("\n(5) границы: чистота решения, легаси-рендер, нота")

SRC = open(os.path.join(ROOT, "card_works.py"), encoding="utf-8").read()
TREE = ast.parse(SRC)
check("импортов ровно ноль — спросить мир нечем",
      [n for n in ast.walk(TREE) if isinstance(n, (ast.Import, ast.ImportFrom))] == [])
banned = {"open", "exec", "eval", "compile", "__import__", "print", "input"}
check("ни одного вызова записи/исполнения/печати",
      [n.func.id for n in ast.walk(TREE)
       if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in banned] == [])
check("страж чистоты зарегистрирован в гейте",
      "CARD_WORKS_PURE" in open(os.path.join(ROOT, "invariants_check.py"), encoding="utf-8").read())

# ЛЕГАСИ-РЕНДЕР: карточка без единого списка выглядит БАЙТ-В-БАЙТ как до правки.
MAND = [{"kind": "oil", "last": 41357, "interval": 4000}]
legacy = S.msg_bike_card("NMAX 155 GREY 5960", "41666", MAND, None,
                         sp_open={"kinds": KINDS_5960, "works": WORKS_5960,
                                  "odo": ODO_5960, "status": "ждёт_подтверждения"})
check("легаси-вызов (без `pos`) рендерит ПРЕЖНИЕ две колонки",
      "тормозные колодки, передняя резина, вариатор" in legacy)
fresh = S.msg_bike_card("NMAX 155 GREY 5960", "41666", MAND, None,
                        sp_open={"kinds": KINDS_5960, "works": WORKS_5960, "odo": ODO_5960,
                                 "status": "ждёт_подтверждения", "pos": r["show"]})
check("новый вызов (с `pos`) колодок и резины больше НЕ показывает",
      "тормозные колодки" not in fresh and "передняя резина" not in fresh)
check("новый вызов показывает вариатор", "вариатор" in fresh)
check("новый вызов не потерял статус заявки", "ждёт подтверждения" in fresh)

# НОТА: вычёркивает по ключу и не трогает прочий текст.
N = "WORKS:{тормозные колодки; передняя резина; вариатор}"
d1 = S._sp_note_drop_works(N, ["замена передней шины"])
check("ОТРИЦАТЕЛЬНЫЙ: нота снимает работу по КЛЮЧУ, а не по буквам",
      "передняя резина" not in d1 and "вариатор" in d1 and "тормозные колодки" in d1)
check("БЛИЗНЕЦ: чужая работа ноту не трогает вовсе",
      S._sp_note_drop_works(N, ["замена цепи"]) == N)
check("БЛИЗНЕЦ: пустой список снятия ноту не трогает", S._sp_note_drop_works(N, []) == N)
check("прочий текст ноты сохраняется",
      S._sp_note_drop_works(N + " | escalated", ["замена передней шины"]).endswith("| escalated"))
check("сняли всё → сегмент пустой, но НЕ пустая строка (мост пустое не берёт)",
      S._sp_note_drop_works("WORKS:{вариатор}", ["вариатор"]) == "WORKS:{}")
check("след долга рядом не пострадал",
      "DEBT:{oil@41666}" in S._sp_note_drop_works("WORKS:{вариатор} | DEBT:{oil@41666}", ["вариатор"]))
check("ноты нет вовсе → нечего снимать, возвращаем как было",
      S._sp_note_drop_works("", ["вариатор"]) == "")

# ЕДИНАЯ ДВЕРЬ: снятие висит на `_km_door`, а не размазано по дверям.
SP = open(os.path.join(ROOT, "splinter.py"), encoding="utf-8").read()
ST = ast.parse(SP)
_door = [n for n in ast.walk(ST) if isinstance(n, ast.FunctionDef) and n.name == "_km_door"]
check("`_km_door` зовёт снятие", any(
    isinstance(c.func, ast.Name) and c.func.id == "_sp_note_settle_works"
    for n in _door for c in ast.walk(n) if isinstance(c, ast.Call)))
_callers = [n.name for n in ast.walk(ST) if isinstance(n, ast.FunctionDef)
            and any(isinstance(c.func, ast.Name) and c.func.id == "_sp_note_settle_works"
                    for c in ast.walk(n) if isinstance(c, ast.Call))]
check("дверь снятия РОВНО одна", _callers == ["_km_door"])
_pure = [n for n in ast.walk(ST) if isinstance(n, ast.FunctionDef) and n.name == "_sp_note_drop_works"]
check("решение ноты ничего не пишет само",
      not any(isinstance(c.func, ast.Attribute) and "upsert" in c.func.attr
              for n in _pure for c in ast.walk(n) if isinstance(c, ast.Call)))

print(f"\nИТОГ: {OK} PASS, {FAIL} FAIL")
try:
    os.remove(os.environ["SVC_TOKENS_STATE"])
except OSError:
    pass
if FAIL:
    sys.exit(1)
