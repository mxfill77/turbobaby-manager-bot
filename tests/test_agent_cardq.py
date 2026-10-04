# -*- coding: utf-8 -*-
"""WACARDQ0410: карточка черновика в «Агентах» показывает вопрос клиента; вопрос не по-русски — ещё перевод вопроса и
ответа на русский с пометкой «перевод для сотрудника, клиенту не уходит». Клиенту — только ответ, как раньше.

Повод — слова владельца 04.10 в 23:52 о черновике №10: дублировать вопрос клиента в карточке; язык другой — там же
вопрос и предполагаемый ответ на русском. Вопрос — блок последних реплик клиента, что ушёл в модель (под маской), а не
пересказ модели; язык — кодом (`K.lang_of`), не полем lang модели; перевод хранится с версией и её текстом.

Случаи — сквозь живой адаптер, ядро и руки Telegram на подделках test_wa_agent_model (модель, мост, Bot API, дверь
отправки; сети и модели нет). Мутанты: правка исходника wa_agent.py или wa_agent_model.py в памяти, мутант обязан
уронить хотя бы один случай."""

import json
import os
import re
import sqlite3
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

try:                                       # spend_ledger импортирует fcntl (только Linux): на ПК — подмена цены
    import fcntl  # noqa: F401
except ImportError:
    sys.modules.setdefault("spend_ledger", types.SimpleNamespace(cost_usd=lambda model, i, o: 0.0,
                                                                 meter=lambda *a, **k: None))

import wa_agent as A_REAL                  # noqa: E402
import wa_agent_model as M_REAL            # noqa: E402
import wa_agent_tg as G                    # noqa: E402
import test_wa_agent_model as TM           # noqa: E402  — мир на подделках

SRC = {"A": os.path.join(ROOT, "wa_agent.py"), "M": os.path.join(ROOT, "wa_agent_model.py")}
Q_RU = "Здравствуйте, а шлем дадите?"
Q_EN = "Hi, do you give a helmet with the bike?"
A_RU = "Добрый день! Да, шлем даём бесплатно."
A_EN = "Hi! Yes, a helmet comes free with the bike."
TR_Q = "ПЕРЕВОД-ВОПРОСА: Привет, вы даёте шлем к байку?"
TR_A = "ПЕРЕВОД-ОТВЕТА: Привет! Да, шлем идёт бесплатно."
WHY = "ПЕРЕСКАЗ-МОДЕЛИ: клиент спросил о шлеме"


def reply(text, lang, q_ru=None, text_ru=None):
    d = {"text": text, "lang": lang, "handoff": [], "why": WHY}
    if q_ru is not None:
        d["q_ru"] = q_ru
    if text_ru is not None:
        d["text_ru"] = text_ru
    return json.dumps(d, ensure_ascii=False)


def world(mods, rep, tools=False):
    """Мир TM на модулях случая (настоящих или мутанта)."""
    keep = (TM.A, TM.WM)
    TM.A, TM.WM = mods["A"], mods["M"]
    try:
        w = TM.World(reply=rep)
    finally:
        TM.A, TM.WM = keep
    if tools:
        w.adapter.tools = {}               # режим со сверкой (AGENTLOOPA0310): T.run, итог — обычный JSON
    return w


def cards(w):
    return [p for p in w.http.of("sendMessage") if "reply_markup" in p]


def card_id(w, did=1):
    return w.core.db.execute("SELECT card_id FROM drafts WHERE id=?", (did,)).fetchone()[0]


def asked_block(user):
    """Последний блок промпта — то, что ушло в модель как вопрос клиента."""
    return user.rsplit("(на это и отвечай):\n", 1)[1]


# ------------------------------- случаи задания (п.4) -------------------------------

def c_russian_only_question(mods):
    """Русский вопрос — над ответом только вопрос; переводов нет, даже если модель их дала и назвала язык «en»."""
    w = world(mods, reply(A_RU, "en", TR_Q, TR_A))
    w.ask(Q_RU)
    user = w.call.calls[0][1]
    assert M_REAL.TR_BLOCK not in user, user[-400:]                  # русский — промпт без просьбы перевода
    t = cards(w)[-1]["text"]
    assert G.W_Q_HEAD + "\n" + Q_RU in t and G.W_A_HEAD + "\n" + A_RU in t, t
    assert t.index(Q_RU) < t.index(A_RU), t                           # вопрос НАД ответом
    assert "перевод" not in t and "ПЕРЕВОД" not in t, t
    assert w.core.db.execute("SELECT COUNT(*) FROM draft_tr").fetchone()[0] == 0
    w.press("wa:send:1:1", card_id(w))
    assert w.door.sends == [(TM.NUM, A_RU)], w.door.sends            # клиенту — ровно ответ


def c_question_is_masked_tail(mods):
    """П2: вопрос на карточке — ровно последний блок промпта (реплики клиента под маской), а не пересказ модели."""
    w = world(mods, reply(A_RU, "ru"))
    w.put(TM.T0 - 5, "Добрый день")
    w.ask("пароль от wifi: Qwerty12345zz, а шлем дадите?")
    user = w.call.calls[0][1]
    sent = asked_block(user)
    assert "Добрый день" in sent and "[скрыто: пароль]" in sent and "Qwerty12345zz" not in sent, sent
    t = cards(w)[-1]["text"]
    assert G.W_Q_HEAD + "\n" + sent + "\n\n" + G.W_A_HEAD in t, t
    assert "Qwerty12345zz" not in t and WHY not in t, t
    assert w.core.db.execute("SELECT question FROM drafts WHERE id=1").fetchone()[0] == sent


def c_english_question_both_translations(mods):
    """Английский вопрос — вопрос, ответ и оба перевода с пометкой; язык решает код, а модель назвала «ru»."""
    w = world(mods, reply(A_EN, "ru", TR_Q, TR_A))
    w.ask(Q_EN)
    user = w.call.calls[0][1]
    assert M_REAL.TR_BLOCK in user, user[-600:]                       # просьба перевода — тем же вызовом
    assert len(w.call.calls) == 1, len(w.call.calls)
    t = cards(w)[-1]["text"]
    assert t.index(Q_EN) < t.index(A_EN) < t.index(G.W_TR_HEAD), t
    assert "перевод для сотрудника, клиенту не уходит" in t, t
    assert G.W_TR_Q + TR_Q in t and G.W_TR_A + TR_A in t, t
    w.press("wa:send:1:1", card_id(w))
    assert w.door.sends == [(TM.NUM, A_EN)], w.door.sends            # переводы клиенту не уходят


def c_no_translation(mods):
    """Английский вопрос, модель перевода не дала — строка «перевода нет: модель не дала»."""
    w = world(mods, reply(A_EN, "en"))
    w.ask(Q_EN)
    t = cards(w)[-1]["text"]
    assert "перевода нет: модель не дала" in t and G.W_TR_HEAD not in t, t
    assert G.W_Q_HEAD + "\n" + Q_EN in t, t


def c_version_2(mods):
    """Версия человека: перевод — к версии 1, на карточке версии 2 его текста нет; «Отправить» шлёт текст человека."""
    w = world(mods, reply(A_EN, "en", TR_Q, TR_A))
    w.ask(Q_EN)
    v1 = cards(w)[-1]
    assert TR_A in v1["text"], v1["text"]
    w.reply(card_id(w), "Hello! Helmet is included, see you tomorrow.")
    v2 = cards(w)[-1]
    assert "версия 2" in v2["text"] and "перевод — к версии 1" in v2["text"], v2["text"]
    assert TR_A not in v2["text"] and TR_Q not in v2["text"], v2["text"]
    assert G.W_Q_HEAD + "\n" + Q_EN in v2["text"], v2["text"]        # вопрос тот же — он над ответом и тут
    w.press("wa:send:1:2", card_id(w))
    assert w.door.sends == [(TM.NUM, "Hello! Helmet is included, see you tomorrow.")], w.door.sends


def c_long_question_cut_order(mods):
    """Длинный вопрос: резка по порядку — подробности, переводы, вопрос; ответ не режется никогда."""
    top, notes, details = "T", "N" * 100, "D" * 300
    answer, q = "A" * 900, "Q" * 1500
    tr = (G.W_TR_HEAD, "вопрос: " + "R" * 700 + "\nответ: " + "S" * 600)
    full = len(G.card_texts(top, answer, notes, "", room=10 ** 6, question=q, trans=tr)[0])
    # (а) не влезают только подробности — режутся они, перевод и вопрос целы
    t = G.card_texts(top, answer, notes, details, room=full + 100, question=q, trans=tr)
    assert len(t) == 1 and "скрыто знаков подробностей" in t[0] and tr[1] in t[0] and q in t[0], t[0][-200:]
    # (б) меньше места — подробности скрыты, перевод урезан с числом скрытых, вопрос цел
    t = G.card_texts(top, answer, notes, details, room=full - 400, question=q, trans=tr)[0]
    m = re.search(r"скрыто знаков перевода: (\d+)", t)
    assert "подробности скрыты" in t and m and q in t and answer in t, t[-300:]
    assert t.count("R") + t.count("S") + int(m.group(1)) == 1300, (t.count("R"), t.count("S"), m.group(1))
    # (в) ещё меньше — перевод не поместился, вопрос урезан с числом скрытых, ответ цел
    t = G.card_texts(top, answer, notes, details, room=full - 2000, question=q, trans=tr)[0]
    m = re.search(r"скрыто знаков вопроса: (\d+)", t)
    assert "перевод не поместился" in t and m and answer in t, t[-300:]
    assert t.count("Q") + int(m.group(1)) == len(q) and len(t) <= full - 2000, (t.count("Q"), m.group(1))
    # (г) ответ длиннее сообщения — отдельно и целиком, вопрос над ним, карточка с переводом и в пределе
    big = "Б" * 6000
    many = G.card_texts(top, big, notes, details, question=q, trans=tr)
    first = many[0]
    m = re.search(r"скрыто знаков вопроса: (\d+)", first)                 # над ответом — не длиннее Q_SPLIT_MAX
    assert first.index(G.W_Q_HEAD) < first.index("Б") and m and first.count("Q") + int(m.group(1)) == len(q), \
        first[:200]
    assert big in "".join(many[:-1]).split(G.W_A_LEAD_Q, 1)[1], [len(x) for x in many]
    assert tr[1] in many[-1] and all(len(x) <= G.TG_TEXT_MAX for x in many) and len(many[-1]) <= G.CARD_ROOM
    # сквозь живой путь: вопрос 3500 знаков — карточка в пределе, ответ целиком, вопрос урезан с числом
    w = world(mods, reply(A_EN, "en", TR_Q, TR_A))
    longq = ("Please tell me about the bike rental terms and the helmet. " * 60)[:3500]
    w.ask(longq)
    c = cards(w)[-1]["text"]
    m = re.search(r"скрыто знаков вопроса: (\d+)", c)
    assert len(c) <= G.CARD_ROOM and A_EN in c and m, (len(c), c[-300:])
    assert c.split(G.W_Q_HEAD + "\n", 1)[1].split("…\n(скрыто", 1)[0] == longq[:len(longq) - int(m.group(1))]


def c_both_model_modes(mods):
    """Режим со сверкой (инструменты) — то же: вопрос, оба перевода, клиенту только ответ."""
    w = world(mods, reply(A_EN, "ru", TR_Q, TR_A), tools=True)
    w.ask(Q_EN)
    assert w.adapter.last.get("tools") is not None, w.adapter.last.keys()
    assert M_REAL.TR_BLOCK in w.call.calls[0][1]
    t = cards(w)[-1]["text"]
    assert G.W_Q_HEAD + "\n" + Q_EN in t and G.W_TR_Q + TR_Q in t and G.W_TR_A + TR_A in t, t
    w.press("wa:send:1:1", card_id(w))
    assert w.door.sends == [(TM.NUM, A_EN)], w.door.sends
    # и одним вызовом — русский: только вопрос
    w2 = world(mods, reply(A_RU, "en", TR_Q, TR_A), tools=True)
    w2.ask(Q_RU)
    t2 = cards(w2)[-1]["text"]
    assert G.W_Q_HEAD + "\n" + Q_RU in t2 and "перевод" not in t2, t2


class OldModel:
    """Прежний контракт адаптера: словарь без вопроса — черновик «старый», вопроса у ядра нет."""

    def draft(self, number, upto_id):
        return {"text": A_EN, "handoff": [], "lang": "en", "why": WHY}


def c_old_draft_without_translation(mods):
    """Старый черновик: вопроса и перевода нет — карточка прежняя байт-в-байт, «Отправить» шлёт ответ; база старой
    формы получает столбцы добавлением."""
    w = world(mods, reply(A_EN, "en"))
    w.core.model = OldModel()
    w.ask(Q_EN)
    t = cards(w)[-1]["text"]
    assert t.split("\n\n")[1] == A_EN and G.W_Q_HEAD not in t and "перевод" not in t, t
    assert w.core.card_extra(1, 1, A_EN) is None
    w.press("wa:send:1:1", card_id(w))
    assert w.door.sends == [(TM.NUM, A_EN)], w.door.sends
    # база до правки: drafts без question/q_lang, draft_tr нет — ядро только добавляет
    d = tempfile.mkdtemp(prefix="wa_cardq_old_")
    db = sqlite3.connect(os.path.join(d, "agent.db"))
    db.execute("CREATE TABLE drafts (id INTEGER PRIMARY KEY AUTOINCREMENT, number TEXT NOT NULL, state TEXT NOT NULL, "
               "ver INTEGER NOT NULL DEFAULT 1, text TEXT NOT NULL, upto_id INTEGER NOT NULL, created_at REAL NOT NULL,"
               " decided_by TEXT, decided_at REAL, reason TEXT, wamid TEXT, card_id INTEGER, closed_at REAL)")
    db.execute("INSERT INTO drafts(number, state, ver, text, upto_id, created_at) VALUES(?,?,?,?,?,?)",
               (TM.NUM, "pending", 1, "старый ответ", 1, TM.T0))
    db.commit()
    db.close()
    core = mods["A"].Core(os.path.join(d, "agent.db"), w.qpath, OldModel(), None, TM.FakeDoor(), clock=lambda: TM.T0)
    cols = {r[1] for r in core.db.execute("PRAGMA table_info(drafts)")}
    assert {"question", "q_lang", "handoff", "ctx"} <= cols, cols
    assert core.db.execute("SELECT text FROM drafts WHERE id=1").fetchone()[0] == "старый ответ"
    assert core.card_extra(1, 1, "старый ответ") is None
    assert core.db.execute("SELECT COUNT(*) FROM draft_tr").fetchone()[0] == 0


CASES = [c_russian_only_question, c_question_is_masked_tail, c_english_question_both_translations, c_no_translation,
         c_version_2, c_long_question_cut_order, c_both_model_modes, c_old_draft_without_translation]


# ------------------------------- мутанты: одно правило — одна правка -------------------------------

MUTANTS = [
    ("отправка тела карточки", "A",
     "        try:\n            res = self.door.send_text(number, text) or {}\n",
     "        try:\n"
     "            res = self.door.send_text(number, (self.db.execute(\"SELECT body FROM tg_cards WHERE draft_id=? \"\n"
     "                \"ORDER BY card_id DESC\", (draft_id,)).fetchone() or [text])[0]) or {}\n"),
    ("язык по полю модели", "M", "    lang = info[\"q_lang\"]\n", "    lang = got.get(\"lang\") or None\n"),
    ("перевод на версии 2", "A", "        if r_ver == int(ver) and a_sha == text_sha(text):\n", "        if True:\n"),
    ("вопрос из текста модели", "M", "    question = info[\"question\"]\n",
     "    question = got.get(\"why\") or info[\"question\"]\n"),
]


def module(src, name, path):
    mod = types.ModuleType(name)
    mod.__file__ = path
    exec(compile(src, name + ".py", "exec"), mod.__dict__)        # noqa: S102 — мутант собственного исходника
    return mod


def run_cases(mods):
    fails = []
    for c in CASES:
        try:
            c(mods)
        except Exception as e:                                       # noqa: BLE001 — падение мутанта = поимка
            fails.append((c.__name__, "%s: %s" % (type(e).__name__, str(e)[:200])))
    return fails


def mutant_kills():
    srcs = {}
    for k, p in SRC.items():
        with open(p, encoding="utf-8") as fh:
            srcs[k] = fh.read()
    out = []
    for i, (rule, which, old, new) in enumerate(MUTANTS, 1):
        assert srcs[which].count(old) == 1, "мутант %d не применился (%s): %r" % (i, rule, old)
        mods = {"A": A_REAL, "M": M_REAL}
        mods[which] = module(srcs[which].replace(old, new), "cardq_mut%d" % i, SRC[which])
        out.append((i, rule, run_cases(mods)))
    return out


def main():
    fails = run_cases({"A": A_REAL, "M": M_REAL})
    for c in CASES:
        f = [x for x in fails if x[0] == c.__name__]
        print(("FAIL " + f[0][1]) if f else "PASS", c.__name__)
    print("случаи: %d/%d" % (len(CASES) - len(fails), len(CASES)))
    killed = 0
    for i, rule, fs in mutant_kills():
        killed += bool(fs)
        print("мутант %d «%s»: упало %d из %d%s — %s" % (i, rule, len(fs), len(CASES), "" if fs else "  ← ВЫЖИЛ",
                                                       ", ".join(n for n, _ in fs)))
    print("мутантов %d — поймано %d" % (len(MUTANTS), killed))
    return 1 if fails or killed < len(MUTANTS) else 0


if __name__ == "__main__":
    sys.exit(main())
