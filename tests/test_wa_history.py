#!/usr/bin/env python3
"""Тесты wa_history — склейка истории клиента WhatsApp, вынесенная из службы показа (WAHISTMOD0110).

СЕТИ ЗДЕСЬ НЕТ, живая база не открывается: очередь — временная, собранная схемой самого wa_webhook,
архив — выдуманный схемы build_archive.py. Временные файлы тесты НЕ удаляют (правило полосы).

Разделы:
  (1) без дублей        — пара архив+очередь по key_id один раз; повтор строки и записи — один раз
  (2) порядок           — по времени; при равном времени — по ключу
  (3) медиа словом      — архив, очередь, заглушка; строка темы и строка модели
  (4) «новое» (trig)    — строка темы и её архивная пара в историю не идут
  (5) не пишет          — файлы баз и описи побайтно те же, новых файлов нет, все соединения mode=ro
  (6) пусто — не ошибка — номер без истории, нет архива, описи, очереди
  (7) служба показа     — зовёт ту же склейку; одна реализация; выдача Mirror.prehistory == read_history
  (8) до и после        — случайные миры: новая склейка == дословная копия прежней (f8f65b3)

Мутанты: WA_HISTORY_SRC=<каталог> ставит копию модуля впереди дерева.
"""

import ast
import base64
import hashlib
import json
import logging
import os
import random
import re
import sqlite3
import sys
import tempfile
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
if os.environ.get("WA_HISTORY_SRC"):
    sys.path.insert(0, os.environ["WA_HISTORY_SRC"])

import wa_history as H
import wa_webhook as W
import wa_tg_mirror as M

logging.getLogger("wa_webhook").setLevel(logging.ERROR)
logging.getLogger("wa_tg_mirror").setLevel(logging.ERROR)

res = []


def ok(cond, label):
    print(("  PASS " if cond else "  FAIL ") + label)
    res.append(bool(cond))
    return bool(cond)


TMP = tempfile.mkdtemp(prefix="wa_history_test_")
NOW0 = int(time.time())
T0 = NOW0 - 200 * 86400
N, O = "66800000011", "66800000012"
_seq, _w = [0], [0]


def wamid_of(number, key_id):
    """wamid живой формы: base64, внутри номер и key_id строками с длиной за байтом 0x18."""
    raw = (b"\x1c\x18" + bytes([len(number)]) + number.encode() + b"\x15\x02\x00\x12\x18"
           + bytes([len(key_id)]) + key_id.encode() + b"\x00")
    return "wamid." + base64.b64encode(raw).decode()


def ev(number, text=None, echo=False, history=True, typ="text", media_id=None, ts=None, wamid=None,
       caption=None):
    _w[0] += 1
    return {"from": number, "name": "", "type": typ, "text": text, "media_id": media_id,
            "mime": "image/jpeg" if media_id else None, "caption": caption,
            "media_note": "no_file" if typ == "media_placeholder" else None,
            "ts": ts if ts is not None else NOW0, "echo": echo, "history": history,
            "wamid": wamid or "wamid.H%05d" % _w[0], "raw": {}}


def world(arch=(), files=None, manifest=True, events=()):
    """→ env: queue_db, archive_db, archive_media, archive_manifest (выдуманные, во временном)."""
    _seq[0] += 1
    d = os.path.join(TMP, "w%d" % _seq[0])
    os.makedirs(os.path.join(d, "arch", "media"))
    q = W.WAQueueDB(os.path.join(d, "wa_queue.db"))
    if events:
        q.enqueue(list(events))
    env = {"queue_db": q.db_path, "archive_db": os.path.join(d, "arch", "wa_archive.db"),
           "archive_media": os.path.join(d, "arch", "media"),
           "archive_manifest": os.path.join(d, "arch", "media_manifest.jsonl"),
           "state_db": os.path.join(d, "wa_tg_mirror.db"), "media_dir": os.path.join(d, "wa_media"),
           "d360_key": "", "tg_token": "", "tg_chat": "", "show": False}
    if arch is not None:
        db = sqlite3.connect(env["archive_db"])
        db.executescript("""CREATE TABLE messages (id INTEGER PRIMARY KEY AUTOINCREMENT, number TEXT NOT NULL,
            ts INTEGER NOT NULL, from_me INTEGER NOT NULL, kind TEXT NOT NULL, text TEXT, caption TEXT,
            transcript TEXT, media_file TEXT, key_id TEXT NOT NULL, UNIQUE (number, key_id, from_me));""")
        db.executemany("INSERT INTO messages (number, ts, from_me, kind, text, caption, transcript, media_file, "
                       "key_id) VALUES (?,?,?,?,?,?,?,?,?)", list(arch))
        db.commit()
        db.close()
    if manifest:
        with open(env["archive_manifest"], "w", encoding="utf-8") as f:
            for key_id, (from_me, data) in (files or {}).items():
                sha = hashlib.sha256(data).hexdigest()
                with open(os.path.join(env["archive_media"], sha + ".bin"), "wb") as g:
                    g.write(data)
                f.write(json.dumps({"sha256": sha, "size": len(data), "mime": "image/jpeg",
                                    "server_file": sha + ".bin", "msg_keys": ["%s|%d" % (key_id, from_me)]}) + "\n")
    return env


def hist(env, num=N, trig=None, media_of=None):
    return H.read_history(num, env["queue_db"], env["archive_db"], env["archive_manifest"],
                          env["archive_media"], trig=trig, media_of=media_of)


# ─────────────────────────────────────────────────────────────────────────────
print("(1) без дублей")
ARCH = [(N, T0, 0, "text", "пара", None, None, None, "KPAIR00001"),
        (N, T0 + 60, 1, "text", "ответ из архива", None, None, None, "KARCH00002"),
        (O, T0, 0, "text", "чужой номер", None, None, None, "KOTHER0003")]
env = world(ARCH, events=[ev(O, "чужой в очереди", ts=T0 + 1),
                          ev(N, "пара", ts=T0, wamid=wamid_of(N, "KPAIR00001")),
                          ev(N, "только в очереди", ts=T0 + 120),
                          ev(N, "эхо с телефона", echo=True, history=False, ts=T0 + 180,
                             wamid=wamid_of("66999000000", "KECHO00004"))])
items, missing = hist(env)
texts = [it["text"] for it in items]
ok(texts.count("пара") == 1, "пара архив+очередь по key_id — один раз: %d" % texts.count("пара"))
ok(texts == ["пара", "ответ из архива", "только в очереди", "эхо с телефона"] and not missing,
   "архив + очередь без пары, чужого номера нет: %d элементов" % len(items))
ok([it["key"] for it in items][0] == "a:KPAIR00001:0", "из пары остаётся запись архива")
rows = H.queue_rows(env["queue_db"], N)
arch = H.read_archive(env["archive_db"], N)[0]
twice = H.merge(arch + arch, rows + rows)
ok([it["key"] for it in twice] == [it["key"] for it in items],
   "повтор строки очереди (wamid) и записи архива (key_id, сторона) — один раз: %d" % len(twice))
ok(len({it["key"] for it in items}) == len(items), "ключи элементов уникальны")

# ─────────────────────────────────────────────────────────────────────────────
print("\n(2) порядок по времени")
ARCH2 = [(N, T0 + 300, 0, "text", "а3", None, None, None, "KORD000003"),
         (N, T0 + 100, 0, "text", "а1", None, None, None, "KORD000001"),
         (N, T0 + 200, 1, "text", "а2", None, None, None, "KORD000002")]
env = world(ARCH2, events=[ev(N, "о4", ts=T0 + 400), ev(N, "о0", ts=T0 + 50), ev(N, "о2", ts=T0 + 250),
                           ev(N, "о-равно", ts=T0 + 100)])
items, _ = hist(env)
ok([it["text"] for it in items] == ["о0", "а1", "о-равно", "а2", "о2", "а3", "о4"],
   "архив и очередь слиты по времени: %s" % [it["text"] for it in items])
ok([it["ts"] for it in items] == sorted(it["ts"] for it in items), "время не убывает")
ok(items[1]["key"].startswith("a:") and items[2]["key"].startswith("wamid."),
   "при равном времени — по ключу (запись архива раньше строки очереди)")
env = world([], events=[ev(N, "позже по времени, раньше по id", ts=T0 + 999), ev(N, "раньше", ts=T0 + 1)])
ok([it["text"] for it in hist(env)[0]] == ["раньше", "позже по времени, раньше по id"],
   "очередь — по времени сообщения, а не по id")
env = world([], events=[ev(N, "время сообщения пусто", ts=0)])
ok(hist(env)[0][0]["ts"] > 0, "время сообщения пусто → время постановки в очередь")

# ─────────────────────────────────────────────────────────────────────────────
print("\n(3) медиа словом")
ARCH3 = [(N, T0, 1, "image", None, "подпись фото", None, "IMG-1.jpg", "KMED000001"),
         (N, T0 + 10, 0, "audio", None, None, "привет голосом", "PTT-1.opus", "KMED000002"),
         (N, T0 + 20, 0, "location", "Раваи", None, None, None, "KMED000003"),
         (N, T0 + 30, 0, "weird_kind", None, None, None, None, "KMED000004")]
env = world(ARCH3, files={"KMED000001": (1, b"IMG")},
            events=[ev(N, typ="image", media_id="MQ1", ts=T0 + 40, caption="фото очереди"),
                    ev(N, typ="media_placeholder", ts=T0 + 50), ev(N, typ="voice", media_id="MQ2", ts=T0 + 60),
                    ev(N, typ="interactive", ts=T0 + 70)])
items, _ = hist(env)
lines = [H.model_line(it) for it in items]
ok(lines[0] == "%s · мы: [фото] подпись фото" % H.pk_full(T0), "модель: архивное фото словом с подписью: %r" % lines[0][17:])
ok(lines[1].endswith("клиент: [аудио] (расшифровка: привет голосом)"), "голосовое архива — словом и расшифровкой")
ok(lines[2].endswith("клиент: [геоточка] Раваи") and lines[3].endswith("клиент: [сообщение неизвестного вида]"),
   "геоточка словом, неизвестный вид — «сообщение неизвестного вида» (WAMIRRRU0210: не именем)")
ok(lines[4].endswith("клиент: [фото] фото очереди") and lines[5].endswith("клиент: [медиа]")
   and lines[6].endswith("клиент: [голосовое]") and lines[7].endswith("клиент: [ответ кнопкой]"),
   "очередь: фото, заглушка, голосовое — словом; вид без текста — русским словом (WAMIRRRU0210)")
ok(" · " in lines[0] and all(ln.split(" · ")[0] == H.pk_full(it["ts"]) for ln, it in zip(lines, items)),
   "строка модели «ДД.ММ.ГГГГ ЧЧ:ММ · клиент|мы: текст»")
ok(H.item_line(items[0]).endswith("мы: [фото — на сервере] подпись фото")
   and H.item_line(items[4]).endswith("клиент: [фото — файла нет] фото очереди"),
   "строка темы: «на сервере» по описи, «файла нет» без файла")
text, chars = H.model_view(items)
ok(chars == len(text) == sum(map(len, lines)) + len(lines) - 1 and text.count("\n") == len(items) - 1,
   "объём представления в символах: %d" % chars)
mf = os.path.join(TMP, "media_ok.jpg")
open(mf, "wb").write(b"J")
of = {items[4]["key"]: (H.MEDIA_OK, mf, 1, "image/jpeg", "")}
ok(hist(env, media_of=of.get)[0][4]["file"] == (mf, 1, "image/jpeg") and items[4]["file"] is None,
   "файл очереди — только из описи службы показа (state ok и файл есть); без неё — неизвестен")
ok(hist(env, media_of={items[4]["key"]: ("fail", mf, 1, "image/jpeg", "x")}.get)[0][4]["file"] is None
   and hist(env, media_of={items[4]["key"]: (H.MEDIA_OK, mf + ".нет", 1, "image/jpeg", "")}.get)[0][4]["file"] is None,
   "отказ скачивания или файла нет на диске — файла нет")
ok(H.arch_item(ARCH3[0][1:], {"KMED000001|1": (os.path.join(TMP, "нет.jpg"), 1, "image/jpeg")})["file"] is None
   and H.arch_item(ARCH3[0][1:], {"KMED000001|0": (mf, 1, "image/jpeg")})["file"] is None
   and H.arch_item(ARCH3[0][1:], {"KMED000001|1": (mf, 1, "image/jpeg")})["file"] == (mf, 1, "image/jpeg"),
   "архив: запись описи без файла на диске или другой стороны — файла нет")
ok(M.M_OK == H.MEDIA_OK, "состояние «скачан» совпадает со службой показа")

# ─────────────────────────────────────────────────────────────────────────────
print("\n(4) «новое»: строка темы и её архивная пара")
env = world([(N, T0, 0, "text", "старое", None, None, None, "KNEW000001"),
             (N, T0 + 60, 0, "text", "живое из архива", None, None, None, "KNEW000002")],
            events=[ev(N, "до темы", ts=T0 + 30),
                    ev(N, "живое из архива", history=False, ts=T0 + 60, wamid=wamid_of(N, "KNEW000002")),
                    ev(N, "после темы", history=False, ts=T0 + 90)])
rows = H.queue_rows(env["queue_db"], N)
trig = rows[1]["id"]
items, _ = hist(env, trig=trig)
ok([it["text"] for it in items] == ["старое", "до темы"], "trig: строки с id ≥ trig и их архивная пара не идут: %s"
   % [it["text"] for it in items])
ok([it["text"] for it in hist(env, trig=trig + 1)[0]] == ["старое", "до темы", "живое из архива"],
   "строка id = trig−1 — история (граница ровно ≥)")
ok(len(hist(env)[0]) == 4, "trig=None — вся очередь история (агент): 4")

# ─────────────────────────────────────────────────────────────────────────────
print("\n(5) функция не пишет ни в одну базу")
env = world(ARCH3, files={"KMED000001": (1, b"IMG")}, events=[ev(N, "раз", ts=T0), ev(N, "два", ts=T0 + 1)])


def snap(env):
    out = {}
    for d in {os.path.dirname(env["queue_db"]), os.path.dirname(env["archive_db"])}:
        for f in sorted(os.listdir(d)):
            p = os.path.join(d, f)
            if os.path.isfile(p):
                st = os.stat(p)
                out[p] = (hashlib.sha256(open(p, "rb").read()).hexdigest(), st.st_size, st.st_mtime_ns)
    return out


before = snap(env)
calls, real_connect = [], sqlite3.connect


def spy(*a, **kw):
    calls.append((a, kw))
    return real_connect(*a, **kw)


H.sqlite3.connect = spy
try:
    for _ in range(3):
        hist(env)
        hist(env, num="66899999999")
finally:
    H.sqlite3.connect = real_connect
ok(snap(env) == before, "файлы очереди, архива и описи побайтно и по mtime те же, новых файлов нет (%d)" % len(before))
ok(calls and all("?mode=ro" in a[0] and kw.get("uri") is True for a, kw in calls),
   "все соединения — mode=ro (%d из %d)" % (sum(1 for a, kw in calls if "?mode=ro" in a[0]), len(calls)))
src = open(H.__file__, encoding="utf-8").read()
code = "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith("#"))
# SQL-слова записи — заглавными, как пишет весь контур (вид архива «deleted» — данные, не SQL)
sql_words = re.findall(r"\b(INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|REPLACE|ATTACH|VACUUM)\b", code)
ok(not sql_words
   and ".commit(" not in code and '"w"' not in code and "'w'" not in code and '"a"' not in code,
   "в исходнике нет записи: INSERT/UPDATE/DELETE/CREATE/ALTER/DROP, commit, открытия файла на запись")
mods = {n.names[0].name if isinstance(n, ast.Import) else n.module
        for n in ast.walk(ast.parse(src)) if isinstance(n, (ast.Import, ast.ImportFrom))}
ok(mods == {"base64", "json", "os", "sqlite3", "time", "wa_kind"}, "импорты без сети и журнала: %s" % sorted(mods))
ro = os.path.join(TMP, "ro_only")
os.makedirs(ro)
open(os.path.join(ro, "x.db"), "wb").close()
try:
    c = H._ro(os.path.join(ro, "x.db"))
    try:
        c.execute("CREATE TABLE t (a)")
        wrote = True
    except sqlite3.OperationalError:
        wrote = False
    c.close()
except sqlite3.Error:
    wrote = False
ok(not wrote, "соединение модуля запись отвергает (readonly)")

# ─────────────────────────────────────────────────────────────────────────────
print("\n(6) номер без истории — пусто, не ошибка")
env = world(ARCH, events=[ev(N, "есть", ts=T0)])
ok(hist(env, num="66899999999") == ([], []), "номера нет нигде, всё читается → ([], [])")
ok(H.model_view([]) == ("", 0) and H.head_text([], []) == "раньше не писал", "пусто → «», 0 и «раньше не писал»")
env = world(None, manifest=False, events=[ev(N, "только очередь", ts=T0)])
items, missing = hist(env)
ok([it["text"] for it in items] == ["только очередь"]
   and missing == ["архива копии телефона нет", "описи медиа архива нет"],
   "нет архива и описи — очередь есть, причины названы: %s" % missing)
items, missing = H.read_history(N, os.path.join(TMP, "нет", "q.db"), os.path.join(TMP, "нет", "a.db"),
                                os.path.join(TMP, "нет", "m.jsonl"), "")
ok(items == [] and missing == ["очереди нет", "архива копии телефона нет", "описи медиа архива нет"],
   "ничего нет — пусто и три причины, не исключение")
bad = world(None, manifest=False)
open(bad["archive_db"], "wb").write(b"not a database" * 100)
open(bad["archive_manifest"], "w").write("{битая строка\n")
items, missing = hist(bad)
ok(items == [] and missing and missing[0].startswith("архив не читается")
   and missing[1].startswith("опись медиа архива не читается"), "битый архив и опись — причины, не падение")

# ─────────────────────────────────────────────────────────────────────────────
print("\n(7) служба показа зовёт ту же склейку")
env = world(ARCH3 + [(N, T0 + 500, 0, "text", "пара", None, None, None, "KPAIR00001")],
            files={"KMED000001": (1, b"IMG")},
            events=[ev(N, "пара", ts=T0 + 500, wamid=wamid_of(N, "KPAIR00001")), ev(N, "очередь", ts=T0 + 600),
                    ev(N, "read", typ="status", echo=True, ts=T0 + 601),
                    ev(N, "👍", typ="reaction", history=False, ts=T0 + 602)])
m = M.Mirror(env, http=lambda *a: (_ for _ in ()).throw(AssertionError("сеть")), clock=lambda: NOW0,
             sleep=lambda s: None, disk_free=lambda p: 10 ** 12)
mrows = [r for r in m._rows("from_number=? ORDER BY id", (N,)) if not M._is_receipt(r) and not M._is_reaction(r)]
ok([r["id"] for r in mrows] == [r["id"] for r in H.queue_rows(env["queue_db"], N)],
   "реплики очереди — те же строки, что берёт служба показа (без квитанций и реакций)")
merges, real_merge = [], H.merge


def spy_merge(*a, **kw):
    merges.append(1)
    return real_merge(*a, **kw)


H.merge = spy_merge
try:
    trig = max(r["id"] for r in mrows) + 1
    got = m.prehistory(N, mrows, trig)
finally:
    H.merge = real_merge
ok(merges == [1], "Mirror.prehistory зовёт wa_history.merge: %d раз" % len(merges))
ok(got == hist(env, media_of=m._media_of), "выдача службы показа == read_history агента (элементы и «чего нет»)")
msrc = open(M.__file__, encoding="utf-8").read()
ok(not hasattr(M.Mirror, "_arch_item") and not hasattr(M.Mirror, "_queue_item")
   and "def parse_wamid" not in msrc and "def item_line" not in msrc and "def head_text" not in msrc
   and M.parse_wamid is H.parse_wamid and M.head_text is H.head_text and M.item_line is H.item_line
   and M.who_of is H.who_of, "реализация одна: элементы, строки и wamid — только в wa_history")

# ─────────────────────────────────────────────────────────────────────────────
print("\n(8) до и после: новая склейка == дословная копия прежней (f8f65b3), латиница вида → русское слово")
# Прежний код службы показа (wa_tg_mirror.py у f8f65b3: parse_wamid, _arch_item, _queue_item,
# prehistory) — дословно, только self.* заменены параметрами. Оракул, а не реализация: не править.
_O_MEDIA_WORD = {"image": "фото", "video": "видео", "audio": "аудио", "voice": "голосовое",
                 "document": "документ", "sticker": "стикер"}
_O_ARCH_MEDIA = {"image": "фото", "video": "видео", "audio": "аудио", "document": "документ",
                 "sticker": "стикер", "gif": "гиф", "view_once_image": "одноразовое фото",
                 "view_once_video": "одноразовое видео"}
_O_ARCH_OTHER = {"location": "геоточка", "live_location": "геоточка", "contact": "контакт",
                 "contacts": "контакты", "deleted": "удалено", "waiting": "ожидает"}


def o_parse_wamid(w):
    if not w or not str(w).startswith("wamid."):
        return None, None
    b64 = str(w)[6:]
    try:
        raw = base64.b64decode(b64 + "=" * (-len(b64) % 4))
    except Exception:
        return None, None
    strs, i = [], 0
    while i < len(raw) - 1:
        if raw[i] == 0x18:
            n = raw[i + 1]
            s = raw[i + 2:i + 2 + n]
            if len(s) == n and n >= 5 and all(32 < c < 127 for c in s):
                strs.append(s.decode())
                i += 2 + n
                continue
        i += 1
    num = next((s for s in strs if s.isdigit()), None)
    return num, next((s for s in strs if s != num), None)


def o_who_of(row):
    import wa_kind
    kind = wa_kind.kind_of(row["msg_type"], row["echo"], row["history"])
    if kind == wa_kind.KIND_REACTION:
        return "мы" if int(row["echo"] or 0) else "клиент"
    if kind == wa_kind.KIND_ECHO:
        return "мы"
    if kind in (wa_kind.KIND_INBOUND, wa_kind.KIND_HISTORY):
        return "клиент"
    return "?"


def o_arch_item(a, man):
    ts, from_me, kind, text, caption, transcript, media_file, key_id = a
    word = _O_ARCH_MEDIA.get(kind) or (kind if media_file else None)
    f = None
    if word:
        hit = man.get("%s|%d" % (key_id, int(from_me)))
        if hit and os.path.exists(hit[0]):
            f = hit
        text = caption or ""
        if transcript:
            text += (" " if text else "") + "(расшифровка: %s)" % transcript
    elif kind in _O_ARCH_OTHER:
        text = "[%s]" % _O_ARCH_OTHER[kind] + (" " + text if text else "")
    elif not text:
        text = "[%s]" % kind
    return {"key": "a:%s:%d" % (key_id, int(from_me)), "ts": int(ts),
            "who": "мы" if int(from_me) else "клиент", "text": text, "word": word, "file": f}


def o_queue_item(r, media_of):
    t = r["msg_type"] or ""
    word, f, text = None, None, r["text"] or ""
    rk = r["wamid"] or ("row:%d" % r["id"])
    if t == "media_placeholder":
        word, text = "медиа", ""
    elif t in _O_MEDIA_WORD:
        word, text = _O_MEDIA_WORD[t], r["caption"] or ""
        md = media_of(rk)
        if md and md[0] == "ok" and md[1] and os.path.exists(md[1]):
            f = (md[1], md[2] or 0, md[3] or "")
    elif not text:
        text = "[" + (t or "?") + "]"
    return {"key": rk, "ts": int(r["ts_msg"] or r["ts_queued"] or 0), "who": o_who_of(r),
            "text": text, "word": word, "file": f}


def o_prehistory(arch, rows, trig, man, media_of):
    arch_keys = {a[7] for a in arch}
    taken, items = set(), []
    for r in rows:
        k = o_parse_wamid(r["wamid"])[1]
        paired = k is not None and k in arch_keys
        if r["id"] >= trig:
            if paired:
                taken.add(k)
        elif not paired:
            items.append(o_queue_item(r, media_of))
    items += [o_arch_item(a, man) for a in arch if a[7] not in taken]
    items.sort(key=lambda it: (it["ts"], it["key"]))
    return items


# WAMIRRRU0210 (02.10): намеренные отличия от оракула — латиница вида в скобках стала русским словом,
# сторона неопознанного вида — по echo вместо «?». Оракул не правится; его выдача переводится o_ru и только ею.
_O_RU_TEXT = {"[weird]": "[сообщение неизвестного вида]", "[text]": "[пустое сообщение]",
              "[interactive]": "[ответ кнопкой]"}
_O_WORDS = set(_O_ARCH_MEDIA.values()) | set(_O_MEDIA_WORD.values()) | {"медиа"}


def o_ru(it, rows_by_key):
    it = dict(it)
    if it["word"] is not None and it["word"] not in _O_WORDS:
        it["word"] = "файл"                    # медиа вида вне словаря: было именем вида
    it["text"] = _O_RU_TEXT.get(it["text"], it["text"])
    r = rows_by_key.get(it["key"])
    if it["who"] == "?" and r is not None and r["echo"] in (0, 1):
        it["who"] = "мы" if r["echo"] else "клиент"   # неопознанный вид: сторона по echo, а не «?»
    return it


KINDS = ["text", "text", "text", "image", "audio", "document", "location", "deleted", "sticker", "weird"]
QTYPES = ["text", "text", "text", "image", "voice", "media_placeholder", "status", "reaction", "interactive"]
rnd = random.Random(20261001)
diff, worlds, n_items, n_pairs = [], 0, 0, 0
mfile = os.path.join(TMP, "media_rand.jpg")
open(mfile, "wb").write(b"R")
for w in range(120):
    keys = ["KR%03d%05d" % (w, i) for i in range(rnd.randint(0, 14))]
    arch, files = [], {}
    for i, k in enumerate(keys):
        kind = rnd.choice(KINDS)
        fm = rnd.randint(0, 1)
        arch.append((N, T0 + rnd.randint(0, 50) * 60, fm, kind, rnd.choice([None, "", "т%d" % i]),
                     rnd.choice([None, "п%d" % i]), rnd.choice([None, None, "р%d" % i]),
                     rnd.choice([None, "F%d.jpg" % i]), k))
        if kind in ("image", "document", "sticker") and rnd.random() < 0.5:
            files[k] = (fm, b"x%d" % i)
    evs = []
    for i in range(rnd.randint(0, 14)):
        typ = rnd.choice(QTYPES)
        pair = keys and rnd.random() < 0.4
        evs.append(ev(N, rnd.choice([None, "", "о%d" % i]), echo=rnd.random() < 0.3,
                      history=rnd.random() < 0.7, typ=typ, media_id=("M%d" % i) if typ in ("image", "voice") else None,
                      ts=rnd.choice([0, T0 + rnd.randint(0, 50) * 60]), caption=rnd.choice([None, "к%d" % i]),
                      wamid=wamid_of(N, rnd.choice(keys)) if pair else None))
        n_pairs += bool(pair)
    evs.append(ev(O, "чужой", ts=T0))
    env = world(arch, files, events=evs)
    rows = H.queue_rows(env["queue_db"], N)
    man = H.read_manifest(env["archive_manifest"], env["archive_media"])[0]
    arch_db = H.read_archive(env["archive_db"], N)[0]
    media = {r["wamid"]: ("ok", mfile, 1, "image/jpeg", "") for r in rows if r["msg_type"] == "image"}
    ids = [r["id"] for r in rows]
    for trig in [None] + ([rnd.choice(ids)] if ids else []):
        old = [o_ru(it, {H.row_key(r): r for r in rows}) for it in
               o_prehistory(arch_db, rows, (max(ids) + 1 if ids else 1) if trig is None else trig, man, media.get)]
        new = H.merge(arch_db, rows, trig, man, media.get)
        worlds += 1
        n_items += len(new)
        if new != old:
            diff.append(w)
ok(not diff and worlds >= 120, "миров %d, элементов %d, пар архив+очередь %d: расхождений %d"
   % (worlds, n_items, n_pairs, len(diff)))

print("\nИтог: %d/%d PASS" % (sum(res), len(res)))
fails = sum(1 for r in res if not r)
if fails:
    print("FAIL: %d тест(а/ов) не прошли" % fails)
    sys.exit(1)
