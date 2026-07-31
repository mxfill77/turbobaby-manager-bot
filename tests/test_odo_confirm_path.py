"""Класс-фикс одометра, заход 1: ПУТЬ ПОДТВЕРЖДЕНИЯ (корни 1 и 2, NMAX 155 GREEN-B 4957).

ЖИВОЙ ФОРМАТ — не выдуманный: дословная последовательность 29.07.2026, чат -1002751134848,
тема 79, снятая с прода (splinter.log, строки 176287…176316):

  09:24:39  текст механика @extthiwxer:
            «На этом мотоцикле заменили моторное масло, масло в редукторе и передние и задние»
            parse: type=event event_type=repair mileage=None works=['замена моторного масла',
                   'замена масла в редукторе', 'замена передних тормозных колодок',
                   'замена задних тормозных колодок']                        ← ЧЕТЫРЕ работы
            → «инфо-работы отложены до пробега: ['замена передних тормозных колодок',
                'замена задних тормозных колодок'] (тема 79)»
            → «работы группы B без пробега → то_заявка ждёт_факт: ['gear']»
  09:32:14  фото приборки → vision: fuel=full mileage=38982 conf=high   (СЫРОЙ OCR, не подтверждён)
            parse: type=None event_type=None mileage=None works=[]
  09:32:16  КОРЕНЬ 1 → «инфо-работа в историю: «замена передних тормозных колодок — 38982 км»
                        msg_id=info:4957:колодки:38982 add_event ok=True saved=True dup=None»
  09:32:18  «инфо-работа в историю: «замена задних тормозных колодок — 38982 км» … dup=True»
  09:32:20  add_event msg_id=-1002751134848:10855 info_works=0 km_now=38982 event_type=photo
            (ветка ОБЫЧНОГО события гейт 06c1ab2 уже держала — mileage там пуст)
            → вопрос «📟 Вижу пробег 38982 км по NMAX 155 GREEN-B 4957 (с фото). Верно?»
  09:32:51  ответ механика ДОСЛОВНО «36982» (поправка на 2000 км вниз)
            КОРЕНЬ 2 → «ТО фаза2 разбор: status=ждёт_факт works=[] done=['gear'] odo=36982
                        completed=False text='36982'»
            → «ТО фаза2 → подтверждение Пыму: NMAX 155 GREEN-B 4957 done=['gear'] odo=36982»
            handle_mileage_confirm НЕ отработал ВООБЩЕ: pending пробега остался висеть, сторож
            убывания/аудит-след/откат записанного не включились.

ЧТО ПРОВЕРЯЕМ (A–H):
  A. корень 1, ветка ИНФО-работ: сырой OCR 38982 не уходит в «события» ни одной строкой;
  B. корень 1, ветка ОБЫЧНОГО события: гейт 06c1ab2 не открылся обратно;
  C. работы не потеряны — остались в буфере до подтверждения (не тихая потеря);
  D. корень 2: пока висит вопрос о пробеге, голое число НЕ перехватывает handle_service_result;
  E. корень 2, граница: заявка 'ждёт_подтверждения' + голое число доверенного — путь не тронут;
  F. вся цепь 1→2→3: в «события» ложится ТОЛЬКО подтверждённое 36982, ни одной строки с 38982;
  G. страховка-откат: строка, всё же записанная сырым числом, удаляется по ТОЧНОМУ msg_id
     и переписывается верным числом;
  H. откат fail-safe: то же число / чужой ключ / нет журнала → ноль удалений.

Сеть/LLM/_send замоканы; ни одной живой таблицы тест не касается.
"""
import os, sys, json, asyncio, datetime
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
import splinter as S

CHAT = -1002751134848
TOPIC = 79
BIKE = "NMAX 155 GREEN-B 4957"
PLATE = "4957"
OCR_KM = "38982"     # сырой OCR с фото 09:32:14 — человеком НЕ подтверждён
REAL_KM = "36982"    # поправка механика 09:32:51, дословно «36982»

TEXT_WORKS = ("На этом мотоцикле заменили моторное масло, масло в редукторе "
              "и передние и задние")
PARSE_WORKS = {"type": "event", "event_type": "repair", "mileage": None,
               "works": ["замена моторного масла", "замена масла в редукторе",
                         "замена передних тормозных колодок",
                         "замена задних тормозных колодок"]}
PARSE_EMPTY = {"type": None, "event_type": None, "mileage": None, "works": []}
VIS_ODO = {"mileage": OCR_KM, "mileage_confidence": "high", "fuel": "full",
           "damage": None, "dirt": False, "tire": None}


class U:
    def __init__(s, uname="extthiwxer", uid=111): s.username = uname; s.id = uid; s.is_bot = False


class Msg:
    def __init__(s, text=None, photo=False, mid=10853, uname="extthiwxer"):
        s.text = text; s.caption = None; s.photo = ([object()] if photo else None)
        s.chat_id = CHAT; s.message_thread_id = TOPIC
        s.date = datetime.datetime(2026, 7, 29, 9, 32, tzinfo=datetime.timezone.utc)
        s.message_id = mid; s.from_user = U(uname); s.reply_to_message = None


class Ctx:
    class B: username = "turbobaby_manager_bot"
    bot = B()


class FakeClaude:
    """quick() отвечает ПО ТЕКСТУ — ровно как живой разбор 29.07 (см. шапку)."""
    def __init__(s, vis=None): s._vis = vis or {}

    def quick(s, system, text, max_tokens=300, **kw):
        if system == getattr(S, "TRANSLATE_RU_TH", "\x00"): return "ครับ"
        if system == getattr(S, "_WORK_TH_SYSTEM", "\x00"): return ""
        t = str(text or "").strip()
        if t == REAL_KM: return json.dumps(PARSE_EMPTY)      # «36982» → works=[] (живой лог)
        if "заменили" in t: return json.dumps(PARSE_WORKS)
        return json.dumps(PARSE_EMPTY)

    def vision(s, *a, **k): return json.dumps(s._vis)


class FakeBridge:
    """Стейтфул то_заявки (один слот) + журнал «события». В Лист1/CRM не ходит."""
    def __init__(s, sp=None):
        s.sp = sp; s.closed = False; s.pend = []; s.events = []; s.deleted = []
        s.col_writes = []          # попытки боевой записи Лист1 — тест их ловит, но НЕ пишет

    def _call(s, *a, **k): return {"ok": False}

    def find_bike(s, q):
        return {"name": BIKE, "mileage": "36900", "status": "", "oil_last_km": 30800}

    def service_pending_get(s, chat_id, topic_id, bike):
        if s.sp and not s.closed:
            return {"ok": True, "item": dict(s.sp)}
        return {"ok": False, "error": "not_found"}

    def service_pending_upsert(s, **kw):
        if s.sp is None:
            s.sp = {"declared": "", "done": "", "status": "заявлено", "odometer": ""}
        for k, v in kw.items():
            if v not in (None, ""): s.sp[k] = v
        s.pend.append(kw); return {"ok": True, "status": s.sp.get("status")}

    def service_pending_list(s, **kw): return {"ok": True, "items": []}
    def service_pending_close(s, **kw): s.closed = True; return {"ok": True}
    def service_list(s, *a, **k): return {"items": []}
    def read_events(s, *a, **k): return {"ok": True, "items": []}
    def service_upsert(s, **k): return {"ok": True, "next_km": 40000, "status": "ok", "km_left": 100}
    def closing_upsert(s, **k): return {"ok": True}
    def state_set(s, **k): return {"ok": True}
    def important_list(s, **k): return {"ok": True, "items": []}

    def set_fleet_service(s, **k):
        # Лист1 — живая таблица. Фикстура ТОЛЬКО фиксирует попытку и отказывает.
        s.col_writes.append(k); return {"ok": False, "error": "fixture_no_write"}

    def set_fleet_oil(s, **k):
        s.col_writes.append(k); return {"ok": False, "error": "fixture_no_write"}

    def add_event(s, **k):
        s.events.append(k); return {"ok": True, "saved": True}

    def delete_event(s, msg_id="", group="", max=50):
        hits = [e for e in s.events if str(e.get("msg_id")) == str(msg_id)]
        if not msg_id:
            return {"ok": False, "error": "no_key"}
        s.events = [e for e in s.events if str(e.get("msg_id")) != str(msg_id)]
        s.deleted.append(msg_id)
        return {"ok": True, "deleted": len(hits),
                "rows": [{"msg_id": str(e.get("msg_id")), "notes": str(e.get("notes", ""))} for e in hits]}


SENDS = []


async def rec_send(context, *, chat_id, text, message_thread_id=None, **k):
    SENDS.append(text)

    class _M: message_id = 1
    return _M()


async def rec_dl(pm): return b"x"


S._send = rec_send
S._send_retry = rec_send
S._download_photo = rec_dl
S.set_topic_bike(CHAT, TOPIC, BIKE)


def reset():
    SENDS.clear(); S._SVC_TOKENS.clear(); S._AWAITING_REPLY.clear()
    S._RECENT_PHOTOS.clear(); S._PENDING_WORKS.clear(); S._ODOMETER_ASK_TS.clear()
    S._SP_ASK_TS.clear(); S._SP_LAST_SENT.clear(); S._CARD_LAST.clear()
    S._PENDING_MILEAGE.clear(); S._SOFT_ODO_PENDING.clear(); S._PENDING_CORRECTION.clear()
    S._LAST_RECORDED_KM.clear(); S._ODO_DROP_CONSEC.clear(); S._SVC_SUMMARY.clear()
    getattr(S, "_KM_EVENTS_WRITTEN", {}).clear()


def run(c): return asyncio.run(c)


def km_rows(bridge, km):
    """Строки «события», в которых фигурирует km — в поле mileage ИЛИ в тексте notes/msg_id.
    Именно так число попадает в историю байка (notes = «<работа> — <км> км»)."""
    out = []
    for e in bridge.events:
        if str(e.get("event_type")) == "odo_audit":
            continue                       # аудит-след убывания — служебный, он и должен нести числа
        blob = f"{e.get('mileage','')}|{e.get('notes','')}|{e.get('msg_id','')}"
        if str(km) in blob:
            out.append(e)
    return out


# ── шаги живой последовательности ───────────────────────────────────────────────

def step1_works_text(bridge, claude):
    """09:24:39 — механик перечислил 4 работы текстом, пробега в сообщении НЕТ."""
    run(S._handle_servicing(Msg(TEXT_WORKS, mid=10853), Ctx(), bridge, claude))


def step2_photo_odo(bridge, claude):
    """09:32:07 — фото приборки, vision отдал 38982 (high). Человек ещё НИЧЕГО не подтвердил."""
    m = Msg(None, photo=True, mid=10855)
    run(S._handle_servicing(m, Ctx(), bridge, claude, photo_msgs=[m]))


def route_bare_number(bridge, claude, text=REAL_KM, uname="extthiwxer"):
    """ЗЕРКАЛО РОУТЕРА bot.py (handle_text, servicing-ветка) — порядок дословно как в проде:
        0) splinter.handle_service_result        (bot.py:824)
        1) pending_correction_for → handle_correction_confirm  (bot.py:828)
        2) pending_mileage_for   → handle_mileage_confirm      (bot.py:832)
    Возвращает (кто перехватил, результат) — чтобы видеть, какая ветка отработала."""
    msg = Msg(text, mid=10857, uname=uname)

    async def _go():
        if await S.handle_service_result(msg, Ctx(), bridge, claude, msg.text):
            return "service_result"
        if S.pending_correction_for(CHAT, TOPIC):
            if await S.handle_correction_confirm(msg, Ctx(), bridge, msg.text):
                return "correction"
        if S.pending_mileage_for(CHAT, TOPIC):
            if await S.handle_mileage_confirm(msg, Ctx(), bridge, msg.text):
                return "mileage_confirm"
        return "brain"

    return run(_go())


# ── A. КОРЕНЬ 1: ветка инфо-работ не пишет сырой OCR ───────────────────────────

def test_a_root1_info_works_do_not_carry_raw_ocr():
    reset(); b = FakeBridge(); c = FakeClaude(VIS_ODO)
    step1_works_text(b, c)
    assert S._PENDING_WORKS.get((CHAT, TOPIC)), "шаг 1: инфо-работы должны лечь в буфер (живой лог 09:24:47)"
    step2_photo_odo(b, c)
    bad = km_rows(b, OCR_KM)
    assert not bad, (
        f"КОРЕНЬ 1: неподтверждённый OCR {OCR_KM} попал в «события» {len(bad)} строк(ами): "
        + "; ".join(f"{e.get('msg_id')} notes={e.get('notes')!r} mileage={e.get('mileage')!r}" for e in bad))


# ── B. КОРЕНЬ 1: ветка обычного события (гейт 06c1ab2) не открылась обратно ────

def test_b_root1_plain_event_branch_still_gated():
    reset(); b = FakeBridge(); c = FakeClaude(VIS_ODO)
    step2_photo_odo(b, c)                     # фото БЕЗ инфо-работ → ветка обычного события
    plain = [e for e in b.events if str(e.get("event_type")) not in ("odo_audit",)]
    assert plain, "обычное событие по фото должно записаться (молчать нельзя)"
    for e in plain:
        assert str(e.get("mileage", "")) != OCR_KM, f"гейт 06c1ab2 открылся обратно: {e}"


# ── C. Работы НЕ потеряны: до подтверждения ждут в буфере ──────────────────────

def test_c_works_wait_in_buffer_not_lost():
    reset(); b = FakeBridge(); c = FakeClaude(VIS_ODO)
    step1_works_text(b, c)
    step2_photo_odo(b, c)
    pend = S._PENDING_WORKS.get((CHAT, TOPIC)) or {}
    assert len(pend.get("works") or []) == 2, (
        f"обе колодки должны ЖДАТЬ подтверждённого пробега, а не пропасть: {pend}")


# ── D. КОРЕНЬ 2: голое число при висящем вопросе о пробеге ─────────────────────

def test_d_root2_bare_number_goes_to_mileage_confirm():
    reset(); b = FakeBridge(); c = FakeClaude(VIS_ODO)
    step1_works_text(b, c); step2_photo_odo(b, c)
    assert S.pending_mileage_for(CHAT, TOPIC), "шаг 2 обязан оставить вопрос о пробеге"
    assert str(b.sp.get("status")) == "ждёт_факт", f"живой статус заявки на 09:32:51: {b.sp}"
    who = route_bare_number(b, c)
    assert who == "mileage_confirm", (
        f"КОРЕНЬ 2: голое «{REAL_KM}» при висящем вопросе о пробеге ушло в «{who}» "
        f"(в проде — в handle_service_result, ветка подтверждения не отработала вовсе)")
    assert not S.pending_mileage_for(CHAT, TOPIC), "после ответа вопрос о пробеге должен быть закрыт"


# ── E. Граница: заявка 'ждёт_подтверждения' + число доверенного — путь не тронут ─

def test_e_trusted_number_on_waiting_confirm_still_writes():
    reset(); b = FakeBridge(sp={"declared": "gear", "done": "gear",
                                "status": "ждёт_подтверждения", "odometer": OCR_KM})
    c = FakeClaude(VIS_ODO)
    S._PENDING_MILEAGE[(CHAT, TOPIC)] = (OCR_KM, BIKE, None, False)   # вопрос висит одновременно
    who = route_bare_number(b, c, text=REAL_KM, uname="Pleummmm")
    assert who == "service_result", (
        f"голое число ДОВЕРЕННОГО по заявке 'ждёт_подтверждения' = санкция на запись, "
        f"её трогать нельзя — перехватил «{who}»")
    assert any(str(w.get("km")) == REAL_KM for w in b.col_writes), (
        f"ветка санкции обязана дойти до записи регламента (фикстура её отклоняет): {b.col_writes}")


# ── F. Вся цепь: в записи только подтверждённое число ─────────────────────────

def test_f_full_chain_records_only_confirmed_km():
    reset(); b = FakeBridge(); c = FakeClaude(VIS_ODO)
    step1_works_text(b, c)
    step2_photo_odo(b, c)
    route_bare_number(b, c)
    bad = km_rows(b, OCR_KM)
    assert not bad, f"после поправки механика строк с {OCR_KM} быть не должно: {bad}"
    good = km_rows(b, REAL_KM)
    notes = " | ".join(str(e.get("notes", "")) for e in good)
    assert "колодок" in notes, (
        f"инфо-работы обязаны лечь в историю с ПОДТВЕРЖДЁННЫМ {REAL_KM} (иначе тихая потеря работ): "
        f"{[e.get('notes') for e in b.events]}")
    assert str(b.sp.get("odometer")) == REAL_KM, f"одометр заявки = поправка механика: {b.sp}"


# ── G. Страховка-откат: если строка всё же проскочила сырым числом ─────────────

def test_g_rollback_removes_leaked_row_and_rewrites():
    reset(); b = FakeBridge(); c = FakeClaude(VIS_ODO)
    step1_works_text(b, c)
    # эмулируем «проскочило»: пишем инфо-работы сырым OCR ровно так, как это делал прод
    S._write_info_works(b, "обслуживание", TOPIC, BIKE,
                        ["замена передних тормозных колодок", "замена задних тормозных колодок"],
                        OCR_KM, f"{CHAT}:10855", "2026-07-29", chat_id=CHAT)
    assert km_rows(b, OCR_KM), "подготовка: строка с сырым числом должна быть записана"
    step2_photo_odo(b, c)
    route_bare_number(b, c)
    assert b.deleted, "откат обязан удалить строку по ТОЧНОМУ msg_id"
    assert all(str(m).startswith(("info:", f"{CHAT}:")) for m in b.deleted), (
        f"откат удаляет ТОЛЬКО свои ключи: {b.deleted}")
    assert not km_rows(b, OCR_KM), f"строка с {OCR_KM} должна исчезнуть: {km_rows(b, OCR_KM)}"
    assert km_rows(b, REAL_KM), "после отката работы переписываются верным числом"


# ── H. Откат fail-safe ────────────────────────────────────────────────────────

def test_h_rollback_is_noop_without_journal_or_on_same_km():
    reset(); b = FakeBridge()
    r = S._rollback_km_events(b, CHAT, TOPIC, wrong_km=OCR_KM, right_km=REAL_KM)
    assert r.get("deleted") == 0 and b.deleted == [], f"нет журнала → ноль действий: {r}"
    S._write_info_works(b, "обслуживание", TOPIC, BIKE, ["замена передних тормозных колодок"],
                        REAL_KM, f"{CHAT}:10855", "2026-07-29", chat_id=CHAT)
    r = S._rollback_km_events(b, CHAT, TOPIC, wrong_km=REAL_KM, right_km=REAL_KM)
    assert r.get("deleted") == 0 and b.deleted == [], f"то же число → ноль действий: {r}"
    r = S._rollback_km_events(b, CHAT, TOPIC, wrong_km=OCR_KM, right_km="37000")
    assert r.get("deleted") == 0 and b.deleted == [], (
        f"журнал про другое число → не трогаем чужие строки: {r}")


# ── I. Зеркало роутера честное: в bot.py порядок остался прежним ───────────────

def test_i_router_order_in_bot_py_unchanged():
    """Фикс живёт в splinter, а не в перестановке роутера. Если порядок в bot.py когда-нибудь
    поменяют — зеркало route_bare_number станет враньём, поэтому проверяем исходник."""
    src = open("/root/turbobaby-manager-bot/bot.py", encoding="utf-8").read()
    i_sr = src.index("splinter.handle_service_result(")
    i_mc = src.index("splinter.handle_mileage_confirm(")
    assert i_sr < i_mc, "зеркало роутера в тесте рассчитано на порядок bot.py: service_result → mileage_confirm"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    bad = 0
    for fn in fns:
        try:
            reset(); fn(); print(f"  ✓ {fn.__name__}")
        except AssertionError as e:
            bad += 1; print(f"  ✗ {fn.__name__}: {e}")
        except Exception as e:
            bad += 1; print(f"  ✗ {fn.__name__}: {type(e).__name__}: {e}")
    print(f"{len(fns) - bad}/{len(fns)} — путь подтверждения одометра (корни 1 и 2)")
    sys.exit(1 if bad else 0)
