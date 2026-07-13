"""Задача 285 (13.07.2026): единая команда «статус» — сводка системы «всё ли завершено».
Секции из фикстур очереди (read-only, один снимок обеих полос):
⚙️ в работе — активные цепи декомпозера (родитель dec-метки без сводки, вкл. pcloc-dec:
шаг i/d из маркеров), new/in_progress/approved одиночки обеих полос, кураторские цели в
работе (счётчиком — детали в дайджесте); 🧑 ждёт тебя — все needs_approval: красные вопросы
и сводные карточки владельцу (куратор/ревизор); 👁 надзор — последний тик ревизора из меток
очереди «[ревизор …]» либо NOTE-строки cc_log, нет нигде → честное «тиков нет».
Всё пусто → «🟢 ТИХО: в работе 0, ждёт тебя 0». Сети/Telegram нет — всё мокнуто."""
import inspect
import os, sys
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")

def ok(c, l): print(("  PASS " if c else "  FAIL ") + l); return c
res = []

import devbot as DB

_ITEMS = [
    # активная pc-цепь 291 (pcloc-dec, сводки НЕТ): выпущены шаги 1/5 (done) и 2/5 (in_progress)
    {"id": 291, "status": "done", "from": "Filipp-pcloc-dec", "lane": "pc",
     "task_text": "перевести suggest на новый playbook целиком"},
    {"id": 292, "status": "done", "from": "Filipp-pcloc-dec", "lane": "pc",
     "task_text": "[шаг 1/5 родитель 291] разведка playbook"},
    {"id": 293, "status": "in_progress", "from": "Filipp-pcloc-dec", "lane": "pc",
     "task_text": "[шаг 2/5 родитель 291] сборка"},
    # завершённая vps-цепь 200: сводка есть → НЕ активна (и её done-шаг не всплывает)
    {"id": 200, "status": "done", "from": "Filipp-328-dec", "lane": "vps",
     "task_text": "цель двести"},
    {"id": 201, "status": "done", "from": "Filipp-328-dec", "lane": "vps",
     "task_text": "[шаг 3/3 родитель 200] финал"},
    {"id": 205, "status": "done", "from": "Filipp-328-dec", "lane": "vps",
     "task_text": "[сводка родитель 200] сводный отчёт по шагам"},
    # failed-родитель без сводки (чисто-красный отказ плана) → НЕ активная цепь
    {"id": 210, "status": "failed", "from": "Filipp-328-dec", "lane": "vps",
     "task_text": "чисто-красный родитель"},
    # одиночки в работе: vps in_progress, pc new
    {"id": 285, "status": "in_progress", "from": "Filipp-328-dev", "lane": "vps",
     "task_text": "единая команда статус в 328"},
    {"id": 288, "status": "new", "from": "Filipp-328", "lane": "pc",
     "task_text": "проверь юзербот"},
    # куратор: цель 231 в работе (followup), открытая карточка владельцу цель 245
    {"id": 301, "status": "in_progress", "from": "Filipp-curator", "lane": "vps",
     "task_text": "[куратор цели 231, шаг 1] докрутить тесты"},
    {"id": 302, "status": "needs_approval", "from": "Filipp-328-dec", "lane": "vps",
     "task_text": "[куратор владельцу цель 245] нужен ключ API"},
    # красный вопрос обычной задачи (needs_approval)
    {"id": 303, "status": "needs_approval", "from": "Filipp-328-dev", "lane": "vps",
     "task_text": "деплой Bridge после фикса", "result": "op=other | clasp redeploy"},
    # чужой from и done-одиночка — в сводку не попадают
    {"id": 400, "status": "in_progress", "from": "Кто-то-чужой", "task_text": "чужое"},
    {"id": 401, "status": "done", "from": "Filipp-328", "lane": "vps", "task_text": "старое"},
]


class Q:
    def __init__(self, items): self._items = items
    def get_pending_multi(self, statuses, lane=None):
        assert lane == "all", "снимок обязан опрашивать ОБЕ полосы (lane='all')"
        return {"ok": True, "items": [dict(it) for it in self._items]}
    def _call(self, a, **k):
        if a == "read_doc" and k.get("name") == "pulse":
            return {"ok": True, "text": "2026-07-13 | 🟢 | тест"}
        return {"ok": False}


# (1) секция «в работе»: цепь + одиночки + куратор, дедуп шагов цепи, чужое мимо
print("(1) ⚙️ в работе:")
out = DB._g_pulse(Q(_ITEMS))
res.append(ok(out.startswith("📟 2026-07-13"), "пульс первой строкой (регресс формата)"))
res.append(ok("⚙️ в работе 4:" in out, "счёт: цепь 291 + одиночки 285/288 + 1 цель куратора = 4"))
res.append(ok("⛓ цепь 291 [pc]: шаг 2/5 — перевести suggest" in out,
              "активная pc-цепь pcloc-dec: «шаг i/d» из максимального выпущенного маркера"))
res.append(ok("цепь 200" not in out, "цепь со сводкой — НЕ активна"))
res.append(ok("210" not in out, "failed-родитель без сводки — не цепь и не одиночка"))
res.append(ok("🔄 285 [vps]: единая команда статус" in out, "vps-одиночка in_progress"))
res.append(ok("⏳ 288 [pc]: проверь юзербот" in out, "pc-одиночка new (обе полосы в сводке)"))
res.append(ok("293" not in out.split("🧑")[0].replace("[шаг 2/5", ""),
              "шаг активной цепи не дублируется одиночкой"))
res.append(ok("цели куратора в работе: 1" in out, "кураторская цель — счётчиком"))
res.append(ok("чужое" not in out and "401" not in out, "чужой from и done-одиночка — мимо"))

# (2) секция «ждёт тебя»: красный вопрос + карточка владельцу
print("(2) 🧑 ждёт тебя:")
res.append(ok("🧑 ждёт тебя 2:" in out, "счёт needs_approval = 2"))
res.append(ok("🧑 карточка 302: [куратор владельцу цель 245]" in out,
              "сводная карточка владельцу распознана"))
res.append(ok("❓ 303 [vps]: деплой Bridge" in out, "красный вопрос обычной задачи"))

# (3) регресс: дайджест куратора остался в статусе
print("(3) дайджест куратора жив:")
res.append(ok("🧭 кураторские цели (2):" in out and "цель 231" in out and "цель 245" in out,
              "дайджест под сводкой (цели 231/245)"))

# (4) надзор: меток ревизора нет нигде → честное «тиков нет»
print("(4) 👁 надзор:")
res.append(ok("👁 надзор: тиков ревизора нет" in out, "ревизора нет → честная строка"))

# (5) тик ревизора из метки очереди (свежайшая по id)
rev_items = _ITEMS + [
    {"id": 500, "status": "done", "from": "Filipp-328", "lane": "vps",
     "task_text": "[ревизор тик] 2026-07-13 05:00 UTC — окон 9, находок 0"},
    {"id": 501, "status": "done", "from": "Filipp-328", "lane": "vps",
     "task_text": "[ревизор тик] 2026-07-13 06:10 UTC — окон 12, находок 2"},
]
out_rev = DB._g_pulse(Q(rev_items))
res.append(ok("👁 надзор: ревизор 2026-07-13 06:10 — окон 12, находок 2 ❗" in out_rev,
              "тик из очереди: свежайший по id, время/окна/находки, ❗ при находках"))
res.append(ok("окон 9" not in out_rev, "старый тик не показывается"))
res.append(ok("500" not in out_rev.split("👁")[0], "тик-карточки не мусорят секции работы"))

# (6) тик ревизора из cc_log (фолбэк, новые сверху — первая совпавшая строка)
cclog = ("NOTE 2026-07-13 04:30 UTC (ревизор): окон 7, находок 0 — всё чисто\n"
         "NOTE 2026-07-12 21:00 UTC (ревизор): окон 5, находок 1 — старое\n")
line = DB._revisor_line([], lambda: cclog)
res.append(ok(line == "👁 надзор: ревизор 2026-07-13 04:30 — окон 7, находок 0",
              "фолбэк cc_log: первая (свежая) NOTE-строка, 0 находок без ❗"))
res.append(ok(DB._revisor_line([], lambda: "журнал без меток")
              == "👁 надзор: тиков ревизора нет", "cc_log без меток → «тиков нет»"))
res.append(ok(DB._revisor_line([], None) == "👁 надзор: тиков ревизора нет",
              "cc_log недоступен → «тиков нет», не падение"))
res.append(ok("окон 12" in DB._parse_revisor("[ревизор] 12 окон, находки: 3"),
              "парсер понимает и порядок «N окон»"))

# (7) пустой случай: «🟢 ТИХО» — сигнал «всё завершено»
print("(7) пустой случай:")
out_empty = DB._g_pulse(Q([]))
res.append(ok("🟢 ТИХО: в работе 0, ждёт тебя 0" in out_empty, "всё пусто → «🟢 ТИХО»"))
res.append(ok("⚙️" not in out_empty and "🧭" not in out_empty,
              "ни секций, ни дайджеста — только пульс + ТИХО + надзор"))
res.append(ok(out_empty.startswith("📟 2026-07-13"), "пульс первой строкой"))

# (8) fail-safe: очередь не опросилась → пульс + честная пометка, не падение
print("(8) fail-safe:")
class QFail(Q):
    def get_pending_multi(self, statuses, lane=None): return {"ok": False, "error": "boom"}
out_fail = DB._g_pulse(QFail([]))
res.append(ok(out_fail.startswith("📟 2026-07-13") and "очередь не опросилась" in out_fail,
              "сбой опроса → пульс жив + честная пометка"))
class QRaise(Q):
    def get_pending_multi(self, statuses, lane=None): raise RuntimeError("сеть упала")
res.append(ok("очередь не опросилась" in DB._g_pulse(QRaise([])),
              "исключение опроса → пометка, не падение"))

# (9) цепь без выпущенных шагов → «план строится»; топ-кап секций
print("(9) края:")
plan_items = [{"id": 600, "status": "done", "from": "Filipp-pc-dec", "lane": "",
               "task_text": "цель шестьсот без шагов"}]
out_plan = DB._g_pulse(Q(plan_items))
res.append(ok("⛓ цепь 600 [vps]: план строится — цель шестьсот" in out_plan,
              "родитель без шагов → «план строится» (пустой lane → vps)"))
many = [{"id": 700 + i, "status": "new", "from": "Filipp-328", "lane": "vps",
         "task_text": f"задача номер {i}"} for i in range(8)]
out_many = DB._g_pulse(Q(many))
res.append(ok("⚙️ в работе 8:" in out_many and "…ещё 3" in out_many,
              "телефонный кап: топ-5 строк + «…ещё K» (счёт полный)"))
res.append(ok("🧑 ждёт тебя 0" in out_many, "нет needs_approval → «ждёт тебя 0» одной строкой"))

# (10) утренняя авто-сводка сводку системы НЕ включает (по расписанию не спамим)
print("(10) morning_summary:")
src = inspect.getsource(DB.morning_summary)
res.append(ok("_system_summary" not in src and "_g_pulse" not in src,
              "morning_summary без сводки системы (только по запросу «статус»)"))

print()
if all(res):
    print(f"OK: {len(res)}/{len(res)} проверок сводки «статус»")
    sys.exit(0)
print(f"FAIL: {sum(1 for r in res if not r)} из {len(res)} проверок красные")
sys.exit(1)
