# -*- coding: utf-8 -*-
"""WAOURWORDS0410: наши прежние слова обязывают агента — правило 12 SYSTEM_PROMPT, «позднее» видно по времени строки.

Повод — WACTXLIST0410: в черновике №14 модель взяла две наши ранние реплики (00:55, 01:09) против поздней 01:30
(предложение владельца) и спорила с ней; ни промпт, ни код наше прежнее слово обязательным не делали. Правило — текстом
раздела 6 того артефакта, дословно, пунктом 12 после последнего. Время строки истории уже есть («ДД.ММ.ГГГГ ЧЧ:ММ ·
клиент|мы: …», `wa_history.model_line`), и этот набор его стережёт: без него «более позднее» модели не прочитать.

Случаи — сквозь живой `build` адаптера на подделках test_wa_agent_model (очередь, архив, мост; сети и модели нет):
сообщение модели целиком, без её вызова. Форма жизни №14 — выдуманными текстами: приветствие архива прошлого года, два
наших «по отдельности — от 5 и от 3», наше позднее «вместе — каждый от 3», вопрос клиента. Деньги (п.6 задания) —
назвать, не чинить: повтор нашего же числа проверка денег по-прежнему ставит причиной, «Отправить» на версии 1 заперто.
Мутанты — правка исходника в памяти (wa_agent_model.py, wa_history.py): без правила, без времени, обратный порядок."""

import json
import os
import re
import sqlite3
import sys
import time
import types

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

try:                                       # spend_ledger импортирует fcntl (только Linux): на ПК — подмена цены
    import fcntl  # noqa: F401
except ImportError:
    sys.modules.setdefault("spend_ledger", types.SimpleNamespace(cost_usd=lambda model, i, o: 0.0,
                                                                 meter=lambda *a, **k: None))

import wa_agent_knowledge as K             # noqa: E402
import wa_agent_model as M_REAL            # noqa: E402
import wa_history as H                     # noqa: E402
import test_wa_agent_model as TM           # noqa: E402  — мир на подделках

MODEL_SRC = os.path.join(ROOT, "wa_agent_model.py")
HIST_SRC = os.path.join(ROOT, "wa_history.py")
T0 = TM.T0                                 # 21.09.2026 21:13 по Пхукету — «сейчас» мира TM
RULE = ("12. НАШИ ПРЕЖНИЕ СЛОВА ОБЯЗЫВАЮТ. Строки «мы» в истории — уже сказанное клиенту компанией: с телефона, из "
        "темы или через «Отправить». Наше последнее предложение, условие, срок или цена о том же действуют, пока мы "
        "сами их не изменили: продолжай их, не спорь с ними и не подменяй прежними нашими словами, знаниями или своим "
        "расчётом. Два наших сообщения о том же расходятся — действует более позднее. Наше слово расходится со знаниями "
        "— клиенту не противоречь, а перенеси расхождение в handoff: «наше сообщение ЧЧ:ММ расходится с правилом …». "
        "Число, которое мы уже назвали, повторяй только к той же модели и тому же сроку; нового числа из него не "
        "выводи.")
HEAD = re.compile(r"^(\d\d)\.(\d\d)\.(\d{4}) (\d\d:\d\d) · (клиент|мы)\b", re.M)

# форма №14 — выдуманные тексты и времена (Пхукет): архив прошлого года, вопрос накануне, три наших, вопрос сейчас
T_GREET, GREET = T0 - 320 * 86400, "Здравствуйте! TurboBaby на связи. Минимальный срок аренды скутера — 5 дней."
T_ASK0, ASK0 = T0 - 6 * 3600, "Хочу ADV 350 или CB 650R, на 3 или 4 суток"
T_WE1, WE1 = T0 - 48 * 60, "ADV 350 — от 5 суток, CB 650R — от 3 суток"
T_WE2, WE2 = T0 - 34 * 60, "По отдельности: ADV 350 от 5 суток, CB 650R от 3; ADV на 2 суток нельзя"
T_WE3, WE3 = T0 - 13 * 60, "Вместе можно: оба байка, каждый от 3 суток"
T_ASK, ASK = T0, "А если CB и ADV на 2 суток вдвоём, сколько выйдет?"
MONEY_WE = "CB 650R на 3 суток — 6 223 бат"


def world(M, reply=TM.OK_JSON):
    keep = TM.WM
    TM.WM = M                              # мир строит адаптер из модуля под случаем (настоящий или мутант)
    try:
        return TM.World(reply=reply)
    finally:
        TM.WM = keep


def built(M, cache=None):
    """Форма №14 в очереди и архиве → (system, user, info) живого `build` модуля M (модель не зовётся)."""
    w = world(M)
    a = sqlite3.connect(w.apath)
    a.execute("INSERT INTO messages(number, ts, from_me, kind, text, key_id) VALUES(?,?,?,?,?,?)",
              (TM.NUM, T_GREET, 1, "text", GREET, "GREET1"))
    a.commit()
    a.close()
    w.put(T_ASK0, ASK0)
    for ts, text in ((T_WE1, WE1), (T_WE2, WE2), (T_WE3, WE3)):
        w.put(ts, text, kind="echo")        # эхо с телефона — «мы», автор не различается
    rid = w.put(T_ASK, ASK)
    ad = w.adapter
    if cache:
        ad = M.ModelAdapter(w.qpath, w.call, read_doc=w.bridge.read_doc, fleet=w.bridge.fleet, door=w.bridge.door,
                            archive_db=w.apath, clock=lambda: T0, log=w.lines.append, cache=cache)
    return ad.build(TM.NUM, rid, now=T0 + 100)


def parts(user):
    hist = user.split("ИСТОРИЯ ПЕРЕПИСКИ", 1)[1].split("КЛИЕНТ СЕЙЧАС", 1)[0]
    return hist, user.split("КЛИЕНТ СЕЙЧАС", 1)[1]


def line_of(hist, text):
    """Строка истории с текстом → (позиция, строка). Нет — AssertionError."""
    for m in re.finditer(r"^.*$", hist, re.M):
        if text in m.group(0):
            return m.start(), m.group(0)
    raise AssertionError("строки нет: %r" % text[:30])


def system_text(system):
    return system if isinstance(system, str) else system[0]["text"]


# ------------------------------- случаи -------------------------------

def c_rule_verbatim_last(M):
    """Правило 12 дословно, сразу после правила 11, в обоих вариантах инструкции; пунктов ровно 12, по порядку."""
    for p in (M.SYSTEM_PROMPT, M.SYSTEM_PROMPT_BOOK):
        assert RULE in p, p[-700:]
        nums = [int(x) for x in re.findall(r"^(\d{1,2})\. ", p.split("Ответ — РОВНО")[0], re.M)]
        assert nums == list(range(1, 13)), nums
        lines = p.splitlines()
        i = lines.index(RULE)
        assert lines[i - 1].startswith("11. ") and lines[i + 1] == "", lines[i - 1:i + 2]


def c_rule_in_system_not_user(M):
    """Сообщение модели из build: правило в системной части (без кэша и с кэшем), в сообщении пользователя его нет."""
    for cache in (None, "1h"):
        system, user, _info = built(M, cache)
        assert RULE in system_text(system), (cache, system_text(system)[-500:])
        assert "НАШИ ПРЕЖНИЕ СЛОВА" not in user, cache


def c_every_history_line_has_time(M):
    """Каждая строка истории в сообщении модели несёт дату и ЧЧ:ММ: голов столько же, сколько элементов истории."""
    _s, user, info = built(M)
    hist, _now = parts(user)
    heads = HEAD.findall(hist)
    assert len(heads) == info["history_items"] == 6, (len(heads), info["history_items"])
    assert sum(1 for h in heads if h[4] == "мы") == 4, heads


def c_later_our_word_reads_later(M):
    """Три наших сообщения дня идут по времени, и позднее (вместе — от 3) стоит последним с самым поздним ЧЧ:ММ."""
    _s, user, _i = built(M)
    hist, _now = parts(user)
    got = [line_of(hist, t) for t in (WE1, WE2, WE3)]
    for (pos, line), ts in zip(got, (T_WE1, T_WE2, T_WE3)):
        assert line.startswith(H.pk_full(ts) + " · мы: "), line[:40]
    assert got[0][0] < got[1][0] < got[2][0], [g[0] for g in got]
    hm = [g[1][11:16] for g in got]
    assert hm[0] < hm[1] < hm[2], hm


def c_archive_greeting_last_year(M):
    """Приветствие архива — первой строкой истории, «мы», с датой прошлого года против «СЕГОДНЯ»."""
    _s, user, info = built(M)
    hist, _now = parts(user)
    first = HEAD.search(hist)
    assert first and first.group(5) == "мы" and first.group(3) == str(info["today"].year - 1), \
        first and first.groups()
    _pos, line = line_of(hist, GREET)
    assert first.start() == _pos and line.startswith(H.pk_full(T_GREET) + " · мы: "), line[:40]
    assert "СЕГОДНЯ: %s" % info["today"].strftime("%d.%m.%Y") in user


def c_owner_word_in_history_not_now(M):
    """Наше позднее слово — строка истории со временем, а не «КЛИЕНТ СЕЙЧАС»; сейчас — только вопрос клиента."""
    _s, user, _i = built(M)
    hist, now = parts(user)
    assert (H.pk_full(T_WE3) + " · мы: " + WE3) in hist, hist[-300:]
    assert ASK in now and WE3 not in now and WE1 not in now, now


def c_handoff_form_matches_history(M):
    """Форма handoff правила («наше сообщение ЧЧ:ММ …») совпадает с форматом времени строк истории."""
    system, user, _i = built(M)
    assert "«наше сообщение ЧЧ:ММ расходится с правилом …»" in system_text(system)
    hist, _now = parts(user)
    assert all(re.fullmatch(r"\d\d:\d\d", h[3]) for h in HEAD.findall(hist)) and HEAD.search(hist), hist[:200]


def c_money_repeat_still_locks_send(M):
    """П.6 — назвать, не чинить: агент повторил наше же число к той же модели и сроку — проверка денег опорой его не
    считает (опора — только «ЦЕНА» этого вызова), причина первой, «Отправить» на версии 1 заперто."""
    reply = json.dumps({"text": "CB 650R на 3 суток — 6 223 бат, как мы и писали.", "lang": "ru", "handoff": [],
                           "why": "повтор нашей цены"}, ensure_ascii=False)
    w = world(M, reply)
    w.put(T0 - 3000, MONEY_WE, kind="echo")
    w.core.tick(T0 - 100)                  # эхо ставит паузу — снимаем её «Продолжить»
    w.core.resume(TM.NUM, 1, "тест")
    w.ask("а CB 650R на 3 суток сколько?")
    user = w.call.calls[0][1]
    assert (H.pk_full(T0 - 3000) + " · мы: " + MONEY_WE) in user, user[-400:]
    assert K.money_claims("CB 650R на 3 суток — 6 223 бат", None) == [("сумма", 6223)]
    d = w.drafts()
    hand = json.loads(d[0][4]) if d[0][4] else []
    assert hand and hand[0] == K.MONEY_CLAIM_WORDS, hand
    cards = [p for p in w.http.of("sendMessage") if "reply_markup" in p]
    assert cards and "wa:send:1:1" not in TM.buttons(cards[-1]), cards and TM.buttons(cards[-1])


CASES = [c_rule_verbatim_last, c_rule_in_system_not_user, c_every_history_line_has_time,
         c_later_our_word_reads_later, c_archive_greeting_last_year, c_owner_word_in_history_not_now,
         c_handoff_form_matches_history, c_money_repeat_still_locks_send]


# ------------------------------- мутанты: одно свойство — одна правка -------------------------------

MUTANTS = [
    ("без правила", "model", "\n" + RULE, ""),
    ("без времени", "hist", '    return "%s · %s: %s" % (pk_full(it["ts"]), it["who"], body or "[пусто]")\n',
     '    return "%s: %s" % (it["who"], body or "[пусто]")\n'),
    ("обратный порядок", "hist", '    text = "\\n".join(model_line(it) for it in items)\n',
     '    text = "\\n".join(model_line(it) for it in reversed(items))\n'),
]


def module(src, name, path):
    mod = types.ModuleType(name)
    mod.__file__ = path
    exec(compile(src, os.path.basename(path), "exec"), mod.__dict__)   # noqa: S102 — мутант собственного исходника
    return mod


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def mutant_module(where, old, new):
    """Модуль адаптера с мутантом в нём самом или в истории: история-мутант подставляется на время сборки адаптера."""
    msrc, hsrc = read(MODEL_SRC), read(HIST_SRC)
    src = msrc if where == "model" else hsrc
    assert src.count(old) == 1, "мутант не применился: %r" % old[:60]
    keep = sys.modules.get("wa_history")
    try:
        if where == "hist":
            sys.modules["wa_history"] = module(hsrc.replace(old, new), "wa_history", HIST_SRC)
        return module(msrc.replace(old, new) if where == "model" else msrc, "wa_agent_model_mut", MODEL_SRC)
    finally:
        sys.modules["wa_history"] = keep


def run_cases(M):
    fails = []
    for c in CASES:
        try:
            c(M)
        except Exception as e:                                       # noqa: BLE001 — падение мутанта = поимка
            fails.append((c.__name__, "%s: %s" % (type(e).__name__, str(e)[:200])))
    return fails


def main():
    t = time.time()
    fails = run_cases(M_REAL)
    for c in CASES:
        f = [x for x in fails if x[0] == c.__name__]
        print(("FAIL " + f[0][1]) if f else "PASS", c.__name__)
    print("случаи: %d/%d" % (len(CASES) - len(fails), len(CASES)))
    killed = 0
    for i, (rule, where, old, new) in enumerate(MUTANTS, 1):
        fs = run_cases(mutant_module(where, old, new))
        killed += bool(fs)
        print("мутант %d «%s»: упало %d из %d%s — %s" % (i, rule, len(fs), len(CASES), "" if fs else "  ← ВЫЖИЛ",
                                                       ", ".join(n for n, _ in fs)))
    print("мутантов %d — поймано %d (%.1f с)" % (len(MUTANTS), killed, time.time() - t))
    return 1 if fails or killed < len(MUTANTS) else 0


if __name__ == "__main__":
    sys.exit(main())
