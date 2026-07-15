"""Реестр проверенных фактов куратора — разрыв петли повторных диагностик (15.07.2026).
Проблема: куратор без памяти ставил DNS-разведку ×3 за 10 мин и аудит headless_settings ×3
с противоречивыми вердиктами. Класс: консультация куратора без памяти вердиктов соседних целей.

Проверки:
(1) _vf_normalize: стрипает куратор-маркер, [глубина 2], lowercase, спецсимволы в пробелы,
    пусто/None → None, длинный текст → ≤120
(2) _vf_check / _vf_write: запись и чтение свежей записи, FACT_TTL=0 → устарело, pending читается
(3) _curator_spawn: кэш pending → refused+сообщение, задача НЕ поставлена в bridge
(4) _curator_spawn: кэш с вердиктом → refused «уже подтверждено задачей N в HH:MM UTC»
(5) _curator_spawn: нет кэша → задача поставлена + запись «pending» в реестр
(6) Contradiction: _vf_write с новым ≠ старому → карточка в 328, реестр обновлён; тот же вердикт → тишина
(7) Fail-safe: битый JSON в реестре → _vf_check возвращает None, spawn ставит задачу как без кэша
(8) done-write пути: CURATOR_FROM done → ключ + вердикт в реестр (фикстура без process_new)
(9) CURATOR=0 → _curator_spawn не вызывается вовсе (регресс существующего поведения)
"""
import os
import sys
import json
import shutil
import tempfile
import datetime

sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ["STEP_SELFHEAL"] = "0"
os.environ["PLAN_ADAPT"] = "0"
os.environ["CURATOR"] = "1"

def ok(c, l):
    print(("  PASS " if c else "  FAIL ") + l)
    return c

res = []

_TMP = tempfile.mkdtemp()

import orchestrator_daemon as OD

# Перенаправляем файлы реестра на temp-директорию (тест не трогает боевой реестр)
# и снимаем заглушку _UNDER_TEST — этот файл тестирует именно функции реестра.
OD.VERIFIED_FACTS_FILE = os.path.join(_TMP, "vf.json")
OD.VERIFIED_FACTS_LOCK = os.path.join(_TMP, "vf.lock")
OD._VF_DISABLED = False   # разблокировать реестр для этого теста


def _clear_vf():
    """Очищает реестр перед тестом."""
    for f in (OD.VERIFIED_FACTS_FILE, OD.VERIFIED_FACTS_LOCK):
        try:
            os.remove(f)
        except FileNotFoundError:
            pass


# ── (1) _vf_normalize ────────────────────────────────────────────────────────
print("(1) _vf_normalize:")

v = OD._vf_normalize("DNS-разведка: проверить все домены")
res.append(ok(v is not None and "dns" in v, "обычный текст → не None, lowercase"))

v = OD._vf_normalize("[куратор цели 100, шаг 1] DNS-разведка")
res.append(ok(v is not None and "[куратор" not in v and "dns" in v,
              "куратор-маркер стрипается"))

v = OD._vf_normalize("[куратор цели 100, шаг 3][глубина 2] DNS-разведка")
res.append(ok(v is not None and "[глубина" not in v and "dns" in v,
              "[глубина 2] тоже стрипается"))

v = OD._vf_normalize("DNS-разведка: www.turbobaby.ru")
res.append(ok(v is not None and "." not in v, "спецсимволы → пробелы (точка пропадает)"))

res.append(ok(OD._vf_normalize("") is None, "пустой → None"))
res.append(ok(OD._vf_normalize(None) is None, "None → None"))
res.append(ok(OD._vf_normalize("[куратор цели 1, шаг 1] ") is None,
              "только маркер без текста → None"))

long_text = "dns разведка " * 20
v = OD._vf_normalize(long_text)
res.append(ok(v is not None and len(v) <= 120, "длинный текст обрезается до 120"))

# Нормализация даёт одинаковый ключ для текста с маркером и без
key_plain = OD._vf_normalize("DNS-разведка: проверить все домены")
key_with = OD._vf_normalize("[куратор цели 50, шаг 2] DNS-разведка: проверить все домены")
res.append(ok(key_plain == key_with,
              "маркер и без-маркера → один ключ (done-write совпадает с enqueue-write)"))


# ── (2) _vf_check / _vf_write ────────────────────────────────────────────────
print("(2) _vf_check / _vf_write:")
_clear_vf()

res.append(ok(OD._vf_check("несуществующий ключ") is None,
              "нет записи → None"))

OD._vf_write("dns разведка", "все домены разрешаются", task_id=101)
entry = OD._vf_check("dns разведка")
res.append(ok(entry is not None
              and entry.get("task_id") == 101
              and entry.get("verdict") == "все домены разрешаются",
              "запись и чтение свежей записи"))

old_ttl = OD.FACT_TTL
OD.FACT_TTL = 0
res.append(ok(OD._vf_check("dns разведка") is None, "FACT_TTL=0 → запись устарела → None"))
OD.FACT_TTL = old_ttl

OD._vf_write("dns разведка", "pending", task_id=200)
entry = OD._vf_check("dns разведка")
res.append(ok(entry is not None and entry.get("verdict") == "pending",
              "pending-запись читается как свежая"))


# ── Bridge-мок для тестов (3)-(9) ────────────────────────────────────────────
class FakeBridge:
    def __init__(s):
        s.rows, s.nid = {}, 300
        s.enq_calls = []  # [(frm, text)]

    def add(s, status, text, frm="Filipp-curator", result=""):
        s.nid += 1
        s.rows[s.nid] = {"id": s.nid, "from": frm, "task_text": text, "status": status,
                         "result": result, "created": "2026-07-15T00:00:00Z",
                         "updated": "2026-07-15T00:00:00Z"}
        return s.nid

    def get_pending(s, status="new", lane=None):
        sts = [x.strip() for x in str(status).split(",")]
        return {"ok": True,
                "items": [dict(r) for r in s.rows.values() if r["status"] in sts]}

    def claim_task(s, tid, lane=None):
        r = s.rows.get(int(tid))
        if not r:
            return {"ok": False}
        r["status"] = "in_progress"
        return {"ok": True, "task": dict(r)}

    def complete_task(s, tid, status, result=""):
        r = s.rows.get(int(tid))
        if not r:
            return {"ok": False}
        r["status"], r["result"] = status, result
        return {"ok": True}

    def enqueue_task(s, frm, text, lane=None):
        s.enq_calls.append((frm, text))
        return {"ok": True, "id": s.add("new", text, frm=frm)}

    def set_needs_approval(s, tid, what):
        r = s.rows.get(int(tid))
        if r:
            r["status"], r["result"] = "needs_approval", what
        return {"ok": True}


fb = FakeBridge()
old_bc = OD.bc
OD.bc = fb


# ── (3) spawn: кэш pending → refused, задача НЕ поставлена ──────────────────
print("(3) spawn кэш pending → refused:")
_clear_vf()

key_dns = OD._vf_normalize("DNS-разведка: проверить все домены")
OD._vf_write(key_dns, "pending", task_id=100)
fb.enq_calls.clear()

sp = OD._curator_spawn("задача", 1, "тз: проверить dns",
                       ["DNS-разведка: проверить все домены"])
followup_enq = [c for c in fb.enq_calls if "куратор цели" in c[1]]
res.append(ok(len(followup_enq) == 0,
              "(3) кэш pending → задача НЕ поставлена в bridge"))
res.append(ok(len(sp["refused"]) > 0 and "кэш" in sp["refused"][0][1],
              "(3) кэш pending → refused с сообщением о кэше"))
res.append(ok("уже поставлена" in sp["refused"][0][1] or "pending" in sp["refused"][0][1].lower()
              or "ожидает" in sp["refused"][0][1],
              "(3) сообщение указывает, что задача ожидает результата"))


# ── (4) spawn: кэш с вердиктом → refused «уже подтверждено» ────────────────
print("(4) spawn кэш с вердиктом → refused:")
_clear_vf()
OD._vf_write(key_dns, "все домены отвечают", task_id=99)
fb.enq_calls.clear()

sp = OD._curator_spawn("задача", 1, "тз: проверить dns",
                       ["DNS-разведка: проверить все домены"])
followup_enq = [c for c in fb.enq_calls if "куратор цели" in c[1]]
res.append(ok(len(followup_enq) == 0,
              "(4) кэш с вердиктом → задача НЕ поставлена"))
res.append(ok(len(sp["refused"]) > 0 and "уже подтверждено" in sp["refused"][0][1],
              "(4) refused: «уже подтверждено задачей N в HH:MM UTC»"))
res.append(ok("99" in sp["refused"][0][1],
              "(4) refused содержит id задачи-источника кэша"))


# ── (5) spawn: нет кэша → задача поставлена + «pending» в реестре ────────────
print("(5) spawn без кэша → поставлена + pending:")
_clear_vf()
task_text_5 = "DNS-разведка: свежая-проверка-уникальная-x5"
key5 = OD._vf_normalize(task_text_5)
fb.enq_calls.clear()

sp = OD._curator_spawn("задача", 1, "тз: dns уникальное", [task_text_5])
res.append(ok(len(sp["placed"]) == 1, "(5) нет кэша → задача поставлена"))
entry5 = OD._vf_check(key5)
res.append(ok(entry5 is not None and entry5.get("verdict") == "pending",
              "(5) после постановки — «pending» в реестре"))
res.append(ok(len(sp["refused"]) == 0, "(5) нет refused (одна задача, нет лимитов)"))


# ── (6) contradiction: старый ≠ новый → карточка; одинаковый → тишина ───────
print("(6) contradiction:")
_clear_vf()
fb.enq_calls.clear()

OD._vf_write("headless settings audit", "всё ок, конфиг чистый", task_id=50)
OD._vf_write("headless settings audit", "обнаружена ошибка в конфиге allow-блока", task_id=51)

card_calls = [(f, t) for f, t in fb.enq_calls if "вердикты расходятся" in t]
res.append(ok(len(card_calls) >= 1,
              "(6) противоречие → карточка «вердикты расходятся» поставлена"))

entry6 = OD._vf_check("headless settings audit")
res.append(ok(entry6 is not None and "ошибка" in str(entry6.get("verdict", "")),
              "(6) реестр обновлён новым вердиктом"))

# Одинаковые вердикты (case-insensitive) → карточки нет
fb.enq_calls.clear()
OD._vf_write("headless settings audit", "Обнаружена Ошибка В Конфиге Allow-Блока", task_id=52)
card_calls2 = [(f, t) for f, t in fb.enq_calls if "вердикты расходятся" in t]
res.append(ok(len(card_calls2) == 0, "(6) одинаковые вердикты (case-insensitive) → карточки нет"))

# pending → actual: не противоречие (pending не считается реальным вердиктом)
_clear_vf()
fb.enq_calls.clear()
OD._vf_write("wa webhook check", "pending", task_id=60)
OD._vf_write("wa webhook check", "вебхук отвечает 200", task_id=61)
card_calls3 = [(f, t) for f, t in fb.enq_calls if "вердикты расходятся" in t]
res.append(ok(len(card_calls3) == 0,
              "(6) pending → реальный вердикт: не противоречие"))


# ── (7) fail-safe: битый JSON → None, spawn ставит как обычно ────────────────
print("(7) fail-safe битый реестр:")
_clear_vf()
with open(OD.VERIFIED_FACTS_FILE, "w") as f:
    f.write("not valid json {{{{")

res.append(ok(OD._vf_check("любой ключ") is None,
              "(7) битый JSON → _vf_check → None (fail-safe)"))

fb.enq_calls.clear()
task_text_7 = "DNS-разведка: failsafe-тест-x7-уникальный"
sp7 = OD._curator_spawn("задача", 1, "тз: dns failsafe",
                        [task_text_7])
followup7 = [c for c in fb.enq_calls if "куратор цели" in c[1]]
res.append(ok(len(followup7) >= 1,
              "(7) битый реестр → spawn ставит задачу как без кэша"))


# ── (8) done-write пути: фикстура CURATOR_FROM done → вердикт в реестре ─────
print("(8) done-write фикстура:")
_clear_vf()
task_text_8 = "[куратор цели 77, шаг 1] DNS-разведка: проверить домены-8"
key8 = OD._vf_normalize(task_text_8)
result8 = "DNS разведка готова: все 3 домена отвечают\nДетали: ...\n"

# Имитация того, что делает process_new после complete_task для CURATOR_FROM-задачи
if OD._curator_on() and OD.CURATOR_FROM == "Filipp-curator":
    vf_key = OD._vf_normalize(task_text_8)
    if vf_key:
        OD._vf_write(vf_key, (result8.splitlines()[0] if result8 else "")[:200], 77)

entry8 = OD._vf_check(key8)
res.append(ok(entry8 is not None and "DNS разведка готова" in str(entry8.get("verdict", "")),
              "(8) done-write: вердикт (первая строка result) записан в реестр"))
res.append(ok(entry8 is not None and entry8.get("task_id") == 77,
              "(8) done-write: task_id сохранён"))


# ── (9) CURATOR=0 → _curator_spawn не вызывается вовсе ──────────────────────
print("(9) CURATOR=0 регресс:")
import subprocess as _sp
_real_run = OD.subprocess.run
_spawn_calls = []

_orig_spawn = OD._curator_spawn
def _spy_spawn(*a, **kw):
    _spawn_calls.append((a, kw))
    return _orig_spawn(*a, **kw)
OD._curator_spawn = _spy_spawn

os.environ["CURATOR"] = "0"
_clear_vf()
fb.enq_calls.clear()

# Симулируем вызов _maybe_curator (который guard'ится _curator_on())
OD._maybe_curator("задача", 1, "тз: dns", "dns готово")
res.append(ok(len(_spawn_calls) == 0,
              "(9) CURATOR=0 → _curator_spawn не вызывается"))

os.environ["CURATOR"] = "1"
OD._curator_spawn = _orig_spawn
OD.bc = old_bc


# ── Итог ─────────────────────────────────────────────────────────────────────
shutil.rmtree(_TMP, ignore_errors=True)

print(f"\nИтог: {sum(res)}/{len(res)} PASS")
fails = sum(1 for r in res if not r)
if fails:
    print(f"FAIL: {fails} тест(а/ов) не прошли")
    sys.exit(1)
