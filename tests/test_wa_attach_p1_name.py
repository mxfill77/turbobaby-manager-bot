#!/usr/bin/env python3
"""П1 (13.10.2026) на всём пути «Отправить» службы с PDF-частью: текст и документ идут НАСТОЯЩИМ `wa_send`
(`send_text` → `_post`, `send_media` → `_post_media` → `multipart`) до ловца на месте `_open` — сети нет.
Имя договора — форма дела R13 (35 знаков, не ASCII), берётся из факта `contract_pdf` сверки, как живьём.

Проверяется: (1) успех — порядок «текст → загрузка → документ», в загрузке ASCII-имя, клиенту — исходное имя,
тело текста посимвольно прежнее; (2) отказ 360dialog при загрузке — текст УЖЕ ушёл (sent), PDF-часть not_sent с
причиной, документа в /messages нет, на карточке «Дослать PDF»; (3) молчание транспорта при загрузке — то же.

WA_AGENT_SRC=<каталог> подменяет модули (прогон мутантов)."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

import test_wa_attach_svc as AS  # noqa: E402
import test_wa_send_upload_name as U  # noqa: E402
import wa_agent as A  # noqa: E402
import wa_send as W  # noqa: E402

NAME = U.NAME_R13
ENV = {"WA_SEND": "1", "WA_360_API_KEY": U.KEY}
_ORIG_TOOLS = AS.tools_out


def _tools_r13():
    out = _ORIG_TOOLS()
    for r in out["results"]:
        if r["tool"] == "contract_pdf":
            for f in r["facts"]:
                f["name"] = NAME
    return out


class PW(AS.World):
    """Мир службы, где обе двери — настоящий `wa_send` до ловца `_open` (U.Net)."""

    def __init__(self, *a, net=None, **kw):
        self.net = net
        AS.World.__init__(self, *a, **kw)

    def send(self, to, text, db_path=None):
        self.sends.append((to, text))
        with U.Wire(self.net):
            return W.send_text(to, text, now=AS.T0 + 150, db_path=db_path, env=ENV, sleep=lambda s: None)

    def send_media(self, to, media, db_path=None):
        self.media.append((to, media["kind"], media["mime"], media["filename"], None))
        with U.Wire(self.net):
            return W.send_media(to, media, now=AS.T0 + 150, db_path=db_path, env=ENV, sleep=lambda s: None)


def _run(net):
    AS.tools_out = _tools_r13
    try:
        w = PW(AS.ON, net=net)
        w.ready()
        w.press("wa:send:1:1")
        return w
    finally:
        AS.tools_out = _ORIG_TOOLS


def _paths(net):
    return [r.full_url[len(W.API_BASE):] for r in net.reqs]


def test_r13_chain_ok_ascii_upload_original_name_for_client():
    net = U.Net(send=[(200, '{"messages":[{"id":"wamid.T1"}]}', None),
                      (200, '{"messages":[{"id":"wamid.P1"}]}', None)])
    w = _run(net)
    assert _paths(net) == [W.SEND_PATH, W.MEDIA_PATH, W.SEND_PATH], _paths(net)       # текст → загрузка → документ
    assert w.media and w.media[-1][3] == NAME, w.media                                 # дверь получила исходное имя
    assert w.q("SELECT state, wamid FROM drafts WHERE id=1") == [(A.SENT, "wamid.T1")], w.q("SELECT * FROM drafts")
    assert w.part()[:3] == (A.SENT, 1, "wamid.P1"), w.part()
    text_req, up, doc = net.reqs
    tb = json.loads(text_req.data.decode("utf-8"))
    assert tb["type"] == "text" and text_req.data == json.dumps(W.build_payload(AS.NUM, tb["text"]["body"]),
                                                                ensure_ascii=False).encode("utf-8"), text_req.data
    fname, ctype, data, head, _tail = U._split(up)
    assert fname == b"25-09-2026.pdf" and ctype == b"application/pdf" and data == AS.PDF, (fname, ctype)
    head.decode("ascii")
    db = json.loads(doc.data.decode("utf-8"))
    assert db["type"] == "document" and db["document"] == {"id": "MEDIA-R13", "filename": NAME}, db


def test_r13_chain_upload_refused_text_sent_pdf_not_sent():
    net = U.Net(media=(400, '{"error":{"message":"(#100) Invalid parameter"}}', None),
                send=(200, '{"messages":[{"id":"wamid.T1"}]}', None))
    w = _run(net)
    assert _paths(net) == [W.SEND_PATH, W.MEDIA_PATH], _paths(net)                    # документа в /messages нет
    assert w.q("SELECT state, wamid FROM drafts WHERE id=1") == [(A.SENT, "wamid.T1")]
    st, att, wamid, reason = w.part()
    assert (st, att, wamid) == (A.NOT_SENT, 1, None) and "файл в 360dialog не загружен" in (reason or ""), w.part()
    assert "wa:pdf:1:1" in AS.kb_data(w.edits()[-1]), AS.kb_data(w.edits()[-1])          # «Дослать PDF» на карточке


def test_r13_chain_upload_silence_text_sent_pdf_not_sent():
    net = U.Net(media=(None, "", "URLError"), send=(200, '{"messages":[{"id":"wamid.T1"}]}', None))
    w = _run(net)
    assert _paths(net) == [W.SEND_PATH] + [W.MEDIA_PATH] * W.MAX_ATTEMPTS, _paths(net)
    assert w.q("SELECT state FROM drafts WHERE id=1") == [(A.SENT,)]
    assert w.part()[:3] == (A.NOT_SENT, 1, None) and "транспорт молчит" in (w.part()[3] or ""), w.part()


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
