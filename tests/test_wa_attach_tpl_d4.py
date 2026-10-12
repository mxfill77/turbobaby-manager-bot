#!/usr/bin/env python3
"""INTEG0710 Д4 — граница 24 ч при Б3в (PDF клиенту, WA_AGENT_ATTACH) и Б3г (шаблон после 24 часов, WA_AGENT_TEMPLATES)
вместе. Гипотеза проверяющего: возврат черновика в pending перетирает карточку шаблона.

Оба флага, ядро с PDF-частью (`wa_agent_attach.AttachCore`), окно 24 ч закрыто → на карточке «📨 Отправить шаблоном».
Путь AttachCore не стирает кнопку и состояние шаблона, а «📨» после него не даёт дубля:
  (1) граница — окно закрылось у ворот двери, ядро вернуло черновик в pending: карточка с «📨» (ветка с PDF и ветка
      без PDF), исход частей на карточку не пишется, правка рук — вне транзакции текстовой части; «📨» потом уходит
      ОДИН раз, второе «📨» и «✅» в закрытое окно дубля не дают; провайдер не одобрил — «📨» жива, одобрил — один;
      проба окна к правке не ответила — карточка не тронута вовсе;
  (2) отказ части — реестр отозвал основание PDF при «✅»: черновик устарел и пересобран, новая карточка шаблона не
      предлагает (шаблон этому клиенту на это сообщение уже ушёл), «📨» дубля не даёт;
  (3) сбой части — COMMIT текстовой части упал на границе: откат, отложенная правка рук не кладётся (и не доезжает со
      следующей текстовой частью), шаблон не уходит ни сразу, ни после рестарта (предел Б3в «R21 для текстовой части»
      — назван строителем Б3в, здесь только его безопасная сторона); транзакция не открылась — исход без неё,
      карточка с «📨», шаблон один;
  (4) повторная карточка — ответ Telegram на первую карточку потерян, карточка пришла второй раз: «📨» с любой из двух
      уходит ОДИН раз; версия 2 (правка человека) после ушедшего шаблона — без «📨», словами;
  (5) рестарт после границы — карточка не перетирается, часть PDF ждёт текста, «📨» один раз и после второго рестарта
      не повторяется;
  (6) срок ритма — окно закрылось между «✅» и сроком (`send_due`): та же граница, «⏳ Отменить» сменяется «📨»;
  (7) как раньше — прежнее ядро с шаблонами на той же границе даёт тот же исход нажатия и ту же клавиатуру.

Подделки — World из tests/test_wa_attach_svc.py (Bot API, модель со сверкой Т4а, двери договоров, провайдер текста и
PDF) и дверь шаблона `SendDoor.tpl` — счётчик вызовов вместо 360dialog. Сети нет (urlopen — ловушка), модель не
зовётся, база — временный каталог. Окно 24 ч меряет дверь по живым часам: очередь World датирована T0 ≈ 21.09.2026,
поэтому окно закрыто; граница задаётся подменой пробы окна и ответа двери, как в tests/test_wa_attach_tpl.py."""
import contextlib
import os
import sqlite3
import sys
import types
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)


def _no_net(*a, **kw):
    raise AssertionError("тест обратился к сети")


urllib.request.urlopen = _no_net

try:                                       # spend_ledger импортирует fcntl (только Linux): на ПК — подмена цены
    import fcntl  # noqa: F401
except ImportError:
    sys.modules.setdefault("spend_ledger", types.SimpleNamespace(cost_usd=lambda model, i, o: 0.0,
                                                                 meter=lambda *a, **k: None))

import test_wa_attach_svc as AS  # noqa: E402
import wa_agent as A  # noqa: E402
import wa_agent_tg as G  # noqa: E402
import wa_send  # noqa: E402

ATT_TPL = dict(AS.ON, WA_AGENT_TEMPLATES="1")
TPL_ONLY = dict(AS.BASE, WA_AGENT_TEMPLATES="1")
KB3 = ["wa:send:1:1", "wa:fix:1:1", "wa:no:1:1"]
TPL = "wa:tpl:1:1"
CLOSED = {"state": "closed", "age": 90000}


# ═══ подделки и чтение ═════════════════════════════════════════════════════════════════════════════════════

def tpl_door(w, outcomes=("sent",)):
    """Дверь шаблона службы (`SendDoor.tpl`, вместо `wa_send.send_template`): вызовы — в список; исход — по очереди из
    outcomes (последний повторяется). Тело ответа — текст шаблона дословно, как у настоящей двери."""
    calls, left = [], list(outcomes)

    def tpl(to, name, lang, params, env=None):
        calls.append((to, name, lang, list(params)))
        outcome = left.pop(0) if len(left) > 1 else left[0]
        text = wa_send.template_text(name, lang, params)
        if outcome == "sent":
            return {"outcome": "sent", "reason": "ok", "wamid": "wamid.TPL%d" % len(calls), "template": name,
                    "lang": lang, "approval": "approved", "text": text}
        return {"outcome": outcome, "reason": "Meta не одобрила шаблон — статус pending — не отправлено",
                "wamid": None, "template": name, "lang": lang, "approval": "not_approved", "text": text}
    w.core.door.tpl = tpl
    return calls


def closing(w):
    """Окно закрылось между пробой ядра при нажатии и воротами двери: первая проба — открыто, дальше — закрыто; дверь
    текста отказывает ДО сети с window=closed, как wa_send при закрытом окне (приём tests/test_wa_attach_tpl.py)."""
    seen = []

    def window(number, now=None):
        seen.append(number)
        return {"state": "open" if len(seen) == 1 else "closed", "age": 90000}
    w.core.door.window = window
    w.core.door.send = lambda to, text, db_path=None: {"outcome": "not_sent", "reason": "окно 24 ч закрыто",
                                                       "window": "closed", "wamid": None}
    return seen


def open_once(w):
    """Проба окна дрогнула: при нажатии — открыто, дальше — закрыто. Дверь текста не подменяется."""
    seen = []

    def window(number, now=None):
        seen.append(number)
        return {"state": "open" if len(seen) == 1 else "closed", "age": 90000}
    w.core.door.window = window
    return seen


def tg_watch(w):
    """Каждый вызов Bot API → (метод, база ядра в транзакции?). Б3в: Telegram в транзакции части не зовётся."""
    seen, api = [], w.tg.api

    def watched(method, params, timeout=30, quiet=()):
        seen.append((method, bool(w.core.db.in_transaction)))
        return api(method, params, timeout=timeout, quiet=quiet)
    w.tg.api = watched
    return seen


class LostOnce:
    """Bot API: первая карточка до Telegram дошла (номер выдан), ответ потерян — ядро считает «неизвестно» и шлёт
    карточку ещё раз (WACARDDONEFIX0210: возможна вторая карточка)."""

    def __init__(self, inner):
        self.inner, self.left = inner, 1

    def __call__(self, method, url, headers=None, data=None, timeout=30):
        status, body = self.inner(method, url, headers, data, timeout)
        if url.rsplit("/", 1)[-1] == "sendMessage" and self.left:
            self.left -= 1
            return None, b""
        return status, body


class NoContractModel(AS.Model):
    """Сверка Т4а без договора: строка attach есть, вложения нет («договор не сверялся») — ветка AttachCore без PDF."""

    def draft(self, number, upto_id):
        self.calls += 1
        self.last = {"tools": {"state": "done", "results": [AS.res("rental", "fact", [
            {"kind": "rental", "booking_id": "B7", "bike": "PCX 160 5580", "date_start": "2026-10-01",
             "date_end": "2026-10-07"}])]}, "info": {"last_in": AS.T0 - 200}}
        return AS.TEXT


@contextlib.contextmanager
def model_as(cls):
    """World собирает модель именем модуля test_wa_attach_svc — подмена на время сборки."""
    old = AS.Model
    AS.Model = cls
    try:
        yield
    finally:
        AS.Model = old


def cards(w):
    """Карточки в «Агенты» (сообщения с клавиатурой) → [кнопки каждой карточки] в порядке отправки."""
    out = []
    for p in w.http.of("sendMessage"):
        kb = (p.get("reply_markup") or {}).get("inline_keyboard")
        if kb and p.get("chat_id") == AS.CHAT:
            out.append([b["callback_data"] for row in kb for b in row])
    return out


def card_texts(w):
    return [p["text"] for p in w.http.of("sendMessage")
            if p.get("chat_id") == AS.CHAT and (p.get("reply_markup") or {}).get("inline_keyboard")]


def last_kb(w, mid=101):
    e = w.edits(mid)
    return AS.kb_data(e[-1]) if e else None


def last_said(w, mid=101):
    """Слова последней правки карточки — то, что легло после «— » под телом карточки."""
    e = w.edits(mid)
    return e[-1]["text"].rsplit("\n\n— ", 1)[-1] if e else None


def tpl_rows(w):
    try:
        return w.q("SELECT draft_id, state, tries FROM tpl_out ORDER BY draft_id")
    except sqlite3.OperationalError:
        return None


def card_out(w, did=1, ver=1):
    rows = w.q("SELECT state FROM card_out WHERE draft_id=? AND ver=?", (did, ver))
    return rows[0][0] if rows else None


def state(w, did=1):
    return w.q("SELECT state, ver FROM drafts WHERE id=?", (did,))


# ═══ (1) граница: возврат в pending не перетирает карточку шаблона ═══════════════════════════════════════════

def _boundary(w):
    calls = tg_watch(w)
    closing(w)
    w.press("wa:send:1:1")
    return calls


def test_boundary_pdf_branch_card_keeps_template_one_template():
    """Ветка с PDF: «✅» на границе — черновик pending v1, клиенту ни текста, ни PDF, часть PDF ждёт текста (wait,
    попытка 1), карточка не закрыта (card_out delivered) и несёт «📨» этой версии, правка — вне транзакции; потом «📨» —
    ОДИН шаблон, кнопка снимается, прежний ряд жив; второе «📨» и «✅» — без второго шаблона, словами."""
    w = AS.World(ATT_TPL)
    w.ready()
    sent = tpl_door(w)
    assert cards(w) == [KB3 + [TPL]], cards(w)                      # окно закрыто с первой карточки
    calls = _boundary(w)
    facts = "черновик=%s часть=%s card_out=%s кнопки=%s ответ=%r вызовы=%s" % (
        state(w), w.part(), card_out(w), last_kb(w), (w.answers() or [None])[-1], calls)
    assert state(w) == [(A.PENDING, 1)], facts
    assert w.sends == [] and w.media == [], (w.sends, w.media)
    part = w.part()
    assert part is not None and part[0] == "wait" and part[1] == 1, facts
    assert card_out(w) == A.CARD_DELIVERED, facts                    # карточка не решена: исход частей не ложился
    assert last_kb(w) == KB3 + [TPL], facts
    assert "«%s» reply_request (ru)" % G.W_TPL_BUTTON in last_said(w), last_said(w)
    body = w.edits()[-1]["text"]                                     # тело карточки цело: строка PDF и строка шаблона
    assert "📄 «Отправить» шлёт ВТОРЫМ" in body and "«%s» reply_request (ru): «" % G.W_TPL_BUTTON in body, body
    assert w.answers()[-1].startswith("окно 24 ч закрыто"), facts
    assert calls and not [c for c in calls if c[1]], facts           # Telegram в транзакции части не звали
    assert sent == [] and tpl_rows(w) == [], (sent, tpl_rows(w))
    w.press(TPL)
    assert len(sent) == 1 and sent[0][:3] == (AS.NUM, "reply_request", "ru"), sent
    assert tpl_rows(w) == [(1, A.SENT, 1)], tpl_rows(w)
    assert w.answers()[-1].startswith("шаблон ушёл"), w.answers()[-1]
    assert last_kb(w) == KB3, last_kb(w)
    w.press(TPL)
    assert len(sent) == 1 and "уже ушёл" in w.answers()[-1], (sent, w.answers()[-1])
    w.press("wa:send:1:1")
    said = w.answers()[-1]
    assert len(sent) == 1 and said.startswith("окно 24 ч закрыто") and "уже ушёл" in said, (sent, said)
    assert last_kb(w) == KB3, last_kb(w)
    assert w.sends == [] and w.media == [] and tpl_rows(w) == [(1, A.SENT, 1)], (w.sends, w.media, tpl_rows(w))
    assert state(w) == [(A.PENDING, 1)] and w.part()[:2] == ("wait", 1), (state(w), w.part())
    assert not [c for c in calls if c[1]], calls


def test_boundary_no_pdf_branch_card_keeps_template_one_template():
    """Ветка без PDF (сверка без договора — строка attach есть, вложения нет): та же граница — pending v1, части PDF
    нет, карточка не закрыта и несёт «📨», правка вне транзакции; «📨» — один шаблон, второе — без дубля."""
    with model_as(NoContractModel):
        w = AS.World(ATT_TPL)
    w.ready()
    meta = w.q("SELECT file_id, reason FROM attach WHERE draft_id=1")
    assert meta and meta[0][0] is None and str(meta[0][1]).startswith("договор не сверялся"), meta
    sent = tpl_door(w)
    calls = _boundary(w)
    facts = "черновик=%s часть=%s card_out=%s кнопки=%s ответ=%r" % (
        state(w), w.part(), card_out(w), last_kb(w), (w.answers() or [None])[-1])
    assert state(w) == [(A.PENDING, 1)] and w.sends == [] and w.media == [], facts
    assert w.part() is None, facts
    assert card_out(w) == A.CARD_DELIVERED and last_kb(w) == KB3 + [TPL], facts
    assert w.answers()[-1].startswith("окно 24 ч закрыто"), facts
    assert calls and not [c for c in calls if c[1]], calls
    w.press(TPL)
    w.press(TPL)
    assert len(sent) == 1 and tpl_rows(w) == [(1, A.SENT, 1)], (sent, tpl_rows(w))
    assert "уже ушёл" in w.answers()[-1] and last_kb(w) == KB3, (w.answers()[-1], last_kb(w))


def test_boundary_probe_unknown_at_offer_card_untouched():
    """Граница, но проба окна к правке карточки не ответила (unknown): ядро возвращает черновик в pending БЕЗ правки
    карточки — и ядро с PDF-частью тоже ничего на неё не пишет: карточка как была (с «📨»), часть PDF ждёт, ответ —
    словами ядра; «📨» при неизмеренном окне шаблон не шлёт."""
    w = AS.World(ATT_TPL)
    w.ready()
    sent = tpl_door(w)
    # проба окна: при нажатии — открыто, у ворот двери — закрыто, дальше (правка карточки, «📨») — не отвечает
    seq = iter(("open", "closed"))

    def window(number, now=None):
        st = next(seq, "unknown")
        return {"state": st, "age": None if st == "unknown" else 90000}
    w.core.door.window = window
    w.core.door.send = lambda to, text, db_path=None: {"outcome": "not_sent", "reason": "окно 24 ч закрыто",
                                                       "window": "closed", "wamid": None}
    calls = tg_watch(w)
    w.press("wa:send:1:1")
    facts = "черновик=%s часть=%s card_out=%s правок=%d ответ=%r вызовы=%s" % (
        state(w), w.part(), card_out(w), len(w.edits()), (w.answers() or [None])[-1], calls)
    assert state(w) == [(A.PENDING, 1)] and w.sends == [] and w.media == [], facts
    assert w.part()[:2] == ("wait", 1) and card_out(w) == A.CARD_DELIVERED and w.edits() == [], facts
    assert w.answers()[-1] == "окно 24 ч закрылось при отправке — черновик ждёт", facts
    assert cards(w) == [KB3 + [TPL]] and not [c for c in calls if c[1]], facts
    w.press(TPL)
    assert sent == [] and w.answers()[-1] == "окно 24 ч не измерено — шаблон не шлём", (sent, w.answers()[-1])
    assert tpl_rows(w) == [] and state(w) == [(A.PENDING, 1)], (tpl_rows(w), state(w))


def test_boundary_then_provider_refuses_button_alive_then_one_template():
    """После границы провайдер шаблон не одобрил — отказ словами, «📨» на карточке жива, черновик ждёт; одобрил —
    шаблон уходит, и это второй вызов двери, но ПЕРВЫЙ ушедший шаблон (tries 2); третьего вызова нет."""
    w = AS.World(ATT_TPL)
    w.ready()
    sent = tpl_door(w, outcomes=("not_sent", "sent"))
    _boundary(w)
    assert last_kb(w) == KB3 + [TPL] and card_out(w) == A.CARD_DELIVERED, (last_kb(w), card_out(w))
    w.press(TPL)
    assert len(sent) == 1 and "статус pending" in w.answers()[-1], (sent, w.answers()[-1])
    assert tpl_rows(w) == [(1, A.NOT_SENT, 1)] and last_kb(w) == KB3 + [TPL], (tpl_rows(w), last_kb(w))
    assert state(w) == [(A.PENDING, 1)], state(w)
    w.press(TPL)
    assert len(sent) == 2 and tpl_rows(w) == [(1, A.SENT, 2)], (sent, tpl_rows(w))
    assert last_kb(w) == KB3, last_kb(w)
    w.press(TPL)
    assert len(sent) == 2 and "уже ушёл" in w.answers()[-1], (sent, w.answers()[-1])
    assert w.sends == [] and w.media == [], (w.sends, w.media)


# ═══ (2) отказ части: реестр отозвал основание — пересборка, без второго шаблона ═══════════════════════════════

def test_registry_refusal_rebuilt_card_offers_no_second_template():
    """Шаблон ушёл; проба окна дрогнула «открыто», а реестр отозвал договор — «✅» снимает черновик (stale, ничего не
    отправлено). Пересобранный черновик того же сообщения клиента: карточка без «📨» и говорит, что шаблон уже ушёл;
    «📨» и «✅» на ней — без второго шаблона."""
    w = AS.World(ATT_TPL)
    w.ready()
    sent = tpl_door(w)
    w.press(TPL)
    assert len(sent) == 1 and tpl_rows(w) == [(1, A.SENT, 1)], (sent, tpl_rows(w))
    open_once(w)
    w.model.find.answer = AS.REVOKED
    w.press("wa:send:1:1")
    assert state(w) == [(A.STALE, 1)], state(w)
    assert w.answers()[-1].startswith("устарело: основание PDF не подтверждено реестром"), w.answers()[-1]
    assert w.sends == [] and w.media == [], (w.sends, w.media)
    del w.core.door.window                                           # проба окна — снова настоящая (закрыто)
    made = w.core.tick(AS.T0 + 400)
    assert made == [2], made
    card2 = w.q("SELECT card_id FROM drafts WHERE id=2")[0][0]
    kb2, text2 = cards(w)[-1], card_texts(w)[-1]
    assert card2 and kb2 == ["wa:send:2:1", "wa:fix:2:1", "wa:no:2:1"], (card2, kb2)
    assert "шаблона нет: шаблон уже ушёл (черновик №1)" in text2, text2
    w.press("wa:tpl:2:1", card_id=card2)
    assert len(sent) == 1 and "уже ушёл" in w.answers()[-1], (sent, w.answers()[-1])
    w.press("wa:send:2:1", card_id=card2)
    said = w.answers()[-1]
    assert len(sent) == 1 and said.startswith("окно 24 ч закрыто") and "уже ушёл" in said, (sent, said)
    assert tpl_rows(w) == [(1, A.SENT, 1)] and w.sends == [] and w.media == [], (tpl_rows(w), w.sends, w.media)


# ═══ (3) сбой части: COMMIT текстовой части упал на границе ════════════════════════════════════════════════════

def test_text_part_commit_fails_at_boundary_no_edit_no_template():
    """COMMIT текстовой части не прошёл на границе: откат (возврат в pending был внутри транзакции и не лёг), исключение
    наружу — руки пишут строку журнала; отложенная правка карточки НЕ кладётся ни сразу, ни со следующей текстовой
    частью (другой клиент, обычная отправка), Telegram в транзакции не звали, клиенту ничего; «📨» на ещё висящей
    карточке шаблона не шлёт; после рестарта — тоже (предел Б3в «R21 для текстовой части»: черновик «неизвестно», а
    не pending, — назван строителем Б3в, не этот заход)."""
    w = AS.World(ATT_TPL)
    w.ready()
    sent = tpl_door(w)
    calls = tg_watch(w)
    closing(w)
    n_edits, n_ans = len(w.edits()), len(w.answers())
    end = w.core._tx_end

    def broken(ok=True):
        if ok and w.core.db.in_transaction:
            raise sqlite3.OperationalError("database is locked")
        return end(ok)
    w.core._tx_end = broken
    w.press("wa:send:1:1")
    w.core._tx_end = end
    facts = "черновик=%s часть=%s правок=%d→%d ответов=%d→%d вызовы=%s" % (
        state(w), w.part(), n_edits, len(w.edits()), n_ans, len(w.answers()), calls)
    assert any("упало: OperationalError" in ln for ln in w.lines), facts
    assert w.sends == [] and w.media == [] and sent == [], facts
    assert len(w.edits()) == n_edits, facts                          # откат — правка «📨» не легла
    assert not [c for c in calls if c[1]], facts
    assert state(w) == [(A.SENDING, 1)], facts                       # Б3в: «часть осталась sending»
    assert tpl_rows(w) == [], facts
    w.press(TPL)
    assert sent == [] and w.answers()[-1].startswith("уже решено"), (sent, w.answers()[-1])
    # отложенная правка упавшей части не «доезжает» со следующей текстовой частью (другой клиент, окно открыто)
    w.put(AS.T0 + 300, number=AS.OTHER)
    assert w.core.tick(AS.T0 + 400) == [2], w.q("SELECT id, number, state FROM drafts")
    card2 = w.q("SELECT card_id FROM drafts WHERE id=2")[0][0]
    w.core.door.window = lambda number, now=None: {"state": "open", "age": 60}
    w.core.door.send = w.send
    n101 = len(w.edits())
    w.press("wa:send:2:1", card_id=card2)
    assert state(w, 2) == [(A.SENT, 1)] and w.sends == [(AS.OTHER, AS.TEXT)] and len(w.media) == 1, (
        state(w, 2), w.sends, w.media)
    assert len(w.edits()) == n101 and w.edits(card2), (len(w.edits()), n101, w.edits(card2))
    assert not [c for c in calls if c[1]], calls
    w.restart()
    sent2 = tpl_door(w)
    w.core.tick(AS.T0 + 500)
    w.press(TPL)
    assert sent2 == [] and tpl_rows(w) == [], (sent2, tpl_rows(w))
    assert w.sends == [(AS.OTHER, AS.TEXT)] and [m[0] for m in w.media] == [AS.OTHER], (w.sends, w.media)


def test_text_part_tx_not_opened_at_boundary_card_keeps_template():
    """Транзакция текстовой части не открылась (база занята) — Б3в пишет исход без неё: возврат в pending ложится
    сразу, карточка с «📨», правка вне транзакции, часть PDF ждёт; «📨» — один шаблон."""
    w = AS.World(ATT_TPL)
    w.ready()
    sent = tpl_door(w)

    def busy():
        raise sqlite3.OperationalError("database is locked")
    w.core._tx_begin = busy
    calls = _boundary(w)
    del w.core._tx_begin
    facts = "черновик=%s часть=%s card_out=%s кнопки=%s вызовы=%s" % (
        state(w), w.part(), card_out(w), last_kb(w), calls)
    assert any("транзакция текстовой части не открылась" in ln for ln in w.lines), facts
    assert state(w) == [(A.PENDING, 1)] and w.sends == [] and w.media == [], facts
    assert w.part()[:2] == ("wait", 1) and card_out(w) == A.CARD_DELIVERED, facts
    assert last_kb(w) == KB3 + [TPL] and w.answers()[-1].startswith("окно 24 ч закрыто"), facts
    assert not [c for c in calls if c[1]], facts
    w.press(TPL)
    w.press(TPL)
    assert len(sent) == 1 and tpl_rows(w) == [(1, A.SENT, 1)], (sent, tpl_rows(w))


# ═══ (4) повторная карточка ══════════════════════════════════════════════════════════════════════════════════

def test_lost_card_answer_second_card_one_template():
    """Ответ на первую карточку потерян — ядро шлёт её ещё раз: обе карточки с «📨» этой версии. «📨» с первой
    (ядру неизвестной) — один шаблон, правка ложится на известную ядру вторую; повторы с обеих и «✅» — без дубля."""
    w = AS.World(ATT_TPL)
    w.tg.http = LostOnce(w.http)
    w.ready()
    assert w.q("SELECT card_id FROM drafts WHERE id=1") == [(None,)], w.q("SELECT card_id FROM drafts")
    w.core.tick(AS.T0 + 200)
    second = w.q("SELECT card_id FROM drafts WHERE id=1")[0][0]
    assert second and second != 101 and cards(w) == [KB3 + [TPL], KB3 + [TPL]], (second, cards(w))
    sent = tpl_door(w)
    w.press(TPL, card_id=101)
    assert len(sent) == 1 and tpl_rows(w) == [(1, A.SENT, 1)], (sent, tpl_rows(w))
    assert last_kb(w, second) == KB3 and w.edits(101) == [], (last_kb(w, second), w.edits(101))
    w.press(TPL, card_id=101)
    w.press(TPL, card_id=second)
    w.press("wa:send:1:1", card_id=101)
    assert len(sent) == 1 and tpl_rows(w) == [(1, A.SENT, 1)], (sent, tpl_rows(w))
    assert "уже ушёл" in w.answers()[-2] and "уже ушёл" in w.answers()[-1], w.answers()[-3:]
    assert w.sends == [] and w.media == [], (w.sends, w.media)
    assert last_kb(w, second) == KB3, last_kb(w, second)


def test_version2_after_template_no_button_no_second():
    """Шаблон ушёл, затем «Исправить» — версия 2: её карточка без «📨», словами «шаблон уже ушёл», строка PDF на месте;
    «📨» версии 1 — «устарело», «📨» и «✅» версии 2 — без второго шаблона."""
    w = AS.World(ATT_TPL)
    w.ready()
    sent = tpl_door(w)
    w.press(TPL)
    assert len(sent) == 1, sent
    w.press("wa:fix:1:1")
    w.uid += 1
    w.tg.handle({"update_id": w.uid, "message": {"message_id": 960, "from": AS.HUMAN, "chat": {"id": AS.CHAT},
                                                 "text": "Здравствуйте! Байк свободен, приезжайте.",
                                                 "reply_to_message": {"message_id": 101}}})
    assert state(w) == [(A.PENDING, 2)], state(w)
    card2 = w.q("SELECT card_id FROM drafts WHERE id=1")[0][0]
    kb2, text2 = cards(w)[-1], card_texts(w)[-1]
    assert card2 and card2 != 101 and kb2 == ["wa:send:1:2", "wa:fix:1:2", "wa:no:1:2"], (card2, kb2)
    assert "шаблона нет: шаблон уже ушёл (черновик №1)" in text2 and "📄 «Отправить» шлёт ВТОРЫМ" in text2, text2
    w.press(TPL)
    assert len(sent) == 1 and w.answers()[-1].startswith("устарело: версия 1"), (sent, w.answers()[-1])
    w.press("wa:tpl:1:2", card_id=card2)
    assert len(sent) == 1 and "уже ушёл" in w.answers()[-1], (sent, w.answers()[-1])
    w.press("wa:send:1:2", card_id=card2)
    assert len(sent) == 1 and "уже ушёл" in w.answers()[-1], (sent, w.answers()[-1])
    assert tpl_rows(w) == [(1, A.SENT, 1)] and w.sends == [] and w.media == [], (tpl_rows(w), w.sends, w.media)


# ═══ (5) рестарт после границы ══════════════════════════════════════════════════════════════════════════════

def test_restart_after_boundary_card_not_overwritten_one_template():
    """После границы — рестарт: старт части PDF не трогает (текст не решён), карточку не правит (ни исхода частей, ни
    снятия кнопок), «📨» после рестарта — один шаблон; второй рестарт — состояние шаблона на месте, дубля нет."""
    w = AS.World(ATT_TPL)
    w.ready()
    _boundary(w)
    assert last_kb(w) == KB3 + [TPL], last_kb(w)
    n_edits = len(w.edits())
    w.restart()
    calls = tg_watch(w)
    w.core.tick(AS.T0 + 500)
    facts = "черновик=%s часть=%s card_out=%s правок=%d→%d вызовы=%s" % (
        state(w), w.part(), card_out(w), n_edits, len(w.edits()), calls)
    assert len(w.edits()) == n_edits and last_kb(w) == KB3 + [TPL], facts
    assert state(w) == [(A.PENDING, 1)] and w.part()[:2] == ("wait", 1), facts
    assert card_out(w) == A.CARD_DELIVERED, facts
    sent = tpl_door(w)
    w.press(TPL)
    assert len(sent) == 1 and tpl_rows(w) == [(1, A.SENT, 1)] and last_kb(w) == KB3, (sent, tpl_rows(w))
    w.restart()
    sent2 = tpl_door(w)
    w.core.tick(AS.T0 + 600)
    w.press(TPL)
    assert sent2 == [] and "уже ушёл" in w.answers()[-1], (sent2, w.answers()[-1])
    assert tpl_rows(w) == [(1, A.SENT, 1)] and w.part()[:2] == ("wait", 1), (tpl_rows(w), w.part())
    assert w.sends == [] and w.media == [], (w.sends, w.media)


# ═══ (6) срок ритма ═══════════════════════════════════════════════════════════════════════════════════════════

def test_pace_due_window_closed_card_gets_template():
    """Ритм вкл: «✅» при открытом окне ставит отправку на срок («⏳ … Отменить»); окно закрылось до срока — `send_due`
    упирается в ворота двери: черновик pending v1, клиенту ничего, часть PDF ждёт, карточка — прежний ряд и «📨»
    (вместо «Отменить»), правка вне транзакции; «📨» — один шаблон."""
    w = AS.World(dict(ATT_TPL, WA_AGENT_PACE="1"))
    w.core.tick(AS.T0 - 1000)
    w.put(AS.T0 - 100)
    assert w.core.tick(AS.T0) == [1]
    w.core.rand = lambda: 0.5
    w.core.door.window = lambda number, now=None: {"state": "open", "age": 100}
    w.clock.t = AS.T0
    w.press("wa:send:1:1")
    due = w.q("SELECT due_at FROM drafts WHERE id=1")[0][0]
    assert state(w) == [(A.SCHEDULED, 1)] and due and due > AS.T0, (state(w), due)
    assert last_kb(w) == ["wa:cancel:1:1"], last_kb(w)
    w.core.door.window = lambda number, now=None: CLOSED
    w.core.door.send = lambda to, text, db_path=None: {"outcome": "not_sent", "reason": "окно 24 ч закрыто",
                                                       "window": "closed", "wamid": None}
    calls = tg_watch(w)
    w.clock.t = due + 1
    w.core.tick(due + 1)
    facts = "черновик=%s часть=%s card_out=%s кнопки=%s вызовы=%s" % (
        state(w), w.part(), card_out(w), last_kb(w), calls)
    assert state(w) == [(A.PENDING, 1)] and w.sends == [] and w.media == [], facts
    assert w.part()[:2] == ("wait", 1) and card_out(w) == A.CARD_DELIVERED, facts
    assert last_kb(w) == KB3 + [TPL], facts
    assert not [c for c in calls if c[1]], facts
    sent = tpl_door(w)
    w.press(TPL)
    w.press(TPL)
    assert len(sent) == 1 and tpl_rows(w) == [(1, A.SENT, 1)], (sent, tpl_rows(w))


# ═══ (7) как раньше: прежнее ядро с шаблонами на той же границе ═══════════════════════════════════════════════

def test_same_boundary_plain_core_same_outcome():
    """Только шаблоны (прежнее ядро wa_agent.Core) и шаблоны с PDF (AttachCore) на одной и той же границе: тот же исход
    черновика, тот же ответ нажавшему, те же слова правки и та же клавиатура."""
    out = []
    for env in (TPL_ONLY, ATT_TPL):
        w = AS.World(env)
        w.ready()
        _boundary(w)
        out.append((type(w.core).__name__, state(w), w.answers()[-1], last_said(w), last_kb(w), w.sends, w.media))
    plain, att = out
    assert plain[0] == "Core" and att[0] == "AttachCore", (plain[0], att[0])
    assert plain[1:] == att[1:], out
    assert plain[4] == KB3 + [TPL], plain


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                                # noqa: BLE001
        pass
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    bad = 0
    for name, fn in tests:
        try:
            fn()
            print("PASS", name)
        except Exception as e:                                       # noqa: BLE001
            bad += 1
            print("FAIL", name, "—", type(e).__name__, str(e)[:600])
    print("ИТОГ %d/%d" % (len(tests) - bad, len(tests)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
