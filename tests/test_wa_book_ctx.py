#!/usr/bin/env python3
"""BOOKCTX1610 (отрезок К2): наличие по переписке — приёмка примеси `wa_book_ctx` и флага службы WA_AGENT_BOOK_CTX.

Клиент: «PCX 160 с 10 по 15 октября сколько?» → цена есть; затем «а свободен?» → прежде наличия не было (двух дат в хвосте
нет), теперь пары «модель + срок» из прежних слов КЛИЕНТА той же функцией, что у цены, и по каждой — `free_bikes`.
Каждый случай — с близнецом. Стенд: мир `test_wa_agent_model.World` и мост `test_wa_book_read.Bridge` (живой формат
clients/fleet, к строкам всегда добавлена строка XMAX «Завершена»). T0 = 21.09.2026 21:13 по Пхукету, номер TM.NUM —
всё выдуманное. Сети нет, модели нет, боевых баз нет.

WA_AGENT_SRC=<каталог> подменяет модули (прогон мутантов)."""
import json
import os
import subprocess
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
if os.environ.get("WA_AGENT_SRC"):
    sys.path.insert(0, os.environ["WA_AGENT_SRC"])

try:                                       # spend_ledger импортирует fcntl (только Linux): на ПК без заглушки — подмена цены
    import fcntl  # noqa: F401
except ImportError:
    sys.modules.setdefault("spend_ledger", types.SimpleNamespace(cost_usd=lambda model, i, o: 0.0,
                                                                 meter=lambda *a, **k: None))

PROBE_ARG = "--probe-book-ctx-off"
PROBE_MARK = "BOOKCTX_PROBE "
NEW_MODULE = "wa_book_ctx"


def _probe():
    """Отдельный процесс: служба БЕЗ засчитанного флага (не запрошен; 1 при выключенных бронях; «0») — модуля выпуска в
    процессе нет, класс адаптера прежний, строка старта — только у «не засчитан»."""
    import wa_agent_svc as S
    import test_wa_agent_model as TM
    import test_wa_book_read as TB
    w, br = TM.World(), TB.Bridge([])
    env = {"queue_db": w.qpath, "agent_db": w.dbpath, "mirror_db": "", "tg_token": "", "show_chat": ""}
    model, _ = S.make_model(env, bridge=br, call=lambda s, u: ("", {}), book=True)
    runs = []
    for i, environ in enumerate(({"WA_AGENT_DRAFTS": "1", "WA_AGENT_BOOK_READ": "1"},
                                 {"WA_AGENT_DRAFTS": "1", "WA_AGENT_BOOK_CTX": "1"},
                                 {"WA_AGENT_DRAFTS": "1", "WA_AGENT_BOOK_READ": "1", "WA_AGENT_BOOK_CTX": "0"})):
        lines = []
        S.build(dict(env, agent_db=w.dbpath + str(i)), environ=environ, model=model, line=lines.append)
        runs.append({"ctx": [ln for ln in lines if "WA_AGENT_BOOK_CTX" in ln or ln.startswith("наличие по переписке")],
                     "type": type(model).__name__, "n": len(lines)})
    print(PROBE_MARK + json.dumps({"runs": runs, "mods": sorted(m for m in sys.modules if m == NEW_MODULE)},
                                  ensure_ascii=False))


if __name__ == "__main__" and PROBE_ARG in sys.argv:
    _probe()
    sys.exit(0)

import ast  # noqa: E402
import datetime  # noqa: E402
import hashlib  # noqa: E402
import inspect  # noqa: E402

import test_wa_agent_model as TM  # noqa: E402
import test_wa_book_read as TB  # noqa: E402
import wa_agent_knowledge as K  # noqa: E402
import wa_agent_model as M  # noqa: E402
import wa_agent_svc as S  # noqa: E402
import wa_book_read as B  # noqa: E402
import wa_book_ctx as BC  # noqa: E402

T0, NUM = TM.T0, TM.NUM                        # 21.09.2026 21:13 по Пхукету; выдуманный номер
OTHER = "10000000008"                          # выдуманный чужой номер
DAY = datetime.date(2026, 9, 21)               # «сегодня» и день вопроса по Пхукету
C1 = "PCX 160 с 10 по 15 октября сколько?"
U1 = "PCX 160 на 5 суток — 2000 бат"
Q = "а свободен?"
LIVE = [{"name": n} for n in ("PCX 160CC WHITE PHUKET 3011", "PCX 160CC BLACK PHUKET 3012",
                              "ADV 350CC BLACK PHUKET 5849", "XADV 750CC GREY PHUKET 4290",
                              "NMAX 155CC BLUE PHUKET 6001", "CB 300CC R 9011", "CB 650R RED PHUKET 9012",
                              "XMAX 300CC NEW BLUE PHUKET 4321")]
BASE = "cbe1322"                               # прод 556e744 + FORMID
PINS = {"wa_agent.py": "70695c7dc669f2b4d14ff7c000763b915e6121e8",
        "wa_agent_model.py": "868b0c4b3abd75d6f4fca6b1c7021d0f121db3ce",
        "wa_agent_tools.py": "fb70716d09b8b2812c08d40f2b0d66ff18ead9e3",
        "wa_agent_knowledge.py": "d338a3c23fcfa7f8180a6ed75b38a93e6e4200d3",
        "rental_case.py": "3e3cba2f63461ae6fccf1a7d3f044da0c22cbca0",
        "bridge_client.py": "71d290387c95dc283a477f1c44ab4e4c9bedb665",
        "wa_book_read.py": "7329698d797d5b045692f4a9889e830c081ce78d",
        "wa_agent_tg.py": "4f83f9be2819306775e48612d13f7bffa1d209ae",
        "contract_ask.py": "be132d7a099dbb84edadca636989cb16dd19c607"}
PROD_MAKE_MODEL = ["env", "line", "bridge", "call", "lessons", "book", "cache", "tools", "hints", "cstate"]
L1 = BC.LOG_HEAD + "история не та — ответ родителя"
L3 = BC.LOG_HEAD + "пар нет — ответ родителя"
L4 = BC.LOG_HEAD + "срок в последнем сообщении без полной даты — НЕИЗВЕСТНО, прежний срок не подставлен"
L5 = BC.LOG_HEAD + "модель в последнем сообщении не из парка — НЕИЗВЕСТНО, прежняя модель не подставлена"
W_ON = ("вкл — вопрос о наличии без модели или дат в последнем сообщении клиента: пары «модель + срок» из его прежних "
        "слов (те же, что у цены), не больше 3, дверь цены — не больше раза на пару; отсев — «неизвестно»; бронь не "
        "пишется, клиенту — только по «Отправить»")
W_NO_BOOK = ("не засчитан — флаг 1, но брони (WA_AGENT_BOOK_READ) выключены: наличие по переписке не читается")
W_NO_SNAP = ("не засчитан — флаг 1, но у модели нет снимка броней (WA_AGENT_DRAFTS выкл или адаптер не собран)")
W_NO_MOD = "не засчитан — модуль наличия по переписке не собран (ImportError) — адаптер прежний"
FREE_LINE = ("— PCX 160 (с 10.10 по 15.10): НАЛИЧИЕ (таблица броней, снимок 0 мин назад; свободный юнит сверен дверью "
             "цены): PCX 160, 2026-10-10 — 2026-10-15: свободно 2 из 2.")


# ══ стенд ══════════════════════════════════════════════════════════════════════════════════════════════════════

def world(rows=(), live=False, mixin=True, **kw):
    """Мир со снимком броней (как WA_AGENT_BOOK_READ=1); live — парк живого формата; mixin — примесь надета."""
    w, br = TB.world(rows, **kw)
    if live:
        w.adapter.book = B.Snapshot(lambda: br.clients(filter="all"), lambda: {"ok": True, "data": {"bikes": LIVE}})
    if mixin:
        w.adapter.__class__ = BC.with_book_ctx(type(w.adapter))
    return w, br


def scene(w, q=Q, c1=C1, c1_ts=T0 - 3600, u1=U1, u1_ts=T0 - 3000, q_ts=T0):
    """C1 (клиент) → U1 (мы, эхо) → вопрос Q (клиент) → номер строки Q."""
    if c1:
        w.put(c1_ts, c1)
    if u1:
        w.put(u1_ts, u1, kind="echo")
    return w.put(q_ts, q)


def built(w, rid, now=T0):
    """build адаптера → (system, user, info, строки журнала этого вызова)."""
    n = len(w.lines)
    system, user, info = w.adapter.build(NUM, rid, now=now)
    return system, user, info, w.lines[n:]


def pair(**kw):
    """Мир + сцена с примесью и близнец без примеси → ((s, u, i, журнал), мост, (s0, u0, i0, журнал0), мост0)."""
    rows, live, extra = kw.pop("rows", ()), kw.pop("live", False), kw.pop("bridge", {})
    w, br = world(rows, live=live, **extra)
    w0, br0 = world(rows, live=live, mixin=False, **extra)
    got = built(w, scene(w, **kw))
    base = built(w0, scene(w0, **kw))
    return got, br, base, br0


def ctx_lines(lines):
    return [ln for ln in lines if ln.startswith(BC.LOG_HEAD)]


def reasons(info):
    return [r["reason"] for r in info["code_reasons"]]


def words_of(info):
    return [r["words"] for r in info["code_reasons"]]


# ══ К1–К14: адаптер ═══════════════════════════════════════════════════════════════════════════════════════════

def test_k01_ctx_pair_free_one_door():
    """К1: «а свободен?» после цены PCX 160 10–15 октября → блок по переписке FREE, одна дверь на юнит, одно чтение
    clients; «агент не видит» снят; в журнале одна строка числами — без номера, моделей и дат."""
    (s, user, info, lines), br, (s0, u0, i0, lines0), br0 = pair()
    assert BC.CTX_HEAD + "\n" + FREE_LINE in user, user[-1500:]
    a = info["avail"]
    assert a["source"] == "ctx" and a["outcome"] == B.FREE and a["sieve"] is None and a["dropped"] == 0, a
    assert K.R_AVAILABILITY not in reasons(info), reasons(info)
    assert br.doors == [("PCX 160 1234", "2026-10-10", "2026-10-15")], br.doors
    assert br.client_calls == ["all"], br.client_calls
    assert ctx_lines(lines) == [BC.LOG_HEAD + "пар 1: свободно 1, занято 0, неизвестно 0 (отсев 0); дверь 1; "
                                              "снимок 0 мин"], ctx_lines(lines)
    w_all = [ln for ln in lines]
    for bad in (NUM, "PCX", "2026-10", "10.10", "15.10"):
        assert not [ln for ln in w_all if bad in ln], (bad, [ln for ln in w_all if bad in ln])
    # (а) близнец без примеси: наличия нет, причина «агент не видит», таблица не звана
    assert "НАЛИЧИЕ" not in u0 and K.R_AVAILABILITY in reasons(i0) and br0.client_calls == [], (reasons(i0), u0[-500:])
    assert K.REASON_WORDS[K.R_AVAILABILITY] in words_of(i0)
    assert "source" not in (i0["avail"] or {}) and i0["avail"] is None


def test_k01_avail_keys_and_pairs():
    """§6: ключи словаря наличия — ключи free_bikes + source, sieve, dropped, pairs; пара — model, даты, исход, отсев,
    почему, двери, строка с меткой."""
    (_s, _u, info, _l), _br, _b, _b0 = pair()
    a = info["avail"]
    assert set(a) == {"outcome", "model", "date_start", "date_end", "units", "free", "busy", "unchecked", "age",
                      "door_calls", "why", "line", "source", "sieve", "dropped", "pairs"}, set(a)
    assert (a["model"], a["date_start"], a["date_end"], a["units"], a["free"], a["busy"], a["unchecked"],
            a["door_calls"], a["why"], a["age"]) == ("PCX 160", "2026-10-10", "2026-10-15", 2, 2, 0, 0, 1, "", 0.0), a
    assert len(a["pairs"]) == 1 and set(a["pairs"][0]) == {"model", "date_start", "date_end", "outcome", "sieve", "why",
                                                          "door_calls", "line"}, a["pairs"]
    p = a["pairs"][0]
    assert p["line"] == FREE_LINE + p["line"][len(FREE_LINE):] and p["line"].startswith(FREE_LINE), p
    assert p["outcome"] == B.FREE and p["sieve"] is None and p["door_calls"] == 1 and p["why"] == "", p


def test_k01_parent_answer_untouched():
    """К1 (б): в вопросе модель и обе даты — ответ родителя (FREE): (system, user, info), журнал, clients и двери равны
    близнецу без примеси; у наличия нет ключа source."""
    q = "PCX 160 с 10 по 15 октября свободен?"
    (s, u, i, l), br, (s0, u0, i0, l0), br0 = pair(q=q)
    assert (s, u, i) == (s0, u0, i0) and l == l0, [x for x in l if x not in l0]
    assert br.client_calls == br0.client_calls == ["all"] and br.doors == br0.doors, (br.doors, br0.doors)
    assert i["avail"]["outcome"] == B.FREE and "source" not in i["avail"] and not ctx_lines(l), i["avail"]


def test_k02_new_dates_old_model_busy():
    """К2: «а с 20 по 25 октября свободен?» (оба PCX — бронь внутри 20–25, 10–15 свободно) → BUSY по 20–25, дверей нет."""
    rows = [TB.row("PCX 160 1234", "Бронь", "2026-10-20 10:00", "2026-10-25 10:00"),
            TB.row("PCX 160 5678", "Бронь", "2026-10-21 10:00", "2026-10-24 10:00")]
    (_s, user, info, lines), br, _b, _b0 = pair(rows=rows, q="а с 20 по 25 октября свободен?")
    a = info["avail"]
    assert a["source"] == "ctx" and a["outcome"] == B.BUSY and br.doors == [], (a, br.doors)
    assert "— PCX 160 (с 20.10 по 25.10): НАЛИЧИЕ (таблица броней, снимок 0 мин назад; прочитаны все юниты модели): " \
           "PCX 160, 2026-10-20 — 2026-10-25: заняты все 2." in user, user[-1200:]
    assert br.client_calls == ["all"], br.client_calls        # родитель прочитал снимок — примесь второй раз не читает
    assert ctx_lines(lines) == [BC.LOG_HEAD + "пар 1: свободно 0, занято 1, неизвестно 0 (отсев 0); дверь 0; "
                                              "снимок 0 мин"], ctx_lines(lines)
    # близнец: таблица наоборот (занято 10–15, 20–25 свободно) → FREE, дверь на 20–25, 10.10 нет ни в одной двери
    rows2 = [TB.row("PCX 160 1234", "Бронь", "2026-10-10 10:00", "2026-10-15 10:00"),
             TB.row("PCX 160 5678", "Бронь", "2026-10-11 10:00", "2026-10-14 10:00")]
    (_s, _u, info2, _l), br2, _b, _b0 = pair(rows=rows2, q="а с 20 по 25 октября свободен?")
    assert info2["avail"]["outcome"] == B.FREE, info2["avail"]
    assert br2.doors == [("PCX 160 1234", "2026-10-20", "2026-10-25")], br2.doors
    assert not [d for d in br2.doors if "2026-10-10" in d], br2.doors


def test_k03_loose_term_g1():
    """К3: «а на 20–25 свободен?» — срок без месяца → ровно G1, снимок и дверь не званы, прежний срок не подставлен."""
    (_s, user, info, lines), br, _b, _b0 = pair(q="а на 20–25 свободен?")
    a = info["avail"]
    assert a["line"] == BC.G_TERM_LINE and a["sieve"] == "term_in_tail" and a["outcome"] == B.UNKNOWN, a
    assert (a["model"], a["date_start"], a["date_end"], a["age"], a["dropped"], a["pairs"], a["why"]) == \
        (None, None, None, None, 0, [], BC.W_G_TERM), a
    assert br.client_calls == [] and br.doors == [] and br.fleets == 0, (br.client_calls, br.doors, br.fleets)
    assert "2026-10-10" not in user and BC.G_TERM_LINE in user and BC.CTX_HEAD not in user, user[-900:]
    assert B.W_AVAIL_UNKNOWN in words_of(info) and K.R_AVAILABILITY not in reasons(info), words_of(info)
    assert ctx_lines(lines) == [L4], ctx_lines(lines)
    # близнец: «на 20–25 октября» — полные даты → проверяется пара PCX 160 20–25
    (_s, _u, info2, _l), br2, _b, _b0 = pair(q="а на 20–25 октября свободен?")
    assert info2["avail"]["source"] == "ctx" and br2.doors == [("PCX 160 1234", "2026-10-20", "2026-10-25")], br2.doors


def test_k04_alias_ambiguous():
    """К4: LIVE, «CB с 10 по 15 октября сколько?» → «CB» подходит к CB 300CC и CB 650R: отсев, двери нет; близнец
    «CB 650R …» — проверяется."""
    (_s, user, info, _l), br, _b, _b0 = pair(live=True, c1="CB с 10 по 15 октября сколько?")
    want = ("— «CB» (с 10.10 по 15.10): НАЛИЧИЕ: НЕИЗВЕСТНО — модель не определена: «CB» подходит к моделям парка "
            "CB 300CC / CB 650R. Не говори ни «есть», ни «нет», ни «свободен»; спроси у клиента, какая модель.")
    assert want in user and br.doors == [], (user[-900:], br.doors)
    a = info["avail"]
    assert a["outcome"] == B.UNKNOWN and a["model"] == "CB" and a["pairs"][0]["sieve"] == "alias", a
    assert a["date_start"] is None and a["units"] == 0 and a["door_calls"] == 0, a
    (_s, _u, info2, _l), br2, _b, _b0 = pair(live=True, c1="CB 650R с 10 по 15 октября сколько?")
    assert info2["avail"]["outcome"] in (B.FREE, B.BUSY), info2["avail"]
    assert br2.doors == [("CB 650R RED PHUKET 9012", "2026-10-10", "2026-10-15")], br2.doors


def test_k05_our_words_give_no_pair():
    """К5: только НАШИ слова о модели и датах (U0), «а свободные есть?» → пар нет: выход равен близнецу без примеси,
    журнал — родительский плюс L3, дверей нет, снимок прочитан не больше раза; близнец — те же слова клиента → блок."""
    u0 = "PCX 160 свободен с 10 по 15 октября"
    (s, u, i, l), br, (s0, u0_, i0, l0), br0 = pair(c1=None, u1=u0, q="а свободные есть?")
    assert (s, u, i) == (s0, u0_, i0), "пар нет — ответ родителя"
    assert [x for x in l if not x.startswith(BC.LOG_HEAD)] == l0 and ctx_lines(l) == [L3], (l, l0)
    assert br.doors == [] and len(br.client_calls) <= 1, (br.doors, br.client_calls)
    (_s, u2, i2, _l), br2, _b, _b0 = pair(c1=u0, c1_ts=T0 - 3600, u1="Сейчас уточню.", q="а свободные есть?")
    assert BC.CTX_HEAD in u2 and i2["avail"]["source"] == "ctx", u2[-900:]


def test_k06_past_term():
    """К6: «с 10 по 15 сентября», сказано за 20 суток до вопроса → цена унесла срок на 2027, а он прошёл: S5, двери нет,
    «2027» в запросе нет; близнецы: «с 1 по 5 октября» — проверяется; «с 20 по 25 сентября» за 6 суток — уже начался."""
    c1 = "PCX 160 с 10 по 15 сентября сколько?"
    (_s, user, info, _l), br, _b, _b0 = pair(c1=c1, c1_ts=T0 - 20 * 86400)
    want = ("— PCX 160 (с 10.09 по 15.09): НАЛИЧИЕ: НЕИЗВЕСТНО — срок из переписки уже прошёл или начался. Не говори ни "
            "«есть», ни «нет», ни «свободен»; спроси у клиента новые даты.")
    assert want in user and br.doors == [] and "2027" not in user, (user[-900:], br.doors)
    assert info["avail"]["pairs"][0]["sieve"] == "past" and info["avail"]["outcome"] == B.UNKNOWN
    (_s, _u, info2, _l), br2, _b, _b0 = pair(c1="PCX 160 с 1 по 5 октября сколько?", c1_ts=T0 - 20 * 86400)
    assert info2["avail"]["outcome"] == B.FREE and br2.doors == [("PCX 160 1234", "2026-10-01", "2026-10-05")], br2.doors
    (_s, u3, info3, _l), br3, _b, _b0 = pair(c1="PCX 160 с 20 по 25 сентября сколько?", c1_ts=T0 - 6 * 86400)
    assert info3["avail"]["pairs"][0]["sieve"] == "past" and br3.doors == [], info3["avail"]
    assert "— PCX 160 (с 20.09 по 25.09): НАЛИЧИЕ: НЕИЗВЕСТНО — срок из переписки уже прошёл" in u3, u3[-700:]


def test_k07_no_avail_word_byte_for_byte():
    """К7: «спасибо» — слова наличия нет: выход, журнал, clients и двери равны близнецу; английский близнец — блок."""
    (s, u, i, l), br, (s0, u0, i0, l0), br0 = pair(q="спасибо")
    assert (s, u, i) == (s0, u0, i0) and l == l0 and not ctx_lines(l), [x for x in l if x not in l0]
    assert br.client_calls == br0.client_calls == [] and br.doors == br0.doors == [], (br.client_calls, br.doors)
    (_s, u2, i2, _l), br2, _b, _b0 = pair(c1="PCX 160 from Oct 10 to Oct 15, how much?", q="is it available?")
    assert BC.CTX_HEAD in u2 and i2["avail"]["source"] == "ctx", u2[-900:]
    assert br2.client_calls == ["all"] and len(br2.doors) <= 1, (br2.client_calls, br2.doors)


def test_k08_restart_and_own_history():
    """К8: второй адаптер с примесью на той же очереди и часах — тот же user (состояние — из истории). Чужая история перед
    _book → ответ родителя и L1; своя → блок; _book без _history → L1."""
    w, br = world()
    rid = scene(w)
    _s, user, info, _l = built(w, rid)
    lines2 = []
    ad = M.ModelAdapter(w.qpath, TM.FakeCall(), read_doc=br.read_doc, fleet=br.fleet, door=br.door,
                        archive_db=w.apath, clock=lambda: T0, log=lines2.append)
    ad.book = B.Snapshot(lambda: br.clients(filter="all"), br.fleet)
    ad.__class__ = BC.with_book_ctx(type(ad))
    _s2, user2, info2 = ad.build(NUM, rid, now=T0)
    assert user2 == user and info2["avail"]["line"] == info["avail"]["line"], "после рестарта блок тот же"
    want = M.ModelAdapter._book(w.adapter, NUM, Q, DAY, T0, DAY)
    n = len(w.lines)
    w.adapter._history(OTHER, rid)
    got = w.adapter._book(NUM, Q, DAY, T0, DAY)
    assert got == want and w.lines[n:] == [L1], (got, w.lines[n:])
    w.adapter._history(NUM, rid)
    got = w.adapter._book(NUM, Q, DAY, T0, DAY)
    assert got[0]["source"] == "ctx" and got[0]["outcome"] == B.FREE, got[0]
    assert got[2] == want[2] + " · " + BC.LOG_HEAD + "пар 1: свободно 1, занято 0, неизвестно 0 (отсев 0); дверь 1; " \
                                                      "снимок 0 мин", got[2]
    n = len(w.lines)
    got = w.adapter._book(NUM, Q, DAY, T0, DAY)
    assert got == want and w.lines[n:] == [L1], (got, w.lines[n:])
    # своя история, но хвост другой (ask не тот, что в истории) — ответ родителя
    w.adapter._history(NUM, rid)
    n = len(w.lines)
    assert w.adapter._book(NUM, "а свободен завтра?", DAY, T0, DAY)[0] is None and w.lines[n:] == [L1], w.lines[n:]


def test_k09_model_not_in_fleet_g2():
    """К9: «а Vespa 150 / PCX 150 с 20 по 25 октября свободна?» → ровно G2, дверей нет, L5; близнец «PCX 160 …» —
    ответ родителя, выход равен близнецу без примеси."""
    for q in ("а Vespa 150 с 20 по 25 октября свободна?", "а PCX 150 с 20 по 25 октября свободен?"):
        (_s, user, info, lines), br, _b, _b0 = pair(q=q)
        a = info["avail"]
        assert a["line"] == BC.G_MODEL_LINE and a["sieve"] == "model_in_tail" and a["why"] == BC.W_G_MODEL, (q, a)
        assert a["age"] == 0.0 and a["pairs"] == [] and a["model"] is None and br.doors == [], (q, a, br.doors)
        assert ctx_lines(lines) == [L5] and BC.CTX_HEAD not in user, (q, ctx_lines(lines))
    (s, u, i, l), br, (s0, u0, i0, l0), br0 = pair(q="а PCX 160 с 20 по 25 октября свободен?")
    assert (s, u, i) == (s0, u0, i0) and l == l0 and br.doors == br0.doors, (br.doors, br0.doors)


def test_k10_client_dates_not_minimum():
    """К10: NMAX 155 «с 10 по 12» — цена тянет срок до минимума 5 суток; наличие — даты клиента 10–12. Близнец: NMAX
    только в вопросе, срок называли для PCX → S4 «срок для этой модели клиент не называл», двери для NMAX нет."""
    (_s, user, info, _l), br, _b, _b0 = pair(live=True, c1="NMAX 155 с 10 по 12 октября сколько?")
    assert br.doors == [("NMAX 155CC BLUE PHUKET 6001", "2026-10-10", "2026-10-12")], br.doors
    assert "— NMAX 155CC (с 10.10 по 12.10): НАЛИЧИЕ (" in user, user[-900:]
    (_s, u2, info2, _l), br2, _b, _b0 = pair(live=True, q="а NMAX свободен?")
    p = info2["avail"]["pairs"]
    assert [(x["model"], x["sieve"]) for x in p] == [("NMAX 155CC", "no_term")], p
    assert p[0]["why"] == "срок для этой модели клиент не называл" and p[0]["date_start"] is None, p
    assert not [d for d in br2.doors if "NMAX" in d[0]], br2.doors
    assert "— NMAX 155CC: НАЛИЧИЕ: НЕИЗВЕСТНО — срок для этой модели клиент не называл." in u2, u2[-900:]


def test_k11_pairs_limit():
    """К11: четыре модели в одном сообщении → ровно 3 строки пар, сверх предела 1, дверей ≤ 3; две модели → 2 и ≤ 2."""
    c1 = "PCX 160, XMAX 300, NMAX 155 или ADV 350 с 10 по 15 октября сколько?"
    (_s, user, info, lines), br, _b, _b0 = pair(live=True, c1=c1)
    a = info["avail"]
    block = a["line"].split("\n")
    assert block[0] == BC.CTX_HEAD and len(block) == 4 and len(a["pairs"]) == 3 and a["dropped"] == 1, a["line"]
    assert len(br.doors) <= 3 and "(сверх предела 1)" in ctx_lines(lines)[0], (br.doors, ctx_lines(lines))
    assert ctx_lines(lines)[0].startswith(BC.LOG_HEAD + "пар 3 (сверх предела 1): "), ctx_lines(lines)
    (_s, _u, info2, _l), br2, _b, _b0 = pair(live=True, c1="PCX 160 или NMAX 155 с 10 по 15 октября сколько?")
    assert len(info2["avail"]["pairs"]) == 2 and info2["avail"]["dropped"] == 0 and len(br2.doors) <= 2, info2["avail"]


def test_k12_door_disagrees():
    """К12: дверь цены не подтвердила свободный юнит → строка пары UNKNOWN «таблица и дверь разошлись», причина
    «наличие не проверено»; близнец К1 — FREE."""
    (_s, user, info, _l), br, _b, _b0 = pair(bridge={"available": False})
    a = info["avail"]
    assert a["outcome"] == B.UNKNOWN and "разошлись" in a["why"] and len(br.doors) == 1, a
    assert "— PCX 160 (с 10.10 по 15.10): НАЛИЧИЕ: НЕИЗВЕСТНО — дверь цены не подтвердила свободный юнит — таблица " \
           "и дверь разошлись." in user, user[-900:]
    assert B.W_AVAIL_UNKNOWN in words_of(info) and a["door_calls"] == 1, words_of(info)
    (_s, _u, info2, _l), _br, _b, _b0 = pair()
    assert info2["avail"]["outcome"] == B.FREE


def test_k13_exception_parent_answer():
    """К13: price_pairs бросает RuntimeError → ответ родителя и строка «сбой RuntimeError»; подмена снята — блок."""
    saved = M.price_pairs

    def boom(*a, **k):
        raise RuntimeError("сбой")
    M.price_pairs = boom
    try:
        (s, u, i, l), _br, (s0, u0, i0, _l0), _br0 = pair()
    finally:
        M.price_pairs = saved
    assert (s, u, i) == (s0, u0, i0), "сбой примеси — ответ родителя"
    assert ctx_lines(l) == [BC.LOG_HEAD + "сбой RuntimeError — ответ родителя"], ctx_lines(l)
    (_s, u2, i2, _l), _br, _b, _b0 = pair()
    assert BC.CTX_HEAD in u2 and i2["avail"]["source"] == "ctx"


def test_k13b_snapshot_unread_parent_answer():
    """L2: дверь clients не ответила → снимок не служит: ответ родителя и строка с причиной снимка; дверей нет."""
    w, br = world()
    br.fail = True
    w0, br0 = world(mixin=False)
    br0.fail = True
    s, u, i, l = built(w, scene(w))
    s0, u0, i0, _l0 = built(w0, scene(w0))
    assert (s, u, i) == (s0, u0, i0) and br.doors == [], br.doors
    assert ctx_lines(l) == [BC.LOG_HEAD + "снимок не служит (дверь clients не дала строк) — ответ родителя"], l


def _csa(w, br):
    import wa_agent_cstate as C
    ad = C.ContractStateAdapter(w.qpath, w.call, read_doc=br.read_doc, fleet=br.fleet, door=br.door,
                                archive_db=w.apath, clock=lambda: T0, log=w.lines.append, agent_db=w.dbpath)
    ad.book = B.Snapshot(lambda: br.clients(filter="all"), br.fleet)
    return ad


def test_k14_with_contract_state():
    """К14: вместе с CASESTATE — примесь на ContractStateAdapter: блок договора первым, CTX_HEAD один раз; без примеси —
    тот же блок договора, CTX_HEAD нет."""
    import wa_contract_state as CS
    q = "а свободен? и пришлите договор"
    w, br = world(mixin=False)
    w.adapter = _csa(w, br)
    w.adapter.__class__ = BC.with_book_ctx(type(w.adapter))
    _s, user, info, _l = built(w, scene(w, q=q))
    w0, br0 = world(mixin=False)
    w0.adapter = _csa(w0, br0)
    _s, u0, i0, _l = built(w0, scene(w0, q=q))
    assert user.startswith(CS.HEAD_START) and user.count(BC.CTX_HEAD) == 1, user[:400]
    assert "cstate" in info and info["avail"]["source"] == "ctx", info.get("avail")
    assert u0.startswith(CS.HEAD_START) and BC.CTX_HEAD not in u0
    assert user.split("\n\n", 1)[0] == u0.split("\n\n", 1)[0], "строки блока договора совпадают"


def test_k17_t4a_first_turn_sees_block():
    """К17: сверка Т4а — первый ход `T.run` несёт CTX_HEAD с примесью и не несёт без неё."""
    tools = {"cash": lambda **k: {"ok": False}, "contract": lambda **k: {"ok": False},
             "contract_pdf": lambda *a, **k: {"ok": False}}
    for mixin in (True, False):
        w, br = world(mixin=mixin)
        w.adapter.tools = dict(tools)
        rid = scene(w)
        w.adapter.draft(NUM, rid)
        assert w.call.calls, "модель не звана"
        assert (BC.CTX_HEAD in w.call.calls[0][1]) is mixin, (mixin, w.call.calls[0][1][-600:])


# ══ К15: служба ════════════════════════════════════════════════════════════════════════════════════════════════

def _env():
    w = TM.World()
    return w, {"queue_db": w.qpath, "agent_db": w.dbpath, "mirror_db": "", "tg_token": "", "show_chat": ""}


def _model(env, **kw):
    model, why = S.make_model(env, bridge=TB.Bridge([]), call=lambda s, u: ("", {}), **kw)
    assert model is not None, why
    return model


def test_k15a_flag_off_subprocess():
    """К15 (а)(б): отдельный процесс — флаг не запрошен, «0» или 1 при выключенных бронях: модуля выпуска нет, класс
    прежний; строка старта — только «не засчитан» у 1 без броней."""
    p = subprocess.run([sys.executable, os.path.abspath(__file__), PROBE_ARG], cwd=ROOT, capture_output=True,
                       timeout=300, env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    text = p.stdout.decode("utf-8", "replace")
    got = [ln for ln in text.splitlines() if ln.startswith(PROBE_MARK)]
    assert p.returncode == 0 and got, (p.returncode, text[-800:], p.stderr.decode("utf-8", "replace")[-1500:])
    r = json.loads(got[-1][len(PROBE_MARK):])
    assert r["mods"] == [], r
    runs = r["runs"]
    assert [x["type"] for x in runs] == ["ModelAdapter"] * 3, runs
    assert runs[0]["ctx"] == [] and runs[2]["ctx"] == [], runs
    assert runs[1]["ctx"] == ["наличие по переписке (WA_AGENT_BOOK_CTX): " + W_NO_BOOK], runs
    assert runs[1]["n"] == runs[0]["n"] + 1 and runs[2]["n"] == runs[0]["n"], runs


def test_k15a_flag_off_in_process():
    """К15 (а): флага нет → (None, None), строки нет, класс прежний, выход build адаптера прежний."""
    w, env = _env()
    model = _model(env, book=True)
    assert S.book_ctx_of({}, model) == (None, None) and type(model) is M.ModelAdapter
    lines = []
    S.build(env, environ={"WA_AGENT_DRAFTS": "1", "WA_AGENT_BOOK_READ": "1"}, model=model, line=lines.append)
    assert not [ln for ln in lines if "WA_AGENT_BOOK_CTX" in ln or ln.startswith("наличие по переписке")], lines
    assert type(model) is M.ModelAdapter and S.F_BOOK_CTX == "WA_AGENT_BOOK_CTX" and S.F_BOOK_CTX not in S.FLAGS


def test_k15b_flag_without_book():
    """К15 (б): флаг 1, брони выкл → «не засчитан — …», класс прежний."""
    w, env = _env()
    model = _model(env, book=True)
    got = S.book_ctx_of({S.F_BOOK_CTX: "1"}, model)
    assert got == (False, W_NO_BOOK) and type(model) is M.ModelAdapter, got


def test_k15c_both_on_mixin():
    """К15 (в): оба флага → (True, «вкл — …»), класс «примесь + ModelAdapter» и «примесь + ContractStateAdapter»;
    второй вызов класс не меняет; строка старта стоит сразу после строки броней."""
    import wa_agent_cstate as C
    on = {S.F_BOOK: "1", S.F_BOOK_CTX: "1"}
    w, env = _env()
    model = _model(env, book=True)
    assert S.book_ctx_of(on, model) == (True, W_ON)
    cls = type(model)
    assert cls.__mro__[1] is BC.BookCtxMixin and cls.__mro__[2] is M.ModelAdapter, cls.__mro__
    assert S.book_ctx_of(on, model) == (True, W_ON) and type(model) is cls, "второй вызов класс не меняет"
    csa = _model(env, book=True, cstate=True)
    assert S.book_ctx_of(on, csa) == (True, W_ON)
    assert isinstance(csa, C.ContractStateAdapter) and type(csa).__mro__[1] is BC.BookCtxMixin, type(csa).__mro__
    assert csa.cstate_on is True
    model2 = _model(env, book=True)
    lines = []
    S.build(dict(env, agent_db=w.dbpath + "b"), environ=dict(on, WA_AGENT_DRAFTS="1"), model=model2,
            line=lines.append)
    i = [k for k, ln in enumerate(lines) if ln.startswith("брони (WA_AGENT_BOOK_READ): ")]
    assert len(i) == 1 and lines[i[0] + 1] == "наличие по переписке (WA_AGENT_BOOK_CTX): " + W_ON, lines
    assert len([ln for ln in lines if ln.startswith("наличие по переписке")]) == 1
    assert type(model2).__mro__[1] is BC.BookCtxMixin


def test_k15d_no_model_or_snapshot():
    """К15 (г): модели нет или у неё нет снимка броней → «не засчитан — … нет снимка броней …»."""
    on = {S.F_BOOK: "1", S.F_BOOK_CTX: "1"}
    assert S.book_ctx_of(on, None) == (False, W_NO_SNAP)
    w, env = _env()
    model = _model(env)                                  # book=False — снимка нет
    assert S.book_ctx_of(on, model) == (False, W_NO_SNAP) and type(model) is M.ModelAdapter


def test_k15e_module_not_built():
    """К15 (д): модуль выпуска не импортируется → «не засчитан — модуль … не собран (ImportError)», класс прежний."""
    w, env = _env()
    model = _model(env, book=True)
    saved = sys.modules.get(NEW_MODULE)
    sys.modules[NEW_MODULE] = None
    try:
        got = S.book_ctx_of({S.F_BOOK: "1", S.F_BOOK_CTX: "1"}, model)
    finally:
        sys.modules[NEW_MODULE] = saved
    assert got == (False, W_NO_MOD) and type(model) is M.ModelAdapter, got


def test_k15f_flag_values():
    """К15 (е): 1/true/yes/on (регистр, пробелы) — засчитан; 0/да/""/off — не запрошен."""
    w, env = _env()
    for v in ("1", "true", "YES", " on "):
        model = _model(env, book=True)
        assert S.book_ctx_of({S.F_BOOK: "1", S.F_BOOK_CTX: v}, model) == (True, W_ON), v
    for v in ("0", "да", "", "off", "2"):
        model = _model(env, book=True)
        assert S.book_ctx_of({S.F_BOOK: "1", S.F_BOOK_CTX: v}, model) == (None, None) and \
            type(model) is M.ModelAdapter, v


def test_with_book_ctx_cached_and_idempotent():
    a = BC.with_book_ctx(M.ModelAdapter)
    assert a is BC.with_book_ctx(M.ModelAdapter) and BC.with_book_ctx(a) is a, "один класс на cls, повтор — как есть"
    assert a.__name__ == "BookCtxModelAdapter" and a.__module__ == "wa_book_ctx" and a.__mro__[1] is BC.BookCtxMixin
    assert BC.PAIRS_MAX == M.PAIRS_MAX == 3


# ══ К16: закрепление ═══════════════════════════════════════════════════════════════════════════════════════════

def _blob(path):
    data = open(path, "rb").read()
    shas = {hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()}
    lf = data.replace(b"\r\n", b"\n")
    shas.add(hashlib.sha1(b"blob %d\0" % len(lf) + lf).hexdigest())
    return shas


def _git(*args):
    p = subprocess.run(["git"] + list(args), cwd=ROOT, capture_output=True, timeout=60)
    assert p.returncode == 0, (args, p.stderr.decode("utf-8", "replace")[-500:])
    return p.stdout.decode("utf-8", "replace")


def _tree(name):
    return ast.parse(open(os.path.join(os.environ.get("WA_AGENT_SRC") or ROOT, name), encoding="utf-8").read())


def _module_level_imports(tree):
    out, todo = set(), list(tree.body)
    while todo:
        node = todo.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        if isinstance(node, ast.Import):
            out |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            out.add((node.module or "").split(".")[0])
        todo.extend(ast.iter_child_nodes(node))
    return out


def test_k16_pins():
    """К16: блобы закреплённых файлов прежние — в гейте всегда (от истории дерева не зависит)."""
    for name, sha in PINS.items():
        assert sha in _blob(os.path.join(ROOT, name)), name


RELEASE_DIFF = "BOOKCTX_RELEASE_DIFF"           # разовая приёмка выпуска: «ровно файлы выпуска против cbe1322»


def test_k16_release_files_once():
    """К16 (разово, только при BOOKCTX_RELEASE_DIFF=1): изменены и новые относительно cbe1322 — только файлы выпуска
    (и файл приёмки), временное место tmp_work/ не в счёт. В гейте НЕ гоняется: «ровно эти файлы» краснело бы на первом
    же следующем коммите и на любом неотслеживаемом файле дерева сервера — и pre-push встал бы (находка B2 критика A)."""
    if os.environ.get(RELEASE_DIFF) != "1":
        return
    changed = {x.strip() for x in _git("diff", "--name-only", BASE, "--").splitlines() if x.strip()}
    changed |= {x.strip() for x in _git("ls-files", "--others", "--exclude-standard").splitlines() if x.strip()}
    changed = {x for x in changed if not x.startswith("tmp_work/")}
    assert {"wa_agent_svc.py", "wa_book_ctx.py", "tests/test_wa_book_ctx.py"} <= changed <= {
        "wa_agent_svc.py", "wa_book_ctx.py", "tests/test_wa_book_ctx.py", "tests/test_bookctx_accept.py"}, changed


def test_k16_release_check_not_in_gate():
    """Замок B2: проверка «ровно файлы выпуска» без ручки молчит — набор не зависит от истории git после cbe1322."""
    src = inspect.getsource(test_k16_release_files_once)
    assert "os.environ.get(RELEASE_DIFF) != \"1\"" in src and src.index("return") < src.index("_git("), src[:400]
    assert "_git(" not in inspect.getsource(test_k16_pins)


def test_k16_module_locks():
    """К16: импорты модуля — ровно разрешённые; ни файлов, ни сети, ни базы, ни записи; в примеси — только _history,
    _book и _bctx_*; модуль не импортируется на уровне модуля нигде в корне."""
    tree = _tree("wa_book_ctx.py")
    imps = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            imps |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            imps.add((n.module or "").split(".")[0])
    assert imps <= {"datetime", "re", "wa_agent_model", "wa_book_read", "wa_agent_knowledge"}, imps
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | \
        {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    bad = {"open", "sqlite3", "subprocess", "socket", "os", "sys", "bridge_client", "create_booking", "_post"}
    assert not names & bad, names & bad
    own = {k for k in vars(BC.BookCtxMixin) if not (k.startswith("__") and k.endswith("__"))}
    assert own <= {"_history", "_book"} | {k for k in own if k.startswith("_bctx_")} and {"_history", "_book"} <= own, own
    for fn in ("__init__", "build", "draft", "build_followup"):
        assert fn not in vars(BC.BookCtxMixin), fn
    for name in sorted(os.listdir(ROOT)):
        if name.endswith(".py") and name != "wa_book_ctx.py":
            try:
                t = ast.parse(open(os.path.join(ROOT, name), encoding="utf-8").read())
            except (SyntaxError, UnicodeDecodeError):
                continue
            assert NEW_MODULE not in _module_level_imports(t), name


def test_k16_signatures():
    """К16: сигнатуры зависимостей прежние; make_model, models_of и main не тронуты по форме."""
    def params(fn):
        return list(inspect.signature(fn).parameters)
    assert params(M.price_pairs) == ["ask", "ctx", "today", "bikes", "ask_day"]
    assert params(M.ModelAdapter._book) == ["self", "number", "ask", "today", "now", "ask_day"]
    assert params(M.ModelAdapter._history) == ["self", "number", "upto_id"]
    assert params(B.free_bikes) == ["model", "units", "ds", "de", "rows", "age", "why", "now_local", "door"]
    assert params(S.make_model) == PROD_MAKE_MODEL and params(S.models_of) == ["env", "environ", "line"]
    assert params(S.book_ctx_of) == ["environ", "model"]
    src = inspect.getsource(S.make_model) + inspect.getsource(S.models_of) + inspect.getsource(S.main)
    assert NEW_MODULE not in src and "book_ctx" not in src


# ══ чистые функции: голдены ═══════════════════════════════════════════════════════════════════════════════════

def test_term_in_tail_goldens():
    pos = ["на 20–25", "а на 20–25 свободен?", "с 20-го", "20th", "20 числа", "на 3 дня", "а с 20 по 25?",
           "а 20 октября свободен?"]
    neg = ["с 20 по 25 октября", "Oct 20 to Oct 25", "PCX 160", "в 10:00-12:00", "а свободен?", "is it available?",
           "а с 20 по 25 октября и с 1 по 5 ноября?", "20.10 - 25.10"]
    assert [p for p in pos if not BC.term_in_tail(p, DAY, DAY)] == [], [p for p in pos if not BC.term_in_tail(p, DAY, DAY)]
    assert [n for n in neg if BC.term_in_tail(n, DAY, DAY)] == [], [n for n in neg if BC.term_in_tail(n, DAY, DAY)]
    assert BC.term_in_tail("а завтра?", DAY, DAY) and BC.term_in_tail("а завтра?", DAY), "день словом — срок"
    assert BC.term_in_tail("tomorrow?", DAY) and not BC.term_in_tail("с завтра по 25 октября", DAY, DAY)


# находка B1 критика A: две даты СЛОВОМ от дня вопроса — `find_dates` с днём видит их двумя датами, а `price_pairs`
# берёт даты БЕЗ дня и только по возрастанию; такой хвост прежде проходил мимо G1, и подставлялся прежний срок
B1_POS = ["а сегодня или завтра свободен?", "завтра и послезавтра?", "today or tomorrow?", "а завтра или 20 октября?",
          "а 25 октября или 20 октября свободен?", "а сегодня-завтра свободен?", "is it available today or tomorrow?",
          "а на завтрашний день свободен?"]
# находка I1 критика A: срок словами без чисел
I1_POS = ["а на неделю свободен?", "а на 2 недели?", "а на месяц?", "а в ноябре свободен?", "а на выходные?",
          "next week?", "is it free for a week?", "for a month?", "а через 2 дня свободен?", "is it available in 3 days?",
          "а в пятницу свободен?", "а на сутки?", "а сейчас свободен?", "is it available now?", "for one night?"]
TERM_NEG = ["а свободен?", "is it available?", "а на эти даты свободен?", "Добрый день! А свободен?", "Is it free?",
            "а свободен? и пришлите договор", "May I know if it's free?", "а он свободен на те же даты?", "спасибо"]


def test_b1_i1_term_goldens_with_ask_day():
    """B1/I1: с днём вопроса и без него — каждый новый срок без полных дат по правилу `price_pairs` даёт G1; ссылка на
    прежние даты («на эти даты»), приветствие «Добрый день» и «May I…» сроком не считаются (близнецы)."""
    for ask_day in (DAY, None):
        bad = [p for p in B1_POS + I1_POS if not BC.term_in_tail(p, DAY, ask_day)]
        assert bad == [], (ask_day, bad)
        bad = [n for n in TERM_NEG if BC.term_in_tail(n, DAY, ask_day)]
        assert bad == [], (ask_day, bad)
    # «price_pairs разберёт» — ровно её правило: полный диапазон; две даты БЕЗ дня и по возрастанию
    assert BC.term_parsed("а 20 октября и 25 октября?", DAY) and not BC.term_parsed("а 25 октября или 20 октября?", DAY)
    assert not BC.term_parsed("а сегодня или завтра?", DAY, DAY) and BC.term_parsed("с завтра по 25 октября", DAY, DAY)
    # «сейчас» — срок в хвосте, но не признак другого срока в прежних словах («сейчас посмотрю»)
    assert not BC.term_sign("сейчас посмотрю", DAY, DAY) and BC.term_sign("прилетаем 9 октября", DAY, DAY)


def test_b1_k_two_relative_days_old_term_not_used():
    """B1 (К): хвост с двумя датами словом / в обратном порядке → ровно G1, двери нет, прежний срок 10–15 не подставлен;
    близнец — полный срок «с 20 по 25 октября» проверяется."""
    for q in ("а сегодня или завтра свободен?", "а завтра и послезавтра свободен?", "is it available today or tomorrow?",
              "а завтра или 20 октября свободен?", "а 25 октября или 20 октября свободен?", "а сегодня-завтра свободен?"):
        (_s, user, info, lines), br, _b, _b0 = pair(q=q)
        a = info["avail"]
        assert a["line"] == BC.G_TERM_LINE and a["sieve"] == "term_in_tail", (q, a)
        assert br.doors == [] and "2026-10-10" not in user and BC.CTX_HEAD not in user, (q, br.doors)
        assert ctx_lines(lines) == [L4], (q, ctx_lines(lines))
    (_s, _u, info2, _l), br2, _b, _b0 = pair(q="а с 20 по 25 октября свободен?")
    assert info2["avail"]["source"] == "ctx" and br2.doors == [("PCX 160 1234", "2026-10-20", "2026-10-25")], br2.doors


def test_i1_k_period_words_old_term_not_used():
    """I1 (К): «а на неделю свободен?», «а в ноябре?», «next week?» → G1, двери нет; близнец «на эти даты» — блок."""
    for q in ("а на неделю свободен?", "а в ноябре свободен?", "is it available next week?", "а сейчас свободен?"):
        (_s, user, info, lines), br, _b, _b0 = pair(q=q)
        assert info["avail"]["sieve"] == "term_in_tail" and br.doors == [] and "2026-10-10" not in user, (q, br.doors)
        assert br.client_calls == [], (q, br.client_calls)
    (_s, u2, i2, _l), br2, _b, _b0 = pair(q="а на эти даты свободен?")
    assert i2["avail"]["outcome"] == B.FREE and br2.doors == [("PCX 160 1234", "2026-10-10", "2026-10-15")], br2.doors


# ══ находки критиков: вопрос не о байке, вторая дверь, смена после пары, своя бронь, пары разошлись ═══════════════

def test_gate_not_about_bike_parent_answer():
    """I3 (A) / I4 (правда): слово наличия про чужой предмет или вопрос о брони → примесь пассивна: выход, журнал,
    clients и двери равны близнецу без примеси. Близнецы: «а есть?», «Is it free?», «а свободен? и сколько депозит?» —
    блок по переписке."""
    for q in ("а шлем есть?", "Is delivery free?", "Есть ли депозит?", "any discount for 10 days?", "бронь в силе?",
              "is my booking confirmed?", "а доставка свободна?", "Есть ли скидка?", "do you have helmets?"):
        (s, u, i, l), br, (s0, u0, i0, l0), br0 = pair(q=q)
        assert (s, u, i) == (s0, u0, i0) and l == l0 and not ctx_lines(l), (q, [x for x in l if x not in l0])
        assert br.client_calls == br0.client_calls and br.doors == br0.doors, (q, br.client_calls, br.doors)
    for q in ("а есть?", "Is it free?", "а свободен? и сколько депозит?"):
        (_s, u2, i2, _l), br2, _b, _b0 = pair(q=q)
        assert BC.CTX_HEAD in u2 and i2["avail"]["source"] == "ctx", (q, u2[-600:])
    assert BC.asks_bike("а свободен?") and not BC.asks_bike("а шлем свободен?") and not BC.asks_bike("бронь в силе?")


def test_i2_parent_checked_pair_no_second_door():
    """I2 (A): хвост назвал модель и даты, родитель проверил пару и получил «неизвестно» (дверь разошлась) → примесь
    второй двери на ту же пару не зовёт: выход и двери как у близнеца без примеси (дверь одна). Близнец — «а свободен?»
    при той же двери: пары из переписки, блок."""
    q = "а PCX 160 с 20 по 25 октября свободен?"
    (s, u, i, l), br, (s0, u0, i0, l0), br0 = pair(q=q, bridge={"available": False})
    assert i0["avail"]["outcome"] == B.UNKNOWN and i0["avail"]["model"] == "PCX 160", i0["avail"]
    assert (s, u, i) == (s0, u0, i0) and l == l0 and br.doors == br0.doors and len(br.doors) == 1, (br.doors, br0.doors)
    assert "source" not in i["avail"] and not ctx_lines(l)
    (_s, _u, i2, _l), br2, _b, _b0 = pair(bridge={"available": False})
    assert i2["avail"]["source"] == "ctx" and len(br2.doors) == 1, (i2["avail"], br2.doors)


def scene4(w, c2, u2="Хорошо, записал.", c1=C1, u1=U1, q=Q):
    """C1 (клиент) → U1 (мы) → C2 (клиент) → U2 (мы) → вопрос Q → номер строки Q."""
    w.put(T0 - 7200, c1)
    w.put(T0 - 6600, u1, kind="echo")
    w.put(T0 - 3600, c2)
    w.put(T0 - 3000, u2, kind="echo")
    return w.put(T0, q)


def pair4(rows=(), live=False, **kw):
    w, br = world(rows, live=live)
    got = built(w, scene4(w, **kw))
    return got, br


def test_b1_truth_model_changed_after_pair():
    """B1 (правда): после пары PCX 160 10–15 клиент спросил про другую модель («а XMAX 300?») → пара PCX — отсев
    «после этих слов клиент называл другую модель», двери нет, «неизвестно». Близнец «а PCX 160?» — проверяется."""
    (_s, user, info, lines), br = pair4(c2="а XMAX 300?", u2="XMAX 300 на 5 суток — 2500 бат")
    a = info["avail"]
    assert a["outcome"] == B.UNKNOWN and [p["sieve"] for p in a["pairs"]] == ["later_model"], a
    assert "— PCX 160 (с 10.10 по 15.10): НАЛИЧИЕ: НЕИЗВЕСТНО — после этих слов клиент называл другую модель." in user
    assert br.doors == [] and B.R_AVAIL_UNKNOWN in reasons(info), (br.doors, reasons(info))
    (_s, _u, info2, _l), br2 = pair4(c2="а PCX 160?")
    assert info2["avail"]["outcome"] == B.FREE and br2.doors == [("PCX 160 1234", "2026-10-10", "2026-10-15")], br2.doors


def test_b1_truth_term_changed_after_pair():
    """B1 (правда): после пары клиент назвал другой срок — словами («а на неделю позже?») или полными датами («а с 20 по
    25 октября?») → прежняя пара 10–15 в отсеве «после этих слов клиент называл другой срок», 10.10 в двери нет. Близнец
    «а депозит какой?» — срок не менялся, пара проверяется."""
    (_s, user, info, _l), br = pair4(c2="а на неделю позже?")
    assert [p["sieve"] for p in info["avail"]["pairs"]] == ["later_term"] and br.doors == [], info["avail"]
    assert "после этих слов клиент называл другой срок" in user
    (_s, user2, info2, _l), br2 = pair4(c2="а с 20 по 25 октября?")
    p2 = {(p["date_start"], p["sieve"]) for p in info2["avail"]["pairs"]}
    assert p2 == {("2026-10-20", None), ("2026-10-10", "later_term")}, info2["avail"]["pairs"]
    assert br2.doors == [("PCX 160 1234", "2026-10-20", "2026-10-25")] and info2["avail"]["outcome"] == B.UNKNOWN
    (_s, _u, info3, _l), br3 = pair4(c2="а депозит какой?")
    assert info3["avail"]["outcome"] == B.FREE and br3.doors == [("PCX 160 1234", "2026-10-10", "2026-10-15")]


def test_i2_truth_term_from_different_messages():
    """I2 (правда): «PCX 160 на 5 дней» и отдельно «прилетаем 10 октября» → цена сшила 10–15 из двух сообщений; наличию
    это не опора: отсев «срок собран из разных сообщений», двери нет. Близнец: «с 10 октября на 5 дней» в одном
    сообщении — проверяется 10–15."""
    (_s, user, info, _l), br = pair4(c1="PCX 160 на 5 дней сколько?", c2="прилетаем 10 октября", u2="Ок.")
    assert [p["sieve"] for p in info["avail"]["pairs"]] == ["split_term"] and br.doors == [], info["avail"]
    assert BC.W_SPLIT in user and info["avail"]["outcome"] == B.UNKNOWN
    (_s, _u, info2, _l), br2 = pair4(c1="PCX 160 с 10 октября на 5 дней сколько?", c2="ок", u2="Ок.")
    assert info2["avail"]["outcome"] == B.FREE and br2.doors == [("PCX 160 1234", "2026-10-10", "2026-10-15")], br2.doors


def test_b2_truth_own_booking_not_busy():
    """B2 (правда): на даты пары в таблице бронь по номеру ЭТОГО клиента → не «заняты все», а «неизвестно» с причиной;
    ни контакты, ни имя строки броней не попадают ни в запрос, ни в журнал. Близнец — те же строки без его номера: BUSY."""
    own = [TB.row("PCX 160 1234", "Бронь", "2026-10-10 10:00", "2026-10-15 10:00", contacts=TB.CONTACT),
           TB.row("PCX 160 5678", "Бронь", "2026-10-11 10:00", "2026-10-14 10:00")]
    (_s, user, info, lines), br, _b, _b0 = pair(rows=own)
    a = info["avail"]
    assert a["outcome"] == B.UNKNOWN and a["pairs"][0]["sieve"] == "own_booking" and BC.W_OWN in user, a
    assert "заняты все" not in user and B.R_AVAIL_UNKNOWN in reasons(info), reasons(info)
    for secret in (TB.SECRET_NAME, "000-0009", "000000009", "x-client"):
        assert secret not in user and not [ln for ln in lines if secret in ln], secret
    other = [dict(r, contacts="") for r in own]
    (_s, _u, info2, _l), _br, _b, _b0 = pair(rows=other)
    assert info2["avail"]["outcome"] == B.BUSY, info2["avail"]
    # свободный второй юнит при брони самого клиента на первом — тоже «неизвестно» (о его брони решает человек)
    half = own[:1]
    (_s, _u, info3, _l), br3, _b, _b0 = pair(rows=half)
    assert info3["avail"]["outcome"] == B.UNKNOWN and info3["avail"]["pairs"][0]["sieve"] == "own_booking", info3["avail"]


def test_b2_truth_booking_talk_busy_unknown():
    """B2 (правда): в переписке речь о брони, а таблица «заняты все» → «неизвестно» (это может быть его же бронь, номер
    в таблице записан иначе). Близнец без слов брони — BUSY."""
    busy = [TB.row("PCX 160 1234", "Бронь", "2026-10-10 10:00", "2026-10-15 10:00"),
            TB.row("PCX 160 5678", "Бронь", "2026-10-11 10:00", "2026-10-14 10:00")]
    (_s, user, info, _l), _br, _b, _b0 = pair(rows=busy, c1="PCX 160 с 10 по 15 октября сколько? хочу забронировать")
    assert info["avail"]["outcome"] == B.UNKNOWN and info["avail"]["pairs"][0]["sieve"] == "booking_talk", info["avail"]
    assert BC.W_BOOK_TALK in user
    (_s, _u, info2, _l), _br, _b, _b0 = pair(rows=busy)
    assert info2["avail"]["outcome"] == B.BUSY


def test_i1_truth_mixed_pairs_unknown():
    """I1 (правда): PCX свободен, XMAX занят на те же даты → исход блока не FREE, а «неизвестно» с причиной «пары
    разошлись» на карточке; строки пар — как есть. Близнец — обе свободны: FREE."""
    c1 = "PCX 160 или XMAX 300 с 10 по 15 октября сколько?"
    rows = [TB.row("XMAX 300CC NEW BLUE PHUKET 4321", "Бронь", "2026-10-10 10:00", "2026-10-15 10:00")]
    (_s, user, info, _l), _br, _b, _b0 = pair(rows=rows, live=True, c1=c1)
    a = info["avail"]
    assert sorted(p["outcome"] for p in a["pairs"]) == [B.BUSY, B.FREE] and a["outcome"] == B.UNKNOWN, a
    assert a["why"] == BC.W_MIXED and B.R_AVAIL_UNKNOWN in reasons(info), (a["why"], reasons(info))
    (_s, _u, info2, _l), _br, _b, _b0 = pair(live=True, c1=c1)
    assert info2["avail"]["outcome"] == B.FREE and info2["avail"]["why"] == "", info2["avail"]


def test_model_in_tail_goldens():
    for t in ("Vespa 150", "PCX 150", "CB 500", "а Vespa 150 с 20 по 25 октября свободна?"):
        assert BC.model_in_tail(t, LIVE), t
    for t in ("PCX 160", "X-ADV 750", "CB 650R", "MT-03", "а свободен?", "NMAX свободен?", "с 20 по 25 октября"):
        assert not BC.model_in_tail(t, LIVE), t


def test_said_day():
    d1, d2 = datetime.date(2026, 9, 1), datetime.date(2026, 9, 15)
    ctx = [("мы", "x", datetime.date(2026, 8, 1)), (M.WHO_CLIENT, "a", d2), (M.WHO_CLIENT, "b", d1),
           (M.WHO_CLIENT, "c", None)]
    assert BC.said_day(ctx, DAY) == d1 and BC.said_day([], DAY) == DAY and BC.said_day([], None) is None
    assert BC.said_day([("мы", "x", d1)], None) is None and BC.said_day(ctx[1:2], None) == d2


def test_sieve_branches_with_twins():
    d = datetime.date
    t = {"ds": d(2026, 10, 10), "de": d(2026, 10, 15), "days": 5}
    alias = {"alias": "CB", "cands": ["CB 300CC", "CB 650R"]}
    # S2 и близнец — та же пара с моделью парка
    assert BC.sieve(alias, t, DAY, DAY) == ("alias", "модель не определена: «CB» подходит к моделям парка CB 300CC / "
                                            "CB 650R", "спроси у клиента, какая модель.", t["ds"], t["de"])
    assert BC.sieve("CB 650R", t, DAY, DAY) == (None, None, None, t["ds"], t["de"])
    # S3: начала нет
    assert BC.sieve("PCX 160", {"ds": None, "de": None, "days": 5}, DAY, DAY) == (
        "no_start", "дата начала аренды в переписке не названа", "спроси у клиента даты (с какого по какое число).",
        None, None)
    # S4: срок — минимум класса, клиент срок не называл; близнец — клиент назвал 2 суток → даты клиента
    tmin = dict(t, min=5)
    assert BC.sieve("NMAX 155CC", tmin, DAY, DAY) == ("no_term", "срок для этой модели клиент не называл",
                                                      "спроси у клиента даты (с какого по какое число).", None, None)
    assert BC.sieve("NMAX 155CC", dict(tmin, client=2), DAY, DAY) == (None, None, None, t["ds"], d(2026, 10, 12))
    # S5: прошёл; унесён на год от дня, когда сказан; 29.02 без пары; близнецы — будущий срок, сказан в тот же год
    past = {"ds": d(2026, 9, 10), "de": d(2026, 9, 15), "days": 5}
    assert BC.sieve("PCX 160", past, DAY, DAY)[0] == "past" and BC.sieve("PCX 160", t, DAY, DAY)[0] is None
    year = {"ds": d(2027, 9, 10), "de": d(2027, 9, 15), "days": 5}
    assert BC.sieve("PCX 160", year, DAY, d(2026, 9, 1)) == ("past", "срок из переписки уже прошёл или начался",
                                                             "спроси у клиента новые даты.", year["ds"], year["de"])
    assert BC.sieve("PCX 160", year, DAY, d(2026, 9, 11))[0] is None
    leap = {"ds": d(2028, 2, 29), "de": d(2028, 3, 3), "days": 3}
    assert BC.sieve("PCX 160", leap, DAY, d(2027, 3, 1))[0] == "past"
    assert BC.sieve("PCX 160", leap, DAY, d(2028, 2, 1))[0] is None
    # S6: время сообщений неизвестно; близнец — известно
    assert BC.sieve("PCX 160", t, DAY, None) == ("no_time", "время сообщений клиента неизвестно — срок не привязан к "
                                                 "дате", "спроси у клиента даты (с какого по какое число).",
                                                 t["ds"], t["de"])
    assert BC.first(d(2026, 9, 21), d(2026, 9, 10)) == d(2027, 9, 10)
    assert BC.first(d(2026, 9, 1), d(2027, 9, 10)) == d(2026, 9, 10)


def test_labels():
    d = datetime.date
    assert BC.pair_label("PCX 160", None, d(2026, 10, 10), d(2026, 10, 15)) == "PCX 160 (с 10.10 по 15.10)"
    assert BC.pair_label({"alias": "CB", "cands": []}, "alias", d(2026, 10, 10), d(2026, 10, 15)) == \
        "«CB» (с 10.10 по 15.10)"
    assert BC.pair_label("NMAX 155CC", "no_term", d(2026, 10, 10), d(2026, 10, 15)) == "NMAX 155CC"
    assert BC.pair_label("PCX 160", "no_start", None, None) == "PCX 160"


def main():
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    bad = 0
    for name, fn in tests:
        try:
            fn()
            print("PASS", name)
        except Exception as e:                                       # noqa: BLE001
            bad += 1
            print("FAIL", name, "—", type(e).__name__, str(e)[:300])
    print("ИТОГ %d/%d" % (len(tests) - bad, len(tests)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
