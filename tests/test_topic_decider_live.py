"""Решатель темы обслуживания В БОЮ (01.10.2026, задание Штаба 0099-76p, SPLLIVEMODE0110).

Повод — слово владельца 01.10 19:36: тень не включать, Splinter сразу в бой, учить с тайцами.
Флаг `TOPIC_DECIDER_LIVE`: выкл. → путь равен 05efc4b; вкл. → сообщение темы не к Splinter решается до
перехватов, решение исполняется через ПРЕЖНИЕ двери, перехваты на нём молчат.

  + L1 доверенный пробег (Пым) записан ровно раз (`_odo_confirmed`), перехваты и мозг молчат
  + L2 пробег сотрудника → кнопка Пыма (вопрос L), `_odo_confirmed` не зван; работа ТО → ТО-заявка
  + L3 фото → вопрос реплаем → реплай Пыма → одна запись (место вызова фото — после разбора)
  + L4 поправка реплаем → пауза → одно сообщение в «Агенты» → пережила перезапуск → «Продолжить» → снята;
       отклонённая кнопка решателя → пауза
  − L5 флаг выключен → трасса равна коду 05efc4b (отдельные процессы; база — `TOPIC_LIVE_BASE_SRC`, если дана)
  − L6 сбой модели / не JSON / таймаут → прежний путь, одно действие, событие с причиной
  − L7 убывание и потолок → зов Пыма, не запись
  − L8 второй вопрос того же вида → ничего
  − L9 зов дважды за окно → один
  − L10 на паузе решатель не действует (модель не звана)

Чат, бот и сообщения выдуманные (−1009990001234); Telegram, мост и модель — заглушки; состояние —
во временном каталоге. Тексты — выдуманные фразы, не речь людей.
"""
import os, sys, json, time, asyncio, tempfile, subprocess, contextlib, ast
from unittest.mock import AsyncMock, MagicMock, patch

_TMP = tempfile.gettempdir()
os.environ.setdefault("DECIDER_LIVE_STATE", os.path.join(_TMP, f"dlive_state_{os.getpid()}.json"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_topic_decider as H    # noqa: E402  (стенд: заглушки, бот, чат, сообщения)

bot, S, Msg, Ref, J = H.bot, H.S, H.Msg, H.Ref, H.J
CHAT, BIKE, PYM, MECH = H.CHAT, H.BIKE, H.PYM, H.MECH
LIVE = "TOPIC_DECIDER_LIVE"
INTERCEPTS = ("expire_stale_mileage_question", "handle_service_result", "handle_mileage_confirm",
              "handle_oil_backdated_service", "handle_mileage_correction", "handle_post_close_ack", "handle")
_T = [300]


def topic():
    _T[0] += 1
    S.set_topic_bike(CHAT, _T[0], BIKE)
    return _T[0]


@contextlib.contextmanager
def live(on=True):
    old = os.environ.get(LIVE)
    os.environ[LIVE] = "1" if on else "0"
    try:
        yield
    finally:
        if old is None:
            os.environ.pop(LIVE, None)
        else:
            os.environ[LIVE] = old


def through(msg, model, *, svc_result=False, on=True):
    """Сообщение через настоящий `bot.handle_text`: перехваты и двери — шпионы, всё прочее настоящее."""
    rec = {"notes": [], "icpt": {}, "odo": MagicMock(), "sp": AsyncMock(),
           "ask": AsyncMock(side_effect=S._ask_mileage_confirm), "r0": len(H.TRACE["replies"]),
           "s0": len(H.TRACE["sent"])}

    async def cap_reply(m, context, context_note="", **k):
        rec["notes"].append(context_note)

    async def go():
        with contextlib.ExitStack() as st:
            st.enter_context(patch.object(bot, "manager_reply", cap_reply))
            st.enter_context(patch.object(S, "ensure_info_pin", new_callable=AsyncMock))
            for n in INTERCEPTS:
                rv = svc_result if n == "handle_service_result" else False
                rec["icpt"][n] = st.enter_context(patch.object(S, n, AsyncMock(return_value=rv)))
            st.enter_context(patch.object(S, "_odo_confirmed", rec["odo"]))
            st.enter_context(patch.object(S, "sp_confirm_from_brain", rec["sp"]))
            st.enter_context(patch.object(S, "_ask_mileage_confirm", rec["ask"]))
            st.enter_context(patch.object(bot, "claude", model))
            st.enter_context(patch.object(bot, "bridge", H.FakeBridge()))
            await bot.handle_text(H.Upd(msg), H.Ctx())
    with live(on):
        H.run(go())
    rec["icpt_calls"] = sum(m.await_count for m in rec["icpt"].values())
    rec["replies"] = H.TRACE["replies"][rec["r0"]:]
    rec["sent"] = H.TRACE["sent"][rec["s0"]:]
    return rec


def htopic(t):
    """Служебное «тема создана» от ЧЕЛОВЕКА: сообщение Пыма без реплая — не обращение к боту.
    (Стенд 0094 создаёт темы от имени бота, и тогда любое сообщение Пыма — «реплай на бота».)"""
    r = Ref(t, topic_created=True)
    r.from_user = H.U("topic_creator_fixture", 4242)
    return r


def write_km(m):
    return lambda u: J(действие="записать", что="пробег", км=m, источник=H.mid_in(u))


def last_live_event(t, mid):
    evs = [e for e in S._tfeed.read(CHAT, t, days=30, limit=0, shadow=True)
           if e.get("kind") == "decision" and e.get("live") and e.get("on") == mid]
    return evs[-1] if evs else {}


def recorded(t, km):
    S.feed_record(CHAT, t, "пробег подтверждён", km=str(km), source="fixture", bike=BIKE)


# ── + L1 ─────────────────────────────────────────────────────────────────────────

def test_l1_trusted_mileage_recorded_once_intercepts_silent():
    t = topic()
    m = Msg("40500", uname=PYM, topic=t, reply_to=htopic(t))
    model = H.Model(write_km(40500))
    r = through(m, model)
    assert len(model.calls) == 1 and model.calls[0]["tag"] == "decider_live", f"модель: {model.calls}"
    assert r["odo"].call_count == 1, f"запись пробега {r['odo'].call_count} ≠ 1"
    a = r["odo"].call_args
    assert a.args[4] == 40500 and a.args[1] == CHAT and a.args[2] == t, f"дверь: {a}"
    assert r["icpt_calls"] == 0 and not r["notes"], f"перехваты/мозг не молчат: {r['icpt_calls']}, {r['notes']}"
    assert not r["replies"] and r["ask"].await_count == 0 and r["sp"].await_count == 0
    ev = last_live_event(t, m.message_id)
    assert ev.get("door") == S._tdec.DOOR_ODO and ev["final"]["действие"] == "записать", f"событие: {ev}"
    # контроль: обращение к Splinter (реплай Пыма на бота) — прежний путь мозга, решатель не зван
    m2 = Msg("сколько км?", uname=PYM, topic=t, reply_to=Ref(5555))
    model2 = H.Model(write_km(1))
    r2 = through(m2, model2)
    assert not model2.calls and len(r2["notes"]) == 1 and r2["odo"].call_count == 0, "обращение ушло не в мозг"


# ── + L2 ─────────────────────────────────────────────────────────────────────────

def test_l2_staff_mileage_goes_via_pym_button():
    t = topic()
    m = Msg("41000", uname=MECH, topic=t)
    r = through(m, H.Model(write_km(41000)))
    assert r["odo"].call_count == 0, "число сотрудника записано мимо кнопки Пыма"
    assert r["ask"].await_count == 1 and str(r["ask"].await_args.args[4]) == "41000", f"кнопка Пыма: {r['ask'].await_args}"
    q = (S._MILEAGE_Q.get(S._mileage_q_key(CHAT, t)) or {}).get("msg_id")
    assert q is not None and q in S._dlive_mids(CHAT, t), "вопрос L двери решателя не помечен как его сообщение"
    assert r["icpt_calls"] == 0, "перехваты не молчат"
    assert last_live_event(t, m.message_id).get("rule") == "доверие"
    # работа ТО — всегда ТО-заявка с кнопкой Пыма, даже от Пыма. Своя тема: вопрос L открыл окно
    # «ждём ответа» (10 мин), и в этой теме сообщение Пыма — обращение к Splinter (прежний путь).
    t = topic()
    w = Msg("поменял масло", uname=PYM, topic=t, reply_to=htopic(t))
    r2 = through(w, H.Model(lambda u: J(действие="записать", что="масло", км=None, источник=H.mid_in(u))))
    assert r2["sp"].await_count == 1 and r2["odo"].call_count == 0, "работа ТО мимо ТО-заявки"


# ── + L3 ─────────────────────────────────────────────────────────────────────────

def test_l3_photo_question_pym_reply_one_record():
    t = topic()
    ph = Msg("", uname=MECH, topic=t, photo=True)
    S.feed_incoming(ph, "photo")
    S.feed_vision(CHAT, t, [ph], {"mileage": "", "mileage_confidence": "low", "kind": "dashboard"}, 1)
    model = H.Model(lambda u: J(действие="спросить", вопрос="Сколько км на одометре?", ждём_что="пробег",
                                от_кого="Пым"))
    r0 = len(H.TRACE["replies"])
    with live(True):
        took = H.run(S.decider_live(ph, H.Ctx(), H.FakeBridge(), model, kind="photo"))
    assert took is True and len(H.TRACE["replies"]) == r0 + 1, "фото: вопрос реплаем не задан"
    qmid = H._MID[0]
    assert S._dlive_asks(CHAT, t).get("пробег") == qmid, "вопрос решателя не открыт своего вида"
    rep = Msg("41250", uname=PYM, topic=t, reply_to=Ref(qmid))
    r = through(rep, H.Model(write_km(41250)))
    assert r["odo"].call_count == 1 and r["odo"].call_args.args[4] == 41250, f"запись: {r['odo'].call_args_list}"
    assert r["icpt_calls"] == 0 and not r["notes"], "реплай на вопрос решателя ушёл перехватам/мозгу"
    assert "пробег" not in S._dlive_asks(CHAT, t), "вопрос после записи не закрыт"
    src = open(os.path.join(H.REPO, "splinter.py"), encoding="utf-8").read()
    fn = [n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.AsyncFunctionDef) and n.name == "_handle_servicing"][0]
    seg = ast.get_source_segment(src, fn)
    assert 0 <= seg.find("feed_vision(") < seg.find("decider_live("), "фото обязано решаться после разбора"
    bsrc = open(os.path.join(H.REPO, "bot.py"), encoding="utf-8").read()
    assert 0 <= bsrc.find("splinter.decider_live(msg") < bsrc.find("splinter.revive_mileage_question_by_reply("), (
        "решатель текста обязан стоять до перехватов")


# ── + L4 ─────────────────────────────────────────────────────────────────────────

class Q:
    def __init__(s, data, uname=PYM, message=None):
        s.data = data; s.from_user = H.U(uname); s.message = message
        s.answer = AsyncMock(); s.edit_message_reply_markup = AsyncMock()


def test_l4_correction_pause_survives_restart_and_button_resumes():
    t = topic()
    first = Msg("готово", uname=MECH, topic=t)
    through(first, H.Model(lambda u: J(действие="спросить", вопрос="Какой пробег?", ждём_что="пробег", от_кого="Пым")))
    qmid = H._MID[0]
    corr = Msg("не тот байк", uname=PYM, topic=t, reply_to=Ref(qmid))
    r = through(corr, H.Model(lambda u: J(действие="ничего", почему="поправка", поправка=True)))
    assert S.decider_paused(CHAT, t), "поправка реплаем не поставила паузу"
    ag = [s for s in r["sent"] if str(s[0]).startswith("⏸ Splinter")]
    assert len(ag) == 1, f"сообщений в «Агенты» {len(ag)} ≠ 1"
    assert r["icpt_calls"] >= 1, "на поправке обязан сработать прежний путь"
    corr2 = Msg("опять не то", uname=PYM, topic=t, reply_to=Ref(qmid))
    r2 = through(corr2, H.Model(lambda u: J(действие="ничего", почему="x", поправка=True)))
    assert not [s for s in r2["sent"] if str(s[0]).startswith("⏸ Splinter")], "второе сообщение в «Агенты»"
    res = _child("--child-paused", t)
    assert res["paused"] and res["took"] is False and res["model_calls"] == 0, f"после перезапуска: {res}"
    q = Q(f"dlv:go:{CHAT}:{t}")
    H.run(S.handle_decider_button(H.Upd(cq=q), H.Ctx()))
    assert not S.decider_paused(CHAT, t) and q.answer.await_count == 1, "«Продолжить» не сняло паузу"
    with open(os.environ["DECIDER_LIVE_STATE"], encoding="utf-8") as f:
        assert f"{CHAT}:{t}" not in json.load(f)["pauses"], "снятие паузы не легло на диск"
    model = H.Model(write_km(42000))
    through(Msg("42000", uname=PYM, topic=t, reply_to=htopic(t)), model)
    assert len(model.calls) == 1, "после снятия паузы решатель не действует"
    # отклонённая кнопка решателя → пауза (другая тема)
    t2 = topic()
    through(Msg("43000", uname=MECH, topic=t2), H.Model(write_km(43000)))
    lmid = (S._MILEAGE_Q.get(S._mileage_q_key(CHAT, t2)) or {}).get("msg_id")
    btn = H.Sent(lmid); btn.chat_id = CHAT; btn.message_thread_id = t2
    with live(True):
        H.run(S.decider_note_button(H.Upd(cq=Q(f"svc:fix:tok", message=btn)), H.Ctx()))
    assert S.decider_paused(CHAT, t2), "отклонённая кнопка решателя не поставила паузу"
    t3 = topic()   # контроль: та же кнопка на НЕ решателевом сообщении паузы не даёт
    other = H.Sent(999001); other.chat_id = CHAT; other.message_thread_id = t3
    with live(True):
        H.run(S.decider_note_button(H.Upd(cq=Q("svc:fix:tok", message=other)), H.Ctx()))
    assert not S.decider_paused(CHAT, t3), "пауза на чужой кнопке"


def _child_paused(t):
    t = int(t)
    model = H.Model(write_km(1))
    with live(True):
        took = H.run(S.decider_live(Msg("1", uname=PYM, topic=t, reply_to=htopic(t)), H.Ctx(), H.FakeBridge(), model))
    print("CHILD_RESULT " + json.dumps({"paused": bool(S.decider_paused(CHAT, t)), "took": took,
                                        "model_calls": len(model.calls)}))


# ── − L5 ─────────────────────────────────────────────────────────────────────────

def test_l5_flag_off_trace_equals_05efc4b():
    base = os.environ.get("TOPIC_LIVE_BASE_SRC")
    td = tempfile.mkdtemp(prefix="live_trace_", dir=_TMP)

    def env_for(tag, extra):
        e = {"TOPIC_FEED_DIR": os.path.join(td, f"{tag}_feed"), "MILEAGE_Q_STATE": os.path.join(td, f"{tag}_mq.json"),
             "SVC_TOKENS_STATE": os.path.join(td, f"{tag}_svc.json"),
             "WORKS_PERSIST_STATE": os.path.join(td, f"{tag}_works.json"),
             "HINT_DEDUP_STATE": os.path.join(td, f"{tag}_hint.json"),
             "DECIDER_LIVE_STATE": os.path.join(td, f"{tag}_dlive.json"), H.FLAG: "0"}
        e.update(extra)
        return e
    off = H._child("--child-trace", extra_env=env_for("off", {LIVE: "0"}))
    on = H._child("--child-trace", extra_env=env_for("on", {LIVE: "1"}))
    assert off["n_steps"] >= 5 and off["bridge"], f"сценарий пуст: {off}"
    assert not [c for c in off["claude"] if c[1] == "decider_live"], "флаг выключен, а решатель в бою звался"
    assert [c for c in on["claude"] if c[1] == "decider_live"], "положительный контроль: при флаге решатель звался"
    os.environ.pop(LIVE, None)
    assert S._tdec.live_enabled() is False, "по умолчанию бой обязан быть выключен"
    # живой gate.py каталога базы не даёт (SPLLIVEON0110): как N3 тени и C ленты — тогда только выкл/вкл
    if not (base and os.path.exists(os.path.join(base, "bot.py"))):
        print("    · каталог базы не дан — сверка с 05efc4b пропущена (только выкл/вкл)")
        return
    b = H._child("--child-trace", extra_env=env_for("base", {"_TD_CHILD_SRC": base, LIVE: "0"}))
    for k in ("sent", "replies", "notes", "bridge", "claude", "feed", "errors"):
        assert b[k] == off[k], f"флаг выключен: {k} ≠ 05efc4b\nбаза: {b[k]}\nветка: {off[k]}"
    print(f"    · сверено с 05efc4b ({base}): отправок {len(off['sent'])}, ответов {len(off['replies'])}, "
          f"мозг {len(off['notes'])}, мост {len(off['bridge'])}, модель {len(off['claude'])}, лента {len(off['feed'])}")


# ── − L6 ─────────────────────────────────────────────────────────────────────────

def test_l6_model_failure_old_path_one_action():
    def boom(u):
        raise RuntimeError("недоступна")

    def slow(u):
        time.sleep(1.5)
        return J(действие="записать", что="пробег", км=40100, источник=H.mid_in(u))
    os.environ["TOPIC_DECIDER_TIMEOUT_S"] = "0.3"
    try:
        for name, fn, why in (("сбой", boom, "модель не ответила"), ("проза", lambda u: "Думаю, записать 40100", "не JSON"),
                              ("таймаут", slow, "таймаут")):
            t = topic()
            m = Msg("40100", uname=PYM, topic=t, reply_to=htopic(t))
            r = through(m, H.Model(fn), svc_result=True)
            assert r["icpt"]["handle_service_result"].await_count == 1, f"{name}: прежний путь не взял"
            assert r["odo"].call_count == 0 and not r["replies"] and r["ask"].await_count == 0, f"{name}: решатель действовал"
            assert r["icpt_calls"] == 2, f"{name}: действий прежнего пути {r['icpt_calls']} (ждали снятие вопроса + одно)"
            ev = last_live_event(t, m.message_id)
            assert why in str(ev.get("fallback")), f"{name}: нет причины в событии: {ev}"
    finally:
        os.environ.pop("TOPIC_DECIDER_TIMEOUT_S", None)


# ── − L7, L9 ─────────────────────────────────────────────────────────────────────

def test_l7_lower_and_ceiling_call_not_record():
    for km in (39000, 75000):
        t = topic()
        recorded(t, 40000)
        r = through(Msg(str(km), uname=PYM, topic=t, reply_to=htopic(t)), H.Model(write_km(km)))
        assert r["odo"].call_count == 0 and r["ask"].await_count == 0, f"{km}: записано"
        assert len(r["replies"]) == 1 and S.PYM_HANDLE in r["replies"][0], f"{km}: нет зова Пыма: {r['replies']}"
        assert r["icpt_calls"] == 0


def test_l9_call_twice_in_window_once():
    t = topic()
    recorded(t, 40000)
    r1 = through(Msg("39000", uname=PYM, topic=t, reply_to=htopic(t)), H.Model(write_km(39000)))
    r2 = through(Msg("39500", uname=PYM, topic=t, reply_to=htopic(t)), H.Model(write_km(39500)))
    assert len(r1["replies"]) == 1 and len(r2["replies"]) == 0, f"зовов {len(r1['replies']) + len(r2['replies'])} ≠ 1"
    assert r2["icpt_calls"] == 0 and r2["odo"].call_count == 0


# ── − L8 ─────────────────────────────────────────────────────────────────────────

def test_l8_second_question_same_kind_nothing():
    t = topic()
    ask = H.Model(lambda u: J(действие="спросить", вопрос="Какой пробег?", ждём_что="пробег", от_кого="Пым"))
    r1 = through(Msg("готово", uname=MECH, topic=t), ask)
    m2 = Msg("сделал", uname=MECH, topic=t)
    r2 = through(m2, ask)
    assert len(r1["replies"]) == 1 and not r2["replies"], "второй вопрос того же вида задан"
    assert r2["icpt_calls"] == 0, "на «ничего» перехваты не молчат"
    ev = last_live_event(t, m2.message_id)
    assert ev.get("rule") == "второй_вопрос" and ev["final"]["действие"] == "ничего", f"событие: {ev}"


# ── − L10 ────────────────────────────────────────────────────────────────────────

def test_l10_paused_topic_decider_silent():
    t = topic()
    with live(True):
        H.run(S.decider_pause(H.Ctx(), CHAT, t, "фикстура", 1))
    model = H.Model(write_km(40700))
    r = through(Msg("40700", uname=PYM, topic=t, reply_to=htopic(t)), model)
    assert not model.calls and r["odo"].call_count == 0 and r["icpt_calls"] >= 1, "на паузе решатель действовал"


def _child(mode, *args):
    r = subprocess.run([sys.executable, os.path.abspath(__file__), mode, *map(str, args)], env=dict(os.environ),
                       capture_output=True, text=True, timeout=120)
    for line in (r.stdout or "").splitlines():
        if line.startswith("CHILD_RESULT "):
            return json.loads(line[len("CHILD_RESULT "):])
    raise AssertionError(f"дочерний процесс без итога rc={r.returncode}: {(r.stderr or '')[-800:]}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--child-paused":
        _child_paused(sys.argv[2]); sys.exit(0)
    fns = [v for k, v in sorted(globals().items(), key=lambda kv: (len(kv[0]), kv[0]))
           if k.startswith("test_") and callable(v)]
    bad = 0
    for fn in fns:
        try:
            fn(); print(f"  ✓ {fn.__name__}")
        except AssertionError as e:
            bad += 1; print(f"  ✗ {fn.__name__}: {e}")
        except Exception as e:
            bad += 1; print(f"  ✗ {fn.__name__}: {type(e).__name__}: {e}")
    print(f"{len(fns) - bad}/{len(fns)} — решатель темы в бою (FAIL {bad})")
    sys.exit(1 if bad else 0)
