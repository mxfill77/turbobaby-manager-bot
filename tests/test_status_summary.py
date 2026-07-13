"""Задача 285 (13.07.2026) + порт ПК-фикса 1403fa2 (задача 287, живой вывод 23:10 13.07:
призраки цепей 194/200/206–208 «план строится», ревизор «время неизвестно»): единая команда
«статус» — сводка системы «всё ли завершено». Секции из фикстур очереди (read-only, один
снимок обеих полос):
⚙️ в работе — активные цепи декомпозера ТОЛЬКО по живым признакам: родитель dec-метки в
new/in_progress ИЛИ незакрытый «[шаг i/N родитель pid]» (new/in_progress/needs_approval/
approved); терминальный родитель (done/failed) без незакрытых шагов = призрак → не в списке;
ярлык — открытый шаг «шаг i/N», иначе «план строится»; synthetic-маркеры родителями не
считаются. Плюс new/in_progress/approved одиночки обеих полос и кураторские цели счётчиком.
🧑 ждёт тебя — все needs_approval: красные вопросы и сводные карточки владельцу.
👁 надзор — честный тик ревизора из свежей NOTE «ревизор: …» в cowork_log (живой формат
«NOTE Orchestrator: ревизор: 2 окон с активностью…» — разведка cowork_log 13.07.2026);
NOTE нет → «ревизор: тиков ещё не было»; НИКАКОГО «время неизвестно»; маркеры очереди
«[ревизор …]» — не тики. Всё пусто → «🟢 ТИХО»; Bridge-молчит ≠ ТИХО.
Сети/Telegram нет — всё мокнуто."""
import inspect
import os, sys
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")

def ok(c, l): print(("  PASS " if c else "  FAIL ") + l); return c
res = []

import devbot as DB

# cowork_log без тик-NOTE ревизора (живые нетиковые строки: NOTE о задачах тик-паттерн не матчят)
_COWORK_NO_TICK = ("NOTE Orchestrator: задача #287 → done · Готово. Косметика «статус контура»\n"
                   "DONE Dispatch 16:05: статус контура — секция «в работе» без призраков\n")

_ITEMS = [
    # живая pc-цепь 291 (pcloc-dec): родитель уже done, но есть НЕЗАКРЫТЫЙ шаг 2/5 (in_progress)
    {"id": 291, "status": "done", "from": "Filipp-pcloc-dec", "lane": "pc",
     "task_text": "перевести suggest на новый playbook целиком"},
    {"id": 292, "status": "done", "from": "Filipp-pcloc-dec", "lane": "pc",
     "task_text": "[шаг 1/5 родитель 291] разведка playbook"},
    {"id": 293, "status": "in_progress", "from": "Filipp-pcloc-dec", "lane": "pc",
     "task_text": "[шаг 2/5 родитель 291] сборка"},
    # ПРИЗРАКИ (живой кейс 194/200/206–208): терминальные pcloc-dec родители БЕЗ незакрытых
    # шагов — цепь целиком на ПК, шагов в Bridge-очереди нет; в списке им не место
    {"id": 194, "status": "done", "from": "Filipp-pcloc-dec", "lane": "pc",
     "task_text": "призрак сто девяносто четыре"},
    {"id": 206, "status": "done", "from": "Filipp-pcloc-dec", "lane": "pc",
     "task_text": "призрак двести шесть"},
    {"id": 207, "status": "done", "from": "Filipp-pcloc-dec", "lane": "pc",
     "task_text": "призрак двести семь"},
    {"id": 208, "status": "done", "from": "Filipp-pcloc-dec", "lane": "pc",
     "task_text": "призрак двести восемь"},
    # завершённая vps-цепь 200 (родитель done, шаг закрыт, сводка есть) → тоже НЕ активна
    {"id": 200, "status": "done", "from": "Filipp-328-dec", "lane": "vps",
     "task_text": "цель двести"},
    {"id": 201, "status": "done", "from": "Filipp-328-dec", "lane": "vps",
     "task_text": "[шаг 3/3 родитель 200] финал"},
    {"id": 205, "status": "done", "from": "Filipp-328-dec", "lane": "vps",
     "task_text": "[сводка родитель 200] сводный отчёт по шагам"},
    # failed-родитель без незакрытых шагов (чисто-красный отказ плана) → НЕ активная цепь
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
    cowork = _COWORK_NO_TICK
    def __init__(self, items): self._items = items
    def get_pending_multi(self, statuses, lane=None):
        assert lane == "all", "снимок обязан опрашивать ОБЕ полосы (lane='all')"
        return {"ok": True, "items": [dict(it) for it in self._items]}
    def _call(self, a, **k):
        if a == "read_doc" and k.get("name") == "pulse":
            return {"ok": True, "text": "2026-07-13 | 🟢 | тест"}
        if a == "read_doc" and k.get("name") == "cowork_log":
            return {"ok": True, "text": self.cowork} if self.cowork is not None else {"ok": False}
        return {"ok": False}


# (1) секция «в работе»: живая цепь + одиночки + куратор, призраки мимо, дедуп шагов
print("(1) ⚙️ в работе (живые признаки, зеркало 1403fa2):")
out = DB._g_pulse(Q(_ITEMS))
res.append(ok(out.startswith("📟 2026-07-13"), "пульс первой строкой (регресс формата)"))
res.append(ok("⚙️ в работе 4:" in out, "счёт: живая цепь 291 + одиночки 285/288 + 1 цель куратора = 4"))
res.append(ok("⛓ цепь 291 [pc]: шаг 2/5 — перевести suggest" in out,
              "живой шаг 2/5 → цепь в списке, ярлык из открытого шага"))
for pid in (194, 206, 207, 208):
    res.append(ok(f"цепь {pid}" not in out and f"призрак" not in out.split(str(pid))[0][-60:],
                  f"призрак {pid} (done-родитель без незакрытых шагов) — НЕ в списке"))
res.append(ok("цепь 200" not in out, "завершённая цепь (родитель done, шаг закрыт) — НЕ активна"))
res.append(ok("210" not in out, "failed-родитель без незакрытых шагов — не цепь и не одиночка"))
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

# (4) надзор: тик-NOTE ревизора в cowork_log нет → честное «тиков ещё не было»
print("(4) 👁 надзор (честный тик из cowork_log):")
res.append(ok("👁 надзор: ревизор: тиков ещё не было" in out,
              "NOTE «ревизор: …» нет → «тиков ещё не было»"))
res.append(ok("время неизвестно" not in out, "никакого «время неизвестно»"))

# (5) маркеры очереди «[ревизор …]» — дедуп/бюджет маршрутизации, НЕ тики (корень призрака)
rev_items = _ITEMS + [
    {"id": 500, "status": "done", "from": "Filipp-pcloc-dec", "lane": "pc",
     "task_text": "[ревизор дата=2026-07-13 класс=greeting] проверить приветствие"},
]
out_rev = DB._g_pulse(Q(rev_items))
res.append(ok("👁 надзор: ревизор: тиков ещё не было" in out_rev
              and "время неизвестно" not in out_rev,
              "маркер очереди [ревизор дата=…] тиком НЕ считается (призрак убит)"))
res.append(ok("500" not in out_rev.split("👁")[0], "маркер-карточки не мусорят секции работы"))

# (6) тик из cowork_log: живой формат (разведка 13.07) и формат с временем; свежая NOTE сверху
print("(6) тик ревизора из cowork_log:")
live = ("NOTE Orchestrator: ревизор: 2 окон с активностью с прошлого прогона — пакеты собраны\n"
        "NOTE Orchestrator: ревизор: 5 окон — старый тик\n")
line = DB._revisor_line(lambda: live)
res.append(ok(line == "👁 надзор: ревизор — окон 2",
              "живой формат NOTE (без времени): окна есть, время не выдумано"))
timed = ("NOTE Orchestrator: задача #287 → done · про ревизора, но не тик\n"
         "NOTE Orchestrator: ревизор: тик 2026-07-13 06:10 — окон 12, находок 2\n"
         "NOTE Orchestrator: ревизор: тик 2026-07-13 05:00 — окон 9, находок 0\n")
line_t = DB._revisor_line(lambda: timed)
res.append(ok(line_t == "👁 надзор: ревизор 2026-07-13 06:10 — окон 12, находок 2 ❗",
              "NOTE с временем: честное время + окна + находки с ❗; свежая (верхняя) NOTE"))
res.append(ok("окон 9" not in line_t, "старый тик не показывается"))
res.append(ok(DB._revisor_line(lambda: "журнал без тик-NOTE")
              == "👁 надзор: ревизор: тиков ещё не было", "нет NOTE → «тиков ещё не было»"))
res.append(ok(DB._revisor_line(None)
              == "👁 надзор: cowork_log недоступен — тик ревизора неизвестен",
              "cowork_log не прочитался → честное «недоступен», не «тиков не было»"))
res.append(ok("время неизвестно" not in DB._parse_revisor("пакеты собраны, деталей нет"),
              "тик без чисел/времени — без «время неизвестно» (короткий текст тика)"))

# (7) пустой случай: «🟢 ТИХО» — сигнал «всё завершено»
print("(7) пустой случай:")
out_empty = DB._g_pulse(Q([]))
res.append(ok("🟢 ТИХО: в работе 0, ждёт тебя 0" in out_empty, "всё пусто → «🟢 ТИХО»"))
res.append(ok("⚙️" not in out_empty and "🧭" not in out_empty,
              "ни секций, ни дайджеста — только пульс + ТИХО + надзор"))
res.append(ok(out_empty.startswith("📟 2026-07-13"), "пульс первой строкой"))

# (8) fail-safe: очередь не опросилась → пульс + честная пометка; Bridge-молчит ≠ ТИХО
print("(8) fail-safe:")
class QFail(Q):
    def get_pending_multi(self, statuses, lane=None): return {"ok": False, "error": "boom"}
out_fail = DB._g_pulse(QFail([]))
res.append(ok(out_fail.startswith("📟 2026-07-13") and "очередь не опросилась" in out_fail,
              "сбой опроса → пульс жив + честная пометка"))
res.append(ok("ТИХО" not in out_fail, "Bridge-молчит ≠ ТИХО (пустота не выдумывается)"))
class QRaise(Q):
    def get_pending_multi(self, statuses, lane=None): raise RuntimeError("сеть упала")
res.append(ok("очередь не опросилась" in DB._g_pulse(QRaise([])),
              "исключение опроса → пометка, не падение"))

# (9) края: живой родитель без шагов → «план строится»; смесь призраков; топ-кап секций
print("(9) края:")
plan_items = [{"id": 600, "status": "in_progress", "from": "Filipp-pc-dec", "lane": "",
               "task_text": "цель шестьсот без шагов"},
              {"id": 601, "status": "done", "from": "Filipp-pc-dec", "lane": "",
               "task_text": "призрак шестьсот один"}]
out_plan = DB._g_pulse(Q(plan_items))
res.append(ok("⛓ цепь 600 [vps]: план строится — цель шестьсот" in out_plan,
              "живой родитель (in_progress) без шагов → «план строится» (пустой lane → vps)"))
res.append(ok("601" not in out_plan and "⚙️ в работе 1:" in out_plan,
              "смесь: призрак рядом с живым — показан только живой"))
new_parent = [{"id": 610, "status": "new", "from": "Filipp-pcloc-dec", "lane": "pc",
               "task_text": "свежий родитель ещё не взят"}]
res.append(ok("⛓ цепь 610 [pc]: план строится" in DB._g_pulse(Q(new_parent)),
              "new-родитель — живой (план строится)"))
many = [{"id": 700 + i, "status": "new", "from": "Filipp-328", "lane": "vps",
         "task_text": f"задача номер {i}"} for i in range(8)]
out_many = DB._g_pulse(Q(many))
res.append(ok("⚙️ в работе 8:" in out_many and "…ещё 3" in out_many,
              "телефонный кап: топ-5 строк + «…ещё K» (счёт полный)"))
res.append(ok("🧑 ждёт тебя 0" in out_many, "нет needs_approval → «ждёт тебя 0» одной строкой"))
# незакрытый шаг ждёт «да» (needs_approval) — цепь жива, хоть родитель терминален
red_step = [{"id": 620, "status": "done", "from": "Filipp-pcloc-dec", "lane": "pc",
             "task_text": "цель с красным шагом"},
            {"id": 621, "status": "needs_approval", "from": "Filipp-pcloc-dec", "lane": "pc",
             "task_text": "[шаг 3/4 родитель 620] красный деплой"}]
res.append(ok("⛓ цепь 620 [pc]: шаг 3/4" in DB._g_pulse(Q(red_step)),
              "needs_approval-шаг = незакрытый → цепь живая, ярлык «шаг 3/4»"))

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
