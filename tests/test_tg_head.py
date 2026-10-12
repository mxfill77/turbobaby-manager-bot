#!/usr/bin/env python3
"""Шапка карточки TG «TG · @ник · имя» (TGHEAD1210, предложение NIGHT0710-B4 §2.3): `wa_agent_svc.TgSide._topic` берёт
ник и имя клиента из raw последних TG_HEAD_LOOK рядов ЭТОГО клиента в очереди TG (mode=ro), чистит невидимые символы,
режет; нет данных или сбой чтения — прежняя шапка «TG · tg:<id>» байт-в-байт.

Ряды — ДОСЛОВНЫЕ строки ленты ПК: их собрал живой `tg_feed.row`/`tg_feed.line` main ПК 653f614d (блоб tg_feed.py
680cf38b; кандидат f72a5a3e, NIGHT0710-B4 З3), сюда они вставлены литералами — на сервере кода ПК нет. В очередь они
идут шагами двери /tg-queue/push (`wa_webhook.tg_row_event` → `WAQueueDB.enqueue_confirmed`), ровно как их кладёт
сервер: ряд целиком в raw, колонка name пустая. Временные каталоги — `tempfile.mkdtemp` (префикс `tghead_`, не
удаляются намеренно). Сети нет, модель не зовётся, .env и окружение процесса не читаются.

Проверки: голдены ленты дверь принимает и кладёт в raw целиком · ник и имя входящего и исходящего · ряд без ключей
не останавливает поиск, null — останавливает · смена ника — последнее известное · без ника — id · коллекционный ник ·
отрицательные: пусто, raw NULL, мусор, чужой tg:<id> и подделанный chat_id, невидимые символы Cf, имя из одних
заполнителей, длинное имя, разрывы строк, база недоступна (нет файла, не база, нет таблицы, ядра нет), не-tg ключ ·
очередь только читается (sha256 до/после, запись через то же соединение отвергнута) · окно 50 рядов считает только
ряды клиента · `_topic` не бросает (перебор) · сквозной путь: карточка и вопрос паузы ядра TG несут новую шапку."""
import hashlib
import json
import os
import random
import sqlite3
import sys
import tempfile
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

import wa_agent as A  # noqa: E402
import wa_agent_svc as S  # noqa: E402
import wa_webhook as W  # noqa: E402

SINCE = 1791823432                       # TG_CHANNEL_SINCE живого включения 12.10 (ряды голденов позже)
ANNA = "tg:6879003264"

# невидимые знаки — только кодами: в тексте программы их нет (иначе исходник сам показывает подменённый вид)
RLO, ZWSP, LRI, PDI, BOM = chr(0x202E), chr(0x200B), chr(0x2066), chr(0x2069), chr(0xFEFF)
HF, HCF, HJF, HHF, BRL, WJ, NBSP, LS = (chr(0x3164), chr(0x115F), chr(0x1160), chr(0xFFA0), chr(0x2800), chr(0x2060),
                                        chr(0x00A0), chr(0x2028))

# ─── дословные строки ленты ПК (tg_feed.line @ 653f614d), без завершающего перевода строки ─────────────────────────
FEED = {
    "anna_in": '{"chat_id":6879003264,"msg_id":10,"dir":"in","ts":1791828000,"kind":"text","text":"Привет, байк на неделю?","reply_to":null,"sender_id":6879003264,"username":"anna_test","name":"Анна"}',
    "anna_out": '{"chat_id":6879003264,"msg_id":11,"dir":"out","ts":1791828000,"kind":"text","text":"Есть, 1200 в сутки","reply_to":null,"sender_id":9000,"username":"anna_test","name":"Анна"}',
    "anna_out_nopeer": '{"chat_id":6879003264,"msg_id":12,"dir":"out","ts":1791828000,"kind":"text","text":"Адрес пришлите","reply_to":null,"sender_id":9000}',
    "anna_renamed": '{"chat_id":6879003264,"msg_id":13,"dir":"in","ts":1791828000,"kind":"text","text":"это снова я","reply_to":null,"sender_id":6879003264,"username":"anna_new","name":"Анна Иванова"}',
    "nonick_in": '{"chat_id":1002,"msg_id":20,"dir":"in","ts":1791828000,"kind":"text","text":"hi","reply_to":null,"sender_id":1002,"username":null,"name":"Без ника"}',
    "old_in": '{"chat_id":1004,"msg_id":30,"dir":"in","ts":1791828000,"kind":"text","text":"старый ряд","reply_to":null,"sender_id":1004}',
    "coll_in": '{"chat_id":1005,"msg_id":40,"dir":"in","ts":1791828000,"kind":"text","text":"коллекционный","reply_to":null,"sender_id":1005,"username":"collect_me","name":"Коля"}',
    "bidi_in": '{"chat_id":1006,"msg_id":50,"dir":"in","ts":1791828000,"kind":"text","text":"bidi","reply_to":null,"sender_id":1006,"username":"ivan_1","name":"' + RLO + "анна" + ZWSP + " " + LRI + "Ив" + PDI + BOM + '"}',
    "void_in": '{"chat_id":1007,"msg_id":60,"dir":"in","ts":1791828000,"kind":"text","text":"пусто","reply_to":null,"sender_id":1007,"username":null,"name":"' + HF + " " + BRL + ZWSP + '"}',
    "long_in": '{"chat_id":1008,"msg_id":70,"dir":"in","ts":1791828000,"kind":"text","text":"длинное","reply_to":null,"sender_id":1008,"username":null,"name":"' + "Я" * 128 + " " + "Ф" * 128 + '"}',
    "nl_in": '{"chat_id":1009,"msg_id":80,"dir":"in","ts":1791828000,"kind":"text","text":"перевод строки","reply_to":null,"sender_id":1009,"username":"nl_user","name":"Очень\\nдлинное Фамилия\\u2028Вторая\\tТретья"}',
    "gone_nick": '{"chat_id":1010,"msg_id":90,"dir":"in","ts":1791828000,"kind":"text","text":"с ником","reply_to":null,"sender_id":1010,"username":"had_nick","name":"Гоша"}',
    "gone_nonick": '{"chat_id":1010,"msg_id":91,"dir":"in","ts":1791828000,"kind":"text","text":"без ника","reply_to":null,"sender_id":1010,"username":null,"name":"Гоша"}',
}
# sha256 склейки голденов (ключи по алфавиту, «ключ\tстрока\n») — замок от случайной правки литералов; равенство
# литералов живому выводу tg_feed.line сверено на ПК пробой захода (b2_tghead/tools/chain_probe.py)
FEED_SHA = "9a727f5ed1640bbad8213698d10a493998fa14a4c9cdc5ce3f0169887838e90a"


def _feed_sha():
    blob = "".join("%s\t%s\n" % (k, FEED[k]) for k in sorted(FEED))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# ─── мир теста ──────────────────────────────────────────────────────────────────────────────────────────────────

def _dir():
    return tempfile.mkdtemp(prefix="tghead_")


def queue(*labels, path=None):
    """Очередь TG шагами двери: каждая строка ленты → json.loads (как тело пушера) → tg_row_event → enqueue_confirmed."""
    path = path or os.path.join(_dir(), "tg_queue.db")
    db = W.WAQueueDB(path)
    for lb in labels:
        key, ev = W.tg_row_event(json.loads(FEED[lb]), SINCE)
        assert key is not None, lb
        assert W.tg_wamid(*key) in db.enqueue_confirmed([ev], source=W.TG_SOURCE), lb
    return path


_JUNK = iter(range(1, 10 ** 9))


def raw_rows(path, rows):
    """Ряды в обход двери (мусор в raw): (from_number, raw)."""
    c = sqlite3.connect(path)
    try:
        for frm, raw in rows:
            i = next(_JUNK)
            c.execute("INSERT INTO wa_inbox(ts_queued, channel, from_number, name, msg_type, text, raw, wamid) "
                      "VALUES(?,?,?,?,?,?,?,?)", (SINCE + i, "tg", frm, "", "text", "x", raw, "tg:junk:%d" % i))
        c.commit()
    finally:
        c.close()
    return path


class Core:
    """Ядро-заглушка: очередь читается НАСТОЯЩИМ `wa_agent.Core._queue` (mode=ro), база рук — в памяти."""

    def __init__(self, queue_path):
        self.queue_path = queue_path
        self.db = sqlite3.connect(":memory:")

    def _queue(self):
        return A.Core._queue(self)


def side(queue_path, lines=None, bind=True):
    s = S.TgSide("123:VYDUMANNYJ", enabled=True, prefix="tg", reader=False, send_closed=False,
                 http=lambda *a, **k: (200, b'{"ok":true,"result":{"message_id":1}}'),
                 log=(lines.append if lines is not None else None))
    if bind:
        s.bind(Core(queue_path))
    return s


def head(queue_path, number=ANNA, lines=None):
    got = side(queue_path, lines)._topic(number)
    assert isinstance(got, tuple) and len(got) == 2 and got[1] == "", got
    return got[0]


def _sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _clean_line(s):
    """Шапка — одна строка без невидимых символов и не длиннее TG_HEAD_MAX."""
    bad = [hex(ord(ch)) for ch in s if unicodedata.category(ch) in ("Cc", "Cf", "Cs", "Zl", "Zp")]
    assert not bad and len(s) <= S.TG_HEAD_MAX and s.startswith("TG · "), (s, bad)


# ═══ голдены ленты и дверь ═══════════════════════════════════════════════════════════════════════════════════════

def test_feed_goldens_are_verbatim_and_door_keeps_row_whole():
    assert _feed_sha() == FEED_SHA, _feed_sha()
    path = queue(*sorted(FEED))
    c = sqlite3.connect("file:%s?mode=ro" % path, uri=True)
    try:
        rows = c.execute("SELECT from_number, name, raw FROM wa_inbox ORDER BY id").fetchall()
    finally:
        c.close()
    assert len(rows) == len(FEED), len(rows)
    for (frm, name, raw), lb in zip(rows, sorted(FEED)):
        rec = json.loads(FEED[lb])
        assert frm == "tg:%d" % rec["chat_id"] and name == "", (lb, frm, name)       # колонка name пуста (дверь)
        assert json.loads(raw) == rec, lb                                            # ряд целиком в raw
    assert "username" not in json.loads(FEED["old_in"]) and "name" not in json.loads(FEED["anna_out_nopeer"])


# ═══ положительные: ник и имя из ряда ленты ═════════════════════════════════════════════════════════════════════

def test_in_row_gives_nick_and_name():
    assert head(queue("anna_in")) == "TG · @anna_test · Анна"


def test_out_row_carries_client_nick_not_ours():
    assert head(queue("anna_out")) == "TG · @anna_test · Анна"        # исходящий: ник КЛИЕНТА, sender_id наш


def test_row_without_keys_does_not_stop_search():
    # самый новый ряд — без ключей (собеседник не передан): повтор ряда старые строки не дополняет, ищем глубже
    assert head(queue("anna_in", "anna_out_nopeer")) == "TG · @anna_test · Анна"


def test_rename_takes_latest_known():
    assert head(queue("anna_in", "anna_out", "anna_renamed")) == "TG · @anna_new · Анна Иванова"
    assert head(queue("anna_renamed", "anna_in")) == "TG · @anna_test · Анна"          # порядок — по id очереди


def test_no_nick_shows_id_and_name():
    assert head(queue("nonick_in"), "tg:1002") == "TG · 1002 · Без ника"


def test_collectible_nick():
    assert head(queue("coll_in"), "tg:1005") == "TG · @collect_me · Коля"


def test_nick_without_name():
    # имени нет (null) или оно из одних невидимых — шапка с одним ником, без хвоста « · »
    for name in ("null", '""', '"' + HF + ZWSP + '"'):
        raw = '{"chat_id":6879003264,"username":"only_nick","name":%s}' % name
        assert head(raw_rows(queue(), [(ANNA, raw)])) == "TG · @only_nick", name


def test_null_nick_stops_search():
    # клиент убрал ник: самый новый ряд говорит null — старый ник НЕ показываем
    assert head(queue("gone_nick", "gone_nonick"), "tg:1010") == "TG · 1010 · Гоша"
    assert head(queue("gone_nonick", "gone_nick"), "tg:1010") == "TG · @had_nick · Гоша"


# ═══ отрицательные ══════════════════════════════════════════════════════════════════════════════════════════════

def test_empty_and_old_rows_byte_for_byte():
    assert side(queue("old_in"))._topic("tg:1004") == ("TG · tg:1004", "")             # ряд до 07.10 — без ключей
    assert side(queue("anna_in"))._topic("tg:1004") == ("TG · tg:1004", "")            # строк клиента нет вовсе
    path = queue()
    assert side(path)._topic(ANNA) == ("TG · " + ANNA, "")                              # очередь пуста
    raw_rows(path, [(ANNA, None), (ANNA, None)])                                        # raw NULL (как test_tg_core)
    assert side(path)._topic(ANNA) == ("TG · " + ANNA, "")


def test_garbage_rows_old_head_and_do_not_hide_valid():
    junk = ["not json", "[1, 2]", "null", '"строка"', "", "{", "[" * 100000,
            '{"chat_id":"6879003264","username":"str_id","name":"Строковый id"}',
            '{"chat_id":true,"username":"bool_id","name":"Да"}',
            '{"chat_id":6879003264,"username":123,"name":{"a":1}}',
            '{"chat_id":6879003264,"username":"bad nick","name":["x"]}',
            '{"chat_id":6879003264,"username":"@anna_test","name":7}',
            '{"chat_id":6879003264,"username":"' + "a" * 33 + '"}',
            '{"chat_id":6879003264,"username":"ник_кириллицей"}']
    path = raw_rows(queue(), [(ANNA, j) for j in junk])
    lines = []
    assert side(path, lines)._topic(ANNA) == ("TG · " + ANNA, ""), "мусор дал шапку"
    assert lines == [], lines                                          # мусор — не сбой чтения: журнал молчит
    # мусор НОВЕЕ валидного ряда валидное не прячет: мусор — «неизвестно», а не «нет»
    path2 = raw_rows(queue("anna_in"), [(ANNA, j) for j in junk])
    assert head(path2) == "TG · @anna_test · Анна"


def test_foreign_client_and_forged_chat_id_do_not_leak():
    path = queue("anna_in", "nonick_in", "coll_in")
    assert head(path) == "TG · @anna_test · Анна"
    assert head(path, "tg:1002") == "TG · 1002 · Без ника"
    assert head(path, "tg:1005") == "TG · @collect_me · Коля"
    # ряд клиента 1003 с чужим chat_id в raw (подделка/порча) — пропуск: шапка 1003 прежняя
    raw_rows(path, [("tg:1003", FEED["anna_in"])])
    assert side(path)._topic("tg:1003") == ("TG · tg:1003", "")
    assert head(path) == "TG · @anna_test · Анна"


def test_window_counts_only_this_client_rows():
    path = queue("anna_in")
    # 60 рядов ДРУГИХ клиентов новее — окно 50 их не считает (фильтр по клиенту в запросе)
    raw_rows(path, [("tg:%d" % (2000 + i), '{"chat_id":%d,"username":"u%04d","name":"Чужой"}' % (2000 + i, i))
                    for i in range(60)])
    assert head(path) == "TG · @anna_test · Анна"
    # 49 своих рядов без ключей новее — ник ещё в окне; 50 — уже нет (окно = TG_HEAD_LOOK рядов клиента)
    raw_rows(path, [(ANNA, FEED["anna_out_nopeer"])] * (S.TG_HEAD_LOOK - 1))
    assert head(path) == "TG · @anna_test · Анна"
    raw_rows(path, [(ANNA, FEED["anna_out_nopeer"])])
    assert side(path)._topic(ANNA) == ("TG · " + ANNA, "")


def test_invisible_cf_removed():
    got = head(queue("bidi_in"), "tg:1006")
    assert got == "TG · @ivan_1 · анна Ив", [hex(ord(c)) for c in got]
    _clean_line(got)


def test_name_of_fillers_only_is_empty():
    # U+3164 (заполнитель хангыля), U+2800 (пустой брайль), U+200B — видимого нет: имя пустое, ника нет → прежняя
    assert side(queue("void_in"))._topic("tg:1007") == ("TG · tg:1007", "")
    assert S.tg_clean(HF + HCF + HJF + HHF + BRL + ZWSP + WJ + BOM + NBSP, 64) == ""
    assert S.tg_clean(HF + "Анна", 64) == HF + "Анна"                   # заполнитель рядом с видимым остаётся
    assert S.tg_clean(RLO + "Ив" + LS + "ан" + chr(0) + chr(0xD800), 64) == "Ив ан"   # Cf, Zl→пробел, Cc, Cs


def test_long_name_cut_and_one_line():
    got = head(queue("long_in"), "tg:1008")
    assert got == "TG · 1008 · " + "Я" * S.TG_HEAD_NAME_MAX, got
    _clean_line(got)
    got = head(queue("nl_in"), "tg:1009")
    assert got == "TG · @nl_user · Очень длинное Фамилия Вторая Третья", got
    _clean_line(got)
    # самая длинная возможная шапка: ник 32 + имя 64 — в TG_HEAD_MAX
    path = raw_rows(queue(), [(ANNA, json.dumps({"chat_id": 6879003264, "username": "n" * 32, "name": "😀" * 300}))])
    got = head(path)
    assert got == "TG · @" + "n" * 32 + " · " + "😀" * 64 and len(got) <= S.TG_HEAD_MAX, got
    # Telegram меряет длину в UTF-16: шапка длиннее себя в знаках не больше чем на имя (ник — латиница)
    assert len(got.encode("utf-16-le")) // 2 - len(got) <= S.TG_HEAD_NAME_MAX, len(got.encode("utf-16-le"))


def test_queue_unavailable_old_head_and_one_line():
    d = _dir()
    cases = {"нет файла": os.path.join(d, "нет", "tg_queue.db"),
             "не база": os.path.join(d, "not_a_db.db"),
             "нет таблицы": os.path.join(d, "empty.db")}
    with open(cases["не база"], "wb") as fh:
        fh.write(b"\x00garbage, not sqlite\x00" * 64)
    sqlite3.connect(cases["нет таблицы"]).close()
    for what, path in cases.items():
        lines = []
        assert side(path, lines)._topic(ANNA) == ("TG · " + ANNA, ""), what
        assert len(lines) == 1 and lines[0].startswith("шапка: очередь TG не прочитана — "), (what, lines)
        assert lines[0].endswith(", шапка прежняя") and "anna" not in lines[0] and "Анна" not in lines[0], lines
    lines = []
    s = side(queue("anna_in"), lines, bind=False)                      # ядра нет (руки не привязаны)
    assert s._topic(ANNA) == ("TG · " + ANNA, "") and len(lines) == 1, lines


def test_not_tg_key_never_reads_queue():
    class Boom(Core):
        def _queue(self):
            raise AssertionError("очередь читали для не-tg ключа")
    lines = []
    s = side(queue("anna_in"), lines, bind=False)
    s.bind(Boom(""))
    for num in ("66812345678", "tg:", "tg:12a", "TG:6879003264", " tg:6879003264", "tg:6879003264 "):
        assert s._topic(num) == ("TG · " + num, ""), num
    assert lines == [], lines


def test_queue_read_only():
    path = queue("anna_in", "anna_out", "nonick_in")
    before = _sha(path)
    for _ in range(20):
        head(path)
        head(path, "tg:1002")
    assert _sha(path) == before, "очередь изменилась от чтения шапки"
    conn = Core(path)._queue()                                         # то же соединение, что у шапки
    try:
        try:
            conn.execute("INSERT INTO wa_inbox(ts_queued, from_number) VALUES(1, 'x')")
            raise AssertionError("запись через соединение шапки прошла")
        except sqlite3.OperationalError as e:
            assert "readonly" in str(e), e
    finally:
        conn.close()


def test_topic_never_raises_fuzz():
    rnd = random.Random(1210)
    alphabet = ["a", "Z", "_", "9", " ", "\n", RLO, ZWSP, HF, BRL, "Я", "😀", "\x00", "\x85", LS, "@", "·", BOM,
                chr(0xD800)]
    path = queue("anna_in")
    rows = []
    for i in range(400):
        def val():
            k = rnd.randrange(6)
            if k == 0:
                return None
            if k == 1:
                return rnd.randrange(-5, 5)
            if k == 2:
                return [rnd.random()]
            return "".join(rnd.choice(alphabet) for _ in range(rnd.randrange(0, 90)))
        rec = {"chat_id": rnd.choice([6879003264, 6879003264, 1, "6879003264", None])}
        for key in ("username", "name"):
            if rnd.random() < 0.7:
                rec[key] = val()
        raw = json.dumps(rec, ensure_ascii=True)                       # \ud800 доходит одиночным суррогатом
        rows.append((ANNA, raw if rnd.random() < 0.9 else raw[: rnd.randrange(len(raw))]))
    lines = []
    s = side(path, lines)
    for k in range(0, len(rows), 7):                                   # перебор кладётся порциями, шапка — после каждой
        raw_rows(path, rows[k:k + 7])
        got = s._topic(ANNA)
        assert got[1] == "", got
        _clean_line(got[0])
    assert lines == [], lines[:3]
    for (_frm, raw) in rows:                                           # и чистая функция — на каждом ряде отдельно
        got = S.tg_head(ANNA, [raw])
        if got is not None:
            _clean_line(got)


# ═══ сквозной путь: карточка и вопрос паузы ядра TG ══════════════════════════════════════════════════════════════

def _world_with(*labels, ts=None, environ=None):
    import test_tg_core as TC
    w = TC.World(environ or TC.TG_ON, tg=True)
    w.tgc.tick(TC.T0 - 1000)                                           # первый старт ядра TG: курсор на MAX(id)
    wq = os.path.join(w.dir, "tg_queue.db")                            # очередь TG мира (World: каталог + tg_queue.db)
    queue(*labels, path=wq)
    c = sqlite3.connect(wq)
    c.execute("UPDATE wa_inbox SET ts_queued=?", (TC.T0 - 200,))       # время очереди — часы мира (как World.put)
    c.commit()
    c.close()
    w.tgc.tick(TC.T0)
    return w, TC


def test_end_to_end_card_first_line():
    w, TC = _world_with("anna_in")
    cards = w.cards("tg")
    assert len(cards) == 1, cards
    top = cards[0][0]["text"].split("\n", 1)[0]
    assert top == "📝 Черновик №1 · версия 1 · TG · @anna_test · Анна", top
    assert not [ln for ln in w.lines if "шапка" in ln], w.lines


def test_end_to_end_old_row_card_unchanged():
    w, TC = _world_with("old_in")
    cards = w.cards("tg")
    assert len(cards) == 1, cards
    assert cards[0][0]["text"].split("\n", 1)[0] == "📝 Черновик №1 · версия 1 · TG · tg:1004", cards[0][0]["text"]


def test_end_to_end_pause_question_head():
    # ответ с телефона после входящего — пауза. Ряды ленты дословные и оба в одну секунду: на основе с TGGREET1310
    # (e57313b) такое эхо ≤ GREET_SEC после «первого» входящего — автоприветствие, паузы нет. Предмет теста — шапка
    # вопроса паузы, а не признак приветствия, поэтому признак выключен его же ручкой (WA_AGENT_TG_GREET=0).
    import test_tg_core as TC
    w, TC = _world_with("anna_in", "anna_out", environ=dict(TC.TG_ON, WA_AGENT_TG_GREET="0"))
    asks = [p["text"] for p in w.http.of("sendMessage") if p["text"].startswith("⏸ ")]
    assert len(asks) == 1, [p["text"][:60] for p in w.http.of("sendMessage")]
    assert asks[0].startswith("⏸ TG · @anna_test · Анна\nтемы в показе нет\n"), asks[0]


def main():
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    bad = 0
    for name, fn in tests:
        try:
            fn()
            print("PASS", name)
        except Exception as e:                                       # noqa: BLE001
            bad += 1
            print("FAIL %s %s: %s" % (name, type(e).__name__, str(e)[:300]))
    print("ИТОГ %d/%d" % (len(tests) - bad, len(tests)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
