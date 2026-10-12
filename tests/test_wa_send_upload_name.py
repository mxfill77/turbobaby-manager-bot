#!/usr/bin/env python3
"""П1 (13.10.2026): имя файла в multipart ЗАГРУЗКИ 360dialog — только печатный ASCII; клиент видит ИСХОДНОЕ имя.

Сквозь настоящие `wa_send.send_media` → `_post_media` → `multipart` и `send_text`/`send_reaction` → `_post` до
САМОГО выхода в сеть `_open`, который подменён ловцом запросов; `urllib.request.urlopen` подменён ловушкой (сети нет).
Голдены — на форме дела R13 (имя PDF 35 знаков, не ASCII), отрицательные — отказ 360dialog, молчание транспорта,
ответ без id, CR/LF и кавычка в имени; ASCII-имя — байт-в-байт прежняя формула; текстовая часть и реакция — тело
запроса посимвольно прежней формы (литеральный голден).

WA_AGENT_SRC=<каталог> подменяет модули (прогон мутантов)."""
import json
import os
import re
import sqlite3
import sys
import tempfile
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
if os.environ.get("WA_AGENT_SRC"):
    sys.path.insert(0, os.environ["WA_AGENT_SRC"])
os.environ["PRETOOL_NOPUSH"] = "1"

import wa_send as W  # noqa: E402

NUM = "66812345678"
NOW = 1_790_000_000.0
KEY = "k-test-p1-0001"                                    # тестовое значение, не ключ
ENV = {"WA_SEND": "1", "WA_360_API_KEY": KEY}
PDF_MIME = "application/pdf"
# байты с CR/LF, кавычкой и всеми октетами: тело файла обязано доехать ровно, заголовки — отделиться
PDF = b"%PDF-1.4\r\n" + bytes(range(256)) * 3 + b'"\r\n--wa\r\n%%EOF\n'
NAME_R13 = "Договор аренды байка 25-09-2026.pdf"         # форма дела R13: 35 знаков, не ASCII, кириллица
NAME_CYR = "Договор_аренды_мотоцикла_клиент.pdf"         # 35 знаков, основа целиком кириллицей
MEDIA_OK = (200, '{"id":"MEDIA-R13"}', None)
SEND_OK = (200, '{"messages":[{"id":"wamid.R13"}]}', None)
FILE_HEAD = re.compile(rb'--(wa[0-9a-f]{24})\r\nContent-Disposition: form-data; name="file"; '
                       rb'filename="([^"\r\n]*)"\r\nContent-Type: ([^\r\n]*)\r\n\r\n')


def _queue():
    d = tempfile.mkdtemp(prefix="wa_p1name_t_")
    path = os.path.join(d, "q.db")
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE wa_inbox (id INTEGER PRIMARY KEY AUTOINCREMENT, ts_queued INTEGER, channel TEXT, "
                "from_number TEXT, name TEXT, msg_type TEXT, text TEXT, media_id TEXT, ts_msg INTEGER, "
                "echo INTEGER DEFAULT 0, history INTEGER DEFAULT 0, status TEXT, raw TEXT, wamid TEXT)")
    con.execute("INSERT INTO wa_inbox(ts_queued, from_number, msg_type, ts_msg, echo) VALUES(?,?,?,?,0)",
                (int(NOW - 600), NUM, "text", int(NOW - 600)))
    con.commit()
    con.close()
    return path


QDB = _queue()


class Net:
    """Ловец запросов на месте `wa_send._open`: отвечает по пути; `media`/`send` — ответ либо список ответов."""

    def __init__(self, media=MEDIA_OK, send=SEND_OK):
        self.media, self.send, self.reqs = media, send, []

    @staticmethod
    def _pick(ans, n):
        return ans[min(n, len(ans) - 1)] if isinstance(ans, list) else ans

    def __call__(self, req, timeout):
        self.reqs.append(req)
        path = req.full_url[len(W.API_BASE):]
        if path == W.MEDIA_PATH:
            return self._pick(self.media, sum(1 for r in self.reqs if r.full_url.endswith(W.MEDIA_PATH)) - 1)
        if path == W.SEND_PATH:
            return self._pick(self.send, sum(1 for r in self.reqs if r.full_url.endswith(W.SEND_PATH)) - 1)
        raise AssertionError("неожиданный адрес " + req.full_url)

    def of(self, path):
        return [r for r in self.reqs if r.full_url == W.API_BASE + path]


class Wire:
    """Подмена выхода в сеть на время прогона: `_open` — ловец, `urlopen` — ловушка."""

    def __init__(self, net):
        self.net = net

    def __enter__(self):
        self._open, self._urlopen = W._open, urllib.request.urlopen
        W._open = self.net

        def trap(*a, **kw):
            raise AssertionError("к сети обратились мимо ловца")
        urllib.request.urlopen = trap
        return self.net

    def __exit__(self, *a):
        W._open, urllib.request.urlopen = self._open, self._urlopen


def _doc(name, net):
    media = {"kind": "document", "mime": PDF_MIME, "size": len(PDF), "filename": name, "caption": "",
             "fetch": lambda cap: (PDF, "")}
    with Wire(net):
        return W.send_media(NUM, media, now=NOW, db_path=QDB, env=ENV, sleep=lambda s: None)


def _split(req):
    """Тело multipart → (имя в заголовке части, тип части, байты файла, заголовки до файла, хвост после файла)."""
    body = req.data
    m = FILE_HEAD.search(body)
    assert m, body[:300]
    bnd = m.group(1)
    tail = b"\r\n--" + bnd + b"--\r\n"
    assert body.endswith(tail), body[-60:]
    assert req.get_header("Content-type") == "multipart/form-data; boundary=" + bnd.decode("ascii"), \
        req.get_header("Content-type")
    return m.group(2), m.group(3), body[m.end():len(body) - len(tail)], body[:m.end()], tail


# ═══ (1) дословная форма R13: загрузка ASCII, клиенту — исходное имя ═══════════════════════════

def test_r13_names_are_35_non_ascii():
    for name in (NAME_R13, NAME_CYR):
        assert len(name) == 35 and not name.isascii() and re.search("[А-Яа-яЁё]", name), name


def test_r13_upload_ascii_client_sees_original():
    net = Net()
    res = _doc(NAME_R13, net)
    assert res["outcome"] == W.SENT and res["wamid"] == "wamid.R13" and res["uploads"] == 1, res
    assert [r.full_url[len(W.API_BASE):] for r in net.reqs] == [W.MEDIA_PATH, W.SEND_PATH], net.reqs
    up = net.of(W.MEDIA_PATH)[0]
    assert up.get_method() == "POST" and up.get_header("D360-api-key") == KEY, up.header_items()
    fname, ctype, data, head, tail = _split(up)
    assert fname == b"25-09-2026.pdf", fname                                  # голден ASCII-имени R13
    assert ctype == PDF_MIME.encode() and data == PDF, (ctype, len(data))      # тип и байты файла — ровно
    head.decode("ascii")                                                       # заголовки частей — чистый ASCII
    tail.decode("ascii")
    assert b"filename*" not in up.data and re.search(rb"[\x80-\xff]", head) is None, head
    assert b'name="messaging_product"\r\n\r\nwhatsapp\r\n' in head and \
        b'name="type"\r\n\r\napplication/pdf\r\n' in head, head
    msg = net.of(W.SEND_PATH)[0]
    assert msg.get_header("Content-type") == "application/json", msg.header_items()
    body = json.loads(msg.data.decode("utf-8"))
    assert body == {"messaging_product": "whatsapp", "recipient_type": "individual", "to": NUM,
                    "type": "document", "document": {"id": "MEDIA-R13", "filename": NAME_R13}}, body
    assert ('"filename": "%s"' % NAME_R13).encode("utf-8") in msg.data, msg.data    # сырой UTF-8, без \\u-экранов


def test_fully_cyrillic_stem_uploads_as_file_pdf():
    net = Net()
    res = _doc(NAME_CYR, net)
    assert res["outcome"] == W.SENT, res
    fname, _ctype, data, head, _tail = _split(net.of(W.MEDIA_PATH)[0])
    assert fname == b"file.pdf" and data == PDF, fname
    head.decode("ascii")
    assert json.loads(net.of(W.SEND_PATH)[0].data.decode("utf-8"))["document"]["filename"] == NAME_CYR


# ═══ (2) ASCII-имя — байт-в-байт прежняя формула (до 13.10: filename=fname.replace('"', "_")) ═══════

def _old_file_head(bnd, fname, mime):
    return ("--%s\r\nContent-Disposition: form-data; name=\"file\"; filename=\"%s\"\r\n"
            "Content-Type: %s\r\n\r\n" % (bnd, fname.replace('"', "_"), mime)).encode("utf-8")


def test_ascii_names_byte_for_byte():
    fields = [("messaging_product", "whatsapp"), ("type", PDF_MIME)]
    for name in ("contract_41.pdf", "contract.pdf", "v.ogg", 'a"b.pdf', "my contract (1).pdf", "file.pdf",
                 ".pdf", "x" * 200 + ".pdf", "", "~!@#$%^&*()_+=`{}[]|\\:;'<>,?.pdf"):
        body, ctype = W.multipart(fields, name, PDF, PDF_MIME)
        bnd = ctype.split("boundary=", 1)[1]
        want = b"".join([("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n" % (bnd, n, v))
                         .encode("utf-8") for n, v in fields]) + _old_file_head(bnd, name, PDF_MIME) + PDF + \
            ("\r\n--%s--\r\n" % bnd).encode("utf-8")
        assert body == want, name
        assert W.upload_name(name, PDF_MIME) == name.replace('"', "_"), name


# ═══ (3) правило ASCII-формы: таблица ═══════════════════════════════════════════════════════════

def test_upload_name_table():
    cases = [
        (NAME_R13, PDF_MIME, "25-09-2026.pdf"),
        (NAME_CYR, PDF_MIME, "file.pdf"),
        ("Договор.pdf", PDF_MIME, "file.pdf"),
        ("Договор.пдф", PDF_MIME, "file.pdf"),                       # расширение не ASCII → по типу
        ("Договор.PDF", PDF_MIME, "file.pdf"),
        ("Договор", "image/jpeg", "file.jpeg"),                      # расширения нет → по типу
        ("สัญญา 5849.PDF", PDF_MIME, "5849.pdf"),                    # тайский
        ("Договор ADV 350 5849 (подписан).pdf", PDF_MIME, "ADV_350_5849.pdf"),
        ("evil\r\nX-Injected: 1.pdf", PDF_MIME, "evil_X-Injected_1.pdf"),   # управляющие — не ASCII-печатные
        ("tab\there.pdf", PDF_MIME, "tab_here.pdf"),
        ('Дог"овор/2026\\x.pdf', PDF_MIME, "2026_x.pdf"),
        ("Отчёт.дoc", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "file.bin"),
        ("Фото.jpg", "image/jpeg; charset=binary", "file.jpg"),
        ("Договор", "", "file.bin"),
        ("Д" * 300 + " 5849.pdf", PDF_MIME, "5849.pdf"),
    ]
    for name, mime, want in cases:
        got = W.upload_name(name, mime)
        assert got == want, (name, mime, got, want)
    for name, mime, _w in cases + [("Ab" * 100 + "Д.pdf", PDF_MIME, None), ("​doc.pdf", PDF_MIME, None)]:
        got = W.upload_name(name, mime)
        assert got and all(" " <= c <= "~" for c in got), (name, got)
        assert '"' not in got and "\\" not in got and " " not in got, (name, got)
        stem, ext = got.rsplit(".", 1)
        assert 0 < len(stem) <= W.UPLOAD_STEM_MAX and 0 < len(ext) <= W.UPLOAD_EXT_MAX, (name, got)


def test_crlf_name_no_header_injection():
    body, ctype = W.multipart([("messaging_product", "whatsapp")], "evil\r\nX-Injected: 1.pdf", PDF, PDF_MIME)
    head = body[:body.index(b"Content-Type: application/pdf\r\n\r\n")]
    assert b"\r\nX-Injected" not in head and b'filename="evil_X-Injected_1.pdf"\r\n' in head, head
    head.decode("ascii")


# ═══ (4) отрицательные: провал загрузки — not_sent, сообщения нет вовсе ═══════════════════════════

def test_upload_refused_not_sent_no_message():
    net = Net(media=(400, '{"error":{"message":"(#100) Param file must be a file with one of the following types"}}',
                     None))
    res = _doc(NAME_R13, net)
    assert res["outcome"] == W.NOT_SENT and res["wamid"] is None and res["uploads"] == 1, res
    assert res["reason"].startswith("файл в 360dialog не загружен: сервер отказал 400: (#100)"), res["reason"]
    assert net.of(W.SEND_PATH) == [] and len(net.of(W.MEDIA_PATH)) == 1, net.reqs     # отказ не повторяется


def test_upload_silence_retries_then_not_sent():
    net = Net(media=(None, "", "URLError"))
    res = _doc(NAME_R13, net)
    assert res["outcome"] == W.NOT_SENT and res["uploads"] == W.MAX_ATTEMPTS, res
    assert "транспорт молчит" in res["reason"] and net.of(W.SEND_PATH) == [], (res, net.reqs)
    assert all(_split(r)[0] == b"25-09-2026.pdf" for r in net.of(W.MEDIA_PATH))   # каждый повтор — то же имя


def test_upload_2xx_without_id_not_sent():
    net = Net(media=(200, '{"messaging_product":"whatsapp"}', None))
    res = _doc(NAME_R13, net)
    assert res["outcome"] == W.NOT_SENT and "id медиа в ответе нет" in res["reason"], res
    assert net.of(W.SEND_PATH) == [], net.reqs


def test_upload_5xx_then_ok_sends_once():
    net = Net(media=[(503, '{"error":{"message":"busy"}}', None), MEDIA_OK])
    res = _doc(NAME_R13, net)
    assert res["outcome"] == W.SENT and res["uploads"] == 2 and len(net.of(W.SEND_PATH)) == 1, res


def test_messages_refused_after_upload():
    net = Net(send=(400, '{"error":{"message":"(#131053) Media upload error"}}', None))
    res = _doc(NAME_R13, net)
    assert res["outcome"] == W.NOT_SENT and "131053" in res["reason"] and len(net.of(W.SEND_PATH)) == 1, res


# ═══ (5) текст и реакция — тело запроса посимвольно прежней формы ═══════════════════════════════

TEXT = "Здравствуйте! Договор во вложении следующим сообщением."


def test_text_body_unchanged():
    net = Net(send=(200, '{"messages":[{"id":"wamid.T1"}]}', None))
    with Wire(net):
        res = W.send_text(NUM, TEXT, now=NOW, db_path=QDB, env=ENV, sleep=lambda s: None)
    assert res["outcome"] == W.SENT and res["wamid"] == "wamid.T1", res
    assert len(net.reqs) == 1 and net.of(W.MEDIA_PATH) == [], net.reqs
    req = net.reqs[0]
    want = ('{"messaging_product": "whatsapp", "recipient_type": "individual", "to": "66812345678", '
            '"type": "text", "text": {"preview_url": false, "body": "%s"}}' % TEXT).encode("utf-8")
    assert req.data == want, req.data
    assert req.get_header("Content-type") == "application/json" and req.get_header("D360-api-key") == KEY


def test_reaction_body_unchanged():
    net = Net(send=(200, '{"messages":[{"id":"wamid.X1"}]}', None))
    with Wire(net):
        res = W.send_reaction(NUM, "wamid.IN1", "👍", now=NOW, db_path=QDB, env=ENV, sleep=lambda s: None)
    assert res["outcome"] == W.SENT, res
    want = ('{"messaging_product": "whatsapp", "recipient_type": "individual", "to": "66812345678", '
            '"type": "reaction", "reaction": {"message_id": "wamid.IN1", "emoji": "👍"}}').encode("utf-8")
    assert net.reqs[0].data == want, net.reqs[0].data


def test_door_seams_unchanged():
    """Швы двери прежние: `upload` по-прежнему получает ИСХОДНОЕ имя (ASCII-форма живёт только в multipart)."""
    seen = []

    def upload(url, fields, file, key, timeout):
        seen.append(file[0])
        return MEDIA_OK

    def post(url, payload, key, timeout):
        return SEND_OK
    media = {"kind": "document", "mime": PDF_MIME, "size": len(PDF), "filename": NAME_R13, "caption": "",
             "fetch": lambda cap: (PDF, "")}
    res = W.send_media(NUM, media, now=NOW, db_path=QDB, env=ENV, transport=post, upload=upload,
                       sleep=lambda s: None)
    assert res["outcome"] == W.SENT and seen == [NAME_R13], (res, seen)


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
