"""ЧЕК, ПОДШИПНИКИ, СРОК «КМ ИЛИ ПОЛГОДА» (27.09.2026, задание Штаба 0054-74w, слова владельца).

  (1) чек в теме обслуживания: альбом «чек + приборка» (форма 27.09 05:57 UTC) — итог и работы
      прочитаны и названы ОДНИМ сообщением RU+TH, «Верно» не доверенного не пишет, доверенного —
      пишет работы строками «события» БЕЗ суммы; неразборчивый чек — вопрос «не читается»;
  (2) подшипники колёс и руля — обязательный вид с первой проверкой на 20 000 км: байк 20 000+
      без записи — «пора: к замене»;
  (3) срок каждой замены — км или полгода, что раньше: замена 7 месяцев назад при малом пробеге —
      «пора по сроку»; даты нет — «не измерено», а не «просрочено»;
  (4) чистые решения `receipt_read` и `service_due`, их импорты.
Мутанты: ручки `RECEIPT_READ=0` / `SERVICE_DUE=0` (путь 0772f84) валят КАЖДЫЙ случай (1)–(3);
построчные мутанты — `tmp/chastb_2709/mutants.py` захода.

Харнесс — `tests/test_act_gate.py` (живой `splinter.handle`, мост/Telegram/зрение — заглушки).
Фразы и чеки ВЫДУМАНЫ, имён людей нет: доверенные авторы берутся из констант кода.
"""
import ast
import asyncio
import datetime as _dt
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
os.environ["RECEIPT_READ"] = "1"
os.environ["SERVICE_DUE"] = "1"

import test_act_gate as H     # noqa: E402  (харнесс: ставит ручки, временные каталоги, заглушки)
import receipt_read as R      # noqa: E402
import service_due as D       # noqa: E402
import park_verdict           # noqa: E402

S = H.S
ON = {"ACT_GATE": "1", "RECEIPT_READ": "1", "SERVICE_DUE": "1"}
RC_OFF = dict(ON, RECEIPT_READ="0")
SD_OFF = dict(ON, SERVICE_DUE="0")
TODAY = _dt.date(2026, 9, 27)

REC_CLEAR = {"readable": True, "total": 1280, "total_confidence": "high", "currency": "THB",
             "lines": [{"text": "เปลี่ยนน้ำมันเครื่อง", "amount": 350},
                       {"text": "замена передних колодок", "amount": 650},
                       {"text": "ค่าแรง", "amount": 280}],
             "shop": "ร้านทดสอบ", "date": "27.09.2026", "plate": None}


def _album(msgs, claude, env, ctx=None, br=None):
    ctx, br = ctx or H._Ctx(), br or H._Bridge()
    with H._Env(env):
        H._fresh()
        asyncio.run(S.handle(H._Upd(msgs[0]), ctx, br, claude, album_msgs=msgs))
    return ctx, br


def _receipt_texts(ctx):
    return [s.get("text", "") for s in ctx.bot.sent if "🧾" in s.get("text", "")]


def _receipt_rows(br):
    return [kw for n, kw in br.calls if n == "add_event" and str(kw.get("msg_id", "")).startswith("receipt:")]


def _th_line(text):
    return next((ln for ln in text.splitlines() if ln.startswith("🇹🇭")), "")


# ============================================================================================
#  (1) ЧЕК
# ============================================================================================
def _case_album_receipt_and_dashboard(env):
    """27.09 05:57 (форма): альбом без подписи — чек + приборка. Итог и работы названы одним
    сообщением, до «Верно» строк «события» с работами чека нет, сумма не пишется."""
    t = H._topic()
    m1 = H._Msg(photo=True, topic=t, mid=7101, user="mech_test")
    m2 = H._Msg(photo=True, topic=t, mid=7102, user="mech_test")
    vis = [{"kind": "receipt"}, dict(REC_CLEAR),
           {"kind": "dashboard", "mileage": 198864, "mileage_confidence": "high"}]
    ctx, br = _album([m1, m2], H._Claude(vision=vis), env)
    rt = _receipt_texts(ctx)
    ok = (len(rt) == 1 and "1280" in rt[0] and "колодок" in rt[0] and "ค่าแรง" in rt[0]
          and "Верно?" in rt[0] and not _receipt_rows(br)
          and not any("1280" in json.dumps(kw, ensure_ascii=False)
                      for n, kw in br.calls if n in H.WRITES))
    return ok, (rt, ctx, br)


def test_album_receipt_total_and_works_read_one_message():
    ok, (rt, ctx, br) = _case_album_receipt_and_dashboard(ON)
    assert ok, rt
    assert not R._CYR.search(_th_line(rt[0])), f"в тайской половине кириллица: {_th_line(rt[0])}"
    kb = [s for s in ctx.bot.sent if "🧾" in s.get("text", "")][0].get("reply_markup")
    assert kb is not None, "у прочитанного чека нет кнопок «Верно/Не так»"


def test_album_yes_from_untrusted_does_not_write_trusted_writes_without_sum():
    ok, (rt, ctx, br) = _case_album_receipt_and_dashboard(ON)
    assert ok, rt
    n = max(S._RECEIPT_PENDING)
    H._press(f"svc:rcy:{n}", H.MECH, ctx, br, ON)
    assert n in S._RECEIPT_PENDING and not _receipt_rows(br), "«Верно» не доверенного записало"
    H._press(f"svc:rcy:{n}", H.OWNER, ctx, br, ON)
    rows = _receipt_rows(br)
    assert n not in S._RECEIPT_PENDING and len(rows) == 3, rows
    assert all("1280" not in r["notes"] and "650" not in r["notes"] for r in rows), rows
    assert any("колодок" in r["notes"] for r in rows), rows


def test_album_no_button_writes_nothing():
    ok, (rt, ctx, br) = _case_album_receipt_and_dashboard(ON)
    n = max(S._RECEIPT_PENDING)
    H._press(f"svc:rcn:{n}", H.PYM, ctx, br, ON)
    assert n not in S._RECEIPT_PENDING and not _receipt_rows(br)


def _case_unreadable(env):
    vis = [{"kind": "receipt"}, {"readable": False, "total": None, "lines": []}]
    texts, calls, ctx, br = H._run(H._Msg(photo=True, mid=7201), H._Claude(vision=vis), env=env)
    rt = _receipt_texts(ctx)
    ok = (len(rt) == 1 and "не читается" in rt[0]
          and not [s for s in ctx.bot.sent if "🧾" in s.get("text", "") and s.get("reply_markup")])
    return ok, rt


def test_unreadable_receipt_is_a_question():
    ok, rt = _case_unreadable(ON)
    assert ok, rt


def test_mutant_receipt_off_kills_each_receipt_case():
    alive = []
    for name, case in (("альбом чек+приборка", _case_album_receipt_and_dashboard),
                       ("неразборчивый чек", _case_unreadable)):
        ok, _ = case(RC_OFF)
        if ok:
            alive.append(name)
    assert not alive, f"мутант RECEIPT_READ=0 выжил: {alive}"


# ============================================================================================
#  (2)–(3) ПОДШИПНИКИ И СРОК — живой `_build_bike_card` на заглушке моста
# ============================================================================================
class _CardBridge:
    def __init__(self, cur_km, fleet=None, events=None, service_rows=None):
        self.cur_km, self.fleet = cur_km, dict(fleet or {})
        self.events, self.rows = list(events or []), list(service_rows or [])

    def find_bike(self, bike):
        return dict({"name": H.BIKE}, **self.fleet)

    def service_list(self):
        rows = [{"bike": H.BIKE, "service_type": "oil", "current_km": str(self.cur_km),
                 "updated_at": "2026-09-27 09:00:00"}] + self.rows
        return {"ok": True, "items": rows}

    def read_events(self, bike, limit=8):
        return {"ok": True, "items": self.events}

    def service_pending_get(self, *a, **k):
        return {"ok": False, "error": "not_found"}

    def _call(self, *a, **k):
        return {"ok": False}

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return lambda *a, **k: {"ok": False}


def _card(env, br):
    with H._Env(env):
        return S._build_bike_card(br, H._chat_servicing(), 9999, H.BIKE)


def _case_bearings_20k_no_record(env):
    """Байк 20 500 км, записи подшипников нет → «Подшипники … пора: к замене»."""
    txt = _card(env, _CardBridge(20500, fleet={"oil_last_km": "20000"}))
    line = next((ln for ln in txt.splitlines() if "Подшипники" in ln), "")
    return ("пора" in line and "к замене" in line), (line, txt)


def _case_bearings_below_first_check(env):
    txt = _card(env, _CardBridge(19200, fleet={"oil_last_km": "19000"}))
    line = next((ln for ln in txt.splitlines() if "Подшипники" in ln), "")
    return ("800" in line and "первой проверки" in line), (line, txt)


def _case_seven_months_small_mileage(env):
    """Масло заменено 7 месяцев назад на 19 000, сейчас 19 500 (остаток 3 500 км) → к замене по сроку."""
    ev = [{"notes": "замена масла — 19000 км", "msg_date": "2026-02-20 10:00"}]
    txt = _card(env, _CardBridge(19500, fleet={"oil_last_km": "19000"}, events=ev))
    line = next((ln for ln in txt.splitlines() if ln.startswith("Масло")), "")
    return ("пора по сроку" in line and "к замене" in line and "просроч" not in line), (line, txt)


def _case_no_date_unmeasured(env):
    """Даты замены нет → «по времени: не измерено», а НЕ «просрочено»."""
    txt = _card(env, _CardBridge(19500, fleet={"oil_last_km": "19000"}))
    line = next((ln for ln in txt.splitlines() if ln.startswith("Масло")), "")
    return ("не измерено" in line and "просроч" not in line and "✅" in line), (line, txt)


CARD_CASES = [
    ("подшипники 20000+ без записи", _case_bearings_20k_no_record),
    ("подшипники до первой проверки", _case_bearings_below_first_check),
    ("7 месяцев при малом пробеге", _case_seven_months_small_mileage),
    ("нет даты — не измерено", _case_no_date_unmeasured),
]


def test_card_bearings_and_six_months():
    bad = []
    for name, case in CARD_CASES:
        ok, detail = case(ON)
        if not ok:
            bad.append((name, detail[0]))
    assert not bad, bad


def test_mutant_service_due_off_kills_each_card_case():
    alive = []
    for name, case in CARD_CASES:
        ok, detail = case(SD_OFF)
        if ok:
            alive.append((name, detail[0]))
    assert not alive, f"мутант SERVICE_DUE=0 выжил: {alive}"


def test_bearings_row_registered_when_work_written_with_km():
    """Дверь записи: инфо-работа «подшипники колёс» с пробегом → строка «обслуживание» bearings."""
    br = H._Bridge()
    with H._Env(ON):
        S._write_info_works(br, "g", 1, H.BIKE, ["замена подшипников переднего колеса"], "20100", "b")
    ups = [kw for n, kw in br.calls if n == "service_upsert" and kw.get("service_type") == "bearings"]
    assert ups and ups[0]["last_service_km"] == "20100" and ups[0]["interval_km"] == 20000, br.calls
    br2 = H._Bridge()
    with H._Env(ON):
        S._write_info_works(br2, "g", 1, H.BIKE, ["подшипник вариатора"], "20100", "b")
    assert not [1 for n, kw in br2.calls if n == "service_upsert"], "подшипник вариатора — не этот вид"


# ============================================================================================
#  (4) ЧИСТЫЕ РЕШЕНИЯ
# ============================================================================================
def test_receipt_verdict_clear_ask_unreadable():
    v = R.verdict(R.parse(REC_CLEAR), H.BIKE)
    assert v["state"] == R.CLEAR and len(v["works"]) == 3, v
    mism = dict(REC_CLEAR, total=1380)
    v = R.verdict(R.parse(mism), H.BIKE)
    assert v["state"] == R.ASK and any("1380" in w[0] and "1280" in w[0] for w in v["why"]), v
    low = dict(REC_CLEAR, total_confidence="low")
    assert R.verdict(R.parse(low), H.BIKE)["state"] == R.ASK
    alien = dict(REC_CLEAR, plate="9890")
    assert R.verdict(R.parse(alien), "TESTBIKE PHUKET 4243")["state"] == R.ASK
    assert R.verdict(R.parse({"readable": False}), H.BIKE)["state"] == R.UNREADABLE
    assert R.verdict(None, H.BIKE)["state"] == R.UNREADABLE


def test_receipt_works_carry_no_sum_and_th_half_has_no_cyrillic():
    rec = R.parse({"total": 900, "total_confidence": "high", "currency": "THB",
                   "lines": [{"text": "ผ้าเบรก 650 บาท", "amount": 650}, {"text": "ค่าแรง 250", "amount": 250}]})
    assert R.works(rec) == ["ผ้าเบรก", "ค่าแรง"], R.works(rec)
    th, ru = R.message(R.verdict(rec, H.BIKE), H.BIKE)
    assert "900" in ru and "900" in th and not R._CYR.search(th)
    assert "650" not in R.event_note(R.works(rec)[0])


def test_service_due_km_or_six_months():
    v = D.verdict("oil", 19000, 4000, 19500, last_date="2026-02-20", today=TODAY)
    assert v["due"] and v["time"] == D.T_OVER and v["km"] == D.KM_OK, v
    v = D.verdict("oil", 19000, 4000, 19500, last_date="2026-08-01", today=TODAY)
    assert not v["due"] and v["due_date"] == _dt.date(2027, 2, 1), v
    v = D.verdict("oil", 19000, 4000, 19500, last_date=None, today=TODAY)
    assert v["time"] == D.T_UNMEASURED and not v["due"], v
    v = D.verdict("oil", 19000, 4000, 23100, last_date="2026-09-01", today=TODAY)
    assert v["due"] and v["km"] == D.KM_OVER, v
    v = D.verdict("bearings", None, 20000, 20000, today=TODAY)
    assert v["first"] and v["due"], v
    v = D.verdict("bearings", None, 20000, 19999, today=TODAY)
    assert v["first"] and not v["due"] and v["rem"] == 1, v
    v = D.verdict("bearings", 20100, 20000, 30000, today=TODAY)
    assert not v["first"] and v["nxt"] == 40100 and not v["due"], v
    assert D.add_months(_dt.date(2026, 8, 31), 6) == _dt.date(2027, 2, 28)


def test_mand_line_without_today_is_byte_for_byte_old():
    for args in (("oil", 19000, 4000, 19500, park_verdict.SRC_OWN),
                 ("airfilter", 0, 20000, 30000, park_verdict.SRC_OWN),
                 ("abs", 5000, 10000, 16000, park_verdict.SRC_FALLBACK)):
        assert S._mand_line(*args) == S._mand_line_km(*args), args


def test_pure_imports():
    for mod, allowed in (("receipt_read.py", {"re"}), ("service_due.py", {"datetime"})):
        tree = ast.parse(open(os.path.join(ROOT, mod), encoding="utf-8").read())
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                names.add((node.module or "").split(".")[0])
            elif isinstance(node, ast.Call) and getattr(node.func, "id", "") in ("open", "exec", "eval"):
                raise AssertionError(f"{mod}: {node.func.id}")
        assert names == allowed, (mod, names)


if __name__ == "__main__":
    ok = fail = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ok += 1
            except Exception as e:
                fail += 1
                print(f"FAIL {name}: {type(e).__name__}: {str(e)[:600]}")
    print(f"{ok}/{ok + fail}")
    sys.exit(1 if fail else 0)
