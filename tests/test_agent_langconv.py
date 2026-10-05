# -*- coding: utf-8 -*-
"""WALANGCONVB0510: язык разговора считает код, а не модель по одной фразе (№21 v2 05.10).

Повод — №21 v2 (05.10 16:56): разговор шёл по-русски, последняя фраза клиента — по-английски, ответ ушёл английским:
правило 3 отдавало выбор языка модели, а модель смотрела на одну фразу. Теперь: (1) `conversation_lang` — `K.lang_of`
по последним CONV_LAST сообщениям клиента с буквами, большинство, ничья — язык самого нового, букв нет — неизвестен;
(2) строка «ЯЗЫК РАЗГОВОРА: …» в сообщении модели (только русский и английский); (3) правило 3 велит писать на языке
этой строки; (4) проверка ответа в обоих путях черновика — язык текста не тот, что в разговоре, — причина
`K.LANG_CONV_WORDS`; «Отправить» не запирается, текст не правится.

Случаи — сквозь живой адаптер, ядро и руки Telegram на подделках test_wa_agent_model (модель, мост, Bot API, дверь
отправки; сети и модели нет). №21 — синтетикой: три русских сообщения клиента с нашими ответами между ними, последняя
фраза — английская. Мутанты: правка исходника wa_agent_model.py в памяти, мутант обязан уронить хотя бы один случай.
WA_AGENT_SRC=<каталог> подменяет модули (прогон на базе)."""

import json
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
if os.environ.get("WA_AGENT_SRC"):
    sys.path.insert(0, os.environ["WA_AGENT_SRC"])

try:                                       # spend_ledger импортирует fcntl (только Linux): на ПК — подмена цены
    import fcntl  # noqa: F401
except ImportError:
    sys.modules.setdefault("spend_ledger", types.SimpleNamespace(cost_usd=lambda model, i, o: 0.0,
                                                                 meter=lambda *a, **k: None))

import wa_agent_knowledge as K             # noqa: E402,F401
import wa_agent_model as M_REAL            # noqa: E402
import wa_agent_tg as G                    # noqa: E402
import test_wa_agent_model as TM           # noqa: E402  — мир на подделках

MODEL_SRC = os.path.join(os.path.dirname(os.path.abspath(M_REAL.__file__)), "wa_agent_model.py")
# литералами: на базе констант нет — случай падает своей проверкой, а не импортом всего набора
LANG = "язык ответа не тот, что в разговоре — проверьте"
LINE_RU = "ЯЗЫК РАЗГОВОРА: русский (%d из %d последних сообщений клиента)"
LINE_EN = "ЯЗЫК РАЗГОВОРА: английский (%d из %d последних сообщений клиента)"
LOG = "модель: язык ответа"
RULE3 = ("3. Пиши на языке из строки «ЯЗЫК РАЗГОВОРА» — её посчитал код по последним сообщениям клиента; одна фраза "
         "клиента на другом языке язык разговора не меняет. Строки нет — пиши на языке клиента: русский или английский.")

# №21 синтетикой (выдумано, форма живого входа): разговор по-русски, последняя фраза — по-английски
CONV_21 = [("in", "Здравствуйте, хочу взять скутер"), ("echo", "Добрый день! Какую модель смотрите?"),
           ("in", "NMAX, на неделю"), ("echo", "Хорошо, уточню наличие."),
           ("in", "А доставка есть?"), ("echo", "Да, по Пхукету бесплатно от 3 суток.")]
ASK_21 = "Ok, how much for tomorrow?"
EN_ANSWER = "Hello! Sure, my colleague will check the NMAX and get back to you with the exact price."
RU_ANSWER = "Здравствуйте! Коллега проверит NMAX и вернётся к вам с точной ценой."
CONV_EN = [("in", "Hi, I want to rent a scooter"), ("echo", "Hello! Which model are you looking for?")]
ASK_EN = "How much is the NMAX?"


def reply(text, lang="ru", handoff=None):
    return json.dumps({"text": text, "lang": lang, "handoff": list(handoff or []), "why": "язык"},
                      ensure_ascii=False)


def run(M, conv, q, text, lang="ru", tools=False):
    """Переписка conv (клиент «in» и наши «echo» по минуте), фраза клиента q + ответ подделки модели сквозь адаптер M →
    (промпт user, причины, кнопки карточки, текст карточки, журнал)."""
    keep = TM.WM
    TM.WM = M                              # мир строит адаптер из модуля под случаем (настоящий или мутант)
    try:
        w = TM.World(reply=reply(text, lang))
    finally:
        TM.WM = keep
    if tools:
        w.adapter.tools = {}               # путь со сверкой (AGENTLOOPA0310): T.run, итог — обычный JSON
    if conv:
        for i, (kind, t) in enumerate(conv):
            w.put(TM.T0 - 3000 + i * 60, t, kind=kind)
        w.core.tick(TM.T0 - 100)           # эхо ставит паузу — снимаем её «Продолжить»
        w.core.resume(TM.NUM, 1, "тест")
    w.ask(q)
    d = w.drafts()
    assert len(d) == 1, d
    hand = json.loads(d[0][4]) if d[0][4] else []
    cards = [p for p in w.http.of("sendMessage") if "reply_markup" in p]
    assert cards, w.http.of("sendMessage")
    user = w.call.calls[0][1]
    return user, hand, TM.buttons(cards[-1]), cards[-1]["text"], w.lines


def logged(lines):
    return [x for x in lines if x.startswith(LOG)]


# ------------------------------- случаи задания (п.1) -------------------------------

def c_21_ru_conv_en_answer_caught(M):
    """№21: три русских сообщения клиента и английская фраза последней → строка «русский 3 из 4»; английский ответ —
    причина, на карточке пометка; перевод для карточки как был; в журнале — только языки и числа."""
    user, hand, kb, card, lines = run(M, CONV_21, ASK_21, EN_ANSWER, lang="en")
    assert LINE_RU % (3, 4) in user, user[-900:]
    assert user.index(LINE_RU % (3, 4)) < user.index("ИСТОРИЯ ПЕРЕПИСКИ"), user[-900:]   # в сообщении, перед историей
    assert "ЯЗЫК РАЗГОВОРА: английский" not in user, user[-900:]
    assert "ПЕРЕВОД ДЛЯ СОТРУДНИКА" in user, user[-900:]           # вопрос по-английски — перевод как был
    assert LANG in hand, hand
    assert "• " + LANG in card.split(G.W_HAND, 1)[1], card[-600:]
    log = logged(lines)
    assert log == ["модель: язык ответа en, язык разговора ru (3 из 4) — причина «нужен человек»"], log
    assert "NMAX" not in log[0] and "colleague" not in log[0], log


def c_21_ru_answer_clean(M):
    """№21, ответ по-русски — причины нет и в журнале строки проверки нет; строка «русский» та же."""
    user, hand, kb, _c, lines = run(M, CONV_21, ASK_21, RU_ANSWER)
    assert LINE_RU % (3, 4) in user, user[-900:]
    assert LANG not in hand, hand
    assert kb[0] == "wa:send:1:1", kb
    assert not logged(lines), lines


def c_21_tools_path_caught(M):
    """Тот же №21 путём со сверкой (`_draft_tools`): английский ответ — причина; русский — нет."""
    user, hand, kb, _c, _l = run(M, CONV_21, ASK_21, EN_ANSWER, lang="en", tools=True)
    assert LINE_RU % (3, 4) in user, user[-900:]
    assert LANG in hand and "wa:send:1:1" in kb, (hand, kb)
    _u, hand2, _kb, _c2, _l2 = run(M, CONV_21, ASK_21, RU_ANSWER, tools=True)
    assert LANG not in hand2, hand2


def c_en_client_en_answer_clean(M):
    """Клиент пишет по-английски — строка «английский 2 из 2», английский ответ без причины; русский ответ — причина."""
    user, hand, kb, _c, lines = run(M, CONV_EN, ASK_EN, EN_ANSWER, lang="en")
    assert LINE_EN % (2, 2) in user, user[-700:]
    assert "ЯЗЫК РАЗГОВОРА: русский" not in user, user[-700:]
    assert LANG not in hand and kb[0] == "wa:send:1:1", (hand, kb)
    assert not logged(lines), lines
    _u, hand2, _kb2, _c2, lines2 = run(M, CONV_EN, ASK_EN, RU_ANSWER)
    assert LANG in hand2, hand2
    assert logged(lines2) == ["модель: язык ответа ru, язык разговора en (2 из 2) — причина «нужен человек»"], lines2


def c_tie_newest_wins(M):
    """Ничья 2 на 2 — по самому новому: RU RU EN EN → «английский 2 из 4»; EN EN RU RU → «русский 2 из 4»."""
    conv = [("in", "Здравствуйте, хочу скутер"), ("echo", "Какую модель?"), ("in", "NMAX, на неделю"),
            ("echo", "Хорошо."), ("in", "Is delivery free?"), ("echo", "Yes, in Phuket from 3 days.")]
    user, hand, _kb, _c, _l = run(M, conv, "And the price?", RU_ANSWER)
    assert LINE_EN % (2, 4) in user, user[-900:]
    assert LANG in hand, hand
    conv2 = [("in", "Hi, I want a scooter"), ("echo", "Which model?"), ("in", "NMAX for a week"),
             ("echo", "Ok."), ("in", "А доставка бесплатная?"), ("echo", "Да, по Пхукету от 3 суток.")]
    user2, hand2, _kb2, _c2, _l2 = run(M, conv2, "А цена?", RU_ANSWER)
    assert LINE_RU % (2, 4) in user2, user2[-900:]
    assert LANG not in hand2, hand2


def c_no_letters_no_line(M):
    """Без букв — строки и причины нет (ответ на любом языке); другой язык — строки и проверки нет."""
    conv = [("in", "👍"), ("echo", "Здравствуйте! Чем помочь?"), ("in", "[фото]"), ("echo", "Вижу фото.")]
    for text, lang in ((EN_ANSWER, "en"), (RU_ANSWER, "ru")):
        user, hand, kb, _c, lines = run(M, conv, "123 456", text, lang=lang)
        assert "ЯЗЫК РАЗГОВОРА" not in user, user[-700:]
        assert LANG not in hand and kb[0] == "wa:send:1:1", (hand, kb)
        assert not logged(lines), lines
    user, hand, _kb, _c, lines = run(M, [("in", "สวัสดีครับ"), ("echo", "Hello!")], "ราคาเท่าไหร่ครับ", EN_ANSWER,
                                     lang="en")
    assert "ЯЗЫК РАЗГОВОРА" not in user and LANG not in hand and not logged(lines), (user[-500:], hand)
    assert M.conversation_lang(["👍", "123", "[фото]", "", None]) == (None, 0, 0)


def c_send_not_locked(M):
    """«Отправить» не заперто: при причине языка кнопка отправки версии 1 стоит первой — в обоих путях; текст ответа
    в черновике прежний."""
    for tools in (False, True):
        keep = TM.WM
        _u, hand, kb, card, _l = run(M, CONV_21, ASK_21, EN_ANSWER, lang="en", tools=tools)
        assert LANG in hand, (tools, hand)
        assert kb[0] == "wa:send:1:1", (tools, kb)
        assert EN_ANSWER in card, (tools, card[:400])
        assert TM.WM is keep


def c_rule3_both_prompts(M):
    """Правило 3 обоих вариантов инструкции — язык из строки «ЯЗЫК РАЗГОВОРА», прежний хвост про другой язык цел."""
    for p in (M.SYSTEM_PROMPT, M.SYSTEM_PROMPT_BOOK):
        line = next((x for x in p.splitlines() if x.startswith("3. ")), "")
        assert line.startswith(RULE3), line
        assert line.endswith("ответь по-английски коротко и поставь в handoff причину «язык не русский и не "
                             "английский»."), line


def c_unit_conversation_lang(M):
    """Разбор: большинство последних CONV_LAST с буквами, ничья — самое новое, метки не слова, строка — только ru/en."""
    cl = M.conversation_lang
    assert M.CONV_LAST == 4, M.CONV_LAST
    assert cl(["Здравствуйте", "Хочу скутер", "NMAX на неделю", "How much?"]) == ("ru", 3, 4)
    assert cl(["Здравствуйте", "Хочу скутер", "Hi there", "How much?"]) == ("en", 2, 4)          # ничья — новое
    assert cl(["Hi there", "How much?", "Здравствуйте", "Хочу скутер"]) == ("ru", 2, 4)
    # окно: пятое с конца не учитывается — без окна английский победил бы 3:2
    assert cl(["Hi there", "Hello", "How much?", "Здравствуйте", "Хочу скутер"]) == ("ru", 2, 4)
    assert cl(["Привет", "👍", "[фото]", "123"]) == ("ru", 1, 1)                                # без букв — мимо
    assert cl([]) == (None, 0, 0) and cl(None) == (None, 0, 0)
    assert M.conv_line(("ru", 3, 4)) == LINE_RU % (3, 4)
    assert M.conv_line(("en", 2, 2)) == LINE_EN % (2, 2)
    assert M.conv_line(("other", 2, 2)) == "" and M.conv_line((None, 0, 0)) == ""


CASES = [c_21_ru_conv_en_answer_caught, c_21_ru_answer_clean, c_21_tools_path_caught, c_en_client_en_answer_clean,
         c_tie_newest_wins, c_no_letters_no_line, c_send_not_locked, c_rule3_both_prompts, c_unit_conversation_lang]


# ------------------------------- мутанты: одно правило — одна правка -------------------------------

MUTANTS = [
    ("язык по последней реплике", "if lang][-CONV_LAST:]", "if lang][-1:]"),
    ("проверки нет", "if lang not in CONV_NAMES or said is None or said == lang:", "if True:"),
    ("строки нет", "        if conv_line(conv):\n            blocks.append(conv_line(conv))\n", ""),
]


def module(src, name):
    mod = types.ModuleType(name)
    mod.__file__ = MODEL_SRC
    exec(compile(src, name + ".py", "exec"), mod.__dict__)        # noqa: S102 — мутант собственного исходника
    return mod


def run_cases(M):
    fails = []
    for c in CASES:
        try:
            c(M)
        except Exception as e:                                       # noqa: BLE001 — падение мутанта = поимка
            fails.append((c.__name__, "%s: %s" % (type(e).__name__, str(e)[:200])))
    return fails


def mutant_kills():
    with open(MODEL_SRC, encoding="utf-8") as fh:
        src = fh.read()
    out = []
    for i, (rule, old, new) in enumerate(MUTANTS, 1):
        if src.count(old) != 1:                                      # база: правки нет — мутант не применим
            out.append((i, rule, None))
            continue
        out.append((i, rule, run_cases(module(src.replace(old, new), "wa_agent_model_mut%d" % i))))
    return out


def main():
    fails = run_cases(M_REAL)
    for c in CASES:
        f = [x for x in fails if x[0] == c.__name__]
        print(("FAIL %s %s" % (c.__name__, f[0][1])) if f else ("PASS " + c.__name__))
    print("ИТОГ %d/%d" % (len(CASES) - len(fails), len(CASES)))
    killed = 0
    for i, rule, fs in mutant_kills():
        if fs is None:
            print("мутант %d «%s»: не применим (правки в исходнике нет)" % (i, rule))
            continue
        killed += bool(fs)
        print("мутант %d «%s»: упало %d из %d%s — %s" % (i, rule, len(fs), len(CASES), "" if fs else "  ← ВЫЖИЛ",
                                                       ", ".join(n for n, _ in fs)))
    print("мутантов %d — поймано %d" % (len(MUTANTS), killed))
    return 1 if fails or killed < len(MUTANTS) else 0


if __name__ == "__main__":
    sys.exit(main())
