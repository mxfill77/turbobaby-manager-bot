#!/usr/bin/env python3
"""Медиа из темы клиента → WhatsApp (WARELAYMEDIA0210): фото, видео, документ, голосовое, аудио, стикер и
место из темы форума показа уходят клиенту своим видом. Файл берётся из Telegram (getFile + скачивание
в память), грузится в 360dialog (POST /media) и уходит сообщением вида (POST /messages) — настоящей дверью
`wa_send.send_media` на поддельных швах загрузки и отправки. Bot API — подделка, очередь, база показа и
база агента — временные (World из test_wa_agent_svc). Сети нет.

WA_AGENT_SRC=<каталог> подменяет модули (прогон мутантов)."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_wa_relay as R  # noqa: E402  (кладёт ROOT и WA_AGENT_SRC в путь)
import test_wa_agent_svc as SV  # noqa: E402

import wa_agent as A  # noqa: E402
import wa_agent_svc as S  # noqa: E402
import wa_agent_tg as G  # noqa: E402
import wa_history as H  # noqa: E402
import wa_send as W  # noqa: E402

NUM, T0, ON = SV.NUM, SV.T0, R.ON
MB = 1024 * 1024
CAP = "Ваш байк у отеля"
KEY = "k-test-1234"


class MHttp(SV.FakeHttp):
    """Bot API + файлы: getFile → file_path, GET /file/bot<ключ>/<путь> → байты из `files`."""

    def __init__(self, clock):
        super().__init__(clock)
        self.files, self.gets = {}, []

    def __call__(self, method, url, headers=None, data=None, timeout=30):
        if method == "GET" and "/file/bot" in url:
            path = url.split("/file/bot", 1)[1].split("/", 1)[1]
            self.gets.append(path)
            fid = path.rsplit("/", 1)[-1]
            return (200, self.files[fid]) if fid in self.files else (404, b"")
        if url.rsplit("/", 1)[-1] == "getFile":
            params = json.loads(data.decode("utf-8"))
            self.calls.append(("getFile", params))
            fid = params["file_id"]
            if fid not in self.files:
                return 400, json.dumps({"ok": False, "description": "Bad Request: file not found"}).encode()
            res = {"file_id": fid, "file_path": "media/" + fid}
            if not fid.startswith("NOSIZE"):                     # NOSIZE* — getFile размера не назвал
                res["file_size"] = len(self.files[fid])
            return 200, json.dumps({"ok": True, "result": res}).encode()
        return super().__call__(method, url, headers, data, timeout)


class MW(R.RW):
    """World + НАСТОЯЩАЯ дверь `wa_send.send_media` (ручка, проверка, ключ, окно, загрузка, отправка) на
    поддельных швах `upload` и `transport`. Входящее клиента `inbound_age` с назад — окно 24 ч."""

    def __init__(self, environ, inbound_age=200, post_res=None, up_res=None, **kw):
        self.uploads, self.posts = [], []
        self.post_res, self.up_res = post_res, up_res
        super().__init__(environ, **kw)
        if inbound_age is not None:
            self.put(T0 - inbound_age)

    def build(self, environ):
        if not isinstance(getattr(self, "http", None), MHttp):
            self.http = MHttp(self.clock)
        self.environ = dict(environ)
        self.core, self.tg, self.flags, self.words = S.build(
            self.env, environ=self.environ, model=self.model, http=self.http, send=self.send,
            react_send=self.react_send, clock=self.clock, line=self.lines.append, send_media=self.send_media)
        return self

    def send_media(self, to, media, db_path=None):
        return W.send_media(to, media, now=self.clock.t, db_path=db_path,
                            env={"WA_SEND": "1", "WA_360_API_KEY": KEY},
                            transport=self.post, upload=self.upload, sleep=lambda s: None)

    def upload(self, url, fields, file, key, timeout):
        self.uploads.append({"url": url, "fields": dict(fields), "file": file, "key": key})
        if self.up_res:
            return self.up_res
        return 200, json.dumps({"id": "MEDIA%d" % len(self.uploads)}), None

    def post(self, url, payload, key, timeout):
        self.posts.append(payload)
        if self.post_res:
            return self.post_res
        return 200, json.dumps({"messages": [{"id": "wamid.M%d" % len(self.posts)}]}), None

    def file(self, fid, data):
        self.http.files[fid] = data
        return {"file_id": fid, "file_unique_id": "u" + fid, "file_size": len(data)}

    def replies(self):
        return [m["text"] for m in self.show_msgs()]

    def reactions(self):
        return [p["message_id"] for p in self.http.of("setMessageReaction")]


JPEG = b"\xff\xd8\xff" + b"j" * 2000
OGG = b"OggS" + b"o" * 3000


# ═══ позитивы ════════════════════════════════════════════════════════════════════════════

def test_photo_caption_one_upload_one_send():
    w = MW(ON)
    small = w.file("PH1", b"\xff\xd8" + b"s" * 100)
    big = w.file("PH2", JPEG)
    w.http.updates = [[w.topic(text=None, photo=[small, big], caption=CAP)]]
    w.serve(10)
    assert len(w.uploads) == 1, w.uploads                                   # одна загрузка
    up = w.uploads[0]
    assert up["url"] == W.API_BASE + "/media" and up["key"] == KEY, up
    assert up["fields"] == {"messaging_product": "whatsapp", "type": "image/jpeg"}, up["fields"]
    assert up["file"][1] == JPEG and up["file"][2] == "image/jpeg", up["file"][2]   # самый большой размер
    assert w.posts == [{"messaging_product": "whatsapp", "recipient_type": "individual", "to": NUM,
                        "type": "image", "image": {"id": "MEDIA1", "caption": CAP}}], w.posts   # одна отправка
    assert w.http.of("getFile") == [{"file_id": "PH2"}], w.http.of("getFile")
    assert w.reactions() == [700] and w.replies() == [], (w.reactions(), w.replies())
    st = w.core.db.execute("SELECT state, wamid FROM relay WHERE msg_id=700").fetchone()
    assert st == (A.SENT, "wamid.M1"), st
    assert w.paused(), "человек прислал фото — агент не на паузе"


def test_voice_goes_as_audio():
    w = MW(ON)
    v = dict(w.file("V1", OGG), duration=3, mime_type="audio/ogg")
    w.http.updates = [[w.topic(text=None, voice=v)]]
    w.serve(10)
    assert [u["fields"]["type"] for u in w.uploads] == ["audio/ogg"], w.uploads
    assert w.uploads[0]["file"][1] == OGG, "в 360dialog ушли не байты голосового"
    assert [(p["type"], p.get("audio")) for p in w.posts] == [("audio", {"id": "MEDIA1"})], w.posts
    assert w.reactions() == [700] and w.replies() == [], w.replies()


def test_location_goes_as_location():
    w = MW(ON)
    w.http.updates = [[w.topic(text=None, location={"latitude": 7.7712, "longitude": 98.3254}),
                       w.topic(text=None, mid=701, location={"latitude": 7.8, "longitude": 98.3},
                               venue={"location": {"latitude": 7.8, "longitude": 98.3}, "title": "Офис",
                                      "address": "Раваи"})]]
    w.serve(10)
    assert w.uploads == [] and w.http.of("getFile") == [], w.uploads                # файла у места нет
    assert [p["type"] for p in w.posts] == ["location", "location"], w.posts
    assert w.posts[0]["location"] == {"latitude": 7.7712, "longitude": 98.3254}, w.posts[0]
    assert w.posts[1]["location"] == {"latitude": 7.8, "longitude": 98.3, "name": "Офис",
                                      "address": "Раваи"}, w.posts[1]
    assert w.reactions() == [700, 701], w.reactions()


def test_document_video_sticker_own_kind():
    w = MW(ON)
    doc = dict(w.file("D1", b"%PDF" + b"d" * 500), mime_type="application/pdf", file_name="договор.pdf")
    vid = dict(w.file("VD1", b"\x00\x00mp4" + b"v" * 800), mime_type="video/mp4")
    stk = dict(w.file("ST1", b"RIFFwebp" + b"w" * 300), is_animated=False, is_video=False)
    w.http.updates = [[w.topic(text=None, document=doc, caption="договор"),
                       w.topic(text=None, mid=701, video=vid, caption="видео"),
                       w.topic(text=None, mid=702, sticker=stk)]]
    w.serve(10)
    assert [u["fields"]["type"] for u in w.uploads] == ["application/pdf", "video/mp4", "image/webp"], w.uploads
    assert w.posts[0]["document"] == {"id": "MEDIA1", "caption": "договор", "filename": "договор.pdf"}, w.posts[0]
    assert w.posts[1]["video"] == {"id": "MEDIA2", "caption": "видео"}, w.posts[1]
    assert w.posts[2]["type"] == "sticker" and w.posts[2]["sticker"] == {"id": "MEDIA3"}, w.posts[2]


def test_album_each_file_caption_first():
    w = MW(ON)
    items = [w.file("AL%d" % i, JPEG + bytes([i])) for i in range(3)]
    w.http.updates = [[w.topic(text=None, mid=700 + i, media_group_id="G1", photo=[items[i]],
                               **({"caption": CAP} if i == 0 else {})) for i in range(3)]]
    w.serve(10)
    assert [u["file"][1] for u in w.uploads] == [JPEG + bytes([i]) for i in range(3)], len(w.uploads)
    assert [p["image"].get("caption") for p in w.posts] == [CAP, None, None], w.posts   # каждый — своим
    assert w.reactions() == [700, 701, 702], w.reactions()


def test_sent_in_history_kind_and_caption():
    w = MW(ON)
    ph = w.file("PH1", JPEG)
    v = dict(w.file("V1", OGG), mime_type="audio/ogg")
    w.http.updates = [[w.topic(text=None, photo=[ph], caption=CAP), w.topic(text=None, mid=701, voice=v),
                       w.topic(text=None, mid=702, location={"latitude": 7.77, "longitude": 98.32})]]
    w.serve(10)
    items, _ = H.read_history(NUM, w.env["queue_db"], None, sent_db=w.env["agent_db"])
    ours = [(it["key"], it["word"], it["text"]) for it in items if it["who"] == "мы"]
    assert ours == [("wamid.M1", "фото", CAP), ("wamid.M2", "голосовое", ""),
                    ("wamid.M3", "геоточка", "7.77, 98.32")], ours
    view, _n = H.model_view(items)
    assert "мы: [фото] " + CAP in view and "мы: [голосовое]" in view, view


def test_audio_caption_dropped_says_so():
    w = MW(ON)
    v = dict(w.file("V1", OGG), mime_type="audio/ogg")
    w.http.updates = [[w.topic(text=None, voice=v, caption="подпись к голосу")]]
    w.serve(10)
    assert w.posts[0]["audio"] == {"id": "MEDIA1"}, w.posts                         # подписи у аудио нет
    assert w.reactions() == [700] and w.replies() == [G.RELAY_NO_CAPTION % "голосового"], w.replies()


# ═══ негативы ════════════════════════════════════════════════════════════════════════════

def test_over_limit_reply_no_send():
    w = MW(ON)
    vid = {"file_id": "BIG", "file_unique_id": "uBIG", "file_size": 17 * MB, "mime_type": "video/mp4"}
    doc = {"file_id": "BIGD", "file_unique_id": "uBIGD", "file_size": 25 * MB, "mime_type": "application/pdf"}
    w.http.updates = [[w.topic(text=None, video=vid), w.topic(text=None, mid=701, document=doc)]]
    w.serve(10)
    assert w.http.of("getFile") == [] and w.uploads == [] and w.posts == [], w.http.calls   # наружу ничего
    assert w.replies() == [A.W_TOPIC % "файл 17 МБ больше предела 16 МБ (видео в WhatsApp)",
                           A.W_TOPIC % "файл 25 МБ больше предела 20 МБ (Telegram отдаёт боту файл до 20 МБ)"], \
        w.replies()
    assert w.reactions() == [], w.reactions()


def test_over_limit_known_only_after_telegram():
    # размера в сообщении нет: getFile назвал 21 МБ — не качаем; не назвал и тоже нет — меряем байты
    w = MW(ON)
    w.http.files["BIGF"] = b"d" * (21 * MB)
    w.http.files["NOSIZE1"] = b"\xff\xd8" + b"p" * (6 * MB)
    w.http.updates = [[w.topic(text=None, document={"file_id": "BIGF", "mime_type": "application/pdf"}),
                       w.topic(text=None, mid=701, photo=[{"file_id": "NOSIZE1"}])]]
    w.serve(10)
    assert w.http.gets == ["media/NOSIZE1"], w.http.gets                            # 21 МБ не скачивали
    assert w.uploads == [] and w.posts == [], len(w.uploads)
    assert w.replies() == [A.W_TOPIC % "файл из Telegram не получен (файл 21 МБ больше предела 20 МБ)",
                           A.W_TOPIC % "файл 6 МБ больше предела 5 МБ (фото в WhatsApp)"], w.replies()


def test_repeat_update_one_send():
    w = MW(ON)
    ph = w.file("PH1", JPEG)
    upd = w.topic(text=None, photo=[ph], caption=CAP)
    w.http.updates = [[upd, upd], [upd], [w.topic(text=None, photo=[ph], caption=CAP)]]
    w.serve(30)
    assert len(w.uploads) == 1 and len(w.posts) == 1, (len(w.uploads), len(w.posts))
    assert w.reactions() == [700], w.reactions()


def test_window_closed_reason_no_fetch():
    w = MW(ON, inbound_age=30 * 3600)
    ph = w.file("PH1", JPEG)
    w.http.updates = [[w.topic(text=None, photo=[ph], caption=CAP)]]
    w.serve(10)
    assert w.http.of("getFile") == [] and w.uploads == [] and w.posts == [], w.http.calls
    assert w.replies() == [A.W_CLOSED], w.replies()
    assert w.paused()


def test_no_pair_kinds_words():
    w = MW(ON)
    w.http.updates = [[w.topic(text=None, contact={"phone_number": "000", "first_name": "x"}),
                       w.topic(text=None, mid=701, sticker={"file_id": "S", "is_animated": True}),
                       w.topic(text=None, mid=702, location={"latitude": 7.7, "longitude": 98.3,
                                                             "live_period": 900}),
                       w.topic(text=None, mid=703, poll={"id": "p", "question": "?"})],
                      [w.topic(text=None, mid=702, edited=True, location={"latitude": 7.71, "longitude": 98.3,
                                                                           "live_period": 900})]]
    w.serve(10)
    assert w.uploads == [] and w.posts == [], w.posts
    assert w.replies() == [G.RELAY_NO_PAIR % x for x in ("контакт", "анимированный стикер", "живая геоточка",
                                                          "опрос")], w.replies()   # движение геоточки — молча


def test_upload_refused_not_sent_no_message():
    w = MW(ON, up_res=(400, json.dumps({"error": {"message": "bad media"}}), None))
    w.http.updates = [[w.topic(text=None, photo=[w.file("PH1", JPEG)])]]
    w.serve(10)
    assert len(w.uploads) == 1 and w.posts == [], (w.uploads, w.posts)              # отказ не повторяем
    assert w.replies() == [A.W_DOOR_ERR % "файл в 360dialog не загружен: сервер отказал 400: bad media — не отправлено"], \
        w.replies()
    w2 = MW(ON, up_res=(None, "", "URLError"))
    w2.http.updates = [[w2.topic(text=None, photo=[w2.file("PH1", JPEG)])]]
    w2.serve(10)
    assert len(w2.uploads) == W.MAX_ATTEMPTS and w2.posts == [], len(w2.uploads)   # молчание — повтор загрузки
    assert w2.core.db.execute("SELECT state FROM relay WHERE msg_id=700").fetchone() == (A.NOT_SENT,)


def test_send_unknown_after_upload_no_repeat():
    w = MW(ON, post_res=(200, "{}", None))                                         # без id сообщения
    ph = w.file("PH1", JPEG)
    w.http.updates = [[w.topic(text=None, photo=[ph])], [w.topic(text=None, photo=[ph])]]
    w.serve(20)
    assert len(w.posts) == 1, w.posts
    assert w.replies() == [A.W_UNSURE], w.replies()


def test_fetch_failed_words_no_upload():
    w = MW(ON)
    w.http.updates = [[w.topic(text=None, photo=[{"file_id": "GONE", "file_size": 10}])]]
    w.serve(10)
    assert w.uploads == [] and w.posts == [], w.uploads
    assert w.replies() == [A.W_TOPIC % "файл из Telegram не получен (getFile не удался (400))"], w.replies()


def test_door_checks_before_network():
    ok = {"kind": "document", "mime": "application/pdf", "size": 10, "caption": ""}
    assert W.media_check(ok) == ""
    assert "application/zip" in W.media_check(dict(ok, mime="application/zip"))
    assert "1024" in W.media_check(dict(ok, caption="x" * 1025))
    assert W.media_check(dict(ok, kind="audio", mime="audio/ogg", caption="x" * 1025)) == ""   # подпись не уйдёт
    assert W.media_check({"kind": "location", "latitude": 95, "longitude": 1})
    calls = []
    res = W.send_media(NUM, dict(ok, fetch=lambda cap: calls.append(cap) or (b"x", "")),
                       env={"WA_SEND": "0", "WA_360_API_KEY": KEY},
                       transport=lambda *a: calls.append(a), upload=lambda *a: calls.append(a))
    assert res["outcome"] == W.NOT_SENT and calls == [], (res, calls)                   # ручка выключена
    off = W.send_media(NUM, dict(ok, mime="application/zip"), env={"WA_SEND": "0", "WA_360_API_KEY": KEY})
    assert "WA_SEND" in off["reason"] and "topic_words" not in off, off   # выключенная дверь файл не судит
    body, ctype = W.multipart([("messaging_product", "whatsapp"), ("type", "audio/ogg")], "v.ogg", OGG, "audio/ogg")
    bnd = ctype.split("boundary=", 1)[1]
    assert ctype.startswith("multipart/form-data; boundary=") and body.endswith(("--%s--\r\n" % bnd).encode())
    assert b'name="messaging_product"\r\n\r\nwhatsapp' in body and b"Content-Type: audio/ogg\r\n\r\n" + OGG in body


def test_journal_no_caption_number_or_token():
    w = MW(ON)
    w.http.updates = [[w.topic(text=None, photo=[w.file("PH1", JPEG)], caption=CAP)]]
    w.serve(400)
    log = "\n".join(w.lines)
    assert CAP not in log and NUM not in log and SV.TOKEN not in log, log
    assert any("тема: сообщение 700 (image) → sent" in ln for ln in w.lines), w.lines


if __name__ == "__main__":
    fails = 0
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        try:
            fn()
            print("PASS", name)
        except Exception as e:                                           # noqa: BLE001
            fails += 1
            print("FAIL", name, type(e).__name__, str(e)[:300])
    print("%d/%d" % (len(tests) - fails, len(tests)))
    sys.exit(1 if fails else 0)
