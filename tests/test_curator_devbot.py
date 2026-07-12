"""Шаг 5/7 родителя 231 (12.07.2026): devbot-канал куратора целей.
(а) РОУТИНГ: метка Filipp-curator (followup-задачи куратора, orchestrator_daemon.CURATOR_FROM)
в QUEUE_FROMS — до фикса фильтр отчётов _poll_queue_sync её выкидывал (урок 682a881), и
done/failed/needs_approval куратор-задач НИКОГДА не доезжали до 328. Полоса vps → тема 328.
(б) ДАЙДЖЕСТ: зелёная команда «статус» дополнена дайджестом кураторских целей из очереди по
маркерам [куратор цели G, шаг m] / [куратор владельцу цель G]: закрыто / в работе / ждёт
владельца. Read-only; в утреннюю авто-сводку НЕ входит (по расписанию не спамим).
Сети/Telegram нет — всё мокнуто."""
import inspect
import os, sys
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")

def ok(c, l): print(("  PASS " if c else "  FAIL ") + l); return c
res = []

import devbot as DB

# (1) метка куратора в фильтре отчётов; полоса vps (НЕ pc)
print("(1) метка Filipp-curator:")
res.append(ok(DB.QUEUE_FROM_CURATOR == "Filipp-curator", "константа = Filipp-curator"))
res.append(ok("Filipp-curator" in DB.QUEUE_FROMS, "в QUEUE_FROMS (фильтр отчётов, урок 682a881)"))
res.append(ok("Filipp-curator" not in DB.QUEUE_FROMS_PC, "НЕ в QUEUE_FROMS_PC (куратор живёт на vps)"))
it = {"from": "Filipp-curator", "lane": "vps"}
res.append(ok(not DB._is_pc_item(it), "_is_pc_item → False (полоса vps)"))
res.append(ok(DB._item_topic(it) == DB.DEVBOT_TOPIC, "тема карточек = 328 (DEVBOT_TOPIC)"))
res.append(ok(DB._item_lane_label(it) == "vps", "ярлык полосы 'vps'"))

# (2) элемент куратора проходит фильтр _poll_queue_sync; мусорный from — нет
print("(2) фильтр _poll_queue_sync:")
class PB:                       # мок без get_pending_multi → по-статусный путь
    def get_pending(self, st, lane="all"):
        items = []
        if st == "done":
            items = [{"id": 301, "from": "Filipp-curator",
                      "task_text": "[куратор цели 231, шаг 1] допиши тесты",
                      "result": "✅ тесты дописаны"},
                     {"id": 302, "from": "Кто-то-чужой", "task_text": "чужое", "result": "x"}]
        if st == "needs_approval":
            items = [{"id": 303, "from": "Filipp-curator",
                      "task_text": "[куратор цели 231, шаг 2] задеплой",
                      "result": "op=other | clasp redeploy"}]
        return {"ok": True, "items": items}
by = DB._poll_queue_sync(PB())
res.append(ok(by is not None and [i["id"] for i in by["done"]] == [301],
              "done куратор-задачи прошёл фильтр, чужой from отсеян"))
res.append(ok([i["id"] for i in by["needs_approval"]] == [303],
              "needs_approval куратор-задачи прошёл фильтр (кнопка дойдёт)"))

# (3) срез целей _curator_goals: маркеры, статусы, чужое игнорируется
print("(3) _curator_goals:")
class QB:                       # очередь с тремя целями во всех состояниях
    def get_pending(self, st, lane=None):
        data = {
            "new": [{"id": 1, "task_text": "[куратор цели 231, шаг 2] докрути Б"},
                    {"id": 2, "task_text": "обычная задача без маркера"}],
            "in_progress": [{"id": 3, "task_text": "[самопочинка задачи 9, попытка 1] "
                                                   "[куратор цели 231, шаг 3] почини"}],
            "approved": [],
            "needs_approval": [{"id": 4, "task_text": "[куратор владельцу цель 245] нужен ключ"},
                               {"id": 5, "task_text": "[куратор цели 250, шаг 1] красный вопрос"}],
            "done": [{"id": 6, "task_text": "[куратор цели 231, шаг 1] сделай А"},
                     {"id": 7, "task_text": "[куратор цели 260, шаг 1] всё готово"},
                     {"id": 8, "task_text": "[куратор владельцу цель 231] принято"}],
            "failed": [{"id": 9, "task_text": "[куратор цели 260, шаг 2] не вышло"}],
        }
        return {"ok": True, "items": list(data.get(st, []))}
g = DB._curator_goals(QB())
res.append(ok(g is not None and set(g) == {231, 245, 250, 260}, "цели 231/245/250/260 найдены, мусор мимо"))
res.append(ok(g[231]["active"] == 2 and g[231]["done"] == 1 and g[231]["steps"] == 3,
              "цель 231: 2 активных + 1 done, max шаг 3 (маркер найден и под префиксом самопочинки)"))
res.append(ok(g[231]["owner"] is False, "закрытая (done) карточка владельцу цель НЕ держит"))
res.append(ok(g[245]["owner"] is True and g[245]["active"] == 0, "цель 245: открытая карточка владельцу"))
res.append(ok(g[250]["wait"] == 1, "цель 250: followup упёрся в красное (needs_approval)"))
res.append(ok(g[260]["active"] == 0 and g[260]["done"] == 1 and g[260]["failed"] == 1,
              "цель 260: все продолжения терминальны (1 done + 1 failed)"))

# (4) дайджест: классификация закрыто / в работе / ждёт владельца + шапка
print("(4) _curator_digest:")
d = DB._curator_digest(QB())
res.append(ok(d is not None and d.startswith("🧭 кураторские цели (4):"), "шапка с числом целей"))
res.append(ok("закрыто 1" in d and "в работе 1" in d and "ждёт владельца 2" in d,
              "счётчики: закрыто 1 · в работе 1 · ждёт владельца 2"))
res.append(ok("цель 231: 🔄 в работе" in d and "активных 2" in d, "цель 231 → в работе"))
res.append(ok("цель 245: 🧑 ждёт владельца — карточка в инбоксе" in d, "цель 245 → ждёт владельца (карточка)"))
res.append(ok("цель 250: 🧑 ждёт владельца — красный вопрос" in d, "цель 250 → ждёт владельца (красный вопрос)"))
res.append(ok("цель 260: ✅ закрыто" in d and "провалено 1" in d, "цель 260 → закрыто, провал не скрыт"))

# (5) fail-safe дайджеста: пустая очередь → None; сбой опроса → честная пометка, не исключение
print("(5) fail-safe:")
class QEmpty:
    def get_pending(self, st, lane=None): return {"ok": True, "items": []}
res.append(ok(DB._curator_digest(QEmpty()) is None, "маркеров нет → None (статус без лишней строки)"))
class QFail:
    def get_pending(self, st, lane=None): return {"ok": False, "error": "boom"}
res.append(ok("не опросилась" in DB._curator_digest(QFail()), "сбой опроса → честная пометка"))
class QRaise:
    def get_pending(self, st, lane=None): raise RuntimeError("сеть упала")
res.append(ok("не опросилась" in DB._curator_digest(QRaise()), "исключение опроса → пометка, не падение"))

# (6) «статус» (_g_pulse): пульс + дайджест; без целей — пульс как раньше
print("(6) команда «статус»:")
class BR(QB):
    def _call(s, a, **k):
        if a == "read_doc" and k.get("name") == "pulse":
            return {"ok": True, "text": "2026-07-12 | 🟢 | тестовый пульс"}
        return {"ok": False}
out = DB._g_pulse(BR())
res.append(ok(out.startswith("📟 2026-07-12"), "строка пульса первой (прежний формат жив)"))
res.append(ok("🧭 кураторские цели (4):" in out and "цель 231" in out, "дайджест дописан под пульсом"))
class BRClean(QEmpty):
    _call = BR._call
res.append(ok(DB._g_pulse(BRClean()) == "📟 2026-07-12 | 🟢 | тестовый пульс",
              "целей нет → чистый пульс, ни строки лишней"))
res.append(ok(DB._match("статус") is not None, "«статус» в зелёном allowlist"))

# (7) по расписанию не спамим: утренняя сводка дайджест/пульс НЕ зовёт
print("(7) утренняя сводка без дайджеста:")
src = inspect.getsource(DB.morning_summary)
res.append(ok("_curator_digest" not in src and "_g_pulse" not in src,
              "morning_summary не включает пульс/дайджест (только по запросу «статус»)"))

print()
if all(res):
    print(f"OK: {len(res)}/{len(res)} проверок devbot-канала куратора")
    sys.exit(0)
print(f"FAIL: {sum(1 for r in res if not r)} из {len(res)} проверок красные")
sys.exit(1)
