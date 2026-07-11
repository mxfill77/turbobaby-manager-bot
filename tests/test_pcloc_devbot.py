"""Шаг 5/7 родителя 185 (11.07.2026): devbot несёт карточки ЛОКАЛЬНОГО дирижёра ПК
(from=Filipp-pcloc-dec) штатно. До фикса метки НЕ было в QUEUE_FROMS → фильтр отчётов
_poll_queue_sync выкидывал задачи локальной цепи: needs_approval красного шага никогда
не доезжал до инбокса (кнопок нет → цепь висела до APPROVAL_TTL и глохла ⏱-failed).
Проверяем: метка в фильтре, элемент проходит _poll_queue_sync, топики/ярлык полосы pc,
чужие from по-прежнему отсеиваются. Сети/Telegram нет — всё мокнуто."""
import os, sys
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")

def ok(c, l): print(("  PASS " if c else "  FAIL ") + l); return c
res = []

import devbot as DB

# (1) метка локального дирижёра в фильтре отчётов и в группе полосы pc
print("(1) метка Filipp-pcloc-dec:")
res.append(ok(DB.QUEUE_FROM_PCLOC_DEC == "Filipp-pcloc-dec", "константа = Filipp-pcloc-dec"))
res.append(ok("Filipp-pcloc-dec" in DB.QUEUE_FROMS, "в QUEUE_FROMS (фильтр отчётов)"))
res.append(ok("Filipp-pcloc-dec" in DB.QUEUE_FROMS_PC, "в QUEUE_FROMS_PC (топик PC-дев + ярлык pc)"))

# (2) элемент локальной цепи проходит фильтр _poll_queue_sync; мусорный from — нет
print("(2) фильтр _poll_queue_sync:")
class PB:                       # мок без get_pending_multi → по-статусный путь
    def get_pending(self, st, lane="all"):
        items = []
        if st == "needs_approval":
            items = [{"id": 7, "from": "Filipp-pcloc-dec", "lane": "pc",
                      "task_text": "[шаг 2/3 родитель 5] задеплой clasp",
                      "result": "op=other | clasp redeploy Bridge"},
                     {"id": 8, "from": "Кто-то-чужой", "lane": "pc",
                      "task_text": "чужое", "result": "x"}]
        if st == "done":
            items = [{"id": 9, "from": "Filipp-pcloc-dec", "lane": "pc",
                      "task_text": "[сводка родитель 5] сводный отчёт по шагам",
                      "result": "🧩 Сводка"}]
        return {"ok": True, "items": items}
by = DB._poll_queue_sync(PB())
res.append(ok(by is not None and [it["id"] for it in by["needs_approval"]] == [7],
              "needs_approval локальной цепи прошёл фильтр, чужой from отсеян"))
res.append(ok([it["id"] for it in by["done"]] == [9], "done-сводка локальной цепи прошла фильтр"))

# (3) маршрутизация: полоса pc (ярлык/тема), инбокс для needs_approval — тем же механизмом,
#     что у Filipp-pc-dec (код одинаковый: inbox_topic() or _item_topic)
print("(3) топики/ярлык:")
it = {"from": "Filipp-pcloc-dec", "lane": "pc"}
res.append(ok(DB._is_pc_item(it), "_is_pc_item → True (и по from, и по lane)"))
res.append(ok(DB._is_pc_item({"from": "Filipp-pcloc-dec"}), "_is_pc_item → True по одному from (старый Bridge без lane)"))
res.append(ok(DB._item_lane_label(it) == "pc", "ярлык полосы 'pc'"))
os.environ["PC_DEV_TOPIC_ID"] = "829"
try:
    res.append(ok(DB._item_topic(it) == 829, "тема карточек = PC-дев (829), не 328"))
finally:
    os.environ.pop("PC_DEV_TOPIC_ID", None)

print()
if all(res):
    print(f"OK: {len(res)}/{len(res)} проверок devbot-канала локального дирижёра")
    sys.exit(0)
print(f"FAIL: {sum(1 for r in res if not r)} из {len(res)} проверок красные")
sys.exit(1)
