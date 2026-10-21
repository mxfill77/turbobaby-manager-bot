#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ПРИЁМКА ВЫПУСКА CSTATE1510 (состояние дела договора для модели, вариант C) поверх прода a1dcbe5 (CASEPDF1510 поверх
SIGNEDCARD1410). Чёрный ящик по СПЕЦИФИКАЦИИ, написан независимо, БЕЗ реализации.

ЧТО ПРИНИМАЕТСЯ (критерий владельца TB-OWNER-AGENT-BEHAVIOR-1510): МОДЕЛЬ сама решает ответ и действие, а КОД даёт ей
факты дела с временем и источником, проверяет привязку и исполняет. Живой случай 14.10: клиент написал «Подписал», модель
ответила без договора (contract не звала), карточку с PDF дал только код. Здесь проверяется поведение:
  · модель на КАЖДОМ ходу сверки видит блок «ДОГОВОР КЛИЕНТА» — факты кода из базы агента со временем и источником, и
    сама выбирает инструмент (contract → contract_pdf) или отвечает без него;
  · PDF доставлен и прочитан — модель видит «ушёл ЧЧ:ММ (сотрудник)» и «прочитан ЧЧ:ММ»; повтора код не предлагает (ни
    новой карточки, ни нового вложения);
  · ожидаемое событие («жду подписи» по просьбе или по «подписал» при пустом реестре) живёт в БАЗЕ, переживает рестарт и
    продолжает дело карточкой подписи при подписи; истёкшее и устаревшее помечено;
  · в блоке нет чужих номеров (в том числе с теми же последними 9 цифрами), текста клиента, имён, сумм, «достав»;
  · флаг выкл — байт-в-байт прежнее (адаптер, ядро, служба, импорты, блобы).

ИНТЕРФЕЙС, КОТОРОГО В a1dcbe5 НЕТ, — ВЗЯТ ИЗ СПЕЦИФИКАЦИИ CSTATE1510 (расхождение имени — правка здесь, не в смысле):
  · модуль `wa_contract_state` — чистые функции, импорты только `re` и `datetime`: `topic(text)`, `signed_claim(text)`,
    `render(facts, now) → str | None`;
  · модуль `wa_agent_cstate`: `ContractStateAdapter(wa_agent_model.ModelAdapter)`; `build()` = `super().build()` +
    `read_facts(agent_db, number, now)` (sqlite URI mode=ro, timeout 2 с) + `render`; блок — В НАЧАЛО user через "\\n\\n",
    `info["user_chars"]` пересчитан, `info["cstate"]` записан; атрибут `cstate_on` (False — build родителя без изменений);
    `build_followup` НЕ переопределён;
  · `wa_agent_svc`: `F_CSTATE = "WA_AGENT_CONTRACT_STATE"` (не в FLAGS); `models_of` кладёт `cstate=True` в вызов
    `make_model` только при флаге И WA_AGENT_TOOLS; `make_model(..., cstate=False)`; `cstate_of(environ, signed, model)`
    → тройка: флаг не запрошен — (None, None, None); запрошен без засчитанной карточки подписи — `model.cstate_on = False`
    и слова «не засчитан»; засчитан — именованные аргументы ядра с `cstate=True` и слова строки старта (строка старта
    называет WA_AGENT_CONTRACT_STATE);
  · `wa_agent_attach.AttachCore(..., cstate=False)`; таблица `contract_expect(number, opened_at, why ask|signed_claim,
    upto_id, due_at, checked_at, outcome empty|timeout|refused, state open|closed|expired, closed_at, closed_by
    card:<id>|held)`, PK (number, opened_at), уникальный частичный индекс по number WHERE state='open'; только при cstate;
  · блок: шапка ДОСЛОВНО (HEADER ниже); строки ищутся по подстроке «<метка>:» — «версия», «реестр», «PDF клиенту»,
    «WhatsApp», «документ человека», «просьба прислать договор», «ожидание подписи»; не больше 8 строк и 1200 знаков.

ТОЛКОВАНИЯ, где спецификация молчит или спорит сама с собой (названы, чтобы расхождение правилось здесь осознанно):
  · строка «PDF клиенту: ушёл ЧЧ:ММ (сотрудник)» — слово роли из спецификации; `wa_agent_model.arrival_claims` ловит
    «сотрудник» рядом со временем как обещание приезда (проверено пробой: ('время', день)) — п.12 «arrival_claims по блоку
    пусты» с ней несовместим буквально; `clean()` допускает РОВНО это одно срабатывание и проверяет, что без слова роли
    утверждений о приезде нет;
  · открывающая проверка реестра — тоже проверка: у открытого ожидания сразу checked_at и outcome=empty (иначе блок
    сказал бы «реестр не проверялся» про реестр, который только что прочитан пустым);
  · ушедший PDF всегда даёт строку «WhatsApp:» (без статуса — «статуса нет …»), пометка «старше 7 суток» — только у
    PDF старше STATUS_DAYS (у свежего она была бы неправдой);
  · «доставлен» в блоке быть не может (п.12 запрещает основу «достав») — доставку называет «получен телефоном»;
  · слова строки журнала об истечении спецификация не задаёт — судится факт строки (истек/expired/срок).

СТЕНД — ЖИВЫЕ ФОРМАТЫ tests/test_wa_signed_card.py (импортом, без копии): World, Registry (форма
`bridge_client.contract_find`), Pdfs (`bridge_client.contract_pdf`), Book (снимок броней), номер 79999966963 с
неразрывными дефисами в контактах, реестр стр.34/35 ОТОЗВАН, стр.36 ПОДПИСАН 2026-10-14 19:04 с pdf_id. Квитанции
провайдера — живой формой вебхука (`wa_status` — все статусы wamid, первый — ещё и строкой `wa_inbox` msg_type='status').
Модель — НАСТОЯЩИЙ адаптер (`ContractStateAdapter` / `ModelAdapter`) со сценарием вместо платного вызова. Сети нет: мост,
модель, Telegram, WhatsApp — подделки, базы временные (tempfile) и не удаляются.

WA_AGENT_SRC=<каталог> подменяет модули (прогон мутантов)."""
import ast
import datetime
import hashlib
import inspect
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
if os.environ.get("WA_AGENT_SRC"):
    sys.path.insert(0, os.environ["WA_AGENT_SRC"])

PROBE_ARG = "--probe-cstate-off-imports"
PROBE_MARK = "CSTATE_OFF_MODULES "
PROBE = PROBE_ARG in sys.argv[1:]
NEW_MODULES = ("wa_contract_state", "wa_agent_cstate")

import wa_agent as A  # noqa: E402
import wa_agent_attach as X  # noqa: E402
import wa_agent_knowledge as K  # noqa: E402
import wa_agent_model as M  # noqa: E402
import wa_agent_svc as S  # noqa: E402
import wa_agent_tools as T  # noqa: E402
import test_wa_signed_card as W  # noqa: E402  (стенд живых форматов SIGNEDCARD1410)

CS = C = None
CS_ERR = C_ERR = "процесс пробы флага выкл: новые модули не импортируются"
if not PROBE:                       # проба флага выкл (случай 21) обязана начаться БЕЗ новых модулей в sys.modules
    try:
        import wa_contract_state as CS  # noqa: E402
        CS_ERR = None
    except Exception as e:                                           # noqa: BLE001 — назовёт случай
        CS_ERR = e
    try:
        import wa_agent_cstate as C  # noqa: E402
        C_ERR = None
    except Exception as e:                                           # noqa: BLE001
        C_ERR = e

NUM, NUM2, T_SIGN, T_START, SHA36 = W.NUM, W.NUM2, W.T_SIGN, W.T_START, W.SHA36
NUM_SAME9 = "66999966963"                  # другой номер с ТЕМИ ЖЕ последними 9 цифрами, что у NUM (999966963)
BIKE_C = "AEROX 155 BLUE PHUKET 7712"     # его байк и договор — свои (телефон договора с явным кодом +66)
CONTACTS_C = "Сомчай +66 99 996 6963"
PDF50 = W.k3_pdf_fixture.classic(b"signed contract row 50 AEROX 7712")
PHUKET = 7 * 3600
T_PRESS = T_SIGN + 660                     # 19:15 — «Отправить» сотрудника
T_READ = T_SIGN + 900                      # 19:19 — PDF прочитан клиентом
STAFF = "Даня"                             # имя нажавшего — в блок не попадает (только роль)
CLAIM = "Подписал"                         # дословно из живого случая 14.10
CLAIM_PARA = ["Подписала договор", "Всё, подписал 👍", "I have signed the contract", "เซ็นสัญญาแล้วครับ"]
CLAIM_NEG = ["не подписал", "где подписать?", "подпишу завтра", "Здравствуйте!", "Ещё не подписал",
             "I haven't signed it yet", "Where do I sign?"]
ASK_RU = "Пришлите, пожалуйста, мой договор"
WHERE = "А договор где?"
NEUTRAL = "Здравствуйте! Во сколько вы открываетесь?"
HEADER = ("ДОГОВОР КЛИЕНТА — факты кода из базы агента на %s (Пхукет). «неизвестно» и «в базе нет» ≠ «договора нет»: "
          "реестр — contract, PDF — contract_pdf (приложит и проверит код). Служебные метки клиенту не называть.")
EXPECT_COLS = {"number", "opened_at", "why", "upto_id", "due_at", "checked_at", "outcome", "state", "closed_at",
               "closed_by"}
HEAD = T.TOOLS_BLOCK % T.MAX_CALLS + "\n\n"            # голова каждого хода сверки (`T.run`): блок инструментов + user
# блобы a1dcbe5 (`git rev-parse a1dcbe5:<файл>`): закреплённые файлы выпуск НЕ трогает
PINS = {"wa_agent.py": "70695c7dc669f2b4d14ff7c000763b915e6121e8",
        "wa_agent_model.py": "b95d3a861f87075f684ba10b7d97e40e411d44a9",  # RCFIX2010: было 868b0c4b (free_bikes с парком снимка) · PROMPT2110: было 7c58cca9
        "wa_agent_tools.py": "fb70716d09b8b2812c08d40f2b0d66ff18ead9e3",
        "wa_agent_knowledge.py": "34fcc7858c39f9f1c705d79f617916cbf636dda6",  # PROMPT2110: было d338a3c2
        "rental_case.py": "3e3cba2f63461ae6fccf1a7d3f044da0c22cbca0"}
TOOLS_BLOCK_SHA = "175b220824b649ce151ae7f463ac864166265b26e9ccd13d42032a93d850d3d1"   # = integ_wa BASE_TOOLS_BLOCK_SHA
SVC_ON = {"WA_AGENT_DRAFTS": "1", "WA_AGENT_CARDS": "1", "WA_SEND": "1", "WA_AGENT_TOOLS": "1",
          "WA_AGENT_BOOK_READ": "1", "WA_AGENT_ATTACH": "1"}
WA_STATUS = ("CREATE TABLE IF NOT EXISTS wa_status (wamid TEXT NOT NULL, status TEXT NOT NULL, recipient TEXT, "
             "ts_msg INTEGER, ts_queued INTEGER NOT NULL, source TEXT, PRIMARY KEY (wamid, status))")   # = wa_webhook


# ══ стенд ══════════════════════════════════════════════════════════════════════════════════════════════════════

def _cs():
    assert CS is not None, "модуля wa_contract_state нет: %r" % (CS_ERR,)
    return CS


def _c():
    assert C is not None, "модуля wa_agent_cstate нет: %r" % (C_ERR,)
    return C


def final(text):
    return {"text": text, "handoff": [], "lang": "ru", "why": "сценарий приёмки"}


class Script:
    """Модель по сценарию: ответы по порядку, последний повторяется; `seen` — user каждого хода (что модель видела)."""

    def __init__(self, *answers):
        self.answers, self.seen = list(answers) or [final("Спасибо!")], []

    def __call__(self, system, user):
        self.seen.append(user)
        a = self.answers[min(len(self.seen) - 1, len(self.answers) - 1)]
        return (a if isinstance(a, str) else json.dumps(a, ensure_ascii=False)), {"in": 10, "out": 5}


def _no_cash(**kw):
    return {"ok": False, "error": "касса стенду не нужна"}


class World(W.World):
    """Стенд SIGNEDCARD1410 + флаг ядра cstate (None — аргумент не передаётся вовсе: прод a1dcbe5) и автоотправка CASEPDF.
    real — сценарий: модель ядра — НАСТОЯЩИЙ адаптер (model_cls, по умолчанию ContractStateAdapter) с дверями сверки
    стенда; None — модель стенда (молчит). `reader()` — отдельный адаптер на тех же файлах: так модель увидит базу."""

    def __init__(self, cstate=True, autosend=None, real=None, model_cls=None, **kw):
        self.cstate, self.autosend, self.real, self.model_cls = cstate, autosend, real, model_cls
        self.mlog = []
        W.World.__init__(self, **kw)

    def reader(self, script=None, cls=None, agent_db=None):
        cls = cls or self.model_cls or _c().ContractStateAdapter
        return cls(self.qpath, script if script is not None else Script(), book=self.book, clock=self.clock,
                   agent_db=agent_db or self.dbpath, log=self.mlog.append,
                   tools={"cash": _no_cash, "contract": self.registry, "contract_pdf": self.pdfs})

    def new_core(self):
        if self.real is not None:
            self.model = self.reader(script=self.real)
        kw = dict(log=self.lines.append, clock=self.clock, attach=True, pdf_fetch=self.pdfs,
                  contract_find=self.registry, signed=self.signed, signed_lookback_h=self.lookback_h)
        if self.cstate is not None:
            kw["cstate"] = self.cstate
        if self.cstate:                 # живой формат сборки ядра = служба (`wa_agent_svc.cstate_of`): детектор «подписал»
            kw["claim_of"] = _cs().signed_claim   # даёт служба — ядро не импортирует wa_contract_state (замки импортов)
        if self.autosend is not None:
            kw["autosend"] = self.autosend
        return X.AttachCore(self.dbpath, self.qpath, self.model, self.tg, self.door, **kw)


class ErrRegistry(W.Registry):
    """Реестр, отвечающий отказом моста (`err`) — форма `{"ok": False, "error": …}`; таймаут — `fail` стенда."""
    err = None

    def __call__(self, phone="", name="", bike="", date_from="", date_to="", limit=None):
        if self.err:
            self.calls.append({"phone": phone, "date_from": date_from, "date_to": date_to})
            return {"ok": False, "error": self.err}
        return W.Registry.__call__(self, phone, name, bike, date_from, date_to, limit)


def hm(ts):
    return time.strftime("%H:%M", time.gmtime(ts + PHUKET))


def dm(ts):
    return time.strftime("%d.%m %H:%M", time.gmtime(ts + PHUKET))


def day(ts):
    return datetime.datetime.fromtimestamp(ts + PHUKET, datetime.timezone.utc).date()


def last_in(w, number=NUM):
    q = sqlite3.connect(w.qpath)
    try:
        return q.execute("SELECT MAX(id) FROM wa_inbox WHERE from_number=? AND echo=0 AND msg_type<>'status'",
                         (number,)).fetchone()[0]
    finally:
        q.close()


def status(w, wamid, word, ts, number=NUM):
    """Квитанция провайдера живой формой вебхука: каждая — в `wa_status`; ПЕРВАЯ на wamid — ещё и строкой `wa_inbox`."""
    q = sqlite3.connect(w.qpath)
    try:
        q.execute(WA_STATUS)
        first = q.execute("SELECT COUNT(*) FROM wa_status WHERE wamid=?", (wamid,)).fetchone()[0] == 0
        q.execute("INSERT OR IGNORE INTO wa_status(wamid, status, recipient, ts_msg, ts_queued, source) "
                  "VALUES(?,?,?,?,?,?)", (wamid, word, number, int(ts), int(ts), "webhook"))
        if first:
            q.execute("INSERT INTO wa_inbox(ts_queued, from_number, msg_type, text, ts_msg, echo, history, wamid) "
                      "VALUES(?,?,?,?,?,0,0,?)", (int(ts), number, "status", word, int(ts), wamid))
        q.commit()
    finally:
        q.close()


def expect_rows(w, number=NUM):
    db = sqlite3.connect(w.dbpath)
    db.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in db.execute("SELECT * FROM contract_expect WHERE number=? ORDER BY opened_at",
                                            (number,)).fetchall()]
    finally:
        db.close()


def tables(path):
    db = sqlite3.connect(path)
    try:
        return {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    finally:
        db.close()


def dump(path):
    """База агента целиком: схема и строки всех таблиц (порядок строк не важен)."""
    db = sqlite3.connect(path)
    try:
        out = {"__schema__": sorted(r[0] or "" for r in db.execute("SELECT sql FROM sqlite_master").fetchall())}
        for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall():
            out[name] = sorted(repr(r) for r in db.execute('SELECT * FROM "%s"' % name).fetchall())
        return out
    finally:
        db.close()


def blk(ad, number, upto, now):
    """Адаптер → (блок | None, user, базовый user, info). Базовый user — `ModelAdapter.build` ТОГО ЖЕ адаптера: блок обязан
    стоять В НАЧАЛЕ user через пустую строку, а всё после него — байт-в-байт прежний запрос."""
    s1, u1, i1 = ad.build(number, upto, now=now)
    s0, u0, _i0 = M.ModelAdapter.build(ad, number, upto, now=now)
    assert s1 == s0, "блок не трогает system"
    assert i1.get("user_chars") == len(u1), ("user_chars не пересчитан", i1.get("user_chars"), len(u1))
    if u1 == u0:
        return None, u1, u0, i1
    assert u1.endswith("\n\n" + u0) and len(u1) > len(u0) + 2, ("блок не в начале user через «\\n\\n»", u1[:400])
    b = u1[:len(u1) - len(u0) - 2]
    assert b.startswith("ДОГОВОР КЛИЕНТА"), b[:200]
    return b, u1, u0, i1


def block(w, number=NUM, now=None, upto=None, ad=None):
    now = w.clock.t if now is None else now
    b, _u, _b, _i = blk(ad or w.reader(), number, upto or last_in(w, number), now)
    assert b is not None, "записи по номеру есть — блок обязан быть"
    return b


def line(b, label):
    got = [ln for ln in b.split("\n") if (label + ":") in ln]
    assert got, ("строки «%s:» в блоке нет" % label, b)
    return got[0]


def seen_block(user):
    """user хода сверки (`T.run`) → блок: голова = блок инструментов + блок «ДОГОВОР КЛИЕНТА» + база с «СЕГОДНЯ: »."""
    assert user.startswith(HEAD), user[:200]
    body = user[len(HEAD):]
    assert body.startswith("ДОГОВОР КЛИЕНТА"), ("блока нет в голове хода", body[:300])
    b, sep, _rest = body.partition("\n\nСЕГОДНЯ: ")
    assert sep, body[:600]
    return b


def clean(b, *texts, when=T_SIGN):
    """Правила блока: ни номеров (9+ цифр), ни текста клиента, имён и сумм; даты только «ДД.ММ ЧЧ:ММ»; без «достав»;
    денежных утверждений нет; не больше 8 строк и 1200 знаков. Утверждение о приезде допускается РОВНО одно —
    от слова роли «сотрудник», которое спецификация сама кладёт рядом со временем отправки PDF (см. возврат приёмки)."""
    assert not re.search(r"\d{9,}", b), ("9+ цифр подряд в блоке", b)
    for t in texts + (NUM, NUM_SAME9, NUM2, NUM[-9:], "Иван", "Пётр", "Сомчай", STAFF, "1500", "THB", "бат"):
        assert t not in b, ("в блоке %r" % t, b)
    assert "достав" not in b.lower(), b
    assert not re.search(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}\.\d{1,2}\.\d{2,4}\b|\b20\d\d\b", b), ("дата не той формы", b)
    assert not re.search(r"\b\d{2}\.\d{2}\b(?! \d{2}:\d{2})", b), ("день без времени", b)
    assert not re.search(r"(?<![\d:])\b\d{3,}\b", b), ("число в блоке (сумма, размер, год?)", b)
    assert K.money_claims(b, None) == [], K.money_claims(b, None)
    arr = M.arrival_claims(b, day(when))
    if arr:
        assert "сотрудник" in b and M.arrival_claims(b.replace("сотрудник", "человек"), day(when)) == [], (arr, b)
    assert len(b) <= 1200 and len(b.split("\n")) <= 8, (len(b), b.count("\n") + 1, b)


def card_sent(w, who=STAFF, t_press=T_PRESS):
    """Клиент «Подписал договор» → карточка подписи → «Отправить» человека: текст и PDF ушли (wamid.T1, wamid.P1)."""
    did = W._card(w)
    w.clock.t = float(t_press)
    out = w.core.press(did, 1, A.ACT_SEND, who, t_press)
    assert out.get("ok"), out
    assert w.q("SELECT state, wamid FROM pdf_parts WHERE draft_id=?", (did,)) == [(A.SENT, "wamid.P1")]
    return did


def no_client_send(w, number=NUM):
    assert w.door.sends == [] and w.door.media == [], (w.door.sends, w.door.media)
    assert w.q("SELECT COUNT(*) FROM outbox WHERE number=?", (number,)) == [(0,)]


def open_by(w, text, t_in, registry):
    """Клиент пишет text при реестре без подписанного договора → проход → ожидание open. → строка ожидания."""
    w.put(t_in, text)
    w.tick(t_in + 600)
    rows = expect_rows(w)
    assert len(rows) == 1 and rows[0]["state"] == "open", (rows, w.sign_lines()[-6:])
    assert w.signed_drafts() == [] and len(registry.calls) == 1, (w.signed_drafts(), registry.calls)
    return rows[0]


# ══ 1–2 · детектор и интерфейс ═════════════════════════════════════════════════════════════════════════════════

def test_c01_detector_signed_claim_and_topic():
    """«Подписал» (дословно 14.10) и 4 перефразировки RU/EN/TH → topic и signed_claim истинны; «не подписал», «где
    подписать?», «подпишу завтра», приветствие и их английские близнецы → signed_claim ложна; вопрос о договоре — topic."""
    cs = _cs()
    for t in [CLAIM] + CLAIM_PARA:
        assert cs.signed_claim(t), t
        assert cs.topic(t), t
    for t in CLAIM_NEG + [None, "", "   ", "👍"]:
        assert not cs.signed_claim(t), t
    for t in (WHERE, "Где мой договор?", "Where is my contract?", ASK_RU):
        assert cs.topic(t), t
    for t in (NEUTRAL, "Здравствуйте!", "Спасибо, всё ок", None, ""):
        assert not cs.topic(t), t


def test_c02_interface_named_in_spec():
    """Имена спецификации: чистый модуль фактов (re + datetime), подкласс адаптера без своего напоминания, флаг службы
    вне FLAGS, `cstate_of`, параметр ядра `cstate` по умолчанию False."""
    cs, c = _cs(), _c()
    tree = ast.parse(open(cs.__file__, encoding="utf-8").read())
    imps = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            imps |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            imps.add((n.module or "").split(".")[0])
    assert imps <= {"re", "datetime"}, imps
    used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert not used & {"open", "exec", "eval", "__import__", "sqlite3", "os", "sys", "socket", "subprocess"}, used
    assert callable(cs.topic) and callable(cs.signed_claim) and callable(cs.render)
    assert issubclass(c.ContractStateAdapter, M.ModelAdapter)
    assert "build_followup" not in vars(c.ContractStateAdapter), "напоминание блока не видит — не переопределяется"
    assert S.F_CSTATE == "WA_AGENT_CONTRACT_STATE" and S.F_CSTATE not in S.FLAGS
    assert callable(S.cstate_of)
    par = inspect.signature(X.AttachCore.__init__).parameters
    assert "cstate" in par and par["cstate"].default is False, par.get("cstate")
    assert "cstate" in inspect.signature(S.make_model).parameters
    assert inspect.signature(S.make_model).parameters["cstate"].default is False


# ══ 3–7 · модель получает факты дела с временем и источником ════════════════════════════════════════════════════

def test_c03_signed_claim_no_version_block_every_turn_model_reads_contract_and_pdf():
    """п.2 спецификации, живой случай 14.10: «Подписал», версии в базе нет → блок в голове КАЖДОГО хода сверки; модель
    сама зовёт contract → contract_pdf, код прикладывает PDF и проверяет, как сейчас; клиенту ничего без нажатия; после —
    блок называет версию источником «сверка ответа» и PDF «ждёт нажатия»."""
    s = Script({"tool": "contract", "args": {}}, {"tool": "contract_pdf", "args": {"file_id": "PDF36"}},
               final("Спасибо! Договор подписан — направляем вам его PDF."))
    w = World(real=s)
    w.put(T_SIGN + 60, CLAIM)
    w.tick(T_SIGN + 600)
    assert len(s.seen) == 3, (len(s.seen), w.mlog[-6:])
    blocks = [seen_block(u) for u in s.seen]
    assert blocks[0] == blocks[1] == blocks[2], "блок одинаков на всех ходах одной сверки"
    assert blocks[0].split("\n")[0] == HEADER % dm(T_SIGN + 600), blocks[0].split("\n")[0]
    clean(blocks[0], CLAIM)
    assert w.q("SELECT id, state, kind FROM drafts") == [(1, A.PENDING, None)], w.q("SELECT id, state, kind FROM drafts")
    a = w.attach(1)
    assert a[:6] == ("PDF36", "contract_36.pdf", len(W.PDF36), SHA36, 36, "D36"), a
    assert "PDF36" in w.pdfs.calls and w.registry.calls[0] == {"phone": NUM, "date_from": "2026-10-14",
                                                               "date_to": "2026-10-17"}, w.registry.calls
    assert w.signed_drafts() == [], "версию покрыл ответ модели — карточки подписи нет"
    no_client_send(w)
    b = block(w, now=T_SIGN + 700)
    vl = line(b, "версия")
    assert "подписан 14.10 19:04" in vl and "сверка ответа" in vl and "…D36" in vl, vl
    assert "ждёт нажатия" in line(b, "PDF клиенту"), b
    clean(b, CLAIM)


def test_c04_pdf_read_model_sees_it_answers_without_tools_no_second_pdf():
    """п.3: «А договор где?», версия подписана, PDF ушёл (нажал сотрудник) и прочитан → модель видит «ушёл 19:15
    (сотрудник)» и «прочитан 19:19», отвечает БЕЗ инструмента; судья пропускает; второй карточки и нового вложения нет."""
    w = World()
    did = card_sent(w)
    status(w, "wamid.P1", "sent", T_PRESS + 10)
    status(w, "wamid.P1", "delivered", T_PRESS + 120)
    status(w, "wamid.P1", "read", T_READ)
    w.tick(T_READ + 10)
    assert w.q("SELECT status FROM part_status WHERE wamid='wamid.P1' ORDER BY status") == [
        ("delivered",), ("read",), ("sent",)]
    answer = "Договор уже у вас в этом чате: мы отправили PDF, и вы его открыли."
    s = Script(final(answer))
    w.real = s
    w.restart()                                                  # модель ядра — настоящий адаптер с блоком
    w.put(T_SIGN + 1500, WHERE)
    w.tick(T_SIGN + 2100)
    assert len(s.seen) == 1, ("модель ответила без инструмента — один ход", len(s.seen))
    b = seen_block(s.seen[0])
    vl = line(b, "версия")
    assert "подписан 14.10 19:04" in vl and "карточка подписи" in vl, vl
    pl = line(b, "PDF клиенту")
    assert ("ушёл " + hm(T_PRESS)) in pl and "сотрудник" in pl, pl
    assert ("прочитан " + hm(T_READ)) in line(b, "WhatsApp"), b
    assert not re.search(r"документ человека: \d{2}:\d{2}", b), "PDF агента — не документ человека"
    clean(b, WHERE)
    new = [r for r in w.q("SELECT id, state, kind, handoff FROM drafts ORDER BY id") if r[0] > did]
    assert [(r[1], r[2]) for r in new] == [(A.PENDING, None)], new
    a = w.attach(new[0][0])
    assert a is None or a[0] is None, ("нового вложения нет", a)
    for word in (T.CONTRACT_WORDS, K.MONEY_CLAIM_WORDS, T.SUMS_WORDS):
        assert word not in (new[0][3] or ""), (word, new[0][3])
    assert len(w.signed_drafts()) == 1 and len(w.door.media) == 1, (w.signed_drafts(), w.door.media)


def test_c05_whatsapp_status_ladder_of_pdf_wamid_only():
    """Ранг read > delivered > sent по wamid ЧАСТИ PDF: sent — «принят, получение не подтверждено»; delivered —
    «получен телефоном ЧЧ:ММ»; прочитанный ТЕКСТ — не прочтение PDF; read PDF — «прочитан ЧЧ:ММ»."""
    w = World()
    card_sent(w)
    status(w, "wamid.P1", "sent", T_PRESS + 5)
    w.tick(T_SIGN + 730)
    wl = line(block(w, now=T_SIGN + 740), "WhatsApp")
    assert "принят" in wl and "прочитан" not in wl and "получен телефоном" not in wl, wl
    status(w, "wamid.P1", "delivered", T_SIGN + 780)                                  # 19:17
    w.tick(T_SIGN + 795)
    wl = line(block(w, now=T_SIGN + 800), "WhatsApp")
    assert ("получен телефоном " + hm(T_SIGN + 780)) in wl and "прочитан" not in wl, wl
    status(w, "wamid.T1", "read", T_SIGN + 840)                                       # прочитан ТЕКСТ, не PDF
    w.tick(T_SIGN + 860)
    wl = line(block(w, now=T_SIGN + 870), "WhatsApp")
    assert "прочитан" not in wl and "получен телефоном" in wl, wl
    status(w, "wamid.P1", "read", T_READ)                                             # 19:19
    w.tick(T_SIGN + 930)
    b = block(w, now=T_SIGN + 940)
    assert ("прочитан " + hm(T_READ)) in line(b, "WhatsApp"), b
    clean(b)


def test_c06_pdf_not_sent_or_failed_never_called_delivered():
    """п.4: PDF не ушёл дверью (not_sent) или провайдер вернул failed → в блоке «не ушёл» / «не дошёл»; слов доставки
    («получен телефоном», «прочитан») нет."""
    w = World()
    did = W._card(w)
    w.door.media_out = "not_sent"
    w.clock.t = float(T_PRESS)
    w.core.press(did, 1, A.ACT_SEND, STAFF, T_PRESS)
    assert w.q("SELECT state FROM pdf_parts WHERE draft_id=?", (did,)) == [(A.NOT_SENT,)]
    b = block(w, now=T_PRESS + 60)
    assert "не ушёл" in line(b, "PDF клиенту"), b
    assert "прочитан" not in b and "получен телефоном" not in b, b
    clean(b)
    w = World()
    did = card_sent(w)
    status(w, "wamid.P1", "failed", T_PRESS + 60)
    w.tick(T_PRESS + 120)
    assert w.q("SELECT state FROM pdf_parts WHERE draft_id=?", (did,)) == [(A.NOT_SENT,)]
    b = block(w, now=T_PRESS + 180)
    assert "не дошёл" in b or "не ушёл" in line(b, "PDF клиенту"), b
    assert "прочитан" not in b and "получен телефоном" not in b, b
    clean(b)


def test_c07_who_by_role_autosend_and_ask_line():
    """Кто отправил — только РОЛЬЮ: AUTO_WHO → «автоотправка» (не «агент: …» дословно); просьба — «чистая → карточка»."""
    w = World(autosend=True)
    w.put(T_SIGN + 60, ASK_RU)
    w.tick(T_SIGN + 600)
    sd = w.signed_drafts()
    assert len(sd) == 1 and sd[0][1] == A.SENT and len(w.door.media) == 1, (sd, w.door.media)
    b = block(w, now=T_SIGN + 700)
    pl = line(b, "PDF клиенту")
    assert ("ушёл " + hm(T_SIGN + 600)) in pl and "автоотправка" in pl and "сотрудник" not in pl, pl
    assert X.AUTO_WHO not in b and "агент:" not in b, b
    al = line(b, "просьба прислать договор")
    assert "чистая" in al and "карточк" in al, al
    clean(b, ASK_RU)
    assert M.arrival_claims(b, day(T_SIGN)) == [], M.arrival_claims(b, day(T_SIGN))


# ══ 8–14 · ожидание подписи — в базе, переживает рестарт, продолжает дело ════════════════════════════════════════

def test_c08_ask_with_empty_registry_opens_expectation_in_db():
    """п.5 (начало): явная просьба при реестре без подписанного → строка contract_expect open (why ask, upto, due_at =
    последнее входящее + 24 ч, checked_at/outcome проверки), ключи спецификации, текста клиента нет; блок называет
    «открыто с ЧЧ:ММ (просьба), реестр проверяется сам до ДД.ММ ЧЧ:ММ» и «проверен ЧЧ:ММ — подписанного не было»;
    клиенту ничего."""
    reg = W.Registry(W.live_rows()[:2])
    w = World(registry=reg)
    t_in = T_SIGN - 1800                                          # 18:34
    t_open = t_in + 600                                           # 18:44
    r = open_by(w, ASK_RU, t_in, reg)
    assert (r["number"], r["why"], r["upto_id"], r["outcome"]) == (NUM, "ask", last_in(w), "empty"), r
    assert abs(r["opened_at"] - t_open) < 1 and abs(r["checked_at"] - t_open) < 1, r
    assert abs(r["due_at"] - (t_in + A.FOLLOW_WINDOW)) < 1, (r["due_at"], t_in + A.FOLLOW_WINDOW)
    assert r["closed_at"] is None and r["closed_by"] is None, r
    info = w.q("PRAGMA table_info(contract_expect)")
    assert EXPECT_COLS <= {c[1] for c in info}, info
    assert [c[1] for c in sorted((c for c in info if c[5]), key=lambda c: c[5])] == ["number", "opened_at"], info
    idx = [x for x in w.q("PRAGMA index_list(contract_expect)") if x[2] == 1 and x[4] == 1]
    assert idx, ("уникального частичного индекса нет", w.q("PRAGMA index_list(contract_expect)"))
    assert [c[2] for c in w.q("PRAGMA index_info(%s)" % idx[0][1])] == ["number"]
    assert "open" in w.q("SELECT sql FROM sqlite_master WHERE type='index' AND name=?", (idx[0][1],))[0][0]
    dump_ = repr(w.q("SELECT * FROM contract_expect"))
    assert ASK_RU not in dump_ and "договор" not in dump_.lower(), dump_
    no_client_send(w)
    b = block(w, now=t_open + 60)
    el = line(b, "ожидание подписи")
    assert ("открыто с " + hm(t_open)) in el and "просьба" in el and dm(t_in + A.FOLLOW_WINDOW) in el, el
    rl = line(b, "реестр")
    assert hm(t_open) in rl and "подписанного не было" in rl, rl
    clean(b, ASK_RU, when=t_open)
    cols = ", ".join(c[1] for c in info if c[1] != "opened_at")
    try:                                                        # второе open по номеру — только через индекс
        w.x("INSERT INTO contract_expect(opened_at, %s) SELECT opened_at + 1, %s FROM contract_expect WHERE number=?"
            % (cols, cols), (NUM,))
        raise AssertionError("второе открытое ожидание по номеру легло")
    except sqlite3.IntegrityError as e:
        assert "UNIQUE" in str(e).upper(), e


def test_c09_signature_card_closes_expectation_in_same_transaction():
    """п.5: реестр стал FACT → карточка подписи и `card:<id>` вместе: откат транзакции вставки (второй процесс успел —
    перепроверка внутри неё) не оставляет ни карточки, ни закрытия; следующим проходом — карточка, closed card:<id> в тот
    же момент; outbox пуст; блок — «закрыто ЧЧ:ММ карточкой», «ждёт нажатия», версия «карточка подписи»."""
    reg = W.Registry(W.live_rows()[:2])
    w = World(registry=reg)
    open_by(w, ASK_RU, T_SIGN - 1800, reg)
    reg.rows.append(W.live_rows()[2])                             # стр.36 подписана 19:04
    real = w.core._signed_held

    def held(number, sha, key):
        if w.core.db.in_transaction:                              # перепроверка ВНУТРИ транзакции вставки
            return None, "стенд: второй процесс успел"
        return real(number, sha, key)
    w.core._signed_held = held
    t1 = T_SIGN + 300
    w.tick(t1)
    assert w.signed_drafts() == [] and w.versions() == [], (w.signed_drafts(), w.versions())
    r = expect_rows(w)[0]
    assert r["state"] == "open" and r["closed_by"] is None and r["closed_at"] is None, r
    del w.core._signed_held
    t2 = t1 + X.SIGNED_EVERY + 10
    w.tick(t2)
    sd = w.signed_drafts()
    assert len(sd) == 1, (sd, w.sign_lines()[-6:])
    did = sd[0][0]
    r = expect_rows(w)[0]
    assert (r["state"], r["closed_by"]) == ("closed", "card:%d" % did) and abs(r["closed_at"] - t2) < 1, r
    created = w.q("SELECT created_at FROM drafts WHERE id=?", (did,))[0][0]
    assert abs(created - r["closed_at"]) < 1, (created, r)
    no_client_send(w)
    b = block(w, now=t2 + 60)
    el = line(b, "ожидание подписи")
    assert ("закрыто " + hm(t2)) in el and "карточк" in el, el
    assert "ждёт нажатия" in line(b, "PDF клиенту"), b
    vl = line(b, "версия")
    assert "подписан 14.10 19:04" in vl and "карточка подписи" in vl, vl
    clean(b, ASK_RU)


def test_c10_signed_claim_expectation_checks_each_pass_beyond_memo_pause():
    """«Подписал» при пустом реестре: без флага (прод) после трёх «договора нет» номер ждёт SIGNED_IDLE — 4 прохода дают
    3 чтения реестра; с ожиданием (why signed_claim) первые ASK_EAGER_SEC — КАЖДЫЙ проход (4 из 4), checked_at/outcome
    последней проверки; дальше — не чаще SIGNED_IDLE."""
    def run(cstate):
        reg = W.Registry(W.live_rows()[:2])
        w = World(registry=reg, cstate=cstate)
        t_in = T_SIGN - 3000
        w.put(t_in, CLAIM)
        ts = [t_in + 600 + i * 130 for i in range(4)]
        for t in ts:
            w.tick(t)
        return w, reg, ts
    _w0, reg0, _ts = run(None)
    assert len(reg0.calls) == 3, ("стенд: прод после трёх пустых ждёт паузу", reg0.calls)
    w, reg, ts = run(True)
    assert len(reg.calls) == 4, ("ожидание держит частую проверку вопреки паузе номера", reg.calls)
    r = expect_rows(w)[0]
    assert (r["why"], r["state"], r["outcome"]) == ("signed_claim", "open", "empty") and abs(r["checked_at"] - ts[-1]) < 1
    n = len(reg.calls)
    t0 = r["opened_at"] + X.ASK_EAGER_SEC + 100
    for i in range(5):                                            # 520 с < SIGNED_IDLE после окна частой проверки
        w.tick(t0 + i * 130)
    assert len(reg.calls) - n <= 1, ("после ASK_EAGER_SEC — не чаще SIGNED_IDLE", reg.calls[n:])
    assert w.signed_drafts() == [] and expect_rows(w)[0]["state"] == "open"
    no_client_send(w)


def test_c11_restart_keeps_expectation_and_closes_on_signature():
    """п.6: между открытием и подписью ядро и адаптер пересозданы на тех же файлах — ожидание то же (opened_at, одна
    строка), блок нового адаптера называет прежнее «открыто с ЧЧ:ММ», реестр проверяется, подпись → карточка и
    closed card:<id>."""
    reg = W.Registry(W.live_rows()[:2])
    w = World(registry=reg)
    t_in = T_SIGN - 3000
    t_open = t_in + 600
    r0 = open_by(w, CLAIM, t_in, reg)
    w.tick(t_open + 130)
    el0 = line(block(w, now=t_open + 200), "ожидание подписи")
    assert ("открыто с " + hm(t_open)) in el0 and "клиент сообщил о подписи" in el0, el0
    w.restart()
    assert [x["opened_at"] for x in expect_rows(w)] == [r0["opened_at"]]
    el1 = line(block(w, now=t_open + 260, ad=w.reader()), "ожидание подписи")
    assert ("открыто с " + hm(t_open)) in el1, el1
    n = len(reg.calls)
    w.tick(t_open + 400)
    assert len(reg.calls) == n + 1, "после рестарта реестр проверяется"
    reg.rows.append(W.live_rows()[2])
    t_sig = T_SIGN + 300
    w.tick(t_sig)
    sd = w.signed_drafts()
    assert len(sd) == 1, (sd, w.sign_lines()[-6:])
    rows = expect_rows(w)
    assert len(rows) == 1 and rows[0]["opened_at"] == r0["opened_at"], rows
    assert (rows[0]["state"], rows[0]["closed_by"]) == ("closed", "card:%d" % sd[0][0]), rows
    assert abs(rows[0]["closed_at"] - t_sig) < 1, rows
    no_client_send(w)


def test_c12_expired_after_due_marked_in_block():
    """п.7: срок вышел (последнее входящее + 24 ч) → expired и строка журнала (без номера и текста клиента); после
    закрытия окна реестр не дёргается; блок — «истекло», а не «открыто»."""
    reg = W.Registry(W.live_rows()[:2])
    w = World(registry=reg)
    t_in = T_SIGN - 3000
    r = open_by(w, CLAIM, t_in, reg)
    due = r["due_at"]
    w.tick(due - 600)                                             # окно закрыто, срок не вышел
    assert expect_rows(w)[0]["state"] == "open"
    n_calls, n_lines = len(reg.calls), len(w.lines)
    w.tick(due + 120)
    w.tick(due + 120 + X.SIGNED_EVERY + 10)
    r = expect_rows(w)[0]
    assert r["state"] == "expired", r
    said = w.lines[n_lines:]                                      # слова строки спецификация не задаёт — только факт
    assert [ln for ln in said if re.search(r"исте[кёч]|expired|срок", ln, re.I)], said
    for ln in w.lines:
        assert NUM not in ln and CLAIM not in ln, ln
    assert len(reg.calls) == n_calls, "окно закрыто — дверей нет"
    b = block(w, now=due + 300)
    el = line(b, "ожидание подписи")
    assert "истекло" in el and "открыто" not in el, el
    clean(b, CLAIM, when=due)


def test_c13_timeout_and_refused_do_not_close():
    """Проверка с открытым ожиданием пишет checked_at и outcome; timeout и refused ожидание НЕ закрывают; после них —
    подпись → карточка и closed card:<id>."""
    reg = ErrRegistry(W.live_rows()[:2])
    w = World(registry=reg)
    t_in = T_SIGN - 1200
    open_by(w, CLAIM, t_in, reg)
    reg.fail = T.last9(NUM)                                        # таймаут двери реестра
    t2 = t_in + 730
    w.tick(t2)
    r = expect_rows(w)[0]
    assert (r["state"], r["outcome"]) == ("open", "timeout") and abs(r["checked_at"] - t2) < 1, r
    reg.fail, reg.err = None, "upstream_error"                     # отказ моста
    t3 = t2 + 130
    w.tick(t3)
    r = expect_rows(w)[0]
    assert (r["state"], r["outcome"]) == ("open", "refused") and abs(r["checked_at"] - t3) < 1, r
    reg.err = None
    reg.rows.append(W.live_rows()[2])
    t4 = T_SIGN + 120
    w.tick(t4)
    sd = w.signed_drafts()
    assert len(sd) == 1, (sd, w.sign_lines()[-6:])
    r = expect_rows(w)[0]
    assert (r["state"], r["closed_by"]) == ("closed", "card:%d" % sd[0][0]), r
    no_client_send(w)


def test_c14_human_document_closes_as_held_and_named_without_content():
    """Документ после подписи отправил человек из темы → карточки нет, ожидание закрыто «held»; блок — «документ
    человека: ЧЧ:ММ (какой — не видно)», без текста строки outbox."""
    reg = W.Registry(W.live_rows()[:2])
    w = World(registry=reg)
    open_by(w, CLAIM, T_SIGN - 1200, reg)
    t_doc = T_SIGN + 200                                          # 19:07
    w.x("INSERT INTO outbox(wamid, number, ts, text, via, kind) VALUES('wamid.H1',?,?,'[документ]',?,'document')",
        (NUM, t_doc, A.VIA_TOPIC))
    reg.rows.append(W.live_rows()[2])
    t_k = T_SIGN + 300
    w.tick(t_k)
    assert w.signed_drafts() == [] and [v[5] for v in w.versions()] == [None], (w.versions(), w.sign_lines()[-4:])
    r = expect_rows(w)[0]
    assert (r["state"], r["closed_by"]) == ("closed", "held") and abs(r["closed_at"] - t_k) < 1, r
    b = block(w, now=t_k + 60)
    hl = line(b, "документ человека")
    assert hm(t_doc) in hl and "какой — не видно" in hl, hl
    assert "[документ]" not in b, b
    clean(b, CLAIM)
    assert w.door.sends == [] and w.door.media == []


# ══ 15–17 · чужое не протекает; база не прочитана; нечего сказать — запрос прежний ═════════════════════════════

def test_c15_foreign_numbers_same_last9_never_in_block():
    """п.8: у двух других клиентов (C — с ТЕМИ ЖЕ последними 9 цифрами, что у A, но свой договор с явным кодом страны
    +66; B — другой номер) карточки, отправки, прочтения и документ человека; у клиента A записей нет, он спрашивает о
    договоре со словом-меткой → в блоке A нет ни doc, ни времени, ни статусов чужих, ни метки, ни 9+ цифр. Блоки самих
    B и C свои факты называют (проверка не пустая)."""
    row_c = W.reg_row(50, "ПОДПИСАН", "2026-10-14 18:50", "PDF50", bike=BIKE_C, phone="+66 99 996 6963")
    book = [W.book_row(bike=BIKE_C, contacts=CONTACTS_C, booking="B7712"),
            W.book_row(bike=W.BIKE2, contacts=W.CONTACTS2, booking="B5580")]
    w = World(rows=[row_c, W.row_num2()], book=book)
    w.pdfs.files["PDF50"] = (50, PDF50)
    w.put(T_SIGN + 60, "Подписал договор", number=NUM_SAME9)
    w.put(T_SIGN + 70, CLAIM, number=NUM2)
    w.tick(T_SIGN + 600)
    cards = {n: d for d, n in w.q("SELECT id, number FROM drafts WHERE kind=?", (X.KIND_SIGNED,))}
    assert set(cards) == {NUM_SAME9, NUM2}, (cards, w.sign_lines()[-6:])
    w.clock.t = float(T_PRESS)
    for n in (NUM_SAME9, NUM2):
        assert w.core.press(cards[n], 1, A.ACT_SEND, STAFF, T_PRESS)["ok"]
    wam = dict(w.q("SELECT d.number, p.wamid FROM pdf_parts p JOIN drafts d ON d.id=p.draft_id"))
    for n in (NUM_SAME9, NUM2):
        status(w, wam[n], "read", T_READ, number=n)
    w.tick(T_READ + 10)
    w.x("INSERT INTO outbox(wamid, number, ts, text, via, kind) VALUES('wamid.H9',?,?,'[документ]',?,'document')",
        (NUM_SAME9, T_SIGN + 1000, A.VIA_TOPIC))
    mark = "Квазимодо"
    uid = w.put(T_SIGN + 1500, "А договор где? Это %s из 12-го номера" % mark)
    now = T_SIGN + 1560
    w.clock.t = float(now)
    b, user, _base, _info = blk(w.reader(), NUM, uid, now)
    assert b is not None, "вопрос о договоре — блок есть и без записей"
    assert mark in user, "стенд: метка в запросе модели есть (история) — только не в блоке"
    body = "\n".join(b.split("\n")[1:])
    assert not re.search(r"\d{1,2}:\d{2}", body), ("у A нет ни одной записи — времени в строках быть не может", b)
    for bad in ("D50", "D40", "18:50", "19:10", "прочитан", "получен телефоном", "сотрудник", mark, "Сомчай"):
        assert bad not in b, (bad, b)
    clean(b, mark, "А договор где?")
    for n, signed in ((NUM_SAME9, "подписан 14.10 18:50"), (NUM2, "подписан 14.10 19:10")):
        bn = block(w, number=n, now=now)
        assert signed in line(bn, "версия") and "прочитан" in line(bn, "WhatsApp"), (n, bn)


def test_c16_unreadable_base_is_unknown_and_draft_still_built():
    """п.9: таблиц нет · вместо базы мусор · база заперта → строки «неизвестно», ни «в базе нет», ни времени фактов;
    чтение ждёт не дольше своего таймаута (2 с, не 10); черновик всё равно строится, блок в голове хода."""
    w = World()
    uid = w.put(T_SIGN + 60, CLAIM)
    now = T_SIGN + 120
    w.clock.t = float(now)
    d = tempfile.mkdtemp(prefix="wa_cstate_unread_")
    empty, junk = os.path.join(d, "agent_empty.db"), os.path.join(d, "agent_junk.db")
    sqlite3.connect(empty).close()
    with open(junk, "wb") as f:
        f.write(b"this is not an sqlite database " * 64)
    for path in (empty, junk):
        s = Script(final("Спасибо, проверяю договор."))
        ad = w.reader(script=s, agent_db=path)
        b, _u, _b0, info = blk(ad, NUM, uid, now)
        assert b is not None, path
        body = "\n".join(b.split("\n")[1:])                    # шапка сама несёт оба слова — судятся строки фактов
        assert "неизвестно" in body and "в базе нет" not in body, (path, b)
        assert not re.search(r"\d{1,2}:\d{2}", body), b
        assert info.get("cstate"), info.get("cstate")
        got = ad.draft(NUM, uid)
        assert isinstance(got, dict) and got.get("text") == "Спасибо, проверяю договор.", got
        assert s.seen and seen_block(s.seen[0]) == b, "блок в голове хода — тот же"
    s = Script(final("Спасибо!"))
    ad = w.reader(script=s)
    ad._history = lambda number, upto_id: M.wa_history.read_history(number, ad.queue_db, "", "", "",
                                                                    trig=int(upto_id) + 1, sent_db=None)
    lock = sqlite3.connect(w.dbpath, timeout=1, isolation_level=None)
    lock.execute("BEGIN EXCLUSIVE")
    try:
        t0 = time.monotonic()
        _s1, u1, _i1 = ad.build(NUM, uid, now=now)
        dt = time.monotonic() - t0
        got = ad.draft(NUM, uid)
    finally:
        lock.execute("ROLLBACK")
        lock.close()
    b = u1.split("\n\nСЕГОДНЯ: ", 1)[0]
    body = "\n".join(b.split("\n")[1:])
    assert b.startswith("ДОГОВОР КЛИЕНТА") and "неизвестно" in body and "в базе нет" not in body, b
    assert dt < 8, ("чтение запертой базы держало сборку %.1f с" % dt)
    assert isinstance(got, dict) and got.get("text") == "Спасибо!", got


def test_c17_no_records_not_about_contract_user_byte_equal():
    """п.10: записей по номеру нет и вопрос не о договоре → system и user побайтно равны базовым."""
    reg = W.Registry([])
    w = World(registry=reg)
    uid = w.put(T_SIGN + 60, NEUTRAL)
    w.tick(T_SIGN + 600)
    assert w.signed_drafts() == [] and expect_rows(w) == [] and len(reg.calls) == 1, (reg.calls, expect_rows(w))
    assert not _cs().topic(NEUTRAL)
    ad = w.reader()
    now = T_SIGN + 660
    s1, u1, i1 = ad.build(NUM, uid, now=now)
    s0, u0, i0 = M.ModelAdapter.build(ad, NUM, uid, now=now)
    assert (s1, u1) == (s0, u0), u1[:300]
    assert i1["user_chars"] == i0["user_chars"] == len(u0)


# ══ 18–22 · флаг выкл — байт-в-байт прежнее ═════════════════════════════════════════════════════════════════════

def test_c18_flag_off_adapter_byte_equal_and_followup_untouched():
    """cstate_on=False: build — ровно результат родителя (system, user, info), сверка — те же запросы и тот же ответ,
    что у прежнего `ModelAdapter`; при вкл тот же мир блок даёт (чувствительность); напоминание — как у родителя."""
    w = World()
    card_sent(w)
    status(w, "wamid.P1", "read", T_READ)
    w.tick(T_READ + 10)
    uid = w.put(T_SIGN + 1500, WHERE)
    now = T_SIGN + 1560
    w.clock.t = float(now)
    b, _u, _b0, _i = blk(w.reader(), NUM, uid, now)
    assert b, "чувствительность: при вкл блок есть"
    off = w.reader()
    off.cstate_on = False
    assert off.build(NUM, uid, now=now) == M.ModelAdapter.build(off, NUM, uid, now=now)
    answers = ({"tool": "contract", "args": {}}, final("Договор у вас в этом чате."))
    s_off, s_base = Script(*answers), Script(*answers)
    a_off = w.reader(script=s_off)
    a_off.cstate_on = False
    a_base = w.reader(script=s_base, cls=M.ModelAdapter)
    g_off, g_base = a_off.draft(NUM, uid), a_base.draft(NUM, uid)
    assert len(s_base.seen) == 2 and s_off.seen == s_base.seen, "сверка при выкл — те же запросы"
    assert g_off == g_base, (g_off, g_base)
    assert w.reader().build_followup(NUM, uid, now=now) == \
        w.reader(cls=M.ModelAdapter).build_followup(NUM, uid, now=now), "напоминание блока не видит"


def test_c19_flag_off_core_no_table_same_story():
    """Ядро без аргумента (прод) и с cstate=False: таблицы contract_expect нет, частота чтения реестра, карточки, нажатие,
    база и журнал — одинаковы байт-в-байт."""
    def story(**kw):
        reg = W.Registry(W.live_rows()[:2])
        w = World(registry=reg, **kw)
        t_in = T_SIGN - 3000
        w.put(t_in, CLAIM)
        for i in range(4):
            w.tick(t_in + 600 + 130 * i)
        reg.rows.append(W.live_rows()[2])
        w.tick(T_SIGN + 300)
        sd = w.signed_drafts()
        assert len(sd) == 1, sd
        w.clock.t = float(T_SIGN + 400)
        assert w.core.press(sd[0][0], 1, A.ACT_SEND, STAFF, T_SIGN + 400)["ok"]
        return w, reg
    w0, r0 = story(cstate=None)
    w1, r1 = story(cstate=False)
    for w in (w0, w1):
        assert "contract_expect" not in tables(w.dbpath), tables(w.dbpath)
    assert r0.calls == r1.calls and len(r0.calls) == 5, (r0.calls, r1.calls)
    assert dump(w0.dbpath) == dump(w1.dbpath)
    assert w0.lines == w1.lines
    assert (w0.door.sends, w0.door.media) == (w1.door.sends, w1.door.media)


def svc(environ, cls):
    """Служба `wa_agent_svc.build` на подделках (Bot API, провайдер) с адаптером класса cls и дверями сверки стенда."""
    import test_wa_agent_svc as SV
    d = tempfile.mkdtemp(prefix="wa_cstate_svc_")
    env = {"queue_db": os.path.join(d, "svc_q.db"), "mirror_db": os.path.join(d, "mirror.db"),
           "agent_db": os.path.join(d, "svc_agent.db"), "tg_token": SV.TOKEN, "show_chat": SV.SHOW,
           "log_path": os.path.join(d, "wa_agent.log")}
    q = sqlite3.connect(env["queue_db"])
    q.execute(SV.QSCHEMA)
    q.commit()
    q.close()
    m = sqlite3.connect(env["mirror_db"])
    m.execute("CREATE TABLE topics (number TEXT PRIMARY KEY, thread_id INTEGER, trigger_id INTEGER, "
              "stage TEXT, ts REAL, name TEXT)")
    m.execute("CREATE TABLE shown (key TEXT PRIMARY KEY, number TEXT, state TEXT, ts REAL, msg_id INTEGER, "
              "solo INTEGER)")
    m.commit()
    m.close()
    clock = SV.Clock(T_START)
    model = cls(env["queue_db"], Script(), book=W.Book([W.book_row()]), clock=clock, agent_db=env["agent_db"],
                log=lambda s: None, tools={"cash": _no_cash, "contract": W.Registry(), "contract_pdf": W.Pdfs()})
    lines = []
    core, _tg, _flags, _words = S.build(
        env, environ=dict(environ), model=model, http=SV.FakeHttp(clock),
        send=lambda to, text, db_path=None: {"outcome": "not_sent", "reason": "набор не шлёт", "wamid": None},
        send_media=lambda to, media, db_path=None: {"outcome": "not_sent", "reason": "набор не шлёт", "wamid": None},
        clock=clock, line=lines.append)
    return core, lines, model, env


def test_c20_flag_off_service_and_flag_rule():
    """Служба: флаг не запрошен — ни строки старта, ни таблицы, вызов make_model прежней формы, cstate_of → (None,)*3;
    запрошен без карточки подписи — «не засчитан», адаптер выключен, таблицы нет; засчитан (карточка подписи и сверка) —
    таблица и строка старта; models_of кладёт cstate только при флаге И WA_AGENT_TOOLS."""
    core, lines, _m, env = svc(dict(SVC_ON, WA_AGENT_SIGNED_CARD="1"), M.ModelAdapter)
    assert isinstance(core, X.AttachCore) and core.signed, type(core)
    assert not [ln for ln in lines if "WA_AGENT_CONTRACT_STATE" in ln], lines
    assert "contract_expect" not in tables(env["agent_db"])
    assert S.F_CSTATE == "WA_AGENT_CONTRACT_STATE" and S.F_CSTATE not in S.FLAGS
    seen = []
    real = S.make_model

    def fake(env_, **kw):
        seen.append(dict(kw))
        return None, "стенд"
    S.make_model = fake
    try:
        base = {"WA_AGENT_DRAFTS": "1", "WA_AGENT_TOOLS": "1"}
        for environ, want in ((base, None), (dict(base, WA_AGENT_CONTRACT_STATE="1"), True),
                              ({"WA_AGENT_DRAFTS": "1", "WA_AGENT_CONTRACT_STATE": "1"}, None)):
            del seen[:]
            S.models_of({}, environ)
            assert len(seen) == 1, seen
            if want is None:
                assert "cstate" not in seen[0], (environ, seen[0])
            else:
                assert seen[0].get("cstate") is True, (environ, seen[0])
        del seen[:]
        S.models_of({}, base)
        assert set(seen[0]) == {"lessons", "book", "cache", "tools"}, seen[0]
    finally:
        S.make_model = real
    w = World(cstate=None)
    ad = w.reader()
    for environ in ({}, {"WA_AGENT_CONTRACT_STATE": "0"}, {"WA_AGENT_CONTRACT_STATE": ""}):
        assert S.cstate_of(environ, True, ad) == (None, None, None), environ
    assert getattr(ad, "cstate_on", None) is not False
    ad2 = w.reader()
    res = S.cstate_of({"WA_AGENT_CONTRACT_STATE": "1", "WA_AGENT_TOOLS": "1"}, False, ad2)
    assert ad2.cstate_on is False and any(isinstance(x, str) and "не засчитан" in x for x in res), res
    ad3 = w.reader()
    res = S.cstate_of({"WA_AGENT_CONTRACT_STATE": "1", "WA_AGENT_TOOLS": "1"}, True, ad3)
    assert getattr(ad3, "cstate_on", None) is not False, res
    assert res[0] is True or any(isinstance(x, dict) and x.get("cstate") is True for x in res), res
    kw3 = next((x for x in res if isinstance(x, dict)), None)    # стенд собирает ядро так же — сверка формы с живой службой
    assert kw3 is not None and kw3.get("claim_of") is _cs().signed_claim, res
    assert any(isinstance(x, str) and x for x in res), res
    core, lines, m, env = svc(dict(SVC_ON, WA_AGENT_SIGNED_CARD="1", WA_AGENT_CONTRACT_STATE="1"),
                              _c().ContractStateAdapter)
    assert "contract_expect" in tables(env["agent_db"]) and m.cstate_on is not False, lines
    assert [ln for ln in lines if "WA_AGENT_CONTRACT_STATE" in ln], lines
    core, lines, m, env = svc(dict(SVC_ON, WA_AGENT_CONTRACT_STATE="1"), _c().ContractStateAdapter)
    assert m.cstate_on is False and "contract_expect" not in tables(env["agent_db"])
    said = [ln for ln in lines if "WA_AGENT_CONTRACT_STATE" in ln]
    assert said and any("не засчитан" in ln for ln in said), said


def probe_off_imports():
    """Отдельный процесс без новых модулей: служба с карточкой подписи (флаг состояния не запрошен), ядро стенда без
    аргумента cstate на пути, где ожидание открылось бы и закрылось, сверка прежнего адаптера, models_of → печать
    загруженных новых модулей."""
    core, _lines, _m, env = svc(dict(SVC_ON, WA_AGENT_SIGNED_CARD="1"), M.ModelAdapter)
    reg = W.Registry(W.live_rows()[:2])
    w = World(registry=reg, cstate=None, model_cls=M.ModelAdapter)
    uid = w.put(T_SIGN - 1800, CLAIM)
    w.tick(T_SIGN - 1200)
    reg.rows.append(W.live_rows()[2])
    w.tick(T_SIGN + 300)
    w.reader(script=Script({"tool": "contract", "args": {}}, final("Спасибо!"))).draft(NUM, uid)
    real = S.make_model
    S.make_model = lambda env_, **kw: (None, "стенд")
    try:
        S.models_of({}, {"WA_AGENT_DRAFTS": "1", "WA_AGENT_TOOLS": "1"})
    finally:
        S.make_model = real
    mods = sorted(m for m in NEW_MODULES if m in sys.modules)
    sys.stdout.write(PROBE_MARK + json.dumps(mods) + "\n")
    sys.stdout.flush()
    return 0


def test_c21_flag_off_process_has_no_new_modules():
    """В выключенном состоянии новых модулей нет в процессе вовсе (импорт — только в ветках флага)."""
    p = subprocess.run([sys.executable, os.path.abspath(__file__), PROBE_ARG], cwd=ROOT, capture_output=True,
                       timeout=300, env=dict(os.environ))
    text = p.stdout.decode("utf-8", "replace")
    got = [ln for ln in text.splitlines() if ln.startswith(PROBE_MARK)]
    assert p.returncode == 0 and len(got) == 1, (p.returncode, text[-1500:], p.stderr.decode("utf-8", "replace")[-1500:])
    assert json.loads(got[0][len(PROBE_MARK):]) == [], got


def test_c22_pinned_blobs_and_defaults_untouched():
    """wa_agent*.py, wa_agent_knowledge.py и rental_case.py — блобы a1dcbe5 (git hash-object); блок инструментов прежний;
    автоотправка по умолчанию выключена."""
    for name, sha in PINS.items():
        with open(os.path.join(ROOT, name), "rb") as f:
            data = f.read()
        assert hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest() == sha, name
    assert hashlib.sha256(T.TOOLS_BLOCK.encode("utf-8")).hexdigest() == TOOLS_BLOCK_SHA
    w = World(cstate=None)                                        # прод-вызов ядра: автоотправки нет
    assert w.core.autosend is False and S.autosend_of({}, True)[0] is False


# ══ 23–25 · форма блока, устаревшее и актуальная версия ═════════════════════════════════════════════════════════

def test_c23_block_shape_header_size_no_claims():
    """Самый полный блок (просьба → ожидание → подпись → карточка → «Отправить» → прочитан → новый вопрос): шапка
    дословно с временем чтения, строки версии, PDF, WhatsApp, просьбы и ожидания по одной; ≤ 8 строк и 1200 знаков; даты
    «ДД.ММ ЧЧ:ММ»; без «достав», сумм, номеров, имён и текста клиента; `info` пересчитан и несёт cstate."""
    reg = W.Registry(W.live_rows()[:2])
    w = World(registry=reg)
    open_by(w, ASK_RU, T_SIGN - 1800, reg)
    reg.rows.append(W.live_rows()[2])
    w.tick(T_SIGN + 300)
    did = w.signed_drafts()[0][0]
    w.clock.t = float(T_PRESS)
    assert w.core.press(did, 1, A.ACT_SEND, STAFF, T_PRESS)["ok"]
    status(w, "wamid.P1", "sent", T_PRESS + 30)
    status(w, "wamid.P1", "read", T_READ)
    w.tick(T_READ + 10)
    uid = w.put(T_SIGN + 1200, WHERE)
    now = T_SIGN + 1260
    w.clock.t = float(now)
    b, user, _base, info = blk(w.reader(), NUM, uid, now)
    assert b is not None
    rows = b.split("\n")
    assert rows[0] == HEADER % dm(now), rows[0]
    for label in ("версия", "PDF клиенту", "WhatsApp", "просьба прислать договор", "ожидание подписи"):
        assert len([ln for ln in rows if (label + ":") in ln]) == 1, (label, b)
    assert "подписан 14.10 19:04" in line(b, "версия")
    assert ("ушёл " + hm(T_PRESS)) in line(b, "PDF клиенту") and ("прочитан " + hm(T_READ)) in line(b, "WhatsApp")
    assert "закрыто" in line(b, "ожидание подписи"), b
    clean(b, ASK_RU, WHERE)
    assert info.get("cstate") and info["user_chars"] == len(user)


def test_c24_stale_status_older_than_7_days_marked():
    """Устаревший факт помечен: PDF ушёл 8 суток назад, статусов нет (старше STATUS_DAYS не собираются) → «старше 7
    суток», не «прочитан/получен»; свежий PDF без статуса этой пометки не несёт. Блок есть и при вопросе не о договоре —
    записи по номеру есть."""
    w = World()
    card_sent(w)
    fresh = T_PRESS + 3600
    w.put(fresh - 60, NEUTRAL)
    wl = line(block(w, now=fresh), "WhatsApp")
    assert "старше 7 суток" not in wl and "прочитан" not in wl and "получен телефоном" not in wl, wl
    later = T_PRESS + 8 * 86400
    w.put(later - 60, NEUTRAL)
    w.clock.t = float(later)
    b = block(w, now=later)
    wl = line(b, "WhatsApp")
    assert "старше 7 суток" in wl and "прочитан" not in wl and "получен телефоном" not in wl, wl
    assert "ушёл" in line(b, "PDF клиенту"), b
    clean(b, NEUTRAL, when=later)


def test_c25_actual_version_after_new_signature():
    """Актуальная версия: стр.36 ушла, затем отозвана, подписана стр.37 (21:30) → блок называет 37 и её PDF «ждёт
    нажатия», а не прежнюю 36 и её «ушёл»."""
    w = World()
    card_sent(w)
    w.registry.revoke(36)
    w.registry.rows.append(W.reg_row(37, "ПОДПИСАН", "2026-10-14 21:30", "PDF37"))
    t = W.phuket(2026, 10, 14, 21, 40)
    w.tick(t)
    assert len(w.signed_drafts()) == 2, w.signed_drafts()
    b = block(w, now=t + 60)
    vl = line(b, "версия")
    assert "подписан 14.10 21:30" in vl and "…D37" in vl and "19:04" not in vl and "D36" not in vl, vl
    assert "ждёт нажатия" in line(b, "PDF клиенту"), b
    clean(b, when=t)


def main():
    if PROBE:
        return probe_off_imports()
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
