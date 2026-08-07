#!/usr/bin/env python3
"""СЛОЙ ОЖИДАНИЙ — первые два ожидания (07.08.2026, решение владельца).

Проект: коммит 6c34186, артефакт docs/artifacts/2026-08-07-three-expectations-narrowed.md.
Владелец выбрал ДВА из трёх; третье (дрейф прода) уже наблюдается `prod_drift.py`, и второй
механизм на тот же факт дал бы двойной шум — поэтому его здесь нет намеренно.

  О1 — ЦЕПОЧКА СМЕНИЛА СОСТОЯНИЕ ЗА ОТВЕДЁННОЕ ВРЕМЯ.
       Факт: строка очереди в `new` на полосе vps. Порог 30 минут ПРИ СВОБОДНОМ ИСПОЛНИТЕЛЕ.
  О2 — ГЛАВНЫЙ ПРОЦЕСС ПРОИЗВЁЛ СВОЙ РЕЗУЛЬТАТ, А НЕ ПРОСТО СУЩЕСТВУЕТ.
       Факт: оборот `cycle()` демона и тик джоба `devbot_report` у splinter. Порог 10 минут.

────────────────────────────────────────────────────────────────────────────────────────────
ПОЧЕМУ УСЛОВИЕ «ПРИ СВОБОДНОМ ИСПОЛНИТЕЛЕ» — ЭТО ВЕСЬ ПОРОГ, А НЕ УКРАШЕНИЕ

Полоса vps ОДНО-ВОРКЕРНАЯ. Строка, ждущая за работающей задачей, — законная очередь, а не
поломка. ЗАМЕР (7 суток, 31.07–07.08, реплей ЖИВЫМ кодом по METRICS-строкам демона, где у
каждого исполнения есть точные start/end):

    порог 30 мин БЕЗ условия занятости               → 24 эпизода (3.43/сут) — все ложные;
    порог 30 мин по ЧИСТОМУ ожиданию (боевое правило) →  0 эпизодов.

МЕРИТСЯ НЕ ВОЗРАСТ СТРОКИ, А НАКОПЛЕННОЕ ОЖИДАНИЕ ПРИ СВОБОДНОЙ ПОЛОСЕ — и это не тонкость, а
единственная рабочая форма правила. Первая редакция считала «строка старше 30 минут И полоса
свободна ПРЯМО СЕЙЧАС» и дала 17 эпизодов за неделю (2.43/сут), все ложные: живой образец —
задача 330, общий возраст в new 69 минут, из них при свободной полосе РОВНО 15; остальное она
законно стояла за исполнявшимися 327 и 328, а поймана была в короткую щель между ними.
Мгновенный снимок занятости не отличает «щель между задачами» от «полоса стоит», а накопленное
ожидание отличает: полоса встала → счётчик растёт КАЖДЫМ наблюдением и порог берётся за 30
минут; полоса работает → счётчик почти не растёт.

Распределение ЧИСТОГО ожидания за те же 7 суток (125 исполненных строк): медиана 2.0 · p90 8.0 ·
p95 12.0 · max 15.0 мин — запас над порогом 2.0×. Прошлый заход мерил то же другим способом и
получил медиану 1.7 · p90 7.8 · p95 11.9 · max 14.1 мин: числа сошлись независимо. Семь самых
долгих ОБЩИХ ожиданий недели (121 · 118 · 107 · 102 · 87 · 74 · 72 мин) — очередь за занятым
исполнителем, и по чистому счёту ни одно из них порога не касается.

ВТОРАЯ ПОЛОВИНА ТОГО ЖЕ УСЛОВИЯ — ГВАРД ПОСЛЕДОВАТЕЛЬНОСТИ. Демон СОЗНАТЕЛЬНО не берёт шаг
цепочки, пока сиблинг того же родителя висит в in_progress/needs_approval/approved
(`_dec_step_blocked`): порядок шагов важнее скорости. Такая строка стоит в `new` при пустом
in_progress — то есть «исполнитель свободен» по грубому счёту, а на деле она ждёт ЗАКОННО, и
ждать может сутками (сиблинг в needs_approval ждёт живого владельца). Поэтому зеркало этого
гварда живёт здесь (`_step_blocked`): без него первая же красная цепочка родила бы заметку
каждые десять минут до ответа владельца — ровно тот шум, за который 05.08 отозван класс push.

ЧЕГО О1 НЕ ЗНАЕТ И ГДЕ ОШИБЁТСЯ ЧЕСТНО. Демон пропускает `new` и по другим причинам: пауза
приёма перед плановым рестартом (секунды), гейт памяти и гейт параллелизма (MEM_MIN_MB,
CLAUDE_RSS_TOTAL_MB, MAX_CLAUDE_PROCS). Эти случаи заметку РОДЯТ — и это правильно: строка
действительно не сменила состояние за отведённое время, а причина («демон голодает по памяти»)
как раз то, что владелец узнать хочет. Ложью заметка не станет ни в одном из них.

────────────────────────────────────────────────────────────────────────────────────────────
ПОЧЕМУ У О2 БЕРЁТСЯ ПРОДУКТ, А НЕ ПУЛЬС ЖИЗНИ

Успешный опрос очереди не логируется вовсе, поэтому «работает вхолостую» и «умер» снаружи
выглядят одинаково: 06.08 в журнале демона есть окно 13:03–23:10 (10 ч 07 м) без единой
строки, и это было ЗДОРОВЬЕМ. Значит факт обязан производиться и тогда, когда работы нет.

Heartbeat для этого НЕ ГОДИТСЯ и не используется: `_heartbeat_loop` демона — отдельный поток,
он стучит независимо от того, делает ли `claude -p` хоть что-нибудь. Он доказывает жизнь
потока, который его шлёт, и ничего больше. Поэтому берётся продукт:

  • демон   — ОБОРОТ `cycle()`: единственная новая запись во всём слое (пульс пишет демон в
              конце цикла). Порог 10 мин = 10×POLL_SEC; max простой юнита за неделю 90 с,
              запас 6.7×. «Ошибка цикла» в журнале демона за всю его историю — 0 раз, поэтому
              пульс в КОНЦЕ цикла (а не в начале) не даёт ложного молчания на сбоях моста:
              они внутри процедур гасятся и оборот завершается.
  • splinter — ТИК джоба `devbot_report` (45 с) в splinter.log. ЗАМЕР 49 суток: 90 843 тика,
              медиана 45 с, p99 90 с, p99.9 212 с, max 491 с, разрывов свыше 600 с — НИ ОДНОГО.
              Порог 5 минут дал бы 0.39 ложных в сутки, порог 10 минут — ноль. Запас 22 %,
              самый узкий в слое: вырастет нагрузка — перемерить.

О2 РАЗЛИЧАЕТ ДВА МОЛЧАНИЯ, и это не украшение (артефакт §6): «лог растёт, а тиков нет» =
процесс жив, встал планировщик; «лог не растёт вовсе» = молчит весь процесс. Диагноз разный,
и заметка говорит какой. Отдельно названо: если тика нет в хвосте ВООБЩЕ (подняли уровень
логирования — факт исчезает молча), мы МОЛЧИМ, а не читаем это как смерть.

────────────────────────────────────────────────────────────────────────────────────────────
ГДЕ СТОИТ НАБЛЮДАТЕЛЬ (правило владельца: он не живёт на том, за чем следит)

Оба ожидания судит ЯРУС 2 — `expectations.timer`, отдельный oneshot-процесс systemd:
  О1 наблюдает, берёт ли работу ДЕМОН   → наблюдатель обязан быть вне демона  ✅ таймер;
  О2 наблюдает оборот ДЕМОНА и тик SPLINTER → наблюдатель вне обоих           ✅ таймер.
Факты берутся из мест, переживающих смерть наблюдаемого: пульс демона — файл в /tmp, тик
splinter — хвост его лога, очередь — GET моста. Таймер не импортирует ни демона, ни splinter.

ЧЕСТНАЯ ЗАВИСИМОСТЬ, КОТОРУЮ ЭТО НЕ СНИМАЕТ: снимок очереди для О1 приходит через мост.
Мост мёртв → строки стоят (нарушение О1 реально), а наблюдатель ослеп и МОЛЧИТ. Худший
непрерывный отказ моста за неделю — 11 минут при пороге 30, но класс назван, а не закрыт.
Ярус 3 («VPS мёртв целиком») не строится и здесь: смерть машины не заметит никто.

────────────────────────────────────────────────────────────────────────────────────────────
ЧЕГО ЭТОТ МОДУЛЬ НЕ УМЕЕТ — УСТРОЙСТВОМ, А НЕ ОБЕЩАНИЕМ

Импортов ровно два: `re` и `time`. Ни файлов, ни сети, ни моста, ни notify, ни подпроцессов —
значит он не может ни перезапустить, ни записать, ни отправить. Он принимает факты словарём и
возвращает вердикт списком; кто соберёт факты и кто понесёт текст в канал — дело рук
(`expectations_run.py`). Стережёт это инвариант EXPECTATIONS_PURE в invariants_check.py
(ast-разбор, в гейте), тем же приёмом, что CARD_DUTY_PURE и PROD_DRIFT_READONLY.

РЕАКЦИЯ — СТРОГО В ГРАНИЦЕ ВЛАДЕЛЬЦА: заметка в ленту 829 и, если нарушение ДЕРЖИТСЯ, задача.
Живые процессы, данные и инфраструктуру слой не трогает ни одной веткой. Ветка «задача»
включается только по правилу 4.2 (`can_task`): её исполнитель обязан быть ДОКАЗАННО жив, иначе
задача ляжет в ту же вставшую очередь и создаст видимость действия там, где действия нет.
Отсюда: у нарушения «демон не даёт оборота» задачи не бывает НИКОГДА — исполнитель и есть
предмет нарушения.

FAIL-SAFE ВЕЗДЕ В СТОРОНУ МОЛЧАНИЯ: нет факта, не разобрались, мусор в фактах, любое
исключение → вердикта нет. Слой умеет ТОЛЬКО заявлять нарушение; сказать «всё хорошо» он не
может физически — это отсутствие вердикта, а не вердикт.

ОТКАТ: любой порог = 0 → соответствующая ветка мертва целиком (проверяется ДО чтения фактов);
полностью — остановить и выключить `expectations.timer`. Парсер порога СВОЙ (`limit_env`), а
не `_env_int` демона: тот на «0» отдаёт дефолт, то есть выключить им ветку нельзя.
"""
import datetime
import re

# ── ПОРОГИ. Значения обоснованы замером в шапке; имена — ключи .env. ────────────────────────
NEW_MIN_ENV, NEW_MIN_DEFAULT = "EXPECT_NEW_MIN", 30.0     # О1: строка ждёт в new (мин)
TURN_MIN_ENV, TURN_MIN_DEFAULT = "EXPECT_TURN_MIN", 10.0  # О2: оборот cycle() демона (мин)
TICK_MIN_ENV, TICK_MIN_DEFAULT = "EXPECT_TICK_MIN", 10.0  # О2: тик devbot_report splinter (мин)
HOLD_MIN_ENV, HOLD_MIN_DEFAULT = "EXPECT_HOLD_MIN", 60.0  # «нарушение держится» → задача (мин)

VPS_LANE = "vps"
OPEN_STATUSES = ("new", "in_progress", "needs_approval", "approved")
# Зеркало _DEC_WAIT_STATUSES демона: пока сиблинг родителя в этих статусах, шаг ждёт ЗАКОННО.
DEC_WAIT_STATUSES = ("in_progress", "needs_approval", "approved")
STEP_RE = re.compile(r"^\[шаг (\d+)/(\d+) родитель (\d+)\]")   # зеркало _STEP_RE демона

KINDS = ("o1_new_vps", "o2_daemon", "o2_splinter")


def limit_env(name, default, env=None):
    """Порог в МИНУТАХ из окружения → СЕКУНДЫ. Пусто/мусор → дефолт; 0 → ветка мертва.
    НОЛЬ ЗДЕСЬ ЗНАЧИМ (это объявленный откат), поэтому парсер свой — см. шапку."""
    try:
        raw = str(((env if env is not None else {}) or {}).get(name) or "").strip()
    except Exception:
        return float(default) * 60.0
    if not raw:
        return float(default) * 60.0
    try:
        v = float(raw.replace(",", "."))
    except (TypeError, ValueError):
        return float(default) * 60.0
    return (v if v >= 0 else float(default)) * 60.0


def config(env=None):
    """Все пороги разом (секунды). Отдельный словарь — чтобы вердикт был чистой функцией
    (facts, cfg) и тест мог задать пороги, не трогая окружение."""
    return {
        "new": limit_env(NEW_MIN_ENV, NEW_MIN_DEFAULT, env),
        "turn": limit_env(TURN_MIN_ENV, TURN_MIN_DEFAULT, env),
        "tick": limit_env(TICK_MIN_ENV, TICK_MIN_DEFAULT, env),
        "hold": limit_env(HOLD_MIN_ENV, HOLD_MIN_DEFAULT, env),
    }


# ═══════════════════ РАЗБОР СЫРЫХ СТРОК (текст → число; мира не касается) ═══════════════════
def parse_iso(val):
    """ISO-время очереди («2026-08-07T07:09:50.918Z») → эпоха | None. Мусор → None (молчим).

    ЖИВОЙ ФОРМАТ снят с прода, а не идеализирован (урок класса «мок колонок = живой формат»):
    мост отдаёт `2026-08-07T07:09:50.918Z` — с «T», долями секунды и зоной «Z». Строка БЕЗ зоны
    читается как UTC: очередь пишет UTC, и локальная зона машины (Бангкок, UTC+7) дала бы
    ошибку в семь часов — ровно тот класс, из-за которого cclog.py считает время сам."""
    s = str(val or "").strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    try:
        return dt.timestamp()
    except (OverflowError, OSError, ValueError):
        return None


LOG_TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})[,.]?(\d{0,3})")
TICK_MARK = "devbot_report"


def parse_log_ts(line):
    """Начало строки splinter.log («2026-08-07 07:12:19,321 [INFO] …») → эпоха | None.
    Время в логе — UTC (так его пишет splinter), поэтому читается как UTC без сдвигов."""
    m = LOG_TS_RE.match(str(line or ""))
    if not m:
        return None
    try:
        dt = datetime.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
        return dt.replace(tzinfo=datetime.timezone.utc).timestamp()
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def tick_facts(tail_text):
    """Хвост splinter.log → {"tick": эпоха|None, "log": эпоха|None}.

    tick — последняя строка джоба `devbot_report` (продукт, который splinter выдаёт БЕЗ спроса);
    log  — последняя строка с временем ВООБЩЕ (растёт ли лог). Их разница и есть различитель
    «планировщик встал» ↔ «процесс молчит целиком»."""
    tick = None
    last = None
    for line in str(tail_text or "").splitlines():
        ts = parse_log_ts(line)
        if ts is None:
            continue
        last = ts if last is None or ts > last else last
        if TICK_MARK in line:
            tick = ts if tick is None or ts > tick else tick
    return {"tick": tick, "log": last}


# ═══════════════════════════ РЕШЕНИЕ: ЧИСТАЯ ФУНКЦИЯ ФАКТОВ ════════════════════════════════
def _rows(facts):
    q = (facts or {}).get("queue") or {}
    if not q.get("ok"):
        return None                               # снимка нет → фактов нет → молчим
    out = []
    for r in (q.get("rows") or []):
        if not isinstance(r, dict):
            continue
        out.append(r)
    return out


def _lane(row):
    return str(row.get("lane") or VPS_LANE).strip().lower() or VPS_LANE


def _status(row):
    return str(row.get("status") or "").strip().lower()


def _step_blocked(row, rows):
    """Зеркало гварда последовательности демона: шаг цепочки ждёт ЗАКОННО, пока у его родителя
    открыт другой шаг. Возвращает True → нарушением это НЕ считается.

    Проверяем ровно то же, что демон: (а) сиблинг родителя в in_progress/needs_approval/approved
    (`_dec_step_blocked`), (б) сам родитель ещё открыт, (в) шаг с МЕНЬШИМ номером ждёт в new
    (`_earlier_new_sibling` — порядок цепочки по номеру шага, а не по id)."""
    m = STEP_RE.match(str(row.get("text") or ""))
    if not m:
        return False
    num, parent = int(m.group(1)), int(m.group(3))
    for other in rows:
        if other is row:
            continue
        st = _status(other)
        if st not in OPEN_STATUSES:
            continue
        try:
            oid = int(other.get("id") or 0)
        except (TypeError, ValueError):
            oid = 0
        if oid == parent:                          # (б) родитель цепочки ещё открыт
            return True
        om = STEP_RE.match(str(other.get("text") or ""))
        if not om or int(om.group(3)) != parent:
            continue
        if st in DEC_WAIT_STATUSES:                # (а) сиблинг занят/ждёт владельца
            return True
        if st == "new" and int(om.group(1)) < num:  # (в) впереди шаг с меньшим номером
            return True
    return False


def _daemon_turning(facts, cfg):
    """Демон ДОКАЗАННО даёт оборот? Нужен правилу 4.2 (годность реакции «задача») и закрытию
    эпизода. Пульса нет → «не доказано», то есть False: право на задачу не выдаём по умолчанию."""
    d = (facts or {}).get("daemon") or {}
    pulse = d.get("pulse") or None
    if not isinstance(pulse, dict):
        return False
    try:
        age = float(facts.get("now") or 0.0) - float(pulse.get("ts") or 0.0)
    except (TypeError, ValueError):
        return False
    return 0 <= age <= float(cfg.get("turn") or 0.0) if cfg.get("turn") else False


def _o1(facts, cfg, now):
    """О1 — строка очереди не сменила состояние за отведённое время ПРИ СВОБОДНОМ ИСПОЛНИТЕЛЕ."""
    limit = float(cfg.get("new") or 0.0)
    if limit <= 0:
        return []                                  # откат: ветка мертва до чтения фактов
    rows = _rows(facts)
    if rows is None:
        return []
    vps = [r for r in rows if _lane(r) == VPS_LANE]
    if any(_status(r) == "in_progress" for r in vps):
        return []                                  # исполнитель занят — законная очередь
    claims = (facts.get("daemon") or {}).get("claims")
    turning = _daemon_turning(facts, cfg)
    out = []
    for r in vps:
        if _status(r) != "new":
            continue
        since = r.get("since")
        try:
            since = float(since)
        except (TypeError, ValueError):
            continue
        if since <= 0:
            continue
        age = now - since
        # ПОРОГ БЕРЁТ ЧИСТОЕ ОЖИДАНИЕ, а не возраст строки: сколько эта строка простояла в new
        # ИМЕННО ПРИ СВОБОДНОЙ ПОЛОСЕ. Счётчик копят руки (по одному наблюдению за прогон) —
        # здесь только сравнение с порогом. Факта нет → нарушения нет (fail-safe в молчание).
        try:
            free = float(r.get("free_wait") or 0.0)
        except (TypeError, ValueError):
            continue
        if free <= limit:
            continue
        if _step_blocked(r, rows):
            continue                               # ждёт сиблинга — не нарушение (см. шапку)
        # ПРАВИЛО 4.2: задача законна, только если демон и оборот даёт, И берёт ДРУГИЕ строки —
        # иначе она ляжет в ту же вставшую очередь. «Берёт другие» = журнал претензий моложе
        # начала этого ожидания.
        took_other = False
        try:
            took_other = claims is not None and float(claims) > since
        except (TypeError, ValueError):
            took_other = False
        out.append({
            "kind": "o1_new_vps",
            "key": "o1|%s|%d" % (r.get("id"), int(since)),
            "id": r.get("id"),
            "from": str(r.get("from") or ""),
            "age": age,                            # общий возраст строки в new — для текста
            "free": free,                          # ЧИСТОЕ ожидание: по нему и взят порог
            "limit": limit,
            "can_task": bool(turning and took_other),
        })
    return out


def _o2_daemon(facts, cfg, now):
    """О2 — демон не дал оборота cycle() за отведённое время."""
    limit = float(cfg.get("turn") or 0.0)
    if limit <= 0:
        return []
    d = (facts or {}).get("daemon") or {}
    pulse, proc = d.get("pulse"), d.get("proc")
    if not isinstance(pulse, dict):
        # Пульса нет ВООБЩЕ. «Демон держит код без пульса» и «демон мёртв» отсюда неотличимы —
        # и молчание тут честнее догадки: о старом коде в памяти говорит детектор дрейфа.
        return []
    if isinstance(proc, dict):
        try:
            if now - float(proc.get("started") or 0.0) < limit:
                return []                          # экземпляр моложе порога — отчитаться не успел
        except (TypeError, ValueError):
            return []
    try:
        last = float(pulse.get("ts") or 0.0)
    except (TypeError, ValueError):
        return []
    if last <= 0:
        return []
    age = now - last
    if age <= limit:
        return []
    return [{
        "kind": "o2_daemon",
        "key": "o2d|%d|%d" % (int(float(pulse.get("started") or 0.0)), int(last)),
        "age": age,
        "limit": limit,
        "pid": (proc or {}).get("pid") if isinstance(proc, dict) else None,
        "alive": isinstance(proc, dict),
        "turns": pulse.get("n"),
        # Исполнитель задачи И ЕСТЬ предмет нарушения → задача невозможна по правилу 4.2.
        "can_task": False,
    }]


def _o2_splinter(facts, cfg, now):
    """О2 — splinter не произвёл тик devbot_report за отведённое время."""
    limit = float(cfg.get("tick") or 0.0)
    if limit <= 0:
        return []
    s = (facts or {}).get("splinter") or {}
    tick = s.get("tick")
    if tick is None:
        # Тика в хвосте нет вовсе: скорее подняли уровень логирования, чем умер процесс.
        # Читать это как смерть — та же ошибка, что «пульс доказывает пульс» (артефакт §6).
        return []
    proc = s.get("proc")
    if isinstance(proc, dict):
        try:
            if now - float(proc.get("started") or 0.0) < limit:
                return []
        except (TypeError, ValueError):
            return []
    try:
        tick = float(tick)
    except (TypeError, ValueError):
        return []
    age = now - tick
    if age <= limit:
        return []
    log_ts = s.get("log")
    log_age = None
    try:
        log_age = None if log_ts is None else now - float(log_ts)
    except (TypeError, ValueError):
        log_age = None
    growing = log_age is not None and log_age <= limit
    return [{
        "kind": "o2_splinter",
        "key": "o2s|%d" % int(tick),
        "age": age,
        "limit": limit,
        "log_age": log_age,
        "growing": growing,
        "alive": isinstance(proc, dict),
        "can_task": bool(_daemon_turning(facts, cfg)),
    }]


def verdict(facts, cfg=None):
    """ФАКТЫ → список нарушений. Ни одного обращения к миру: ни ФС, ни сети, ни времени — всё
    приходит в `facts`. Пустой список = вердикта нет (НЕ «всё хорошо»: сказать так слой не умеет).

    Любое исключение внутри ветки гасится в молчание этой ветки: одна кривая строка очереди не
    смеет отнять у владельца заметку о вставшем демоне."""
    if not isinstance(facts, dict):
        return []
    cfg = cfg if isinstance(cfg, dict) else config()
    try:
        now = float(facts.get("now") or 0.0)
    except (TypeError, ValueError):
        return []
    if now <= 0:
        return []
    out = []
    for fn in (_o1, _o2_daemon, _o2_splinter):
        try:
            out.extend(fn(facts, cfg, now) or [])
        except Exception:                                            # noqa: BLE001
            continue
    return out


def closures(facts, cfg, open_keys):
    """Какие ИЗ УЖЕ ОБЪЯВЛЕННЫХ эпизодов доказанно закрылись (артефакт §4.4.3: закрытие
    объявляется тоже — иначе владелец не знает, кончилось ли).

    ДОКАЗАННО — ключевое слово: закрытым считается эпизод, чей ИСТОЧНИК ФАКТА доступен и
    говорит «нарушения больше нет». Источник недоступен (мост молчит, пульса нет, тика нет) →
    эпизод НЕ закрывается: молчание источника не есть выздоровление."""
    if not isinstance(cfg, dict):
        cfg = config()
    live = {str(v.get("key")) for v in (verdict(facts, cfg) or [])}
    rows = _rows(facts)                              # None = снимка очереди нет
    tick = ((facts or {}).get("splinter") or {}).get("tick")
    out = []
    for key in (open_keys or []):
        key = str(key)
        if key in live:
            continue                                 # нарушение продолжается — закрывать нечего
        kind = key.split("|", 1)[0]
        if kind == "o1" and rows is not None:
            out.append(key)                          # снимок есть, строки в нарушении нет
        elif kind == "o2d" and _daemon_turning(facts, cfg):
            out.append(key)                          # пульс свежий = оборот вернулся
        elif kind == "o2s" and tick is not None:
            out.append(key)                          # тик найден и в вердикт не попал = свежий
    return out


# ═══════════════════════════ ФОРМА ЗАМЕТКИ И ТЕКСТА ЗАДАЧИ ═════════════════════════════════
# Заметка ленты: кнопок нет, номера карточки нет, слова «да» нет — отвечать не на что и нечем.
# Первый токен «🔔» общий с лентой фазы 1, чтобы в теме 829 заметки читались одним семейством.
NOTE_HEAD = {
    "o1_new_vps": "🔔 очередь стоит при свободном исполнителе",
    "o2_daemon": "🔔 демон не даёт оборота",
    "o2_splinter": "🔔 splinter не производит тик",
}
CLOSE_HEAD = "🔔 ожидание снова выполняется"
# Строка, которой заканчивается КАЖДАЯ заметка: граница владельца названа в самом сообщении.
TAIL = "рестарта и правок не делаю — это решение владельца"


def human_age(sec):
    """«48 мин» / «5 ч 12 мин» / «1 сут 10 ч». Ноль дробей: заметку читают с телефона."""
    s = max(0, int(sec or 0))
    d, rest = divmod(s, 86400)
    h, rest = divmod(rest, 3600)
    m = rest // 60
    if d:
        return "%d сут %d ч" % (d, h)
    if h:
        return "%d ч %d мин" % (h, m)
    return "%d мин" % m


def _mins(sec):
    return "%d мин" % int(round(float(sec or 0) / 60.0))


def render(v, lane="VPS"):
    """Текст заметки. Отправляет её РУКА (expectations_run) — модуль в канал не ходит."""
    kind = str((v or {}).get("kind") or "")
    head = NOTE_HEAD.get(kind, "🔔 ожидание нарушено")
    parts = [head, str(lane or "VPS")]
    if kind == "o1_new_vps":
        parts += [
            "задача %s (%s) ждёт в new %s" % (v.get("id"), v.get("from") or "?",
                                              human_age(v.get("age"))),
            # ОБА числа названы: общий возраст — то, что видно глазами в очереди; чистое ожидание
            # — то, ПО ЧЕМУ взят порог. Без второго заметка выглядела бы придиркой к живой очереди.
            "из них %s при СВОБОДНОЙ полосе (порог %s), сейчас на vps ни одной строки in_progress"
            % (human_age(v.get("free")), _mins(v.get("limit"))),
        ]
    elif kind == "o2_daemon":
        parts += [
            "последний оборот cycle() %s назад (порог %s)" % (human_age(v.get("age")),
                                                              _mins(v.get("limit"))),
            ("процесс жив (PID %s), но продукта не даёт" % v.get("pid")) if v.get("alive")
            else "живого процесса демона не видно вовсе",
            "очередь не движется, пока это так",
        ]
    elif kind == "o2_splinter":
        parts += [
            "последний тик devbot_report %s назад (порог %s)" % (human_age(v.get("age")),
                                                                 _mins(v.get("limit"))),
            ("лог растёт (последняя строка %s назад) — процесс жив, встал планировщик"
             % human_age(v.get("log_age"))) if v.get("growing")
            else "лог не растёт вовсе — молчит весь процесс",
        ]
    else:
        parts.append("нарушение ожидания")
    parts.append(TAIL)
    return " · ".join(parts)


def render_close(v_key, lane="VPS", detail=""):
    """Закрытие эпизода — одна строка, тем же семейством. Без неё владелец не знает, кончилось ли."""
    kind = str(v_key or "").split("|", 1)[0]
    what = {"o1": "очередь снова движется",
            "o2d": "демон снова даёт оборот",
            "o2s": "splinter снова тикает"}.get(kind, "ожидание снова выполняется")
    parts = [CLOSE_HEAD, str(lane or "VPS"), what]
    if detail:
        parts.append(str(detail))
    return " · ".join(parts)


# ТЕКСТ ЗАДАЧИ — вторая, СИЛЬНАЯ реакция («если нарушение держится»). Границу владельца текст
# несёт в себе: разбор read-only, живые процессы не трогать, данные не править. Слов, которыми в
# этой системе перезапускают процессы, здесь нет намеренно — ни как команды, ни как цитаты.
TASK_HEAD = "[слой ожиданий] нарушение держится %s: %s"
TASK_BODY = (
    "Это автоматическая заявка наблюдателя (ярус 2, expectations.timer), а не поручение владельца.\n"
    "ЧТО НАБЛЮДАЛОСЬ: %s\n"
    "ЗАДАЧА: разобраться в ПРИЧИНЕ и назвать её. Разбор READ-ONLY: журналы, очередь, состояние "
    "юнитов, код. \n"
    "ЖЁСТКО: живые процессы НЕ перезапускать и НЕ останавливать, данные и рабочие таблицы НЕ "
    "править, инфраструктуру НЕ трогать — по решению владельца это только его ход. Если причина "
    "требует такого действия — НАЗОВИ его отчётом и остановись, не выполняя.\n"
    "ОТЧЁТ: одна строка сути + факты, на которых стоит вывод."
)


def task_text(v):
    """ТЗ задачи-эскалации. Пустая строка → задачу ставить нельзя (вызывающий обязан проверить)."""
    if not isinstance(v, dict) or not v.get("can_task"):
        return ""
    what = {
        "o1_new_vps": "строка очереди %s не взята исполнителем" % v.get("id"),
        "o2_splinter": "splinter не производит тик devbot_report",
    }.get(str(v.get("kind") or ""))
    if not what:
        return ""
    return (TASK_HEAD % (human_age(v.get("age")), what)) + "\n\n" + (TASK_BODY % render(v))
