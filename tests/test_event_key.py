"""ЗАПРЕТ ПУСТОГО КЛЮЧА У ЗАПИСИ СОБЫТИЯ (класс «строка без свидетеля», 02.08.2026).

ОСНОВАНИЕ: docs/artifacts/2026-08-02-enqueue-dedup.md §5. Сверка ключа на мосту при ПУСТОМ
ключе возвращает ложь — `botMsgExists_`: `if (!msgId) return false` (BotData.js:449-450).
Следствие ровно одно и оно двойное: у записи с пустым ключом НЕТ ни защиты от дубля
(вторая такая же строка ляжет рядом), ни СВИДЕТЕЛЯ (две одинаковые строки потом уже не
отличить от двух настоящих событий). Пустой ключ — это не «дедуп выключен», это «событие
записано анонимно».

ФОРМА ВЗЯТА ОТ ПОСТАНОВКИ (667d314): ключ обязателен у записи, отказ — на КЛИЕНТЕ, до сети.
РАЗНИЦА С ПОСТАНОВКОЙ НАМЕРЕННАЯ: у enqueue пустой ключ = «дедупа нет, поведение прежнее»
(fail-open: потерять задачу владельца хуже, чем продублировать). Здесь наоборот — запись
БЕЗ ключа не проходит, потому что анонимная строка в живом листе хуже ненаписанной: её
нельзя ни сверить, ни отозвать по ключу (`delete_event` тоже работает ТОЛЬКО по точному
ключу и без него отказывает — BotData.js:549, тот же принцип уже стоит на удалении).

ЧТО ПРОВЕРЯЕМ (красный до правки, зелёный после):
 (1) ключа нет вовсе / пусто / None / одни пробелы → записи НЕТ, мост не дёрнут, отказ явный;
 (2) отказ НЕ МОЛЧАЛИВЫЙ: в журнале остаётся свидетель с сутью события (группа/байк/тип/заметка)
     — иначе «не прошло» неотличимо от «прошло» и событие теряется бесследно;
 (3) с ключом — байт-в-байт прежнее поведение: одна отправка, действие и тело не тронуты;
 (4) ЗАКОННЫЕ АВТОМАТИЧЕСКИЕ ЗАПИСИ НЕ СЛОМАНЫ. Записи не от сообщения владельца в проде уже
     есть, и все они несут СИНТЕТИЧЕСКИЙ КОНТЕНТНЫЙ ключ: `info:<номер>:<работа>:<км>`
     (splinter:2062), `odo_audit:<чат>:<тема>:<км>` (splinter:2849), `sp:<чат>:<тема>:<вид>:<км>`
     (splinter:5861). Это и есть замена свидетеля для автоматики — ключ строится из СОДЕРЖАНИЯ
     события, а не из сообщения; повторный прогон той же работы на том же пробеге даёт тот же
     ключ и схлопывается мостом. Кейс проверяет, что все три формы проходят;
 (5) СТРУКТУРНЫЙ ИНВАРИАНТ (страж будущего): ни один живой вызов записи события в splinter.py
     не остаётся без ключа. Читаем разбором (ast), а не подстрокой — новый вызов, забывший
     ключ, красит тест, а не всплывает через месяц строкой без свидетеля в листе.

ДЕНЬГИ ЗДЕСЬ НЕ УЧАСТВУЮТ — ни вызовом, ни импортом: у проводок свой ключ и свой объектный
гейт, эта правка их не касается (сверено чтением: тело метода проводки не тронуто диффом).
Сети нет: транспорт клиента подменён заглушкой, наружу не уходит ничего.
"""
import os
import re
import ast
import sys
import logging

sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x/exec")
os.environ.setdefault("BRIDGE_TOKEN", "T")

from bridge_client import BridgeClient                              # noqa: E402

SPLINTER = "/root/turbobaby-manager-bot/splinter.py"


def ok(c, l):
    print(("  PASS " if c else "  FAIL ") + l)
    return c


res = []


class FakeBridge:
    """Заглушка транспорта: считает отправки и запоминает тело. Сети нет по построению."""

    def __init__(s):
        s.posts = []

    def post(s, action, **fields):
        s.posts.append((action, dict(fields)))
        return {"ok": True, "saved": True}


def client():
    c = BridgeClient(url="http://x/exec", token="T")
    q = FakeBridge()
    c._post = q.post
    return c, q


class Catcher(logging.Handler):
    """Ловит журнал клиента — свидетель отказа должен быть виден, а не съеден."""

    def __init__(s):
        super().__init__()
        s.lines = []

    def emit(s, rec):
        s.lines.append(rec.getMessage())      # getMessage сам подставляет args


# ── (1) ПУСТОЙ КЛЮЧ ВО ВСЕХ ЖИВЫХ ФОРМАХ → ЗАПИСИ НЕТ ────────────────────────────────────
EMPTY_FORMS = [
    ("ключа нет вовсе", {}),
    ("ключ пустой строкой", {"msg_id": ""}),
    ("ключ None", {"msg_id": None}),
    ("ключ из одних пробелов", {"msg_id": "   "}),
]
for label, extra in EMPTY_FORMS:
    b, q = client()
    kw = dict(group="обслуживание", bike="NMAX 7530", event_type="repair",
              mileage="12450", notes="колодки — 12450 км")
    kw.update(extra)
    r = b.add_event(**kw) or {}
    res.append(ok(len(q.posts) == 0 and r.get("ok") is False,
                  f"{label}: запись НЕ ушла на мост, отказ явный (ok={r.get('ok')})"))
    res.append(ok(str(r.get("error") or "") == "no_msg_id",
                  f"{label}: причина названа кодом no_msg_id (было {r.get('error')!r})"))

# ── (2) ОТКАЗ НЕ МОЛЧАЛИВЫЙ: свидетель в журнале несёт суть события ──────────────────────
cat = Catcher()
lg = logging.getLogger("bridge_client")
lg.addHandler(cat)
lg.setLevel(logging.INFO)
b, q = client()
b.add_event(group="обслуживание / тема 12", bike="ADV 8004", event_type="attendance",
            notes="отметка прихода | t=07:56 UTC")
lg.removeHandler(cat)
witness = "\n".join(cat.lines)
res.append(ok(bool(cat.lines), "отказ оставил след в журнале (свидетель есть)"))
res.append(ok("ADV 8004" in witness and "attendance" in witness,
              "свидетель называет СУТЬ события (байк и тип) — потерянное восстановимо"))

# ── (3) С КЛЮЧОМ — БАЙТ-В-БАЙТ ПРЕЖНЕЕ ПОВЕДЕНИЕ ─────────────────────────────────────────
b, q = client()
body = dict(msg_date="2026-08-02", group="обслуживание / тема 12", bike="NMAX 7530",
            event_type="photo", fuel="half", mileage="12450", photos=1,
            notes="вернулся, фото есть", msg_id="-1002751134848:11091", sender="@Mojojo2547")
r = b.add_event(**body) or {}
res.append(ok(len(q.posts) == 1 and q.posts[0][0] == "add_event",
              "живой ключ сообщения: ровно одна отправка, действие прежнее"))
res.append(ok(q.posts[0][1] == body,
              "тело запроса не тронуто — ни одно поле не добавлено и не переписано"))
res.append(ok(r.get("ok") is True, "ответ моста возвращается как есть"))

b, q = client()
b.add_event(group="г", bike="б", event_type="photo", msg_id=11091)
res.append(ok(len(q.posts) == 1, "ключ числом — законная форма, проходит"))

# ── (4) АВТОМАТИЧЕСКИЕ ЗАПИСИ (не от сообщения владельца) НЕ СЛОМАНЫ ─────────────────────
AUTO_KEYS = [
    ("инфо-работа (контентный ключ)", "info:8004:oil:38982"),
    ("аудит одометра", "odo_audit:-1002751134848:12:38982"),
    ("ТО фаза 2", "sp:-1002751134848:12:brakes:38982"),
]
for label, key in AUTO_KEYS:
    b, q = client()
    b.add_event(group="обслуживание", bike="ADV 8004", event_type="repair",
                mileage="38982", notes="работа", msg_id=key)
    res.append(ok(len(q.posts) == 1 and q.posts[0][1].get("msg_id") == key,
                  f"{label}: синтетический ключ проходит ({key})"))

# ── (5) СТРУКТУРНЫЙ ИНВАРИАНТ: живые вызовы записи события несут ключ ────────────────────
# Разбором, а не подстрокой: имя в комментарии/строке вызовом не является (класс «корень А»).
with open(SPLINTER, encoding="utf-8") as f:
    tree = ast.parse(f.read())
explicit, unpacked, naked = 0, 0, []
for node in ast.walk(tree):
    if not isinstance(node, ast.Call):
        continue
    fn = node.func
    name = fn.attr if isinstance(fn, ast.Attribute) else (fn.id if isinstance(fn, ast.Name) else "")
    if name != "add_event":
        continue
    kws = {k.arg for k in node.keywords}
    if "msg_id" in kws:
        explicit += 1
    elif None in kws:          # **kw — статически не видно; отказ клиента ловит такой случай в бою
        unpacked += 1
    else:
        naked.append(node.lineno)
res.append(ok(not naked,
              f"ни один вызов записи события не остался без ключа (явных {explicit}, "
              f"через ** {unpacked}, голых {naked or 'нет'})"))
res.append(ok(explicit >= 6, f"страж видит живые вызовы с ключом (найдено {explicit}) — "
                             f"инвариант не выродился в пустую проверку"))

# ── (6) ПРОБА НЕ КАСАЕТСЯ ЖИВОГО: транспорт подменён у КАЖДОГО клиента теста ─────────────
# Единственная точка рождения клиента — client(), и она ЖЕ подменяет транспорт: значит
# подменён он у КАЖДОГО клиента прогона (проверяем счётом по своему исходнику, а не верой).
src = open(__file__, encoding="utf-8").read()
ctors = len(re.findall(r"BridgeClient\(", src))
stubs = len(re.findall(r"_post = q\.post", src))
res.append(ok(ctors == 1 and stubs == 1,
              f"клиент рождается в одном месте и там же заглушен (ctors={ctors}, stubs={stubs}) "
              f"— живого транспорта в прогоне нет"))

print(f"\nИТОГО: {sum(res)}/{len(res)}")
sys.exit(0 if all(res) else 1)
