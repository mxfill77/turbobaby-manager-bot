"""ДЕДУП ПОСТАНОВКИ ЗАДАЧИ — КЛЮЧ, А НЕ «ТЕКСТ В ОКНЕ» (класс дублей, 02.08.2026).

ЖИВОЙ ФАКТ (сверка по живым данным, журнал ПК-контура 02.08 17:12 UTC): из восьми
подозрений на дубль реальными оказались ДВЕ пары — и обе в очереди задач: 164/165
(текст побайтно одинаков, 43 с порознь) и 167/168 (46 с порознь). Владелец отправлял
каждую по одному разу. По деньгам реальных дублей НОЛЬ.
МЕХАНИЗМ РАЗНИЦЫ: addTransaction/addEvent (BotData.js:468/508) сверяют msg_id —
тот же ключ → {ok:true, duplicate:true} и второй строки нет; enqueueTask_ (BotData.js:290)
ключа дедупа НЕ ИМЕЕТ вовсе, поэтому вторая отправка становится второй задачей.

ЧТО ПРОВЕРЯЕМ (красный до правки, зелёный после):
 (1) одна постановка, две отправки в узком окне (наши живые 43 с) → ОДНА задача;
 (2) ОСОЗНАННЫЙ ПОВТОР ВЛАДЕЛЬЦА (тот же текст, ДРУГОЕ сообщение) → две задачи;
 (3) без ключа (синтетика демона) → байт-в-байт прежнее поведение, поля ключа в теле нет;
 (4) окно истекло → постановка проходит (стор не держит вечно);
 (5) провал постановки НЕ запоминается → verify+повтор надёжной постановки цел;
 (6) стор на диске → переживает рестарт процесса (новый клиент видит ключ);
 (7) битый стор → постановка НЕ падает и НЕ теряется (fail-open);
 (8) изоляция проб: тест-прогон в боевой стор не пишет НИКОГДА;
 (9) e2e devbot: то же сообщение владельца дважды → одна задача; другое сообщение → две.

ПОЧЕМУ КЛЮЧ, А НЕ ТЕКСТ+ОКНО: 43 и 46 с — ровно тот масштаб, на котором владелец руками
повторяет упавшую задачу. Дедуп по тексту в окне съел бы осознанный повтор молча; ключ
(«то же сообщение») пропускает его всегда — это и проверяет кейс (2).

СОВМЕСТИМОСТЬ ЗАМЕРА: вызовы идут через _enq/_try — обёртки ловят TypeError на старой
сигнатуре без ключа и зовут прежнюю форму. Тест меряет ПОВЕДЕНИЕ (сколько задач родилось),
а не наличие параметра: до правки он красный по числу задач, а не по трассировке.
Сети нет: _post подменён; стор — во временном каталоге прогона.
"""
import os
import sys
import json
import time
import shutil
import tempfile

sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x/exec")
os.environ.setdefault("BRIDGE_TOKEN", "T")
os.environ["THEATER_ROUTER"] = "0"          # роутер театра в этом тесте не участвует
_STORE_DIR = tempfile.mkdtemp(prefix="tb_enqdedup_")
_LIVE_STORE = "/root/turbobaby-manager-bot/enqueue_dedup.json"
# ИЗОЛЯЦИЯ ПРОБ (класс 01.08): канал персиста мокается ВСЕГДА и ПЕРВЫМ — иначе тест-ключи
# легли бы в боевой стор и живая постановка могла бы схлопнуться о чужой прогон.
os.environ["ENQUEUE_DEDUP_FILE"] = os.path.join(_STORE_DIR, "store.json")

import bridge_client as BC                                        # noqa: E402
from bridge_client import BridgeClient                            # noqa: E402
import devbot as DB                                               # noqa: E402


def ok(c, l):
    print(("  PASS " if c else "  FAIL ") + l)
    return c


res = []


class FakeQueue:
    """Мост-заглушка: считает отправки enqueue и раздаёт id по порядку (как appendRow)."""
    def __init__(s, first_id=164, fail_times=0):
        s.posts, s.next_id, s.fail_times = [], first_id, fail_times

    def post(s, action, **fields):
        s.posts.append((action, dict(fields)))
        if s.fail_times > 0:
            s.fail_times -= 1
            return {"ok": False, "error": "receipt_unknown", "outcome": "unknown"}
        i = s.next_id
        s.next_id += 1
        return {"ok": True, "id": i}


def client(q):
    c = BridgeClient(url="http://x/exec", token="T")
    c._post = q.post
    return c


def _enq(c, frm, text, key=None):
    """Постановка с ключом; старая сигнатура (без ключа) → прежняя форма вызова."""
    try:
        return c.enqueue_task(frm, text, dedup_key=key)
    except TypeError:
        return c.enqueue_task(frm, text)


def _fresh_store():
    p = os.environ["ENQUEUE_DEDUP_FILE"]
    for suffix in ("", ".lock", ".tmp"):
        try:
            os.remove(p + suffix)
        except OSError:
            pass


# ---- (1) одна постановка, две отправки в узком окне → одна задача ----
print("(1) две отправки одной постановки в окне 43 с:")
_fresh_store()
q = FakeQueue()
c = client(q)
KEY = "tg:-1003853365891:9241"          # то же сообщение владельца (форма ключа devbot)
TEXT = "тз: проверь дедуп постановки задачи"
r1 = _enq(c, "Filipp-328-dev", TEXT, KEY)
r2 = _enq(c, "Filipp-328-dev", TEXT, KEY)   # 43 с спустя — в стор время не идёт, окно 600 с
ids = {r1.get("id"), r2.get("id")}
res.append(ok(len(q.posts) == 1, f"отправка в мост РОВНО одна (было {len(q.posts)}) — вторая задача не родилась"))
res.append(ok(r1.get("ok") and r2.get("ok") and ids == {164}, f"обе постановки успешны и указывают на ОДНУ задачу 164 (ids={ids})"))
res.append(ok(r2.get("duplicate") is True, "повтор помечен duplicate — форма как у транзакций/событий"))

# ---- (2) осознанный повтор владельца: тот же текст, ДРУГОЕ сообщение ----
print("(2) осознанный повтор владельца (новое сообщение, тот же текст):")
q = FakeQueue()
c = client(q)
_fresh_store()
a = _enq(c, "Filipp-328-dev", TEXT, "tg:-1003853365891:9301")
b = _enq(c, "Filipp-328-dev", TEXT, "tg:-1003853365891:9302")   # владелец повторил руками
res.append(ok(len(q.posts) == 2 and a.get("id") != b.get("id"),
              f"две задачи ({a.get('id')} и {b.get('id')}) — повтор владельца НЕ съеден"))
res.append(ok(not b.get("duplicate"), "второй постановке дубль не приписан"))

# ---- (3) без ключа → прежнее поведение байт-в-байт ----
print("(3) постановка без ключа (синтетика демона):")
q = FakeQueue()
c = client(q)
_fresh_store()
_enq(c, "Filipp-328-dec", "[шаг 1/3 родитель 500] сделай дело")
_enq(c, "Filipp-328-dec", "[шаг 1/3 родитель 500] сделай дело")
res.append(ok(len(q.posts) == 2, "две отправки как раньше (дедуп без ключа не включается)"))
res.append(ok(all("dedup_key" not in f for _, f in q.posts),
              "в теле запроса поля ключа НЕТ — форма прежняя (совместимость с мостом и тестами полосы)"))

# ---- (4) окно истекло ----
print("(4) окно истекло:")
q = FakeQueue()
c = client(q)
_fresh_store()
os.environ["ENQUEUE_DEDUP_WINDOW"] = "0.3"
_enq(c, "Filipp-328", "задача: посмотри логи", "tg:1:77")
time.sleep(0.45)
_enq(c, "Filipp-328", "задача: посмотри логи", "tg:1:77")
os.environ["ENQUEUE_DEDUP_WINDOW"] = "600"
res.append(ok(len(q.posts) == 2, "за окном ключ не держит — постановка проходит"))

# ---- (5) провал не запоминается: verify+повтор надёжной постановки цел ----
print("(5) провал постановки не запоминается:")
q = FakeQueue(first_id=200, fail_times=1)
c = client(q)
_fresh_store()
f1 = _enq(c, "Filipp-328-dev", "тз: сбойная постановка", "tg:1:88")
f2 = _enq(c, "Filipp-328-dev", "тз: сбойная постановка", "tg:1:88")
res.append(ok(not f1.get("ok") and f2.get("ok") and len(q.posts) == 2,
              "после неизвестного исхода повтор УХОДИТ в мост (потерять задачу хуже, чем продублировать)"))

# ---- (6) стор на диске переживает рестарт процесса ----
print("(6) персист:")
q = FakeQueue(first_id=300)
c = client(q)
_fresh_store()
_enq(c, "Filipp-328", "задача: персист", "tg:1:99")
on_disk = os.path.exists(os.environ["ENQUEUE_DEDUP_FILE"])
q2 = FakeQueue(first_id=400)
c2 = client(q2)                                  # «новый процесс» — общий стор на диске
r = _enq(c2, "Filipp-328", "задача: персист", "tg:1:99")
res.append(ok(on_disk and len(q2.posts) == 0 and r.get("id") == 300,
              "ключ живёт на диске: после рестарта та же постановка не рождает вторую задачу"))

# ---- (7) битый стор → постановка не падает ----
print("(7) битый стор (fail-open):")
q = FakeQueue(first_id=500)
c = client(q)
with open(os.environ["ENQUEUE_DEDUP_FILE"], "w", encoding="utf-8") as f:
    f.write("{это не json")
r = _enq(c, "Filipp-328", "задача: битый стор", "tg:1:111")
res.append(ok(r.get("ok") and r.get("id") == 500 and len(q.posts) == 1,
              "стор нечитаем → постановка идёт как прежде (дедуп молча выключен, задача не потеряна)"))

# ---- (8) изоляция проб: боевой стор не тронут ----
print("(8) изоляция проб:")
res.append(ok(not os.path.exists(_LIVE_STORE) or os.path.getmtime(_LIVE_STORE) < time.time() - 5,
              "боевой стор прогоном не создан и не переписан"))
_saved = os.environ.pop("ENQUEUE_DEDUP_FILE")
os.environ["ORCH_TEST_MODE"] = "1"
default_path = BC._dedup_file() if hasattr(BC, "_dedup_file") else _LIVE_STORE
os.environ["ENQUEUE_DEDUP_FILE"] = _saved
res.append(ok(default_path != _LIVE_STORE,
              f"даже без подмены пути тест-прогон метит в свой файл ({os.path.basename(str(default_path))}) — второй пояс"))

# ---- (9) e2e devbot: то же сообщение владельца дважды ----
print("(9) e2e через постановку из темы:")


def _try(text, bridge, lane, key):
    """e2e-постановка с ключом сообщения; старая сигнатура → прежняя форма."""
    try:
        return DB._try_enqueue(text, bridge, lane, key)
    except TypeError:
        return DB._try_enqueue(text, bridge, lane)


# мост — НАСТОЯЩИЙ клиент с подменённым транспортом (в проде devbot получает именно его):
# так проверяется весь путь ключа «сообщение → постановка из темы → тело запроса».
_fresh_store()
q = FakeQueue()
b = client(q)
card1 = _try("тз: почини дедуп постановки", b, "vps", "tg:-1003853365891:9241")
card2 = _try("тз: почини дедуп постановки", b, "vps", "tg:-1003853365891:9241")
res.append(ok(len(q.posts) == 1, f"мост дёрнут один раз (было {len(q.posts)}) — пары 164/165 больше не будет"))
res.append(ok("164" in (card1 or "") and "164" in (card2 or "") and "165" not in (card2 or ""),
              "обе карточки владельцу называют ОДНУ задачу 164"))

_fresh_store()
q2 = FakeQueue()
b2 = client(q2)
c1 = _try("тз: почини дедуп постановки", b2, "vps", "tg:-1003853365891:9401")
c2 = _try("тз: почини дедуп постановки", b2, "vps", "tg:-1003853365891:9402")
res.append(ok(len(q2.posts) == 2 and "165" in (c2 or ""),
              "осознанный повтор владельца из темы проходит — вторая задача поставлена"))

shutil.rmtree(_STORE_DIR, ignore_errors=True)
print(f"\nИТОГО: {sum(res)}/{len(res)}")
sys.exit(0 if all(res) else 1)
