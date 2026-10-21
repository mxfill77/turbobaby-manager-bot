#!/usr/bin/env python3
"""CSTATE1510 (вариант C): состояние дела договора для МОДЕЛИ — приёмка блока (пункты 1–4, 8–12 спецификации).

Флаг службы WA_AGENT_CONTRACT_STATE: адаптер `wa_agent_cstate.ContractStateAdapter` (наследник `ModelAdapter`, блобы
wa_agent*.py не тронуты) на каждом вызове кладёт в начало user блок фактов кода о договоре клиента из базы агента
(`read_facts`: mode=ro, точный номер) — `wa_contract_state.render`. Что ответить и какой инструмент позвать — решает модель;
PDF прикладывает и проверяет код (`wa_agent_attach`), как прежде.

Стенды. `Real` — НАСТОЯЩИЙ адаптер со сверкой Т4а: модель — сценарий (`Script`), двери договоров — подделки живого формата
`tests/test_wa_signed_card.py` (Registry, Pdfs: номер 79999966963, стр.34/35 ОТОЗВАН, стр.36 ПОДПИСАН 2026-10-14 19:04,
sha PDF36), аренда — снимок броней `Book`; ядро — `AttachCore` с карточкой подписи и ожиданием подписи в базе. `World` —
стенд подписи `test_wa_signed_card.World` (поддельная модель) с теми же параметрами ядра, что передаёт служба. Сети нет;
модель, мост, Telegram и WhatsApp не зовутся.

WA_AGENT_SRC=<каталог> подменяет модули (прогон мутантов)."""
import os
import subprocess
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
if os.environ.get("WA_AGENT_SRC"):
    sys.path.insert(0, os.environ["WA_AGENT_SRC"])

try:                                       # spend_ledger импортирует fcntl (только Linux): на ПК без заглушки — подмена цены
    import fcntl  # noqa: F401
except ImportError:
    sys.modules.setdefault("spend_ledger", types.SimpleNamespace(cost_usd=lambda model, i, o: 0.0,
                                                                 meter=lambda *a, **k: None))

PROBE_ARG = "--probe-off-imports"
PROBE_MARK = "CSTATE_OFF_MODULES "
NEW_MODULES = ("wa_agent_cstate", "wa_contract_state")


def _probe_off_imports():
    """Отдельный процесс: служба собрана БЕЗ флага WA_AGENT_CONTRACT_STATE (карточка подписи и всё прочее включены), адаптер
    модели — `make_model` прежней формы. Печатает, какие из модулей выпуска есть в процессе (обязано быть пусто)."""
    import wa_agent_svc as S
    import test_wa_attach_svc as AS
    import tempfile
    d = tempfile.mkdtemp(prefix="wa_cstate_probe_")
    bridge = types.SimpleNamespace(_call=lambda *a, **k: {"ok": False}, fleet=lambda: {"ok": False},
                                   quote_price=lambda *a: {"ok": False}, tx_find=lambda **k: {"ok": False},
                                   contract_find=lambda **k: {"ok": False}, contract_pdf=lambda f: {"ok": False},
                                   clients=lambda **k: {"ok": False})
    model, why = S.make_model({"queue_db": os.path.join(d, "q.db"), "agent_db": os.path.join(d, "a.db")},
                              bridge=bridge, call=lambda s, u: ("", {}), tools=True, book=True)
    assert type(model).__name__ == "ModelAdapter" and not hasattr(model, "cstate_on"), (type(model), why)

    class Model(AS.Model):                          # дверь аренды сверки — карточка подписи засчитывается
        def _tool_doors(self, number, upto_id):
            return {"rental": lambda: {"ok": True, "rows": []}, "history": lambda: []}
    env = dict(AS.ON, WA_AGENT_SIGNED_CARD="1")
    w = AS.World(env)
    w.model = Model()
    w.lines[:] = []
    w.build(env)
    assert type(w.core).__name__ == "AttachCore" and w.core.signed and not w.core.cstate, w.lines[-4:]
    assert not [ln for ln in w.lines if "WA_AGENT_CONTRACT_STATE" in ln], w.lines
    tables = {r[0] for r in w.core.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "contract_expect" not in tables and "signed_cards" in tables, tables
    print(PROBE_MARK + ",".join(sorted(m for m in sys.modules if m in NEW_MODULES)))


if __name__ == "__main__" and PROBE_ARG in sys.argv:
    _probe_off_imports()
    sys.exit(0)

import ast  # noqa: E402
import datetime  # noqa: E402
import re  # noqa: E402
import sqlite3  # noqa: E402
import tempfile  # noqa: E402

import wa_agent as A  # noqa: E402
import wa_agent_attach as X  # noqa: E402
import wa_agent_knowledge as K  # noqa: E402
import wa_agent_model as M  # noqa: E402
import wa_agent_tools as T  # noqa: E402
import wa_contract_state as CS  # noqa: E402
import wa_agent_cstate as C  # noqa: E402
import wa_history  # noqa: E402
import test_wa_agent_attach as AT  # noqa: E402  (подделки Telegram и двери WhatsApp, схема очереди)
import test_wa_signed_card as SC  # noqa: E402  (живые форматы стенда подписи)

NUM, T_SIGN, T_START, PDF36, SHA36 = SC.NUM, SC.T_SIGN, SC.T_START, SC.PDF36, SC.SHA36
SIGNED_AT = "2026-10-14 19:04"
HEAD0 = CS.HEAD_START                                              # «ДОГОВОР КЛИЕНТА — факты кода из базы агента»
HEAD_T = (T.TOOLS_BLOCK % T.MAX_CALLS) + "\n\n"                    # голова хода сверки Т4а перед user
DATE_ANY = re.compile(r"\d{1,4}[./-]\d{1,2}(?:[./-]\d{2,4})?")      # любая дата: в блоке — только «ДД.ММ»
FROZEN = {"wa_agent.py": "70695c7dc669f2b4d14ff7c000763b915e6121e8",       # блобы a1dcbe5 (CASEPDF1510)
          "wa_agent_model.py": "29fcf2350bbcc7a574bc6a44be67b8a71e1ddc2b",  # RCFIX2010: было 868b0c4b (free_bikes с парком снимка) · PROMPT2110: было 7c58cca9 · WAFIX2210: было b95d3a86
          "wa_agent_tools.py": "fb70716d09b8b2812c08d40f2b0d66ff18ead9e3",
          "wa_agent_knowledge.py": "34fcc7858c39f9f1c705d79f617916cbf636dda6"}  # PROMPT2110: было d338a3c2
# RCFIX2010 (20.10, класс 1 Codex TB-REVIEW-2010-1520 п.1): wa_agent_model.py перепинен (bikes= в free_bikes);
# блоб a1dcbe5 — прежний, сверка с git идёт по нему (тот же приём, что 9af5017 на срезе offer-b)
# PROMPT2110: перепинен и wa_agent_knowledge.py (голос «мы» в строках блоков) — у a1dcbe5 прежний блоб d338a3c2
AT_A1DCBE5 = dict(FROZEN, **{"wa_agent_model.py": "868b0c4b3abd75d6f4fca6b1c7021d0f121db3ce",
                             "wa_agent_knowledge.py": "d338a3c23fcfa7f8180a6ed75b38a93e6e4200d3"})


class Script:
    """Модель по сценарию: ответы по порядку, последний повторяется; `seen` — что ушло в модель (user каждого хода)."""

    def __init__(self, *answers):
        self.answers, self.seen = list(answers), []

    def __call__(self, system, user):
        import json
        self.seen.append(user)
        a = self.answers[min(len(self.seen) - 1, len(self.answers) - 1)]
        return (a if isinstance(a, str) else json.dumps(a, ensure_ascii=False)), {"in": 10, "out": 5}


def final(text, handoff=()):
    return {"text": text, "handoff": list(handoff), "lang": "ru", "why": "тест"}


def tool(name, **args):
    return {"tool": name, "args": args}


def block_of(user):
    """Блок договора — первый абзац user (строки блока разделены «\n», от остального запроса — «\n\n»)."""
    user = user[len(HEAD_T):] if user.startswith(HEAD_T) else user
    return user.split("\n\n", 1)[0] if user.startswith(HEAD0) else None


class World(SC.World):
    """Стенд подписи (поддельная модель `SC.DoorModel`) — ядро с параметрами службы: детектор просьбы (`ask_of`),
    ожидание подписи в базе (`cstate`) и детектор «подписал» (`claim_of = wa_contract_state.signed_claim`)."""

    def __init__(self, cstate=True, ask=True, claim=True, autosend=False, **kw):
        self.cstate, self.ask, self.claim, self.autosend = cstate, ask, claim, autosend
        SC.World.__init__(self, **kw)

    def new_core(self):
        return X.AttachCore(self.dbpath, self.qpath, self.model, self.tg, self.door, log=self.lines.append,
                            clock=self.clock, attach=True, pdf_fetch=self.pdfs, contract_find=self.registry,
                            signed=self.signed, signed_lookback_h=self.lookback_h,
                            ask_of=X.ask_verdict_many if self.ask else None, autosend=self.autosend,
                            cstate=self.cstate, claim_of=CS.signed_claim if self.claim else None)

    def expects(self):
        return self.q("SELECT number, opened_at, why, upto_id, due_at, checked_at, outcome, state, closed_at, closed_by "
                      "FROM contract_expect ORDER BY opened_at")

    def tables(self):
        return {r[0] for r in self.q("SELECT name FROM sqlite_master WHERE type='table'")}

    def facts(self, number=NUM, now=None):
        return C.read_facts(self.dbpath, number, self.clock.t if now is None else now)

    def block(self, number=NUM, topic=False, now=None):
        now = self.clock.t if now is None else now
        f = C.read_facts(self.dbpath, number, now)
        f["topic"] = topic
        return CS.render(f, now)

    def expect_lines(self):
        return [ln for ln in self.lines if ln.startswith("ожидание подписи:")]


class Real(SC.World):
    """НАСТОЯЩИЙ адаптер `ContractStateAdapter` со сверкой Т4а и ядро `AttachCore` (карточка подписи, детектор просьбы,
    ожидание подписи в базе). Модель — `Script`, менять — `w.script = Script(...)`."""

    def __init__(self, start=T_START, cstate=True, rows=None, media="sent", ask=True, adapter_cls=None):
        d = tempfile.mkdtemp(prefix="wa_cstate_t_")
        self.qpath, self.dbpath = os.path.join(d, "q.db"), os.path.join(d, "agent.db")
        q = sqlite3.connect(self.qpath)
        q.execute(AT.QSCHEMA)
        q.commit()
        q.close()
        self.clock = SC.Clock(start)
        self.book = SC.Book([SC.book_row()])
        self.registry = SC.Registry(rows)
        self.registry.clock = self.clock
        self.pdfs = SC.Pdfs()
        self.tg, self.door = AT.FakeTG(), AT.FakeDoor(media=media)
        self.lines, self.alines = [], []
        self.signed, self.lookback_h, self.cstate, self.ask = True, 6, cstate, ask
        self.script = Script(final("Хорошо."))
        self.adapter = self.new_adapter(adapter_cls)
        self.core = self.new_core()
        self.core.tick(start)

    def call(self, system, user):
        return self.script(system, user)

    def new_adapter(self, cls=None):
        a = (cls or C.ContractStateAdapter)(
            self.qpath, self.call, read_doc=None, book=self.book, clock=self.clock, agent_db=self.dbpath,
            log=self.alines.append, tools={"cash": lambda **kw: {"ok": False, "error": "нет"}, "contract": self.registry,
                                           "contract_pdf": self.pdfs})
        if hasattr(a, "cstate_on"):
            a.cstate_on = self.cstate
        return a

    def new_core(self):
        return X.AttachCore(self.dbpath, self.qpath, self.adapter, self.tg, self.door, log=self.lines.append,
                            clock=self.clock, attach=True, pdf_fetch=self.pdfs, contract_find=self.registry,
                            signed=True, signed_lookback_h=6, ask_of=X.ask_verdict_many if self.ask else None,
                            cstate=self.cstate, claim_of=CS.signed_claim)

    def status(self, wamid, word, ts, number=NUM):
        """Квитанция провайдера так, как её кладёт вебхук (строка очереди msg_type='status')."""
        q = sqlite3.connect(self.qpath)
        q.execute("INSERT OR IGNORE INTO wa_inbox(ts_queued, from_number, msg_type, text, ts_msg, echo, history, wamid) "
                  "VALUES(?,?,'status',?,?,1,0,?)", (ts, number, word, ts, wamid))
        q.commit()
        q.close()

    def render(self, now, number=NUM, topic=False):
        f = C.read_facts(self.dbpath, number, now)
        f["topic"] = topic
        return CS.render(f, now)


def _signed_turns(media="sent"):
    """«Подписал» (дословно 14.10), версии в базе нет; сценарий модели: contract → contract_pdf → итог."""
    w = Real(media=media)
    w.script = Script(tool("contract"), tool("contract_pdf", file_id="PDF36"),
                      final("Спасибо! Договор подписан, PDF отправим следующим сообщением."))
    w.put(T_SIGN + 60, "Подписал")
    w.tick(T_SIGN + 600)
    return w


def _signed_sent():
    """Тот же случай, человек нажал «Отправить»: текст и PDF ушли (wamid PDF — wamid.P1, 14.10 19:15)."""
    w = _signed_turns()
    out = w.core.press(1, 1, A.ACT_SEND, "Даня", T_SIGN + 700)
    assert out["ok"] and out["words"] == "текст: ушёл · PDF: ушёл", out
    return w


# ═══ 1. детектор ═══════════════════════════════════════════════════════════════════════════════════════════

CLAIMS = ("Подписал",                                              # дословно 14.10
          "Я подписала договор", "Готово, всё подписано!", "I have signed the contract", "Signed it, thanks",
          "เซ็นสัญญาแล้วครับ", "Нет-нет, я уже подписал", "ไม่ต้องห่วงครับ เซ็นแล้ว", "No worries, I've signed",
          # находка критика: вопрос о ДРУГОМ через запятую — сообщение о подписи (частая форма WhatsApp)
          "Подписал, что дальше?", "I signed it, when do you deliver?", "Signed, can you check?",
          "Договор подписан, жду PDF")
NOT_CLAIMS = ("не подписал", "где подписать?", "подпишу завтра", "Здравствуйте!", "Ещё не подписала",
              "I haven't signed yet", "Will sign tomorrow", "ยังไม่ได้เซ็น", "Пришлите подписанный договор",
              "Send me the signed contract", "Вы подписали договор?", "Добрый день, сколько стоит байк на неделю?",
              # находки критиков: тайский вопрос и отказ, переспрос, сослагательное, будущее, «signed up», «Central»
              "เซ็นแล้วหรือยัง", "เซ็นแล้วไหม", "ไม่เซ็นแล้ว", "Вы подписали, да?", "Has it been signed?",
              "Подписал бы, но ссылка не открывается", "Когда договор будет подписан",
              "Договор должен быть подписан до выдачи", "I signed up on your site", "ถึงเซ็นทรัลแล้ว")
NOT_TOPIC = ("Договорились, жду байк завтра в 10", "Договоримся на 10:00", "Подписка на новости",
             "Подпишитесь на наш канал", "How do I sign up?", "No signal here", "เจอกันที่เซ็นทรัล")


def test_1_detector_live_and_paraphrases():
    for t in CLAIMS:
        assert CS.topic(t) and CS.signed_claim(t), t
    for t in NOT_CLAIMS:
        assert not CS.signed_claim(t), t
    for t in ("А договор где?", "Где подписать?", "PDF пришлите", "Send the agreement please", "ส่งสัญญาให้หน่อย"):
        assert CS.topic(t), t
    for t in ("Здравствуйте!", "Сколько стоит байк на неделю?", "Hello, is the bike free?", "Спасибо", "", None):
        assert not CS.topic(t), t
    for t in NOT_TOPIC:                                            # тема — по слову, а не по подстроке (находка критика)
        assert not CS.topic(t), t
    for t in ("Где подписать?", "Подпишу завтра", "Нужна подпись?", "Скиньте пдфку", "Where do I sign?",
              "Договора нет", "Can I get the PDFs?"):
        assert CS.topic(t), t
    assert CS.signed_claim(None) is False and CS.topic(None) is False


def test_1_modules_pure_and_core_imports_unchanged():
    tree = ast.parse(open(CS.__file__, encoding="utf-8").read())
    imps = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            imps |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            imps.add((n.module or "").split(".")[0])
    assert imps == {"re", "datetime"}, imps
    assert CS.PHUKET.utcoffset(None).total_seconds() == A.PHUKET_OFFSET == 7 * 3600
    bad = {"open", "exec", "eval", "__import__", "input", "os", "sys", "socket", "sqlite3", "subprocess", "time"}
    used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert not (used & bad), used & bad
    # замок импортов ядра (test_wa_signed_card / test_wa_agent_attach) — прежний: детектор передаётся параметром
    tree = ast.parse(open(X.__file__, encoding="utf-8").read())
    names = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))
             for a in (n.names if isinstance(n, ast.Import) else [ast.alias(n.module or "")])}
    assert names == {"base64", "hashlib", "re", "zlib", "wa_agent", "wa_agent_tools"}, names


# ═══ 2. «Подписал», версии в базе нет → блок в голове КАЖДОГО хода; модель зовёт contract → contract_pdf ═══════════

def test_2_signed_no_version_block_in_every_turn():
    w = _signed_turns()
    seen = w.script.seen
    assert len(seen) == 3, len(seen)
    for u in seen:
        assert u.startswith(HEAD_T + HEAD0), u[:300]
        b = block_of(u)
        assert b and "• версия: в базе нет" in b, b
        assert "КЛИЕНТ СЕЙЧАС (на это и отвечай):\nПодписал" in u, "остальной запрос — прежний"
    info = w.adapter.last["info"]["cstate"]
    assert info["lines"] >= 2 and info["unread"] == [] and info["read_at"] == T_SIGN + 600, info
    a = w.attach(1)
    assert a[:7] == ("PDF36", "contract_36.pdf", len(PDF36), SHA36, 36, "D36", SIGNED_AT), a
    out = w.core.press(1, 1, A.ACT_SEND, "Даня", T_SIGN + 700)                # код прикладывает и проверяет как сейчас
    assert out["ok"] and out["words"] == "текст: ушёл · PDF: ушёл", out
    assert w.door.media == [(NUM, "document", "application/pdf", "contract_36.pdf", SHA36)], w.door.media
    assert [r["tool"] for r in w.adapter.last["tools"]["results"]] == ["contract", "contract_pdf"]


def test_2_flag_off_same_run_no_block():
    """Тот же сценарий с выключенным блоком (cstate_on=False) — ни одного хода с блоком; сведения — как у родителя."""
    w = Real(cstate=False)
    w.script = Script(tool("contract"), tool("contract_pdf", file_id="PDF36"), final("Спасибо!"))
    w.put(T_SIGN + 60, "Подписал")
    w.tick(T_SIGN + 600)
    assert len(w.script.seen) == 3 and not any(HEAD0 in u for u in w.script.seen)
    assert "cstate" not in w.adapter.last["info"], "выкл — сведения прежние"
    assert "contract_expect" not in {r[0] for r in w.q("SELECT name FROM sqlite_master WHERE type='table'")}
    assert w.attach(1)[0] == "PDF36", "PDF прикладывает код, как прежде"


# ═══ 3. «А договор где?», версия подписана, PDF ушёл и прочитан → блок это называет, нового вложения нет ═════════════

def test_3_where_is_contract_sent_and_read():
    w = _signed_sent()
    w.status("wamid.P1", "read", T_SIGN + 800)
    w.tick(T_SIGN + 900)                                           # такт собирает статусы частей (STATUS_EVERY)
    assert w.q("SELECT status FROM part_status WHERE wamid='wamid.P1'") == [("read",)]
    text = "Договор уже у вас в WhatsApp, вы его открывали."
    w.script = Script(final(text))
    w.put(T_SIGN + 1000, "А договор где?")
    w.tick(T_SIGN + 1600)
    assert len(w.script.seen) == 1, "модель ответила без инструмента"
    b = block_of(w.script.seen[0])
    assert b, w.script.seen[0][:400]
    assert "• версия: подписан 14.10 19:04 · doc …D36 · сверка ответа" in b, b
    assert "• PDF клиенту: ушёл 19:15; отправил: сотрудник" in b, b
    assert "• WhatsApp: прочитан 19:17 (статус провайдера)" in b, b
    assert "Даня" not in b and NUM not in b and "А договор где" not in b, b
    d = w.q("SELECT id, state, text FROM drafts ORDER BY id")
    assert d[-1][1] == A.PENDING and d[-1][2] == text, d
    assert w.attach(d[-1][0])[0] is None, "нового вложения нет"
    assert len(w.door.media) == 1 and len(w.door.sends) == 1 and w.signed_drafts() == []
    words, _fig = T.judge(text, None, [], T.Journal("0"))                # судья пропускает
    assert words == [], words
    assert w.adapter.last["tools"]["results"] == [] and w.adapter.last["tools"]["state"] == T.DONE


# ═══ 4. PDF не ушёл / не дошёл ═════════════════════════════════════════════════════════════════════════════

def test_4_not_sent_named():
    w = _signed_turns(media="not_sent")
    out = w.core.press(1, 1, A.ACT_SEND, "Даня", T_SIGN + 700)
    assert out["parts"] == {"text": A.SENT, "pdf": A.NOT_SENT}, out
    b = w.render(T_SIGN + 800, topic=True)
    assert "• PDF клиенту: не ушёл (19:15)" in b and "WhatsApp" not in b, b


def test_4_failed_status_named():
    w = _signed_sent()
    w.status("wamid.P1", "failed", T_SIGN + 800)
    w.tick(T_SIGN + 900)
    assert w.q("SELECT state FROM pdf_parts WHERE draft_id=1") == [(A.NOT_SENT,)], "failed — часть не ушла"
    b = w.render(T_SIGN + 950)
    assert "• PDF клиенту: не ушёл (19:15)" in b, b
    assert "• WhatsApp: не дошёл 19:17 (статус провайдера)" in b, b


def test_4_status_rank_and_no_status():
    w = _signed_sent()
    f = C.read_facts(w.dbpath, NUM, T_SIGN + 750)
    assert f["wa"] == {"status": None, "at": T_SIGN + 700, "old": False}, f["wa"]
    assert "• WhatsApp: статуса нет" in CS.render(f, T_SIGN + 750)
    late = T_SIGN + 700 + X.STATUS_DAYS * 86400 + 60
    assert "• WhatsApp: статуса нет (старше 7 суток не собирается)" in w.render(late)
    for word, dt in (("sent", 801), ("delivered", 802), ("failed", 803)):
        w.x("INSERT INTO part_status(wamid, status, part, draft_id, attempt, ts, seen, src) VALUES(?,?,?,?,?,?,?,?)",
            ("wamid.P1", word, "pdf", 1, 1, T_SIGN + dt, T_SIGN + dt, "test"))
    assert "• WhatsApp: получен телефоном 19:17 (статус провайдера)" in w.render(T_SIGN + 900), "delivered > sent"
    w.x("INSERT INTO part_status(wamid, status, part, draft_id, attempt, ts, seen, src) VALUES(?,?,?,?,?,?,?,?)",
        ("wamid.T1", "read", "text", 1, 1, T_SIGN + 805, T_SIGN + 805, "test"))
    assert "получен телефоном" in w.render(T_SIGN + 900), "статус ТЕКСТА части PDF не подтверждает"


# ═══ 8. чужие номера: одинаковые последние 9 цифр, слово-метка клиента ════════════════════════════════════════════

NUM_B = "8" + NUM[1:]                                              # те же последние 9 цифр, другой номер


def _seed_b(w):
    """Записи клиента B прямо в базу агента (все источники блока)."""
    t = T_SIGN + 300
    w.x("INSERT INTO drafts(id, number, state, ver, text, upto_id, created_at, kind) VALUES(77,?,?,1,'x',1,?,?)",
        (NUM_B, A.SENT, t, X.KIND_SIGNED))
    w.x("INSERT INTO signed_cards VALUES(?,?,?,?,?,?,?)", (NUM_B, "DOCB777", "2026-10-13 08:41", "PB7", "b" * 64, 77, t))
    w.x("INSERT INTO attach(draft_id, file_id, name, size, sha256, row, doc_id, ts, signed_at, number) "
        "VALUES(77,'PB7','b.pdf',10,?,7,'DOCB777',?,'2026-10-13 08:41',?)", ("b" * 64, t, NUM_B))
    w.x("INSERT INTO pdf_parts(draft_id, state, attempt, who, at, sending_at, wamid) VALUES(77,?,1,?,?,?,'wamid.B7')",
        (A.SENT, X.AUTO_WHO, t + 1, t + 1))
    w.x("INSERT INTO part_status VALUES('wamid.B7','read','pdf',77,1,?,?,'test')", (t + 5, t + 5))
    w.x("INSERT INTO outbox(wamid, number, ts, text, via, kind) VALUES('wamid.HB',?,?,'',?,'document')",
        (NUM_B, t + 9, A.VIA_TOPIC))
    w.x("INSERT INTO signed_asks(draft_id, number, asked, kind, upto_id, ts) VALUES(77,?,'pure','card',1,?)",
        (NUM_B, t + 2))
    w.x("INSERT INTO contract_expect(number, opened_at, why, upto_id, due_at, checked_at, outcome, state, closed_at, "
        "closed_by) VALUES(?,?,'ask',1,?,?,'empty','closed',?,'card:77')", (NUM_B, t - 50, t + 86400, t - 40, t))


def test_8_foreign_numbers_and_client_words_not_in_block():
    w = World()
    _seed_b(w)
    assert T.last9(NUM_B) == T.last9(NUM) and NUM_B != NUM
    fa = w.facts(NUM, T_SIGN + 1000)
    assert fa["records"] == 0 and fa["version"] is None and fa["ask"] is None and fa["expect"] is None, fa
    assert w.block(NUM, topic=False, now=T_SIGN + 1000) is None
    ba = w.block(NUM, topic=True, now=T_SIGN + 1000)
    bb = w.block(NUM_B, topic=False, now=T_SIGN + 1000)
    for piece in ("…OCB777", "13.10 08:41", "прочитан", "автоотправка", "документ человека", "просьба", "ожидание",
                  "реестр: проверка ожидания окончена"):
        assert piece in bb, (piece, bb)                                       # у B всё на месте
        assert piece not in ba, (piece, ba)                                   # у A — ничего чужого
    for b in (ba, bb):
        assert not re.search(r"\d{9,}", b), b
    # слово-метка из сообщения клиента в блок не попадает (настоящий адаптер, вопрос о договоре)
    r = Real()
    r.put(T_SIGN + 60, "МЕТКАЗЕБРА договор пришлите, номер 79999966963")
    _s, user, _i = r.adapter.build(NUM, 10 ** 6, now=T_SIGN + 600)
    blk = block_of(user)
    assert blk and "МЕТКАЗЕБРА" not in blk and "зебра" not in blk.lower() and not re.search(r"\d{9,}", blk), blk


# ═══ 9. таблиц нет / база заперта → «неизвестно», черновик строится ═══════════════════════════════════════════════

def test_9_tables_missing_unknown():
    d = tempfile.mkdtemp(prefix="wa_cstate_bare_")
    path, qpath = os.path.join(d, "agent.db"), os.path.join(d, "q.db")
    q = sqlite3.connect(qpath)
    q.execute(AT.QSCHEMA)
    q.commit()
    q.close()
    core = A.Core(path, qpath, SC.Model(), AT.FakeTG(), AT.FakeDoor())    # база без PDF-таблиц
    core.db.close()
    f = C.read_facts(path, NUM, T_SIGN)
    assert f["version"] == {"unknown": "нет таблиц: signed_cards, attach"}, f["version"]
    assert f["pdf"] == f["wa"] == f["human_doc"] == {"unknown": "версия не прочитана"}, f
    assert f["ask"] == {"unknown": "нет таблиц: signed_asks"} and f["expect"] == {"unknown": "нет таблиц: contract_expect"}
    assert f["records"] == 0 and CS.render(f, T_SIGN) is None, "записей нет, вопрос не о договоре — блока нет"
    f["topic"] = True
    b = CS.render(f, T_SIGN)
    assert "• версия: неизвестно (нет таблиц: signed_cards, attach)" in b and "• версия: в базе нет" not in b, b
    assert "• ожидание подписи: неизвестно (нет таблиц: contract_expect)" in b, b
    assert "• реестр: неизвестно (нет таблиц: contract_expect)" in b, b


def test_9_locked_or_absent_db_unknown_and_draft_still_built():
    w = Real()
    w.put(T_SIGN + 60, "Подписал")
    a = w.adapter
    # история адаптера читает ту же базу агента (`wa_history.read_sent`, timeout 10 с) — её запертость не предмет теста
    a._history = lambda number, upto_id: wa_history.read_history(number, a.queue_db, "", "", "", trig=int(upto_id) + 1)
    lock = sqlite3.connect(w.dbpath, isolation_level=None, timeout=1)
    lock.execute("BEGIN EXCLUSIVE")
    try:
        a.cstate_timeout = 0.2
        w.script = Script(final("Проверю договор."))
        got = a.draft(NUM, 10 ** 6)
    finally:
        lock.execute("ROLLBACK")
        lock.close()
    assert isinstance(got, dict) and got["text"] == "Проверю договор.", got
    b = block_of(w.script.seen[0])
    assert b and b.count("неизвестно (база агента не прочитана: OperationalError)") == 7, b
    assert len(b.split("\n")) == CS.BLOCK_LINES and "• версия: в базе нет" not in b, b
    assert a.last["info"]["cstate"]["unread"] == ["база агента не прочитана: OperationalError"]
    assert any("не прочитано: база агента не прочитана" in ln for ln in w.alines), w.alines[-3:]
    f = C.read_facts("", NUM, T_SIGN)
    assert f["version"] == {"unknown": C.W_NO_DB} and f["records"] == 0
    f = C.read_facts(os.path.join(tempfile.mkdtemp(prefix="wa_cstate_none_"), "нет.db"), NUM, T_SIGN)
    assert f["version"]["unknown"].startswith("база агента не прочитана: "), f["version"]
    assert C.READ_TIMEOUT == 2.0 and a.cstate_timeout == 0.2 and C.ContractStateAdapter(
        w.qpath, None).cstate_timeout == 2.0


def test_9_block_crash_keeps_old_request():
    w = Real()
    w.put(T_SIGN + 60, "Подписал")
    base = M.ModelAdapter.build(w.adapter, NUM, 10 ** 6, now=T_SIGN + 600)
    saved = CS.render
    try:
        CS.render = lambda facts, now: 1 / 0
        got = w.adapter.build(NUM, 10 ** 6, now=T_SIGN + 600)
    finally:
        CS.render = saved
    assert got[1] == base[1] and got[2]["cstate"]["unread"] == ["блок не собран: ZeroDivisionError"], got[2]["cstate"]
    assert "договор клиента: блок не собран (ZeroDivisionError) — запрос модели прежний" in w.alines


# ═══ 10. записей нет и вопрос не о договоре → user побайтно равен базовому ════════════════════════════════════

def test_10_no_records_not_topic_user_byte_equal():
    w = Real()
    w.put(T_SIGN + 60, "Добрый день, сколько стоит байк на неделю?")
    base = M.ModelAdapter.build(w.adapter, NUM, 10 ** 6, now=T_SIGN + 600)
    got = w.adapter.build(NUM, 10 ** 6, now=T_SIGN + 600)
    assert got[0] == base[0] and got[1] == base[1], "user/system побайтно равны базе"
    assert got[2]["cstate"] == {"lines": 0, "read_at": T_SIGN + 600, "unread": []}, got[2]["cstate"]
    assert got[2]["user_chars"] == len(base[1])
    assert any("блока нет — записей по номеру нет, вопрос не о договоре" in ln for ln in w.alines), w.alines[-2:]
    # и наоборот: вопрос о договоре без записей — блок есть, ровно перед прежним запросом
    w.put(T_SIGN + 700, "А договор где?")
    base = M.ModelAdapter.build(w.adapter, NUM, 10 ** 6, now=T_SIGN + 800)
    got = w.adapter.build(NUM, 10 ** 6, now=T_SIGN + 800)
    assert got[1].endswith("\n\n" + base[1]) and got[1].startswith(HEAD0), got[1][:200]
    assert got[2]["user_chars"] == len(got[1]) and got[2]["cstate"]["lines"] == 2


def test_10_cstate_off_parent_unchanged_with_records():
    w = _signed_sent()
    w.adapter.cstate_on = False
    w.put(T_SIGN + 1000, "А договор где?")
    base = M.ModelAdapter.build(w.adapter, NUM, 10 ** 6, now=T_SIGN + 1100)
    got = w.adapter.build(NUM, 10 ** 6, now=T_SIGN + 1100)
    assert got[1] == base[1] and "cstate" not in got[2] and got[2] == base[2]


# ═══ 11. флаг выключен ════════════════════════════════════════════════════════════════════════════════════

def _blob(path):
    import hashlib
    data = open(path, "rb").read().replace(b"\r\n", b"\n")
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def test_11_frozen_blobs_equal_a1dcbe5():
    for name, sha in FROZEN.items():
        assert _blob(os.path.join(ROOT, name)) == sha, name
    try:
        got = {n: subprocess.run(["git", "-C", ROOT, "rev-parse", "a1dcbe5:%s" % n], capture_output=True, text=True,
                                 timeout=60).stdout.strip() for n in FROZEN}
    except Exception as e:                                           # noqa: BLE001
        print("  ПРОПУЩЕНО: git недоступен (%s) — сверка с a1dcbe5 не сделана (это НЕ зелёное)" % type(e).__name__)
        return
    if not all(got.values()):
        print("  ПРОПУЩЕНО: объекта a1dcbe5 нет — сверка с git не сделана (это НЕ зелёное)")
        return
    assert got == AT_A1DCBE5, got


def test_11_core_without_cstate_no_table_no_reads():
    w = World(cstate=False)
    assert not w.core.cstate and w.core.claim_of is None
    assert "contract_expect" not in w.tables()
    w.registry.rows[:] = SC.live_rows()[:2]
    w.put(T_SIGN - 700, "Подписал")
    w.tick(T_SIGN - 400)
    assert "contract_expect" not in w.tables() and not w.expect_lines(), w.lines[-4:]
    assert w.core._cstate_due(NUM, T_SIGN) is False and w.core._cstate_expire(T_SIGN) == 0
    assert w.core._cstate_note(NUM, T.EMPTY, T_SIGN, 1, "pure") is None
    c = World(cstate=True, signed=False)
    assert not c.core.cstate and "contract_expect" not in c.tables(), "без карточки подписи — ни флага, ни таблицы"


def test_11_flag_off_process_has_no_new_modules():
    """Отдельный процесс: служба собрана БЕЗ флага (карточка подписи и прочее вкл) — модулей выпуска в процессе нет."""
    p = subprocess.run([sys.executable, os.path.abspath(__file__), PROBE_ARG], capture_output=True, text=True,
                       timeout=300, env=dict(os.environ, PYTHONIOENCODING="utf-8"), encoding="utf-8", errors="replace")
    got = [ln for ln in p.stdout.splitlines() if ln.startswith(PROBE_MARK)]
    assert p.returncode == 0 and got, (p.returncode, p.stdout[-800:], p.stderr[-1500:])
    assert got[-1] == PROBE_MARK, got[-1]


# ═══ 12. в блоке нет «достав» и сумм ═══════════════════════════════════════════════════════════════════════

def _rich_facts(now):
    t = now - 3600
    return {"read_at": now, "topic": True, "records": 5, "unread": [],
            "version": {"signed_at": SIGNED_AT, "doc": "1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789", "src": "card"},
            "pdf": {"state": "sent", "at": t, "who": "staff", "wamids": ["w"]},
            "wa": {"status": "delivered", "at": t + 60},
            "human_doc": {"at": t + 120}, "ask": {"at": t - 600, "asked": "pure", "kind": "card"},
            "expect": {"state": "closed", "why": "ask", "opened_at": t - 900, "due_at": t + 86400, "checked_at": t - 30,
                       "outcome": "empty", "closed_at": t - 10, "closed_by": "card", "card_wait": True}}


def test_12_no_delivery_word_no_sums_dates_one_form():
    now = T_SIGN + 7200
    today = datetime.date(2026, 10, 14)
    for f in (_rich_facts(now), dict(_rich_facts(now), expect={"state": "open", "why": "signed_claim",
                                                                "opened_at": now - 60, "due_at": now + 80000,
                                                                "checked_at": None}),
              dict(_rich_facts(now), pdf={"state": "sent", "at": now - 99, "who": "auto", "wamids": ["w"]})):
        b = CS.render(f, now)
        lines = b.split("\n")
        assert len(lines) == CS.BLOCK_LINES and len(b) <= CS.BLOCK_CHARS, (len(lines), len(b))
        assert "достав" not in b.lower(), b
        assert K.money_claims(b, None) == [], K.money_claims(b, None)
        assert T.money_claims(b, None, set()) == [], T.money_claims(b, None, set())
        assert M.arrival_claims(b, today, ()) == [], M.arrival_claims(b, today, ())
        for d in DATE_ANY.findall(b):
            assert re.fullmatch(r"\d{2}\.\d{2}", d), (d, b)
        assert not re.search(r"\d{9,}", b) and "2026" not in b, b
        assert "…456789" in b and "1AbCdEf" not in b, "doc — только хвостом 6 знаков"
        # дата — только «ДД.ММ ЧЧ:ММ» (без времени дня нет); у каждой строки — время: того же дня — «ЧЧ:ММ» (день — шапка)
        assert not re.search(r"\b\d{2}\.\d{2}\b(?! \d{2}:\d{2})", b), b
        for ln in lines[1:]:
            assert re.search(r"\d{2}:\d{2}", ln), ln
    assert "• PDF клиенту: ушёл 20:04; отправил: сотрудник" in CS.render(_rich_facts(now), now)


def _facts(now, **over):
    f = {"read_at": now, "topic": True, "records": 1, "unread": [], "version": None, "pdf": None, "wa": None,
         "human_doc": None, "ask": None, "expect": None}
    f.update(over)
    return f


def _line(f, label):
    got = [ln for ln in CS.render(f, f["read_at"]).split("\n") if (label + ":") in ln]
    assert got, (label, CS.render(f, f["read_at"]))
    return got[0]


# ═══ 13. находки критиков (CSTATE1510, исправление): время строк, давность и аренда версии, документ человека, ═══════
#        прошлое ожидания, тема по слову

def test_13_time_same_day_short_other_day_full_old_with_age():
    """Время строки: тот же день, что чтение, — «ЧЧ:ММ» (день — в шапке, форма спецификации); другой — «ДД.ММ ЧЧ:ММ»;
    прошлое от AGE_DAYS суток — с давностью словами: в «ДД.ММ» нет года, прошлогодний факт не читается вчерашним."""
    now = T_SIGN + 600
    assert CS.when(T_SIGN, now) == "19:04"
    assert CS.when(T_SIGN - 86400, now) == "13.10 19:04"
    assert CS.when(T_SIGN + 86400, now) == "15.10 19:04", "будущее (срок ожидания) — с датой, без давности"
    assert CS.when(T_SIGN - 8 * 86400, now) == "06.10 19:04, 8 сут назад"
    assert CS.when(T_SIGN - 365 * 86400, now) == "14.10 19:04, больше 2 мес. назад"
    assert CS.when(None, now) == "время неизвестно" and CS.when(T_SIGN, None) == "14.10 19:04"
    assert CS.AGE_DAYS == X.STATUS_DAYS
    assert [CS.age_words(d) for d in (0, -3, 1, 2, 60, 61)] == ["", "", "вчера", "2 сут назад", "60 сут назад",
                                                                "больше 2 мес. назад"]


def test_13_old_version_age_and_rental_end_named():
    """Находка обоих критиков: прошлый договор не выдаётся за договор нынешнего обращения — версия называет давность и
    то, что срок её аренды прошёл; сегодняшняя — без пометок (форма спецификации)."""
    now = T_SIGN + 600
    v = {"signed_at": SIGNED_AT, "doc": "D36", "src": "card", "date_to": "2026-10-17"}
    assert _line(_facts(now, version=v), "версия") == "• версия: подписан 14.10 19:04 · doc …D36 · карточка подписи"
    later = T_SIGN + 8 * 86400
    assert _line(_facts(later, version=v), "версия") == (
        "• версия: подписан 14.10 19:04 · doc …D36 · карточка подписи · 8 сут назад, аренда этой версии закончилась")
    year = _line(_facts(T_SIGN + 365 * 86400, version=v), "версия")
    assert year.endswith("· больше 2 мес. назад, аренда этой версии закончилась"), year
    run = _line(_facts(T_SIGN + 2 * 86400, version=dict(v, date_to="2026-10-25")), "версия")
    assert run.endswith("· карточка подписи · 2 сут назад"), "аренда ещё идёт — только давность"
    assert _line(_facts(later, version=dict(v, date_to=None)), "версия").endswith("· карточка подписи · 8 сут назад")
    # из базы: срок аренды версии — `attach.date_to` её черновика; та же версия через 8 суток названа прошлой арендой
    w = _signed_sent()
    f = C.read_facts(w.dbpath, NUM, later)
    assert f["version"]["date_to"] == w.q("SELECT date_to FROM attach WHERE draft_id=1")[0][0], f["version"]
    assert f["version"]["date_to"] and CS.raw_day(f["version"]["date_to"]) < CS._day(later), f["version"]
    f["topic"] = False
    vl = _line(f, "версия")
    assert vl.endswith("· сверка ответа · 8 сут назад, аренда этой версии закончилась"), vl
    assert "ушёл 14.10 19:15, 8 сут назад" in _line(f, "PDF клиенту"), "PDF той версии — тоже с давностью"


def test_13_human_decided_version_named_and_doc_line():
    """Находка критика: версию решил документ, отправленный человеком (`signed_cards` без черновика), — источник так и
    назван, а строка «документ человека» есть и без строки темы (с телефона): модель видит, что документ уже у клиента."""
    w = World()
    t = T_SIGN + 300
    w.x("INSERT INTO signed_cards VALUES(?,?,?,?,?,?,?)", (NUM, "D36", SIGNED_AT, "PDF36", SHA36, None, t))
    f = w.facts(NUM, T_SIGN + 400)
    assert f["version"]["src"] == "human" and f["human_doc"] == {"at": t, "via": "noted"}, f
    b = w.block(NUM, now=T_SIGN + 400)
    assert "• версия: подписан 14.10 19:04 · doc …D36 · документ ушёл человеком" in b, b
    assert "• документ человека: отмечен кодом 19:09 — тема или телефон (какой — не видно)" in b, b
    assert "проход подписи" not in b, b
    w.x("INSERT INTO outbox(wamid, number, ts, text, via, kind) VALUES('wamid.H1',?,?,'[документ]',?,'document')",
        (NUM, T_SIGN + 200, A.VIA_TOPIC))
    b = w.block(NUM, now=T_SIGN + 400)
    assert "• документ человека: 19:07 из темы (какой — не видно)" in b and "[документ]" not in b, b


def test_13_negative_registry_outcome_after_expectation_is_past():
    """Находка критика: «подписанного не было» из ОКОНЧЕННОГО ожидания не звучит как «сейчас договора нет» — названо
    прошлым; пока ожидание открыто — проверка как есть; найденный подписанный — факт и после закрытия."""
    now = T_SIGN + 600
    e = {"state": "open", "why": "signed_claim", "opened_at": T_SIGN - 400, "due_at": T_SIGN + 86000,
         "checked_at": T_SIGN - 30, "outcome": "empty", "closed_at": None, "closed_by": None, "card_wait": False}
    assert _line(_facts(now, expect=e), "реестр") == "• реестр: проверен 19:03 — подписанного не было (проверка ожидания)"
    gone = dict(e, state="expired", closed_at=T_SIGN + 86100)
    for f in (_facts(T_SIGN + 86000 + 7 * 86400, expect=gone), _facts(T_SIGN + 86100, expect=e)):
        ln = _line(f, "реестр")                              # отмечено истёкшим · срок вышел, проход ещё не отметил
        assert ln.startswith("• реестр: проверка ожидания окончена; последняя ") and "сейчас не проверялся" in ln, ln
        assert "проверен " not in ln, ln
        assert "истекло" in _line(f, "ожидание подписи")
    found = dict(e, state="closed", outcome="fact", closed_by="card", closed_at=T_SIGN + 60, checked_at=T_SIGN + 60)
    assert _line(_facts(now, expect=found), "реестр") == \
        "• реестр: проверен 19:05 — подписанный найден (проверка ожидания)"
    assert "подписанных несколько — выбор за человеком" in _line(_facts(now, expect=dict(e, outcome="ambiguous")),
                                                                "реестр")
    assert set(CS.OUTCOME_WORDS) == set(T.OUTCOMES), "у каждого исхода двери — свои слова"


def test_13_agreed_word_not_topic_request_unchanged():
    """Находка критика: «Договорились…» — не о договоре: записей нет — запрос модели побайтно прежний."""
    w = Real()
    w.put(T_SIGN + 60, "Договорились, жду байк завтра в 10")
    base = M.ModelAdapter.build(w.adapter, NUM, 10 ** 6, now=T_SIGN + 600)
    got = w.adapter.build(NUM, 10 ** 6, now=T_SIGN + 600)
    assert got[1] == base[1] and got[2]["cstate"]["lines"] == 0, got[1][:300]


def test_12_limits_hold_on_long_reasons():
    now = T_SIGN
    long = "x" * 400
    f = {k: {"unknown": long} for k in C.SOURCES}
    f.update(read_at=now, topic=True, records=0, unread=[long])
    b = CS.render(f, now)
    assert len(b.split("\n")) <= CS.BLOCK_LINES and len(b) <= CS.BLOCK_CHARS, (len(b.split("\n")), len(b))
    assert all(len(ln) <= CS.LINE_MAX + 2 for ln in b.split("\n")[1:]), [len(x) for x in b.split("\n")]
    # по построению ничего не срезается: шапка + 7 строк по LINE_MAX укладываются в BLOCK_CHARS (ожидание — последняя)
    assert len(b.split("\n")) == CS.BLOCK_LINES and b.split("\n")[-1].startswith("• ожидание подписи:"), b[-200:]


def main():
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    bad = 0
    for name, fn in tests:
        try:
            fn()
            print("PASS", name)
        except Exception as e:                                       # noqa: BLE001
            bad += 1
            print("FAIL", name, "—", type(e).__name__, str(e)[:400])
    print("ИТОГ %d/%d" % (len(tests) - bad, len(tests)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
