"""Класс-фикс одометра, заход 2: УЧЁТ (корни 3, 4, 5) — NMAX 155 GREEN-B 4957.

ЖИВОЙ ФОРМАТ — снят с прода, не выдуман:
  splinter.log 29.07.2026, чат -1002751134848, тема 79 (строки 176287…176316):
    09:24:39  @extthiwxer «На этом мотоцикле заменили моторное масло, масло в редукторе
              и передние и задние»
              parse works=['замена моторного масла','замена масла в редукторе',
                           'замена передних тормозных колодок','замена задних тормозных колодок']
              → «инфо-работы отложены до пробега: [передние колодки, задние колодки]»
              → «работы группы B без пробега → то_заявка ждёт_факт: ['gear']»   ← МАСЛО ВЫПАЛО
    09:32:16  «инфо-работа в историю: передние колодки — 38982 км … saved=True»
    09:32:18  «инфо-работа в историю: задние колодки — 38982 км … dup=True»     ← ЗАДНИЕ СХЛОПНУТЫ
    09:32:51  механик поправил дословно «36982»
  splinter.log 31.07.2026 (те же чат/тема):
    07:22:42  владелец «Инфо» → карточка держит 38982 поверх живых чисел
    07:29:5x  сообщение владельца СЪЕДЕНО вопросом о пробеге, заданным 46 ч назад
              (в логе нет строки «Splinter [servicing] …» — перехват случился до неё)
    07:31:16  service_upsert current_km=37000 · 07:31:50 set_fleet_oil I16=37000
    Лист1 на момент разбора: I16=37000 (масло), колJ=36982 (редуктор), колH = пробег ПРИ ПОКУПКЕ.

ЧТО ПРОВЕРЯЕМ:
  A. корень 3: моторное масло НЕ выпадает из перечня работ (то_заявка держит oil И gear);
  B. корень 3, граница: «масло в редукторе» без моторного — oil в заявку НЕ лезет (кол.I не трогаем);
  C. корень 3: дедуп различает передние и задние колодки (разные ключи → две строки);
  D. корень 3: карточка тоже не схлопывает переднее/заднее в одну строку;
  E. корень 3, вся цепь: ЧЕТЫРЕ работы 29.07 доезжают раздельно, ни одна не теряется;
  F. корень 3: работа НЕ записалась → это ВИДНО (в сводке и в возврате), а не тихо;
  G. корень 4: карточка Инфо показывает 37000 (свой одометр), а не 38982 из строки «события»;
  H. корень 4: подтверждённое число уходит В ИСТОЧНИК ПРАВДЫ даже когда заявка уводит в ранний return;
  I. корень 4: кол.H (пробег ПРИ ПОКУПКЕ) в текущем пробеге не участвует вовсе;
  J. корень 5: протухший вопрос о пробеге не съедает сообщение человека;
  K. корень 5: про устаревший вопрос сказано вслух («вопрос устарел»), а не молча;
  L. корень 5: СВЕЖИЙ вопрос работает ровно как раньше (заход 1 не сломан).

Сеть/LLM/_send замоканы; ни одной живой таблицы тест не касается (set_fleet_* фикстура отказывает).
"""
import os, sys, json, asyncio, datetime, time
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
# Ручной прогон вне гейта не должен слать пуши/дёргать сеть (гейт ставит это сам подпроцессам).
os.environ.setdefault("PRETOOL_NOPUSH", "1")
os.environ.setdefault("ORCH_TEST_MODE", "1")
import splinter as S

CHAT = -1002751134848
TOPIC = 79
BIKE = "NMAX 155 GREEN-B 4957"
PLATE = "4957"
OCR_KM = "38982"     # сырой OCR 29.07, человеком НЕ подтверждён
REAL_KM = "36982"    # поправка механика 29.07 09:32:51
OWNER_KM = "37000"   # живой одометр 31.07 (I16 + обслуживание)
BUY_KM = "9500"      # кол.H — пробег ПРИ ПОКУПКЕ (в «текущем» участвовать не должен вовсе)

TEXT_WORKS = ("На этом мотоцикле заменили моторное масло, масло в редукторе "
              "и передние и задние")
W_OIL = "замена моторного масла"
W_GEAR = "замена масла в редукторе"
W_PADS_F = "замена передних тормозных колодок"
W_PADS_R = "замена задних тормозных колодок"
PARSE_WORKS = {"type": "event", "event_type": "repair", "mileage": None,
               "works": [W_OIL, W_GEAR, W_PADS_F, W_PADS_R]}
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
    def __init__(s, vis=None): s._vis = vis or {}

    def quick(s, system, text, max_tokens=300, **kw):
        if system == getattr(S, "TRANSLATE_RU_TH", "\x00"): return "ครับ"
        if system == getattr(S, "_WORK_TH_SYSTEM", "\x00"): return ""
        t = str(text or "").strip()
        if "заменили" in t: return json.dumps(PARSE_WORKS)
        return json.dumps(PARSE_EMPTY)

    def vision(s, *a, **k): return json.dumps(s._vis)


class FakeBridge:
    """Стейтфул то_заявки + журнал «события» + «обслуживание». Живые таблицы НЕ трогает."""
    def __init__(s, sp=None, svc_rows=None, events=None, fleet=None, fail_events=False):
        s.sp = sp; s.closed = False; s.pend = []; s.events = list(events or [])
        s.deleted = []; s.col_writes = []; s.upserts = []
        s.svc_rows = list(svc_rows or [])
        s.fleet = dict(fleet or {"name": BIKE, "mileage": BUY_KM, "status": "",
                                 "oil_last_km": 0, "gear_last_km": 0,
                                 "abs_last_km": 0, "airfilter_last_km": 0})
        s.fail_events = fail_events

    def _call(s, *a, **k): return {"ok": False}

    def find_bike(s, q): return dict(s.fleet)

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

    def service_list(s, *a, **k): return {"ok": True, "items": list(s.svc_rows)}

    def read_events(s, *a, **k): return {"ok": True, "items": list(s.events)}

    def service_upsert(s, **k):
        s.upserts.append(dict(k))
        return {"ok": True, "next_km": 40000, "status": "ok", "km_left": 100}

    def closing_upsert(s, **k): return {"ok": True}
    def state_set(s, **k): return {"ok": True}
    def important_list(s, **k): return {"ok": True, "items": []}

    def set_fleet_service(s, **k):
        s.col_writes.append(k); return {"ok": False, "error": "fixture_no_write"}

    def set_fleet_oil(s, **k):
        s.col_writes.append(k); return {"ok": False, "error": "fixture_no_write"}

    def add_event(s, **k):
        if s.fail_events and str(k.get("msg_id", "")).startswith("info:"):
            return {"ok": False, "error": "bridge_down"}
        dup = any(str(e.get("msg_id")) == str(k.get("msg_id")) for e in s.events)
        if dup:
            return {"ok": True, "saved": False, "duplicate": True}
        s.events.append(k); return {"ok": True, "saved": True}

    def delete_event(s, msg_id="", group="", max=50):
        if not msg_id: return {"ok": False, "error": "no_key"}
        hits = [e for e in s.events if str(e.get("msg_id")) == str(msg_id)]
        s.events = [e for e in s.events if str(e.get("msg_id")) != str(msg_id)]
        s.deleted.append(msg_id)
        return {"ok": True, "deleted": len(hits)}


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
    getattr(S, "_SVC_WRITE_DEDUP", {}).clear()


def run(c): return asyncio.run(c)


def info_rows(b):
    return [e for e in b.events if str(e.get("msg_id", "")).startswith("info:")]


def step1_works_text(bridge, claude):
    """09:24:39 — четыре работы текстом, пробега в сообщении НЕТ."""
    run(S._handle_servicing(Msg(TEXT_WORKS, mid=10853), Ctx(), bridge, claude))


def step2_photo_odo(bridge, claude):
    """09:32:07 — фото приборки, vision 38982 (high), человек ещё ничего не подтвердил."""
    m = Msg(None, photo=True, mid=10855)
    run(S._handle_servicing(m, Ctx(), bridge, claude, photo_msgs=[m]))


def answer_km(bridge, claude, text=REAL_KM, uname="extthiwxer"):
    """Зеркало роутера bot.py (servicing-ветка), порядок дословно как в проде."""
    msg = Msg(text, mid=10857, uname=uname)

    async def _go():
        await S.expire_stale_mileage_question(Ctx(), CHAT, TOPIC, msg.text)
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


# ── A. КОРЕНЬ 3: моторное масло не выпадает из перечня работ ───────────────────

def test_a_root3_oil_not_dropped_from_works():
    reset(); b = FakeBridge(); c = FakeClaude(VIS_ODO)
    step1_works_text(b, c)
    declared = S._sp_split((b.sp or {}).get("declared"))
    assert "oil" in declared and "gear" in declared, (
        "КОРЕНЬ 3: фильтр пропускал только gear/abs/airfilter — моторное масло выпадало "
        f"из заявки совсем (живой лог 09:24:47 «то_заявка ждёт_факт: ['gear']»). declared={declared}")


# ── B. КОРЕНЬ 3, ГРАНИЦА: «масло в редукторе» ≠ моторное масло ─────────────────

def test_b_root3_gear_oil_does_not_open_engine_oil():
    reset(); b = FakeBridge()
    c = FakeClaude(VIS_ODO)
    c.quick = lambda system, text, max_tokens=300, **kw: json.dumps(
        {"type": "event", "event_type": "repair", "mileage": None, "works": [W_GEAR]}
        if "редуктор" in str(text) else PARSE_EMPTY)
    run(S._handle_servicing(Msg("поменял масло в редукторе", mid=10860), Ctx(), b, c))
    declared = S._sp_split((b.sp or {}).get("declared"))
    assert "gear" in declared, f"редуктор обязан попасть в заявку: {declared}"
    assert "oil" not in declared, (
        "«масло в редукторе» — это кол.J, а не кол.I: предлагать запись моторного масла нельзя "
        f"(слово «масло» само по себе не основание). declared={declared}")


# ── C. КОРЕНЬ 3: дедуп различает передние и задние колодки ────────────────────

def test_c_root3_front_and_rear_are_different_keys():
    reset(); b = FakeBridge()
    written = S._write_info_works(b, "обслуживание", TOPIC, BIKE, [W_PADS_F, W_PADS_R],
                                  REAL_KM, f"{CHAT}:10855", "2026-07-29", chat_id=CHAT)
    mids = [e["msg_id"] for e in info_rows(b)]
    assert len(set(mids)) == 2, (
        "КОРЕНЬ 3: стем схлопывал переднее и заднее в один ключ — вторая строка приходила "
        f"как duplicate и работа исчезала (живой лог 09:32:18 dup=True). ключи={mids}")
    assert len(info_rows(b)) == 2, f"обе работы обязаны лечь отдельными строками: {mids}"
    assert len(written) == 2, f"обе работы должны считаться записанными: {written}"


# ── D. КОРЕНЬ 3: карточка тоже не схлопывает переднее/заднее ──────────────────

def test_d_root3_card_history_keeps_both_pads():
    items = [{"notes": f"{W_PADS_F} — {REAL_KM} км"}, {"notes": f"{W_PADS_R} — {REAL_KM} км"}]
    out = S._parse_service_items(items, limit=6)
    assert len(out) == 2, (
        f"история карточки схлопывала переднее/заднее в одну строку: {out}")
    out2 = S._parse_service_items([{"notes": f"{W_PADS_F} — {REAL_KM} км"},
                                   {"notes": f"{W_PADS_F} — {REAL_KM} км"}], limit=6)
    assert len(out2) == 1, f"точный повтор той же работы на том же км — по-прежнему один раз: {out2}"


# ── E. КОРЕНЬ 3, ВСЯ ЦЕПЬ: четыре работы доезжают раздельно ───────────────────

def test_e_root3_all_four_works_arrive_separately():
    reset(); b = FakeBridge(); c = FakeClaude(VIS_ODO)
    step1_works_text(b, c)          # 09:24:39 — четыре работы, пробега нет
    step2_photo_odo(b, c)           # 09:32:07 — фото 38982 (не подтверждено)
    answer_km(b, c, REAL_KM)        # 09:32:51 — «36982»
    notes = " | ".join(str(e.get("notes", "")) for e in info_rows(b))
    assert "передн" in notes and "задн" in notes, (
        f"обе пары колодок обязаны быть в истории отдельными строками: {notes!r}")
    declared = S._sp_split((b.sp or {}).get("declared")) + S._sp_split((b.sp or {}).get("done"))
    assert "oil" in declared and "gear" in declared, (
        f"масло и редуктор обязаны дойти до подтверждения Пыму: {declared}")
    assert not [e for e in info_rows(b) if OCR_KM in str(e.get("notes", ""))], (
        "заход 1: сырой OCR в истории остаться не должен")


# ── F. КОРЕНЬ 3: не записалось → ВИДНО ───────────────────────────────────────

def test_f_root3_failed_write_is_visible():
    reset(); b = FakeBridge(fail_events=True)
    written = S._write_info_works(b, "обслуживание", TOPIC, BIKE, [W_PADS_F],
                                  REAL_KM, f"{CHAT}:10855", "2026-07-29", chat_id=CHAT)
    assert written == [], f"Bridge отказал — работу нельзя считать записанной: {written}"
    acc = S._SVC_SUMMARY.get((CHAT, TOPIC)) or {}
    assert acc.get("failed"), "провал записи обязан попасть в сводку (иначе никто не узнает)"
    txt = S.msg_service_summary(BIKE, acc)
    assert "не записалось" in txt.lower() and "колодок" in txt.lower(), (
        f"сводка обязана НАЗВАТЬ незаписанную работу: {txt!r}")
    reset(); b2 = FakeBridge(fail_events=True)
    S._write_info_works(b2, "обслуживание", TOPIC, BIKE, [W_PADS_F], REAL_KM, "x", "", chat_id=CHAT)
    sent = run(S._emit_summary(Ctx(), CHAT, TOPIC, BIKE))
    assert sent is not None and SENDS and "не записалось" in SENDS[-1].lower(), (
        f"сводка с одними провалами всё равно должна уйти в тему: {SENDS!r}")


# ── G. КОРЕНЬ 4: карточка держит свой одометр, а не число из «события» ────────

def _card_bridge():
    """Живое состояние 31.07: обслуживание 37000, Лист1 I16=37000/J=36982, колH=пробег при покупке,
    в «события» висит строка с 38982 (её и держала карточка)."""
    return FakeBridge(
        svc_rows=[{"bike": BIKE, "service_type": "oil", "current_km": OWNER_KM,
                   "updated_at": "2026-07-31T07:31:16Z"},
                  {"bike": BIKE, "service_type": "gear", "current_km": REAL_KM,
                   "updated_at": "2026-07-29T09:40:00Z"}],
        events=[{"notes": f"{W_PADS_F} — {OCR_KM} км", "mileage": OCR_KM, "event_type": "repair"}],
        fleet={"name": BIKE, "mileage": BUY_KM, "status": "",
               "oil_last_km": OWNER_KM, "gear_last_km": REAL_KM,
               "abs_last_km": 0, "airfilter_last_km": 0})


def test_g_root4_card_shows_own_odometer_not_event_km():
    reset()
    card = S._build_bike_card(_card_bridge(), CHAT, TOPIC, BIKE)
    assert f"<b>пробег {OWNER_KM} км</b>" in card, (
        f"карточка обязана показывать свой одометр {OWNER_KM}: {card[:400]!r}")
    assert f"<b>пробег {OCR_KM} км</b>" not in card, (
        f"КОРЕНЬ 4: {OCR_KM} из строки «события» держался поверх живых чисел: {card[:400]!r}")


# ── H. КОРЕНЬ 4: подтверждённое число → в источник правды, а не в летучий накопитель ──

def test_h_root4_confirmed_km_reaches_source_of_truth():
    reset()
    b = FakeBridge(sp={"declared": "oil,gear", "done": "oil,gear",
                       "status": "ждёт_факт", "odometer": ""})
    c = FakeClaude(VIS_ODO)
    S._PENDING_MILEAGE[(CHAT, TOPIC)] = (OCR_KM, BIKE, None, False, time.time())
    who = answer_km(b, c, REAL_KM)
    kms = [str(u.get("current_km")) for u in b.upserts if u.get("current_km") not in (None, "")]
    assert REAL_KM in kms, (
        f"КОРЕНЬ 4: подтверждённое число оседало только в летучем накопителе сводки — "
        f"в «обслуживание» (источник правды) не доходило. перехватил={who} upserts={b.upserts}")


# ── I. КОРЕНЬ 4: пробег ПРИ ПОКУПКЕ (кол.H) в текущем не участвует ────────────

def test_i_root4_purchase_mileage_never_counts():
    reset()
    b = FakeBridge(
        svc_rows=[],
        events=[],
        fleet={"name": BIKE, "mileage": "99999", "status": "",
               "oil_last_km": OWNER_KM, "gear_last_km": REAL_KM,
               "abs_last_km": 0, "airfilter_last_km": 0})
    card = S._build_bike_card(b, CHAT, TOPIC, BIKE)
    assert "<b>пробег 99999 км</b>" not in card, (
        f"кол.H — пробег ПРИ ПОКУПКЕ, текущим он быть не может: {card[:300]!r}")
    assert f"<b>пробег {OWNER_KM} км</b>" in card, (
        f"фоллбэк — одометр на момент замены (I/J/K/L), а не стартовое число: {card[:300]!r}")


# ── J. КОРЕНЬ 5: протухший вопрос не съедает сообщение человека ───────────────

def test_j_root5_stale_question_does_not_eat_the_answer():
    reset(); b = FakeBridge(); c = FakeClaude(VIS_ODO)
    old = time.time() - 46 * 3600            # ровно как 29.07 09:32 → 31.07 07:29
    S._PENDING_MILEAGE[(CHAT, TOPIC)] = (OCR_KM, BIKE, None, False, old)
    assert not S.pending_mileage_for(CHAT, TOPIC), (
        "КОРЕНЬ 5: вопрос 46-часовой давности считался открытым и перехватывал ответ")
    msg = Msg(OWNER_KM, mid=10915, uname="turbophuket1")
    ate = run(S.handle_mileage_confirm(msg, Ctx(), b, msg.text))
    assert ate is False, "протухший вопрос не имеет права засчитать ответ как подтверждение"


# ── K. КОРЕНЬ 5: «вопрос устарел» сказано вслух ───────────────────────────────

def test_k_root5_expiry_is_spoken_not_silent():
    reset()
    S._PENDING_MILEAGE[(CHAT, TOPIC)] = (OCR_KM, BIKE, None, False, time.time() - 46 * 3600)
    fired = run(S.expire_stale_mileage_question(Ctx(), CHAT, TOPIC, OWNER_KM))
    assert fired, "протухший вопрос обязан быть снят"
    assert SENDS and "устарел" in SENDS[-1].lower(), (
        f"человеку надо сказать, что вопрос устарел, а не проглотить ответ: {SENDS!r}")
    assert (CHAT, TOPIC) not in S._PENDING_MILEAGE, "снятый вопрос не должен оставаться в памяти"
    # свежий вопрос не трогаем
    reset()
    S._PENDING_MILEAGE[(CHAT, TOPIC)] = (OCR_KM, BIKE, None, False, time.time())
    fired2 = run(S.expire_stale_mileage_question(Ctx(), CHAT, TOPIC, OWNER_KM))
    assert not fired2 and SENDS == [], f"свежий вопрос трогать нельзя: {SENDS!r}"
    assert (CHAT, TOPIC) in S._PENDING_MILEAGE, "свежий вопрос обязан остаться открытым"


# ── L. КОРЕНЬ 5, граница: свежий вопрос работает как раньше (заход 1 цел) ─────

def test_l_fresh_question_still_works():
    reset(); b = FakeBridge(); c = FakeClaude(VIS_ODO)
    step1_works_text(b, c)
    step2_photo_odo(b, c)
    assert S.pending_mileage_for(CHAT, TOPIC), "шаг 2 обязан оставить ЖИВОЙ вопрос о пробеге"
    who = answer_km(b, c, REAL_KM)
    assert not S.pending_mileage_for(CHAT, TOPIC), "после ответа вопрос закрыт"
    assert any(REAL_KM in str(e.get("notes", "")) for e in info_rows(b)), (
        f"работы обязаны лечь подтверждённым числом (перехватил={who})")


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
    print(f"{len(fns) - bad}/{len(fns)} — учёт одометра (корни 3, 4, 5)")
    sys.exit(1 if bad else 0)
