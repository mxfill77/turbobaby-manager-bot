#!/usr/bin/env python3
"""Тесты службы показа WhatsApp в Telegram (`wa_tg_mirror.py`), 01.10.2026.

СЕТИ ЗДЕСЬ НЕТ: единственный шов к сети — `http`, переданный в Mirror; он подменён выдуманными
API 360dialog и Telegram, а любой чужой хост роняет тест. Живая база не открывается: очередь —
временная, собранная схемой самого wa_webhook. Временные файлы тесты НЕ удаляют (правило полосы).

Разделы:
  (1) флаг выключен   — вызовов Telegram 0 при полном конфиге, медиа качаются, строка старта
  (2) медиа           — файл 600 рядом с базой, повтор не качается, отказ с кодом, потолок, чужой хост
  (3) показ стоит     — нет ключа / нет тем / нет прав: WARNING с причиной раз в час, вызовов показа 0
  (4) показ           — тема «имя · номер», предыстория, строка провала, файлы, новое; квитанции нет
  (5) дедуп и рестарт — повтор такта и новый процесс не дают дублей; обрыв посреди вызова — без повтора
  (6) темп            — ≤20 вызовов в скользящую минуту; 429 → ждать retry_after
  (7) ожидание        — тревога в общую тему через 10 минут, один раз; сводка числами
  (8) границы         — очередь только mode=ro, выход в сеть один

Мутанты: WA_TG_MIRROR_SRC=<каталог> ставит копию модуля впереди дерева.
"""

import base64
import json
import logging
import os
import re
import sys
import tempfile
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
if os.environ.get("WA_TG_MIRROR_SRC"):
    sys.path.insert(0, os.environ["WA_TG_MIRROR_SRC"])

import wa_webhook as W
import wa_tg_mirror as M

res = []


def ok(cond, label):
    print(("  PASS " if cond else "  FAIL ") + label)
    res.append(bool(cond))
    return bool(cond)


class Logs(logging.Handler):
    def __init__(self):
        super().__init__()
        self.lines = []

    def emit(self, record):
        self.lines.append((record.levelname, record.getMessage()))

    def count(self, level, sub):
        return sum(1 for lv, msg in self.lines if lv == level and sub in msg)


LOGS = Logs()
logging.getLogger("wa_tg_mirror").addHandler(LOGS)
logging.getLogger("wa_tg_mirror").setLevel(logging.INFO)
logging.getLogger("wa_webhook").setLevel(logging.ERROR)

KEY = "k" * 26
NOW0 = int(time.time())


class Clock:
    def __init__(self, t):
        self.t = float(t)
        self.slept = []

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.slept.append(s)
        self.t += s


class FakeHTTP:
    """Выдуманные 360dialog и Telegram. Любой другой хост → AssertionError (тест падает)."""

    def __init__(self, clock, member=None, chat=None):
        self.clock = clock
        self.tg = []          # (время, метод, params|bytes)
        self.d360 = []        # url
        self.script = {}      # метод или url → [(код, тело)]
        self.member = member or {"status": "administrator", "can_manage_topics": True}
        self.chat = chat or {"id": -1001, "type": "supergroup", "is_forum": True}
        self.thread = 500
        self.fail_threads = False

    def __call__(self, method, url, headers, data, timeout):
        if url.startswith(M.TG_BASE + "/"):
            meth = url.rsplit("/", 1)[1]
            if headers.get("Content-Type", "").startswith("multipart"):
                params = data
                thread = re.search(rb'name="message_thread_id"\r\n\r\n(\d+)', data)
                thread = int(thread.group(1)) if thread else None
            else:
                params = json.loads(data.decode("utf-8"))
                thread = params.get("message_thread_id")
            self.tg.append((self.clock(), meth, params))
            if self.script.get(meth):
                st, body = self.script[meth].pop(0)
                return st, json.dumps(body).encode()
            if self.fail_threads and meth in ("sendMessage", "sendDocument") and thread:
                return 400, json.dumps({"ok": False, "description": "Bad Request: topic closed"}).encode()
            result = {"getMe": {"id": 77, "is_bot": True},
                      "getChat": self.chat,
                      "getChatMember": self.member}.get(meth)
            if meth == "createForumTopic":
                self.thread += 1
                result = {"message_thread_id": self.thread, "name": params["name"]}
            if result is None:
                result = {"message_id": len(self.tg)}
            return 200, json.dumps({"ok": True, "result": result}).encode()
        if url.startswith(M.D360_BASE + "/"):
            assert headers.get(M.D360_KEY_HEADER) == KEY, "ключ канала не тот"
            self.d360.append(url)
            if self.script.get(url):
                st, body = self.script[url].pop(0)
                return st, body
            tail = url[len(M.D360_BASE) + 1:]
            if tail.startswith("whatsapp_business/"):
                return 200, b"FILE:" + tail.encode()
            return 200, json.dumps({"url": M.META_MEDIA_HOST + "/whatsapp_business/attachments/?mid="
                                    + tail, "mime_type": "image/jpeg", "file_size": 20}).encode()
        raise AssertionError("чужой хост: " + url.split("/")[2])

    def methods(self, since=0):
        return [m for _, m, _ in self.tg[since:]]

    def texts(self, since=0):
        return [p["text"] for _, m, p in self.tg[since:] if m == "sendMessage"]


def docs(http, since=0, fname=None):
    """Тела файлов sendDocument (multipart) → [bytes]; fname — только файл с этим именем."""
    out = []
    for _, meth, p in http.tg[since:]:
        if meth != "sendDocument":
            continue
        mm = re.search(rb'filename="([^"]*)"\r\nContent-Type: [^\r]*\r\n\r\n(.*)\r\n--[0-9a-f]+--\r\n$', p, re.S)
        if mm and (fname is None or mm.group(1).decode() == fname):
            out.append(mm.group(2))
    return out


def doc_text(http, since, fname):
    return "\n".join(d.decode("utf-8") for d in docs(http, since, fname))


TMP = tempfile.mkdtemp(prefix="wa_tg_mirror_test_")
_seq = [0]


def world(show, token=True, chat=True):
    _seq[0] += 1
    d = os.path.join(TMP, "w%d" % _seq[0])
    os.makedirs(d)
    q = W.WAQueueDB(os.path.join(d, "wa_queue.db"))
    env = {"queue_db": q.db_path, "state_db": os.path.join(d, "wa_tg_mirror.db"),
           "media_dir": os.path.join(d, "wa_media"), "d360_key": KEY,
           "tg_token": "123:fake" if token else "", "tg_chat": "-1001" if chat else "", "show": show,
           # архив по умолчанию — выдуманный и отсутствующий: боевой /root/wa_archive тест не читает
           "archive_db": os.path.join(d, "arch", "wa_archive.db"),
           "archive_media": os.path.join(d, "arch", "media"),
           "archive_manifest": os.path.join(d, "arch", "media_manifest.jsonl")}
    return q, env


_w = [0]


def ev(number, text=None, echo=False, history=False, typ="text", media_id=None, ts=None, name="",
       wamid=None):
    _w[0] += 1
    return {"from": number, "name": name, "type": typ, "text": text, "media_id": media_id,
            "mime": "image/jpeg" if media_id else None,
            "media_note": "no_file" if typ == "media_placeholder" else None,
            "ts": ts if ts is not None else NOW0, "echo": echo, "history": history,
            "wamid": wamid or "wamid.T%05d" % _w[0], "raw": {}}


def wamid_of(number, key_id):
    """wamid живой формы: base64, внутри номер и key_id строками с длиной за байтом 0x18."""
    raw = (b"\x1c\x18" + bytes([len(number)]) + number.encode() + b"\x15\x02\x00\x12\x18"
           + bytes([len(key_id)]) + key_id.encode() + b"\x00")
    return "wamid." + base64.b64encode(raw).decode()


def make_archive(env, rows, files=None, manifest=True):
    """Выдуманный архив схемы build_archive.py (нужные службе поля) + опись + файлы медиа.
    rows: (номер, ts, from_me, kind, text, caption, transcript, media_file, key_id);
    files: {key_id: (from_me, байты)} — ляжет в media/ под именем sha256 и в опись."""
    import hashlib
    import sqlite3
    d = os.path.dirname(env["archive_db"])
    os.makedirs(env["archive_media"], exist_ok=True)
    db = sqlite3.connect(env["archive_db"])
    db.executescript("""CREATE TABLE messages (id INTEGER PRIMARY KEY AUTOINCREMENT, number TEXT NOT NULL,
        ts INTEGER NOT NULL, from_me INTEGER NOT NULL, kind TEXT NOT NULL, text TEXT, caption TEXT,
        transcript TEXT, media_file TEXT, key_id TEXT NOT NULL, UNIQUE (number, key_id, from_me));
        CREATE TABLE chats (number TEXT PRIMARY KEY, first_ts INTEGER, last_ts INTEGER, n_messages INTEGER);""")
    db.executemany("INSERT INTO messages (number, ts, from_me, kind, text, caption, transcript, media_file, "
                   "key_id) VALUES (?,?,?,?,?,?,?,?,?)", rows)
    db.commit()
    db.close()
    if manifest:
        with open(env["archive_manifest"], "w", encoding="utf-8") as f:
            for key_id, (from_me, data) in (files or {}).items():
                sha = hashlib.sha256(data).hexdigest()
                with open(os.path.join(env["archive_media"], sha + ".bin"), "wb") as g:
                    g.write(data)
                f.write(json.dumps({"sha256": sha, "ext": ".bin", "size": len(data), "mime": "image/jpeg",
                                    "server_file": sha + ".bin", "msg_keys": ["%s|%d" % (key_id, from_me)]})
                        + "\n")
    return d


def mirror(env, clock, http, free=10 ** 12):
    return M.Mirror(env, http=http, clock=clock, sleep=clock.sleep, disk_free=lambda p: free)


A, B, C, D = "66800000001", "66800000002", "66800000003", "66800000004"

# ─────────────────────────────────────────────────────────────────────────────
print("(1) флаг выключен")
ok(M._flag_on(None) is False and M._flag_on("") is False and M._flag_on("0") is False
   and M._flag_on("1") is True and M._flag_on(" on ") is True, "флаг: пусто/0 → выкл, 1/on → вкл")
q, env = world(show=False)
q.enqueue([ev(A, "привет"), ev(A, typ="image", media_id="MID1"), ev(B, "эхо", echo=True)])
clk = Clock(NOW0 + 5)
http = FakeHTTP(clk)
m = mirror(env, clk, http)
for _ in range(3):
    m.tick()
    clk.t += 400
ok(len(http.tg) == 0, "показ выключен, ключ и группа есть: вызовов Telegram %d (ждали 0)" % len(http.tg))
ok("показ выключен" in M.start_line(m), "строка старта говорит «показ выключен»")
ok(len(http.d360) == 2, "медиа качается и при выключенном показе: вызовов 360dialog %d" % len(http.d360))
files = os.listdir(env["media_dir"])
ok(len(files) == 1, "файл один: %d" % len(files))
ok(M.show_enabled({}) is False, "show_enabled без ключа флага → выключен")

# ─────────────────────────────────────────────────────────────────────────────
print("\n(2) медиа")
path = os.path.join(env["media_dir"], files[0])
ok(os.path.dirname(env["media_dir"]) == os.path.dirname(env["queue_db"]), "каталог медиа рядом с базой")
if os.name == "posix":
    ok(oct(os.stat(path).st_mode & 0o777) == "0o600", "права файла 600")
    ok(oct(os.stat(env["media_dir"]).st_mode & 0o777) == "0o700", "права каталога 700")
ok(open(path, "rb").read().startswith(b"FILE:whatsapp_business/"), "содержимое — тело второго GET")
ok(A not in files[0] and files[0].endswith(".jpg"), "в имени файла нет номера, расширение по mime")
n0 = len(http.d360)
m.tick()
m2 = mirror(env, clk, http)
m2.tick()
ok(len(http.d360) == n0, "повтор такта и рестарт: повторного скачивания нет (%d → %d)" % (n0, len(http.d360)))

q, env = world(show=False)
q.enqueue([ev(A, typ="image", media_id="GONE"), ev(A, typ="image", media_id="FLAKY"),
           ev(A, typ="image", media_id="BIG"), ev(A, typ="image", media_id="EVIL")])
clk = Clock(NOW0 + 5)
http = FakeHTTP(clk)
http.script[M.D360_BASE + "/GONE"] = [(404, b'{"error":"x"}')]
http.script[M.D360_BASE + "/FLAKY"] = [(500, b"")]
http.script[M.D360_BASE + "/EVIL"] = [(200, json.dumps({"url": "https://evil.example/x"}).encode())]
http.script[M.D360_BASE + "/BIG"] = [(200, json.dumps({"url": M.META_MEDIA_HOST + "/whatsapp_business/b",
                                                      "file_size": 10 ** 10}).encode())]
LOGS.lines.clear()
m = mirror(env, clk, http)
m.tick()
st = dict(m.st.execute("SELECT code, state FROM media").fetchall())
ok(st.get("meta:404") == "fail", "404 → отказ конечный, код meta:404")
ok(st.get("meta:500") == "retry", "500 → повтор позже")
ok(st.get("CEILING") == "wait", "файл больше потолка → ждёт, не качается")
ok(st.get("url:foreign_host") == "fail", "ссылка на чужой хост → отказ, ключ туда не ушёл (иначе тест упал бы)")
ok(LOGS.count("WARNING", "код=meta:404") == 1 and LOGS.count("WARNING", "код=CEILING") == 1,
   "отказ — строка WARNING с кодом")
n0 = len(http.d360)
m.tick()
ok(len(http.d360) == n0, "конечный отказ и ранний повтор не качаются снова")
clk.t += 61
m.tick()
ok(len(http.d360) == n0 + 2, "повтор после паузы — одна новая попытка (+%d)" % (len(http.d360) - n0))
ok(len(os.listdir(env["media_dir"])) == 1, "после повтора файл лёг (1)")
q2, env3 = world(show=False)
q2.enqueue([ev(A, typ="image", media_id="M9")])
env3["d360_key"] = ""
LOGS.lines.clear()
m = mirror(env3, clk, http)
m.tick()
m.tick()
ok(LOGS.count("WARNING", "WA_D360_API_KEY") == 1, "нет ключа канала → WARNING раз в час, скачивания нет")

q, env = world(show=False)
q.enqueue([ev(A, typ="image", media_id="SMALL")])
clk = Clock(NOW0 + 5)
http = FakeHTTP(clk)
m = mirror(env, clk, http, free=M.FREE_FLOOR + 10)
m.tick()
ok(dict(m.st.execute("SELECT code, state FROM media").fetchall()).get("CEILING") == "wait",
   "пол свободного места → не пишется")

# ─────────────────────────────────────────────────────────────────────────────
print("\n(3) показ включён, но стоит")
for label, kw, member, chat, reason in (
        ("нет ключа", {"token": False}, None, None, "нет ключа бота"),
        ("нет группы", {"chat": False}, None, None, "нет группы"),
        ("нет тем", {}, None, {"id": -1, "is_forum": False}, "выключены темы"),
        ("нет прав", {}, {"status": "administrator", "can_manage_topics": False}, None, "права управлять темами")):
    q, env = world(show=True, **kw)
    q.enqueue([ev(A, "привет")])
    clk = Clock(NOW0 + 5)
    http = FakeHTTP(clk, member=member, chat=chat)
    LOGS.lines.clear()
    m = mirror(env, clk, http)
    m.tick()
    clk.t += 400
    m.tick()
    shows = [x for x in http.methods() if x in ("createForumTopic", "sendMessage", "sendDocument")]
    ok(LOGS.count("WARNING", reason) == 1 and not shows,
       "%s: показ стоит, WARNING с причиной 1 раз за час, вызовов показа %d" % (label, len(shows)))
    clk.t += 3600
    m.tick()
    ok(LOGS.count("WARNING", reason) == 2, "%s: через час WARNING снова" % label)
    if not kw:
        ok(http.methods()[:1] == ["getMe"], "%s: проверка идёт вызовами чтения" % label)
    else:
        ok(len(http.tg) == 0, "%s: без ключа или группы Telegram не зовётся вовсе" % label)

# ─────────────────────────────────────────────────────────────────────────────
print("\n(4) показ: тема, предыстория, провал, файлы, новое")
q, env = world(show=True)
T0 = NOW0 - 30 * 86400
q.enqueue([ev(A, "старый вопрос", history=True, ts=T0, name="Анна"),
           ev(A, "старый ответ", echo=True, history=True, ts=T0 + 60),
           ev(A, typ="media_placeholder", history=True, ts=T0 + 120),
           ev(A, typ="image", media_id="HIST1", history=True, ts=T0 + 180),
           ev(A, "delivered", typ="status", echo=True, ts=T0 + 200)])
clk = Clock(NOW0 + 5)
http = FakeHTTP(clk)
m = mirror(env, clk, http)
m.tick()                                  # первое включение: проверка + медиа истории
ok(http.methods() == ["getMe", "getChat", "getChatMember"], "до живого сообщения темы нет: %s" % http.methods())
q.enqueue([ev(A, "новый вопрос", name="Анна"), ev(A, "sent", typ="status", echo=True)])
clk.t = NOW0 + 10
k0 = len(http.tg)
m.tick()
meths = http.methods(k0)
ok(meths[:1] == ["createForumTopic"], "первое живое входящее открыло тему")
name = http.tg[k0][2]["name"]
ok(name == "Анна · +" + A, "тема названа «имя · номер»")
ok(meths[1:] == ["sendMessage", "sendDocument", "sendMessage", "sendDocument", "sendMessage"],
   "порядок: шапка → файл истории → последние текстом → их медиа → новое: %s" % meths[1:])
texts = http.texts(k0) + ["", "", ""]
hist = doc_text(http, k0, "history.txt")
pos = [hist.find(s) for s in ("старый вопрос", "старый ответ", "[медиа — файла нет]", "[фото — на сервере]")]
ok(-1 not in pos and pos == sorted(pos), "файл истории по времени; заглушка — «файла нет», скачанное — «на сервере»")
ok("клиент: старый вопрос" in hist and "мы: старый ответ" in hist, "пометки «клиент» и «мы»")
ok(M.pk_full(T0) in hist and M.pk_full(T0) == time.strftime("%d.%m.%Y %H:%M", time.gmtime(T0 + 7 * 3600)),
   "время по Пхукету (UTC+7), ДД.ММ.ГГГГ ЧЧ:ММ")
ok("delivered" not in hist and all("sent" not in t and "delivered" not in t for t in texts), "квитанций в показе нет")
ok(texts[0].startswith("писал раньше: с %s, 4 сообщений (клиент 3 / мы 1), серий обращений 1" % M.pk_date(T0))
   and "архива копии телефона нет" in texts[0], "шапка: с даты, N (клиент/мы), серии, и чего нет: %r" % texts[0][:60])
ok("клиент: старый вопрос" in texts[1] and "мы: старый ответ" in texts[1], "последние сообщения — текстом")
ok(not hasattr(M, "GAP_LINE") and not any("переписки на сервере нет" in t for t in texts), "строки о провале нет")
ok("новый вопрос" in texts[2] and "клиент" in texts[2], "затем новое")
threads = {p.get("message_thread_id") if isinstance(p, dict) else "file" for _, mm, p in http.tg[k0 + 1:]}
ok(threads <= {501, "file"}, "всё в свою тему")
q.enqueue([ev(B, "мы пишем первыми", echo=True)])
k1 = len(http.tg)
m.tick()
ok(http.methods(k1)[:1] == ["createForumTopic"] and "без имени · +" + B == http.tg[k1][2]["name"],
   "живое эхо клиента тоже открывает тему; без имени — «без имени»")
q.enqueue([ev(A, "ещё")])
k2 = len(http.tg)
m.tick()
ok(http.methods(k2) == ["sendMessage"] and http.tg[k2][2]["message_thread_id"] == 501,
   "дальше каждое живое — в свою тему, одним сообщением")

q, env = world(show=True)
q.enqueue([ev(C, "строка номер %03d " % i + "x" * 40, history=True, ts=T0 + i) for i in range(300)])
clk = Clock(NOW0 + 5)
http = FakeHTTP(clk)
m = mirror(env, clk, http)
m.tick()
q.enqueue([ev(C, "живое")])
m.tick()
batches = [t for t in http.texts() if "строка номер" in t]
ok(batches and all(len(t) <= 4000 for t in batches),
   "текстовые сообщения ≤4000 знаков: %d шт., максимум %d" % (len(batches), max(map(len, batches), default=0)))
nums = [int(x) for x in re.findall(r"строка номер (\d+)", "\n".join(batches))]
ok(nums == list(range(285, 300)), "текстом — ровно последние 15, по времени: %s" % nums[:3])
nums = [int(x) for x in re.findall(r"строка номер (\d+)", doc_text(http, 0, "history.txt"))]
ok(nums == list(range(300)), "в файле истории все 300 прежних строк, по времени, без пропусков и повторов")
ok(M.batch_lines([("k", "я" * 9000)]) and all(len(t) <= 4000 for _, t in M.batch_lines([("k", "я" * 9000)])),
   "длинная строка режется по 4000")

# ─────────────────────────────────────────────────────────────────────────────
print("\n(5) дедуп и рестарт")
q, env = world(show=True)
q.enqueue([ev(D, "было", history=True, ts=T0)])
clk = Clock(NOW0 + 5)
http = FakeHTTP(clk)
m = mirror(env, clk, http)
m.tick()
q.enqueue([ev(D, "живое 1"), ev(D, "живое 2")])
m.tick()
n_show = len([x for x in http.methods() if x.startswith("send") or x == "createForumTopic"])
m.tick()
m.tick()
n_again = len([x for x in http.methods() if x.startswith("send") or x == "createForumTopic"])
ok(n_again == n_show, "повтор такта: новых показов %d (ждали 0)" % (n_again - n_show))
m2 = mirror(env, clk, http)
m2.tick()
m2.tick()
n_restart = len([x for x in http.methods() if x.startswith("send") or x == "createForumTopic"])
ok(n_restart == n_again, "рестарт процесса: новых показов %d (ждали 0), тем не открыто заново" % (n_restart - n_again))
q.enqueue([ev(D, "живое 3")])
m2.tick()
n_after = len([x for x in http.methods() if x.startswith("send") or x == "createForumTopic"])
ok(http.texts()[-1].endswith("живое 3") and n_after == n_restart + 1,
   "после рестарта — с места: новое показано ровно одно (+%d)" % (n_after - n_restart))
shown_keys = m2.st.execute("SELECT COUNT(*), COUNT(DISTINCT key) FROM shown").fetchone()
ok(shown_keys[0] == shown_keys[1], "wamid в журнале показа уникальны")
# обрыв посреди вызова: ключ «в отправке» → после рестарта считается показанным
q.enqueue([ev(D, "оборвано")])
wam = "msg:wamid.T%05d" % _w[0]
m2.st.execute("INSERT INTO shown(key, number, state, ts) VALUES (?,?,?,?)", (wam, D, "sending", 0))
m2.st.commit()
LOGS.lines.clear()
m3 = mirror(env, clk, http)
k3 = len(http.tg)
m3.tick()
ok(not any("оборвано" in t for t in http.texts(k3)), "обрыв посреди вызова: повтора (дубля) нет")
ok(LOGS.count("WARNING", "после обрыва") == 1, "обрыв назван строкой WARNING")

# ─────────────────────────────────────────────────────────────────────────────
print("\n(6) темп и 429")
q, env = world(show=True)
clk = Clock(NOW0 + 5)
http = FakeHTTP(clk)
m = mirror(env, clk, http)
m.tick()
q.enqueue([ev(A, "м%02d" % i) for i in range(45)])
m.tick()
times = [t for t, _, _ in http.tg]
worst = max(sum(1 for u in times if t <= u < t + 60) for t in times)
ok(len(http.texts()) >= 45 and worst <= 20, "45 сообщений: в любой минуте не больше 20 (худшая %d)" % worst)
q, env = world(show=True)
clk = Clock(NOW0 + 5)
http = FakeHTTP(clk)
m = mirror(env, clk, http)
m.tick()
q.enqueue([ev(A, "раз")])
http.script["createForumTopic"] = [(429, {"ok": False, "parameters": {"retry_after": 7}})]
m.tick()
ok(7 in clk.slept and http.methods().count("createForumTopic") == 2 and
   sum(1 for t in http.texts() if t.endswith("раз")) == 1, "429 → ждали retry_after=7, повтор один, дубля нет")

# ─────────────────────────────────────────────────────────────────────────────
print("\n(7) ожидание и сводка")
q, env = world(show=True)
clk = Clock(NOW0 + 5)
http = FakeHTTP(clk)
m = mirror(env, clk, http)
m.tick()
q.enqueue([ev(A, "застряло")])
http.fail_threads = True
LOGS.lines.clear()
m.tick()
alarms = [t for t in http.texts() if "отстал" in t]
ok(not alarms, "моложе 10 минут — тревоги нет")
clk.t = NOW0 + 700
m.tick()
gen = [(p.get("message_thread_id"), p["text"]) for _, mm, p in http.tg if mm == "sendMessage" and "отстал" in p["text"]]
ok(len(gen) == 1 and gen[0][0] is None, "старше 10 минут — тревога в общую тему, одна")
m.tick()
ok(len([t for t in http.texts() if "отстал" in t]) == 1, "повтор такта — тревога не повторяется")
ok(LOGS.count("INFO", "сводка: показ=идёт") >= 1, "сводка числами в журнале")
clk.t += 301
k7 = len(http.tg)
m.tick()
ok(any(t.startswith("сводка:") for t in http.texts(k7)), "пока отставание есть — сводка в группу раз в 5 минут")
ok(not any(x in msg for _, msg in LOGS.lines for x in (A, B, C, D)), "в журнале нет номеров клиентов")
ok(not any("застряло" in msg or "Анна" in msg for _, msg in LOGS.lines), "в журнале нет текстов и имён")

# ─────────────────────────────────────────────────────────────────────────────
print("\n(8) границы")
src = open(M.__file__, encoding="utf-8").read()
ok(src.count("urlopen(") == 1, "выход в сеть ровно один (http_request)")
ok("mode=ro" in src and "sqlite3.connect(self.queue_db" not in src, "живая очередь открывается только mode=ro")
ok(re.search(r"(INSERT|UPDATE|DELETE|ALTER|CREATE)[^\"\n]*wa_inbox", src) is None,
   "записи в очередь нет: ни одного INSERT/UPDATE/DELETE/ALTER/CREATE по wa_inbox")
# WAMIRROR0410: четвёртое соединение — база агента (строка показа и текст ушедшего), тоже только mode=ro
ok(len(re.findall(r"sqlite3\.connect\(", src)) == 4 and src.count("?mode=ro") == 3,
   "архив, очередь и база агента открываются только mode=ro; четвёртая база — своя")

# ─────────────────────────────────────────────────────────────────────────────
print("\n(9) предыстория из архива копии телефона")
E, F, G = "66800000005", "66800000006", "66800000007"
T1 = NOW0 - 400 * 86400
T2 = T1 + 100 * 86400
ARCH = [(E, T1, 0, "text", "архив первый", None, None, None, "KARCH00001"),
        (E, T1 + 60, 1, "image", None, "подпись фото", None, "IMG-1.jpg", "KARCH00002"),
        (E, T1 + 120, 0, "audio", None, None, None, "PTT-1.opus", "KARCH00003"),
        (E, T2, 0, "text", "пара с очередью", None, None, None, "KPAIR00004"),
        (E, T2 + 60, 1, "document", None, None, None, "DOC-1.pdf", "KBIG000005"),
        (E, NOW0 - 60, 0, "text", "живое из архива", None, None, None, "KLIVE00006"),
        (F, T1, 0, "text", "чужой номер", None, None, None, "KOTHER0008")]
AFILES = {"KARCH00002": (1, b"IMG"), "KBIG000005": (1, b"D" * 20)}


def arch_world(files=AFILES, manifest=True):
    q, env = world(show=True)
    make_archive(env, ARCH, files, manifest)
    q.enqueue([ev(E, "пара с очередью", history=True, ts=T2, wamid=wamid_of(E, "KPAIR00004")),
               ev(E, "только в очереди", history=True, ts=T2 + 120, wamid=wamid_of(E, "KQONLY0007")),
               ev(E, "read", typ="status", echo=True, ts=T2 + 130)])
    return q, env


def run_arch(q, env, http=None, clk=None):
    clk = clk or Clock(NOW0 + 5)
    http = http or FakeHTTP(clk)
    m = mirror(env, clk, http)
    m.tick()                                    # первое включение
    q.enqueue([ev(E, "живое из архива", wamid=wamid_of(E, "KLIVE00006"))])
    m.tick()
    return m, http, clk


ok(M.parse_wamid(wamid_of(E, "KPAIR00004")) == (E, "KPAIR00004") and M.parse_wamid("wamid.T00001")[1] is None,
   "wamid раскрывается в номер и key_id; выдуманный — без key_id")
q, env = arch_world()
old_max, M.TG_FILE_MAX = M.TG_FILE_MAX, 10
try:
    m, http, clk = run_arch(q, env)
finally:
    M.TG_FILE_MAX = old_max
texts = http.texts()
hist = doc_text(http, 0, "history.txt")
hl = [ln for ln in hist.split("\n") if ln]
ok(len(hl) == 6, "файл истории: архив (5, без записи живой строки) + очередь без пары (1) = %d строк" % len(hl))
ok(hist.count("пара с очередью") == 1, "пара архив+очередь (номер и key_id) в файле истории один раз: %d"
   % hist.count("пара с очередью"))
ok(sum(t.count("пара с очередью") for t in texts) == 1, "и среди последних текстом — один раз")
ok("живое из архива" not in hist and sum(t.count("живое из архива") for t in texts) == 1,
   "архивная пара живой строки не уходит в историю; живое показано один раз — «новым»")
ok("только в очереди" in hist and "чужой номер" not in hist, "строка очереди без пары — в истории; чужой номер — нет")
pos = [hist.find(s) for s in ("архив первый", "подпись фото", "[аудио — файла нет]", "пара с очередью",
                              "[документ — на сервере]", "только в очереди")]
ok(-1 not in pos and pos == sorted(pos), "архив и очередь слиты по времени")
ok("мы: [фото — на сервере] подпись фото" in hist and "клиент: [аудио — файла нет]" in hist,
   "медиа: «на сервере» по описи, «файла нет» без файла")
head = texts[0]
ok(head == "писал раньше: с %s, 6 сообщений (клиент 4 / мы 2), серий обращений 2 (перерыв больше 30 дней), "
   "последнее %s" % (M.pk_date(T1), M.pk_date(T2 + 120)), "шапка: %r" % head[:90])
ok(docs(http, 0, "file.bin") == [b"IMG"], "медиа последних — файлом из архива (1 файл)")
ok(any("[документ — файл 0 МБ на сервере, больше лимита Telegram]" in t for t in texts),
   "файл больше лимита — строкой")
ok(http.methods()[3:] == ["createForumTopic", "sendMessage", "sendDocument", "sendMessage", "sendDocument",
                          "sendMessage", "sendMessage"], "порядок темы: %s" % http.methods()[3:])

# без пары в архиве + ни одной строки — «раньше не писал»
q, env = world(show=True)
make_archive(env, ARCH, AFILES)
clk = Clock(NOW0 + 5)
http = FakeHTTP(clk)
m = mirror(env, clk, http)
m.tick()
q.enqueue([ev(G, "впервые")])
m.tick()
ok(http.texts()[:1] == ["раньше не писал"] and not docs(http, 0, "history.txt"),
   "нового клиента шапка зовёт «раньше не писал», файла истории нет")

print("\n(9б) архива или описи нет")
q, env = world(show=False)
clk = Clock(NOW0 + 5)
LOGS.lines.clear()
m = mirror(env, clk, FakeHTTP(clk))
m.tick()
m.tick()
ok(LOGS.count("WARNING", "архива копии телефона нет") == 1 and LOGS.count("WARNING", "описи медиа архива нет") == 1,
   "нет архива и описи — WARNING раз в час, служба идёт")
clk.t += 3600
m.tick()
ok(LOGS.count("WARNING", "архива копии телефона нет") == 2, "через час — снова")
ok("архив: нет, опись медиа: нет" in M.start_line(m), "строка старта говорит, чего нет")
q, env = arch_world(manifest=False)
m, http, clk = run_arch(q, env)
ok("описи медиа архива нет" in http.texts()[0] and "[фото — файла нет]" in doc_text(http, 0, "history.txt")
   and not docs(http, 0, "file.bin"), "нет описи — тема открыта, шапка называет, файлов архива нет")
q, env = world(show=True)
os.makedirs(os.path.dirname(env["archive_db"]))
open(env["archive_db"], "wb").write(b"not a database" * 100)
clk = Clock(NOW0 + 5)
http = FakeHTTP(clk)
m = mirror(env, clk, http)
m.tick()
q.enqueue([ev(G, "привет")])
m.tick()
ok(http.texts()[:1] and "архив не читается" in http.texts()[0] and http.texts()[-1].endswith("привет"),
   "битый архив — не падение: тема открыта, шапка называет причину")


class Kill(BaseException):
    pass


class KillHTTP(FakeHTTP):
    def __init__(self, clock, at):
        super().__init__(clock)
        self.at, self.n = at, 0

    def __call__(self, method, url, headers, data, timeout):
        if "/sendMessage" in url or "/sendDocument" in url:
            self.n += 1
            if self.n == self.at:
                raise Kill()
        return FakeHTTP.__call__(self, method, url, headers, data, timeout)


print("\n(9в) рестарт посреди открытия темы")
bad = []
for at in range(1, 7):
    q, env = arch_world()
    clk = Clock(NOW0 + 5)
    h1 = KillHTTP(clk, at)
    try:
        run_arch(q, env, http=h1, clk=clk)
    except Kill:
        pass
    h2 = FakeHTTP(clk)
    h2.thread = 900
    m2 = mirror(env, clk, h2)
    m2.tick()
    m2.tick()
    sent = [(meth, json.dumps(p, ensure_ascii=False, sort_keys=True) if isinstance(p, dict)
             else re.sub(rb"[0-9a-f]{32}", b"", p)) for h in (h1, h2) for _, meth, p in h.tg
            if meth in ("sendMessage", "sendDocument", "createForumTopic")]
    stage = m2.st.execute("SELECT stage FROM topics").fetchall()
    if len(sent) != len(set(map(str, sent))) or [x for x, _ in sent].count("createForumTopic") != 1 \
            or stage != [("live",)]:
        bad.append(at)
ok(not bad, "обрыв на каждом из 6 вызовов темы: после рестарта дублей 0, тема одна, дошла до «нового» (сбой на %s)"
   % bad)

print("\n(9г) первое включение: 24 часа")
q, env = world(show=True)
q.enqueue([ev(F, "за 23 часа")])
clk = Clock(time.time() + 23 * 3600)
http = FakeHTTP(clk)
http.fail_threads = True
m = mirror(env, clk, http)
m.tick()
ok(http.methods().count("createForumTopic") == 1, "живая строка за 23 ч до включения открыла тему")
clk.t += 700
m.tick()
ok(not [t for t in http.texts() if "отстал" in t], "по строке до включения тревоги нет")
q.enqueue([ev(F, "после включения")])
m.tick()
al = [t for t in http.texts() if "отстал" in t]
ok(len(al) == 1 and "1 живых" in al[0], "строка после включения, не показанная 10 минут, — тревога (одна)")
http.fail_threads = False
m.tick()
ok(any(t.endswith("за 23 часа") for t in http.texts()), "строка до включения показана «новым» в своей теме")
q, env = world(show=True)
q.enqueue([ev(G, "за 25 часов")])
clk = Clock(time.time() + 25 * 3600)
http = FakeHTTP(clk)
m = mirror(env, clk, http)
m.tick()
m.tick()
ok(http.methods().count("createForumTopic") == 0, "строка старше 24 ч до включения тему не открывает")

print("\nИтог: %d/%d PASS" % (sum(res), len(res)))
fails = sum(1 for r in res if not r)
if fails:
    print("FAIL: %d тест(а/ов) не прошли" % fails)
    sys.exit(1)
