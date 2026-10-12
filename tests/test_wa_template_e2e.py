#!/usr/bin/env python3
"""NIGHT0710-B3g, второй круг: сквозная проверка «флаг вкл» на НАСТОЯЩЕЙ сборке службы (`wa_agent_svc.build`), НАСТОЯЩЕЙ
пробе окна двери (`SendDoor.window` → `wa_send.last_inbound_ts`/`window_state` по очереди) и НАСТОЯЩИХ
`wa_send.send_template` / `send_text`. Перенесена строителем из пробы независимого проверяющего
(tpl_aux/review/probe_flagon.py, замечание З5: «сквозной связки очередь → окно → кнопка → ответ клиента → open в
наборах нет»), шаги и проверки — её; добавлены (10) строка ушедшего шаблона в теме клиента и (11) ответ с телефона.

Подделки — только Bot API, GET списка шаблонов и POST /messages (швы `get`/`transport`). Сети нет: urlopen — ловушка.
Формат набора дерева: каждая проверка — строка PASS/FAIL, в конце «ИТОГ ok/всего»."""
import json
import os
import sqlite3
import sys
import tempfile
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.environ["PRETOOL_NOPUSH"] = "1"
os.environ["PYTHON_DOTENV_DISABLED"] = "1"


def _no_net(*a, **kw):
    raise AssertionError("тест обратился к сети")


urllib.request.urlopen = _no_net

import wa_agent as A  # noqa: E402
import wa_agent_svc as SVC  # noqa: E402
import wa_send as S  # noqa: E402

QSCHEMA = """CREATE TABLE wa_inbox (id INTEGER PRIMARY KEY AUTOINCREMENT, ts_queued INTEGER NOT NULL,
 channel TEXT NOT NULL DEFAULT 'wa', from_number TEXT, name TEXT, msg_type TEXT, text TEXT, media_id TEXT,
 ts_msg INTEGER, echo INTEGER NOT NULL DEFAULT 0, history INTEGER NOT NULL DEFAULT 0,
 status TEXT NOT NULL DEFAULT 'new', raw TEXT, wamid TEXT)"""
NUM, NUM_EN, NUM_K, NUM_P = "66810000011", "66810000012", "66810000013", "66810000014"
SHOW = "-1004401325262"
HUMAN = {"id": 501, "is_bot": False, "first_name": "Дарья"}
NOW = float(int(time.time()))
RES = []


def check(cond, what, detail=""):
    RES.append((bool(cond), what, "" if cond else str(detail)[:400]))
    return cond


class FakeHttp:
    def __init__(self):
        self.calls, self.updates, self.mid = [], [], 100

    def __call__(self, method, url, headers=None, data=None, timeout=30):
        name = url.rsplit("/", 1)[-1]
        params = json.loads(data.decode("utf-8")) if data else {}
        self.calls.append((name, params))
        if name == "sendMessage":
            self.mid += 1
            return 200, json.dumps({"ok": True, "result": {"message_id": self.mid}}).encode()
        if name == "getUpdates":
            batch = self.updates.pop(0) if self.updates else []
            return 200, json.dumps({"ok": True, "result": batch}).encode()
        return 200, json.dumps({"ok": True, "result": True}).encode()

    def of(self, name):
        return [p for n, p in self.calls if n == name]


class Model(A.Model):
    def __init__(self):
        self.text = {NUM: "Здравствуйте! Байк свободен, приезжайте.",
                     NUM_EN: "Hello! The bike is available, come and pick it up.",
                     NUM_K: "Здравствуйте! Байк свободен.",
                     NUM_P: "Здравствуйте! Байк свободен, ждём."}

    def draft(self, number, upto_id):
        return self.text[number]


def listing(status, category="UTILITY"):
    items = [{"name": n, "language": lg, "status": status, "category": category, "rejected_reason": None,
              "id": "x%s%s" % (n, lg)} for n in sorted(S.TEMPLATE_PARAMS) for lg in ("ru", "en")]
    return json.dumps({"waba_templates": items, "count": len(items), "total": len(items)})


def buttons(params):
    return [b["callback_data"] for row in (params.get("reply_markup") or {}).get("inline_keyboard", []) for b in row]


def scenario():
    d = tempfile.mkdtemp(prefix="wa_tpl_e2e_")
    q, m, agent = os.path.join(d, "q.db"), os.path.join(d, "m.db"), os.path.join(d, "a.db")
    c = sqlite3.connect(q)
    c.execute(QSCHEMA)
    c.commit()
    c.close()
    c = sqlite3.connect(m)
    c.execute("CREATE TABLE topics (number TEXT PRIMARY KEY, thread_id INTEGER, trigger_id INTEGER, stage TEXT, "
              "ts REAL, name TEXT)")
    for i, n in enumerate((NUM, NUM_EN, NUM_K, NUM_P)):
        c.execute("INSERT INTO topics VALUES(?,?,?,?,?,?)", (n, 42 + i, 1, "live", NOW, "Клиент %d" % i))
    c.commit()
    c.close()
    posts, gets = [], []
    get_body = [listing("pending")]

    def fake_post(url, payload, key, timeout):
        posts.append(payload)
        return 200, '{"messages":[{"id":"wamid.P%d"}]}' % len(posts), None

    def fake_get(url, key, timeout):
        gets.append(url)
        return 200, get_body[0], None

    environ = {"WA_AGENT_DRAFTS": "1", "WA_AGENT_CARDS": "1", "WA_SEND": "1", "WA_AGENT_TEMPLATES": "1",
               "WA_360_API_KEY": "real_key_abcdef0123456789"}
    send = (lambda to, text, db_path=None: S.send_text(to, text, db_path=db_path, env=environ, transport=fake_post,
                                                        sleep=lambda s: None))
    http, lines = FakeHttp(), []
    clock = [NOW]
    env = {"agent_db": agent, "queue_db": q, "mirror_db": m, "tg_token": "123:SECRET", "show_chat": SHOW}
    core, tg, _flags, _words = SVC.build(env, environ=environ, model=Model(), http=http, send=send,
                                         clock=lambda: clock[0], line=lines.append)
    # настоящий wa_send.send_template с поддельными швами провайдера — через ту же дверь службы
    core.door.tpl = (lambda to, n, lg, p, env=None: S.send_template(to, n, lg, p, env=env, get=fake_get,
                                                                  transport=fake_post, sleep=lambda s: None))
    check(core.templates is True and any(ln.startswith("шаблоны (WA_AGENT_TEMPLATES): вкл") for ln in lines),
          "служба: флаг вкл, строка старта", lines)
    core.tick(NOW - 1000)
    uid = [1000]

    def put(number, ts, echo=0, wamid=None):
        cc = sqlite3.connect(q)
        cur = cc.execute("INSERT INTO wa_inbox(ts_queued, from_number, msg_type, text, ts_msg, echo, history, wamid) "
                         "VALUES(?,?,?,?,?,?,0,?)", (int(ts), number, "text", "x", int(ts), echo, wamid))
        cc.commit()
        cc.close()
        return cur.lastrowid

    def press(data, card_id):
        uid[0] += 1
        http.updates.append([{"update_id": uid[0], "callback_query": {
            "id": "cq%d" % uid[0], "from": HUMAN, "data": data,
            "message": {"message_id": card_id, "chat": {"id": tg.chat}}}}])
        tg.poll()
        ans = http.of("answerCallbackQuery")
        return ans[-1]["text"] if ans else None

    def last_edit():
        e = http.of("editMessageText")
        return e[-1] if e else {}

    def tpl_row(did):
        return core.db.execute("SELECT state, wamid, tries FROM tpl_out WHERE draft_id=?", (did,)).fetchone()

    def card_of(did):
        return core.db.execute("SELECT card_id FROM drafts WHERE id=?", (did,)).fetchone()[0]

    # (1) окно закрыто НАСТОЯЩЕЙ пробой двери: карточка с кнопкой шаблона и текстом шаблона ru
    put(NUM, NOW - 30 * 3600)
    core.tick(NOW)
    card1 = card_of(1)
    p = http.of("sendMessage")[-1]
    check("wa:tpl:1:1" in buttons(p) and "по аренде байка" in p["text"], "(1) карточка при закрытом окне: кнопка+текст",
          (buttons(p), p["text"][-400:]))
    check(core.door.window(NUM)["state"] == "closed", "(1) SendDoor.window по очереди → closed")
    # (2) «✅ Отправить» в закрытое окно: POST нет, черновик ждёт, слова, правка карточки с кнопкой
    ans = press("wa:send:1:1", card1)
    st = core.db.execute("SELECT state FROM drafts WHERE id=1").fetchone()[0]
    check(posts == [] and st == A.PENDING and "окно 24 ч закрыто" in (ans or "") and "30 ч назад" in (ans or ""),
          "(2) «Отправить» в закрытое окно — до захвата, словами", (posts, st, ans))
    check("wa:tpl:1:1" in buttons(last_edit()), "(2) правка карточки несёт кнопку шаблона", last_edit())
    # (3) провайдер: pending → отказ словами, POST нет
    ans = press("wa:tpl:1:1", card1)
    check(len(gets) == 1 and posts == [] and "статус pending" in (ans or "") and "статус pending" in last_edit().get(
        "text", ""), "(3) не одобрен (pending) — отказ словами в ответе и на карточке, POST нет", (gets, posts, ans))
    check(tpl_row(1) and tpl_row(1)[0] == A.NOT_SENT and "wa:tpl:1:1" in buttons(last_edit()),
          "(3) tpl_out not_sent, кнопка жива", (tpl_row(1), buttons(last_edit())))
    # (3b) MARKETING → отказ словами
    get_body[0] = listing("approved", "MARKETING")
    ans = press("wa:tpl:1:1", card1)
    check(posts == [] and "MARKETING" in (ans or ""), "(3b) категория MARKETING — отказ словами, POST нет", ans)
    # (3c) список не читается (500) → «одобрение не проверено»
    core.door.tpl = (lambda to, n, lg, p, env=None: S.send_template(
        to, n, lg, p, env=env, get=lambda u, k, t: (500, '{"error":{"message":"boom"}}', None),
        transport=fake_post, sleep=lambda s: None))
    ans = press("wa:tpl:1:1", card1)
    check(posts == [] and "одобрение не проверено" in (ans or ""), "(3c) 500 на список — «не проверено», POST нет", ans)
    core.door.tpl = (lambda to, n, lg, p, env=None: S.send_template(to, n, lg, p, env=env, get=fake_get,
                                                                  transport=fake_post, sleep=lambda s: None))
    # (4) одобрен → один POST вида template
    get_body[0] = listing("approved")
    n_show = len([x for x in http.of("sendMessage") if str(x.get("chat_id")) == SHOW])
    ans = press("wa:tpl:1:1", card1)
    check(len(posts) == 1 and posts[0].get("type") == "template" and posts[0]["template"]["name"] == "reply_request"
          and posts[0]["template"]["language"] == {"code": "ru"}
          and posts[0]["template"]["components"][0]["parameters"] == [{"type": "text", "text": "байка"}],
          "(4) одобрен — ровно один POST template reply_request ru {{1}}=байка", posts)
    check(tpl_row(1)[:2] == (A.SENT, "wamid.P1") and "шаблон ушёл" in (ans or ""), "(4) tpl_out sent, слова", ans)
    ob = core.db.execute("SELECT via, text FROM outbox WHERE wamid='wamid.P1'").fetchone()
    check(ob and ob[0] == A.VIA_TEMPLATE and "по аренде байка" in ob[1], "(4) ушедший — в outbox", ob)
    # (10) ушедший шаблон — строкой в теме клиента (показ ушедшего агентом, WAMIRROR0410; красная команда M2)
    shown = [x for x in http.of("sendMessage") if str(x.get("chat_id")) == SHOW][n_show:]
    check(len(shown) == 1 and "шаблон" in shown[0]["text"] and "по аренде байка" in shown[0]["text"],
          "(10) строка шаблона в теме клиента — одна, с текстом шаблона", [x.get("text") for x in shown])
    # (5) повтор нажатия и «Отправить» — второго POST нет
    ans5 = press("wa:tpl:1:1", card1)
    ans6 = press("wa:send:1:1", card1)
    check(len(posts) == 1 and "уже ушёл" in (ans5 or "") and "уже ушёл" in (ans6 or ""),
          "(5) второй шаблон и текст в закрытое окно — нет", (len(posts), ans5, ans6))
    # (6) эхо нашего шаблона — не пауза, черновик жив
    put(NUM, NOW + 5, echo=1, wamid="wamid.P1")
    clock[0] = NOW + 6
    core.tick(NOW + 6)
    paused = core.db.execute("SELECT paused FROM clients WHERE number=?", (NUM,)).fetchone()[0]
    st = core.db.execute("SELECT state FROM drafts WHERE id=1").fetchone()[0]
    check(paused == 0 and st == A.PENDING, "(6) эхо шаблона: паузы нет, черновик жив", (paused, st))
    shown2 = [x for x in http.of("sendMessage") if str(x.get("chat_id")) == SHOW][n_show:]
    check(len(shown2) == 1, "(10) такт второй строки шаблона в тему не кладёт", [x.get("text") for x in shown2])
    # (7) клиент ответил: окно открыто (настоящая проба), прежний черновик STALE, новый — обычной кнопкой текстом
    put(NUM, NOW + 10)
    clock[0] = NOW + 11
    core.tick(NOW + 11)
    st1 = core.db.execute("SELECT state FROM drafts WHERE id=1").fetchone()[0]
    clock[0] = NOW + 11 + A.QUIET_DEFAULT + 1
    core.tick(clock[0])
    row2 = core.db.execute("SELECT id, state FROM drafts WHERE number=? ORDER BY id DESC LIMIT 1", (NUM,)).fetchone()
    p2 = [x for x in http.of("sendMessage") if str(x.get("chat_id")) != SHOW][-1]
    check(st1 == A.STALE and row2 and row2[1] == A.PENDING and not any(b.startswith("wa:tpl") for b in buttons(p2)),
          "(7) после ответа: прежний STALE, новый черновик без кнопки шаблона", (st1, row2, buttons(p2)))
    check(core.door.window(NUM)["state"] == "open", "(7) SendDoor.window → open")
    ans = press("wa:send:%d:1" % row2[0], card_of(row2[0]))
    check(len(posts) == 2 and posts[1].get("type") == "text" and "sent" == (ans or ""),
          "(7) новый черновик ушёл обычной кнопкой текстом", (posts[-1:], ans))
    # (8) английский клиент — en, {{1}}=bike
    put(NUM_EN, NOW - 30 * 3600)
    clock[0] = clock[0] + 1
    core.tick(clock[0])
    row3 = core.db.execute("SELECT id FROM drafts WHERE number=?", (NUM_EN,)).fetchone()
    ans = press("wa:tpl:%d:1" % row3[0], card_of(row3[0]))
    check(len(posts) == 3 and posts[2]["template"]["language"] == {"code": "en"}
          and posts[2]["template"]["components"][0]["parameters"] == [{"type": "text", "text": "bike"}],
          "(8) английский клиент — reply_request en, {{1}}=bike", (posts[-1:], ans))
    # (11) ответ с телефона до нажатия «📨» (эхо в очереди, такт ещё не прошёл) — шаблон не уходит (красная команда M1)
    put(NUM_P, NOW - 30 * 3600)
    clock[0] = clock[0] + 1
    core.tick(clock[0])
    row5 = core.db.execute("SELECT id FROM drafts WHERE number=?", (NUM_P,)).fetchone()
    put(NUM_P, clock[0], echo=1, wamid="wamid.PHONE_E2E")
    n_get = len(gets)
    ans = press("wa:tpl:%d:1" % row5[0], card_of(row5[0]))
    st5 = core.db.execute("SELECT state FROM drafts WHERE id=?", (row5[0],)).fetchone()[0]
    check(len(posts) == 3 and len(gets) == n_get and st5 == A.SUPERSEDED and "ответили с телефона" in (ans or ""),
          "(11) ответ с телефона до «📨» — шаблон не уходит, черновик снят, словами", (len(posts), st5, ans))
    # (9) ключа нет → отказ словами (до сети): третий клиент, окно закрыто
    del environ["WA_360_API_KEY"]
    put(NUM_K, NOW - 30 * 3600)
    clock[0] = clock[0] + 1
    core.tick(clock[0])
    row4 = core.db.execute("SELECT id FROM drafts WHERE number=?", (NUM_K,)).fetchone()
    n_get = len(gets)
    ans = press("wa:tpl:%d:1" % row4[0], card_of(row4[0]))
    check(len(posts) == 3 and len(gets) == n_get and "ключ" in (ans or "") and "ключ" in last_edit().get("text", ""),
          "(9) ключа нет — отказ словами до сети", (ans, len(gets), n_get))
    # (12) неушедший шаблон (not_sent) строки в теме клиента не даёт — ни нажатием, ни тактом
    clock[0] = clock[0] + 1
    core.tick(clock[0])
    tag = "черновик №%d," % row4[0]
    shown_k = [x for x in http.of("sendMessage") if str(x.get("chat_id")) == SHOW and tag in x.get("text", "")]
    check(shown_k == [], "(12) отказанный шаблон в тему клиента не ложится", [x.get("text") for x in shown_k])


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    try:
        scenario()
    except Exception as e:                                           # noqa: BLE001
        RES.append((False, "сценарий упал", "%s: %s" % (type(e).__name__, str(e)[:300])))
    bad = 0
    for i, (ok, what, detail) in enumerate(RES, 1):
        name = "e2e_%02d" % i
        if ok:
            print("PASS", name, "—", what)
        else:
            bad += 1
            print("FAIL", name, "—", what, "·", detail)
    print("ИТОГ %d/%d" % (len(RES) - bad, len(RES)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
