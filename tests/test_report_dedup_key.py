"""Дыра видимости 28.07.2026 (задача 9) — регресс.

Класс бага: дедуп карточек devbot жил по ГОЛОМУ номеру задачи. Лист очереди пересобрали,
нумерация пошла заново с 1, а в памяти процесса от seed-on-start лежали номера прежней
очереди (1..399) → три свежих failed (1, 2, 3) были отброшены как «уже показанные» и в 328
НЕ пришли. Ни в логе, ни в теме следа не осталось.

Что доказывает файл:
  1) ключ дедупа = номер + генерация (created строки очереди) — пересборка очереди видимость
     больше не обнуляет ни при каких номерах;
  2) seed-on-start гасит ТОЛЬКО терминальное ДО старта процесса; всё, что финишировало после
     старта, рапортуется при любом номере; нечитаемое время → не гасим (видимость дороже);
  3) result, упёршийся в потолок исполнителя (4500), несёт ЯВНУЮ пометку обрезки с числом —
     молча резать нельзя;
  4) пометки «по номеру» (кнопка/«нет N») не глушат более позднюю задачу того же номера.

Сеть, Telegram и время замоканы; Bridge — фейковый (get_pending по статусам)."""
import asyncio, os, sys, time, datetime

sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")
# Жёсткая изоляция окружения (урок test_curator: headless-тест наследует env демона с боевыми
# флагами — setdefault НЕ хватает): куратор и тема-инбокс не должны менять форму карточек.
os.environ["CURATOR"] = "0"
os.environ["INBOX_TOPIC_ID"] = "0"
os.environ["TASK_TIMEOUT"] = "600"
os.environ["TASK_TIMEOUT_DEV"] = "2700"
os.environ["PC_STEP_TIMEOUT"] = "3600"

import devbot as DB

_res = []


def ok(cond, label):
    _res.append(bool(cond))
    print(("  PASS " if cond else "  FAIL ") + label)
    return cond


# ── инфраструктура ───────────────────────────────────────────────────────────
SENDS = []          # (topic, text)


class FakeBot:
    class _M:
        message_id = 777

    async def send_message(self, chat_id, message_thread_id=None, text="", **kw):
        SENDS.append((message_thread_id, text))
        return FakeBot._M()


class Ctx:
    bot = FakeBot()


class FakeBridge:
    """get_pending(status) по подготовленному снимку; без url/token → devbot опрашивает его сам."""
    def __init__(s, snapshot):
        s.snapshot = snapshot

    def get_pending(s, status="new", lane=None):
        return {"ok": True, "items": [dict(i) for i in s.snapshot.get(status, [])]}


def iso(ts):
    """epoch-секунды → ISO в формате очереди Bridge ('2026-07-28T10:18:55.172Z')."""
    return (datetime.datetime.fromtimestamp(ts, datetime.timezone.utc)
            .isoformat().replace("+00:00", "Z"))


NOW = time.time()
START = NOW - 300           # процесс bot.py стартовал 5 минут назад


def item(id, created_ts, updated_ts=None, st="failed", frm=None, result="итог",
         text="сделай X"):
    return {"id": id, "created": iso(created_ts),
            "updated": iso(updated_ts if updated_ts is not None else created_ts),
            "status": st, "from": frm or DB.QUEUE_FROM_DEV, "lane": "vps",
            "result": result, "task_text": text}


def reset(snapshot, seeded=True, start=START):
    SENDS.clear()
    DB._reported.clear(); DB._asked.clear()
    DB._inprogress_seen.clear(); DB._stalled.clear()
    DB._curator_pending.clear()
    DB._report_seeded = seeded
    DB._PROC_START_TS = start
    DB.BRIDGE = FakeBridge(snapshot)


def tick():
    asyncio.run(DB.report_results(Ctx()))


def cards(needle="Задача"):
    return [t for _, t in SENDS if needle in t]


# ── 1. РЕГРЕСС ИНЦИДЕНТА: пересозданная очередь ──────────────────────────────
print("1. Пересобранная очередь: номера пошли заново с 1 — карточки ПРИХОДЯТ:")
# Тик 1 — seed по СТАРОЙ очереди (её задачи 1..3 завершились задолго до старта процесса)
old = {"failed": [item(1, START - 90000), item(2, START - 89000), item(3, START - 88000)]}
reset(old, seeded=False)
tick()
ok(SENDS == [], f"seed-on-start молчит по истории старой очереди: {SENDS}")
ok(len(DB._reported) == 3, f"история помечена показанной (3 записи), факт {len(DB._reported)}")

# Лист очереди пересобрали: те же номера 1..3, но СВЕЖИЕ строки (created сегодня)
DB.BRIDGE = FakeBridge({"failed": [item(1, NOW - 60, NOW - 30),
                                   item(2, NOW - 50, NOW - 25),
                                   item(3, NOW - 40, NOW - 20)]})
DB._poll_bridge = None          # сбросить кеш клиента опроса
tick()
got = cards()
ok(len(got) == 3, f"три failed новой очереди доехали (было 0 — инцидент 28.07): {len(got)}")
ok(all(any(f"Задача {n} " in t for t in got) for n in (1, 2, 3)),
   f"карточки именно по номерам 1,2,3: {[t[:24] for t in got]}")

print("2. Повтор той же генерации НЕ дублируется:")
n_before = len(SENDS)
tick()
ok(len(SENDS) == n_before, f"второй тик не шлёт дублей: +{len(SENDS) - n_before}")


# ── 3. SEED ПО ВРЕМЕНИ, А НЕ ПО НОМЕРУ ───────────────────────────────────────
print("3. Seed гасит только терминальное ДО старта; свежее проходит при любом номере:")
snap = {"failed": [
    item(1, NOW - 30, NOW - 10),                 # НОМЕР МАЛЫЙ, но финиш ПОСЛЕ старта
    item(400, START - 50000, START - 50000),     # номер большой, финиш до старта → история
]}
reset(snap, seeded=False)
tick()
ok(SENDS == [], "первый (seed) тик молчит всегда")
tick()
got = cards()
ok(len(got) == 1 and "Задача 1 " in got[0],
   f"после seed рапортуется задача 1 (пришла ПОСЛЕ старта), и только она: {[t[:24] for t in got]}")

print("4. Окно рестарта (SEED_GRACE_SEC): финиш за секунды до старта seed'ом НЕ гасится:")
snap = {"done": [item(5, START - 200, START - 5, st="done"),        # финиш за 5с до старта
                 item(6, START - 9000, START - 8000, st="done")]}   # финиш задолго до старта
reset(snap, seeded=False)
tick(); tick()
got = cards()
ok(len(got) == 1 and "Задача 5 " in got[0],
   f"задача 5 (окно рестарта) видна, 6 (история) — нет: {[t[:24] for t in got]}")

print("5. Нечитаемое время → seed НЕ гасит (видимость дороже лишней карточки):")
bad = item(9, NOW - 100, st="done")
bad["updated"] = ""
reset({"done": [bad]}, seeded=False)
tick(); tick()
ok(len(cards()) == 1, f"задача с пустым updated отрапортована: {[t[:24] for t in cards()]}")


# ── 6. ОБРЕЗКА RESULT ────────────────────────────────────────────────────────
print("6. Result на потолке исполнителя → ЯВНАЯ пометка обрезки:")
long_res = "щ" * DB.RESULT_CAP
reset({"done": [item(11, NOW - 60, NOW - 30, st="done", result=long_res)]})
tick()
txt = "".join(t for _, t in SENDS)
ok("РЕЗУЛЬТАТ ОБРЕЗАН" in txt, "карточка несёт пометку «РЕЗУЛЬТАТ ОБРЕЗАН»")
ok(str(DB.RESULT_CAP) in txt, f"в пометке названо число ({DB.RESULT_CAP})")
ok("хвост срезан ДО записи" in txt, "сказано, что хвост потерян ДО очереди (в карточке его нет)")

reset({"done": [item(12, NOW - 60, NOW - 30, st="done", result="коротко")]})
tick()
ok("ОБРЕЗАН" not in "".join(t for _, t in SENDS), "короткий result — БЕЗ пометки обрезки")

print("7. Тот же потолок у конверта needs_approval:")
reset({"needs_approval": [item(13, NOW - 60, st="needs_approval", result=long_res)]})
tick()
ok("РЕЗУЛЬТАТ ОБРЕЗАН" in "".join(t for _, t in SENDS), "конверт тоже помечает обрезку")


# ── 8. ДЕДУП ОСТАЛЬНЫХ КАРТОЧЕК ПО ГЕНЕРАЦИИ ─────────────────────────────────
print("8. needs_approval: тот же номер из новой очереди спрашивается заново:")
reset({"needs_approval": [item(2, NOW - 300, st="needs_approval", result="op=clasp")]})
tick()
n1 = len(cards("требует подтверждения"))
tick()
n2 = len(cards("требует подтверждения"))
ok(n1 == 1 and n2 == 1, f"один и тот же конверт спрошен РОВНО раз: {n1}/{n2}")
DB.BRIDGE = FakeBridge({"needs_approval": [item(2, NOW - 5, st="needs_approval", result="op=clasp")]})
DB._poll_bridge = None
tick()
ok(len(cards("требует подтверждения")) == 2,
   f"конверт №2 из ПЕРЕСОЗДАННОЙ очереди спрошен снова: {len(cards('требует подтверждения'))}")

print("9. in_progress: анонс «в работе» — раз на генерацию, не раз на номер:")
reset({"in_progress": [item(3, NOW - 60, NOW - 10, st="in_progress")]})
tick(); tick()
ok(len(cards("в работе")) == 1, f"анонс один раз: {len(cards('в работе'))}")
DB.BRIDGE = FakeBridge({"in_progress": [item(3, NOW - 5, NOW - 1, st="in_progress")]})
DB._poll_bridge = None
tick()
ok(len(cards("в работе")) == 2, f"новая задача №3 (др. генерация) анонсирована: {len(cards('в работе'))}")


# ── 10. ПОМЕТКИ «ПО НОМЕРУ» (кнопка / «нет N») ───────────────────────────────
print("10. «нет N» глушит ТУ задачу, но не более позднюю с тем же номером:")
reset({})
DB._mark_seen_by_id(DB._reported, 7)
older = item(7, NOW - 600, NOW - 5, result="отклонено Филиппом")
newer = item(7, NOW + 5, NOW + 9, result="итог новой задачи 7")
ok(DB._seen(DB._reported, older), "отклонённая задача 7 считается показанной (дубля не будет)")
ok(not DB._seen(DB._reported, newer), "задача 7, СОЗДАННАЯ позже пометки, — не глушится")

print("11. «да N» снимает пометку → терминал рапортуется штатно:")
reset({})
it7 = item(7, NOW - 600, NOW - 5)
DB._mark_seen(DB._reported, it7)
ok(DB._seen(DB._reported, it7), "перед approve пометка стоит")
DB._forget_seen(DB._reported, 7)
ok(not DB._seen(DB._reported, it7), "после approve пометка снята")

print("12. Отсутствие created (старый/чужой источник) — деградация, не падение:")
reset({})
noc = {"id": 1, "status": "failed", "from": DB.QUEUE_FROM, "result": "x"}
ok(not DB._seen(DB._reported, noc), "без created задача сначала не показана")
DB._mark_seen(DB._reported, noc)
ok(DB._seen(DB._reported, noc), "после пометки — показана (поведение как у прежнего дедупа по id)")


fails = _res.count(False)
print(f"\nИТОГ: {'ВСЕ PASS' if fails == 0 else f'ЕСТЬ FAIL ({fails}/{len(_res)})'}")
sys.exit(0 if fails == 0 else 1)
