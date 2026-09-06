#!/usr/bin/env python3
"""WA-1: тесты отправляющей двери (`wa_send.py`).

СЕТИ ЗДЕСЬ НЕТ НИ В ОДНОМ ТЕСТЕ, и это не обещание, а устройство: единственный шов к сети —
`wa_send._post`, и он либо подменён поддельным транспортом, либо подменён ЛОВУШКОЙ, которая
роняет тест при первом же касании. Секция (7) как раз про ловушку: она доказывает, что все
пути отказа (дверь выключена / ключ-заполнитель / окно закрыто / окно неизвестно) до сети НЕ
ДОХОДЯТ — а не «доходят, но безобидно».

Разделы:
  (1) ручка двери           — по умолчанию закрыта
  (2) ключ                  — пусто/заполнитель/годен, и значение НЕ течёт в текст причины
  (3) окно 24 часа          — открыто / закрыто / неизвестно (три исхода, разные слова)
  (4) разбор ответа сервера — sent / not_sent / unknown и «повторять ли»
  (5) отправка              — успех, повтор на 5xx, отсутствие повтора на 4xx, молчание
  (6) последнее входящее    — живая временная база: эхо и статусы окном не считаются
  (7) ноль обращений к сети на путях отказа + общий бюджет
  (8) границы               — транзит остаётся транзитом: вебхук эту дверь не импортирует
"""

import os
import sys
import sqlite3
import tempfile
import time

REPO = "/root/turbobaby-manager-bot"
sys.path.insert(0, REPO)
os.environ["PRETOOL_NOPUSH"] = "1"

import wa_send as S

res = []


def ok(cond, label):
    print(("  PASS " if cond else "  FAIL ") + label)
    res.append(bool(cond))
    return bool(cond)


class _Trap:
    """Транспорт, который не должен быть вызван ни разу."""

    def __init__(self):
        self.calls = 0

    def __call__(self, *a, **kw):
        self.calls += 1
        raise AssertionError("к сети обратились там, где обращаться нельзя")


class _Fake:
    """Поддельный транспорт: отдаёт заранее записанные ответы по очереди."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = []
        self.keys = []

    def __call__(self, url, payload, key, timeout):
        self.calls.append({"url": url, "payload": payload, "timeout": timeout})
        self.keys.append(key)
        return self.answers[min(len(self.calls) - 1, len(self.answers) - 1)]


def _env(send="1", key="real_key_abcdef0123456789"):
    return {"WA_SEND": send, "WA_360_API_KEY": key}


def _tmp_queue(rows):
    """Временная база очереди со строками (from, echo, msg_type, ts_msg, ts_queued)."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    with sqlite3.connect(path) as conn:
        conn.execute("""CREATE TABLE wa_inbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT, ts_queued INTEGER, channel TEXT,
            from_number TEXT, name TEXT, msg_type TEXT, text TEXT, media_id TEXT,
            ts_msg INTEGER, echo INTEGER DEFAULT 0, history INTEGER DEFAULT 0,
            status TEXT, raw TEXT, wamid TEXT)""")
        for frm, echo, typ, ts_msg, ts_q in rows:
            conn.execute(
                """INSERT INTO wa_inbox (ts_queued, from_number, msg_type, ts_msg, echo)
                   VALUES (?,?,?,?,?)""", (ts_q, frm, typ, ts_msg, echo))
        conn.commit()
    return path


# ─────────────────────────────────────────────────────────────────────────────
print("\n(1) ручка двери — закрыта по умолчанию")

ok(S.send_enabled({}) is False, "переменной нет → дверь закрыта")
ok(S.send_enabled({"WA_SEND": ""}) is False, "пусто → закрыта")
ok(S.send_enabled({"WA_SEND": "0"}) is False, "«0» → закрыта")
ok(S.send_enabled({"WA_SEND": "yes_please"}) is False, "мусор → закрыта (белый список, не чёрный)")
ok(S.send_enabled({"WA_SEND": "1"}) is True, "«1» → открыта")
ok(S.send_enabled({"WA_SEND": "TRUE"}) is True, "«TRUE» → открыта (регистр не важен)")


# ─────────────────────────────────────────────────────────────────────────────
print("\n(2) ключ — годность и НЕПРОТЕКАНИЕ значения")

ok(S.key_usable("")[0] is False, "пустой ключ не годен")
ok(S.key_usable(None)[0] is False, "None не годен")
ok(S.key_usable("   ")[0] is False, "пробелы не ключ")
for bad in ("PLACEHOLDER", "placeholder", "wa-PLACEHOLDER-key", "CHANGEME", "TODO_set_me",
            "your_key_here", "DUMMY123"):
    ok(S.key_usable(bad)[0] is False, "заполнитель не годен: " + bad[:14])
ok(S.key_usable("k7Fq2mZp9Lx4Tn8VbR3s")[0] is True, "похожий на настоящий ключ годен")

SECRET = "sUpErSeCrEt_KEY_9911"
_, why = S.key_usable("PLACEHOLDER")
ok(SECRET not in why, "причина отказа не несёт постороннего значения")
r = S.send_text("66812345678", "привет", env=_env(key=SECRET + "PLACEHOLDER"),
                transport=_Trap())
ok(SECRET not in r["reason"],
   "значение ключа НЕ попало в причину отказа (искали дословно) — " + r["reason"][:60])
ok(r["outcome"] == S.NOT_SENT, "ключ-заполнитель → not_sent")


# ─────────────────────────────────────────────────────────────────────────────
print("\n(3) окно 24 часа — три исхода, и слова у них разные")

NOW = 1_700_000_000.0
st, info = S.window_state(NOW - 3600, NOW)
ok(st == S.WINDOW_OPEN, "час назад писал → окно ОТКРЫТО")
st, info = S.window_state(NOW - 86399, NOW)
ok(st == S.WINDOW_OPEN, "23:59:59 назад → ещё открыто")
st, info = S.window_state(NOW - 86401, NOW)
ok(st == S.WINDOW_CLOSED, "24:00:01 назад → ЗАКРЫТО")
st, _ = S.window_state(None, NOW)
ok(st == S.WINDOW_UNKNOWN, "записи нет → НЕИЗВЕСТНО (не «закрыто»)")
st, _ = S.window_state(0, NOW)
ok(st == S.WINDOW_UNKNOWN, "ноль → неизвестно")
st, _ = S.window_state("не-число", NOW)
ok(st == S.WINDOW_UNKNOWN, "мусор → неизвестно")
st, _ = S.window_state(NOW + 60, NOW)
ok(st == S.WINDOW_OPEN, "метка на минуту вперёд — дрожание часов, окно открыто")
st, _ = S.window_state(NOW + 99999, NOW)
ok(st == S.WINDOW_UNKNOWN, "метка далеко в будущем → неизвестно, а не «свежайшее»")


# ─────────────────────────────────────────────────────────────────────────────
print("\n(4) разбор ответа сервера")

o, why, wamid, retry = S.classify_response(200, '{"messages":[{"id":"wamid.XYZ"}]}')
ok(o == S.SENT and wamid == "wamid.XYZ" and retry is False, "200 + id → sent, без повтора")
o, why, wamid, retry = S.classify_response(200, '{"messages":[]}')
ok(o == S.UNKNOWN and retry is False, "200 без id → unknown (успехом не зовём)")
o, why, wamid, retry = S.classify_response(200, "не json")
ok(o == S.UNKNOWN, "200 с нечитаемым телом → unknown")
o, why, _, retry = S.classify_response(400, '{"error":{"message":"bad number"}}')
ok(o == S.NOT_SENT and retry is False, "400 → not_sent и повторять нечего")
ok("bad number" in why, "слова API об отказе доехали дословно: " + why[:50])
o, _, _, retry = S.classify_response(401, "{}")
ok(o == S.NOT_SENT and retry is False, "401 → not_sent, без повтора")

# Промах разбора тела ЗВУЧИТ, а не притворяется молчанием сервера (храповик слепых читателей).
_, why_nojson, _, _ = S.classify_response(400, "<html>502 Bad Gateway</html>")
ok("не разобран" in why_nojson, "тело пришло, но не JSON → сказано прямо: " + why_nojson[:60])
_, why_silent, _, _ = S.classify_response(400, "")
ok("не разобран" not in why_silent,
   "тела нет вовсе → о разборе молчим (пусто здесь значит «сервер ничего не сказал»)")
ok(why_nojson != why_silent, "наша слепота и молчание сервера звучат ПО-РАЗНОМУ")
_, why_notobj, _, _ = S.classify_response(400, '["список, а не объект"]')
ok("не разобран" in why_notobj, "JSON не-объект → тоже названо")
o, _, _, retry = S.classify_response(429, "{}")
ok(o == S.NOT_SENT and retry is True, "429 → not_sent, но повторить стоит")
o, _, _, retry = S.classify_response(500, "{}")
ok(o == S.UNKNOWN and retry is True, "500 → unknown (могло быть принято) + повтор")
o, _, _, retry = S.classify_response(503, "{}")
ok(o == S.UNKNOWN and retry is True, "503 → unknown + повтор")
o, why, _, retry = S.classify_response(None, "", err="timeout")
ok(o == S.UNKNOWN and retry is True, "молчание транспорта → unknown + повтор")
ok("мог долететь" in why, "и сказано прямо, что запрос мог долететь")

ok(S.backoff_delay(1) == 0.0, "первая попытка без паузы")
ok(S.backoff_delay(2) == 1.0 and S.backoff_delay(3) == 2.0, "паузы растут вдвое: 1 с, 2 с")


# ─────────────────────────────────────────────────────────────────────────────
print("\n(5) отправка")

db_open = _tmp_queue([("66812345678", 0, "text", int(NOW - 600), int(NOW - 600))])

fake = _Fake([(200, '{"messages":[{"id":"wamid.OK1"}]}', None)])
r = S.send_text("66812345678", "привет", now=NOW, db_path=db_open, env=_env(), transport=fake)
ok(r["outcome"] == S.SENT, "окно открыто, сервер принял → sent")
ok(r["wamid"] == "wamid.OK1", "идентификатор сообщения возвращён")
ok(r["attempts"] == 1, "одна попытка при успехе")
ok(r["verify"] is False, "при sent перечитывать нечего")
ok(fake.calls[0]["url"].startswith("https://waba-v2.360dialog.io"),
   "адрес production 360dialog: " + fake.calls[0]["url"])
ok(fake.calls[0]["payload"]["type"] == "text", "тип сообщения text")
ok(fake.calls[0]["payload"]["text"]["body"] == "привет", "текст доехал дословно")
ok(fake.calls[0]["payload"]["to"] == "66812345678", "получатель тот")
ok(fake.keys[0] == "real_key_abcdef0123456789", "ключ ушёл в заголовок D360-API-KEY")

slept = []
fake = _Fake([(500, "{}", None), (200, '{"messages":[{"id":"wamid.OK2"}]}', None)])
r = S.send_text("66812345678", "привет", now=NOW, db_path=db_open, env=_env(),
                transport=fake, sleep=slept.append)
ok(r["outcome"] == S.SENT and r["attempts"] == 2, "500 → повтор → sent со второй попытки")
ok(slept == [1.0], "перед второй попыткой пауза 1 с (бэкофф): " + str(slept))

fake = _Fake([(400, '{"error":{"message":"invalid recipient"}}', None)])
r = S.send_text("66812345678", "привет", now=NOW, db_path=db_open, env=_env(),
                transport=fake, sleep=slept.append)
ok(r["outcome"] == S.NOT_SENT and r["attempts"] == 1,
   "400 → РОВНО одна попытка: отказ вынес сам сервер, повтор бессмыслен")

fake = _Fake([(None, "", "timeout")])
r = S.send_text("66812345678", "привет", now=NOW, db_path=db_open, env=_env(),
                transport=fake, sleep=lambda s: None)
ok(r["outcome"] == S.UNKNOWN, "молчание на всех попытках → unknown")
ok(r["attempts"] == S.MAX_ATTEMPTS, "исчерпаны все попытки: " + str(r["attempts"]))
ok(r["verify"] is True, "unknown несёт требование выяснить, ушло ли — вслепую не повторять")

r = S.send_text("", "привет", now=NOW, db_path=db_open, env=_env(), transport=_Trap())
ok(r["outcome"] == S.NOT_SENT, "пустой получатель → not_sent без сети")
r = S.send_text("66812345678", "   ", now=NOW, db_path=db_open, env=_env(), transport=_Trap())
ok(r["outcome"] == S.NOT_SENT, "пустой текст → not_sent без сети")


# ─────────────────────────────────────────────────────────────────────────────
print("\n(6) последнее входящее — контракт читателя, а не голый нуль")

db = _tmp_queue([
    ("66812345678", 0, "text",   int(NOW - 5000), int(NOW - 5000)),
    ("66812345678", 0, "text",   int(NOW - 1000), int(NOW - 1000)),   # свежее
    ("66812345678", 1, "text",   int(NOW - 10),   int(NOW - 10)),     # эхо — НЕ клиент
    ("66812345678", 1, "status", int(NOW - 5),    int(NOW - 5)),      # квитанция — НЕ клиент
    ("66899999999", 0, "text",   int(NOW - 20),   int(NOW - 20)),     # другой номер
])
r6 = S.last_inbound_ts("66812345678", db)
ok(r6.ok and r6.payload == int(NOW - 1000),
   "берётся САМОЕ СВЕЖЕЕ входящее клиента, эхо и статусы не в счёт")
ok(r6.scanned == 2, "осмотрено ровно 2 входящих клиента (эхо и статус не считаны): "
                    + str(r6.scanned))
ok(S.last_inbound_ts("66899999999", db).payload == int(NOW - 20), "у соседнего номера своя метка")

# ГЛАВНОЕ РАЗЛИЧЕНИЕ, ради которого заведён контракт: «посмотрели, пусто» ≠ «не посмотрели».
empty = S.last_inbound_ts("66800000000", db)
unread = S.last_inbound_ts("66812345678", "/tmp/нет-такой-базы-wa.db")
ok(empty.outcome == "empty", "незнакомый номер → empty (ОСМОТРЕЛИ, входящих нет)")
ok(unread.outcome == "unreadable", "базы нет → unreadable (осмотра НЕ БЫЛО)")
ok(empty.outcome != unread.outcome,
   "слепота читателя и пустая выборка — РАЗНЫЕ исходы, а не общий None")
ok(empty.payload is None and unread.payload is None,
   "метки нет в обоих — потому и нельзя было различать их по возвращённому значению")
ok("не прочитан" in unread.say(), "и «не прочитан» произносится вслух: " + unread.say())
ok(S.last_inbound_ts("", db).outcome == "empty", "пустой номер → empty, не падение")

db_zero = _tmp_queue([("66812345678", 0, "text", 0, int(NOW - 300))])
ok(S.last_inbound_ts("66812345678", db_zero).payload == int(NOW - 300),
   "ts_msg пуст → берём время приёма, а не ноль")


# ─────────────────────────────────────────────────────────────────────────────
print("\n(7) ноль обращений к сети на путях отказа + бюджет")

db_closed = _tmp_queue([("66812345678", 0, "text", int(NOW - 200000), int(NOW - 200000))])

trap = _Trap()
r = S.send_text("66812345678", "привет", now=NOW, db_path=db_open,
                env=_env(send="0"), transport=trap)
ok(r["outcome"] == S.NOT_SENT and trap.calls == 0, "дверь выключена → 0 обращений к сети")
ok("выключена" in r["reason"], "и сказано, что именно выключено: " + r["reason"][:50])

trap = _Trap()
r = S.send_text("66812345678", "привет", now=NOW, db_path=db_open,
                env=_env(key="PLACEHOLDER"), transport=trap)
ok(r["outcome"] == S.NOT_SENT and trap.calls == 0, "ключ-заполнитель → 0 обращений к сети")

trap = _Trap()
r_closed = S.send_text("66812345678", "привет", now=NOW, db_path=db_closed,
                       env=_env(), transport=trap)
ok(r_closed["outcome"] == S.NOT_SENT and trap.calls == 0,
   "окно закрыто → 0 обращений к сети (отказываем САМИ, а не «спросим сервер»)")
ok(r_closed["window"] == S.WINDOW_CLOSED, "исход окна назван: closed")
ok("окно закрыто" in r_closed["reason"] and "шаблоны не шлём" in r_closed["reason"],
   "формулировка ТЗ дословно: " + r_closed["reason"][:70])

trap = _Trap()
db_none = _tmp_queue([])
r_unk = S.send_text("66812345678", "привет", now=NOW, db_path=db_none,
                    env=_env(), transport=trap)
ok(r_unk["outcome"] == S.NOT_SENT and trap.calls == 0, "окно неизвестно → 0 обращений к сети")
ok(r_unk["window"] == S.WINDOW_UNKNOWN, "исход окна назван: unknown")
ok(r_unk["reason"] != r_closed["reason"],
   "«неизвестно» и «закрыто» звучат ПО-РАЗНОМУ — незнание не выдаётся за измерение")
ok("НЕ «окно закрыто»" in r_unk["reason"], "и разница названа прямо: " + r_unk["reason"][:70])

trap = _Trap()
r = S.send_text("66812345678", "привет", now=NOW, db_path=db_open, env=_env(),
                transport=trap, budget=0.0)
ok(trap.calls == 0, "бюджет 0 → к сети не обращались ВООБЩЕ")
ok(r["outcome"] == S.UNKNOWN and r["attempts"] == 0, "и это unknown с нулём попыток")

# бюджет режет плечо: остаток меньше LEG_TIMEOUT_SEC → в транспорт уходит остаток
fake = _Fake([(200, '{"messages":[{"id":"w1"}]}', None)])
S.send_text("66812345678", "привет", now=NOW, db_path=db_open, env=_env(),
            transport=fake, budget=3.0)
ok(fake.calls[0]["timeout"] <= 3.0,
   "плечо урезано остатком общего бюджета: " + str(round(fake.calls[0]["timeout"], 2)))

# подставленное «сейчас» не съедает бюджет: часы дедлайна СВОИ
fake = _Fake([(200, '{"messages":[{"id":"w2"}]}', None)])
r = S.send_text("66812345678", "привет", now=1.0, db_path=_tmp_queue(
    [("66812345678", 0, "text", 0, 0)]), env=_env(), transport=fake)
ok(r["attempts"] >= 1 or r["window"] != S.WINDOW_OPEN,
   "фальшивое «сейчас» не обнуляет бюджет отправки (дедлайн на своих часах)")


# ─────────────────────────────────────────────────────────────────────────────
print("\n(8) границы — транзит остаётся транзитом")

src = open(os.path.join(REPO, "wa_webhook.py"), encoding="utf-8").read()
ok("import wa_send" not in src and "from wa_send" not in src,
   "wa_webhook НЕ импортирует отправляющую дверь — приёмник не отвечает в WhatsApp")

send_src = open(os.path.join(REPO, "wa_send.py"), encoding="utf-8").read()
ok(send_src.count("urlopen") == 1,
   "выход в сеть РОВНО один (_post) — иначе подмена транспорта не гарантировала бы тишины")
ok("template" not in send_src.lower(),
   "шаблонов Meta дверь не умеет вовсе — вне окна отказ, а не обход правила")

import wa_webhook as W
ok(getattr(W, "send_text", None) is None, "у приёмника нет отправляющей функции")


# ─────────────────────────────────────────────────────────────────────────────
for p in (db, db_open, db_closed, db_none, db_zero):
    try:
        os.remove(p)
    except OSError:
        pass

print("\nИтог: %d/%d PASS" % (sum(res), len(res)))
fails = sum(1 for r in res if not r)
if fails:
    print("FAIL: %d тест(а/ов) не прошли" % fails)
    sys.exit(1)
