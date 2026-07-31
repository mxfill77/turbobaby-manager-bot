"""Приёмник подтверждений: ОТВЕТ С НАЗВАННЫМ ОБЪЕКТОМ (инцидент карточки 95, 31.07.2026).

ЖИВОЙ ФАКТ, с которого снят регресс (не выдуманный):
  31.07.2026 09:23 и 09:24 UTC (16:23/16:24 по Бангкоку) владелец ДВАЖДЫ ответил на карточку
  задачи 95 в теме-инбоксе 1160 ДОСЛОВНО текстом «да systemctl restart splinter» — первый раз
  обычным сообщением, второй раз реплаем на саму карточку. Оба раза приёмник выдал общую справку
  «🤖 Это тема-инбокс подтверждений: «да N» / «нет N» или кнопки под карточкой…» и ответ НЕ принял.
  След: orchestrator_daemon.log 09:12:33 «curator: задача 93 → human, карточка задачей 94»,
  09:29:04 «curator-human: сводная карточка 95 закрыта владельцем (✅)».

ЖИВОЙ ФОРМАТ КАРТОЧКИ (мок = формат прода, класс row705→1268):
  тело карточки 95 = orchestrator_daemon._curator_human_render(93, [(пункт, 1)]);
  сам пункт — ДОСЛОВНО из result задачи 94 (read-only разведка очереди 31.07.2026, поле «что нужно»);
  сообщение в Telegram = обёртка devbot.report_results («⚠️ Задача 95 [vps] требует подтверждения…»).
  Объект в карточке назван в ОБРАТНЫХ КАВЫЧКАХ — `systemctl restart splinter`.

Проверяем:
 (R1) 16:23 — «да systemctl restart splinter» БЕЗ номера и БЕЗ реплая → КОНКРЕТНЫЙ отказ
      «не принято, потому что не понял, к какой карточке» (не общая справка), approve НЕ зовётся;
 (R2) 16:24 — тот же текст РЕПЛАЕМ на карточку 95 → привязка по реплаю + сверка объекта → approve(95);
 (R3) реплай на 95 с ЧУЖИМ объектом («да clasp redeploy») → явный отказ С УКАЗАНИЕМ ожидаемого;
 (R4) легаси «да 95» работает как раньше (approve), (R5) «нет 95» → failed;
 (R6) текст без «да»/«нет» в инбоксе → конкретное «не принято, потому что…», не общая справка;
 (R7) регресс 328: «да, поехали» приёмник НЕ перехватывает (прежний путь, зелёный роутер);
 (R8) «да 95 systemctl restart splinter» (номер + объект) → approve;
 (R9) карточка БЕЗ названного объекта + ответ с объектом → отказ «сверять не с чем», approve НЕ зовётся.
"""
import sys, asyncio
sys.path.insert(0, "/root/turbobaby-manager-bot")
import os
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ["CURATOR"] = "0"          # изоляция от боевого .env
os.environ["PLAN_ADAPT"] = "0"
os.environ["THEATER_ROUTER"] = "0"   # 328 — легаси-поведение без думателя-роутера
os.environ["PC_DEC_LOCAL"] = "0"
os.environ["INBOX_TOPIC_ID"] = "1160"
import devbot as DB

INBOX = 1160

# --- ЖИВОЙ ФОРМАТ: пункт карточки 95 ДОСЛОВНО (result задачи 94, разведка очереди 31.07.2026) ---
CARD95_ITEM = (
    "Нужно явное «да» владельца на `systemctl restart splinter`: фикс одометра (корни 1 и 2, "
    "commit bbbe458) уже в origin/main и зелёный по гейту (142 теста) и по живому регрессу 4957 "
    "(6/9 красных → 9/9 зелёных), но в проде НЕ действует, пока сервис работает на старом коде — "
    "в ТЗ рестарт был прямо запрещён до отдельного разрешения с названным объектом.")

# тело карточки 95 — ДОСЛОВНО как оно было В МОМЕНТ ИНЦИДЕНТА (подпись демона до 31.07.2026).
# Заморожено намеренно: это снимок с прода, по которому снят регресс. Подпись с тех пор
# изменилась (✅ теперь ставит задачу — класс карточек 95/100), поэтому актуальный формат
# проверяется ОТДЕЛЬНО, живым рендером — см. R10 внизу файла.
CARD95_RESULT = (
    "🧑 нужно от владельца (цель 93) — куратор задач по этим пунктам НЕ ставит:\n"
    f"1. {CARD95_ITEM}\n"
    "\n"
    "✅ — принял/сделал (карточка закроется), ❌ — отклонить. Новые пункты этой цели "
    "куратор дописывает в ЭТУ карточку (актуальный список — /inbox).")

# сообщение карточки в Telegram — обёртка devbot.report_results (needs_approval)
CARD95_TG = (
    f"⚠️ Задача 95 [vps] требует подтверждения красной зоны:\n\n{CARD95_RESULT}\n\n"
    "Подтвердить? Тапни кнопку ниже — или ответь «да 95» / «нет 95».")

# дословные сообщения владельца 16:23 и 16:24
OWNER_MSG = "да systemctl restart splinter"

GENERIC_HELP = "Это тема-инбокс подтверждений"   # общая справка — её быть НЕ должно


class FakeBridge:
    """Очередь: одна открытая карточка needs_approval. approve/complete — счётчики."""
    def __init__(s, items=None):
        s.items = items if items is not None else [
            {"id": 95, "from": "Filipp-328-dec", "lane": "vps",
             "status": "needs_approval", "result": CARD95_RESULT,
             "task_text": "[куратор владельцу цель 93] " + CARD95_ITEM}]
        s.approved = []
        s.completed = []
        s.enqueued = []
    def get_pending(s, status="new", lane=None):
        if status != "needs_approval":
            return {"ok": True, "items": []}
        return {"ok": True, "items": list(s.items)}
    def approve_task(s, qid, who):
        s.approved.append((qid, who))
        return {"ok": True}
    def complete_task(s, qid, st, res):
        s.completed.append((qid, st, res))
        return {"ok": True}
    def enqueue_task(s, frm, txt, lane=None):
        s.enqueued.append((frm, txt, lane))
        return {"ok": True, "id": 1}


SENDS = []

class FakeBot:
    async def send_message(self, chat_id, message_thread_id=None, text="", reply_markup=None):
        SENDS.append((message_thread_id, text, reply_markup))

class Ctx:
    bot = FakeBot()

class FakeUser:
    def __init__(s, uid): s.id = uid

class FakeReply:
    """Сообщение карточки, на которое владелец ответил реплаем."""
    def __init__(s, text): s.text = text; s.caption = None

class FakeMsg:
    def __init__(s, text, topic=INBOX, uid=DB.DEVBOT_USER, reply_to=None):
        s.text = text
        s.message_thread_id = topic
        s.from_user = FakeUser(uid)
        s.chat_id = DB.HQ_CHAT_ID
        s.reply_to_message = FakeReply(reply_to) if reply_to else None


def _run(msg, bridge):
    SENDS.clear()
    asyncio.run(DB.handle_command(msg, Ctx(), bridge))
    return "\n".join(t for _, t, _ in SENDS)


# R1: 16:23 — обычное сообщение, без номера и без реплая → КОНКРЕТНЫЙ отказ, не общая справка
def test_r1_plain_named_object_no_binding():
    b = FakeBridge()
    out = _run(FakeMsg(OWNER_MSG), b)
    assert b.approved == [] and b.completed == [], f"без привязки ничего не одобряем: {b.approved}"
    assert GENERIC_HELP not in out, f"общая справка вместо конкретного отказа: {out}"
    assert "не принято" in out.lower(), f"нет явного «не принято»: {out}"
    assert ("реплай" in out.lower() or "ответом на карточку" in out.lower()), \
        f"отказ обязан назвать причину и способ (номер / реплай): {out}"
    assert "95" in out, f"отказ обязан назвать открытые карточки, чтобы владелец попал точно: {out}"


# R2: 16:24 — ТОТ ЖЕ текст реплаем на карточку 95 → привязка по реплаю + сверка объекта → approve
def test_r2_named_object_by_reply():
    b = FakeBridge()
    out = _run(FakeMsg(OWNER_MSG, reply_to=CARD95_TG), b)
    assert b.approved == [(95, "Filipp")], f"реплай с названным объектом → approve(95): {b.approved} / {out}"
    assert GENERIC_HELP not in out, f"общая справка при принятом ответе: {out}"
    assert "systemctl restart splinter" in out, f"ответ обязан показать сверенный объект: {out}"


# R3: чужой объект в реплае → явный отказ С УКАЗАНИЕМ ожидаемого
def test_r3_object_mismatch_is_explicit():
    b = FakeBridge()
    out = _run(FakeMsg("да clasp redeploy", reply_to=CARD95_TG), b)
    assert b.approved == [], f"несовпавший объект НЕ одобряет: {b.approved} / {out}"
    assert "не принято" in out.lower(), f"молчание вместо отказа: {out}"
    assert "systemctl restart splinter" in out, f"отказ обязан назвать ОЖИДАЕМЫЙ объект: {out}"
    assert "clasp redeploy" in out, f"отказ обязан назвать, что услышал: {out}"


# R4/R5: легаси «да N» / «нет N» — байт-в-байт как раньше
def test_r4_legacy_yes_number():
    b = FakeBridge()
    out = _run(FakeMsg("да 95"), b)
    assert b.approved == [(95, "Filipp")], f"легаси «да 95» сломан: {b.approved} / {out}"

def test_r5_legacy_no_number():
    b = FakeBridge()
    out = _run(FakeMsg("нет 95"), b)
    assert b.completed == [(95, "failed", "отклонено Филиппом")], f"легаси «нет 95» сломан: {b.completed}"
    assert b.approved == []


# R6: текст без «да»/«нет» в инбоксе → конкретное «не принято, потому что…», не общая справка
def test_r6_unparsed_gets_concrete_reason():
    b = FakeBridge()
    out = _run(FakeMsg("systemctl restart splinter"), b)
    assert b.approved == [] and b.completed == []
    assert GENERIC_HELP not in out, f"общая справка вместо конкретной причины: {out}"
    assert "не принято" in out.lower() and "потому что" in out.lower(), \
        f"нужна форма «не принято, потому что …»: {out}"


# R7: регресс 328 — «да, поехали» приёмник НЕ перехватывает (прежний путь)
def test_r7_no_hijack_in_328():
    b = FakeBridge()
    out = _run(FakeMsg("да, поехали", topic=DB.DEVBOT_TOPIC), b)
    assert b.approved == [] and b.completed == [] and b.enqueued == [], \
        f"328: свободный текст не должен уходить в приёмник: {b.approved}/{b.enqueued}"
    assert "не зелёная команда" in out, f"328 обязан вести себя как раньше: {out}"


# R8: номер + названный объект в одном сообщении
def test_r8_number_plus_object():
    b = FakeBridge()
    out = _run(FakeMsg("да 95 systemctl restart splinter"), b)
    assert b.approved == [(95, "Filipp")], f"«да N <объект>» → approve: {b.approved} / {out}"


# R9: карточка без названного объекта → сверять не с чем → отказ, approve НЕ зовётся
def test_r9_card_without_object():
    b = FakeBridge(items=[{"id": 7, "from": "Filipp-328-dev", "lane": "vps",
                           "status": "needs_approval",
                           "result": "нужно решение владельца по спорному тарифу"}])
    tg = ("⚠️ Задача 7 [vps] требует подтверждения красной зоны:\n\n"
          "нужно решение владельца по спорному тарифу\n\n"
          "Подтвердить? Тапни кнопку ниже — или ответь «да 7» / «нет 7».")
    out = _run(FakeMsg("да тариф 500 бат", reply_to=tg), b)
    assert b.approved == [], f"неверифицируемый объект НЕ одобряет: {b.approved} / {out}"
    assert "не принято" in out.lower(), f"нужен явный отказ: {out}"


# R10: АКТУАЛЬНАЯ подпись карточки (живой рендер демона) приёмник не ломает.
# Зачем: подпись сводной карточки сменилась 31.07.2026 (✅ теперь СТАВИТ задачу), а объект
# сверки devbot берёт из ТЕЛА карточки — служебный текст подписи не должен подсовывать
# приёмнику посторонний объект или прятать настоящий.
def test_r10_current_render_still_binds():
    import orchestrator_daemon as OD
    body = OD._curator_human_render(93, [(CARD95_ITEM, 1)])
    assert DB._card_objects(body) == ["systemctl restart splinter"], \
        f"подпись карточки подменила/размножила объект сверки: {DB._card_objects(body)}"
    b = FakeBridge(items=[{"id": 95, "from": "Filipp-328-dec", "lane": "vps",
                           "status": "needs_approval", "result": body,
                           "task_text": "[куратор владельцу цель 93] " + CARD95_ITEM}])
    tg = (f"⚠️ Задача 95 [vps] требует подтверждения красной зоны:\n\n{body}\n\n"
          "Подтвердить? Тапни кнопку ниже — или ответь «да 95» / «нет 95».")
    out = _run(FakeMsg(OWNER_MSG, reply_to=tg), b)
    assert b.approved == [(95, "Filipp")], f"на НОВОЙ подписи привязка сломалась: {b.approved} / {out}"


if __name__ == "__main__":
    failed = []
    for name, fn in sorted(list(globals().items())):
        if not (name.startswith("test_") and callable(fn)):
            continue
        try:
            fn()
            print(f"  ✅ {name}")
        except AssertionError as e:
            failed.append(name)
            print(f"  ❌ {name}: {e}")
    if failed:
        print(f"test_named_object_approval: КРАСНЫХ {len(failed)} — {', '.join(failed)}")
        sys.exit(1)
    print("test_named_object_approval: OK")
