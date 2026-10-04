#!/usr/bin/env python3
"""Фото и файлы, присланные клиенту с телефона, паузы не ставят; текст ставит (WAPAUSEMEDIA0410, решение
владельца 05.10.2026, вопрос Б).

Эхо с телефона — поле `smb_message_echoes` Coexistence; в очередь его кладёт ЖИВОЙ разбор входа
(`wa_webhook.normalize_wa_payload` → `WAQueueDB.enqueue_stats`), тела — форма Cloud API (image/video/document
с `id`, `mime_type`, `caption`; text с `body`; audio с `voice`; sticker). Ядро wa-agent живое; модель, Telegram
и дверь — подделки test_wa_agent. Сети нет; модель, мост, Telegram, WhatsApp и 360dialog не зовутся; номера и
тексты выдуманные. Временные файлы тест НЕ удаляет.

Случаи: фото · видео · документ · фото с подписью — паузы нет; текст — пауза; фото, потом текст — одна пауза
(разными тактами и одним); голосовое, аудио, стикер — пауза, как прежде; эхо нашей API-отправки — как было;
клиент уже на паузе, затем фото — пауза остаётся; после фото клиент пишет — черновик без «Продолжить»;
«Отправить» после фото — не отправлено и без паузы; после фото и текста — одна пауза; история модели — фото
«мы»; журнал без текста и номера.
Мутанты: каждый замок ломается копией модуля (WA_AGENT_SRC=<каталог> ставит копии впереди дерева) — набор
обязан упасть; итог — число упавших случаев на мутант."""
import os
import shutil
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

import wa_agent as A  # noqa: E402
import wa_agent_model as WM  # noqa: E402
import wa_kind as K  # noqa: E402
import wa_webhook as W  # noqa: E402
import test_wa_agent as T  # noqa: E402

CL, OUR = "66800000001", "66800000009"      # выдуманные: клиент и наш номер
NOW = int(time.time())                      # эхо моложе суток: живой разбор не назовёт его историей
QUIET = A.QUIET_DEFAULT
MIME = {"image": "image/jpeg", "video": "video/mp4", "document": "application/pdf",
        "audio": "audio/ogg; codecs=opus", "voice": "audio/ogg; codecs=opus", "sticker": "image/webp"}
ASK = "ВОПРОС-ПЕРВЫЙ а скутер на неделю есть?"
ASK2 = "ВОПРОС-ВТОРОЙ а шлем дадите?"
CAPTION = "ПОДПИСЬ вот этот байк, синий"
PHONE_TEXT = "ТЕКСТ-С-ТЕЛЕФОНА добрый день, сейчас уточню"


class World:
    def __init__(self):
        d = tempfile.mkdtemp(prefix="wa_pause_media_")
        self.q = W.WAQueueDB(os.path.join(d, "wa_queue.db"))
        self.qpath, self.dbpath = self.q.db_path, os.path.join(d, "wa_agent.db")
        self.model, self.tg, self.door, self.lines = T.FakeModel(), T.FakeTG(), T.FakeDoor(), []
        self.core = A.Core(self.dbpath, self.qpath, self.model, self.tg, self.door, log=self.lines.append)
        self.core.tick(NOW - 1000)                                      # первый старт: курсор на MAX(id)
        self.n = 0

    def _feed(self, field, msg):
        val = {"messaging_product": "whatsapp", "metadata": {"display_phone_number": OUR}}
        val["message_echoes" if field == "smb_message_echoes" else "messages"] = [msg]
        p = {"object": "whatsapp_business_account", "entry": [{"changes": [{"field": field, "value": val}]}]}
        st = self.q.enqueue_stats(W.normalize_wa_payload(p, OUR))
        assert st["inserted"] == 1, st
        c = sqlite3.connect(self.qpath)
        rid = c.execute("SELECT MAX(id) FROM wa_inbox").fetchone()[0]
        c.close()
        return rid

    def client_says(self, text=ASK):
        self.n += 1
        return self._feed("messages", {"from": CL, "id": "wamid.IN%d" % self.n, "timestamp": str(NOW),
                                       "type": "text", "text": {"body": text}})

    def phone(self, kind, caption=None, wamid=None):
        """Эхо того, что человек прислал клиенту С ТЕЛЕФОНА (поле smb_message_echoes)."""
        self.n += 1
        m = {"from": OUR, "to": CL, "id": wamid or "wamid.PH%d" % self.n, "timestamp": str(NOW), "type": kind}
        if kind == "text":
            m["text"] = {"body": caption or PHONE_TEXT}
        else:
            body = {"id": "MEDIA%d" % self.n, "mime_type": MIME[kind]}
            if kind == "audio":
                body["voice"] = True
            if kind == "document":
                body["filename"] = "price.pdf"
            if caption:
                body["caption"] = caption
            m[kind] = body
        return self._feed("smb_message_echoes", m)

    def row(self, rid):
        c = sqlite3.connect(self.qpath)
        r = c.execute("SELECT msg_type, echo, history, caption FROM wa_inbox WHERE id=?", (rid,)).fetchone()
        c.close()
        return r

    def client(self):
        r = self.core.db.execute("SELECT last_in_id, done_upto, paused, pause_no, pause_row, ctx FROM clients "
                                 "WHERE number=?", (CL,)).fetchone()
        return dict(zip(("last_in", "done", "paused", "pause_no", "pause_row", "ctx"), r)) if r else None

    def draft(self, did):
        return self.core.db.execute("SELECT state, reason FROM drafts WHERE id=?", (did,)).fetchone()

    def pending(self):
        return [r[0] for r in self.core.db.execute("SELECT id FROM drafts WHERE number=? AND state=? ORDER BY id",
                                                   (CL, A.PENDING))]

    def said(self, rid):
        return [ln for ln in self.lines if ln.startswith("эхо строки %d:" % rid)]


def with_draft(w):
    """Клиент спросил, черновик родился. → (id входящего, id черновика)."""
    rin = w.client_says()
    w.core.tick(NOW + QUIET + 60)
    p = w.pending()
    assert len(p) == 1 and w.model.calls == 1, ("черновика нет", p)
    return rin, p[0]


def assert_no_pause(w, rid, kind, rin, did, ctx0):
    c = w.client()
    assert w.row(rid)[:3] == (kind, 1, 0), ("строка очереди не эхо живого разбора", w.row(rid))
    assert c["paused"] == 0 and c["pause_no"] == 0 and w.tg.asks == [], ("эхо %s поставило паузу" % kind, c,
                                                                         w.tg.asks)
    # ждущий черновик, прежние входящие и версия контекста — как у всякого эха с телефона
    st = w.draft(did)
    assert st[0] == A.SUPERSEDED and "ответили с телефона" in st[1], ("черновик не снят, как прежде", st)
    assert c["done"] == rin and c["ctx"] == ctx0 + 1, ("эхо не закрыло прежние входящие", c, ctx0)
    said = w.said(rid)
    assert len(said) == 1 and said[0].endswith("— вид %s, паузы нет (WAPAUSEMEDIA0410)" % kind), said


def assert_paused(w, rid, kind, did=None):
    c = w.client()
    assert w.row(rid)[:3] == (kind, 1, 0), w.row(rid)
    assert c["paused"] == 1 and c["pause_no"] == 1 and c["pause_row"] == rid and w.tg.asks == [(CL, 1)], (
        "эхо %s — нет паузы" % kind, c, w.tg.asks)
    if did is not None:
        assert w.draft(did)[0] == A.SUPERSEDED, w.draft(did)
    said = w.said(rid)
    assert len(said) == 1 and said[0].endswith("— пауза"), said
    w.core.tick(NOW + 3 * QUIET)
    w.client_says(ASK2)
    w.core.tick(NOW + 6 * QUIET)
    assert w.pending() == [] and w.model.calls == (1 if did is not None else 0), ("черновик на паузе", w.pending())


def no_pause_case(kind, caption=None):
    w = World()
    rin, did = with_draft(w)
    ctx0 = w.client()["ctx"]
    rid = w.phone(kind, caption)
    w.core.tick(NOW + QUIET + 70)
    assert_no_pause(w, rid, kind, rin, did, ctx0)
    return w, rid


CASES = []


def case(fn):
    CASES.append(fn)
    return fn


# ═══ фото, видео, документ — паузы нет ═════════════════════════════════════════════════════════

@case
def c_photo_no_pause():
    no_pause_case("image")


@case
def c_video_no_pause():
    no_pause_case("video")


@case
def c_document_no_pause():
    no_pause_case("document")


@case
def c_photo_with_caption_no_pause():
    w, rid = no_pause_case("image", CAPTION)
    assert w.row(rid)[3] == CAPTION, ("подпись не дошла до очереди", w.row(rid))


# ═══ текст и неназванное владельцем — пауза, как прежде ════════════════════════════════════════

@case
def c_text_pauses():
    w = World()
    _rin, did = with_draft(w)
    rid = w.phone("text")
    w.core.tick(NOW + QUIET + 70)
    assert_paused(w, rid, "text", did)


@case
def c_voice_pauses():
    """Голосовое: Cloud API шлёт его видом audio с voice=true; вид voice — тоже пауза."""
    for kind in ("audio", "voice"):
        w = World()
        _rin, did = with_draft(w)
        rid = w.phone(kind)
        w.core.tick(NOW + QUIET + 70)
        assert_paused(w, rid, kind, did)


@case
def c_sticker_pauses():
    w = World()
    _rin, did = with_draft(w)
    rid = w.phone("sticker")
    w.core.tick(NOW + QUIET + 70)
    assert_paused(w, rid, "sticker", did)


# ═══ фото и текст вместе ═══════════════════════════════════════════════════════════════════════

@case
def c_photo_then_text_one_pause():
    """Фото, потом текст — одна пауза, на строке текста; и разными тактами, и одним."""
    for one_tick in (False, True):
        w = World()
        _rin, did = with_draft(w)
        r1 = w.phone("image")
        if not one_tick:
            w.core.tick(NOW + QUIET + 65)
            assert w.client()["paused"] == 0 and w.tg.asks == [], ("фото поставило паузу", w.client())
        r2 = w.phone("text")
        w.core.tick(NOW + QUIET + 70)
        assert w.said(r1)[0].endswith("паузы нет (WAPAUSEMEDIA0410)"), w.said(r1)
        assert_paused(w, r2, "text", did)


@case
def c_already_paused_then_photo_stays():
    """Клиент уже на паузе (текст с телефона), затем фото — пауза остаётся, второго вопроса нет."""
    w = World()
    _rin, _did = with_draft(w)
    r1 = w.phone("text")
    w.core.tick(NOW + QUIET + 65)
    assert w.client()["paused"] == 1 and w.tg.asks == [(CL, 1)], w.client()
    w.phone("image")
    w.core.tick(NOW + QUIET + 70)
    c = w.client()
    assert c["paused"] == 1 and c["pause_no"] == 1 and c["pause_row"] == r1 and w.tg.asks == [(CL, 1)], (
        "фото сняло или сменило паузу", c, w.tg.asks)
    w.client_says(ASK2)
    w.core.tick(NOW + 6 * QUIET)
    assert w.pending() == [] and w.model.calls == 1, ("черновик на паузе", w.pending())
    r = w.core.resume(CL, 1, "owner")
    assert r["ok"], r


@case
def c_after_photo_client_writes_draft_without_resume():
    """Смысл решения: после фото клиент отвечает — черновик рождается сам, «Продолжить» не нужно."""
    w = World()
    _rin, _did = with_draft(w)
    w.phone("image", CAPTION)
    w.core.tick(NOW + QUIET + 70)
    rin2 = w.client_says(ASK2)
    w.core.tick(NOW + 3 * QUIET)
    p = w.pending()
    assert len(p) == 1 and w.model.calls == 2 and w.tg.asks == [], ("черновика нет или пауза", p, w.tg.asks)
    assert w.core.db.execute("SELECT upto_id FROM drafts WHERE id=?", (p[0],)).fetchone()[0] == rin2


# ═══ эхо нашей API-отправки — как было ═════════════════════════════════════════════════════════

@case
def c_our_api_echo_as_before():
    w = World()
    _rin, did = with_draft(w)
    r = w.core.press(did, 1, A.ACT_SEND, "owner")
    assert r["ok"] and r["state"] == A.SENT and w.door.sends, r
    w.core._sent_out("wamid.TOPICMEDIA", CL, "[фото]", A.VIA_TOPIC, NOW + QUIET + 61, kind="фото")
    ctx0 = w.client()["ctx"]
    e1 = w.phone("text", wamid="wamid.OUT1")                         # эхо «Отправить» агента
    e2 = w.phone("image", wamid="wamid.TOPICMEDIA")                  # эхо фото, ушедшего из темы через API
    w.core.tick(NOW + QUIET + 70)
    c = w.client()
    assert c["paused"] == 0 and w.tg.asks == [] and c["ctx"] == ctx0, ("эхо нашей отправки — пауза", c)
    assert w.said(e1) == [] and w.said(e2) == [], (w.said(e1), w.said(e2))
    assert w.draft(did)[0] == A.SENT, w.draft(did)


# ═══ «Отправить» до такта ══════════════════════════════════════════════════════════════════════

@case
def c_press_after_photo_not_sent_no_pause():
    """Черновик, фото с телефона ещё не разобрано тактом, «Отправить» — не отправлено (как прежде), паузы нет."""
    w = World()
    _rin, did = with_draft(w)
    rid = w.phone("image")
    r = w.core.press(did, 1, A.ACT_SEND, "owner", now=NOW + QUIET + 65)
    assert not r["ok"] and r["state"] == A.SUPERSEDED and r["words"] == "не отправлено: ответили с телефона", r
    assert w.door.sends == [] and w.client()["paused"] == 0 and w.tg.asks == [], (w.client(), w.tg.asks)
    w.core.tick(NOW + QUIET + 70)
    assert w.client()["paused"] == 0 and w.tg.asks == [], ("такт после «Отправить» поставил паузу", w.client())
    assert w.said(rid)[0].endswith("паузы нет (WAPAUSEMEDIA0410)"), w.said(rid)


@case
def c_press_after_photo_and_text_one_pause():
    """Фото и текст с телефона до такта, «Отправить» — не отправлено, одна пауза на строке текста."""
    w = World()
    _rin, did = with_draft(w)
    w.phone("image")
    r2 = w.phone("text")
    r = w.core.press(did, 1, A.ACT_SEND, "owner", now=NOW + QUIET + 65)
    assert not r["ok"] and r["state"] == A.SUPERSEDED and w.door.sends == [], r
    c = w.client()
    assert c["paused"] == 1 and c["pause_row"] == r2 and w.tg.asks == [(CL, 1)], (c, w.tg.asks)
    w.core.tick(NOW + QUIET + 70)
    c = w.client()
    assert c["paused"] == 1 and c["pause_no"] == 1 and w.tg.asks == [(CL, 1)], ("вторая пауза", c, w.tg.asks)


# ═══ история модели и журнал ═══════════════════════════════════════════════════════════════════

@case
def c_model_history_photo_is_ours():
    """В истории модели фото с телефона — наше («мы · [фото] подпись»), вопрос до него отвечен."""
    w = World()
    rin, _did = with_draft(w)
    rid = w.phone("image", CAPTION)
    w.core.tick(NOW + QUIET + 70)
    ad = WM.ModelAdapter(w.qpath, lambda s, u: ("", {}), agent_db=w.dbpath, clock=lambda: NOW + 100)
    items, _missing = ad._history(CL, rid)
    ph = [it for it in items if it["key"] == "wamid.PH%d" % (w.n)]
    assert len(ph) == 1 and ph[0]["who"] == "мы" and ph[0]["word"] == "фото" and ph[0]["text"] == CAPTION, ph
    assert ad._tail(items) == [], ("вопрос клиента до фото — всё ещё «сейчас»", ad._tail(items))
    assert any(it["who"] == "клиент" and it["text"] == ASK for it in items), items
    assert rin < rid


@case
def c_journal_no_text_no_number():
    w, _rid = no_pause_case("image", CAPTION)
    log = "\n".join(w.lines)
    assert CAPTION not in log and ASK not in log and CL not in log and OUR not in log, log


@case
def c_rule_is_closed_list():
    """Решение — закрытый список: ровно фото, видео, документ; пустое, незнакомое, правка — пауза."""
    assert K.ECHO_NO_PAUSE_TYPES == frozenset(("image", "video", "document")), K.ECHO_NO_PAUSE_TYPES
    for t in ("image", "video", "document", " Image "):
        assert K.echo_pauses(t) is False, t
    for t in ("text", "audio", "voice", "sticker", "location", "contacts", "interactive", "edit", "unsupported",
              "", None, 5):
        assert K.echo_pauses(t) is True, t


def run_cases(quiet=False):
    failed = []
    for fn in CASES:
        try:
            fn()
            if not quiet:
                print("PASS", fn.__name__)
        except Exception as e:                                       # noqa: BLE001
            failed.append(fn.__name__)
            if not quiet:
                print("FAIL", fn.__name__, type(e).__name__, str(e)[:300])
    return failed


# замок → (файл, было, стало): копия модуля с одной правкой; набор обязан упасть
MUTANTS = [
    ("фото снова ставит паузу (такт)", "wa_agent.py",
     "        if pause:\n            self._pause(number, rid, now)\n",
     "        self._pause(number, rid, now)\n"),
    ("фото снова ставит паузу («Отправить»)", "wa_agent.py",
     "                    prid = self._pausing_echo(number, upto)\n",
     "                    prid = rid\n"),
    ("«Отправить»: решает первое эхо — текст после фото без паузы", "wa_agent.py",
     "                return rid\n        return None\n\n    # ── нажатие",
     "                return rid\n            if self._live_kind(msg_type, echo, history) == wa_kind.KIND_ECHO:\n"
     "                break\n        return None\n\n    # ── нажатие"),
    ("голосовое без паузы", "wa_kind.py",
     'ECHO_NO_PAUSE_TYPES = frozenset(("image", "video", "document"))',
     'ECHO_NO_PAUSE_TYPES = frozenset(("image", "video", "document", "audio", "voice"))'),
    ("стикер без паузы", "wa_kind.py",
     'ECHO_NO_PAUSE_TYPES = frozenset(("image", "video", "document"))',
     'ECHO_NO_PAUSE_TYPES = frozenset(("image", "video", "document", "sticker"))'),
    ("текст без паузы", "wa_kind.py",
     "    return _type(msg_type) not in ECHO_NO_PAUSE_TYPES", "    return False"),
    ("видео ставит паузу", "wa_kind.py",
     'ECHO_NO_PAUSE_TYPES = frozenset(("image", "video", "document"))',
     'ECHO_NO_PAUSE_TYPES = frozenset(("image", "document"))'),
    ("документ ставит паузу", "wa_kind.py",
     'ECHO_NO_PAUSE_TYPES = frozenset(("image", "video", "document"))',
     'ECHO_NO_PAUSE_TYPES = frozenset(("image", "video"))'),
    ("фото снимает прежнюю паузу", "wa_agent.py",
     "        if pause:\n            self._pause(number, rid, now)\n",
     "        if pause:\n            self._pause(number, rid, now)\n        else:\n"
     "            self.db.execute(\"UPDATE clients SET paused=0 WHERE number=?\", (number,))\n"),
    ("фото не снимает ждущий черновик", "wa_agent.py",
     "        self._client(number)\n        self._bump(number)\n        # человек ответил",
     "        if not pause:\n            return\n        self._client(number)\n        self._bump(number)\n"
     "        # человек ответил"),
    ("фото не закрывает прежние входящие", "wa_agent.py",
     "        # человек ответил на всё, что было до его эха: эти входящие закрыты\n        self.db.execute(",
     "        # человек ответил на всё, что было до его эха: эти входящие закрыты\n        if pause: self.db.execute("),
    ("эхо нашей API-отправки ставит паузу", "wa_agent.py",
     "                elif not self._our_wamid(wamid):\n", "                elif True:\n"),
    ("фото в истории модели — клиент", "wa_history.py",
     '    if kind == wa_kind.KIND_ECHO:\n        return "мы"\n',
     '    if kind == wa_kind.KIND_ECHO:\n'
     '        return "клиент" if (row["msg_type"] or "") in ("image", "video", "document") else "мы"\n'),
    ("журнал: фото без слов «паузы нет»", "wa_agent.py",
     '"вид %s, паузы нет (WAPAUSEMEDIA0410)"', '"пауза%.0s"'),
]


def mutate(i):
    _name, fname, old, new = MUTANTS[i]
    src = os.environ.get("WA_AGENT_SRC") or ROOT
    d = tempfile.mkdtemp(prefix="wa_pause_media_mut%d_" % (i + 1))
    for f in ("wa_agent.py", "wa_kind.py", "wa_history.py"):
        shutil.copy(os.path.join(src, f), os.path.join(d, f))
    path = os.path.join(d, fname)
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    n = text.count(old)
    if n != 1:
        return d, "правка не легла (%d совпадений)" % n
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text.replace(old, new))
    return d, ""


if __name__ == "__main__":
    if os.environ.get("WA_PAUSE_MEDIA_CHILD"):
        print("FAILED " + ",".join(run_cases(quiet=True)))
        sys.exit(0)
    failed = run_cases()
    print("случаи: %d/%d" % (len(CASES) - len(failed), len(CASES)))
    caught = 0
    for i, (name, *_rest) in enumerate(MUTANTS):
        d, bad = mutate(i)
        if bad:
            print("мутант %d «%s»: %s" % (i + 1, name, bad))
            continue
        env = dict(os.environ, WA_AGENT_SRC=d, WA_PAUSE_MEDIA_CHILD="1", PYTHONDONTWRITEBYTECODE="1")
        p = subprocess.run([sys.executable, "-B", os.path.abspath(__file__)], env=env, capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=600)
        got = [x for x in (p.stdout or "").splitlines() if x.startswith("FAILED ")]
        fell = [x for x in got[-1][7:].split(",") if x] if got else ["<нет итога: %s>" % (p.stderr or "")[-200:]]
        caught += bool(fell)
        print("мутант %d «%s»: упало %d из %d — %s" % (i + 1, name, len(fell), len(CASES), ", ".join(fell)))
    print("мутантов %d — поймано %d" % (len(MUTANTS), caught))
    sys.exit(0 if not failed and caught == len(MUTANTS) else 1)
