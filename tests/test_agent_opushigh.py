# -*- coding: utf-8 -*-
"""WAOPUSHIGHC0510: код агента готов к Claude Opus 5.5 уровня high.

Повод — владелец 05.10 19:01: Opus 5.5 high. По Anthropic 05.10 уровень идёт в запросе `output_config.effort`
(по умолчанию medium), max_tokens — общий предел мыслей и текста; claude-opus-5-5 — $4/$20 за млн. Теперь:
  п.1 уровень — аргумент paid_call(effort=…) или WA_AGENT_EFFORT (low, medium, high, xhigh, max): задан — в запросе
      output_config через extra_body; не задан — запрос как был; иное — не шлётся и названо в строке старта;
  п.2 предел — аргумент paid_call(max_tokens=…) или WA_AGENT_MAX_TOKENS; не задан — при уровне 16000, без 1500;
  п.3 ответ, оборванный пределом (stop_reason max_tokens), — черновика нет, причина «ответ модели оборван пределом
      токенов» в журнале — даже если обрывок разбирается;
  п.4 цена: claude-opus-5-5 (4, 20), claude-sonnet-5-5 (2, 10) в spend_ledger;
  п.5 строка старта службы — модель, уровень и предел, ключей нет.
Подделка клиента пишет аргументы `messages.create`; настройки — словарём, файл настроек не читается. Сети и модели
нет. Учёт трат `spend_ledger.meter` подменён записью в память — живой учёт не пишется; цена — настоящая таблица.
Мутанты: правка исходника wa_agent_model.py в памяти; мутант обязан уронить хотя бы один случай."""

import json
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

try:                                       # spend_ledger импортирует fcntl (только Linux): на ПК — имя модуля на время
    import fcntl  # noqa: F401              # импорта; цена — НАСТОЯЩАЯ таблица PRICE_PER_MTOK, учёт — подменён ниже
    import spend_ledger                    # noqa: E402
except ImportError:
    sys.modules["fcntl"] = types.SimpleNamespace(LOCK_EX=2, LOCK_SH=1, LOCK_UN=8, LOCK_NB=4, flock=lambda *a: None)
    import spend_ledger                    # noqa: E402
    del sys.modules["fcntl"]

METERED = []
spend_ledger.meter = lambda model, usage: METERED.append(                  # живой учёт трат не пишется
    (model, getattr(usage, "input_tokens", None), getattr(usage, "output_tokens", None)))

import wa_agent_model as M_REAL            # noqa: E402
import wa_agent_svc as SV                  # noqa: E402
import test_wa_agent_model as TM           # noqa: E402  — мир на подделках

MODEL_SRC = os.path.join(ROOT, "wa_agent_model.py")
EFFORTS = ("low", "medium", "high", "xhigh", "max")
CUT = "ответ модели оборван пределом токенов"
OPUS = "claude-opus-5-5"
BAIT = "sk-ПРИМАНКА-ключа-0510"             # ключ-приманка: в строку старта не попадает
OK = json.dumps({"text": "Добрый день! Подскажу.", "lang": "ru", "handoff": [], "why": "вопрос"}, ensure_ascii=False)
PLAIN = {"model", "max_tokens", "system", "messages"}          # ключи запроса без уровня — как до правки


class FakeMessages:
    """Подделка `client.messages`: пишет аргументы create, отдаёт ответ с блоком мысли и текстом."""

    def __init__(self, reply=OK, stop="end_turn", model=OPUS):
        self.kw, self.reply, self.stop, self.model = [], reply, stop, model

    def create(self, **kw):
        self.kw.append(kw)
        return types.SimpleNamespace(
            content=[types.SimpleNamespace(type="thinking", thinking="МЫСЛЬ-МОДЕЛИ"),
                     types.SimpleNamespace(type="text", text=self.reply)],
            usage=types.SimpleNamespace(input_tokens=1000, output_tokens=200, cache_creation_input_tokens=0,
                                        cache_read_input_tokens=0, cache_creation=None),
            model=self.model, stop_reason=self.stop)


def client(reply=OK, stop="end_turn"):
    return types.SimpleNamespace(messages=FakeMessages(reply, stop))


def one(M, env, **kw):
    """paid_call модуля M на подделке клиента, один вызов → (аргументы запроса, текст, usage, настройки)."""
    cl = client()
    call = M.paid_call(env=env, client=cl, **kw)
    text, use = call("СИСТЕМА", "ВОПРОС")
    assert len(cl.messages.kw) == 1, cl.messages.kw
    return cl.messages.kw[0], text, use, getattr(call, "settings", None)


def world(M, env, stop="end_turn", tools=False):
    """Мир test_wa_agent_model с адаптером модуля M, вызов — настоящий paid_call на подделке клиента."""
    keep = TM.WM
    TM.WM = M
    try:
        w = TM.World()
    finally:
        TM.WM = keep
    cl = client(OK, stop)
    w.adapter.call = M.paid_call(env=env, client=cl)
    if tools:
        w.adapter.tools = {}                                         # путь сверки: двери адаптера, моста нет
    return w, cl


# ------------------------------- п.1 уровень -------------------------------

def c_effort_set(M):
    """Уровень задан аргументом или окружением — output_config.effort через extra_body, предел 16000."""
    for lvl in EFFORTS:
        kw, _t, _u, _s = one(M, {}, effort=lvl)
        assert kw.get("extra_body") == {"output_config": {"effort": lvl}}, (lvl, kw.get("extra_body"))
        assert kw["max_tokens"] == 16000, (lvl, kw["max_tokens"])
    kw, _t, _u, s = one(M, {"WA_AGENT_EFFORT": " High ", "WA_AGENT_MODEL": OPUS})
    assert kw.get("extra_body") == {"output_config": {"effort": "high"}} and kw["model"] == OPUS, kw
    assert kw["max_tokens"] == 16000 and s["effort"] == "high", (kw["max_tokens"], s)


def c_effort_unset(M):
    """Уровня нет — запрос как был: те же четыре ключа, предел 1500, одно сообщение user; из ответа — только текст."""
    kw, text, use, s = one(M, {})
    assert set(kw) == PLAIN, sorted(kw)
    assert kw["max_tokens"] == 1500 and kw["model"] == "claude-sonnet-4-5", kw
    assert kw["messages"] == [{"role": "user", "content": "ВОПРОС"}] and kw["system"] == "СИСТЕМА", kw
    assert text == OK and "МЫСЛЬ" not in text, text                 # блок мысли в черновик не идёт
    assert use["stop"] == "end_turn" and s["effort"] is None, (use, s)
    kw, _t, _u, _s = one(M, {"WA_AGENT_MODEL": OPUS})
    assert set(kw) == PLAIN and kw["model"] == OPUS and kw["max_tokens"] == 1500, kw


def c_effort_bad(M):
    """Иное слово уровня — не шлётся (запрос без уровня, предел 1500), слово — в строке старта."""
    kw, _t, _u, s = one(M, {"WA_AGENT_EFFORT": "extreme"})
    assert set(kw) == PLAIN and kw["max_tokens"] == 1500, kw
    assert s["effort"] is None and s["effort_bad"] == "extreme", s
    words = M.settings_words(s)
    assert "уровень «extreme» не принят" in words and "не шлётся" in words, words
    kw, _t, _u, s = one(M, {"WA_AGENT_EFFORT": "high"}, effort="ultra")   # неверный аргумент — тоже не шлётся
    assert set(kw) == PLAIN and s["effort_bad"] == "ultra", (kw, s)


def c_arg_over_env(M):
    """Аргумент сильнее окружения: уровень, предел и модель."""
    kw, _t, _u, _s = one(M, {"WA_AGENT_EFFORT": "max", "WA_AGENT_MAX_TOKENS": "20000", "WA_AGENT_MODEL": "x-model"},
                         effort="low", max_tokens=8000, model_name=OPUS)
    assert kw.get("extra_body") == {"output_config": {"effort": "low"}}, kw.get("extra_body")
    assert kw["max_tokens"] == 8000 and kw["model"] == OPUS, kw


# ------------------------------- п.2 предел -------------------------------

def c_max_tokens(M):
    """Предел окружением — с уровнем и без; не принятый — умолчание и слово в строке старта."""
    kw, _t, _u, _s = one(M, {"WA_AGENT_EFFORT": "high", "WA_AGENT_MAX_TOKENS": "20000"})
    assert kw["max_tokens"] == 20000, kw["max_tokens"]
    kw, _t, _u, _s = one(M, {"WA_AGENT_MAX_TOKENS": "3000"})
    assert kw["max_tokens"] == 3000 and set(kw) == PLAIN, kw
    for bad in ("много", "0", "-5"):
        kw, _t, _u, s = one(M, {"WA_AGENT_EFFORT": "high", "WA_AGENT_MAX_TOKENS": bad})
        assert kw["max_tokens"] == 16000 and s["tokens_bad"] == bad, (bad, kw["max_tokens"], s)
        assert "«%s» не принят" % bad in M.settings_words(s), M.settings_words(s)


# ------------------------------- п.3 обрыв пределом -------------------------------

def c_cut_no_draft(M):
    """stop_reason max_tokens — черновика нет, причина в журнале; карточки нет; цена вызова учтена.
    Обрывок нарочно разбирается (целый JSON): правило судит stop_reason, а не разбор."""
    w, cl = world(M, {"WA_AGENT_MODEL": OPUS, "WA_AGENT_EFFORT": "high"}, stop="max_tokens")
    w.ask("Привет")
    assert len(cl.messages.kw) == 1 and cl.messages.kw[0]["max_tokens"] == 16000, cl.messages.kw
    assert w.drafts() == [], w.drafts()
    assert any(CUT in ln for ln in w.lines), [ln for ln in w.lines if "модель" in ln]
    assert w.http.of("sendMessage") == [], w.http.of("sendMessage")
    assert w.adapter.spend["calls"] == 1, w.adapter.spend


def c_cut_tools_no_draft(M):
    """Путь сверки (WA_AGENT_TOOLS): итог сверки оборван пределом — черновика нет, та же причина."""
    w, _cl = world(M, {"WA_AGENT_EFFORT": "high"}, stop="max_tokens", tools=True)
    w.ask("Привет")
    assert w.drafts() == [], w.drafts()
    assert any(CUT in ln for ln in w.lines), [ln for ln in w.lines if "модель" in ln or "сверк" in ln]


def c_not_cut_draft(M):
    """Близнец: тот же ответ, stop_reason end_turn — черновик есть, причины обрыва нет (правило не «всегда нет»)."""
    w, _cl = world(M, {"WA_AGENT_MODEL": OPUS, "WA_AGENT_EFFORT": "high"}, stop="end_turn")
    w.ask("Привет")
    assert len(w.drafts()) == 1, w.drafts()
    assert not any(CUT in ln for ln in w.lines), [ln for ln in w.lines if CUT in ln]


# ------------------------------- п.4 цена -------------------------------

def c_price(M):
    """Цена: opus-5-5 $4/$20, sonnet-5-5 $2/$10 за млн; sonnet-5 по-прежнему $3/$15; вызов через адаптер — строкой
    журнала по цене opus-5-5 (вход 1000, выход 200 → $0.0080) и в учёт трат под именем модели."""
    c = spend_ledger.cost_usd
    assert (c(OPUS, 1_000_000, 0), c(OPUS, 0, 1_000_000)) == (4.0, 20.0), (c(OPUS, 1_000_000, 0), c(OPUS, 0, 1_000_000))
    assert (c("claude-sonnet-5-5", 1_000_000, 0), c("claude-sonnet-5-5", 0, 1_000_000)) == (2.0, 10.0)
    assert (c("claude-sonnet-5", 1_000_000, 0), c("claude-sonnet-5", 0, 1_000_000)) == (3.0, 15.0)
    assert abs(M.cost_of(OPUS, {"in": 1_000_000, "out": 1_000_000})["usd"] - 24.0) < 1e-9
    del METERED[:]
    w, _cl = world(M, {"WA_AGENT_MODEL": OPUS, "WA_AGENT_EFFORT": "high"})
    w.ask("Привет")
    line = [ln for ln in w.lines if ln.startswith("черновик: цена:")]
    assert line and "вход 1000" in line[0] and "выход 200" in line[0] and "$0.0080" in line[0], line
    assert METERED and METERED[-1][0] == OPUS, METERED


# ------------------------------- п.5 строка старта -------------------------------

def c_start_line(M):
    """Строка старта службы: модель, уровень и предел; не принятый уровень — словами; адаптера нет — словами; ключ
    из настроек в строки старта не попадает."""
    head = "модель (WA_AGENT_MODEL, WA_AGENT_EFFORT, WA_AGENT_MAX_TOKENS): "
    for env, want in (
            ({"WA_AGENT_MODEL": OPUS, "WA_AGENT_EFFORT": "high", "ANTHROPIC_API_KEY": BAIT},
             head + OPUS + " · уровень high (output_config.effort) · предел 16000 токенов на мысли и текст"),
            ({"WA_AGENT_MODEL": OPUS, "WA_AGENT_EFFORT": "turbo", "ANTHROPIC_API_KEY": BAIT},
             head + OPUS + " · уровень «turbo» не принят (low, medium, high, xhigh, max) — не шлётся, запрос без "
             "уровня · предел 1500 токенов"),
            ({"ANTHROPIC_API_KEY": BAIT},
             head + "claude-sonnet-4-5 · уровень не задан — запрос без уровня, как раньше · предел 1500 токенов")):
        w, _cl = world(M, env)
        lines = []
        env_svc = {"queue_db": w.qpath, "agent_db": os.path.join(os.path.dirname(w.qpath), "svc.db")}
        SV.build(env_svc, environ={}, model=w.adapter, line=lines.append)
        assert want in lines, [ln for ln in lines if ln.startswith("модель")]
        assert not any(BAIT in ln for ln in lines), "ключ в строке старта"
    lines = []
    env_svc = {"queue_db": w.qpath, "agent_db": os.path.join(os.path.dirname(w.qpath), "svc2.db")}
    SV.build(env_svc, environ={}, model=None, line=lines.append)
    assert "модель: адаптера нет — модель не зовётся" in lines, [ln for ln in lines if ln.startswith("модель")]


CASES = [c_effort_set, c_effort_unset, c_effort_bad, c_arg_over_env, c_max_tokens, c_cut_no_draft,
         c_cut_tools_no_draft, c_not_cut_draft, c_price, c_start_line]


# ------------------------------- мутанты: одно правило — одна правка -------------------------------

MUTANTS = [
    ("уровень не передан",
     '    more = {"extra_body": {"output_config": {"effort": s["effort"]}}} if s["effort"] else {}\n',
     "    more = {}\n"),
    ("предел не поднят", "MAX_TOKENS_EFFORT = 16000\n", "MAX_TOKENS_EFFORT = MAX_TOKENS\n"),
    ("обрыв не пойман", "        if stop != STOP_CUT:\n            return False\n",
     "        if True:\n            return False\n"),
]


def module(src, name, path):
    mod = types.ModuleType(name)
    mod.__file__ = path
    exec(compile(src, name + ".py", "exec"), mod.__dict__)        # noqa: S102 — мутант собственного исходника
    return mod


def run_cases(M):
    fails = []
    for c in CASES:
        try:
            c(M)
        except Exception as e:                                       # noqa: BLE001 — падение мутанта = поимка
            fails.append((c.__name__, "%s: %s" % (type(e).__name__, str(e)[:300])))
    return fails


def main():
    M = M_REAL
    try:
        w, _cl = world(M, {"WA_AGENT_MODEL": OPUS, "WA_AGENT_EFFORT": "high"})
        print("строка старта: %s" % SV.model_line(w.adapter))
    except Exception as e:                                           # noqa: BLE001
        print("строка старта: прогон упал — %s: %s" % (type(e).__name__, str(e)[:200]))
    fails = run_cases(M)
    for c in CASES:
        f = [x for x in fails if x[0] == c.__name__]
        print(("FAIL %s %s" % (c.__name__, f[0][1])) if f else "PASS %s" % c.__name__)
    print("ИТОГ %d/%d" % (len(CASES) - len(fails), len(CASES)))
    with open(MODEL_SRC, encoding="utf-8") as fh:
        src = fh.read()
    killed = 0
    for i, (rule, old, new) in enumerate(MUTANTS, 1):
        if src.count(old) != 1:
            print("мутант %d «%s»: не применим — якорь найден %d раз" % (i, rule, src.count(old)))
            continue
        fs = run_cases(module(src.replace(old, new), "wa_agent_model_mut%d" % i, MODEL_SRC))
        killed += bool(fs)
        print("мутант %d «%s»: упало %d из %d%s — %s" % (i, rule, len(fs), len(CASES), "" if fs else "  ← ВЫЖИЛ",
                                                       ", ".join(n for n, _ in fs)))
    print("мутантов %d — поймано %d" % (len(MUTANTS), killed))
    return 1 if fails or killed < len(MUTANTS) else 0


if __name__ == "__main__":
    sys.exit(main())
