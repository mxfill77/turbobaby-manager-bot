#!/usr/bin/env python3
"""WA HISTORY — история клиента WhatsApp: архив копии телефона + строки очереди, одна склейка (01.10.2026).

Склейка вынесена из службы показа (`wa_tg_mirror.Mirror.prehistory`, WAHISTMOD0110). Её зовут служба
показа (тема клиента: шапка, файл истории, последние сообщения) и агент WhatsApp (контекст модели),
поэтому сотрудник в теме и модель читают одну и ту же историю.

Правила склейки (каждое — тест и мутант, tests/test_wa_history.py):
  • архив — все записи номера; строка очереди — только без пары в архиве. Пара — key_id из wamid
    строки (номер — from_number: у эха номер внутри wamid другой);
  • строка очереди с id ≥ trig — «новое» (его покажет живая лента темы): в историю не идёт, и её
    архивная пара тоже. trig=None — вся очередь история (агент);
  • дублей нет: строка очереди — один раз на wamid, запись архива — один раз на key_id и сторону;
  • квитанции и реакции — не реплики: `queue_rows` их отсекает (служба показа — сама, тем же wa_kind);
  • порядок — по времени, при равном времени — по ключу;
  • вид без текста и без файла — русским словом (`kind_word`, WAMIRRRU0210): латиницы в скобках нет
    ни в теме, ни в файле истории, ни в строке модели; вид вне словаря — «сообщение неизвестного вида»,
    а его имя уходит вызывающему (служба показа пишет строку журнала — здесь журнала нет);
  • правка с телефона (WAPHONEEDIT0210, `apply_edits`): цель в истории есть — у неё последний текст
    с пометкой «(изменено)», правка строкой не идёт; цели нет — правка своей строкой с пометкой.

Только чтение: очередь и архив открываются mode=ro, своего состояния нет, журнала нет, сети нет.
Тексты, номера и имена клиентов наружу не идут — функции отдают их только вызывающему.
"""

import base64
import json
import os
import sqlite3
import time

import wa_kind

PHUKET_OFFSET = 7 * 3600
SERIES_GAP    = 30 * 86400     # перерыв больше 30 дней — новая серия обращений

MEDIA_PLACEHOLDER = "media_placeholder"
MEDIA_OK = "ok"                # файл скачан — состояние описи службы показа (wa_tg_mirror.M_OK)
# виды строк очереди с медиа (msg_type) → слово
MEDIA_WORD = {"image": "фото", "video": "видео", "audio": "аудио", "voice": "голосовое",
              "document": "документ", "sticker": "стикер"}
# виды архива (build_archive.py → messages.kind): медиа — со словом «на сервере / файла нет»
ARCH_MEDIA = {"image": "фото", "video": "видео", "audio": "аудио", "document": "документ",
              "sticker": "стикер", "gif": "гиф", "view_once_image": "одноразовое фото",
              "view_once_video": "одноразовое видео"}
ARCH_OTHER = {"location": "геоточка", "live_location": "геоточка", "contact": "контакт",
              "contacts": "контакты", "deleted": "удалено", "waiting": "ожидает"}
# Вид без текста и без файла (строка очереди — msg_type, запись архива — kind) → русское слово
# (WAMIRRRU0210, владелец 01.10: «надо, чтобы всё было обычно»). До 02.10 такой вид показывался
# своим именем в скобках: «[revoke]», «[unsupported]», «[edit]», «[code_99]».
KIND_WORD = {
    "text":          "пустое сообщение",
    "unsupported":   "неподдерживаемое сообщение — смотреть в телефоне",
    "revoke":        "сообщение удалено с телефона",
    "edit":          "сообщение изменено",
    "errors":        "сообщение не передано — смотреть в телефоне",
    "contacts":      "контакт",
    "contact":       "контакт",
    "location":      "геоточка",
    "live_location": "геоточка",
    "interactive":   "ответ кнопкой",
    "button":        "ответ кнопкой",
    "order":         "заказ из каталога",
    "system":        "служебное сообщение",
    "reaction":      "реакция",
    "status":        "квитанция",
    "deleted":       "удалено",
    "waiting":       "ожидает",
}
UNKNOWN_WORD = "сообщение неизвестного вида"
FILE_WORD = "файл"             # медиа вида вне словаря медиа (архив: code_<N> с файлом)

# колонки очереди wa_inbox, которые читают склейка и служба показа
QCOLS = ("id", "ts_queued", "from_number", "name", "msg_type", "text", "media_id", "mime",
         "caption", "media_note", "ts_msg", "echo", "history", "wamid", "react_to", "edit_to", "edit_text")

# Правка с телефона (WAPHONEEDIT0210): строка вида edit несёт wamid цели (edit_to) и новый текст
# (edit_text). В истории у цели — последний текст с пометкой; сама правка строкой тогда не идёт.
EDIT_TYPE = "edit"
EDIT_MARK = "(изменено)"
ARCH_COLS = "ts, from_me, kind, text, caption, transcript, media_file, key_id"


def pk_full(ts) -> str:
    return time.strftime("%d.%m.%Y %H:%M", time.gmtime(int(ts or 0) + PHUKET_OFFSET))


def pk_date(ts) -> str:
    return time.strftime("%d.%m.%Y", time.gmtime(int(ts or 0) + PHUKET_OFFSET))


def parse_wamid(w):
    """wamid → (номер, key_id). После «wamid.» — base64, внутри строки с длиной за байтом 0x18:
    номер и key_id (WAARCHIVE0110 П3: 5 347 из 5 347). Не раскрылся → (None, None)."""
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


def who_of(row) -> str:
    kind = wa_kind.kind_of(row["msg_type"], row["echo"], row["history"])
    if kind == wa_kind.KIND_REACTION:
        return "мы" if int(row["echo"] or 0) else "клиент"
    if kind == wa_kind.KIND_ECHO:
        return "мы"
    if kind in (wa_kind.KIND_INBOUND, wa_kind.KIND_HISTORY):
        return "клиент"
    if row["echo"] in (0, 1):
        return "мы" if row["echo"] else "клиент"     # вид не опознан, сторона записана (unsupported клиента)
    return "?"


def kind_word(kind, unknown=None) -> str:
    """Вид без текста → русское слово. Вне словаря — UNKNOWN_WORD, а имя вида — в unknown (set),
    если вызывающий его дал: строку журнала пишет он."""
    word = KIND_WORD.get(kind or "")
    if word is None:
        if unknown is not None:
            unknown.add(kind or "")
        word = UNKNOWN_WORD
    return word


def row_key(row) -> str:
    return row["wamid"] or ("row:%d" % row["id"])


def col(row, name):
    """Колонка строки или None: строка из очереди до правки входа (или словарь теста) её не несёт."""
    try:
        return row[name]
    except (KeyError, IndexError):
        return None


def edit_of(row):
    """Строка очереди → (wamid цели, новый текст) для правки · (None, None) — не правка или полей нет."""
    if (row["msg_type"] or "") != EDIT_TYPE:
        return None, None
    return col(row, "edit_to") or None, col(row, "edit_text") or None


def edited(row, new):
    """Копия строки цели с новым текстом: у медиа — подпись, у прочих — текст. Её показывают те же
    функции, что показали цель (тема, хвост, файл истории), поэтому вид строки не расходится."""
    d = {k: row[k] for k in row.keys()}
    if (d.get("msg_type") or "") in MEDIA_WORD or d.get("msg_type") == MEDIA_PLACEHOLDER:
        d["caption"] = new
    else:
        d["text"] = new
    return d


def is_utterance(row) -> bool:
    """Реплика — всё, кроме квитанции и реакции (они в историю не идут)."""
    return wa_kind.kind_of(row["msg_type"], row["echo"], row["history"]) not in (
        wa_kind.KIND_RECEIPT, wa_kind.KIND_REACTION)


# ── элементы истории ─────────────────────────────────────────────────────────────────────
# элемент: {"key", "ts", "who" (клиент|мы|?), "text", "word" (медиа словом | None),
#           "file" ((путь, размер, mime) — файл на сервере | None)}

def arch_item(a, man, unknown=None):
    """Запись архива (ARCH_COLS) → элемент. man — опись медиа {«key_id|from_me»: (путь, размер, mime)}.
    unknown — set, куда ложатся имена видов вне словарей (строку журнала пишет вызывающий)."""
    ts, from_me, kind, text, caption, transcript, media_file, key_id = a
    word = ARCH_MEDIA.get(kind)
    if not word and media_file:
        word = FILE_WORD                          # медиа неизвестного вида — «файл», имя вида — в журнал
        if unknown is not None:
            unknown.add(kind or "")
    f = None
    if word:
        hit = man.get("%s|%d" % (key_id, int(from_me)))
        if hit and os.path.exists(hit[0]):
            f = hit
        text = caption or ""
        if transcript:
            text += (" " if text else "") + "(расшифровка: %s)" % transcript
    elif kind in ARCH_OTHER:
        text = "[%s]" % ARCH_OTHER[kind] + (" " + text if text else "")
    elif not text:
        text = "[%s]" % kind_word(kind, unknown)
    return {"key": "a:%s:%d" % (key_id, int(from_me)), "ts": int(ts),
            "who": "мы" if int(from_me) else "клиент", "text": text, "word": word, "file": f}


def queue_item(r, media_of=None, unknown=None):
    """Строка очереди → элемент. media_of(ключ) → (state, path, size, mime, code) | None — опись
    скачанных файлов службы показа; нет её (агент) — файл неизвестен, слово медиа остаётся.
    unknown — set для имён видов вне словаря (см. kind_word)."""
    t = r["msg_type"] or ""
    word, f, text = None, None, r["text"] or ""
    if t == MEDIA_PLACEHOLDER:
        word, text = "медиа", ""
    elif t in MEDIA_WORD:
        word, text = MEDIA_WORD[t], r["caption"] or ""
        md = media_of(row_key(r)) if media_of else None
        if md and md[0] == MEDIA_OK and md[1] and os.path.exists(md[1]):
            f = (md[1], md[2] or 0, md[3] or "")
    elif not text:
        text = "[%s]" % kind_word(t, unknown)
    return {"key": row_key(r), "ts": int(r["ts_msg"] or r["ts_queued"] or 0), "who": who_of(r),
            "text": text, "word": word, "file": f}


def merge(arch, rows, trig=None, man=None, media_of=None, unknown=None):
    """Склейка → элементы по времени. arch — записи архива номера (ARCH_COLS), rows — реплики
    очереди номера по id. Строка очереди с id ≥ trig — «новое»: не идёт сама и снимает свою
    архивную пару; trig=None — вся очередь история. Дублей нет ни одной дорогой. unknown — set,
    куда ложатся имена видов вне словаря (служба показа пишет по ним строку журнала)."""
    man = man or {}
    arch_keys = {a[7] for a in arch}
    taken, seen, items, edits = set(), set(), [], []
    for r in rows:
        k = parse_wamid(r["wamid"])[1]
        paired = k is not None and k in arch_keys
        if trig is not None and r["id"] >= trig:
            if paired:
                taken.add(k)
            continue
        if (r["msg_type"] or "") == EDIT_TYPE:
            edits.append((r, k if paired else None))
        if not paired and row_key(r) not in seen:
            seen.add(row_key(r))
            items.append(queue_item(r, media_of, unknown))
    for a in arch:
        if a[7] in taken:
            continue
        it = arch_item(a, man, unknown)
        if it["key"] not in seen:
            seen.add(it["key"])
            items.append(it)
    if edits:
        items = apply_edits(items, edits)
    items.sort(key=lambda it: (it["ts"], it["key"]))
    return items


def apply_edits(items, edits):
    """Правки истории (WAPHONEEDIT0210). Цель есть в истории и новый текст есть — у цели последний
    текст (по времени правки, затем по id) с пометкой «(изменено)», а сама правка строкой не идёт.
    Иначе правка остаётся своей строкой: новым текстом с пометкой; без нового текста — словом, как до
    02.10; запись архива, парная правке (живой досинхрон: 98 из 98 — текстом правки), — с пометкой."""
    by_key = {it["key"]: it for it in items}
    by_kid = {}
    for it in items:
        if it["key"].startswith("a:"):
            by_kid.setdefault(it["key"][2:].rsplit(":", 1)[0], it)
    last, drop = {}, set()
    for r, pk in edits:
        target, new = edit_of(r)
        own = by_key.get(row_key(r)) or (by_kid.get(pk) if pk else None)
        tit = (by_key.get(target) or by_kid.get(parse_wamid(target)[1] or "")) if target else None
        if tit is not None and new and tit is not own:
            stamp = (int(r["ts_msg"] or r["ts_queued"] or 0), r["id"])
            if tit["key"] not in last or stamp > last[tit["key"]][0]:
                last[tit["key"]] = (stamp, new)
            if own is not None:
                drop.add(own["key"])
        elif own is not None:
            if own["key"] == row_key(r):
                if new:
                    own["text"] = new + " " + EDIT_MARK
            elif not (own["text"] or "").endswith(EDIT_MARK):
                own["text"] = ((own["text"] or "") + " " + EDIT_MARK).strip()
    for key, (_stamp, new) in last.items():
        by_key[key]["text"] = new + " " + EDIT_MARK
    return [it for it in items if it["key"] not in drop]


# ── чтение: только mode=ro ─────────────────────────────────────────────────────────────────

def _ro(path):
    return sqlite3.connect("file:%s?mode=ro" % os.path.abspath(path).replace("\\", "/"),
                           uri=True, timeout=10)


def archive_select(conn, num):
    """Записи архива номера по соединению вызывающего (служба показа держит своё)."""
    return conn.execute("SELECT " + ARCH_COLS + " FROM messages WHERE number=? ORDER BY ts, id",
                        (num,)).fetchall()


def read_archive(path, num):
    """→ (записи номера, причина «чего нет» | ""). Нет или не читается — причина, а не падение."""
    if not path or not os.path.exists(path):
        return [], "архива копии телефона нет"
    try:
        conn = _ro(path)
    except sqlite3.Error as e:
        return [], "архив не читается (%s)" % type(e).__name__
    try:
        return archive_select(conn, num), ""
    except sqlite3.Error as e:
        return [], "архив не читается (%s)" % type(e).__name__
    finally:
        conn.close()


def read_manifest(path, media_dir):
    """Опись медиа архива → ({«key_id|from_me»: (путь, размер, mime)}, "") · (None, причина)."""
    if not path or not os.path.exists(path):
        return None, "описи медиа архива нет"
    out = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                rec = json.loads(line)
                fpath = os.path.join(media_dir or "", os.path.basename(rec["server_file"]))
                for k in rec.get("msg_keys") or ():
                    out[k] = (fpath, int(rec.get("size") or 0), rec.get("mime") or "")
    except (OSError, ValueError, KeyError, TypeError) as e:
        return None, "опись медиа архива не читается (%s)" % type(e).__name__
    return out, ""


def queue_rows(queue_db, num):
    """Реплики номера из очереди (без квитанций и реакций), по id. Колонок ещё нет — NULL."""
    conn = _ro(queue_db)
    conn.row_factory = sqlite3.Row
    try:
        have = {r[1] for r in conn.execute("PRAGMA table_info(wa_inbox)")}
        cols = [c if c in have else "NULL AS " + c for c in QCOLS]
        rows = conn.execute("SELECT " + ", ".join(cols) + " FROM wa_inbox WHERE from_number=? "
                            "ORDER BY id", (num,)).fetchall()
    finally:
        conn.close()
    return [r for r in rows if is_utterance(r)]


def read_history(num, queue_db, archive_db, manifest="", media_dir="", trig=None, media_of=None):
    """История номера (агент) → (элементы по времени, чего нет). Номер без истории — ([], …), не
    ошибка; очередь, архив или опись не читаются — причина в списке, а не исключение."""
    missing = []
    try:
        rows = queue_rows(queue_db, num) if queue_db and os.path.exists(queue_db) else None
    except sqlite3.Error as e:
        rows = None
        missing.append("очередь не читается (%s)" % type(e).__name__)
    if rows is None and not missing:
        missing.append("очереди нет")
    arch, why = read_archive(archive_db, num)
    if why:
        missing.append(why)
    man, why_m = read_manifest(manifest, media_dir)
    if man is None:
        missing.append(why_m)
    return merge(arch, rows or [], trig, man or {}, media_of), missing


# ── представление ──────────────────────────────────────────────────────────────────────────

def item_line(it) -> str:
    """Строка предыстории темы: «ДД.ММ.ГГГГ ЧЧ:ММ клиент|мы: …»; медиа — «[вид — на сервере|файла нет]»."""
    body = it["text"] or ""
    if it["word"]:
        body = "[%s — %s]" % (it["word"], "на сервере" if it["file"] else "файла нет") \
            + (" " + body if body else "")
    return "%s %s: %s" % (pk_full(it["ts"]), it["who"], body or "[пусто]")


def head_text(items, missing) -> str:
    """Шапка темы по предыстории; missing — чего нет (архив, опись), чтобы пустое не читалось «не писал»."""
    if items:
        ts = sorted(it["ts"] for it in items)
        series = 1 + sum(1 for a, b in zip(ts, ts[1:]) if b - a > SERIES_GAP)
        s = ("писал раньше: с %s, %d сообщений (клиент %d / мы %d), серий обращений %d "
             "(перерыв больше 30 дней), последнее %s"
             % (pk_date(ts[0]), len(items), sum(1 for it in items if it["who"] == "клиент"),
                sum(1 for it in items if it["who"] == "мы"), series, pk_date(ts[-1])))
    else:
        s = "раньше не писал"
    if missing:
        s += "\n⚠️ предыстория неполная: " + "; ".join(missing)
    return s


def model_line(it) -> str:
    """Строка для модели: «ДД.ММ.ГГГГ ЧЧ:ММ · клиент|мы: текст»; медиа — словом: «[фото] подпись»."""
    body = it["text"] or ""
    if it["word"]:
        body = "[%s]" % it["word"] + (" " + body if body else "")
    return "%s · %s: %s" % (pk_full(it["ts"]), it["who"], body or "[пусто]")


def model_view(items):
    """Представление истории для модели → (текст, объём в символах). Пусто → ("", 0)."""
    text = "\n".join(model_line(it) for it in items)
    return text, len(text)
