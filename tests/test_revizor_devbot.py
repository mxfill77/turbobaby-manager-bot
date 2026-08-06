"""Куратор цели 365, шаг 1 (06.08.2026): карточки РЕВИЗОРА доезжают до владельца.

КЛАСС — тот же, что 682a881 (Filipp-pcloc-dec) и Filipp-curator: метки НЕТ в QUEUE_FROMS →
фильтр отчётов `_poll_queue_sync` (devbot.py:113, `str(it.get("from")) in QUEUE_FROMS`)
выкидывает задачу, и её needs_approval-карточка НИКОГДА не доезжает до владельца.

ЖИВОЙ ФАКТ (снимок очереди 06.08.2026, 372 задачи, read-only get_pending по всем статусам):
метка `Filipp-revizor` стоит у 2 задач, и одна из них — id=244, status=needs_approval,
lane=pc, created 2026-08-03 — ЕДИНСТВЕННЫЙ открытый needs_approval во всей очереди; висит
третьи сутки. Метка `Filipp` (голая, 3 задачи id 14/89/90 — ручные пробы канала) тоже
отсутствовала в списке: их отчёты так же отсеивались.

Фикстуры ДОСЛОВНЫЕ — поля взяты из снимка очереди (id/from/lane/task_text/result).
Сети/Telegram/моста нет — всё мокнуто."""
import os, sys
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")

def ok(c, l): print(("  PASS " if c else "  FAIL ") + l); return c
res = []

import devbot as DB

# (1) метки-константы и их место в группах
print("(1) метки в фильтре отчётов:")
res.append(ok(getattr(DB, "QUEUE_FROM_REVIZOR", None) == "Filipp-revizor",
              "константа QUEUE_FROM_REVIZOR = Filipp-revizor"))
res.append(ok("Filipp-revizor" in DB.QUEUE_FROMS, "Filipp-revizor в QUEUE_FROMS (фильтр отчётов)"))
res.append(ok("Filipp-revizor" in DB.QUEUE_FROMS_PC,
              "Filipp-revizor в QUEUE_FROMS_PC (ревизор — производитель полосы pc, lane=pc)"))
res.append(ok(getattr(DB, "QUEUE_FROM_OWNER", None) == "Filipp",
              "константа QUEUE_FROM_OWNER = Filipp (ручные пробы владельца)"))
res.append(ok("Filipp" in DB.QUEUE_FROMS, "Filipp в QUEUE_FROMS (отчёты ручных проб доезжают)"))
res.append(ok("Filipp" not in DB.QUEUE_FROMS_PC,
              "Filipp НЕ в QUEUE_FROMS_PC (ставится с обеих полос, тема = 328 по постановке)"))

# (2) ГЛАВНОЕ: дословная задача 244 проходит фильтр _poll_queue_sync
print("(2) фильтр _poll_queue_sync на ДОСЛОВНОЙ задаче 244:")
_R244 = ("🔍 Ревизор: находки — требуют твоего решения (спорный тариф / политика / "
         "неоднозначный кейс). Ревизор сам ничего не правит и клиентам не пишет.\n"
         "• [класс #92] окно 690197908: чек «нет утверждений о наличии»")

class PB:                       # мок без get_pending_multi → по-статусный путь
    def get_pending(self, st, lane="all"):
        items = []
        if st == "needs_approval":
            items = [{"id": 244, "from": "Filipp-revizor", "lane": "pc",
                      "task_text": "[ревизор-находки] сводная карточка находок ревизора",
                      "result": _R244},
                     {"id": 245, "from": "Кто-то-чужой", "lane": "pc",
                      "task_text": "чужое", "result": "x"}]
        if st == "done":
            items = [{"id": 6, "from": "Filipp-revizor", "lane": "pc",
                      "task_text": "[ревизор-находки] сводная карточка находок ревизора",
                      "result": "🔍 owner-находки ревизора приняты Филиппом"},
                     {"id": 89, "from": "Filipp", "lane": "pc",
                      "task_text": "ПРОВЕРКА КАНАЛА ОДОБРЕНИЯ С ПК",
                      "result": "RESULT: канал одобрения с ПК жив."}]
        return {"ok": True, "items": items}

by = DB._poll_queue_sync(PB())
res.append(ok(by is not None and [it["id"] for it in by["needs_approval"]] == [244],
              "needs_approval ревизора (244) прошёл фильтр, чужой from отсеян"))
res.append(ok(by is not None and 6 in [it["id"] for it in by["done"]],
              "done ревизора (6) прошёл фильтр"))
res.append(ok(by is not None and 89 in [it["id"] for it in by["done"]],
              "done ручной пробы Filipp (89) прошёл фильтр"))

# (3) маршрутизация карточки 244: needs_approval → ИНБОКС (там, где владелец отвечает)
print("(3) маршрут карточки владельцу:")
it244 = {"id": 244, "from": "Filipp-revizor", "lane": "pc"}
res.append(ok(DB._is_pc_item(it244), "_is_pc_item → True"))
res.append(ok(DB._is_pc_item({"from": "Filipp-revizor"}),
              "_is_pc_item → True по одному from (старый Bridge без lane)"))
res.append(ok(DB._item_lane_label(it244) == "pc", "ярлык полосы 'pc'"))
os.environ["PC_DEV_TOPIC_ID"] = "829"
os.environ["INBOX_TOPIC_ID"] = "1160"
try:
    # живой код доставки: _approval_topic = inbox_topic() or _item_topic(it)
    res.append(ok((DB.inbox_topic() or DB._item_topic(it244)) == 1160,
                  "needs_approval → инбокс 1160 (владелец отвечает там)"))
    os.environ["INBOX_TOPIC_ID"] = "0"
    res.append(ok((DB.inbox_topic() or DB._item_topic(it244)) == 829,
                  "инбокс выключен → тема PC-дев 829 (не 328): ревизор — полоса pc"))
    res.append(ok(DB._item_topic({"from": "Filipp", "lane": "vps"}) == DB.DEVBOT_TOPIC,
                  "ручная проба Filipp → 328 (тема постановки)"))
finally:
    os.environ.pop("PC_DEV_TOPIC_ID", None)
    os.environ.pop("INBOX_TOPIC_ID", None)

# (4) ГРАНИЦА: расширение фильтра не рождает пачку карточек из истории.
#     Терминальные задачи, закрытые ДО старта процесса, гасит seed (_seed_silences);
#     needs_approval НЕ сидится намеренно — незакрытый вопрос переспрашивают (devbot.py:1719).
print("(4) граница — история не спамит:")
old = {"id": 6, "from": "Filipp-revizor", "updated": "2026-07-28T12:29:37.029Z"}
res.append(ok(DB._seed_silences(old), "старая done ревизора гасится seed-ом (пачки не будет)"))
res.append(ok(not DB._seed_silences({"id": 999, "from": "Filipp-revizor", "updated": None}),
              "время не прочли → НЕ гасим (видимость дороже лишней карточки)"))

# (5) чужие метки по-прежнему отсеиваются (список не стал «пропускать всё»)
print("(5) фильтр не ослаблен:")
for foreign in ("Filipp-revizor-x", "revizor", "filipp", "Filipp-", ""):
    res.append(ok(foreign not in DB.QUEUE_FROMS, f"чужая метка {foreign!r} НЕ в QUEUE_FROMS"))

print()
if all(res):
    print(f"OK: {len(res)}/{len(res)} проверок канала карточек ревизора")
    sys.exit(0)
print(f"FAIL: {sum(1 for r in res if not r)} из {len(res)} проверок красные")
sys.exit(1)
