#!/usr/bin/env python3
"""РУКИ СЛОЯ ОЖИДАНИЙ — ярус 2 (07.08.2026). Зовётся `expectations.timer` раз в 10 минут.

Решение живёт в `expectations.py` (чистая функция «факты → вердикт», ни одного обращения к миру).
Здесь — ровно руки: СОБРАТЬ факты, ОТНЕСТИ вердикт в канал, СОХРАНИТЬ доказательство и состояние.

ПОЧЕМУ ОТДЕЛЬНЫЙ ПРОЦЕСС, А НЕ ВЕТКА В ДЕМОНЕ (правило владельца «наблюдатель не живёт на том,
за чем следит»): О1 наблюдает, БЕРЁТ ЛИ РАБОТУ ДЕМОН, а О2 — даёт ли демон оборот. Наблюдатель
внутри демона молчал бы ровно в наблюдаемом случае — так сегодня устроен `_maybe_prod_drift`
(живёт в `cycle()` и слеп, когда демон стоит), и повторять это здесь нельзя.

ТРИ ИСТОЧНИКА ФАКТОВ, КАЖДЫЙ ПЕРЕЖИВАЕТ СМЕРТЬ СВОЕГО ПРЕДМЕТА:
  очередь  — GET моста (одним вызовом, обе полосы);
  оборот   — файл пульса в /tmp, который демон пишет в конце cycle();
  тик      — хвост splinter.log на диске.
Ни демон, ни splinter отсюда НЕ импортируются. Единственный сосед — `prod_drift`, у которого
берётся read-only разведка /proc (кто жив и когда стартовал): она уже доказана инвариантом
PROD_DRIFT_READONLY и покрыта своими тестами, дубль того же кода был бы второй правдой.

ГРАНИЦА ВЛАДЕЛЬЦА (реакция): заметка в ленту 829 и, если нарушение ДЕРЖИТСЯ, задача в очередь.
Ни одна ветка не перезапускает процессов, не правит данных и не трогает инфраструктуру. Задача
ставится по правилу годности 4.2 — её исполнитель обязан быть доказанно жив (иначе она ляжет в
ту же вставшую очередь и создаст ВИДИМОСТЬ действия), поэтому у нарушения «демон не даёт
оборота» задачи не бывает никогда.

ПРОТИВ read-and-ignore: одно сообщение на эпизод и одно на его закрытие. Повторов-напоминаний
НЕТ намеренно — это ровно тот шум, за который 05.08 отозван класс push из ленты.

FAIL-SAFE: любой сбой сбора → факта нет → вердикта нет (молчание). Заметка не ушла → эпизод НЕ
помечен, скажем на следующем прогоне. Доказательство не записалось → заметка всё равно уходит.

ОТКАТ: остановить и выключить таймер `expectations` (одна команда владельца), либо порог
соответствующей ветки = 0 в .env (EXPECT_NEW_MIN / EXPECT_TURN_MIN / EXPECT_TICK_MIN),
либо EXPECT_TASK=0 — тогда живут только заметки, задач не ставится вовсе.
"""
import json
import os
import sys
import time

REPO = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, REPO)

from dotenv import load_dotenv
load_dotenv(os.path.join(REPO, ".env"))

import expectations
import prod_drift                  # только read-only разведка /proc (live/started_at)

LANE = "VPS"                       # метка полосы в заметке; на зеркале ПК обязана стать «ПК»
PULSE_DIR = "/tmp/cc_expect_pulse"          # сюда демон пишет оборот cycle() (см. _expect_pulse)
STATE_DIR = "/tmp/cc_expect_seen"           # открытые эпизоды: о чём уже сказали
SPLINTER_LOG = os.path.join(REPO, "splinter.log")
CLAIMS_LOG = os.path.join(REPO, "orchestrator_claims.jsonl")
REPORTS = os.path.join(REPO, "reports")
TAIL_BYTES = 400_000               # ≈16 часов лога: тик найдётся, даже если splinter давно молчит
TASK_FROM = "Filipp-328-dev"       # метка очереди: отчёт доезжает в 328 без правки devbot
TASK_CAP_DAY = 2                   # потолок задач-эскалаций в сутки (страховка от петли)
STATE_KEEP = 32


def _dir(base):
    """Каталог состояния. ORCH_TEST_MODE → тест-каталог (тест НЕ пишет в боевой никогда),
    CC_EXPECT_DIR — явная подмена. Зеркало дисциплины _drift_dir демона."""
    explicit = (os.environ.get("CC_EXPECT_DIR") or "").strip()
    if explicit:
        return os.path.join(explicit, os.path.basename(base))
    if (os.environ.get("ORCH_TEST_MODE") or "").strip():
        return base + "_test"
    return base


# ═════════════════════════════════ СБОР ФАКТОВ (только чтение) ═════════════════════════════
def read_pulse():
    """Пульс демона → {"ts","n","pid","started"} | None. Нет файла/мусор → None, и это МОЛЧАНИЕ:
    «демон держит код без пульса» и «демон мёртв» отсюда неотличимы (см. expectations._o2_daemon)."""
    try:
        with open(os.path.join(_dir(PULSE_DIR), "pulse.json"), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) and d.get("ts") else None
    except Exception:
        return None


def claims_ts():
    """Когда демон в последний раз ВЗЯЛ работу (журнал претензий). → эпоха | None.
    Берётся mtime файла: он и есть момент записи претензии, а разбор последней строки добавил бы
    разбор ради того же числа."""
    try:
        return os.stat(CLAIMS_LOG).st_mtime
    except OSError:
        return None


def log_tail(path=None, nbytes=TAIL_BYTES):
    """Хвост файла текстом. splinter.log без ротации (39 МБ, 67 суток) — читать целиком нельзя,
    это прямо названо пределом в проекте; читаем хвост."""
    path = path or SPLINTER_LOG
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            if size > nbytes:
                f.seek(size - nbytes)
                f.readline()                       # первая строка после seek обычно обрезана
            return f.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


def queue_facts():
    """Снимок открытых строк ОБЕИХ полос одним GET → {"ok":bool,"rows":[...]}.
    Мост молчит → ok=False, то есть фактов нет и О1 молчит (честная зависимость, названа в проекте)."""
    try:
        from bridge_client import BridgeClient
        bc = BridgeClient(timeout=45)
        r = bc.get_pending_multi(list(expectations.OPEN_STATUSES), lane="all")
    except Exception:
        return {"ok": False, "rows": []}
    if not r.get("ok"):
        return {"ok": False, "rows": []}
    rows = []
    for it in (r.get("items") or []):
        if not isinstance(it, dict):
            continue
        # «когда строка вошла в нынешнее состояние»: updated, а при его отсутствии created.
        since = expectations.parse_iso(it.get("updated")) or expectations.parse_iso(it.get("created"))
        rows.append({
            "id": it.get("id"),
            "status": it.get("status"),
            "lane": it.get("lane"),
            "from": it.get("from"),
            "since": since,
            "text": str(it.get("task_text") or "")[:200],
        })
    return {"ok": True, "rows": rows}


def _proc(unit, entry):
    """Живой процесс юнита (read-only /proc, через prod_drift) → {"pid","started"} | None."""
    try:
        p = prod_drift.live(unit, entry)
    except Exception:
        return None
    return {"pid": p["pid"], "started": p["started"]} if p else None


def snapshot(now=None):
    """ФАКТЫ и ни одного решения. Порогов здесь нет — их применяет expectations.verdict()."""
    now = time.time() if now is None else float(now)
    tick = expectations.tick_facts(log_tail())
    return {
        "now": now,
        "queue": queue_facts(),
        "daemon": {"pulse": read_pulse(),
                   "proc": _proc("orchestrator-daemon", "orchestrator_daemon.py"),
                   "claims": claims_ts()},
        "splinter": {"tick": tick.get("tick"), "log": tick.get("log"),
                     "proc": _proc("splinter", "bot.py")},
    }


# ═══════════════════════════════ СОСТОЯНИЕ: ОДИН ЭПИЗОД — ОДНО СООБЩЕНИЕ ═══════════════════
def load_state():
    try:
        with open(os.path.join(_dir(STATE_DIR), "state.json"), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def save_state(st):
    """Best-effort: диск недоступен → худшее, что случится, — повтор заметки на следующем прогоне."""
    d = _dir(STATE_DIR)
    try:
        os.makedirs(d, exist_ok=True)
        tmp = os.path.join(d, "state.json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(st, f, ensure_ascii=False)
        os.replace(tmp, os.path.join(d, "state.json"))
    except Exception as e:                                           # noqa: BLE001
        print("состояние не сохранено (%s) — возможен повтор заметки" % e, file=sys.stderr)


WAIT_STEP_CAP = 1200.0             # сколько максимум засчитывать за ОДНО наблюдение (2 периода)


def update_waits(state, facts, now):
    """Накопить ЧИСТОЕ ожидание каждой строки `new` полосы vps — время, простоянное ИМЕННО ПРИ
    СВОБОДНОЙ полосе. Именно по нему О1 берёт порог (обоснование — шапка expectations.py).

    ПОЧЕМУ СЧЁТЧИК, А НЕ МГНОВЕННЫЙ СНИМОК. Полоса одно-воркерная, и между двумя задачами всегда
    есть щель, в которую снимок видит «свободно». Правило по мгновенному снимку дало на реплее
    7 суток 17 ложных эпизодов (живой образец — задача 330: 69 минут в new, из них при свободной
    полосе 15). Счётчик эти щели складывает и до порога не доводит, а вставшую полосу доводит за
    три наблюдения.

    ЗА ОДНО НАБЛЮДЕНИЕ ЗАСЧИТЫВАЕТСЯ НЕ БОЛЬШЕ WAIT_STEP_CAP: таймер мог не работать час, и о
    занятости полосы в этот час мы не знаем НИЧЕГО — записать его в «свободное» значило бы
    выдумать факт. Первое наблюдение строки не добавляет ничего вовсе (не с чем сравнивать).

    Снимка очереди нет → счётчики не трогаем ВООБЩЕ: молчание моста не есть простой полосы."""
    q = (facts or {}).get("queue") or {}
    if not q.get("ok"):
        return
    rows = [r for r in (q.get("rows") or [])
            if str(r.get("lane") or "vps").lower() == expectations.VPS_LANE]
    busy = any(str(r.get("status") or "").lower() == "in_progress" for r in rows)
    prev = state.get("waits") or {}
    cur = {}
    for r in rows:
        if str(r.get("status") or "").lower() != "new":
            continue
        try:
            since = float(r.get("since") or 0)
        except (TypeError, ValueError):
            continue
        if since <= 0:
            continue
        key = "%s|%d" % (r.get("id"), int(since))          # тот же ключ, что у эпизода О1
        old = prev.get(key) or {}
        free = float(old.get("free") or 0.0)
        last = float(old.get("seen") or 0.0)
        if not busy and last > 0:
            free += max(0.0, min(now - last, WAIT_STEP_CAP))
        cur[key] = {"free": free, "seen": now}
        r["free_wait"] = free
    state["waits"] = cur          # строки, ушедшие из new, выпадают сами — состояние не растёт


def _tasks_today(st, now):
    """Сколько задач-эскалаций поставлено за последние сутки (потолок TASK_CAP_DAY)."""
    out = 0
    for rec in (st.get("tasks") or []):
        try:
            if now - float(rec.get("ts") or 0) < 86400:
                out += 1
        except (TypeError, ValueError):
            continue
    return out


# ═══════════════════════════════ ДОКАЗАТЕЛЬСТВО (улики живут меньше нарушения) ═════════════
def write_proof(v, facts, now):
    """Файл в reports/<дата>/expect-<ключ>.md — сырые факты в момент обнаружения.
    Когда ПК выключен, а мост отказывает, улик потом не будет: журнал перетрётся, тела ответов
    исчезнут. → путь | "" (сбой записи заметку НЕ отменяет)."""
    try:
        day = time.strftime("%Y-%m-%d", time.gmtime(now))
        d = os.path.join(REPORTS, day)
        os.makedirs(d, exist_ok=True)
        safe = "".join(c if (c.isalnum() or c in "-_") else "-" for c in str(v.get("key")))
        path = os.path.join(d, "expect-%s.md" % safe[:60])
        body = [
            "# Ожидание нарушено: %s" % v.get("kind"),
            "",
            "- обнаружено: %s UTC" % time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(now)),
            "- ключ эпизода: `%s`" % v.get("key"),
            "- возраст нарушения: %s (порог %s)" % (expectations.human_age(v.get("age")),
                                                    expectations.human_age(v.get("limit"))),
            "- реакция: заметка в ленту 829; задача — только если нарушение держится и правило "
            "годности 4.2 выполнено (`can_task=%s`)" % v.get("can_task"),
            "",
            "## Заметка, ушедшая владельцу",
            "",
            "```", expectations.render(v, LANE), "```",
            "",
            "## Сырые факты снимка",
            "",
            "```json",
            json.dumps(facts, ensure_ascii=False, indent=1, default=str)[:12000],
            "```",
        ]
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(body) + "\n")
        return path
    except Exception as e:                                           # noqa: BLE001
        print("доказательство не записано (%s)" % e, file=sys.stderr)
        return ""


# ═══════════════════════════════════ МАРШРУТ РЕАКЦИИ ═══════════════════════════════════════
def send_note(text):
    """Заметка в ленту 829. Адреса нет → не уходит НИКУДА (у ленты фолбэка нет намеренно)."""
    try:
        import notify
        return bool(notify.send_feed(text))
    except Exception as e:                                           # noqa: BLE001
        print("заметка не ушла (%s)" % e, file=sys.stderr)
        return False


def enqueue_escalation(v):
    """Вторая реакция: задача в очередь. → id | 0.

    Ставится ТОЛЬКО при can_task (правило 4.2) — проверку дублируем здесь, потому что руки не
    вправе полагаться на то, что вызывающий её сделал."""
    text = expectations.task_text(v)
    if not text:
        return 0
    try:
        from bridge_client import BridgeClient
        r = BridgeClient(timeout=45).enqueue_task(TASK_FROM, text, lane="vps",
                                                  dedup_key="expect:" + str(v.get("key")))
        return int(r.get("id") or 0) if r.get("ok") else 0
    except Exception as e:                                           # noqa: BLE001
        print("задача-эскалация не встала (%s)" % e, file=sys.stderr)
        return 0


def run(dry=False, now=None):
    """Один прогон яруса 2. → словарь итога (для теста, лога и ручной проверки)."""
    now = time.time() if now is None else float(now)
    cfg = expectations.config(os.environ)
    facts = snapshot(now)
    st = load_state()
    # Счётчики чистого ожидания копятся ДО вердикта: О1 судит по ним, а не по возрасту строки.
    update_waits(st, facts, now)
    verdicts = expectations.verdict(facts, cfg)
    open_eps = dict(st.get("open") or {})
    out = {"verdicts": len(verdicts), "notes": [], "tasks": [], "closed": [], "dry": bool(dry)}

    # 1. ЗАКРЫТИЕ ЭПИЗОДОВ — первым: владелец обязан узнать, что кончилось, даже если сейчас
    #    открылось что-то новое.
    for key in expectations.closures(facts, cfg, list(open_eps.keys())):
        if dry:
            out["closed"].append(key)
            open_eps.pop(key, None)
            continue
        if send_note(expectations.render_close(key, LANE)):
            open_eps.pop(key, None)
            out["closed"].append(key)

    # 2. НАРУШЕНИЯ.
    task_on = str(os.environ.get("EXPECT_TASK") or "1").strip() not in ("0", "no", "off")
    for v in verdicts:
        key = str(v.get("key"))
        rec = open_eps.get(key) or {}
        first = float(rec.get("first") or now)
        if not rec:                                        # ПЕРВОЕ ОБНАРУЖЕНИЕ → одна заметка
            if dry:
                out["notes"].append(key)
                open_eps[key] = {"first": now, "noted": now, "task": 0, "kind": v.get("kind")}
                continue
            proof = write_proof(v, facts, now)             # доказательство ДО канала: улики летучи
            if not send_note(expectations.render(v, LANE)):
                continue                                   # не помечаем — скажем на следующем прогоне
            open_eps[key] = {"first": now, "noted": now, "task": 0,
                             "kind": v.get("kind"), "proof": proof}
            out["notes"].append(key)
            continue
        # ЭПИЗОД УЖЕ ОБЪЯВЛЕН. Повторов нет; единственное, что может добавиться, — задача.
        if rec.get("task") or not task_on or not v.get("can_task"):
            continue
        if now - first < float(cfg.get("hold") or 0):
            continue                                       # ещё не «держится»
        if _tasks_today(st, now) + len(out["tasks"]) >= TASK_CAP_DAY:
            continue                                       # потолок суток — страховка от петли
        if dry:
            out["tasks"].append({"key": key, "id": -1})
            continue
        tid = enqueue_escalation(v)
        if not tid:
            continue
        rec["task"] = tid
        open_eps[key] = rec
        st.setdefault("tasks", []).append({"ts": now, "id": tid, "key": key})
        out["tasks"].append({"key": key, "id": tid})
        send_note("🔔 нарушение держится · %s · поставил задачу %s на разбор причины (read-only; "
                  "живые процессы и данные не трогаются) · %s"
                  % (LANE, tid, expectations.render(v, LANE).split(" · ", 2)[-1]))

    if not dry:
        st["open"] = dict(list(open_eps.items())[-STATE_KEEP:])
        st["tasks"] = (st.get("tasks") or [])[-STATE_KEEP:]
        save_state(st)
    return out


def main():
    dry = "--dry" in sys.argv[1:]
    try:
        out = run(dry=dry)
    except Exception as e:                                           # noqa: BLE001
        print("прогон не удался (%s) — вердикта нет" % e, file=sys.stderr)
        return 0                                           # молчание не считается сбоем таймера
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
