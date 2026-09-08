"""ФИКС КЛАССА «задание ящика Штаба умирает молча» (08.09.2026, повод — ряд 172).

Отчёт в 328 доезжал, только если метка отправителя СОВПАДАЛА с именем из закрытого списка
`QUEUE_FROMS`. Список ведётся руками, а метку заводит производитель — поэтому каждый НОВЫЙ
источник очереди молча терял done/failed/needs_approval. Это ЧЕТВЁРТЫЙ повтор одного класса
(Filipp-pcloc-dec = 682a881, Filipp-curator, Filipp-revizor = карточка 244, Filipp).

ЗАМЕР (живой снимок очереди 08.09.2026, все статусы, обе полосы, 203 ряда): метки списку НЕ
известны у ЧЕТЫРЁХ источников — Filipp-shtab 91 · Filipp-review-claim 63 · Filipp-recon 6 ·
Filipp-recon-ask 5 = 165 рядов (81 %) невидимы. Среди них 8 failed ящика Штаба и ПЯТЬ
needs_approval Filipp-recon-ask — открытые вопросы, которых владелец не видел ни разу.

Поэтому чинится ПРИЗНАК, а не список: `devbot._is_our_source` судит, ЧЕЙ ряд, а не как он назван.
Забор при этом НЕ снят — чужой производитель темы 205 (`pc_agent-205`) по-прежнему молчит
(голден D2 `test_inprogress_report`), и «полный отчёт по факту наличия ряда» отвергнут именно
потому, что снял бы этот забор. Сеть/бот замоканы."""
import sys, asyncio, datetime
import os
# ЛОВУШКА МЕТОДА (записана в CLAUDE.md, урок прогона «до» через git worktree): хардкод боевого
# корня в sys.path даёт ЛОЖНОЕ ЗЕЛЁНОЕ — модуль приезжает из живого дерева, а не из проверяемого.
# Поэтому корень считается ОТ КАТАЛОГА ЭТОГО ФАЙЛА, а чужой корень из пути УБИРАЕТСЯ (вернуть
# свой в начало НЕ довольно — боевой ниже по списку всё равно разрешил бы импорт).
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:] = [p for p in sys.path
               if os.path.abspath(p or ".") != "/root/turbobaby-manager-bot" or _REPO == p]
sys.path.insert(0, _REPO)
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ["TASK_TIMEOUT"] = "600"
os.environ["TASK_TIMEOUT_DEV"] = "2700"
os.environ["PC_STEP_TIMEOUT"] = "3600"
os.environ["INBOX_TOPIC_ID"] = "0"      # инбокс выключен → needs_approval идёт по _item_topic
os.environ["CURATOR"] = "0"             # предмет теста — видимость отчёта, не вердикт куратора
import devbot as DB

SENDS = []                              # (thread_id, text)


class FakeBot:
    async def send_message(self, chat_id, message_thread_id=None, text="", **kw):
        SENDS.append((message_thread_id, text))
        return None


class Ctx:
    bot = FakeBot()


class FakeBridge:
    """get_pending по статусам: отдаём ряды заданного снимка, прочее пусто."""
    def __init__(s, items):
        s.items = items

    def get_pending(s, status="new", lane=None):
        return {"ok": True,
                "items": [dict(i) for i in s.items if str(i.get("status")) == status]}


def _iso(age_sec):
    t = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=age_sec)
    return t.isoformat().replace("+00:00", "Z")


def _reset(items):
    SENDS.clear()
    DB._reported.clear(); DB._asked.clear()
    DB._inprogress_seen.clear(); DB._stalled.clear()
    DB._queue_busy = None; DB._closed_since_busy = []
    DB._report_seeded = True            # пропустить seed-on-start
    DB._poll_bridge = None; DB._poll_bridge_for = None   # сбросить кэш опросного клиента
    DB.BRIDGE = FakeBridge(items)


def run():
    asyncio.run(DB.report_results(Ctx()))


def row(qid, frm, status, text="работа", lane=None, result="итог"):
    it = {"id": qid, "from": frm, "status": status, "task_text": text,
          "result": result, "updated": _iso(5)}
    if lane:
        it["lane"] = lane
    return it


RES = []


def ok(cond, name):
    RES.append((bool(cond), name))
    return bool(cond)


# ============ (1) ПОВОД: ряд 172 ящика Штаба, failed → карточка в 328 ============
def test_shtab_failed_card_reaches_328():
    it = row(172, "Filipp-shtab", "failed",
             text="[от Штаба дата=2026-09-08 ключ=01-u] ЗАДАНИЕ ШТАБА ИЗ ЯЩИКА", lane="pc")
    _reset([it])
    run()
    cards = [(t, x) for t, x in SENDS if "172" in x]
    ok(cards, "ряд 172 (Filipp-shtab, failed) порождает карточку — ДО фикса её не было вовсе")
    ok(any("❌" in x for _t, x in cards), "карточка несёт ❌ (failed), а не молчание")
    ok(all(t == DB.DEVBOT_TOPIC for t, _x in cards),
       f"карточка ящика Штаба уходит в 328 (DEVBOT_TOPIC), а не в тему PC-дев: {cards}")


def test_shtab_done_card_reaches_328():
    _reset([row(173, "Filipp-shtab", "done", lane="pc")])
    run()
    ok(any("173" in x and "✅" in x for _t, x in SENDS), "done ящика Штаба тоже доезжает")


# ============ (2) ОСТАЛЬНЫЕ ТРИ НЕВИДИМЫХ ИСТОЧНИКА ЖИВОГО ЗАМЕРА ============
def test_all_unknown_live_sources_visible():
    """Дописывание одного имени вылечило бы 1 источник из 4. Признак лечит все сразу."""
    _reset([row(180, "Filipp-review-claim", "done", lane="pc"),
            row(181, "Filipp-recon", "done", lane="pc"),
            row(182, "Filipp-shtab", "failed", lane="pc")])
    run()
    for qid in (180, 181, 182):
        ok(any(str(qid) in x for _t, x in SENDS), f"ряд {qid} невидимого источника доезжает")


def test_recon_ask_needs_approval_reaches_owner():
    """ПЯТЬ таких рядов висели needs_approval и владелец не видел их НИ РАЗУ (класс карточки 244)."""
    _reset([row(199, "Filipp-recon-ask", "needs_approval",
                text="[разведка-заявка] нужно твоё решение", lane="pc")])
    run()
    ask = [x for _t, x in SENDS if "199" in x and "подтверждения" in x]
    ok(ask, f"needs_approval незнакомого НАШЕГО источника доезжает как карточка: {SENDS}")


# ============ (3) ЗАБОР ЧЕСТЕРТОНА: ЧУЖОЙ ПРОИЗВОДИТЕЛЬ ПО-ПРЕЖНЕМУ МОЛЧИТ ============
def test_foreign_pc_agent_still_ignored():
    """Очередь — общая таблица; pc_agent/userbot темы 205 пишет в неё свои ряды. Их в 328 не
    выносим — иначе «отчёт по факту наличия ряда» снёс бы настоящий забор (голден D2)."""
    _reset([row(8, "pc_agent-205", "failed", text="не наше")])
    run()
    ok(SENDS == [], f"ряд чужого производителя НЕ выносится: {SENDS}")


def test_foreign_variants_ignored():
    for frm in ("pc_agent-205", "pc_agent", "userbot", "", "  ", "Someone-else"):
        ok(not DB._is_our_source({"from": frm}), f"чужая/пустая метка {frm!r} — не наша")
    ok(not DB._is_our_source({}), "ряд без метки from — не наш")
    ok(not DB._is_our_source(None), "None не роняет предикат и не считается нашим")


def test_prefix_is_not_substring():
    """Признак — подпись НАЧАЛА метки, а не вхождение слова: чужой ряд не станет нашим,
    упомянув имя владельца в середине."""
    ok(not DB._is_our_source({"from": "pc_agent-Filipp"}), "имя владельца в СЕРЕДИНЕ — не наш ряд")
    ok(not DB._is_our_source({"from": "notFilipp-328"}), "приклеенный префикс — не наш ряд")
    ok(not DB._is_our_source({"from": "Filipping"}), "«Filipp» без разделителя — не наш ряд")


# ============ (4) ИЗВЕСТНЫЕ МЕТКИ РАБОТАЮТ КАК РАНЬШЕ ============
def test_known_labels_unchanged():
    for frm in DB.QUEUE_FROMS:
        ok(DB._is_our_source({"from": frm}), f"именованная метка {frm} по-прежнему наша")


def test_dev_dec_curator_still_report():
    _reset([row(20, DB.QUEUE_FROM_DEV, "done", result="итог FACT: сделано"),
            row(21, DB.QUEUE_FROM_DEC, "failed"),
            row(22, DB.QUEUE_FROM_CURATOR, "done")])
    run()
    for qid in (20, 21, 22):
        ok(any(str(qid) in x for _t, x in SENDS), f"метка dev/dec/curator: ряд {qid} рапортуется")
    ok(all(t == DB.DEVBOT_TOPIC for t, _x in SENDS), "vps-метки — тема 328, как было")


def test_pc_labels_keep_their_topic():
    """Метка не потеряла работу: она по-прежнему решает ТЕМУ карточки."""
    _reset([row(30, DB.QUEUE_FROM_PC_DEV, "done", lane="pc")])
    run()
    ok(SENDS and all(t == (DB.pc_dev_topic() or DB.DEVBOT_TOPIC) for t, _x in SENDS),
       f"pc-метка уходит в тему PC-дев, а не в 328: {SENDS}")
    ok(DB._item_topic({"from": "Filipp-shtab", "lane": "pc"}) == DB.DEVBOT_TOPIC,
       "незнакомая НАША метка получает тему 328, даже когда исполнялась на полосе pc")


# ============ (5) СОГЛАСОВАННОСТЬ: СЧЁТЧИКИ ВИДЯТ ТО ЖЕ, ЧТО ОТЧЁТ ============
def test_open_count_sees_unknown_source():
    """Если бы гейт сменился ТОЛЬКО в отчёте, счётчики остались бы на списке имён и сигнал
    «очередь пуста» звучал бы при живом задании Штаба — та же немота с другой стороны."""
    by = {st: [] for st in DB._REPORT_STATUSES}
    by["in_progress"] = [row(1, "Filipp-shtab", "in_progress")]
    by["needs_approval"] = [row(2, "Filipp-recon-ask", "needs_approval")]
    ok(DB._queue_open_count(by) == 2,
       f"открытые ряды незнакомых НАШИХ меток считаются: {DB._queue_open_count(by)}")
    by2 = {st: [] for st in DB._REPORT_STATUSES}
    by2["in_progress"] = [row(3, "pc_agent-205", "in_progress")]
    ok(DB._queue_open_count(by2) == 0, "чужой ряд очередь непустой не делает")


def test_claim_events_gate_matches():
    """Журнал взятий судится тем же признаком — иначе «взял в работу» молчал бы для Штаба."""
    ok(DB._is_our_source({"from": "Filipp-shtab", "id": 1}), "событие взятия ряда Штаба — наше")


# ============ (6) СПИСОК ИМЁН БОЛЬШЕ НЕ ГЕЙТ ============
def test_list_is_no_longer_the_gate():
    ok("Filipp-shtab" not in DB.QUEUE_FROMS,
       "Filipp-shtab НЕ дописан в список — лечился признак, а не имя")
    ok(DB._is_our_source({"from": "Filipp-shtab"}),
       "и при этом ряд Штаба виден: гейт — признак, не членство в списке")
    ok(DB._is_our_source({"from": "Filipp-совершенно-новый-источник-2027"}),
       "будущий источник НАШЕЙ стороны виден сам, без правки кода — класс закрыт вперёд")


def main():
    for fn in sorted([f for n, f in globals().items() if n.startswith("test_") and callable(f)],
                     key=lambda f: f.__code__.co_firstlineno):
        fn()
    bad = [n for good, n in RES if not good]
    for good, n in RES:
        print(("  ok  " if good else "  FAIL") + " " + n)
    print(f"\n{len(RES) - len(bad)}/{len(RES)} проверок зелёные")
    if bad:
        print("КРАСНОЕ:")
        for n in bad:
            print("  - " + n)
        sys.exit(1)


if __name__ == "__main__":
    main()
