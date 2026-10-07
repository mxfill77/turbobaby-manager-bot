#!/usr/bin/env python3
"""NIGHT0710 Б3в — тесты агента мутантов: каждый ловит мутанта, выжившего на наборах кандидата 79cfd3d
(`attach_aux/mut/out_1`). Формат наборов дерева (PASS/FAIL, «ИТОГ N/M»). Всё на подделках тех же наборов
(`test_wa_agent_attach` — ядро с FakeTG/FakeDoor/Fetch/Find, `test_wa_attach_svc` — служба с поддельным Bot API):
сети нет, модель, мост, Telegram и WhatsApp не зовутся.

Кладётся в tests/ дерева. WA_AGENT_SRC=<каталог> подменяет модули (прогон мутантов)."""
import base64
import hashlib
import os
import sqlite3
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
if os.environ.get("WA_AGENT_SRC"):
    sys.path.insert(0, os.environ["WA_AGENT_SRC"])

import wa_agent as A  # noqa: E402
import wa_agent_attach as X  # noqa: E402
import test_wa_agent_attach as T  # noqa: E402  (ядро: FakeTG, FakeDoor, Fetch, Find, World)
import test_wa_attach_svc as SVC  # noqa: E402  (служба: World с поддельным Bot API)

NUM, T0 = T.NUM, T.T0
OTHER = "66899999999"
PDF_B = b"%PDF-1.4 OTHER client signed contract bytes"


def sha(data):
    return hashlib.sha256(data).hexdigest()


# ═══ двое клиентов, два договора ══════════════════════════════════════════════════════════════════

CONTRACTS = {
    NUM: {"row": 41, "doc_id": "D41", "pdf_id": "F41", "signed_at": "2026-10-01", "bike": "PCX 160 5580",
          "data": T.PDF, "name": "contract_41.pdf"},
    OTHER: {"row": 77, "doc_id": "D77", "pdf_id": "F77", "signed_at": "2026-10-02", "bike": "NMAX 155 1234",
            "data": PDF_B, "name": "contract_77.pdf"},
}
BY_FILE = {c["pdf_id"]: c for c in CONTRACTS.values()}


def tools_of(c):
    """Итог сверки Т4а клиента: его аренда, его подписанный договор и PDF этого договора."""
    return {"state": "done", "results": [
        T.res("rental", "fact", [{"kind": "rental", "booking_id": "B%d" % c["row"], "bike": c["bike"]}]),
        T.res("contract", "fact", [{"kind": "contract", "row": c["row"], "doc_id": c["doc_id"], "bike": c["bike"],
                                    "signed_at": c["signed_at"], "pdf_id": c["pdf_id"]}]),
        T.res("contract_pdf", "fact", [{"kind": "pdf", "id": c["pdf_id"], "name": c["name"], "size": len(c["data"]),
                                        "sha256": sha(c["data"]), "row": c["row"]}]),
    ]}


class Model2(A.Model):
    def __init__(self):
        self.last = None

    def draft(self, number, upto_id):
        self.last = {"tools": tools_of(CONTRACTS[number])}
        return "черновик для …%s" % number[-2:]


class Fetch2:
    """contract_pdf: байты договора по file_id (мост называет и свою строку реестра)."""
    def __init__(self):
        self.calls = []

    def __call__(self, file_id):
        self.calls.append(file_id)
        c = BY_FILE[file_id]
        return {"ok": True, "id": file_id, "verified": True, "size": len(c["data"]), "sha256": sha(c["data"]),
                "row": c["row"], "content_b64": base64.b64encode(c["data"]).decode()}


class Find2:
    """contract_find: реестр по номеру клиента; revoked — номера, чей договор отозван."""
    def __init__(self):
        self.calls, self.revoked = [], set()

    def __call__(self, **kw):
        self.calls.append(kw)
        phone = kw.get("phone")
        if phone in self.revoked or phone not in CONTRACTS:
            return {"ok": True, "outcome": "none_signed", "checked": {"unread": [], "undated_signed": 0}}
        c = CONTRACTS[phone]
        return {"ok": True, "outcome": "one",
                "pick": {"row": c["row"], "doc_id": c["doc_id"], "pdf_id": c["pdf_id"], "signed_at": c["signed_at"],
                         "signed": True},
                "checked": {"rows_scanned": 50, "unread": [], "undated_signed": 0, "complete": True}}


class World2:
    def __init__(self):
        d = tempfile.mkdtemp(prefix="wa_attach_mut_t_")
        self.qpath, self.dbpath = os.path.join(d, "q.db"), os.path.join(d, "agent.db")
        q = sqlite3.connect(self.qpath)
        q.execute(T.QSCHEMA)
        q.commit()
        q.close()
        self.model, self.tg, self.door = Model2(), T.FakeTG(), T.FakeDoor()
        self.fetch, self.find, self.lines = Fetch2(), Find2(), []
        self.core = X.AttachCore(self.dbpath, self.qpath, self.model, self.tg, self.door, log=self.lines.append,
                                 attach=True, pdf_fetch=self.fetch, contract_find=self.find)
        self.core.tick(T0 - 1000)

    def put(self, ts, number):
        q = sqlite3.connect(self.qpath)
        q.execute("INSERT INTO wa_inbox(ts_queued, from_number, msg_type, text, ts_msg, echo, history, wamid) "
                  "VALUES(?,?,'text','x',?,0,0,NULL)", (ts, number, ts))
        q.commit()
        q.close()

    def q(self, sql, args=()):
        db = sqlite3.connect(self.dbpath)
        try:
            return db.execute(sql, args).fetchall()
        finally:
            db.close()


def _two():
    w = World2()
    w.put(T0, NUM)
    w.put(T0 + 1, OTHER)
    made = w.core.tick(T0 + 100)
    assert len(made) == 2, made
    ids = dict(w.q("SELECT number, id FROM drafts"))
    assert set(ids) == {NUM, OTHER}, ids
    return w, ids


def test_two_clients_each_gets_own_contract():
    """Два клиента, два договора: «Отправить» каждого шлёт ЕГО PDF (файл, sha256) ЕМУ — в любом порядке нажатий."""
    w, ids = _two()
    for number in sorted(ids, key=lambda n: ids[n]):
        out = w.core.press(ids[number], 1, A.ACT_SEND, "Даня", T0 + 200)
        assert out.get("parts") == {"text": A.SENT, "pdf": A.SENT}, (number, out)
        to, _kind, _mime, fname, got = w.door.media[-1]
        c = CONTRACTS[number]
        assert (to, fname, got) == (number, c["name"], sha(c["data"])), (number, w.door.media)
    assert w.fetch.calls == [CONTRACTS[n]["pdf_id"] for n in sorted(ids, key=lambda n: ids[n])], w.fetch.calls


def test_two_clients_revoked_contract_not_masked_by_other_draft():
    """Договор клиента отозван, у соседа — жив: реестр перечитывается по ЕГО номеру и ничего не уходит."""
    w, ids = _two()
    low = min(ids, key=lambda n: ids[n])
    w.find.revoked.add(low)
    out = w.core.press(ids[low], 1, A.ACT_SEND, "Даня", T0 + 200)
    assert out["state"] == A.STALE and w.door.sends == [] and w.door.media == [], (out, w.door.sends, w.door.media)
    assert w.find.calls and w.find.calls[-1]["phone"] == low, w.find.calls


# ═══ основание: каждый ключ реестра сам по себе ════════════════════════════════════════════════════

def _registry_refuses(**over):
    pick = {"row": 41, "doc_id": "D41", "pdf_id": "F41", "signed_at": "2026-10-01", "signed": True}
    pick.update(over)
    w = T.World(find=T.Find(pick=pick))
    did = w.draft()
    out = w.core.press(did, 1, A.ACT_SEND, "Даня", T0 + 200)
    assert out["state"] == A.STALE and w.door.sends == [] and w.door.media == [] and w.fetch.calls == [], (over, out)
    return out


def test_registry_unsigned_pick_nothing_sent():
    """Реестр: договор найден, но НЕ подписан (signed False) — отозван: ничего не уходит."""
    out = _registry_refuses(signed=False)
    assert "не подписан" in out["words"], out


def test_registry_other_pdf_id_nothing_sent():
    """Реестр: тот же договор и строка, но другой файл PDF (pdf_id) — ничего не уходит."""
    out = _registry_refuses(pdf_id="F99")
    assert "pdf_id" in out["words"], out


def test_registry_other_doc_id_nothing_sent():
    """Реестр: та же строка и файл, но другой документ (doc_id) — ничего не уходит."""
    out = _registry_refuses(doc_id="D99")
    assert "doc_id" in out["words"], out


def test_registry_other_row_nothing_sent():
    """Реестр: тот же документ и файл, но другая строка (row) — ничего не уходит."""
    out = _registry_refuses(row=99)
    assert "row" in out["words"], out


def test_core_without_contract_find_nothing_sent():
    """Ядру не дали двери реестра — «Отправить» с PDF ничего не шлёт (stale со словами), не «пропуск»."""
    w = T.World()
    w.core.contract_find = None
    did = w.draft()
    out = w.core.press(did, 1, A.ACT_SEND, "Даня", T0 + 200)
    assert out["state"] == A.STALE and w.door.sends == [] and w.door.media == [], out
    assert "contract_find" in out["words"], out


class FetchNoVerified(T.Fetch):
    def __call__(self, file_id):
        out = T.Fetch.__call__(self, file_id)
        out.pop("verified", None)
        return out


def test_unverified_pdf_not_sent():
    """Ответ contract_pdf без verified (мост файл не сверил) — PDF не уходит, «не ушёл» с причиной."""
    w = T.World(fetch=FetchNoVerified())
    did = w.draft()
    out = w.core.press(did, 1, A.ACT_SEND, "Даня", T0 + 200)
    assert w.door.media == [] and w.part(did)[0] == A.NOT_SENT and "без verified" in out["words"], out


# ═══ две части — у каждой своё подтверждение, поздние статусы по точной части ═══════════════════════

def test_text_delivery_by_own_wamid_only():
    """delivered по wamid PDF не доставляет ТЕКСТ: у текста своя доставка."""
    w = T.World()
    did = w.draft()
    w.core.press(did, 1, A.ACT_SEND, "Даня", T0 + 200)
    w.put(T0 + 206, "status", wamid="wamid.P1", word="delivered")
    p = w.core.parts(did)
    assert p["delivery"][0] == X.D_DELIVERED and p["text_delivery"][0] == X.D_UNKNOWN, p


def test_saved_text_status_does_not_confirm_pdf():
    """Сохранённый delivered ТЕКСТА не подтверждает PDF того же черновика: у PDF только sent — «принято WhatsApp»;
    и после потери очереди хранимое судит по точному wamid."""
    w = T.World()
    did = w.draft()
    w.core.press(did, 1, A.ACT_SEND, "Даня", T0 + 200)
    w.put(T0 + 205, "status", wamid="wamid.T1", word="delivered")
    w.put(T0 + 206, "status", wamid="wamid.P1", word="sent")
    w.core.tick(T0 + 400)
    saved = sorted(w.q("SELECT wamid, status, part FROM part_status"))
    assert saved == [("wamid.P1", "sent", "pdf"), ("wamid.T1", "delivered", "text")], saved
    p = w.core.parts(did)
    assert p["delivery"][0] == X.D_ACCEPTED and p["text_delivery"][0] == X.D_DELIVERED, p
    w.core.queue_path = os.path.join(os.path.dirname(w.qpath), "нет.db")
    assert w.core.delivery_check(NUM, "wamid.P1")[0] == X.D_ACCEPTED


def test_late_status_saved_to_its_attempt():
    """Поздний delivered второй попытки PDF ложится в part_status с attempt=2, а не 1."""
    door = T.FakeDoor(media="not_sent")
    w = T.World(door=door)
    did = w.draft()
    w.core.press(did, 1, A.ACT_SEND, "Даня", T0 + 200)
    door.media_out = "sent"
    assert w.core.press(did, 1, X.ACT_PDF, "Пым", T0 + 300)["ok"]
    assert w.part(did)[:3] == (A.SENT, 2, "wamid.P2"), w.part(did)
    w.put(T0 + 310, "status", wamid="wamid.P2", word="delivered")
    w.core.tick(T0 + 500)
    got = w.q("SELECT wamid, status, part, attempt FROM part_status WHERE wamid='wamid.P2'")
    assert got == [("wamid.P2", "delivered", "pdf", 2)], got


def test_failed_status_kept_by_part():
    """Статус failed по wamid PDF хранится по части; без очереди проверка доставки всё равно говорит «failed»."""
    w = T.World()
    did = w.draft()
    w.core.press(did, 1, A.ACT_SEND, "Даня", T0 + 200)
    w.put(T0 + 206, "status", wamid="wamid.P1", word="failed")
    w.core.tick(T0 + 400)
    assert w.q("SELECT status, part FROM part_status WHERE wamid='wamid.P1'") == [("failed", "pdf")]
    w.core.queue_path = os.path.join(os.path.dirname(w.qpath), "нет.db")
    assert w.core.delivery_check(NUM, "wamid.P1")[0] == X.D_FAILED


# ═══ «неизвестно» вслепую не повторяется ═══════════════════════════════════════════════════════════

class DoorTimeout(T.FakeDoor):
    """Провайдер принял файл и замолчал: исключение таймаута ПОСЛЕ отправки."""
    def send_media(self, to, media):
        T.FakeDoor.send_media(self, to, media)
        raise TimeoutError("read timed out")


class DoorGarbage(T.FakeDoor):
    """Дверь вернула нечитаемое (None) — исход не назван."""
    def send_media(self, to, media):
        T.FakeDoor.send_media(self, to, media)
        return None


def _unknown_not_resent(door):
    w = T.World(door=door)
    did = w.draft()
    out = w.core.press(did, 1, A.ACT_SEND, "Даня", T0 + 200)
    assert w.part(did)[:3] == (A.UNSURE, 1, None) and out["words"] == "текст: ушёл · PDF: неизвестно", (w.part(did), out)
    got = w.core.press(did, 1, X.ACT_PDF, "Пым", T0 + 300)
    assert got.get("need_permit") and len(door.media) == 1 and w.part(did)[0] == A.UNSURE, got


def test_pdf_door_timeout_is_unknown_not_resent():
    """Таймаут/обрыв на двери PDF — «неизвестно»; простое «Дослать» не шлёт второй раз (нужна кнопка риска)."""
    _unknown_not_resent(DoorTimeout())


def test_pdf_door_garbage_answer_is_unknown_not_resent():
    """Нечитаемый ответ двери PDF — «неизвестно», а не «не ушёл»; простое «Дослать» второй раз не шлёт."""
    _unknown_not_resent(DoorGarbage())


def test_resend_refused_when_text_unknown():
    """Текст «неизвестно» — «Дослать PDF» (и с риском) не шлёт файл без текста."""
    w = T.World(door=T.FakeDoor(text="unknown"))
    did = w.draft()
    w.core.press(did, 1, A.ACT_SEND, "Даня", T0 + 200)
    for act in (X.ACT_PDF, X.ACT_PDF_RISK):
        got = w.core.press(did, 1, act, "Пым", T0 + 300)
        assert not got["ok"] and "дослать нельзя" in got["words"] and w.door.media == [], (act, got)


# ═══ двойное нажатие — одна отправка ═══════════════════════════════════════════════════════════════

def test_stale_attempt_button_no_bridge_call():
    """Кнопка прежней попытки — «уже решено» с номером ТЕКУЩЕЙ попытки, ДО моста: реестр не читается, двери нет."""
    door = T.FakeDoor(media="not_sent")
    w = T.World(door=door)
    did = w.draft()
    w.core.press(did, 1, A.ACT_SEND, "Даня", T0 + 200)
    w.core.press(did, 1, X.ACT_PDF, "Пым", T0 + 300)
    assert w.part(did)[:2] == (A.NOT_SENT, 2)
    finds = len(w.find.calls)
    door.media_out = "sent"
    old = w.core.press(did, 1, X.ACT_PDF, "Даня", T0 + 301)
    assert not old["ok"] and old["words"].startswith("уже решено") and "попытка 2" in old["words"], old
    assert len(w.find.calls) == finds and len(door.media) == 2, (w.find.calls, door.media)


def test_sent_pdf_not_resent_by_current_attempt_button():
    """PDF ушёл (попытка 1): поздний колбэк «Дослать» той же попытки — «уже решено», второй PDF не уходит."""
    w = T.World()
    did = w.draft()
    w.core.press(did, 1, A.ACT_SEND, "Даня", T0 + 200)
    for act in (X.ACT_PDF, X.ACT_PDF_RISK):
        got = w.core.press(did, 1, act, "Пым", T0 + 300)
        assert not got["ok"] and got["words"].startswith("уже решено"), (act, got)
    assert len(w.door.media) == 1 and w.part(did)[:2] == (A.SENT, 1), (w.door.media, w.part(did))


# ═══ атомарность текстовой части ═══════════════════════════════════════════════════════════════════

def test_text_part_error_rolls_back_in_process():
    """Исключение после ответа двери текста (процесс жив) — откат: исход текста и outbox не легли, транзакция закрыта;
    черновик остаётся sending (рестарт скажет «неизвестно»), PDF не звали."""
    w = T.World()
    did = w.draft()
    real = w.core._plog

    def boom(draft_id, part, *a, **kw):
        if part == "text":
            raise RuntimeError("диск")
        return real(draft_id, part, *a, **kw)
    w.core._plog = boom
    try:
        w.core.press(did, 1, A.ACT_SEND, "Даня", T0 + 200)
        raised = False
    except RuntimeError:
        raised = True
    assert raised and not w.core.db.in_transaction
    assert w.q("SELECT state, wamid FROM drafts WHERE id=?", (did,)) == [(A.SENDING, None)], w.q("SELECT state FROM drafts")
    assert w.q("SELECT COUNT(*) FROM outbox")[0][0] == 0 and w.door.media == []


def test_no_pdf_draft_card_gets_outcome():
    """Флаг вкл, сверка PDF не приняла (вложения нет) — уходит только текст, и исход текста ЛОЖИТСЯ на карточку."""
    w = T.World(tools=T.tools_ok(contract=T.res("contract", "empty", reason="подписанного нет")))
    did = w.draft()
    out = w.core.press(did, 1, A.ACT_SEND, "Даня", T0 + 200)
    assert out["ok"] and w.door.media == [], out
    mine = [words for d, words in w.tg.done if d == did]
    assert mine and mine[-1].startswith(A.SENT), w.tg.done


# ═══ служба: флаг засчитывается только при обеих дверях сверки ═════════════════════════════════════

def test_svc_tools_without_one_door_old_core():
    """У сверки нет двери contract (или contract_pdf) — служба собирает прежний Core и говорит это строкой старта."""
    for drop in ("contract", "contract_pdf"):
        w = SVC.World(SVC.ON)
        full = {"cash": lambda **kw: {"ok": False}, "contract": w.model.find, "contract_pdf": w.model.fetch}
        w.model.tools = {k: v for k, v in full.items() if k != drop}
        del w.lines[:]
        w.build(w.environ)
        assert type(w.core) is A.Core, (drop, type(w.core))
        said = [ln for ln in w.lines if ln.startswith("PDF клиенту (WA_AGENT_ATTACH)")]
        assert said and "нет дверей contract_pdf/contract" in said[-1], (drop, said)


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
