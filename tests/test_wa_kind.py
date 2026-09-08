"""ВИД ЗАПИСИ ВХОДЯЩЕЙ ОЧЕРЕДИ WhatsApp — решение `wa_kind` и его доезд до выдачи забора.

Предмет: четыре рода событий делят ОДНУ таблицу `wa_inbox`, и до 07.09.2026 выдача забора не
несла НИ ОДНОГО поля, которым они различаются. Здесь проверяется, что:

  (1) вид решается ПОЛЯМИ, а не текстом, и квитанция отделяется ОДНИМ полем;
  (2) неопознанное становится `unknown`, а НЕ входящим — третий исход;
  (3) ОТРИЦАТЕЛЬНО: запись, ВЫГЛЯДЯЩАЯ входящим клиентом, но им не являющаяся, отделена;
  (4) различитель доезжает до выдачи забора конец-в-конец, живым кодом;
  (5) прежние семь ключей выдачи целы — прибавка, а не замена.

Сети нет, живая очередь `wa_queue.db` не открывается ни одной веткой: каждый случай поднимает
свою временную базу.
"""

import sys
import os
import json
import time
import tempfile

sys.path.insert(0, "/root/turbobaby-manager-bot")

os.environ.setdefault("WA_VERIFY_TOKEN",    "test_verify_token")
os.environ.setdefault("WA_APP_SECRET",      "test_secret")
os.environ.setdefault("WA_PHONE_NUMBER_ID", "66999000111")

import wa_kind as wk
import wa_webhook as wh

res = []


def ok(cond, label):
    mark = "  PASS " if cond else "  FAIL "
    print(mark + label)
    res.append(bool(cond))
    return bool(cond)


def _tmp_db() -> wh.WAQueueDB:
    fd, path = tempfile.mkstemp(suffix=".db", prefix="wa_kind_")
    os.close(fd)
    return wh.WAQueueDB(path)


OUR = "66999000111"          # наш деловой номер — от него приходит эхо
CLIENT = "66812345678"       # номер клиента


def _msg_payload(sender, text, ts, wamid, our=OUR, mtype="text"):
    """Живая форма Meta Cloud API: один входящий/эхо в одном payload."""
    msg = {"from": sender, "id": wamid, "timestamp": str(int(ts)), "type": mtype}
    if mtype == "text":
        msg["text"] = {"body": text}
    return {
        "object": "whatsapp_business_account",
        "entry": [{"id": "WABA_1", "changes": [{
            "field": "messages",
            "value": {
                "messaging_product": "whatsapp",
                "metadata": {"display_phone_number": our, "phone_number_id": "PHID"},
                "contacts": [{"wa_id": sender, "profile": {"name": "Ivan"}}],
                "messages": [msg],
            },
        }]}],
    }


def _status_payload(recipient, state, ts, wamid, our=OUR):
    """Живая форма квитанции доставки: value.statuses, а не value.messages."""
    return {
        "object": "whatsapp_business_account",
        "entry": [{"id": "WABA_1", "changes": [{
            "field": "messages",
            "value": {
                "messaging_product": "whatsapp",
                "metadata": {"display_phone_number": our, "phone_number_id": "PHID"},
                "statuses": [{
                    "id": wamid, "recipient_id": recipient,
                    "status": state, "timestamp": str(int(ts)),
                }],
            },
        }]}],
    }


# ═══ (1) РЕШЕНИЕ: четыре вида по полям ═══════════════════════════════════════════════

def test_four_kinds_by_fields():
    ok(wk.kind_of("text", 0, 0) == wk.KIND_INBOUND, "клиент написал → inbound")
    ok(wk.kind_of("text", 1, 0) == wk.KIND_ECHO, "наше исходящее вернулось → echo")
    ok(wk.kind_of("text", 0, 1) == wk.KIND_HISTORY, "досинхрон старой переписки → history")
    ok(wk.kind_of("status", 0, 0) == wk.KIND_RECEIPT, "квитанция доставки → receipt")
    ok(len(set(wk.KINDS)) == 5, "видов ровно пять, и все разные")


def test_receipt_decided_by_one_field_not_by_text():
    """Пункт 2 задания: квитанция отделяется ОДНИМ полем, а не догадкой по тексту."""
    for state in ("sent", "delivered", "read", "failed"):
        ok(wk.kind_of("status", 0, 0) == wk.KIND_RECEIPT,
           "квитанция «" + state + "» — receipt по msg_type, текст не спрашивали")
    # и обратная сторона того же: слово состояния В ТЕКСТЕ клиента квитанцией его не делает
    ok(wk.kind_of("text", 0, 0) == wk.KIND_INBOUND,
       "клиент, написавший слово состояния, остаётся inbound — судится поле, не текст")


def test_receipt_survives_junk_neighbours():
    """Квитанция обязана остаться квитанцией при ЛЮБОМ состоянии соседних полей."""
    for echo, history in ((0, 0), (1, 0), (0, 1), (1, 1), (None, None), ("мусор", "мусор")):
        ok(wk.kind_of("status", echo, history) == wk.KIND_RECEIPT,
           "квитанция при echo=%r history=%r — всё равно receipt" % (echo, history))


def test_receipt_gives_neither_card_nor_context():
    """Пункт 2: сказано прямо — ни карточки, ни контекста."""
    ok(wk.disposition_of(wk.KIND_RECEIPT) == wk.DISP_DROP,
       "распоряжение по квитанции: drop — ни карточки, ни контекста")
    ok(wk.disposition_of(wk.KIND_INBOUND) == wk.DISP_CARD, "входящее клиента — карточка")
    ok(wk.disposition_of(wk.KIND_ECHO) == wk.DISP_CONTEXT, "эхо — контекст без карточки")
    ok(wk.disposition_of(wk.KIND_HISTORY) == wk.DISP_CONTEXT, "история — контекст без карточки")
    ok(wk.disposition_of(wk.KIND_UNKNOWN) == wk.DISP_REVIEW, "неопознанное — показать, не карточка")
    ok(wk.disposition_of("вид, которого нет") == wk.DISP_REVIEW,
       "незнакомый вид → review (fail-closed: карточки молча не заводим)")


def test_echo_beats_history():
    ok(wk.kind_of("text", 1, 1) == wk.KIND_ECHO,
       "эхо И история сразу → echo (ось «чьё» главнее; обе величины едут сырыми)")


# ═══ (2) ТРЕТИЙ ИСХОД: неопознанное НЕ становится входящим ════════════════════════════

def test_unknown_type_is_not_inbound():
    """Пункт 3: молчаливое приведение к входящему дало бы карточку там, где её быть не должно."""
    for t in ("reaction", "order", "button", "system", "жжж"):
        got = wk.kind_of(t, 0, 0)
        ok(got == wk.KIND_UNKNOWN, "незнакомый тип «" + t + "» → unknown, а не inbound (" + got + ")")


def test_empty_type_is_unknown():
    ok(wk.kind_of("", 0, 0) == wk.KIND_UNKNOWN, "пустой тип → unknown")
    ok(wk.kind_of(None, 0, 0) == wk.KIND_UNKNOWN, "тип не записан → unknown")


def test_unreadable_flag_is_unknown():
    """NULL и мусор во флаге НЕ приводятся к нулю: «не знаю, наше ли» ≠ «точно не наше»."""
    ok(wk.kind_of("text", None, 0) == wk.KIND_UNKNOWN, "echo не записан → unknown")
    ok(wk.kind_of("text", 0, None) == wk.KIND_UNKNOWN, "history не записан → unknown")
    ok(wk.kind_of("text", "мусор", 0) == wk.KIND_UNKNOWN, "echo не разобран → unknown")
    ok(wk.kind_of("text", [], 0) == wk.KIND_UNKNOWN, "echo чужого типа → unknown")


def test_flag_forms_that_are_readable():
    ok(wk.kind_of("text", "0", "0") == wk.KIND_INBOUND, "строковые нули читаются")
    ok(wk.kind_of("text", "1", "0") == wk.KIND_ECHO, "строковая единица читается")
    ok(wk.kind_of("text", True, False) == wk.KIND_ECHO, "булев флаг читается")
    ok(wk.kind_of("TEXT", 0, 0) == wk.KIND_INBOUND, "регистр типа не решает")
    ok(wk.kind_of("  status ", 0, 0) == wk.KIND_RECEIPT, "пробелы вокруг типа не решают")


def test_kind_always_returns_a_known_kind():
    for args in (("text", 0, 0), ("status", 1, 1), ("жжж", None, "мусор"), (None, [], {})):
        ok(wk.kind_of(*args) in wk.KINDS, "вид всегда из списка: kind_of%r" % (args,))


# ═══ (3) ОТРИЦАТЕЛЬНЫЙ ТЕСТ — обязателен по пункту 4 ═════════════════════════════════

def test_negative_looks_like_client_but_is_not():
    """ВЫГЛЯДИТ входящим клиентом — но им не является. Прибор обязан отделить.

    Все четыре записи ниже неотличимы от сообщения клиента по ФОРМЕ: реальный номер, живой
    текст, свежая метка времени, тот же канал. Разделяет их только поле.
    """
    db = _tmp_db()
    now = int(time.time())

    # (а) эхо менеджера: пришло ОТ нашего номера — текст человеческий, вид не клиентский
    db.enqueue(wh.normalize_wa_payload(
        _msg_payload(OUR, "Привет, байк свободен", now, "wamid.echo1"), OUR), source="meta")
    # (б) история: тот же клиент, тот же текст — но метка позавчерашняя
    db.enqueue(wh.normalize_wa_payload(
        _msg_payload(CLIENT, "Привет, байк свободен", now - 3 * 86400, "wamid.hist1"), OUR),
        source="meta")
    # (в) квитанция: recipient_id — живой номер клиента, текст «delivered»
    db.enqueue(wh.normalize_wa_payload(
        _status_payload(CLIENT, "delivered", now, "wamid.rcpt1"), OUR), source="meta")
    # (г) неопознанный вид от живого клиента
    db.enqueue(wh.normalize_wa_payload(
        _msg_payload(CLIENT, None, now, "wamid.unk1", mtype="reaction"), OUR), source="meta")
    # (д) КОНТРОЛЬ: настоящее входящее — иначе «отделяет» могло бы значить «отвергает всё»
    db.enqueue(wh.normalize_wa_payload(
        _msg_payload(CLIENT, "Привет, байк свободен", now, "wamid.real1"), OUR), source="meta")

    got = {it["text"] or it["msg_type"]: it for it in db.pull()}
    by_wamid = {it["id"]: it for it in db.pull(now=now + wh.LEASE_SECS + 1)}
    ok(len(by_wamid) == 5, "все пять записей доехали до выдачи (ни одна не отсеяна)")

    kinds = [it["kind"] for it in sorted(by_wamid.values(), key=lambda x: x["id"])]
    ok(kinds == [wk.KIND_ECHO, wk.KIND_HISTORY, wk.KIND_RECEIPT,
                 wk.KIND_UNKNOWN, wk.KIND_INBOUND],
       "виды разложены: эхо · история · квитанция · неопознанное · входящее (" + str(kinds) + ")")

    cards = [it for it in by_wamid.values() if it["disposition"] == wk.DISP_CARD]
    ok(len(cards) == 1, "карточку рождает РОВНО одна запись из пяти")
    ok(cards[0]["from"] == CLIENT and cards[0]["kind"] == wk.KIND_INBOUND,
       "и это настоящее сообщение клиента, а не эхо, история, квитанция или неопознанное")
    del got


def test_negative_receipt_text_is_not_a_client_message():
    """Клиент, приславший слово «delivered», ОБЯЗАН остаться входящим."""
    db = _tmp_db()
    now = int(time.time())
    db.enqueue(wh.normalize_wa_payload(
        _msg_payload(CLIENT, "delivered", now, "wamid.trap1"), OUR), source="meta")
    it = db.pull()[0]
    ok(it["kind"] == wk.KIND_INBOUND,
       "текст «delivered» от клиента — inbound: судится поле msg_type, а не слово")
    ok(it["disposition"] == wk.DISP_CARD, "и он получает карточку, как и должен")


# ═══ (4) ЗАМЕР пункта 5: доезжают ли эхо и история до забора ВООБЩЕ ═══════════════════

def test_echo_and_history_reach_the_pull_door():
    """Замером, а не чтением схемы: кладём живым кодом и смотрим, что отдаёт живой забор."""
    db = _tmp_db()
    now = int(time.time())
    db.enqueue(wh.normalize_wa_payload(
        _msg_payload(OUR, "эхо", now, "wamid.e1"), OUR), source="meta")
    db.enqueue(wh.normalize_wa_payload(
        _msg_payload(CLIENT, "старое", now - 5 * 86400, "wamid.h1"), OUR), source="meta")
    db.enqueue(wh.normalize_wa_payload(
        _status_payload(CLIENT, "read", now, "wamid.s1"), OUR), source="meta")

    items = db.pull()
    kinds = sorted(it["kind"] for it in items)
    ok(len(items) == 3, "все три записи выданы забором — ни одна не отсеяна раньше")
    ok(kinds == sorted([wk.KIND_ECHO, wk.KIND_HISTORY, wk.KIND_RECEIPT]),
       "и каждая названа своим видом: " + str(kinds))
    ok(all(it["echo"] is not None and it["history"] is not None for it in items),
       "сырые различители доехали не пустыми")


# ═══ (5) ВЫДАЧА: прибавка полей, а не замена ═════════════════════════════════════════

_OLD_KEYS = ("id", "from", "name", "type", "text", "ts", "source")


def test_old_seven_keys_intact():
    """Старые потребители не сломаны: прежние семь ключей на местах и с прежними значениями."""
    db = _tmp_db()
    now = int(time.time())
    db.enqueue(wh.normalize_wa_payload(
        _msg_payload(CLIENT, "Здравствуйте", now, "wamid.k1"), OUR), source="meta")
    it = db.pull()[0]
    for k in _OLD_KEYS:
        ok(k in it, "прежний ключ на месте: " + k)
    ok(it["id"] == 1 and it["from"] == CLIENT and it["name"] == "Ivan", "прежние значения целы")
    ok(it["type"] == "text" and it["text"] == "Здравствуйте", "тип и текст прежние")
    ok(it["ts"] == now and it["source"] == "meta", "метка и источник прежние")


def test_new_keys_use_table_names():
    """Пункт 1: имена полей — те же, что в таблице, чтобы у вещи не стало двух имён."""
    db = _tmp_db()
    db.enqueue(wh.normalize_wa_payload(
        _msg_payload(CLIENT, "привет", int(time.time()), "wamid.n1"), OUR), source="meta")
    it = db.pull()[0]
    for k in ("msg_type", "echo", "history", "kind", "disposition"):
        ok(k in it, "различитель доехал: " + k)
    cols = {r[1] for r in __import__("sqlite3").connect(db.db_path)
            .execute("PRAGMA table_info(wa_inbox)")}
    for k in ("msg_type", "echo", "history"):
        ok(k in cols, "имя «" + k + "» взято у таблицы, а не выдумано")


def test_msg_type_and_legacy_type_cannot_diverge():
    """`type` оставлен легаси-псевдонимом: то же значение из того же столбца."""
    db = _tmp_db()
    now = int(time.time())
    for i, t in enumerate(("text", "image", "location")):
        db.enqueue(wh.normalize_wa_payload(
            _msg_payload(CLIENT, "x", now, "wamid.d%d" % i, mtype=t), OUR), source="meta")
    for it in db.pull():
        ok(it["type"] == it["msg_type"], "type == msg_type для «" + it["msg_type"] + "»")


def test_pull_output_is_json_serialisable():
    """Выдача уезжает по HTTP — новые поля обязаны пережить сериализацию."""
    db = _tmp_db()
    now = int(time.time())
    db.enqueue(wh.normalize_wa_payload(
        _status_payload(CLIENT, "sent", now, "wamid.j1"), OUR), source="meta")
    body = json.dumps({"ok": True, "items": db.pull()}, ensure_ascii=False)
    back = json.loads(body)["items"][0]
    ok(back["kind"] == wk.KIND_RECEIPT and back["disposition"] == wk.DISP_DROP,
       "вид и распоряжение пережили JSON")


def test_row_with_unrecognised_type_is_unknown_not_inbound():
    """Строка живой формы с неопознанным типом НЕ становится входящим молча.

    Это ветка третьего исхода, ДОСТИЖИМАЯ из самой таблицы: WhatsApp волен прислать род, о
    котором нормализация не знает (`reaction`, `order`, `button`), — и он ляжет в очередь.
    """
    db = _tmp_db()
    now = int(time.time())
    import sqlite3
    with sqlite3.connect(db.db_path) as conn:
        conn.execute(
            "INSERT INTO wa_inbox (ts_queued, channel, from_number, name, msg_type, text,"
            " ts_msg, echo, history, status, raw, wamid)"
            " VALUES (?,?,?,?,?,?,?,0,0,'new','{}',?)",
            (now, "wa", CLIENT, "Ivan", "reaction", None, now, "wamid.unk2"),
        )
        conn.commit()
    it = db.pull()[0]
    ok(it["kind"] == wk.KIND_UNKNOWN,
       "неопознанный тип → unknown, а не inbound (" + it["kind"] + ")")
    ok(it["disposition"] == wk.DISP_REVIEW, "и карточки такая строка не рождает")


def test_null_flags_are_forbidden_by_the_table_itself():
    """ЧЕСТНО О ВЕТКЕ NULL: сегодня она из ЭТОЙ таблицы недостижима, и это сказано числом.

    `echo`/`history` объявлены `INTEGER NOT NULL DEFAULT 0` в ИСХОДНОЙ схеме (в отличие от
    `source`/`delivered_at`/`acked_at`, добавленных 06.09 и потому NULL-евых). Значит
    трёхзначный `_flag` — ремень, а не рабочая ветка: он держит случай, когда те же поля придут
    не из этой таблицы. Сама ветка проверена на функции (`test_unreadable_flag_is_unknown`), а
    отказ таблицы доказывает, что вторая проверка через базу была бы фикстурой МИМО ветки.
    """
    db = _tmp_db()
    import sqlite3
    refused = False
    try:
        with sqlite3.connect(db.db_path) as conn:
            conn.execute(
                "INSERT INTO wa_inbox (ts_queued, channel, from_number, msg_type, echo, history)"
                " VALUES (?,?,?,?,NULL,NULL)",
                (int(time.time()), "wa", CLIENT, "text"),
            )
            conn.commit()
    except sqlite3.IntegrityError:
        refused = True
    ok(refused, "таблица сама запрещает NULL в echo/history — ветка NULL из неё недостижима")
    cols = {r[1]: (r[3], r[4]) for r in
            sqlite3.connect(db.db_path).execute("PRAGMA table_info(wa_inbox)")}
    ok(cols.get("echo") == (1, "0") and cols.get("history") == (1, "0"),
       "и это записано в схеме: NOT NULL DEFAULT 0")


# ═══ (6) ЗАМКИ: два набора типов не разъедутся в опасную сторону ═════════════════════

def test_media_types_are_a_subset_of_inbound_types():
    """`_MEDIA_TYPES` отвечает «где media_id», `INBOUND_TYPES` — «бывает ли такой род у клиента».

    Вопросы разные, но если media-тип выпадет из клиентских, живое сообщение клиента поедет
    `unknown` и карточки не даст. Направление ошибки безопасное, а вот молчать о нём нельзя.
    """
    missing = sorted(set(wh._MEDIA_TYPES) - set(wk.INBOUND_TYPES))
    ok(not missing, "все media-типы признаются клиентскими (выпали: " + str(missing) + ")")


def test_receipt_type_matches_what_normalisation_writes():
    """Значение `status` — не литерал из головы: его пишут ОБА нормализатора."""
    now = int(time.time())
    meta = wh.normalize_wa_payload(_status_payload(CLIENT, "delivered", now, "w1"), OUR)
    d360 = wh.normalize_d360_v1_payload({"statuses": [
        {"id": "w2", "recipient_id": CLIENT, "status": "read", "timestamp": str(now)}]})
    ok(meta and meta[0]["type"] == wk.RECEIPT_TYPE, "Meta метит квитанцию тем же значением")
    ok(d360 and d360[0]["type"] == wk.RECEIPT_TYPE, "360dialog метит квитанцию тем же значением")


def test_window_door_and_kind_agree_on_the_same_axes():
    """Живая дверь окна суток фильтрует ровно по тем осям, по которым здесь решается вид."""
    import inspect
    import wa_send
    src = inspect.getsource(wa_send.last_inbound_ts)
    ok("echo = 0" in src, "дверь окна судит по echo — та же ось")
    ok("msg_type <> 'status'" in src, "и по msg_type='status' — тот же различитель квитанции")


def test_decision_module_has_no_imports():
    """Чистота решения: ни базы, ни сети, ни часов (страж WA_KIND_PURE — в гейте)."""
    import ast
    src = open("/root/turbobaby-manager-bot/wa_kind.py", encoding="utf-8").read()
    imports = [n for n in ast.walk(ast.parse(src))
               if isinstance(n, (ast.Import, ast.ImportFrom))]
    ok(not imports, "импортов ноль (нашли " + str(len(imports)) + ")")


def test_pull_still_deletes_nothing():
    """Прибавка полей не завела удаления: строка живёт тремя метками, как жила."""
    import ast
    src = open("/root/turbobaby-manager-bot/wa_webhook.py", encoding="utf-8").read()
    bad = []
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
           and node.func.attr in ("execute", "executemany") and node.args:
            arg = node.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                sql = arg.value.strip().upper()
                if sql.startswith(("DELETE", "DROP", "TRUNCATE")):
                    bad.append(sql[:40])
    ok(not bad, "среди уходящего в execute нет DELETE/DROP/TRUNCATE (" + str(bad) + ")")


# ═══ (7) КОНЕЦ-В-КОНЕЦ ЧЕРЕЗ HTTP — та дверь, которой пользуется ПК ═══════════════════

def test_end_to_end_over_http():
    """Замер не функции, а ЦЕЛОГО пути: HTTP → подпись → нормализация → очередь → забор → JSON.

    Прежние секции судят `db.pull()` напрямую; здесь поднимается ЖИВОЙ сервер тем же
    `make_server`, каким его поднимает боевой юнит, и с ним говорят по настоящему HTTP —
    иначе HTTP-слой (подпись, маршрут, сериализация ответа) остался бы непроверенным, а
    именно он стоит между ПК и решением о виде.

    Боевая очередь не открывается: своя база, порт даёт ОС (0 → свободный), секреты свои.
    """
    import hmac
    import hashlib
    import threading
    import urllib.request

    secret, pull_secret = "e2e_app_secret", "e2e_pull_secret"
    fd, dbpath = tempfile.mkstemp(suffix=".db", prefix="wa_e2e_")
    os.close(fd)

    server = wh.make_server({
        "verify_token": "e2e_verify", "app_secret": secret, "phone_id": OUR,
        "queue_db": dbpath, "port": 0, "bind_host": "127.0.0.1",
        "d360_path_secret": "", "pull_secret": pull_secret,
    })
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        now = int(time.time())

        def post(payload):
            body = json.dumps(payload).encode()
            sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
            req = urllib.request.Request(
                "http://127.0.0.1:%d/wa-webhook" % port, data=body,
                headers={"Content-Type": "application/json", "X-Hub-Signature-256": sig})
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status

        sent = [
            post(_msg_payload(OUR, "Байк свободен", now, "e2e.echo")),
            post(_msg_payload(CLIENT, "Здравствуйте", now - 3 * 86400, "e2e.hist")),
            post(_status_payload(CLIENT, "delivered", now, "e2e.rcpt")),
            post(_msg_payload(CLIENT, None, now, "e2e.unk", mtype="reaction")),
            post(_msg_payload(CLIENT, "Привет, есть байк?", now, "e2e.real")),
        ]
        ok(sent == [200] * 5, "все пять событий приняты дверью вебхука (" + str(sent) + ")")

        with urllib.request.urlopen(
                "http://127.0.0.1:%d/wa-queue/pull/%s" % (port, pull_secret), timeout=5) as r:
            out = json.loads(r.read().decode())

        ok(out["ok"] and out["count"] == 5, "дверь забора выдала все пять записей")
        items = out["items"]
        ok(all("echo" in i and "history" in i and "msg_type" in i for i in items),
           "выдача забора несёт эхо, историю и msg_type — по HTTP, а не только в памяти")

        by_type = {i["msg_type"]: i for i in items}
        ok(by_type["status"]["kind"] == wk.KIND_RECEIPT
           and by_type["status"]["disposition"] == wk.DISP_DROP,
           "квитанция не считается входящим: receipt / drop")
        ok(by_type["reaction"]["kind"] == wk.KIND_UNKNOWN
           and by_type["reaction"]["disposition"] != wk.DISP_CARD,
           "неопознанное не становится входящим: unknown, карточки нет")

        cards = [i for i in items if i["disposition"] == wk.DISP_CARD]
        ok(len(cards) == 1 and cards[0]["from"] == CLIENT,
           "карточку рождает РОВНО одно событие из пяти — настоящее сообщение клиента")
        ok(all(all(k in i for k in _OLD_KEYS) for i in items),
           "прежние семь ключей целы и по HTTP — прибавка, а не замена")
    finally:
        server.shutdown()
        server.server_close()
        os.remove(dbpath)


def _run_all():
    tests = [
        test_four_kinds_by_fields,
        test_receipt_decided_by_one_field_not_by_text,
        test_receipt_survives_junk_neighbours,
        test_receipt_gives_neither_card_nor_context,
        test_echo_beats_history,
        test_unknown_type_is_not_inbound,
        test_empty_type_is_unknown,
        test_unreadable_flag_is_unknown,
        test_flag_forms_that_are_readable,
        test_kind_always_returns_a_known_kind,
        test_negative_looks_like_client_but_is_not,
        test_negative_receipt_text_is_not_a_client_message,
        test_echo_and_history_reach_the_pull_door,
        test_old_seven_keys_intact,
        test_new_keys_use_table_names,
        test_msg_type_and_legacy_type_cannot_diverge,
        test_pull_output_is_json_serialisable,
        test_row_with_unrecognised_type_is_unknown_not_inbound,
        test_null_flags_are_forbidden_by_the_table_itself,
        test_media_types_are_a_subset_of_inbound_types,
        test_receipt_type_matches_what_normalisation_writes,
        test_window_door_and_kind_agree_on_the_same_axes,
        test_decision_module_has_no_imports,
        test_pull_still_deletes_nothing,
        test_end_to_end_over_http,
    ]
    for t in tests:
        try:
            t()
        except Exception as e:
            ok(False, f"{t.__name__}: EXCEPTION {e}")
    passed = sum(res)
    total = len(res)
    print(f"\n{'OK' if passed == total else 'FAIL'} {passed}/{total}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(_run_all())
