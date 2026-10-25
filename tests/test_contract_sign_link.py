#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ESIGNLINK2510 · команда Splinter «договор»: одна ссылка клиенту на подпись (та же, что у TB e-Sign) и рядом правка.

Ручка CONTRACT_SIGN_LINK (по умолчанию ВЫКЛ). Выкл — ответ «✅ Договор готов: <url>» прежний байт-в-байт, мост
`contract_find` не зовётся, модуль `contract_sign_link` в процесс не загружается (отдельный процесс-проба). Вкл — сразу
«договор готов» со ссылкой на правку (без превью ссылок), затем фоновая досылка: чтение реестра `contract_find(doc_id=…)`
по расписанию `contract_sign_link.offsets()` до первого решения; ссылка — только годная ссылка TB e-Sign ЭТОГО документа.

Сквозной контракт: ответы двери — снимки её же харнесса (`tests/contract_door_gs_harness.js --snap`, секция 21: реестр
TB e-Sign 0.2.2 и реестр до 0.2.2), а не выдуманные словари. Мост — подделка со счётчиком; Telegram (`splinter._send`) —
запись; настоящий `_send` проверяется на подделке `context.bot` (превью выключено только по просьбе). Сети, моста,
Telegram и файлов вне временного каталога нет. Данные синтетические."""
import ast
import asyncio
import json
import logging
import os
import subprocess
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ.setdefault("BOT_TOKEN", "x")
FLAG = "CONTRACT_SIGN_LINK"
os.environ.pop(FLAG, None)

PROBE_ARG = "--probe-sign-link-off"
PROBE_MARK = "ESIGNLINK_OFF "
PROBE = PROBE_ARG in sys.argv[1:]

try:                                       # spend_ledger/bridge_client берут fcntl (только Linux): на ПК — подмены
    import fcntl  # noqa: F401
except ImportError:
    sys.modules.setdefault("spend_ledger", types.SimpleNamespace(cost_usd=lambda model, i, o: 0.0,
                                                                 meter=lambda *a, **k: None))
    sys.modules.setdefault("fcntl", types.SimpleNamespace(LOCK_EX=2, LOCK_SH=1, LOCK_UN=8, LOCK_NB=4,
                                                          flock=lambda *a, **k: None))

import splinter as S  # noqa: E402

DOC_N = "1LinkNew0000000000000000000000000000000000001"          # = харнесс двери, секция 21
EDIT_MAKE = "https://docs.google.com/document/d/%s/edit?usp=drivesdk" % DOC_N
OK_MAKE = {"ok": True, "name": "Тест Тестов 25.10.2026", "url": EDIT_MAKE, "file_id": DOC_N,
           "flags": {"km_request": False}}
REMINDER = "Проверь перед печатью: топливо, время выдачи, пробег."
OLD_TEXT = "🐀 Splinter\n✅ Договор готов: %s\n%s" % (EDIT_MAKE, REMINDER)
INTAKE = S.INTAKE_CHAT


def C():
    """Модуль решений — лениво: процесс-проба выключенной ручки не должен его видеть."""
    import contract_sign_link
    return contract_sign_link


def snap(name):
    import contract_door_snaps
    return contract_door_snaps.snap(name)


class Bridge:
    """Поддельный мост: make_contract — заданный ответ; contract_find — ответы по очереди (последний повторяется,
    исключение в очереди — бросается); каждый вызов — в `calls`."""

    def __init__(self, make=None, finds=()):
        self.calls, self.make, self.finds = [], dict(make or OK_MAKE), list(finds)

    def issue_write_ticket(self):
        self.calls.append(("issue_write_ticket", {}))
        return {"ok": True, "ticket": "t-1"}

    def make_contract(self, **kw):
        self.calls.append(("make_contract", kw))
        return dict(self.make)

    def contract_find(self, **kw):
        self.calls.append(("contract_find", kw))
        n = sum(1 for c, _ in self.calls if c == "contract_find")
        r = self.finds[min(n, len(self.finds)) - 1] if self.finds else {"ok": False, "error": "стенд"}
        if isinstance(r, BaseException):
            raise r
        return json.loads(json.dumps(r))

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)

        def call(*a, **k):
            self.calls.append((name, k))
            return {"ok": False, "error": "стенд"}
        return call

    def args(self, name):
        return [k for c, k in self.calls if c == name]


class Logs(logging.Handler):
    def __init__(self):
        logging.Handler.__init__(self)
        self.lines = []

    def emit(self, record):
        self.lines.append(record.getMessage())


LOGS = Logs()
for _name in ("turbobaby", "splinter"):
    logging.getLogger(_name).addHandler(LOGS)
    logging.getLogger(_name).setLevel(logging.INFO)

REAL_SEND = S._send
SENDS = []


SEND_HOOK = []          # r2: подмена поведения отправки на один тест (поднять исключение / повиснуть)


async def _rec_send(context, *, chat_id, text, message_thread_id=None, **k):
    if SEND_HOOK:
        await SEND_HOOK[0](text)
    SENDS.append(dict(k, text=text, chat_id=chat_id, thread=message_thread_id))
    return types.SimpleNamespace(message_id=len(SENDS))     # как у Telegram: отправленное сообщение, не None


S._send = _rec_send


class _U:
    def __init__(self, uname="deramor"):
        self.username, self.is_bot, self.id = uname, False, 1


class Msg:
    def __init__(self, text, uname="deramor"):
        self.text, self.caption, self.photo = text, None, None
        self.chat_id, self.message_thread_id = INTAKE, None
        self.message_id, self.from_user, self.reply_to_message = 777, _U(uname), None


def flag(on):
    if on:
        os.environ[FLAG] = "1"
    else:
        os.environ.pop(FLAG, None)


def intake(bridge, on, offs=(0, 0, 0), text="договор Тест Тестов 25.10.2026"):
    """Одна команда «договор …» во «Входящих бронях»; фоновая досылка дожидается здесь же.
    → (сообщения, сколько сообщений было к возврату обработчика, сколько досылок ждало, новые строки журнала)."""
    flag(on)
    SENDS.clear()
    S._INTAKE_DRAFTS.clear()
    start = len(LOGS.lines)
    orig = None
    if on:
        mod = C()
        orig, mod.offsets = mod.offsets, (lambda: list(offs))

    async def main():
        await S._handle_intake(Msg(text), None, bridge, None)
        at_return, pending = len(SENDS), list(S._SIGN_LINK_TASKS)
        if pending:
            await asyncio.gather(*pending)
        return at_return, len(pending)

    try:
        at_return, pending = asyncio.run(main())
    finally:
        if orig is not None:
            C().offsets = orig
        flag(False)
    return list(SENDS), at_return, pending, LOGS.lines[start:]


# ═══ A · решения и слова (contract_sign_link) ═══════════════════════════════════════════════════════════════════════

def test_a01_module_imports_only_re_and_urllib():
    tree = ast.parse(open(os.path.join(ROOT, "contract_sign_link.py"), encoding="utf-8").read())
    mods = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            mods |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            mods.add((n.module or "").split(".")[0])
    assert mods == {"re", "urllib"}, mods
    assert C().FLAG == S.F_CONTRACT_SIGN_LINK == FLAG


def test_a02_doc_id_of(c=None):
    c = c or C()
    assert c.doc_id_of(DOC_N, "") == DOC_N
    assert c.doc_id_of("", EDIT_MAKE) == DOC_N                         # нет file_id — id из ссылки
    assert c.doc_id_of(" %s " % DOC_N, "https://other") == DOC_N
    assert c.doc_id_of("short", "https://docs.google.com/document/u/0/") == ""
    assert c.doc_id_of(None, None) == ""


def test_a03_sign_url_ok_only_this_docs_esign_link(c=None):
    c = c or C()
    good = snap("link_new")["items"][0]["sign_url"]                    # форма ссылки — из ответа самой двери
    assert c.sign_url_ok(good, DOC_N), good
    ws = "https://script.google.com/a/macros/turbophuket.com/s/AKfyc/exec?a=sign&d=%s&k=tk1&who=client" % DOC_N
    assert c.sign_url_ok(ws, DOC_N)                                     # адрес Workspace-развёртывания
    other = "1LinkSent000000000000000000000000000000000002"
    bad = [
        good.replace("https://", "http://"),
        good.replace("script.google.com", "script.google.com.evil.example"),
        good.replace("d=" + DOC_N, "d=" + other),                       # ссылка ДРУГОГО договора
        good.replace("who=client", "who=agent"),                        # ссылка агента
        good.replace("a=sign", "a=status"),
        good.split("&k=")[0] + "&who=client",                           # без токена
        good + "&d=" + DOC_N,                                           # d дважды
        good.replace("/exec", "/dev"),                                  # тестовое развёртывание
        good + "#x",
        good.replace("?", " ?"),
        "https://app.boldsign.com/document/sign/?documentId=bs-direct-0001",
        "", None,
    ]
    for u in bad:
        assert not c.sign_url_ok(u, DOC_N), u
    assert not c.sign_url_ok(good, "")


def test_a04_offsets_bounded_schedule(c=None):
    c = c or C()
    o = c.offsets()
    assert o[0] == 0 and o == sorted(set(o)) and o[-1] < c.WAIT_S and len(o) <= 11, o   # r2: чтению нужен остаток
    assert o[1] == c.FIRST_GAP_S and all(b - a == c.STEP_S for a, b in zip(o[1:], o[2:])), o
    assert c.WAIT_S <= 600, "ожидание дольше 10 минут — сотрудник уже ушёл в группу контрактов"


def test_a05_verdict_on_door_snapshots(c=None):
    c = c or C()
    n = snap("link_new")
    v = c.verdict(n, DOC_N)
    assert v["act"] == "send" and v["url"] == n["items"][0]["sign_url"] and v["edit"] == n["items"][0]["doc_url"], v
    sig, emp = snap("link_signed"), snap("link_empty")
    assert c.verdict(sig, sig["items"][0]["doc_id"])["act"] == "signed"
    e = c.verdict(emp, emp["items"][0]["doc_id"])
    assert e["act"] == "wait" and "ссылки на подпись в ней ещё нет" in e["why"], e
    assert c.verdict(snap("link_none"), DOC_N)["act"] == "wait"
    o = c.verdict(snap("link_old_registry"), DOC_N)
    assert o["act"] == "stop" and "0.2.2" in o["why"], o                 # реестр до 0.2.2 — не ждать
    nc = c.verdict(snap("link_no_doc_column"), DOC_N)
    assert nc["act"] == "stop" and "колонки" in nc["why"], nc
    # r2: аннулированный (бронь отменена) — стоп «аннулирован», не ссылка и не ожидание; и тогда, когда дверь r1
    # ещё отдаёт мёртвую ссылку из неочищенной ячейки (Splinter не полагается только на мост)
    cn = snap("link_canceled")
    doc_c = cn["items"][0]["doc_id"]
    v = c.verdict(cn, doc_c)
    assert v["act"] == "stop" and v.get("canceled") is True and v["why"] == c.CANCELED_WHY, v
    stale = json.loads(json.dumps(cn))
    stale["items"][0]["sign_url"] = n["items"][0]["sign_url"].replace(DOC_N, doc_c)
    assert c.sign_url_ok(stale["items"][0]["sign_url"], doc_c)
    for st in ("АННУЛИРОВАН", " аннулирован ", "Аннулирован"):
        stale["items"][0]["status"] = st
        v = c.verdict(stale, doc_c)
        assert v["act"] == "stop" and v.get("canceled") is True, (st, v)
    stale["items"][0]["status"] = "ОТПРАВЛЕН"                           # близнец: живой статус — ссылка уходит
    assert c.verdict(stale, doc_c)["act"] == "send"


def test_a06_verdict_errors_stop_or_wait(c=None):
    c = c or C()
    v = c.verdict({"ok": False, "error": "no_filter", "message": "x"}, DOC_N)
    assert v["act"] == "stop" and "выкладка моста" in v["why"], v      # мост @88 не довозит doc_id
    assert c.verdict({"ok": False, "error": "unknown_action"}, DOC_N)["act"] == "stop"
    for err in ("TimeoutError", "exception", "registry_unreadable", "card_deadline"):
        assert c.verdict({"ok": False, "error": err}, DOC_N)["act"] == "wait", err
    assert c.verdict(None, DOC_N)["act"] == "wait"
    n = snap("link_new")
    n.pop("optional_columns")
    assert c.verdict(n, DOC_N)["act"] == "stop"                          # ответ без признака колонок — не судим


def test_a07_verdict_guards(c=None):
    c = c or C()
    n = snap("link_new")
    foreign = json.loads(json.dumps(n))
    foreign["items"][0]["doc_id"] = "1LinkSent000000000000000000000000000000000002"
    assert c.verdict(foreign, DOC_N)["act"] == "wait"                    # чужая строка не наша
    two = json.loads(json.dumps(n))
    twin = dict(two["items"][0], row=9, sign_url=two["items"][0]["sign_url"].replace("k=tk", "k=zz"))
    two["items"].append(twin)
    assert c.verdict(two, DOC_N)["act"] == "stop"                        # две разные ссылки — не выбираем
    alien = json.loads(json.dumps(n))
    alien["items"][0]["sign_url"] = "https://app.boldsign.com/document/sign/?documentId=bs-direct-0001"
    v = c.verdict(alien, DOC_N)
    assert v["act"] == "stop" and "не похожа" in v["why"], v
    odd_edit = json.loads(json.dumps(n))
    odd_edit["items"][0]["doc_url"] = "https://docs.google.com/document/d/1Other00000000000000000000000/edit"
    v = c.verdict(odd_edit, DOC_N)
    assert v["act"] == "send" and v["edit"] == "", v                     # чужая правка не подставляется
    mix = json.loads(json.dumps(n))
    mix["items"].insert(0, dict(mix["items"][0], row=1, signed=True, status="ПОДПИСАН", sign_url=""))
    assert c.verdict(mix, DOC_N)["act"] == "send"


def test_a08_words(c=None):
    c = c or C()
    assert c.TO_GROUP == "ссылка будет в группе контрактов"
    assert c.SIGN_LABEL == "✍️ Ссылка клиенту на подпись" and c.EDIT_LABEL == "✏️ Редактировать договор"
    r = c.ready_text("Имя 25.10.2026", EDIT_MAKE, REMINDER, True)
    assert r.splitlines()[:4] == ["🐀 Splinter", "✅ Договор готов «Имя 25.10.2026».", c.EDIT_LABEL + ":", EDIT_MAKE], r
    assert "следующим сообщением" in r and r.endswith(REMINDER), r
    assert c.TO_GROUP in c.ready_text("", EDIT_MAKE, "", False)
    t = c.link_text("Имя", "U-SIGN", "U-EDIT").splitlines()
    assert t == ["🐀 Splinter", c.SIGN_LABEL + " «Имя»:", "U-SIGN", c.EDIT_LABEL + ":", "U-EDIT"], t
    assert c.fail_text("", "почему").endswith("почему — %s." % c.TO_GROUP)
    assert "TurboBaby" not in r + "\n".join(t)
    # r2: аннулированный — свои слова (без «ссылка будет в группе»: её не будет); итог — по ФАКТИЧЕСКИ прошедшему
    assert c.CANCELED_WHY == "договор аннулирован в TB e-Sign — ссылка на подпись не действует"
    k = c.canceled_text("Имя")
    assert k == "🐀 Splinter\n⚠️ Договор «Имя»: %s." % c.CANCELED_WHY and c.TO_GROUP not in k, k
    assert c.text_for({"act": "stop", "why": c.CANCELED_WHY, "canceled": True}, "Имя") == k
    assert c.timeout_why("x", 45) == "за 45 с не дождался (x)"
    assert c.timeout_why("x", 270).startswith("за 5 мин") and c.timeout_why("x", 1800).startswith("за 30 мин")
    assert c.timeout_why("", 300) == "за 5 мин не дождался (договора нет в реестре подписей)"
    assert c.RESTART_WHY == "Splinter перезапускается" and 0 < c.CANCEL_SEND_S <= 10 and 0 < c.STOP_WAIT_S <= 15


# мутант = (имя, было, стало): правка исходника contract_sign_link в памяти; обязан уронить хотя бы один тест раздела A
MUTANTS = [
    ("d-not-checked", 'and _one(q, "d") == doc_id', ""),
    ("who-not-checked", '_one(q, "who") == "client" and ', ""),
    ("host-not-checked", 'u.netloc != "script.google.com" or ', ""),
    ("token-not-checked", '\n            and bool(_one(q, "k")))', ")"),
    ("two-urls-picks-first", "if len(urls) > 1:", "if False:"),
    ("alien-url-sent", "if urls and not sign_url_ok(urls[0], doc_id):", "if False:"),
    ("old-registry-waits", 'if cols.get("sign_url") is not True:', "if False:"),
    ("stop-errors-wait", "if err in STOP_ERRORS:", "if False:"),
    ("foreign-row-taken", ' and str(r.get("doc_id") or "").strip() == doc_id]', "]"),
    ("signed-not-seen", 'open_rows = [r for r in rows if r.get("signed") is not True]', "open_rows = rows"),
    ("foreign-edit-kept", 'edit if edit_url_ok(edit, doc_id) else ""', "edit"),
    ("ceiling-tripled", "while step_s > 0 and t < wait_s:", "while step_s > 0 and t <= wait_s * 3:"),
    ("doc-id-from-junk", "if _BARE_ID.match(fid):", "if fid:"),
    # r2
    ("read-on-ceiling", "while step_s > 0 and t < wait_s:", "while step_s > 0 and t <= wait_s:"),
    ("canceled-sent", 'open_rows = [r for r in open_rows if not is_canceled(r.get("status"))]', "pass"),
    ("canceled-case-strict", '" ".join(str(status or "").replace("Ё", "Е").replace("ё", "е").split()).upper()',
     "str(status)"),
    ("canceled-says-group", "    if v.get(\"canceled\"):\n        return canceled_text(name)\n", ""),
    ("timeout-says-ceiling", "spent_words(spent_s)", "spent_words(WAIT_S)"),
]
A_TESTS = ("test_a02_doc_id_of", "test_a03_sign_url_ok_only_this_docs_esign_link", "test_a04_offsets_bounded_schedule",
           "test_a05_verdict_on_door_snapshots", "test_a06_verdict_errors_stop_or_wait", "test_a07_verdict_guards",
           "test_a08_words")


def _mutant_module(old, new):
    src = open(os.path.join(ROOT, "contract_sign_link.py"), encoding="utf-8").read()
    assert src.count(old) == 1, "«было» встречается %d раз: %r" % (src.count(old), old)
    mod = types.ModuleType("contract_sign_link_mutant")
    exec(compile(src.replace(old, new), "contract_sign_link_mutant", "exec"), mod.__dict__)
    return mod


def test_a09_every_rule_has_a_killing_mutant():
    alive = []
    for name, old, new in MUTANTS:
        mod = _mutant_module(old, new)
        fails = 0
        for t in A_TESTS:
            try:
                globals()[t](mod)
            except Exception:  # noqa: BLE001 — падение и есть цель мутанта
                fails += 1
        if not fails:
            alive.append(name)
    assert not alive, "мутанты выжили: %s" % alive
    for t in A_TESTS:                          # близнец: немутированная копия проходит всё
        globals()[t](_mutant_module("FIND_LIMIT = 5", "FIND_LIMIT = 5"))


# ═══ B · Splinter: команда «договор» ═════════════════════════════════════════════════════════════════════════════════

def test_b01_flag_off_reply_byte_for_byte():
    b = Bridge(finds=[snap("link_new")])
    sends, at_return, pending, _l = intake(b, on=False)
    assert [s["text"] for s in sends] == [OLD_TEXT], sends
    assert "no_preview" not in sends[0], sends[0]                        # прежний вызов _send — без нового ключа
    assert b.args("contract_find") == [] and pending == 0, b.calls


def probe_off():
    """Отдельный процесс: ручка выключена — «договор» отвечает прежним текстом; модуль решений не загружается."""
    b = Bridge(finds=[snap("link_new")])
    sends, _r, _p, _l = intake(b, on=False)
    out = {"modules": sorted(m for m in ("contract_sign_link",) if m in sys.modules), "find": len(b.args("contract_find")),
           "sends": [s["text"] for s in sends]}
    sys.stdout.write(PROBE_MARK + json.dumps(out, ensure_ascii=False) + "\n")
    sys.stdout.flush()
    return 0


def test_b01b_flag_off_process_never_imports_module():
    p = subprocess.run([sys.executable, os.path.abspath(__file__), PROBE_ARG], cwd=ROOT, capture_output=True,
                       timeout=300, env=dict(os.environ))
    text = p.stdout.decode("utf-8", "replace")
    got = [ln for ln in text.splitlines() if ln.startswith(PROBE_MARK)]
    assert p.returncode == 0 and len(got) == 1, (p.returncode, text[-1500:], p.stderr.decode("utf-8", "replace")[-1500:])
    out = json.loads(got[0][len(PROBE_MARK):])
    assert out == {"modules": [], "find": 0, "sends": [OLD_TEXT]}, out


def test_b02_flag_on_ready_now_link_later():
    n = snap("link_new")
    b = Bridge(finds=[snap("link_none"), snap("link_none"), n])
    sends, at_return, pending, lines = intake(b, on=True, offs=(0, 0, 0))
    c = C()
    assert at_return == 1 and pending == 1, (at_return, pending)        # обработчик не ждёт реестра
    ready, link = sends[0], sends[1]
    assert len(sends) == 2, sends
    assert ready["text"] == c.ready_text(OK_MAKE["name"], EDIT_MAKE, REMINDER, True), ready["text"]
    assert ready.get("no_preview") is True and ready["chat_id"] == INTAKE, ready
    assert n["items"][0]["sign_url"] not in ready["text"]
    assert link["text"] == c.link_text(OK_MAKE["name"], n["items"][0]["sign_url"], n["items"][0]["doc_url"]), link["text"]
    assert link.get("no_preview") is True and link["chat_id"] == INTAKE, link
    assert b.args("contract_find") == [{"doc_id": DOC_N, "limit": c.FIND_LIMIT}] * 3, b.calls
    assert not any(n["items"][0]["sign_url"] in ln for ln in lines), "ссылка с токеном попала в журнал"
    assert any("ESIGNLINK" in ln and "итог send" in ln and "сообщение доставлено" in ln for ln in lines), lines


def test_b03_timeout_says_group_and_sends_no_link():
    b = Bridge(finds=[snap("link_none")])
    sends, _r, _p, _l = intake(b, on=True, offs=(0, 0, 0, 0))
    c = C()
    assert len(b.args("contract_find")) == 4, b.calls
    last = sends[-1]["text"]
    assert len(sends) == 2 and c.TO_GROUP in last and "не дождался" in last, sends
    assert "script.google.com" not in "".join(s["text"] for s in sends)


def test_b04_old_bridge_stops_at_once():
    b = Bridge(finds=[{"ok": False, "error": "no_filter", "message": "нужен телефон, имя или байк"}])
    sends, _r, _p, _l = intake(b, on=True, offs=(0, 0, 0, 0))
    assert len(b.args("contract_find")) == 1, b.calls
    assert C().TO_GROUP in sends[-1]["text"] and "выкладка моста" in sends[-1]["text"], sends


def test_b05_old_registry_stops_at_once():
    b = Bridge(finds=[snap("link_old_registry")])
    sends, _r, _p, _l = intake(b, on=True, offs=(0, 0, 0, 0))
    assert len(b.args("contract_find")) == 1 and "0.2.2" in sends[-1]["text"], (b.calls, sends)


def test_b06_signed_contract_no_sign_link():
    sig = snap("link_signed")
    doc = sig["items"][0]["doc_id"]
    b = Bridge(make=dict(OK_MAKE, file_id=doc, url="https://docs.google.com/document/d/%s/edit" % doc), finds=[sig])
    sends, _r, _p, _l = intake(b, on=True)
    assert sends[-1]["text"] == C().signed_text(OK_MAKE["name"]), sends
    assert "script.google.com" not in "".join(s["text"] for s in sends)


def test_b07_read_failure_then_link():
    n = snap("link_new")
    b = Bridge(finds=[TimeoutError("timed out"), n])
    sends, _r, _p, _l = intake(b, on=True, offs=(0, 0, 0))
    assert len(b.args("contract_find")) == 2 and n["items"][0]["sign_url"] in sends[-1]["text"], (b.calls, sends)


def test_b08_no_doc_id_says_group_now():
    b = Bridge(make={"ok": True, "name": "X", "url": "https://docs.google.com/open", "flags": {}}, finds=[snap("link_new")])
    sends, at_return, pending, _l = intake(b, on=True)
    assert len(sends) == 1 and pending == 0 and C().TO_GROUP in sends[0]["text"], sends
    assert b.args("contract_find") == [], b.calls


def test_b09_real_send_preview_off_only_when_asked():
    calls = []

    class Bot:
        async def send_message(self, **kw):
            calls.append(kw)
            return types.SimpleNamespace(message_id=1)

    ctx = types.SimpleNamespace(bot=Bot())
    asyncio.run(REAL_SEND(ctx, chat_id=INTAKE, text="a", bilingual=False, no_preview=True))
    asyncio.run(REAL_SEND(ctx, chat_id=INTAKE, text="b", bilingual=False))
    lpo = calls[0].get("link_preview_options")
    assert lpo is not None and lpo.is_disabled is True, calls[0]
    assert "disable_web_page_preview" not in calls[0]
    assert calls[1] == {"chat_id": INTAKE, "text": "b"}, calls[1]          # прежние вызовы — прежние ключи


class Clock:
    """Подставные часы досылки: sleep сдвигает время, а не ждёт."""

    def __init__(self):
        self.t, self.slept = 1000.0, []

    def __call__(self):
        return self.t

    async def sleep(self, d):
        self.slept.append(round(d, 6))
        self.t += d


def follow(bridge, ck=None, name="N"):
    ck = ck or Clock()
    return asyncio.run(S._contract_sign_link_follow(None, bridge, INTAKE, None, DOC_N, name, EDIT_MAKE,
                                                    sleep=ck.sleep, clock=ck))


def test_b10_real_schedule_and_ceiling():
    """Расписание — настоящее (без подмены offsets): первое чтение сразу, второе через минуту, дальше раз в 30 с;
    без строки реестра — до последнего чтения перед потолком WAIT_S, и одно итоговое сообщение."""
    c = C()
    SENDS.clear()
    ck = Clock()
    b = Bridge(finds=[snap("link_none"), snap("link_none"), snap("link_new")])
    v = asyncio.run(S._contract_sign_link_follow(None, b, INTAKE, None, DOC_N, "N", EDIT_MAKE, sleep=ck.sleep, clock=ck))
    assert v["act"] == "send" and ck.slept == [c.FIRST_GAP_S, c.STEP_S], (v, ck.slept)
    assert len(SENDS) == 1 and SENDS[0].get("no_preview") is True, SENDS

    SENDS.clear()
    ck = Clock()
    b = Bridge(finds=[snap("link_none")])
    v = asyncio.run(S._contract_sign_link_follow(None, b, INTAKE, None, DOC_N, "N", EDIT_MAKE, sleep=ck.sleep, clock=ck))
    assert v["act"] == "stop" and len(b.args("contract_find")) == len(c.offsets()), (v, b.calls)
    assert abs(sum(ck.slept) - c.offsets()[-1]) < 1e-6 and c.offsets()[-1] < c.WAIT_S, ck.slept
    assert len(SENDS) == 1 and c.TO_GROUP in SENDS[0]["text"], SENDS
    assert "за %s не дождался" % c.spent_words(c.offsets()[-1]) in SENDS[0]["text"], SENDS[0]["text"]


# ═══ C · r2 (ревью перед пушем): потолок, итоговая отправка, отмена при остановке, аннулированный ═══════════════════

class SlowBridge(Bridge):
    """Мост, чьё чтение «длится» `cost` секунд подставных часов; honor — срезать длительность бюджетом чтения, как это
    делает `bridge_client.card_budget` у настоящего клиента. Бюджет читается ИЗ ПОТОКА чтения (ContextVar)."""

    def __init__(self, ck, cost, honor, **kw):
        Bridge.__init__(self, **kw)
        self.ck, self.cost, self.honor, self.budgets = ck, cost, honor, []

    def contract_find(self, **kw):
        cb = S.bridge_client.current_card_budget()
        self.budgets.append(None if cb is None else round(cb.budget, 6))
        spent = self.cost if not (self.honor and cb is not None) else min(self.cost, cb.budget)
        self.ck.t += spent
        return Bridge.contract_find(self, **kw)


def test_c01_ceiling_holds_with_slow_bridge():
    """Каждое чтение длится 200 с. Под дедлайном остатка (как настоящий клиент) — два чтения (бюджеты 300 и 100),
    итог ровно на потолке и словами «за 5 мин»; мост дедлайн не соблюл (400 с) — второе чтение НЕ начинается,
    итог называет фактические 7 мин, а не обещанные 5."""
    c = C()
    SENDS.clear()
    ck = Clock()
    b = SlowBridge(ck, 200, True, finds=[snap("link_none")])
    v = follow(b, ck)
    assert b.budgets == [c.WAIT_S, c.WAIT_S - 200], b.budgets
    assert v["act"] == "stop" and len(b.args("contract_find")) == 2 and ck.t - 1000.0 == c.WAIT_S, (v, ck.t)
    assert "за 5 мин не дождался" in SENDS[-1]["text"], SENDS
    SENDS.clear()
    ck = Clock()
    b = SlowBridge(ck, 400, False, finds=[snap("link_none")])
    v = follow(b, ck)
    assert len(b.args("contract_find")) == 1 and "за 7 мин не дождался" in SENDS[-1]["text"], (b.calls, SENDS)


def test_c02_final_send_failure_does_not_escape():
    """Forbidden (бот удалён из чата) на итоговой отправке — задача не бросает, «итог» пишется ПОСЛЕ отправки со
    словами «НЕ доставлено»; _send_retry вернул None (сеть трижды) — тоже «НЕ доставлено»."""
    from telegram.error import Forbidden, TimedOut

    async def boom(text):
        raise Forbidden("bot was kicked")

    SENDS.clear()
    start = len(LOGS.lines)
    SEND_HOOK[:] = [boom]
    try:
        v = follow(Bridge(finds=[snap("link_new")]))
    finally:
        SEND_HOOK[:] = []
    lines = LOGS.lines[start:]
    assert v["act"] == "send" and v["delivered"] is False and SENDS == [], (v, SENDS)
    assert any("итоговое сообщение не отправлено (Forbidden" in ln for ln in lines), lines
    i_fail = next(i for i, ln in enumerate(lines) if "итоговое сообщение не отправлено" in ln)
    i_itog = next(i for i, ln in enumerate(lines) if "итог send" in ln)
    assert i_fail < i_itog and "сообщение НЕ доставлено" in lines[i_itog], lines

    async def net(text):
        raise TimedOut("timed out")

    start = len(LOGS.lines)
    SEND_HOOK[:] = [net]
    try:
        v = follow(Bridge(finds=[snap("link_new")]))
    finally:
        SEND_HOOK[:] = []
    assert v["delivered"] is False and any("сообщение НЕ доставлено" in ln for ln in LOGS.lines[start:]), v
    SENDS.clear()
    v = follow(Bridge(finds=[snap("link_new")]))                         # близнец: доставлено
    assert v["delivered"] is True and len(SENDS) == 1, (v, SENDS)


async def _blocked_follow(bridge, name="N"):
    """Досылка, повисшая в ожидании (второе чтение через минуту, часы настоящие): → задача."""
    t = asyncio.get_running_loop().create_task(
        S._contract_sign_link_follow(None, bridge, INTAKE, None, DOC_N, name, EDIT_MAKE))
    for _ in range(200):                                                # первое чтение прошло — задача спит
        await asyncio.sleep(0.01)
        if bridge.args("contract_find"):
            break
    await asyncio.sleep(0.05)
    return t


def test_c03_cancel_during_wait_says_restart_once_and_reraises():
    c = C()
    SENDS.clear()
    calls = []

    async def count(text):
        calls.append(text)

    async def main():
        b = Bridge(finds=[snap("link_none")])
        t = await _blocked_follow(b, "Имя")
        SEND_HOOK[:] = [count]
        t.cancel()
        try:
            await t
        except asyncio.CancelledError:
            return "cancelled", b
        return "not-cancelled", b

    try:
        res, b = asyncio.run(main())
    finally:
        SEND_HOOK[:] = []
    assert res == "cancelled", res                                      # отмена переброшена
    assert [s["text"] for s in SENDS] == [c.fail_text("Имя", c.RESTART_WHY)], SENDS
    assert SENDS[0].get("no_preview") is True and len(calls) == 1, (SENDS, calls)   # одна попытка, без повторов
    assert len(b.args("contract_find")) == 1


def test_c04_cancel_restart_send_is_bounded():
    """Фраза «перезапускается» повисла — отмена всё равно уходит выше не позже CANCEL_SEND_S."""
    c = C()
    SENDS.clear()

    async def hang(text):
        await asyncio.sleep(3600)

    async def main():
        t = await _blocked_follow(Bridge(finds=[snap("link_none")]))
        SEND_HOOK[:] = [hang]
        t0 = asyncio.get_running_loop().time()
        t.cancel()
        try:
            await t
        except asyncio.CancelledError:
            return asyncio.get_running_loop().time() - t0
        return None

    orig = c.CANCEL_SEND_S
    c.CANCEL_SEND_S = 0.2
    try:
        took = asyncio.run(main())
    finally:
        c.CANCEL_SEND_S = orig
        SEND_HOOK[:] = []
    assert took is not None and took < 2.0 and SENDS == [], (took, SENDS)


def test_c05_cancel_during_final_send_no_restart_phrase():
    """Отмена, когда итог уже отправляется, — второй фразы «перезапускается» нет (итог мог уйти)."""
    c = C()
    SENDS.clear()
    started = []

    async def hang(text):
        started.append(text)
        await asyncio.sleep(3600)

    async def main():
        SEND_HOOK[:] = [hang]
        t = asyncio.get_running_loop().create_task(
            S._contract_sign_link_follow(None, Bridge(finds=[snap("link_new")]), INTAKE, None, DOC_N, "N", EDIT_MAKE))
        for _ in range(300):
            await asyncio.sleep(0.01)
            if started:
                break
        t.cancel()
        try:
            await t
        except asyncio.CancelledError:
            return "cancelled"
        return "not-cancelled"

    try:
        res = asyncio.run(main())
    finally:
        SEND_HOOK[:] = []
    assert res == "cancelled" and len(started) == 1 and c.RESTART_WHY not in started[0], (res, started)


def test_c06_stop_drain_cancels_live_tasks():
    """`sign_link_drain`: живые досылки отменены, каждая сказала «перезапускается»; живых нет → 0, ничего не шлётся."""
    c = C()
    SENDS.clear()

    async def main():
        ts = [await _blocked_follow(Bridge(finds=[snap("link_none")]), "A"),
              await _blocked_follow(Bridge(finds=[snap("link_none")]), "B")]
        for t in ts:
            S._SIGN_LINK_TASKS.add(t)
            t.add_done_callback(S._SIGN_LINK_TASKS.discard)
        n = await S.sign_link_drain(5.0)
        return n, [t.cancelled() for t in ts], await S.sign_link_drain(5.0)

    n, cancelled, again = asyncio.run(main())
    assert n == 2 and cancelled == [True, True] and again == 0, (n, cancelled, again)
    assert sorted(s["text"] for s in SENDS) == sorted([c.fail_text("A", c.RESTART_WHY), c.fail_text("B", c.RESTART_WHY)])
    assert not S._SIGN_LINK_TASKS


def test_c07_bot_on_stop_line_counts_cancelled():
    """`bot.on_stop` (post_stop) отменяет досылки в бюджете остановки и дописывает число в строку дренажа; без живых
    досылок строка прежняя — без хвоста. Отдельный процесс: импорт bot.py со заглушками, как в test_contract_ref_gen."""
    p = subprocess.run([sys.executable, os.path.abspath(__file__), PROBE_STOP_ARG], cwd=ROOT, capture_output=True,
                       timeout=300, env=dict(os.environ))
    text = p.stdout.decode("utf-8", "replace")
    got = [ln for ln in text.splitlines() if ln.startswith(PROBE_STOP_MARK)]
    assert p.returncode == 0 and len(got) == 1, (p.returncode, text[-1500:], p.stderr.decode("utf-8", "replace")[-1500:])
    out = json.loads(got[0][len(PROBE_STOP_MARK):])
    c = C()
    assert out["with"].endswith("; досылки ссылки на подпись: отменено 1"), out
    assert "досылки" not in out["without"] and out["without"].startswith("  🛑 дренаж остановки: "), out
    assert out["sends"] == [c.fail_text("N", c.RESTART_WHY)] and out["cancelled"] is True, out


PROBE_STOP_ARG = "--probe-stop-drain"
PROBE_STOP_MARK = "ESIGNLINK_STOP "


def probe_stop():
    """Отдельный процесс: bot.py со заглушками тяжёлых зависимостей; передача карточек — во временный каталог."""
    import tempfile
    tmp = tempfile.mkdtemp(prefix="esignlink_stop_")
    os.environ["RESTART_HANDOFF_STATE"] = os.path.join(tmp, "restart_handoff.json")

    def _stub(name, **attrs):
        m = types.ModuleType(name)
        for k, v in attrs.items():
            setattr(m, k, v)
        sys.modules[name] = m

    class _Mem:
        def all_topic_bikes(self):
            return {}

        def all_info_pins(self):
            return {}

    class _Aud:
        audit_groups = []

        def __init__(self, *a, **k):
            pass

        def set_audit_config(self, *a, **k):
            pass

    _stub("dotenv", load_dotenv=lambda *a, **k: None)
    _stub("claude_client", ClaudeClient=lambda *a, **k: types.SimpleNamespace())
    _stub("memory", Memory=_Mem)
    _stub("auditor", Auditor=_Aud)
    _stub("prompts", SYSTEM_PROMPT="", daily_pulse_prompt=lambda *a, **k: "")
    import bot as B

    def stop_line():
        return next((ln for ln in reversed(LOGS.lines) if "🛑 дренаж остановки" in ln), "")

    async def main():
        t = await _blocked_follow(Bridge(finds=[snap("link_none")]), "N")
        S._SIGN_LINK_TASKS.add(t)
        t.add_done_callback(S._SIGN_LINK_TASKS.discard)
        B._SHUTDOWN_T0 = B._mono()
        await B.on_stop(None)
        with_ = stop_line()
        await B.on_stop(None)
        return with_, stop_line(), t.cancelled()

    SENDS.clear()
    with_, without, cancelled = asyncio.run(main())
    out = {"with": with_, "without": without, "sends": [s["text"] for s in SENDS], "cancelled": cancelled}
    sys.stdout.write(PROBE_STOP_MARK + json.dumps(out, ensure_ascii=False) + "\n")
    sys.stdout.flush()
    return 0


def test_c08_canceled_contract_via_command():
    """«договор» по брони с аннулированным договором (make_contract пересобрал тот же документ): одно чтение, слова
    «аннулирован», ссылки на подпись нет ни в одном сообщении."""
    c = C()
    cn = snap("link_canceled")
    doc = cn["items"][0]["doc_id"]
    b = Bridge(make=dict(OK_MAKE, file_id=doc, url="https://docs.google.com/document/d/%s/edit" % doc), finds=[cn])
    sends, _r, _p, _l = intake(b, on=True, offs=(0, 0, 0, 0))
    assert len(b.args("contract_find")) == 1 and sends[-1]["text"] == c.canceled_text(OK_MAKE["name"]), (b.calls, sends)
    assert "script.google.com" not in "".join(s["text"] for s in sends)


def main():
    if PROBE:
        return probe_off()
    if PROBE_STOP_ARG in sys.argv[1:]:
        return probe_stop()
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    bad = 0
    for k, fn in tests:
        try:
            fn()
            print("PASS", k)
        except Exception as e:  # noqa: BLE001 — печатаем и считаем
            bad += 1
            print("FAIL %s — %s %s" % (k, type(e).__name__, str(e)[:1500]))
    print("ИТОГ %d/%d" % (len(tests) - bad, len(tests)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
