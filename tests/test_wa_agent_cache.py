#!/usr/bin/env python3
"""Кэш промпта агента WhatsApp (WAAGENTCACHE0210): неизменная часть (инструкция, снимки `faq` и `business_rules`
без возраста) — впереди с отметкой кэша, переменная — после; второй черновик в срок читает кэш; смена снимка —
новая запись; цена вызова по usage — строкой журнала, в учёт трат и в сводку службы; кэш выключен — запрос
как раньше. Всё на подделке API модели (кэш по правилам документации: префикс до отметки байт-в-байт и срок
не вышел — чтение, срок продлевается; иначе запись) — путь идёт через настоящий `paid_call`. Сети нет,
модели нет; учёт трат `spend_ledger.meter` подменён записью в память — живой учёт не пишется.

WA_AGENT_SRC=<каталог> подменяет модули (прогон мутантов)."""
import os
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
if os.environ.get("WA_AGENT_SRC"):
    sys.path.insert(0, os.environ["WA_AGENT_SRC"])

import spend_ledger  # noqa: E402

LEDGER = []
spend_ledger.meter = lambda model, usage: LEDGER.append(               # живой учёт трат не трогаем
    (model, getattr(usage, "input_tokens", None), getattr(usage, "output_tokens", None)))

import test_wa_agent_model as TM  # noqa: E402
import wa_agent_knowledge as K  # noqa: E402
import wa_agent_model as WM  # noqa: E402
import wa_agent_svc as SV  # noqa: E402

NUM, T0, FAQ, RULES, OK_JSON = TM.NUM, TM.T0, TM.FAQ, TM.RULES, TM.OK_JSON
MODEL = "claude-sonnet-4-5"                      # $3 вход / $15 выход за 1 млн (spend_ledger.PRICE_PER_MTOK)
TOK = 4                                          # символов на токен в подделке
NOENV = os.path.join(tempfile.mkdtemp(prefix="wa_cache_t_"), "нет.env")


class FakeAPI:
    """Подделка `messages.create`: usage как у API. Отметка cache_control на блоке system — префикс до неё
    включительно; тот же префикс байт-в-байт в срок — чтение (срок продлевается), иначе запись по сроку
    отметки (5 мин по умолчанию, 1 ч по ttl='1h'). Без отметки — всё во вход."""

    def __init__(self, clock):
        self.clock, self.store, self.kw, self.reply = clock, {}, [], OK_JSON

    def create(self, **kw):
        self.kw.append(kw)
        system, user = kw["system"], kw["messages"][0]["content"]
        cw5 = cw1h = cr = 0
        if isinstance(system, str):
            rest = len(system) + len(user)
        else:
            marks = [i for i, b in enumerate(system) if b.get("cache_control")]
            idx = marks[-1] if marks else -1
            pre = "".join(b["text"] for b in system[:idx + 1])
            rest = sum(len(b["text"]) for b in system[idx + 1:]) + len(user)
            if idx < 0:
                rest += len(pre)
            else:
                ttl = system[idx]["cache_control"].get("ttl", "5m")
                now = self.clock()
                if self.store.get(pre, 0) > now:
                    cr = len(pre) // TOK
                elif ttl == "1h":
                    cw1h = len(pre) // TOK
                else:
                    cw5 = len(pre) // TOK
                self.store[pre] = now + (3600 if ttl == "1h" else 300)
        usage = types.SimpleNamespace(
            input_tokens=rest // TOK, output_tokens=50, cache_creation_input_tokens=cw5 + cw1h,
            cache_read_input_tokens=cr,
            cache_creation=types.SimpleNamespace(ephemeral_5m_input_tokens=cw5, ephemeral_1h_input_tokens=cw1h))
        return types.SimpleNamespace(model=kw["model"], usage=usage,
                                     content=[types.SimpleNamespace(type="text", text=self.reply)])


class Rig:
    """Очередь из мира test_wa_agent_model, адаптер с настоящим paid_call поверх подделки API."""

    def __init__(self, cache="1h", rules=None):
        self.w = TM.World()
        self.clock = [T0]
        self.api = FakeAPI(lambda: self.clock[0])
        api = self.api
        fake = types.ModuleType("anthropic")

        class Anthropic:
            def __init__(self, api_key=None):
                self.messages = types.SimpleNamespace(create=api.create)
        fake.Anthropic = Anthropic
        saved = sys.modules.get("anthropic")
        sys.modules["anthropic"] = fake
        os.environ["ANTHROPIC_API_KEY"] = "fake-key-for-test"
        try:
            call = WM.paid_call(model_name=MODEL, env_file=NOENV)
        finally:
            if saved is not None:
                sys.modules["anthropic"] = saved
            else:
                sys.modules.pop("anthropic", None)
        self.rules = [rules or RULES]
        self.reads, self.lines = [], []

        def read_doc(name):
            self.reads.append(name)
            return {"ok": True, "text": FAQ if name == "faq" else self.rules[0]}
        self.read_doc = read_doc
        self.adapter = WM.ModelAdapter(self.w.qpath, call, read_doc=read_doc, clock=lambda: self.clock[0],
                                       log=self.lines.append, cache=cache)
        self.n = 0

    def draft(self, text, at):
        self.clock[0] = at
        rid = self.w.put(at - 30, text)
        return self.adapter.draft(NUM, rid)

    def usage(self, i=-1):
        return self.adapter.last["usage"]


def _pre(system):
    return "".join(b["text"] for b in system if True)


# ═══ плюсы ═══════════════════════════════════════════════════════════════════════════════

def test_second_draft_in_ttl_reads_cache():
    r = Rig("1h")
    assert r.draft("ВОПРОС-1 а доставка есть?", T0)
    u1 = dict(r.usage())
    assert u1["cw"] > 0 and u1["cw1h"] == u1["cw"] and u1["cr"] == 0, u1
    assert r.draft("ВОПРОС-2 и шлем дадите?", T0 + 1200)      # 20 мин: узлы перечитаны тем же текстом
    u2 = dict(r.usage())
    assert u2["cr"] == u1["cw"] and u2["cw"] == 0, (u1, u2)
    assert r.reads.count("faq") == 2 and r.reads.count("business_rules") == 2, r.reads
    s1, s2 = r.api.kw[0]["system"], r.api.kw[1]["system"]
    assert s1 == s2 and isinstance(s1, list) and len(s1) == 2, s1
    assert s1[0]["text"] == WM.SYSTEM_PROMPT and "cache_control" not in s1[0], s1[0].keys()
    assert s1[1]["cache_control"] == {"type": "ephemeral", "ttl": "1h"}, s1[1]
    assert FAQ in s1[1]["text"] and RULES in s1[1]["text"] and "снят" not in s1[1]["text"], s1[1]["text"]
    user2 = r.api.kw[1]["messages"][0]["content"]
    assert FAQ not in user2 and RULES not in user2, user2[:300]
    assert "ВОЗРАСТ ЗНАНИЙ: business_rules — снят 10 мин назад; faq — снят 10 мин назад" in user2 or \
        "ВОЗРАСТ ЗНАНИЙ: business_rules — снят 0 мин назад; faq — снят 0 мин назад" in user2, user2[:300]
    assert "ВОПРОС-2" in user2.split("КЛИЕНТ СЕЙЧАС")[1] and "ВОПРОС" not in _pre(s2), user2[-200:]
    assert any(ln.startswith("черновик: цена:") and "чтение из кэша %d" % u2["cr"] in ln for ln in r.lines), r.lines


def test_snapshot_change_new_write():
    r = Rig("1h")
    r.draft("ВОПРОС-1 а доставка есть?", T0)
    r.rules[0] = RULES + " Новое правило: каска детям бесплатно."
    r.draft("ВОПРОС-2 и шлем дадите?", T0 + 700)               # узел перечитан — текст другой
    u2 = r.usage()
    assert u2["cw"] > 0 and u2["cr"] == 0, u2
    s1, s2 = r.api.kw[0]["system"], r.api.kw[1]["system"]
    assert s1[0] == s2[0] and s1[1]["text"] != s2[1]["text"] and "каска детям" in s2[1]["text"]


def test_age_only_in_message_prefix_stable():
    """Возраст меняется каждую минуту — в префиксе его нет: 3 мин и 9 мин дают один и тот же префикс."""
    r = Rig("1h")
    s1, u1, _ = r.adapter.build(NUM, 0, now=T0)
    s2, u2, _ = r.adapter.build(NUM, 0, now=T0 + 540)
    assert s1 == s2, "префикс сменился от возраста"
    assert "снят 0 мин назад" in u1 and "снят 9 мин назад" in u2, (u1[:200], u2[:200])


def test_unread_node_reason_not_in_prefix():
    r = Rig("1h")
    errs = ["Timeout", "HTTP 502"]
    r.adapter.knowledge = K.Knowledge(lambda n: {"ok": False, "error": errs[0]} if n == "business_rules"
                                      else {"ok": True, "text": FAQ})
    s1, u1, _ = r.adapter.build(NUM, 0, now=T0)
    errs[0] = errs[1]
    s2, u2, _ = r.adapter.build(NUM, 0, now=T0 + 700)
    assert s1 == s2 and "НЕИЗВЕСТНО" in s1[1]["text"], s1[1]["text"][:300]
    assert "Timeout" not in _pre(s1) and "HTTP 502" in u2 and "business_rules — НЕИЗВЕСТНО" in u2, u2[:300]


def test_ttl_5m_read_in_term_write_after():
    r = Rig("5m")
    r.draft("ВОПРОС-1", T0)
    assert r.usage()["cw5"] > 0 and r.api.kw[0]["system"][1]["cache_control"]["ttl"] == "5m"
    r.draft("ВОПРОС-2", T0 + 200)
    assert r.usage()["cr"] > 0 and r.usage()["cw"] == 0, r.usage()
    r.draft("ВОПРОС-3", T0 + 200 + 301)                          # 5 мин после последнего чтения — истёк
    assert r.usage()["cw5"] > 0 and r.usage()["cr"] == 0, r.usage()


def test_cost_by_usage():
    z = {"in": 0, "cw": 0, "cw5": 0, "cw1h": 0, "cr": 0, "out": 0}
    c = WM.cost_of(MODEL, dict(z, **{"in": 1000, "cw": 40000, "cw1h": 40000, "out": 200}))
    assert abs(c["usd"] - (1000 * 3 + 40000 * 2 * 3 + 200 * 15) / 1e6) < 1e-9, c
    assert abs(c["usd_nocache"] - (41000 * 3 + 200 * 15) / 1e6) < 1e-9, c
    c = WM.cost_of(MODEL, dict(z, **{"in": 1000, "cw": 40000, "cw5": 40000, "out": 200}))
    assert abs(c["usd"] - (1000 * 3 + 40000 * 1.25 * 3 + 200 * 15) / 1e6) < 1e-9, c
    c = WM.cost_of(MODEL, dict(z, **{"in": 1000, "cr": 40000, "out": 200}))
    assert abs(c["usd"] - (1000 * 3 + 40000 * 0.1 * 3 + 200 * 15) / 1e6) < 1e-9, c
    c = WM.cost_of(MODEL, dict(z, **{"in": 1000, "cw": 40000, "out": 200}))    # разбивки по сроку нет — 2×
    assert abs(c["usd"] - (1000 * 3 + 40000 * 2 * 3 + 200 * 15) / 1e6) < 1e-9, c
    c = WM.cost_of(MODEL, dict(z, **{"in": 41000, "out": 200}))                 # без кэша — как раньше
    assert abs(c["usd"] - c["usd_nocache"]) < 1e-12 and c["eq_in"] == 41000, c


def test_cost_reaches_journal_ledger_and_summary():
    del LEDGER[:]
    r = Rig("1h")
    r.draft("ВОПРОС-1", T0)
    u1 = dict(r.usage())
    r.draft("ВОПРОС-2", T0 + 120)
    u2 = dict(r.usage())
    r.draft("ВОПРОС-3", T0 + 240)
    u3 = dict(r.usage())
    assert LEDGER[0] == (MODEL, u1["in"] + 2 * u1["cw1h"], 50), (LEDGER, u1)
    assert LEDGER[1] == (MODEL, int(round(u2["in"] + 0.1 * u2["cr"])), 50), (LEDGER, u2)
    s = r.adapter.spend
    want = sum(WM.cost_of(MODEL, u)["usd"] for u in (u1, u2, u3))
    assert s["calls"] == 3 and s["cw"] == u1["cw"] and s["cr"] == u2["cr"] + u3["cr"] and abs(s["usd"] - want) < 1e-9, s
    # запись 1 ч стоит 2× — выгода с третьего вызова в срок: 2 + 0.1 + 0.1 < 3 (на двух 2.1 > 2)
    assert s["usd_nocache"] > s["usd"], s
    cost = [ln for ln in r.lines if ln.startswith("черновик: цена:")]
    assert len(cost) == 3 and "запись в кэш %d (5 мин 0, 1 ч %d)" % (u1["cw"], u1["cw1h"]) in cost[0], cost
    assert "$%.4f" % WM.cost_of(MODEL, u2)["usd"] in cost[1], cost
    assert not any("ВОПРОС" in ln or NUM in ln for ln in r.lines), r.lines
    r.w.core.model = r.adapter
    words = {k: "выкл" for k in SV.FLAGS}
    line = SV.summary(r.w.core, r.w.tg, words, {})
    assert "модель: вызовов 3 · вход %d · запись в кэш %d · чтение из кэша %d" % (s["in"], s["cw"], s["cr"]) in line
    assert "$%.4f (без кэша $%.4f)" % (s["usd"], s["usd_nocache"]) in line, line


def test_followup_same_rule():
    r = Rig("1h")
    r.w.put(T0 - 100, "ВОПРОС-1")
    s, u, info = r.adapter.build_followup(NUM, 1, now=T0)
    assert s[0]["text"] == WM.FOLLOW_SYSTEM_PROMPT and s[1]["cache_control"]["ttl"] == "1h", s
    assert RULES in s[1]["text"] and RULES not in u and "ВОЗРАСТ ЗНАНИЙ" in u and info["cache"] == "1h"
    assert r.adapter.followup(NUM, 1) and r.adapter.spend["calls"] == 1 and r.adapter.spend["cw"] > 0
    assert any(ln.startswith("напоминание: цена:") for ln in r.lines), r.lines


def test_cache_switch_values_and_start_line():
    for v in (None, "", "0", "off", "no", "2h", "5 m", "yes please"):
        assert WM.cache_ttl_of(v) is None, v
    for v, want in (("1", "1h"), ("on", "1h"), ("TRUE", "1h"), ("1h", "1h"), (" 1H ", "1h"), ("5m", "5m")):
        assert WM.cache_ttl_of(v) == want, (v, WM.cache_ttl_of(v))
    r = Rig(None)
    assert r.adapter.cache is None and WM.ModelAdapter(r.w.qpath, None, cache="2h").cache is None
    br = types.SimpleNamespace(_call=lambda *a, **k: {"ok": False}, fleet=lambda: {}, quote_price=lambda *a: {},
                               clients=lambda **k: {})
    env = {"queue_db": r.w.qpath, "agent_db": os.path.join(os.path.dirname(r.w.qpath), "svc.db")}
    m, why = SV.make_model(env, bridge=br, call=lambda s, u: ("", {}), cache="1h")
    assert m is not None and m.cache == "1h", why
    lines = []
    SV.build(env, environ={}, model=m, line=lines.append)
    assert "кэш промпта (WA_AGENT_CACHE): вкл, срок 1h — инструкция и узлы знаний впереди с отметкой кэша" in lines
    lines2 = []
    env2 = dict(env, agent_db=os.path.join(os.path.dirname(r.w.qpath), "svc2.db"))
    SV.build(env2, environ={}, model=None, line=lines2.append)
    assert "кэш промпта (WA_AGENT_CACHE): выкл — запрос модели как раньше" in lines2, lines2


def test_main_passes_cache_switch():
    """Служба: main передаёт срок WA_AGENT_CACHE в make_model («1» → 1h, «5m» → 5m, нет — None). Руки main
    подменены (образец — test_wa_book_read.test_main_passes_switch)."""
    class Stop(Exception):
        pass

    def build(*a, **k):
        raise Stop()
    w, seen = TM.World(), []
    env = {"queue_db": w.qpath, "agent_db": w.dbpath, "mirror_db": "", "tg_token": "", "show_chat": "",
           "log_path": w.dbpath + ".log"}
    saved = (SV.env_of, SV.make_model, SV.build, dict(os.environ))
    try:
        SV.env_of, SV.build = (lambda: env), build
        SV.make_model = lambda e, line=None, bridge=None, call=None, lessons=False, book=False, cache=None: \
            seen.append(cache) or (None, "")
        for flag in ("1", "5m", None):
            os.environ["WA_AGENT_DRAFTS"] = "1"
            os.environ.pop(SV.F_CACHE, None)
            if flag:
                os.environ[SV.F_CACHE] = flag
            try:
                SV.main()
            except Stop:
                pass
    finally:
        SV.env_of, SV.make_model, SV.build = saved[:3]
        os.environ.clear()
        os.environ.update(saved[3])
    assert seen == ["1h", "5m", None], seen


# ═══ минусы ══════════════════════════════════════════════════════════════════════════════

def test_cache_off_request_as_before():
    """Выключен — system строкой (прежняя инструкция), узлы с возрастом в сообщении по-прежнему, отметок
    кэша нет; запрос тот же, что у адаптера без параметра cache; usage без кэша — цена как раньше."""
    del LEDGER[:]
    r = Rig(None)
    r.draft("ВОПРОС-1 а доставка есть?", T0)
    kw = r.api.kw[0]
    assert kw["system"] == WM.SYSTEM_PROMPT, type(kw["system"])
    user = kw["messages"][0]["content"]
    assert "cache_control" not in repr(kw) and "ВОЗРАСТ ЗНАНИЙ" not in user and WM.KNOW_HEAD not in user
    i_rules, i_faq = user.index("УЗЕЛ business_rules (снят 0 мин назад"), user.index("УЗЕЛ faq (снят 0 мин назад")
    assert user.index("СЕГОДНЯ:") < i_rules < i_faq < user.index("ИСТОРИЯ ПЕРЕПИСКИ") < user.index("КЛИЕНТ СЕЙЧАС")
    legacy = WM.ModelAdapter(r.w.qpath, None, read_doc=r.read_doc, clock=lambda: T0)
    assert legacy.cache is None and legacy.build(NUM, 1, now=T0)[:2] == r.adapter.build(NUM, 1, now=T0)[:2]
    u = r.usage()
    assert u["cw"] == 0 and u["cr"] == 0 and LEDGER[0] == (MODEL, u["in"], 50), (u, LEDGER)
    s = r.adapter.spend
    assert abs(s["usd"] - s["usd_nocache"]) < 1e-12 and s["calls"] == 1, s


def test_followup_off_as_before():
    r = Rig(None)
    r.w.put(T0 - 100, "ВОПРОС-1")
    s, u, _ = r.adapter.build_followup(NUM, 1, now=T0)
    assert s == WM.FOLLOW_SYSTEM_PROMPT and "УЗЕЛ faq (снят 0 мин назад" in u and "ВОЗРАСТ ЗНАНИЙ" not in u


def test_no_cache_mark_no_cache_usage():
    """Подделка честна: без отметки кэша запись и чтение — ноль даже на повторе того же запроса."""
    r = Rig(None)
    r.draft("ВОПРОС-1", T0)
    r.draft("ВОПРОС-2", T0 + 60)
    assert r.usage()["cr"] == 0 and r.usage()["cw"] == 0


def main():
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    bad = 0
    for name, fn in tests:
        try:
            fn()
            print("PASS", name)
        except Exception as e:                                       # noqa: BLE001
            bad += 1
            print("FAIL", name, "—", type(e).__name__, str(e)[:200])
    print("ИТОГ %d/%d" % (len(tests) - bad, len(tests)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
