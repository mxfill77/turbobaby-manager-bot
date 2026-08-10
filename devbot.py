"""Дев-бот (полу-оркестратор), пункт 5 лестницы — первый заход.

ТОЛЬКО зелёные read-only задачи по ЖЁСТКОМУ allowlist (БЕЗ LLM, детерминированно). Живёт в HQ
topic 328 (Splinter там молчит). 205 = pc_agent/userbot на ПК — НЕ наша тема. Команды ТОЛЬКО от Филиппа (504608015).
origin=agent → ЛЮБАЯ попытка красной записи ловится токен-замком 4.2 (rejected+пуш), деплой —
тесты-гейтом 4.3. Красное/вне-allowlist → НЕ выполняет, просит «да». Не новый процесс — на bot.py.
"""
import os
import re
import sys
import json
import time
import asyncio
import hashlib
import datetime
import logging
import subprocess
import contextvars
import unicodedata
from collections import Counter

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import notify                # дверь каналов: лента 829 = заметка, на которую не отвечают
import bridge_client
import task_metrics          # общий детектор тест-прогона (под тестом боевые артефакты не трогаем)
import report_digest         # чистая функция «тело отчёта → что показать в чате» (часть 2)
import revizor_route         # чистая функция «находки ревизора → лента или карточка»

log = logging.getLogger(__name__)
ROOT = os.path.dirname(os.path.abspath(__file__))
PY = os.path.join(ROOT, "venv", "bin", "python3")

DEVBOT_USER = 504608015                 # Филипп — единственный, кто командует дев-ботом
HQ_CHAT_ID = -1003853365891
DEVBOT_TOPIC = 328                      # тема dev-bot (VPS). 205 = pc_agent/userbot (ПК) — НЕ наша
CC_LOG_ID = "1464zaINaLnOwXMsHNaEyy-4FpuQCVTYF"


def pc_dev_topic():
    """Тема «PC-дев» (вторая полоса lane=pc, 04.07.2026) — id из env PC_DEV_TOPIC_ID.
    0/пусто/мусор = полоса ВЫКЛЮЧЕНА (id Филипп даёт после создания темы). Читается лениво
    на каждый вызов: bot.py импортирует devbot ДО load_dotenv(), модульная константа
    зафиксировала бы пустое значение."""
    try:
        return int(os.getenv("PC_DEV_TOPIC_ID", "0") or 0)
    except (TypeError, ValueError):
        return 0


def inbox_topic():
    """Тема «Единый инбокс подтверждений» (ст3 оркестратора, KB_MASTER §7 Вариант Б, 06.07.2026)
    из env INBOX_TOPIC_ID. 0/пусто/мусор = ИНБОКС ВЫКЛЮЧЕН → карточки needs_approval идут по старым
    полосам 328/829 (текущее поведение, без регресса); задан → approve-карточки ОБЕИХ полос сходятся
    в эту тему. Лениво (как pc_dev_topic — bot.py импортирует devbot ДО load_dotenv())."""
    try:
        return int(os.getenv("INBOX_TOPIC_ID", "0") or 0)
    except (TypeError, ValueError):
        return 0

BRIDGE = None   # выставляется из bot.py при старте (devbot.BRIDGE = bridge)

# === Фикс заморозки event loop (разбор таймаутов get_pending 02.07.2026) ===
# Синхронные requests к Bridge прямо в async job вешали ВЕСЬ event loop PTB до 60-240с
# (окна деградации Apps Script /exec). Фикс: опрос очереди — ОДНИМ синхронным прогоном в
# отдельном потоке (asyncio.to_thread) + отдельный клиент с коротким timeout: опрос
# идемпотентен, при таймауте просто ждём следующий тик 45с, а не держим 60с.
POLL_TIMEOUT = 15                       # сек на get_pending при опросе очереди (вместо 60)
_REPORT_STATUSES = ("done", "failed", "needs_approval", "in_progress", "new", "approved")
_poll_bridge = None                     # ленивый клиент опроса (timeout=POLL_TIMEOUT)
_poll_bridge_for = None                 # BRIDGE, под который создан _poll_bridge (тесты меняют BRIDGE)


def _get_poll_bridge():
    """Отдельный BridgeClient для 45с-опроса очереди (timeout=POLL_TIMEOUT вместо 60с).
    Тестовый/нестандартный BRIDGE без url/token опрашиваем как есть (моки в tests/)."""
    global _poll_bridge, _poll_bridge_for
    b = BRIDGE
    if b is None:
        return None
    if _poll_bridge is None or _poll_bridge_for is not b:
        url = getattr(b, "url", None)
        token = getattr(b, "token", None)
        _poll_bridge = (bridge_client.BridgeClient(url=url, token=token, timeout=POLL_TIMEOUT)
                        if url and token else b)
        _poll_bridge_for = b
    return _poll_bridge


def _poll_queue_sync(pb):
    """СИНХРОННЫЙ опрос очереди одним прогоном — звать ТОЛЬКО через asyncio.to_thread.
    Склейка статусов: get_pending_multi = 1 CSV-вызов на новом Bridge (фоллбэк по-статусно
    на старом/мокнутом). lane='all' (04.07.2026): опрашиваем ОБЕ полосы (vps+pc) — карточки
    pc-задач devbot разносит в тему PC-дев (_item_topic). → {status: [items c from∈QUEUE_FROMS]}
    | None (ошибка → ждём тик)."""
    fn = getattr(pb, "get_pending_multi", None)
    if fn is not None:
        r = fn(_REPORT_STATUSES, lane="all")
    else:                                   # мок в тестах без multi — по-статусно
        items = []
        for st in _REPORT_STATUSES:
            rr = pb.get_pending(st, lane="all")
            if not rr.get("ok"):
                return None
            for it in rr.get("items", []):
                if isinstance(it, dict):
                    it.setdefault("status", st)
                items.append(it)
        r = {"ok": True, "items": items}
    if not r.get("ok"):
        return None
    by = {st: [] for st in _REPORT_STATUSES}
    for it in r.get("items", []):
        st = str(it.get("status") or "")
        if st in by and str(it.get("from")) in QUEUE_FROMS:
            by[st].append(it)
    return by

# === ОРКЕСТРАТОР (ступень1 заход2б-1 + ступень2 O4): дев-бот ↔ очередь ===
# Префикс в 328 → кладём задачу в очередь оркестратора; фоновый job приносит результат обратно.
QUEUE_FROM = "Filipp-328"               # метка источника быстрых задач «задача:» (таймаут 10 мин)
QUEUE_FROM_DEV = "Filipp-328-dev"       # метка дев-ТЗ «тз:» (ступень 2 O4, таймаут 45 мин у демона)
# 229 (FACT-верификация): блок FACT: в результате dev-задачи = живое доказательство эффекта.
_FACT_RE = re.compile(r"\bFACT\s*:", re.IGNORECASE)


def _unverified_card_prefix(st, it):
    """229 недеструктивно: dev-задача (from *-dev) со st=='done' и БЕЗ блока FACT: в result →
    префикс карточки 328 «⚠️ unverified (нет блока FACT:)\n»; иначе ''. Хранимый result в
    Bridge НЕ трогаем — демон пишет финал байт-в-байт, видимость даёт только текст карточки."""
    if st == "done" and str(it.get("from") or "").endswith("-dev") \
            and not _FACT_RE.search(str(it.get("result") or "")):
        return "⚠️ unverified (нет блока FACT:)\n"
    return ""
QUEUE_FROM_DEC = "Filipp-328-dec"       # метка декомпозиции «декомпозируй:» (ступень 2 часть C):
                                        # родитель + его шаги «[шаг i/N родитель id]» + сводка
QUEUE_FROM_PC = "Filipp-pc"             # быстрая задача из темы PC-дев (lane=pc, исполняет ПК-агент)
QUEUE_FROM_PC_DEV = "Filipp-pc-dev"     # дев-ТЗ из темы PC-дев (lane=pc)
QUEUE_FROM_PC_DEC = "Filipp-pc-dec"     # декомпозиция ПК-театра (кусок 2, 07.07.2026): родитель
                                        # БЕЗ lane (план строит VPS-демон — единственный мозг),
                                        # шаги демон релизит на lane=pc по одному; карточки → 829
QUEUE_FROM_PCLOC_DEC = "Filipp-pcloc-dec"  # ЛОКАЛЬНЫЙ дирижёр-декомпозер ПК (родитель 185, шаг 5/7,
                                        # 11.07.2026): план/релиз/надзор целиком на ПК
                                        # (pc_orchestrator, PC_LOCAL_DEC=1), VPS-демон цепь НЕ видит;
                                        # devbot несёт её карточки штатно — needs_approval красного
                                        # шага → инбокс (INBOX_TOPIC_ID, прод 1160) с кнопками ✅/❌,
                                        # done/failed/сводки/карточки → тема PC-дев
QUEUE_FROM_CURATOR = "Filipp-curator"   # followup-задачи куратора целей (шаг 3/7 родитель 231):
                                        # ставит orchestrator_daemon (CURATOR_FROM), полоса vps →
                                        # карточки в 328. Урок 682a881: метки нет в QUEUE_FROMS →
                                        # done/failed/needs_approval куратор-задач НЕ доезжают
QUEUE_FROM_REVIZOR = "Filipp-revizor"   # сводные карточки РЕВИЗОРА (производитель на ПК, lane=pc):
                                        # «[ревизор-находки] …» — находки, требующие решения
                                        # владельца (спорный тариф/политика). ТРЕТИЙ случай урока
                                        # 682a881: метки не было в QUEUE_FROMS → фильтр отчётов
                                        # выкидывал задачу, и needs_approval-карточка НЕ доезжала.
                                        # ЖИВОЙ ФАКТ (снимок 06.08.2026, 372 задачи): id=244
                                        # висела needs_approval с 03.08 — ЕДИНСТВЕННЫЙ открытый
                                        # needs_approval очереди, владелец её не видел ни разу
QUEUE_FROM_OWNER = "Filipp"             # ручные пробы владельца (id 14/89/90 — «проверка канала
                                        # одобрения»): ставятся с обеих полос, тема = 328. Тот же
                                        # класс: отчёты проб отсеивались фильтром (иронично —
                                        # пробы КАНАЛА, чей отчёт по каналу и не доезжал)
QUEUE_FROMS_PC = (QUEUE_FROM_PC, QUEUE_FROM_PC_DEV, QUEUE_FROM_PC_DEC,
                  QUEUE_FROM_PCLOC_DEC,
                  QUEUE_FROM_REVIZOR)    # метки полосы pc (карточки → тема PC-дев)
QUEUE_FROMS = (QUEUE_FROM, QUEUE_FROM_DEV, QUEUE_FROM_DEC,
               QUEUE_FROM_CURATOR, QUEUE_FROM_OWNER) + QUEUE_FROMS_PC  # фильтр отчётов: все наши
_TASK_PREFIXES = ("задача:", "оркестратор:", "task:")
_DEV_PREFIXES = ("тз:", "dev:", "tz:")  # дев-режим: произвольное ТЗ через headless CC, до 45 мин
_DEC_PREFIXES = ("декомпозируй:", "разбей:", "decompose:")  # крупное ТЗ → план шагов → по одному
_STRUCT_PREFIXES = _DEC_PREFIXES + _DEV_PREFIXES + _TASK_PREFIXES  # ВСЕ командные префиксы очереди:
                                        # матчатся ПЕРВЫМИ по началу сообщения, абсолютный приоритет
                                        # над зелёным allowlist (инцидент 23:49 11.07.2026)
# === ДЕДУП КАРТОЧЕК: ключ = НОМЕР + ГЕНЕРАЦИЯ (фикс дыры видимости 28.07.2026) ===
# Класс бага: голый id жив только до пересоздания листа очереди. Лист пересобрали — нумерация
# снова пошла с 1, а в памяти процесса от seed-on-start лежали номера прежней очереди (1..399) →
# новые задачи 1, 2, 3 (три failed 28.07) были отброшены как «уже показанные» и в 328 НЕ дошли.
# Фикс: к номеру добавлена «генерация» — колонка `created` очереди (момент постановки СТРОКИ).
# Пересобранная очередь ставит строки заново, поэтому её задача №1 несёт created=28.07, а не
# created прошлой №1 → совпадения номеров больше не глушат карточку. Хранилища — dict
# {str(id): генерация}: одна запись на номер (память не растёт), сверка O(1).
_SEEN_ANY = "*"                         # пометка «по номеру» (item под рукой нет — кнопка/«нет N»);
                                        # гасит ТОЛЬКО задачи, существовавшие на момент пометки
_reported = {}                          # задачи, уже отрапортованные (done/failed; память процесса)
_report_seeded = False                  # seed-on-start: не спамим историей done/failed при рестарте
_asked = {}                             # задачи needs_approval, по которым УЖЕ задан вопрос (дедуп)
# heartbeat/детект-зависания (части 1-2): анонс «в работе» и предупреждение «зависла» — по разу на задачу
_inprogress_seen = {}                   # задачи in_progress, по которым УЖЕ слали «🔄 в работе» (дедуп)
_stalled = {}                           # задачи, по которым УЖЕ слали «⚠️ зависла» (дедуп)
STALL_GRACE_SEC = 120                   # люфт НАД штатным потолком задачи
# {qid: (chat_id, topic_id, msg_id, base_text, task_text, task_from, st, sent_at)}
_curator_pending = {}                   # карточки, показывающие «куратор оценивает» — ждут edit
# ОДИН ОТЧЁТ О ЗАДАЧЕ (решение владельца 05.08.2026): вердикт куратора — СТРОКА в карточке задачи,
# а не второе сообщение. Сюда попадают (вид, id) терминалов, чей вердикт УЖЕ доехал до владельца
# внутри карточки задачи — их кураторская карточка-маркер своего сообщения в 328 не получает.
# Пометка ставится ТОЛЬКО по факту доставки (отправка/edit прошли) — не доехало, значит не вклеено,
# значит карточка уйдёт отдельным сообщением, как раньше: молча вердикт не исчезает.
# ПОМЕТКА ЖИВЁТ МИНУТЫ, А НЕ ВЕЧНО: карточка-маркер приходит следующим тиком (45с), а долгая память
# опасна — при ПЕРЕСОЗДАНИИ очереди номера начинаются заново (живой случай 28.07), и старый ключ
# погасил бы чужую карточку. {(вид, id): monotonic-метка}.
_curator_glued = {}
_CURATOR_GLUED_TTL = 3600               # сек: на порядок больше тика, на порядок меньше суток
_CURATOR_THINKING = "🧭 Куратор оценивает итог — вердикт через ~10с"
_CURATOR_WAIT_MAX = 240                 # сек до fallback-перерасчёта (CURATOR_TIMEOUT 180 + буфер) (даём демону/реаперу самому
                                        # довести терминал done/failed раньше тревоги владельцу).
                                        # Порог «зависла» — per-задача: _stall_threshold_sec(it).
                                        # Урок задачи 287 (22:55 13.07.2026): плоский порог 12 мин
                                        # тревожил за минуту до честного done долгого «тз:» (норма
                                        # до 45 мин) — класс «долго работает ≠ умерла» (ПК-вотчдог 5167365).

# Старт ПРОЦЕССА (devbot импортируется bot.py на старте) — граница seed-on-start: гасим только то,
# что стало терминальным ДО нас. SEED_GRACE_SEC — окно рестарта: задача, финишировавшая в эти
# секунды перед стартом, seed'ом НЕ гасится (её карточку мог не успеть отправить прошлый процесс;
# лишний дубль лучше тишины — цена ошибки в разные стороны разная).
_PROC_START_TS = time.time()
SEED_GRACE_SEC = 120


def _iso_ts(v):
    """ISO-строка очереди ('2026-07-28T10:18:55.172Z') → epoch-секунды UTC. Мусор/пусто → None."""
    try:
        s = str(v or "").strip().replace("Z", "+00:00")
        if not s:
            return None
        t = datetime.datetime.fromisoformat(s)
        if t.tzinfo is None:
            t = t.replace(tzinfo=datetime.timezone.utc)
        return t.timestamp()
    except Exception:
        return None


def _gen(it):
    """«Генерация» задачи = created из очереди (момент постановки СТРОКИ). Именно она переживает
    пересоздание листа: новый лист ставит строки заново, поэтому его №1 несёт другой created."""
    return str(it.get("created") or "")


def _seen(store, it):
    """True → карточка по ЭТОЙ задаче уже уходила. Сверяем номер И генерацию: одинаковый номер
    из ДРУГОЙ (пересозданной) очереди — другая задача, её показываем."""
    prev = store.get(str(it.get("id")))
    if prev is None:
        return False
    if isinstance(prev, tuple) and prev and prev[0] == _SEEN_ANY:
        c = _iso_ts(_gen(it))           # пометка «по номеру» с моментом простановки
        return c is None or c <= prev[1]  # созданная ПОЗЖЕ пометки — уже другая задача, не глушим
    return prev == _gen(it)


def _mark_seen(store, it):
    """Пометить задачу показанной (ключ — номер+генерация)."""
    store[str(it.get("id"))] = _gen(it)


def _mark_seen_by_id(store, qid):
    """Пометка по ГОЛОМУ номеру — когда строки очереди под рукой нет (кнопка/ответ «нет N»).
    Держим момент простановки: задача с тем же номером, СОЗДАННАЯ позже, под неё не попадёт."""
    store[str(qid)] = (_SEEN_ANY, time.time())


def _forget_seen(store, qid):
    """Снять пометку по номеру (одобренная задача обязана отрапортоваться штатно)."""
    store.pop(str(qid), None)


def _seed_silences(it):
    """True → задача стала ТЕРМИНАЛЬНОЙ ещё до старта процесса (история) → seed её гасит.
    Всё, что финишировало ПОСЛЕ старта — рапортуем ПРИ ЛЮБОМ номере (в этом и была дыра).
    Время не прочли → НЕ гасим: видимость дороже лишней карточки."""
    ts = _iso_ts(it.get("updated"))
    if ts is None:
        return False
    return ts < _PROC_START_TS - SEED_GRACE_SEC


# === ХВОСТ 1 (28.07.2026): «ВЗЯЛ В РАБОТУ» ЧЕРЕЗ ЖУРНАЛ СОБЫТИЙ, А НЕ ЧЕРЕЗ СНИМОК ===
# Анонс «🔄 в работе» рождался ТОЛЬКО из 45-секундного снимка in_progress, а задача живёт
# 5–9 секунд — между двумя опросами она успевала родиться и умереть, в снимок не попадала и
# анонс не приходил НИ РАЗУ (живые примеры 28.07: задачи 14 и 15, обе done без «в работе»).
# Опрос состояния тут бессилен по природе. Демон пишет ФАКТ взятия строкой JSONL
# (orchestrator_daemon.write_claim_event, единственная точка — process_new), мы читаем журнал
# с байтового оффсета и выносим карточку. Событие переживает любую скорость задачи.
# Дедуп ОБЩИЙ со снимком (_inprogress_seen, ключ номер+генерация) — двух карточек не будет.
# Журнала нет (демон старый / не запускался) → пусто → прежнее поведение по снимку, без регресса.
CLAIM_LOG_PATH = os.path.join(ROOT, "orchestrator_claims.jsonl")
_LIVE_CLAIM_LOG_PATH = CLAIM_LOG_PATH   # заморожен на импорте: тесты подменяют CLAIM_LOG_PATH
_claims_offset = 0                      # прочитано байт журнала взятий (в пределах процесса)


def _claims_live_path(p):
    """True → это БОЕВОЙ журнал взятий (а не тестовая подмена). Симметрия с писателем демона."""
    try:
        return os.path.abspath(p) == os.path.abspath(_LIVE_CLAIM_LOG_PATH)
    except Exception:
        return True                     # сомнение → считаем боевым (в сторону тишины под тестом)


def _drain_claim_events(path=None):
    """Считать НОВЫЕ строки журнала взятий и вернуть их списком dict-ов (оффсет сдвигается).
    Читаем в БИНАРНОМ режиме: оффсет байтовый, seek по нему в текстовом режиме не определён.
    Недописанный хвост без '\\n' не трогаем — заберём следующим тиком (торн-райт не теряем).
    Журнал подрезан демоном (ротация) → читаем с начала: дубли гасит дедуп по номер+генерация.
    Под тестом БОЕВОЙ журнал не читаем (демон в него так же не пишет): иначе живые взятия
    протекают карточками в чужие тесты — так и случилось на первом же прогоне 28.07, красные
    test_inbox/test_claim_event. Тест обязан подсунуть свой путь (reset ставит CLAIM_LOG_PATH)."""
    global _claims_offset
    p = path or CLAIM_LOG_PATH
    if _claims_live_path(p) and task_metrics.under_test(
            (sys.argv[0] if sys.argv else ""), os.environ, sys.modules):
        return []
    try:
        size = os.path.getsize(p)
    except OSError:
        return []                       # журнала нет — фоллбэк на снимок in_progress
    if size < _claims_offset:
        _claims_offset = 0
    if size == _claims_offset:
        return []
    try:
        with open(p, "rb") as f:
            f.seek(_claims_offset)
            raw = f.read()
    except OSError as e:
        log.warning("devbot: журнал взятий не прочитан (%s) — анонс пойдёт по снимку", e)
        return []
    cut = raw.rfind(b"\n")
    if cut < 0:
        return []
    _claims_offset += cut + 1
    out = []
    for line in raw[:cut].split(b"\n"):
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line.decode("utf-8", "replace"))
        except Exception:
            continue                    # битая строка журнала не должна валить опрос
        if isinstance(ev, dict) and ev.get("id") is not None \
                and str(ev.get("from")) in QUEUE_FROMS:
            out.append(ev)
    return out


def _claims_seek_end(path=None):
    """Seed-on-start: перемотать журнал взятий в конец, ничего не вынося (история молчит)."""
    global _claims_offset
    try:
        _claims_offset = os.path.getsize(path or CLAIM_LOG_PATH)
    except OSError:
        _claims_offset = 0


# Потолок result у исполнителей: orchestrator_daemon.RESULT_MAX = 4500 (запас под лимит Bridge
# 5000). Демон/ПК-агент режут отчёт ДО записи в очередь — devbot видит уже обрубок и обязан
# сказать об этом вслух: молча срезанный хвост читался как полный отчёт (28.07.2026).
RESULT_CAP = 4500

# ХВОСТ 2 закрыт 28.07.2026: демон (orchestrator_daemon.cap_result) сам дописывает в конец result
# машиночитаемую пометку с ПОЛНОЙ длиной ДО обрезки. Нашли её — число уже в теле карточки, свою
# «длины взять неоткуда» НЕ добавляем (иначе карточка противоречила бы сама себе). Не нашли, а
# result упёрся в потолок — прежняя пометка-фоллбэк: так пишет ПК-агент (чужой контур, его мы не
# трогаем) и старые записи очереди, сделанные демоном до этой правки.
_TRUNC_FULL_RE = re.compile(r"ОБРЕЗАН ДЕМОНОМ: полная длина (\d+) симв")


def _result_full_len(body):
    """Полная длина ДО обрезки из пометки исполнителя. Пометки нет → None."""
    m = _TRUNC_FULL_RE.search(body or "")
    return int(m.group(1)) if m else None


def _result_body(it, empty="(пустой результат)"):
    """Текст result для карточки + ЯВНАЯ пометка обрезки, если он упёрся в потолок исполнителя."""
    raw = it.get("result")
    body = str(raw) if raw not in (None, "") else empty
    if _result_full_len(body) is not None:
        return body                     # исполнитель сам назвал полную длину — она уже в тексте
    n = len(body)
    if n >= RESULT_CAP:
        body += (f"\n\n✂️ РЕЗУЛЬТАТ ОБРЕЗАН: в очереди {n} симв. — это потолок исполнителя "
                 f"({RESULT_CAP}, orchestrator_daemon.RESULT_MAX), значит хвост срезан ДО записи. "
                 f"Полной длины исходного отчёта эта запись не несёт (сделана исполнителем без "
                 f"пометки длины — ПК-агент либо демон до 28.07.2026); недостающее ищи в "
                 f"splinter.log/cc_log или переспроси задачу короче.")
    return body


# Маркер клона (микрофикс §7 12.07.2026, инцидент 156): демон при возврате задачи из-под чужого
# рестарта (orchestrator_daemon._requeue_foreign_restart) дописывает «[повтор задачи N]» в КОНЕЦ
# текста клона. Карточки такой задачи несут «(повтор)» в заголовке — владелец отличает клон от
# новой задачи (в 156 «задвоение карточки» выглядело как дубль). Константа продублирована из
# orchestrator_daemon.REPEAT_MARK (devbot живёт в процессе bot.py, демон не импортируем).
REPEAT_MARK = "[повтор задачи"


def _is_repeat_item(it):
    """True → задача рождена ПОВТОРНОЙ постановкой той же задачи (клон возврата, маркер в task_text)."""
    return REPEAT_MARK in str(it.get("task_text") or "")


# «да N» / «нет N» (+ англ., + опц. # и пунктуация) — ответ Филиппа на запрос подтверждения (заход 2б-2)
_APPROVAL_RE = re.compile(r"^(да|нет|yes|no)\b[\s,.:]*#?\s*(\d+)\s*$", re.IGNORECASE)
_YES = ("да", "yes")


def _apply_verdict(bridge, qid, yes):
    """Применить решение владельца к задаче qid. ТЕЛО ЛЕГАСИ-ПУТИ «да N»/«нет N» — вынесено
    дословно, чтобы новая форма ответа (с названным объектом) исполнялась ТЕМ ЖЕ кодом."""
    if yes:
        r = bridge.approve_task(qid, "Filipp")
        if r.get("ok"):
            _forget_seen(_reported, qid)   # пусть дальнейший done/failed по ней отрапортуется штатно
            return (f"✅ Задача {qid} одобрена — демон выполнит approved-операцию по op-коду "
                    f"(git_push / restart_splinter) и принесёт результат сюда. Вне авто-перечня → failed "
                    f"«требуется решение владельца — переставь задачу в 328 после его ответа».")
        if r.get("error") == "not_awaiting":
            return f"🤖 Задача {qid} не ждёт подтверждения (статус {r.get('status')}). Ничего не сделал."
        if r.get("error") == "not_found":
            return f"🤖 Задачи {qid} нет в очереди."
        return f"🤖 approve не прошёл: {r.get('error')}"
    else:
        r = bridge.complete_task(qid, "failed", "отклонено Филиппом")
        if r.get("ok"):
            _mark_seen_by_id(_reported, qid)   # уже сообщили «отклонена» — не дублируем failed-рапортом
            return f"🚫 Задача {qid} отклонена — статус failed."
        return f"🤖 Не удалось отклонить задачу {qid}: {r.get('error')}"


# ===== ОТВЕТ С НАЗВАННЫМ ОБЪЕКТОМ (31.07.2026, инцидент карточки 95) =====
# ЖИВОЙ ФАКТ: 31.07 09:23 и 09:24 UTC владелец ДВАЖДЫ ответил на карточку задачи 95 текстом
# «да systemctl restart splinter» (первый раз обычным сообщением, второй — реплаем на карточку).
# Приёмник знал ТОЛЬКО «да N»/«нет N» → оба раза выдал общую справку и ответ не принял. Доктрина
# требует, чтобы операции высшего вида подтверждались ответом с НАЗВАННЫМ ОБЪЕКТОМ, а не коротким
# «да N» — но приёмник этой формы не знал вовсе, и правило жило только на бумаге.
# ТЕПЕРЬ: «да|нет <объект>» привязывается к карточке ПО НОМЕРУ в тексте ИЛИ ПО РЕПЛАЮ на её
# сообщение (номер вынимается ИЗ ТЕКСТА карточки — restart-proof, память процесса не нужна);
# названный объект СВЕРЯЕТСЯ с объектами карточки; несовпадение и непонятая форма получают
# КОНКРЕТНЫЙ отказ («не принято, потому что …» + что ожидалось), а не общую справку.
# НЕ ТРОНУТО: «да N»/«нет N» (легаси _APPROVAL_RE → _apply_verdict, байт-в-байт) и кнопки ✅/❌.
# ПОНЯТИЕ «высший вид карточки» НЕ ЗАВОДИМ (его в коде нет и не было): приёмник учится ФОРМЕ;
# запрет короткого «да N» для высших операций — отдельное решение владельца, отдельным заходом.
# ИЗОЛЯЦИЯ 328/PC: свободный текст с «да …» перехватывается ТОЛЬКО когда он реально привязан к
# ОТКРЫТОЙ карточке (реплай или номер живой карточки); иначе — прежний путь байт-в-байт.

# «да|нет [N] [объект]» — шапка ответа; объект = весь остаток (DOTALL: многострочный ответ не теряем)
_VERDICT_HEAD_RE = re.compile(r"^(да|нет|yes|no)\b[\s,.:]*#?\s*(\d+)?\s*(.*)$", re.IGNORECASE | re.DOTALL)
# номер карточки из ТЕКСТА сообщения, на которое ответили реплаем («⚠️ Задача 95 [vps] требует …»)
_CARD_ID_RE = re.compile(r"задач[аиуе]\s*№?\s*(\d+)", re.IGNORECASE)
# объект, названный в карточке: литерал в обратных кавычках (так его называет куратор/демон)
_OBJ_BACKTICK_RE = re.compile(r"`([^`\n]{3,120})`")
# … либо явная команда прямо в тексте карточки (карточки без обратных кавычек)
_OBJ_CMD_RE = re.compile(
    r"(systemctl\s+(?:restart|start|stop|disable|enable)\s+[\w.@-]+"
    r"|clasp\s+(?:redeploy|push|deploy|run)"
    r"|git\s+push"
    r"|sqlite3\s+[\w./-]+)", re.IGNORECASE)
# op-код карточки → каноническое имя объекта (зеркало AUTO_OPS демона)
_OP_CANON = {"git_push": "git push", "restart_splinter": "systemctl restart splinter"}
_OBJ_TRIM = " \t\n\r`'\"«»‘’“”.,:;!?()[]{}"
_OBJ_MIN_CHARS = 4          # короче — не «названный объект», а обрывок пунктуации


def _norm_obj(s):
    """Нормализация объекта для сверки: снять кавычки/пунктуацию по краям, схлопнуть пробелы, lower."""
    return re.sub(r"\s+", " ", str(s or "").strip(_OBJ_TRIM)).strip().lower()


def _card_objects(card_text):
    """Объекты, НАЗВАННЫЕ в карточке (порядок = приоритет показа): op-код → каноническая команда,
    литералы в обратных кавычках, явные команды в тексте. Пусто → карточка объекта не называет,
    сверять не с чем (это НЕ повод одобрить вслепую — см. вызывающий код)."""
    w = str(card_text or "")
    objs = []
    m = _INBOX_OP_RE.search(w)
    if m:
        canon = _OP_CANON.get(m.group(1).lower())
        if canon:
            objs.append(canon)
    objs.extend(_OBJ_BACKTICK_RE.findall(w))
    objs.extend(_OBJ_CMD_RE.findall(w))
    out, seen = [], set()
    for o in objs:
        k = _norm_obj(o)
        if k and k not in seen:
            seen.add(k)
            out.append(o.strip())
    return out


def _object_matches(named, card_objs):
    """Названный владельцем объект совпал с объектом карточки → сам объект карточки, иначе None.
    Совпадение — по нормализованному вхождению в любую сторону («restart splinter» засчитывается
    против `systemctl restart splinter`): владелец доказывает, что ПРОЧИТАЛ карточку, а не диктует."""
    n = _norm_obj(named)
    if len(n) < _OBJ_MIN_CHARS:
        return None
    for o in card_objs:
        c = _norm_obj(o)
        if c and (n == c or n in c or c in n):
            return o
    return None


def _card_id_from_text(t):
    """Номер задачи из текста карточки, на которую ответили реплаем. Нет номера → None."""
    m = _CARD_ID_RE.search(str(t or ""))
    return int(m.group(1)) if m else None


def _open_approval_cards(bridge):
    """Открытые карточки needs_approval ОБЕИХ полос → (чтение удалось?, [items]). read-only."""
    try:
        r = bridge.get_pending("needs_approval", lane="all")
    except Exception as e:
        log.warning("devbot: чтение открытых карточек упало (%s)", e)
        return False, []
    if not r.get("ok"):
        return False, []
    return True, [it for it in (r.get("items") or []) if isinstance(it, dict)]


def _open_ids_hint(items):
    """Хвост-подсказка «какие карточки открыты» для конкретного отказа."""
    ids = [str(it.get("id")) for it in items if it.get("id") is not None][:10]
    if not ids:
        return "Открытых карточек сейчас нет."
    return "Открытые карточки: " + ", ".join(ids) + "."


def _how_to_answer(qid=None, items=None):
    """Подсказка «как ответить». Открыта РОВНО одна карточка → подставляем её номер вместо «N»,
    чтобы владелец мог повторить ответ точно, не разыскивая id."""
    if qid is None and items and len(items) == 1 and items[0].get("id") is not None:
        qid = items[0].get("id")
    n = qid if qid is not None else "N"
    return (f"Как ответить: «да {n}» / «нет {n}», либо кнопкой ✅/❌ под карточкой, либо РЕПЛАЕМ на "
            f"саму карточку — тогда можно с названным объектом («да systemctl restart splinter»).")


def _named_object_reply(text, bridge, reply_text, lane):
    """Новая форма ответа: «да|нет [N] [объект]». Возврат — текст ответа владельцу либо None
    («это не ответ на карточку, обработай прежним путём»). Красное НЕ ослаблено: ничего не
    исполняется, только approve/reject той же задачи, что и раньше."""
    t = (text or "").strip()
    head = _VERDICT_HEAD_RE.match(t)
    owned = (lane == "inbox") or bool(reply_text)   # инбокс и реплай на карточку — наша территория
    if not head:
        return None                                  # нет «да»/«нет» в начале — это вообще не вердикт
    word = head.group(1).lower()
    yes = word in _YES
    num = head.group(2)
    obj = (head.group(3) or "").strip()
    if not _norm_obj(obj):
        obj = ""                                     # «да 95.» — хвост из пунктуации объектом не считаем
    qid = int(num) if num else _card_id_from_text(reply_text)
    ok_read, items = _open_approval_cards(bridge)
    if qid is None:
        if not owned:
            return None                              # 328/PC: свободный текст не перехватываем
        return ("🚫 Не принято, потому что не понял, к какой карточке относится ответ: номера в "
                "тексте нет и это не реплай на карточку.\n"
                + (_open_ids_hint(items) if ok_read else "Очередь сейчас не читается.") + "\n"
                + _how_to_answer(items=items if ok_read else None))
    item = next((it for it in items if str(it.get("id")) == str(qid)), None)
    if not ok_read:
        if not owned:
            return None
        return (f"🚫 Не принято, потому что очередь подтверждений сейчас не читается — сверить "
                f"объект с карточкой {qid} не могу, вслепую не одобряю. Повтори через минуту "
                f"или тапни ✅/❌ под карточкой.")
    if item is None:
        if not owned:
            return None                              # 328: номер не от живой карточки → прежний путь
        return (f"🚫 Не принято, потому что задачи {qid} нет среди открытых карточек (уже закрыта "
                f"или номер не тот).\n" + _open_ids_hint(items))
    if not obj:
        return _apply_verdict(bridge, qid, yes)      # «да» + реплай = ровно то же, что «да N»
    objs = _card_objects(str(item.get("result") or ""))
    if not objs:
        return (f"🚫 Не принято, потому что карточка задачи {qid} объект не называет (ни op-кода, "
                f"ни команды в тексте) — сверить «{obj[:120]}» не с чем, а вслепую не одобряю.\n"
                + _how_to_answer(qid))
    hit = _object_matches(obj, objs)
    if hit is None:
        expected = " / ".join(f"«{o}»" for o in objs[:3])
        return (f"🚫 Не принято, потому что названный объект не совпал: ты назвал «{obj[:120]}», "
                f"а карточка задачи {qid} — про {expected}.\n"
                f"Ожидалось: «{word} {qid} {objs[0]}» (либо «{word} {qid}» без объекта, либо кнопка).")
    res = _apply_verdict(bridge, qid, yes)
    return f"🔒 Объект сверён с карточкой {qid}: «{hit}».\n{res}"


def _try_approval_reply(text, bridge, reply_text=None, lane=None):
    """«да N» → approve_task(N); «нет N» → complete_task(N, failed) — ЛЕГАСИ, байт-в-байт.
    Не подошло → новая форма «да|нет [N] [объект]» с привязкой по номеру ИЛИ по реплаю на
    сообщение карточки (31.07.2026). Иначе None.
    Проверяется ПЕРВОЙ в handle_command (специфичный паттерн ответа на запрос подтверждения).
    FAIL-SAFE: любое исключение НОВОЙ ветки → None (прежнее поведение, не хуже)."""
    m = _APPROVAL_RE.match((text or "").strip())
    if m:
        return _apply_verdict(bridge, int(m.group(2)), m.group(1).lower() in _YES)
    try:
        return _named_object_reply(text, bridge, reply_text, lane)
    except Exception as e:
        log.warning("devbot: разбор ответа с названным объектом упал (%s) — прежний путь", e)
        return None


def inbox_reject_hint(text, bridge):
    """Тема-инбокс: текст, который приёмник НЕ понял → КОНКРЕТНОЕ «не принято, потому что …»
    вместо общей справки (31.07.2026). Причина называется по форме самого текста."""
    t = (text or "").strip()
    if t.lower().startswith(_STRUCT_PREFIXES + _PC_TEXT_PREFIXES):
        # постановка ТЗ/команды прилетела не в ту тему — причина конкретная, и адрес назван
        return ("🚫 Не принято, потому что это тема-инбокс подтверждений, а не постановки: тут "
                "принимаются только ответы на карточки. Команды и ТЗ — в тему 328 (полоса vps) "
                "или PC-дев.")
    ok_read, items = _open_approval_cards(bridge)
    tail = ((_open_ids_hint(items) if ok_read else "Очередь сейчас не читается.") + "\n"
            + _how_to_answer(items=items if ok_read else None))
    if re.search(r"\d", t):
        return ("🚫 Не принято, потому что в ответе нет решения: номер вижу, а «да» или «нет» — нет.\n"
                + tail)
    return ("🚫 Не принято, потому что это не похоже на ответ на карточку: нет ни «да»/«нет», "
            "ни номера карточки, и это не реплай на карточку.\n" + tail)


# ===================== РОУТЕР ТЕАТРА (кусок 3 «единый пульт», 07.07.2026) =====================
# ОДИН вход (тема 328) для всех команд — система САМА определяет театр исполнения (vps | pc).
# Слой 1 (детерминированный, БЕЗ LLM): явный префикс «пк:»/«pc:» сразу после команды → pc
# (префикс срезается); keyword-классы pc/vps — ровно один класс совпал → он и театр. Оба или
# ни один → слой 2: думатель-классификатор (claude -p, --model haiku --fallback-model sonnet,
# --max-turns 1 — чистый генератор, ничего не исполняет; строгий JSON {"theater":"vps"|"pc"}).
# FAIL-SAFE любого сбоя слоя 2 (запуск/таймаут/exit!=0/мусор) → vps (= прежнее поведение, не
# хуже) + строка-подсказка в карточке приёма. Тема 829 = явный запасной вход БЕЗ роутера
# (форс pc, как раньше). Театр=pc: одиночные «тз:»/«задача:» → ТА ЖЕ 328-метка from (карточки
# идут в тему ПОСТАНОВКИ 328 по from-метке) + lane=pc (claim'ит ПК-агент); «декомпозируй:» →
# родитель QUEUE_FROM_PC_DEC (опора на кусок 2: план строит VPS-демон, шаги lane=pc по одному,
# отчёты цепи — в теме PC-дев по метке цепи). Изоляция полос НЕ ослаблена: роутер только
# ВЫБИРАЕТ полосу при enqueue, claim-механику не трогает. Красное НЕ ослаблено (роутер ничего
# не исполняет). Откат: THEATER_ROUTER=0 в .env + restart splinter — прежнее поведение
# байт-в-байт (пк:-префикс НЕ срезается, 🎭 не показывается, слой 2 не зовётся).
CLAUDE_BIN = "/usr/bin/claude"          # зеркало orchestrator_daemon.CLAUDE_BIN (импорт демона в
                                        # процесс бота нельзя — signal.signal на import, см. выше)
ROUTER_KW_PC = ("userbot", "suggest", "playbook", "модербот", "dispatch",
                "d:\\turbobaby-userbot", "приветстви", "черновик клиенту")
ROUTER_KW_VPS = ("splinter", "bridge", "manager-bot", "registry", "гейт", "cc_log",
                 "devbot", "orchestrator_daemon", "vps")
ROUTER_HINT = "театр: vps (по умолчанию); нужен ПК — префикс пк:"
_PC_TEXT_PREFIXES = ("пк:", "pc:")      # явный префикс театра сразу после команды («тз: пк: …»)


def _router_on():
    """THEATER_ROUTER (деф. 1 = включён). Лениво на каждый вызов: bot.py импортирует devbot
    ДО load_dotenv() (как pc_dev_topic)."""
    return str(os.getenv("THEATER_ROUTER", "1")).strip().lower() not in ("0", "false", "off")


def _router_timeout():
    """Таймаут слоя 2 в секундах (THEATER_ROUTER_TIMEOUT, деф. 45с; haiku отвечает за секунды)."""
    try:
        return int(os.getenv("THEATER_ROUTER_TIMEOUT", "45") or 45)
    except (TypeError, ValueError):
        return 45


def _pc_dec_local():
    """PC_DEC_LOCAL (деф. 0 = ВЫКЛ, старое поведение). 1 → родитель «пк: декомпозируй» ставится
    как from=Filipp-pcloc-dec + lane=pc: его целиком (план → релиз шагов → надзор) ведёт
    ЛОКАЛЬНЫЙ дирижёр ПК (pc_orchestrator, PC_LOCAL_DEC=1; живьём доказан родителем 195),
    VPS-демон такую цепь НЕ трогает (его надзор группирует строго Filipp-pc-dec). Карточки
    цепи devbot уже носит (682a881). Откат = PC_DEC_LOCAL=0 в .env + restart splinter,
    без деплоя. Лениво на каждый вызов (bot.py импортирует devbot ДО load_dotenv)."""
    return str(os.getenv("PC_DEC_LOCAL", "0")).strip().lower() in ("1", "true", "on")


def _classify_theater(task_text):
    """Слой 2: думатель-классификатор театра — claude -p дешёвым кондуктором haiku→sonnet
    (--max-turns 1, --output-format json; зеркало orchestrator_daemon._thinker_exec).
    → 'vps' | 'pc' | None при ЛЮБОМ сбое (fail-safe, решает вызывающий)."""
    model = (os.getenv("ROUTER_MODEL") or "haiku").strip() or "haiku"
    fallback = (os.getenv("ROUTER_MODEL_FALLBACK") or "sonnet").strip() or "sonnet"
    prompt = (
        "Ты — роутер театра исполнения дев-задач TurboBaby. Театры:\n"
        "- vps: серверный репозиторий manager-bot на VPS (Splinter-бот, bot.py, Apps Script "
        "Bridge, гейт тестов, cc_log, devbot, orchestrator_daemon, деплой/рестарт на VPS).\n"
        "- pc: репозиторий userbot на ПК Windows (D:\\turbobaby-userbot: suggest.py, playbook, "
        "модербот, Dispatch, приветствия и черновики ответов клиентам).\n"
        "Определи театр задачи. Ответь СТРОГО одним JSON без пояснений и без markdown:\n"
        "{\"theater\":\"vps\"|\"pc\",\"reason\":\"одна строка\"}\n\n"
        f"ЗАДАЧА (дословно):\n{str(task_text or '')[:2000]}")
    child_env = dict(os.environ)
    child_env.setdefault("HOME", "/root")
    child_env.setdefault("PATH", "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin")
    child_env.pop("ANTHROPIC_API_KEY", None)   # как думатели демона: по ~/.claude, не платный API
    child_env.pop("OPENAI_API_KEY", None)
    cmd = [CLAUDE_BIN, "-p",
           "--model", model,
           "--fallback-model", fallback,
           "--output-format", "json",
           "--max-turns", "1",
           prompt]                             # prompt последним (тест-моки читают args[-1])
    try:
        proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                              timeout=_router_timeout(), env=child_env)
    except Exception as e:
        log.warning("theater-router: классификатор не отработал (%s) — fail-safe vps", e)
        return None
    if proc.returncode != 0:
        log.warning("theater-router: классификатор exit=%s — fail-safe vps", proc.returncode)
        return None
    out = (proc.stdout or "").strip()
    try:
        env_j = json.loads(out)
        if isinstance(env_j, dict) and "result" in env_j:   # CLI-конверт --output-format json
            out = (env_j.get("result") or "").strip()
    except Exception:
        pass
    i, j = out.find("{"), out.rfind("}")
    if i < 0 or j <= i:
        return None
    try:
        d = json.loads(out[i:j + 1])
    except Exception:
        return None
    th = str(d.get("theater") or "").strip().lower() if isinstance(d, dict) else ""
    return th if th in ("vps", "pc") else None


def _route_theater(task_text):
    """Роутер театра → (театр 'vps'|'pc', текст без явного пк:-префикса, note|None —
    строка-подсказка при fail-safe слоя 2)."""
    t = (task_text or "").strip()
    low = t.lower()
    for p in _PC_TEXT_PREFIXES:
        if low.startswith(p):
            return "pc", t[len(p):].strip(), None
    pc_hit = any(k in low for k in ROUTER_KW_PC)
    vps_hit = any(k in low for k in ROUTER_KW_VPS)
    if pc_hit != vps_hit:                      # ровно один класс совпал → слой 1 решил
        return ("pc" if pc_hit else "vps"), t, None
    th = _classify_theater(t)                  # оба/ни один → слой 2 (думатель)
    if th is not None:
        return th, t, None
    return "vps", t, ROUTER_HINT               # fail-safe: vps + подсказка владельцу


def _route_328(task_text):
    """Роутер для темы 328. Выключен (THEATER_ROUTER=0) → (None, текст как есть, None) —
    прежнее поведение байт-в-байт, 🎭 в карточке не показываем.
    ТОТАЛЬНЫЙ fail-safe (инцидент 07.07.2026): ЛЮБОЕ исключение роутера (не только пойманные
    внутри _classify_theater сбои классификатора — unauthorized CLI, exit!=0, таймаут, мусор) →
    театр vps + подсказка в карточке. Постановка задачи из-за роутера НЕ падает НИКОГДА."""
    if not _router_on():
        return None, task_text, None
    try:
        return _route_theater(task_text)
    except Exception as e:
        log.warning("theater-router: роутер упал (%s) — ТОТАЛЬНЫЙ fail-safe vps", e)
        return "vps", task_text, ROUTER_HINT


def _router_card(theater, note):
    """Хвост карточки приёма с решением роутера: «🎭 vps|pc» (+ подсказка fail-safe).
    theater=None (роутер выключен) → пустая строка (карточка как раньше)."""
    if theater is None:
        return ""
    s = f"\n🎭 {theater}"
    if note:
        s += f"\n{note}"
    return s


def _bridge_err_detail(r):
    """Человекочитаемое описание ошибки Bridge для Telegram-карточки.
    Показывает реальную причину вместо голого кода «internal_error»."""
    err = str(r.get("error") or "unknown")
    msg = str(r.get("message") or "")
    # Google Sheets LockService timeout — появляется на разных языках (нем./англ./etc.)
    _LOCK_MARKERS = ("lock", "exklusiv", "zeitübers", "timed out waiting",
                     "waitlock", "exclusive", "exklus")
    if err == "internal_error" and any(m in msg.lower() for m in _LOCK_MARKERS):
        return "Bridge занят (Google lock), повтори через ~1 мин"
    if err == "timeout":
        return "Bridge не ответил (timeout), повтори через ~1 мин"
    if err == "internal_error":
        detail = msg[:100].strip() if msg else ""
        return f"internal_error: {detail}" if detail else "internal_error (Bridge)"
    if msg:
        return f"{err}: {msg[:100]}"
    return err


def _find_enqueued(bridge, frm, text):
    """Verify после сбойного enqueue: есть ли НАША задача (тот же from + текст ДОСЛОВНО) в new
    (обе полосы)? → id | None. Любой сбой чтения → None (не хуже прежнего).
    NFC-нормализация обеих сторон — устойчивость к Unicode-вариантам (тайский, emoji)."""
    try:
        rr = bridge.get_pending("new", lane="all")
        if not rr.get("ok"):
            return None
        needle = unicodedata.normalize("NFC", text)
        for it in rr.get("items", []):
            if isinstance(it, dict) and str(it.get("from") or "") == frm \
                    and unicodedata.normalize("NFC", str(it.get("task_text") or "")) == needle:
                return it.get("id")
    except Exception:
        return None
    return None


# === КЛЮЧ ПОСТАНОВКИ (дедуп задач, класс дублей 164/165 и 167/168, 02.08.2026) ===
# Ключ несёт СООБЩЕНИЕ-постановку, а не её текст: осознанный повтор владельца — это НОВОЕ
# сообщение, у него другой ключ, и он проходит всегда. Разбор формы — bridge_client, блок
# «ДЕДУП ПОСТАНОВКИ ЗАДАЧИ». Контекст-переменная, а не аргумент через 11 веток _try_enqueue:
# постановка одна, а мест вызова много; asyncio.to_thread копирует контекст на КАЖДЫЙ вызов,
# поэтому параллельные сообщения ключами не пересекаются.
_MSG_KEY = contextvars.ContextVar("devbot_msg_key", default="")


def _msg_key(msg):
    """Ключ сообщения-постановки: (чат, id сообщения). Telegram нумерует id в пределах чата —
    пара уникальна. ЛЮБОЙ сбой → «» (дедупа нет, постановка идёт как раньше)."""
    try:
        return f"tg:{msg.chat_id}:{msg.message_id}"
    except Exception:
        return ""


def _dedup_key(frm, text):
    """Ключ дедупа постановки: сообщение + отпечаток САМОЙ постановки (метка+текст).
    Отпечаток нужен на случай, когда одно сообщение породит две РАЗНЫЕ постановки — они не
    должны схлопнуться. Нет сообщения (синтетика/прямой вызов) → «» = дедупа нет."""
    src = (_MSG_KEY.get() or "").strip()
    if not src:
        return ""
    body = unicodedata.normalize("NFC", f"{frm}\x00{text}")
    return f"{src}:{hashlib.sha1(body.encode('utf-8')).hexdigest()[:12]}"


def _enqueue_reliable(bridge, frm, text, lane=None):
    """Постановка, которая НЕ падает наружу зря (инцидент 07.07.2026, задача 138): Bridge в сбое
    (404 на redirect-echo) может ИСПОЛНИТЬ enqueue, потеряв ответ («unauthorized»/request_failed
    клиенту) — Филипп видел «не удалось», хотя задача встала. Слепой ретрай дал бы ДУБЛЬ, поэтому:
    (1) enqueue; ok → как раньше; (2) сбой → verify: задача с тем же from+текстом уже в new →
    ответ потерялся, считаем поставленной (её id); (3) не нашли → РОВНО один повтор enqueue;
    (4) снова сбой → честная ошибка (карточка «не удалось», как раньше). Не хуже прежнего ни в
    одной ветке; красное не ослаблено (это только постановка в очередь)."""
    kw = {} if lane is None else {"lane": lane}      # без lane зовём БЕЗ kwarg (форма как раньше)
    key = _dedup_key(frm, text)
    if key:
        kw["dedup_key"] = key        # без ключа форма вызова прежняя байт-в-байт
    r = bridge.enqueue_task(frm, text, **kw)
    if r.get("ok"):
        return r
    err1 = r.get("error")
    qid = _find_enqueued(bridge, frm, text)
    if qid is not None:
        log.warning("enqueue: ответ потерялся (%s), но задача %s найдена в new — поставлена", err1, qid)
        return {"ok": True, "id": qid}
    r2 = bridge.enqueue_task(frm, text, **kw)
    if r2.get("ok"):
        log.warning("enqueue: первая попытка упала (%s) — повтор успешен (id=%s)", err1, r2.get("id"))
    else:
        log.warning("enqueue: обе попытки упали (%s / %s) — честная ошибка Филиппу", err1, r2.get("error"))
    return r2


def _canon_theater_prefix(t):
    """Канонизация порядка префиксов: «пк: тз: X» → «тз: пк: X» (команда первой, театр внутри).
    Инцидент 23:49 11.07.2026: лидирующий «пк:» ПЕРЕД командным префиксом не матчился ни одним
    структурированным префиксом → «пк: декомпозируй: <крупное ТЗ>» падал мимо очереди в зелёный
    allowlist и угонялся словом из тела ТЗ (простыня журнала вместо постановки родителя).
    Перестановка чисто СИНТАКСИЧЕСКАЯ: дальше работает прежний слой 1 роутера (явный пк:-префикс
    ПОСЛЕ команды); THEATER_ROUTER=0 и полоса pc ведут себя с «тз: пк: X» ровно как раньше.
    Театр-префикс БЕЗ командного дальше — не трогаем (это не команда очереди)."""
    low = t.lower()
    for p in _PC_TEXT_PREFIXES:
        if not low.startswith(p):
            continue
        rest = t[len(p):].strip()
        rl = rest.lower()
        for cp in _STRUCT_PREFIXES:
            if rl.startswith(cp):
                body = rest[len(cp):].strip()
                return f"{rest[:len(cp)]} {p} {body}".strip()
        break
    return t


def _try_enqueue(text, bridge, lane="vps", msg_key=None):
    """Если текст начинается с префикса задачи — кладём в очередь оркестратора. Иначе None.
    msg_key (02.08.2026) — ключ сообщения-постановки (`tg:<чат>:<id>`, см. _msg_key): одно
    сообщение = одна задача, сколько бы раз постановка ни ушла в мост. Пусто/не передан →
    дедупа нет, поведение прежнее.
    «тз:»/«dev:» → метка QUEUE_FROM_DEV (демон даст 45 мин); «задача:» → быстрый режим (10 мин).
    Проверяется ДО allowlist (иначе ключевые слова в тексте задачи перехватили бы зелёную команду).
    lane='pc' (тема PC-дев, 04.07.2026): «тз:»/«задача:» → enqueue с lane='pc' и метками
    Filipp-pc-dev / Filipp-pc (исполняет ПК-агент); «декомпозируй:» (ПК-театр кусок 2,
    07.07.2026) → родитель QUEUE_FROM_PC_DEC БЕЗ lane (план строит VPS-демон — единственный
    планировщик), шаги демон релизит на lane=pc по одному.
    lane='vps' (328, кусок 3 «единый пульт» 07.07.2026): текст задачи идёт через роутер театра
    (_route_328). Театр vps → вызовы enqueue_task байт-в-байт как раньше (БЕЗ lane — Bridge
    дефолтит vps); театр pc → одиночные с 328-меткой + lane='pc' (карточки в тему постановки),
    «декомпозируй:» → родитель QUEUE_FROM_PC_DEC (кусок 2). Карточка приёма показывает 🎭.
    PC_DEC_LOCAL=1 (.env, финал развязки 12.07.2026): ОБЕ ветки pc-декомпозиции (829 и 328-pc)
    ставят родителя QUEUE_FROM_PCLOC_DEC + lane='pc' — цепь целиком ведёт локальный дирижёр ПК
    (см. _pc_dec_local); 0 (дефолт) → байт-в-байт старый путь QUEUE_FROM_PC_DEC без lane."""
    _MSG_KEY.set(str(msg_key or ""))     # ставим ВСЕГДА: чужой ключ из прежнего вызова не липнет
    t = _canon_theater_prefix(unicodedata.normalize("NFC", (text or "").strip()))
    low = t.lower()
    pc = (lane == "pc")
    for p in _DEC_PREFIXES:
        if low.startswith(p):
            task_text = t[len(p):].strip()
            if not task_text:
                return ("🤖 Пустое ТЗ. Формат: «декомпозируй: <крупное ТЗ>» — разобью на шаги "
                        "и выполню по одному.")
            if pc:
                if _pc_dec_local():
                    r = _enqueue_reliable(bridge, QUEUE_FROM_PCLOC_DEC, task_text, lane="pc")
                    if r.get("ok"):
                        return (f"🧩 ТЗ {r.get('id')} в очереди на декомпозицию (ЛОКАЛЬНЫЙ "
                                f"дирижёр ПК): план/шаги/надзор целиком на ПК (lane=pc). "
                                f"Каждый шаг отчитается сюда; красный спрошу кнопкой в инбоксе; "
                                f"в конце — сводка. ПК выключен → цепь честно упадёт по таймауту.")
                    return f"🤖 Не удалось поставить ТЗ на декомпозицию: {_bridge_err_detail(r)}"
                r = _enqueue_reliable(bridge, QUEUE_FROM_PC_DEC, task_text)
                if r.get("ok"):
                    return (f"🧩 ТЗ {r.get('id')} в очереди на декомпозицию (театр PC): план "
                            f"построит VPS-дирижёр (~60с), шаги уйдут ПК-агенту по одному "
                            f"(lane=pc). Каждый шаг отчитается сюда; красный спрошу кнопкой; "
                            f"в конце — сводка. ПК выключен → цепь честно упадёт по таймауту.")
                return f"🤖 Не удалось поставить ТЗ на декомпозицию: {_bridge_err_detail(r)}"
            theater, task_text, note = _route_328(task_text)
            if not task_text:
                return ("🤖 Пустое ТЗ. Формат: «декомпозируй: <крупное ТЗ>» — разобью на шаги "
                        "и выполню по одному.")
            if theater == "pc":
                if _pc_dec_local():
                    r = _enqueue_reliable(bridge, QUEUE_FROM_PCLOC_DEC, task_text, lane="pc")
                    if r.get("ok"):
                        return (f"🧩 ТЗ {r.get('id')} в очереди на декомпозицию (ЛОКАЛЬНЫЙ "
                                f"дирижёр ПК): план/шаги/надзор целиком на ПК (lane=pc); отчёты "
                                f"шагов и сводка цепи — в теме PC-дев, красный шаг спрошу "
                                f"кнопкой в инбоксе. ПК выключен → цепь честно упадёт по "
                                f"таймауту." + _router_card("pc", note))
                    return f"🤖 Не удалось поставить ТЗ на декомпозицию: {_bridge_err_detail(r)}"
                r = _enqueue_reliable(bridge, QUEUE_FROM_PC_DEC, task_text)
                if r.get("ok"):
                    return (f"🧩 ТЗ {r.get('id')} в очереди на декомпозицию (театр PC): план "
                            f"построит VPS-дирижёр (~60с), шаги уйдут ПК-агенту по одному "
                            f"(lane=pc); отчёты шагов и сводка цепи — в теме PC-дев (метка цепи "
                            f"pc), красный шаг спрошу кнопкой. ПК выключен → цепь честно упадёт "
                            f"по таймауту." + _router_card("pc", note))
                return f"🤖 Не удалось поставить ТЗ на декомпозицию: {_bridge_err_detail(r)}"
            r = _enqueue_reliable(bridge, QUEUE_FROM_DEC, task_text)
            if r.get("ok"):
                return (f"🧩 ТЗ {r.get('id')} в очереди на декомпозицию (демон возьмёт ~60с). "
                        f"Сначала верну план шагов, затем шаги пойдут отдельными задачами по одному "
                        f"(каждый отчитается сюда; красный шаг спрошу кнопкой), в конце — сводка."
                        + _router_card(theater, note))
            return f"🤖 Не удалось поставить ТЗ на декомпозицию: {_bridge_err_detail(r)}"
    for p in _DEV_PREFIXES:
        if low.startswith(p):
            task_text = t[len(p):].strip()
            if not task_text:
                return "🤖 Пустое ТЗ. Формат: «тз: <что сделать>» (дев-режим, до 45 мин)."
            if pc:
                r = _enqueue_reliable(bridge, QUEUE_FROM_PC_DEV, task_text, lane="pc")
                if r.get("ok"):
                    return (f"✅ ТЗ {r.get('id')} в очереди полосы PC (lane=pc) — возьмёт ПК-агент. "
                            f"Статусы/красные вопросы/итог принесу в эту тему.")
                return f"🤖 Не удалось поставить ТЗ в очередь: {_bridge_err_detail(r)}"
            theater, task_text, note = _route_328(task_text)
            if not task_text:
                return "🤖 Пустое ТЗ. Формат: «тз: <что сделать>» (дев-режим, до 45 мин)."
            if theater == "pc":
                r = _enqueue_reliable(bridge, QUEUE_FROM_DEV, task_text, lane="pc")
                if r.get("ok"):
                    return (f"✅ ТЗ {r.get('id')} в очереди (театр PC, lane=pc) — возьмёт ПК-агент. "
                            f"Статусы/красные вопросы/итог принесу сюда, в тему постановки."
                            + _router_card("pc", note))
                return f"🤖 Не удалось поставить ТЗ в очередь: {_bridge_err_detail(r)}"
            r = _enqueue_reliable(bridge, QUEUE_FROM_DEV, task_text)
            if r.get("ok"):
                return (f"✅ ТЗ {r.get('id')} в очереди (дев-режим, до 45 мин; демон возьмёт ~60с). "
                        f"Работает headless Claude Code: зелёное/оранжевое (вкл. restart splinter "
                        f"через гейт) сам, настоящее красное спрошу кнопкой. Результат принесу сюда."
                        + _router_card(theater, note))
            return f"🤖 Не удалось поставить ТЗ в очередь: {_bridge_err_detail(r)}"
    for p in _TASK_PREFIXES:
        if low.startswith(p):
            task_text = t[len(p):].strip()
            if not task_text:
                return "🤖 Пустая задача. Формат: «задача: <что сделать>»."
            if pc:
                r = _enqueue_reliable(bridge, QUEUE_FROM_PC, task_text, lane="pc")
                if r.get("ok"):
                    return (f"✅ Задача {r.get('id')} в очереди полосы PC (lane=pc) — возьмёт ПК-агент. "
                            f"Принесу результат в эту тему, когда будет done/failed.")
                return f"🤖 Не удалось поставить задачу в очередь: {_bridge_err_detail(r)}"
            theater, task_text, note = _route_328(task_text)
            if not task_text:
                return "🤖 Пустая задача. Формат: «задача: <что сделать>»."
            if theater == "pc":
                r = _enqueue_reliable(bridge, QUEUE_FROM, task_text, lane="pc")
                if r.get("ok"):
                    return (f"✅ Задача {r.get('id')} в очереди (театр PC, lane=pc) — возьмёт "
                            f"ПК-агент. Результат принесу сюда, в тему постановки."
                            + _router_card("pc", note))
                return f"🤖 Не удалось поставить задачу в очередь: {_bridge_err_detail(r)}"
            r = _enqueue_reliable(bridge, QUEUE_FROM, task_text)
            if r.get("ok"):
                return (f"✅ Задача {r.get('id')} поставлена в очередь — демон возьмёт её (опрос ~60с). "
                        f"Принесу результат сюда, когда будет done/failed."
                        + _router_card(theater, note))
            return f"🤖 Не удалось поставить задачу в очередь: {_bridge_err_detail(r)}"
    return None


# ===================== INLINE-КНОПКИ (вместо «да N») =====================
# Спека: KB_DEVBOT_BUTTONS_SPEC. Под needs_approval — ✅/❌ (одноразовые) + 🔄/📋 (многоразовые);
# под done — только 🔄/📋. callback_data: approve|reject|check|next : <id>. Зелёная зона (UI Splinter).
def _kb_approval(qid):
    """Кнопки под needs_approval: одноразовые ✅ Да, деплой / ❌ Нет + многоразовые 🔄 Проверь / 📋 Дальше."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Да, деплой", callback_data=f"approve:{qid}"),
         InlineKeyboardButton("❌ Нет", callback_data=f"reject:{qid}")],
        [InlineKeyboardButton("🔄 Проверь", callback_data=f"check:{qid}"),
         InlineKeyboardButton("📋 Дальше", callback_data=f"next:{qid}")],
    ])


def _kb_done(qid, full=False):
    """Кнопки под done: многоразовые 🔄 Проверь / 📋 Дальше (✅/❌ тут не нужны — задача уже завершена).
    full=True → отчёт не поместился в карточку (см. report_digest): сверху встаёт «📄 отчёт» —
    это и есть «ссылка» из правила «итог + ссылка», работающая с телефона, без путей и файлов."""
    rows = [[InlineKeyboardButton("🔄 Проверь", callback_data=f"check:{qid}"),
             InlineKeyboardButton("📋 Дальше", callback_data=f"next:{qid}")]]
    if full:
        rows.insert(0, [InlineKeyboardButton("📄 отчёт", callback_data=f"full:{qid}")])
    return InlineKeyboardMarkup(rows)


def _kb_full(qid):
    """Одна кнопка «📄 отчёт» — для failed-карточки с урезанным телом (кнопок у failed не было и
    не появляется, пока отчёт помещается целиком: без урезания карточка байт-в-байт прежняя)."""
    return InlineKeyboardMarkup([[InlineKeyboardButton("📄 отчёт", callback_data=f"full:{qid}")]])


# ── ЗАМОК ИНБОКСА: кнопка ВЕРДИКТА обязана уехать в 1160, что бы ни решил вызывающий ─────────
# Признак маршрута один — «ждёт ли сообщение ответа». У карточки devbot этот признак есть в виде
# ФАКТА, а не слова: клавиатура несёт кнопку, которая меняет судьбу задачи (approve:/reject:).
# Навигация (🔄 Проверь / 📋 Дальше) и ссылка на отчёт (📄) ответом НЕ являются — карточка done с
# «📄 отчёт» обязана остаться в теме постановки, иначе замок сам натаскает в инбокс информационное.
_VERDICT_CB = ("approve:", "reject:")


def _is_verdict_markup(markup):
    """Несёт ли клавиатура кнопку ВЕРДИКТА владельца? Судим по callback_data реального объекта,
    который сейчас отправляется, а не по тексту карточки: подпись можно переписать, callback —
    это то, что нажатие сделает. Нет клавиатуры / чужая форма → False (замок не вмешивается)."""
    try:
        for row in (getattr(markup, "inline_keyboard", None) or []):
            for btn in (row or []):
                if str(getattr(btn, "callback_data", "") or "").startswith(_VERDICT_CB):
                    return True
    except Exception:
        return False
    return False


def _inbox_lock_topic(topic, markup_last, qid=None):
    """→ тема доставки. Карточка с кнопкой вердикта идёт в инбокс ВСЕГДА, даже если вызывающий
    посчитал тему иначе (замок направления «спрашивающее — в инбоксе»). Инбокс выключен
    (INBOX_TOPIC_ID = 0/мусор) → тема вызывающего, как было: это штатный режим «инбокса нет»,
    и подменять его нечем. Информационная карточка не трогается вовсе."""
    if not _is_verdict_markup(markup_last):
        return topic
    inbox = inbox_topic()
    if not inbox or topic == inbox:
        return topic
    log.warning("devbot: ЗАМОК ИНБОКСА — карточка qid=%s с кнопкой вердикта шла в тему %s, "
                "увожу в инбокс %s (спрашивающее мимо инбокса не уходит)", qid, topic, inbox)
    return inbox


def _find_task(bridge, qid):
    """Найти задачу по id среди всех статусов очереди → (status, item) | (None, None). read-only
    (get_pending, lane='all' — кнопки 🔄/📋 работают и под карточками полосы pc)."""
    for st in ("needs_approval", "approved", "in_progress", "new", "done", "failed"):
        try:
            r = bridge.get_pending(st, lane="all")
        except Exception:
            continue
        if not r.get("ok"):
            continue
        for it in r.get("items", []):
            if str(it.get("id")) == str(qid):
                return st, it
    return None, None


def _next_approval(bridge, exclude_id):
    """Найти первый другой открытый needs_approval (кроме exclude_id). Sync → asyncio.to_thread."""
    try:
        r = bridge.get_pending("needs_approval", lane="all")
    except Exception:
        return None
    if not r.get("ok"):
        return None
    for it in (r.get("items") or []):
        if str(it.get("id")) != str(exclude_id):
            return it
    return None


async def _send_stale_followup(context, q, next_it):
    """Отправить свежую карточку следующего открытого needs_approval после стейл-ответа."""
    if next_it is None:
        return
    try:
        next_id = int(next_it.get("id"))
    except (TypeError, ValueError):
        return
    what = str(next_it.get("result") or "").strip()
    # ЗАМОК ИНБОКСА: тема бралась у НАЖАТОЙ карточки, а это СЛЕДУЮЩИЙ открытый вопрос со своими
    # ✅/❌ — карточка, ждущая ответа. Нажми владелец легаси-карточку в 328 (инбокс тогда был
    # выключен), и новый вопрос остался бы в 328 мимо инбокса.
    markup = _kb_approval(next_id)
    tid = _inbox_lock_topic(getattr(q.message, "message_thread_id", None) or DEVBOT_TOPIC,
                            markup, next_id)
    try:
        await context.bot.send_message(
            chat_id=HQ_CHAT_ID,
            message_thread_id=tid,
            text=what[:4000] if what else f"Задача {next_id} — ждёт подтверждения",
            reply_markup=markup,
        )
    except Exception as e:
        log.warning("devbot._send_stale_followup: send_message упал (%s)", e)


def _is_pc_item(it):
    """Задача полосы pc? По полю lane (новый Bridge) ИЛИ по метке from (работает и до redeploy)."""
    lane = str((it or {}).get("lane") or "").strip().lower()
    return lane == "pc" or str((it or {}).get("from") or "") in QUEUE_FROMS_PC


def _item_topic(it):
    """Тема для карточки задачи — по метке from = тема ПОСТАНОВКИ (кусок 3 «единый пульт»,
    07.07.2026): from полосы pc (Filipp-pc*) → тема PC-дев; иначе → 328. Задача, поставленная
    в 328 и роутнутая на театр pc (from=Filipp-328*, lane=pc), отчитывается в 328 — где её
    ставили. По lane тему НЕ решаем (lane = полоса ИСПОЛНЕНИЯ, не тема владельца); ярлык [pc]
    в карточке остаётся по lane (_item_lane_label)."""
    if str((it or {}).get("from") or "") in QUEUE_FROMS_PC:
        return pc_dev_topic() or DEVBOT_TOPIC
    return DEVBOT_TOPIC


def _item_lane_label(it):
    """Ярлык полосы для строки инбокса: pc → 'pc', иначе 'vps'."""
    return "pc" if _is_pc_item(it) else "vps"


# === Отпечаток конверта для дедупа В СПИСКЕ /inbox (ст3, часть г) ===
# ЗЕРКАЛО orchestrator_daemon.parse_op / _OP_PREFIX_RE (см. AUTO_OPS там). Импортировать демон в
# процесс бота нельзя: его модуль на import ставит signal.signal — в рабочем потоке to_thread это
# ValueError, а в main-потоке перебил бы обработчики PTB. Логика отпечатка крошечная — повторяем.
# КОРНЕВОЙ дедуп конвертов в очереди тут НЕ решаем (отдельный заход §7) — только схлопывание строк.
_INBOX_AUTO_OPS = ("git_push", "restart_splinter")
_INBOX_OP_RE = re.compile(r"op\s*=\s*([a-z_]+)", re.IGNORECASE)
_INBOX_OP_PREFIX_RE = re.compile(r"^\s*op\s*=\s*[a-z_]+\s*\|\s*", re.IGNORECASE)


def _inbox_fingerprint(what):
    """Отпечаток карточки needs_approval = (op-код, очищенный от 'op=… |' текст). НЕ по id —
    одинаковые конверты (один и тот же op + один и тот же текст) схлопываются в списке в одну строку."""
    w = str(what or "")
    m = _INBOX_OP_RE.search(w)
    op = m.group(1).lower() if m else "other"
    if op not in _INBOX_AUTO_OPS:
        op = "other"
    card = _INBOX_OP_PREFIX_RE.sub("", w).strip()
    return op, card


def build_inbox(bridge):
    """ЕДИНЫЙ ИНБОКС (ст3, часть в+г): текст-список ВСЕХ открытых needs_approval по ОБЕИМ полосам
    (get_pending needs_approval lane='all' — чистый read-only GET, без записи). Дедуп в списке по
    отпечатку конверта (_inbox_fingerprint, НЕ id): одинаковые карточки — одной строкой ×N со списком
    id и возрастом старейшей. Пусто/ошибка → человеческая строка. Зона 🟢 (read-only)."""
    try:
        r = bridge.get_pending("needs_approval", lane="all")
    except Exception as e:
        return f"📥 Инбокс: ошибка чтения очереди ({type(e).__name__}: {e})."
    if not r.get("ok"):
        return f"📥 Инбокс: очередь недоступна ({r.get('error')})."
    items = [it for it in (r.get("items") or []) if isinstance(it, dict)]
    if not items:
        return "📥 Инбокс пуст — открытых подтверждений нет 👍"
    # группировка по отпечатку конверта
    groups = {}   # fp -> {"op", "card", "lanes":set, "ids":[], "ages":[]}
    for it in items:
        what = str(it.get("result") or "")
        op, card = _inbox_fingerprint(what)
        g = groups.setdefault((op, card), {"op": op, "card": card, "lanes": set(), "ids": [], "ages": []})
        g["lanes"].add(_item_lane_label(it))
        try:
            g["ids"].append(int(it.get("id")))
        except (TypeError, ValueError):
            g["ids"].append(it.get("id"))
        age = _task_age_sec(it.get("updated"))
        if age is not None:
            g["ages"].append(age)
    total = len(items)
    out = [f"📥 Инбокс подтверждений: открыто {total} (по обеим полосам vps+pc):"]
    # старейшая группа сверху (по максимальному возрасту в группе; без возраста → в конец)
    ordered = sorted(groups.values(),
                     key=lambda g: (-(max(g["ages"]) if g["ages"] else -1), min(str(i) for i in g["ids"])))
    for g in ordered:
        ids = g["ids"]
        n = len(ids)
        lanes = "/".join(sorted(g["lanes"]))
        op = g["op"]
        card1 = (g["card"] or "(карточка пустая — см. исходную задачу)").splitlines()[0][:200]
        oldest = max(g["ages"]) if g["ages"] else None
        if n == 1:
            age_txt = f", висит {int(oldest // 60)} мин" if oldest is not None else ""
            out.append(f"  • id {ids[0]} [{lanes}] op={op}{age_txt}")
        else:
            id_list = ", ".join(str(i) for i in sorted(ids, key=lambda x: str(x)))
            age_txt = f", старейшая {int(oldest // 60)} мин" if oldest is not None else ""
            out.append(f"  • ×{n} [{lanes}] op={op} (id: {id_list}{age_txt})")
        out.append(f"      {card1}")
    out.append("\nОтвет: тапни ✅/❌ под карточкой в теме, либо «да N» / «нет N».")
    return "\n".join(out)


async def _strip_and_mark(q, mark):
    """Одноразовые ✅/❌: убрать кнопки и дописать пометку к тексту сообщения.
    editMessageText заодно снимает reply_markup; если упало — хотя бы снять кнопки."""
    base = (q.message.text or "") if q.message else ""
    new_text = f"{base}\n\n{mark}" if base else mark
    try:
        await q.edit_message_text(text=new_text)
    except Exception as e:
        log.warning("devbot._strip_and_mark: edit_message_text упал (%s)", e)
        try:
            await q.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass


async def _send_thread(context, q, text):
    """Отдельным сообщением в ту же тему (для многоразовых 🔄/📋 — исходные кнопки остаются)."""
    tid = getattr(q.message, "message_thread_id", None) or DEVBOT_TOPIC
    for chunk in _chunks(text):
        try:
            await context.bot.send_message(chat_id=HQ_CHAT_ID, message_thread_id=tid, text=chunk)
        except Exception as e:
            log.warning("devbot._send_thread: отправка не прошла (%s)", e)


async def _btn_answer(q, txt=None, **kw):
    """q.answer() с защитой — паттерн _o3_answer (хвост ревизии §7): колбэк, отлежавшийся
    в очереди за долгим Bridge-вызовом (approve/check ходят в Apps Script по несколько секунд),
    протухает — BadRequest «Query is too old». Ack тогда невозможен, но ДЕЙСТВИЕ кнопки
    обязано выполниться; упавший q.answer не валит хендлер."""
    try:
        await q.answer(txt, **kw)
    except Exception as e:
        log.warning("devbot: q.answer протух/упал (действие кнопки всё равно выполняю): %s", e)


async def _cb_approve(context, q, qid, bridge):
    """approve:<id> → approve_task (та же логика «да N»). ОДНОРАЗОВО + идемпотентность."""
    # Стейл-гейт: проверить статус ДО действия (конверт мог быть обработан параллельно)
    cur_status, _ = await asyncio.to_thread(_find_task, bridge, qid)
    if cur_status != "needs_approval":
        st_txt = f" (статус: {cur_status})" if cur_status else " (задача не найдена)"
        next_it = await asyncio.to_thread(_next_approval, bridge, qid)
        mark = f"⏱ карточка устарела{st_txt}"
        if next_it is not None:
            mark += f" — актуальный конверт №{next_it.get('id')} ниже"
        await _btn_answer(q, "карточка устарела")
        await _strip_and_mark(q, mark)
        await _send_stale_followup(context, q, next_it)
        return
    r = await asyncio.to_thread(bridge.approve_task, qid, "Filipp")
    if r.get("ok"):
        _forget_seen(_reported, qid)      # пусть дальнейший done/failed отрапортуется штатно
        await _btn_answer(q, "✅ одобрено")
        await _strip_and_mark(q, "✅ одобрено")
    elif r.get("error") == "not_awaiting":
        # уже approved/done/failed → идемпотентно: сообщить + убрать кнопки (гонка/повторный тап)
        await _btn_answer(q, "уже обработано")
        await _strip_and_mark(q, f"✅ уже обработано (статус {r.get('status')})")
    elif r.get("error") == "not_found":
        await _btn_answer(q, "задачи нет в очереди")
        await _strip_and_mark(q, "🤖 задачи нет в очереди")
    else:
        await _btn_answer(q, f"approve не прошёл: {r.get('error')}")


async def _cb_reject(context, q, qid, bridge):
    """reject:<id> → complete_task failed (как «нет N»). ОДНОРАЗОВО."""
    # Стейл-гейт: проверить статус ДО действия
    cur_status, _ = await asyncio.to_thread(_find_task, bridge, qid)
    if cur_status != "needs_approval":
        st_txt = f" (статус: {cur_status})" if cur_status else " (задача не найдена)"
        next_it = await asyncio.to_thread(_next_approval, bridge, qid)
        mark = f"⏱ карточка устарела{st_txt}"
        if next_it is not None:
            mark += f" — актуальный конверт №{next_it.get('id')} ниже"
        await _btn_answer(q, "карточка устарела")
        await _strip_and_mark(q, mark)
        await _send_stale_followup(context, q, next_it)
        return
    r = await asyncio.to_thread(bridge.complete_task, qid, "failed", "отклонено Филиппом (кнопка)")
    if r.get("ok"):
        _mark_seen_by_id(_reported, qid)  # уже сообщили «отклонена» — не дублируем failed-рапортом
        await _btn_answer(q, "❌ отклонено")
        await _strip_and_mark(q, "❌ отклонено")
    elif r.get("error") == "not_found":
        await _btn_answer(q, "задачи нет в очереди")
        await _strip_and_mark(q, "🤖 задачи нет в очереди")
    else:
        await _btn_answer(q, f"reject не прошёл: {r.get('error')}")


async def _cb_check(context, q, qid, bridge):
    """check:<id> → свежий статус задачи. МНОГОРАЗОВО (кнопка остаётся → новое сообщение)."""
    await _btn_answer(q, "проверяю…")
    status, item = await asyncio.to_thread(_find_task, bridge, qid)
    if status is None:
        txt = f"🔄 Задача {qid}: не найдена в очереди."
    else:
        res = (item.get("result") or "").strip()
        upd = item.get("updated") or ""
        txt = f"🔄 Задача {qid}: статус {status}" + (f"\nupdated: {upd}" if upd else "")
        if res:
            txt += f"\n\n{res[:1500]}"
    await _send_thread(context, q, txt)


async def _cb_full(context, q, qid, bridge):
    """full:<id> → ПОЛНЫЙ отчёт задачи в тему. МНОГОРАЗОВО (кнопка остаётся → новое сообщение).
    Источник — та же запись очереди, из которой собиралась карточка: полный текст никуда не
    копируется ради кнопки и не может разойтись с тем, что записал исполнитель."""
    await _btn_answer(q, "📄")
    status, item = await asyncio.to_thread(_find_task, bridge, qid)
    if status is None:
        txt = (f"📄 Задача {qid}: в очереди не найдена (подрезана?) — полный отчёт остался "
               f"файлом-артефактом, путь назван в карточке.")
    else:
        res = str(item.get("result") or "").strip() or "(пустой результат)"
        txt = f"📄 Задача {qid} — полный отчёт ({len(res)} симв.):\n\n{res}"
    await _send_thread(context, q, txt)


async def _cb_next(context, q, qid, bridge):
    """next:<id> → подсказка по следующему шагу. МНОГОРАЗОВО (кнопка остаётся → новое сообщение)."""
    await _btn_answer(q, "📋")
    status, _item = await asyncio.to_thread(_find_task, bridge, qid)
    if status is None:
        txt = f"📋 Задача {qid}: не найдена — поставь новую командой «задача: <что сделать>»."
    elif status == "done":
        txt = (f"📋 Задача {qid} — done. Следующий шаг: новой командой «задача: <что дальше>» "
               f"или 🔄 Проверь для свежего статуса.")
    elif status == "needs_approval":
        txt = f"📋 Задача {qid} ждёт твоего решения (красная зона). Тапни ✅ Да, деплой / ❌ Нет."
    elif status in ("approved", "in_progress", "new"):
        txt = f"📋 Задача {qid}: статус {status} — в работе. Жди завершения или 🔄 Проверь."
    else:
        txt = f"📋 Задача {qid}: статус {status}."
    await _send_thread(context, q, txt)


async def handle_callback(update, context, bridge) -> None:
    """Inline-кнопки дев-бота (вместо «да N»). ТОЛЬКО Филипп (504608015); чужой → answer «не для тебя».
    answerCallbackQuery на каждый тап. approve/reject — одноразовые; check/next — многоразовые."""
    q = update.callback_query
    if not q:
        return
    uid = q.from_user.id if q.from_user else None
    if uid != DEVBOT_USER:
        await _btn_answer(q, "не для тебя", show_alert=False)
        return
    try:
        action, sid = (q.data or "").split(":", 1)
        qid = int(sid)
    except Exception:
        await _btn_answer(q)
        return
    # origin=human (как «да N»): тап Филиппа = ручное действие, токен-замок 4.2 не вмешивается.
    try:
        if action == "approve":
            await _cb_approve(context, q, qid, bridge)
        elif action == "reject":
            await _cb_reject(context, q, qid, bridge)
        elif action == "check":
            await _cb_check(context, q, qid, bridge)
        elif action == "next":
            await _cb_next(context, q, qid, bridge)
        elif action == "full":
            await _cb_full(context, q, qid, bridge)
        else:
            await _btn_answer(q)
    except Exception as e:
        log.exception("devbot.handle_callback error (%s:%s)", action, qid)
        await _btn_answer(q, f"ошибка: {type(e).__name__}")


def _task_age_sec(updated_iso):
    """Возраст последнего updated задачи в секундах (по ISO из очереди). None при ошибке разбора
    → зависание НЕ объявляем (лучше не пугать ложняком, чем поднять тревогу из-за парсинга)."""
    try:
        s = str(updated_iso).replace("Z", "+00:00")
        t = datetime.datetime.fromisoformat(s)
        if t.tzinfo is None:
            t = t.replace(tzinfo=datetime.timezone.utc)
        return (datetime.datetime.now(datetime.timezone.utc) - t).total_seconds()
    except Exception:
        return None


def _env_sec(name, default):
    """Секунды из env с дефолтом; мусор/пусто → дефолт (порог тревоги не должен падать на парсинге)."""
    try:
        return int(str(os.getenv(name, "") or "").strip() or default)
    except (TypeError, ValueError):
        return default


def _stall_threshold_sec(it):
    """Порог «зависла» для КОНКРЕТНОЙ задачи = её штатный потолок исполнения + люфт STALL_GRACE_SEC.
    «Долго работает» ≠ «умерла» (урок 287, класс ПК-вотчдога 5167365): пока in_progress моложе
    своего потолка — тишина; тревога только ПОСЛЕ потолка и без терминала (цикл идёт лишь по
    in_progress — терминальная задача сюда не попадает, done/failed рапортуются штатно, «отбой»
    не шлём). Потолки зеркалят исполнителей — env-имена/дефолты те же, что в .env демона:
    полоса pc → PC_STEP_TIMEOUT (надзор ПК-театра, 3600); vps from=*-dev/*-dec/Filipp-curator →
    TASK_TIMEOUT_DEV (orchestrator_daemon._task_timeout, 2700); прочее vps → TASK_TIMEOUT (600).
    Возраст меряем по updated (heartbeat демона его освежает) — строже потолка от старта задачи,
    ложняка до потолка не даёт."""
    if _is_pc_item(it):
        cap = _env_sec("PC_STEP_TIMEOUT", 3600)
    else:
        frm = str((it or {}).get("from") or "")
        if frm == QUEUE_FROM_CURATOR or frm.endswith(("-dev", "-dec")):
            cap = _env_sec("TASK_TIMEOUT_DEV", 2700)
        else:
            cap = _env_sec("TASK_TIMEOUT", 600)
    return cap + STALL_GRACE_SEC


async def _check_curator_pending(context, by) -> None:
    """Дописывает вердикт куратора В УЖЕ ОТПРАВЛЕННУЮ done/failed-карточку (edit, не новое
    сообщение) — либо снимает надпись «куратор оценивает» по таймауту (_CURATOR_WAIT_MAX).
    Вызывается из report_results с текущим by-снимком, ДО разбора терминальных задач: пометка
    _curator_glued должна успеть встать раньше, чем цикл дойдёт до самой карточки-маркера
    (её id всегда БОЛЬШЕ id задачи, а цикл идёт по возрастанию)."""
    if not _curator_pending:
        return
    now = time.monotonic()
    to_remove = []
    for qid, info in list(_curator_pending.items()):
        chat_id, topic_id, msg_id, base_text, task_text, task_from, st, sent_at = info[:8]
        # 9-й элемент (был ли отчёт урезан) появился 05.08.2026 — читаем мягко: старая 8-элементная
        # запись пережившего рестарт тика и фикстуры прежних тестов должны работать как раньше.
        full = bool(info[8]) if len(info) > 8 else False
        kind, key = _curator_key(qid, task_text, task_from)
        card = _curator_card_item(kind, key, by)
        timed_out = (now - sent_at) > _CURATOR_WAIT_MAX
        if card is None and not timed_out:
            continue  # ещё ждём следующего тика
        to_remove.append(qid)
        line = None
        if card is not None:
            line = _curator_line(_result_body(card, empty=""))
            if line is None:
                # Сбойный вердикт (НЕ поставлено / карточка владельцу не встала) — в строку не
                # ужать. Плашка остаётся прежней, а карточка куратора уйдёт отдельным сообщением
                # со ВСЕМ текстом, как раньше.
                fid = _curator_followup_id(key, by)
                new_banner = (f"⏳ Куратор поставил продолжение (задача {fid})" if fid is not None
                              else _build_banner(qid, task_text, task_from, by))
            else:
                new_banner = _build_banner(qid, task_text, task_from, by)
        else:
            # Таймаут: вердикта не будет (closed или сбой думателя) — плашка по состоянию очереди,
            # БЕЗ повторного входа в ветку ожидания (иначе текст не менялся бы вовсе).
            new_banner = _build_banner(qid, task_text, task_from, by, curator_wait=False)
        new_text = base_text + (("\n" + line) if line else "") + "\n" + new_banner
        # Кнопки восстанавливаем ТЕ ЖЕ, что были на карточке: у урезанного отчёта это «📄 отчёт»
        # (и у failed тоже — там она единственная). Правка не имеет права обеднить сообщение,
        # ради полноты которого она и делается.
        markup = _kb_done(qid, full=full) if st == "done" else (_kb_full(qid) if full else None)
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id, message_id=msg_id,
                text=new_text, reply_markup=markup,
            )
            if line:
                _mark_glued((kind, key))          # доехало → второго сообщения не будет
        except Exception as e:
            log.warning("devbot.banner: edit_message_text задача %s упал (%s)", qid, e)
    for qid in to_remove:
        _curator_pending.pop(qid, None)


# ── ФИКС B: доставка TG-карточки с ретраями (тихая потеря 20.07.2026) ────────────────
_TG_SEND_RETRIES = 3          # попыток отправки карточки при Telegram-исключении
_TG_SEND_BACKOFF = 0.5        # база backoff (сек); задержка = _TG_SEND_BACKOFF * 2**(попытка-1)


async def _send_card_with_retry(context, qid, chunks, topic, markup_last, label):
    """Отправить ВСЕ чанки карточки с ретраями (backoff, до _TG_SEND_RETRIES попыток).
    Возвращает True ТОЛЬКО когда доставлены ВСЕ чанки. Уже доставленные чанки
    при ретрае НЕ пересылаются (курсор sent_idx) → нет дублей. Пометку «отправлено»
    ставит ВЫЗЫВАЮЩИЙ строго после True; False → карточка уйдёт на следующий тик.

    ЗАМОК ИНБОКСА стоит ЗДЕСЬ, в узком месте доставки, а не у вызывающего: тему вызывающий
    считает сам, и следующий путь карточки-вопроса легко забудет про инбокс. Клавиатура вердикта
    — факт об отправляемом сообщении, поэтому адрес чинится в последний момент."""
    topic = _inbox_lock_topic(topic, markup_last, qid)
    n = len(chunks)
    sent_idx = 0
    for attempt in range(1, _TG_SEND_RETRIES + 1):
        try:
            while sent_idx < n:
                kw = {"chat_id": HQ_CHAT_ID, "message_thread_id": topic, "text": chunks[sent_idx]}
                if markup_last is not None and sent_idx == n - 1:
                    kw["reply_markup"] = markup_last
                await context.bot.send_message(**kw)
                sent_idx += 1          # инкремент ТОЛЬКО после успешной отправки чанка
            return True
        except Exception as e:
            log.warning("devbot.report_results: %s qid=%s попытка %d/%d упала на чанке %d/%d (%s)",
                        label, qid, attempt, _TG_SEND_RETRIES, sent_idx + 1, n, e)
            if attempt < _TG_SEND_RETRIES:
                await asyncio.sleep(_TG_SEND_BACKOFF * (2 ** (attempt - 1)))
    log.warning("devbot.report_results: %s qid=%s НЕ доставлена за %d попыток — "
                "НЕ помечаю отправленной, повтор на следующем тике", label, qid, _TG_SEND_RETRIES)
    return False


async def _send_inprogress_card(context, it):
    """Карточка «🔄 в работе» — ОДИН формат для обоих источников события: журнала взятий демона
    (доезжает даже у 5-секундной задачи) и снимка in_progress (длинные задачи, полоса pc).
    Дедуп ставит вызывающий: сюда попадают только непоказанные задачи."""
    qid = it.get("id")
    task_text = str(it.get("task_text") or "")[:120]
    rep = " (повтор)" if _is_repeat_item(it) else ""   # клон возврата ≠ новая задача (инцидент 156)
    msg = f"🔄 Задача {qid}{rep} в работе…\n\n{task_text}"
    for chunk in _chunks(msg):
        try:
            m = await context.bot.send_message(chat_id=HQ_CHAT_ID,
                                               message_thread_id=_item_topic(it), text=chunk)
            log.info("devbot.report_results: анонс «в работе» задачи %s отправлен в тему %s, "
                     "message_id=%s", qid, _item_topic(it), getattr(m, "message_id", "?"))
        except Exception as e:
            log.warning("devbot.report_results: анонс in_progress %s не ушёл (%s)", qid, e)


# ── ОТЧЁТ В 328 = ИТОГ + ССЫЛКА (разделение каналов, часть 2, 05.08.2026) ────────────────
# Замер до правки (снимок очереди, 298 терминальных задач 28.07–05.08): средняя длина result
# 2096 симв., медиана 2050, 72 % длиннее 600 — тема 328 читалась как простыня, последовательность
# задач одним взглядом не видна. Решение владельца: тело длиннее порога уходит в артефакт, в чат
# едет номер + строка сути + ссылка. Решение о ФОРМЕ карточки — чистая функция report_digest
# (юнит на дословных телах), здесь только руки: файл и кнопка.
_DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _reports_dir():
    """Каталог артефактов отчётов. REPORTS_DIR — ручка для тестов (боевые файлы не трогаем)."""
    return os.getenv("REPORTS_DIR") or os.path.join(ROOT, "reports")


def _write_report_artifact(it, st, body):
    """Полное тело отчёта → файл `reports/<дата>/task-<id>.md`. → путь для карточки | None.

    FAIL-SAFE: любой сбой записи (диск, права, кривая дата) = None → карточка уходит БЕЗ строки
    пути, но с кнопкой «📄 отчёт» и полным телом в очереди. Отчёт не может пропасть из-за файла."""
    try:
        qid = it.get("id")
        day = str(it.get("updated") or "")[:10]
        if not _DAY_RE.match(day):
            day = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        d = os.path.join(_reports_dir(), day)
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, f"task-{qid}.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(report_digest.artifact_text(qid, st, it.get("task_text"), body))
        return os.path.relpath(path, ROOT) if path.startswith(ROOT + os.sep) else path
    except Exception as e:
        log.warning("devbot.report_results: артефакт отчёта %s не записан (%s)", it.get("id"), e)
        return None


# ── СИГНАЛ «ОЧЕРЕДЬ ПУСТА» (разделение каналов, часть 3, 05.08.2026) ──────────────────────
# Одно короткое сообщение в 328 на ПЕРЕХОД в пустоту — не повтор каждые 45 секунд. Пустота = ни
# одной задачи ОБЕИХ полос в очереди / в работе / в ожидании ответа / одобренной. Считается из
# ТОГО ЖЕ снимка, что и плашка карточки (_build_banner), чтобы две правды не разошлись.
_OPEN_STATUSES = ("new", "in_progress", "needs_approval", "approved")
_queue_busy = None          # None = ещё не наблюдали: первый снимок сигнала НЕ рождает
_closed_since_busy = []     # id, закрытые с момента, когда очередь последний раз была непустой


def _queue_open_count(by):
    """Сколько задач наших меток ещё живо в снимке. by=None сюда не доходит: без данных очереди
    о пустоте не заявляем НИКОГДА (тот же fail-safe, что у плашки «состояние недоступно»)."""
    n = 0
    for st in _OPEN_STATUSES:
        for it in by.get(st, []) or []:
            if str(it.get("from") or "") not in QUEUE_FROMS:
                continue
            # Карточка ревизора, целиком уехавшая сводкой в ленту, владельца НЕ ждёт: вопроса
            # ей никто не задавал. Иначе «ждёт тебя 0» не наступило бы никогда — сводная
            # карточка на ПК живёт, пока владелец её не закроет (06.08.2026).
            if st == "needs_approval" and _revizor_silenced.get(str(it.get("id"))) == _gen(it):
                continue
            n += 1
    return n


async def _announce_idle(context, by):
    """Переход «работа была → всё закрыто» → РОВНО одно сообщение в 328. Пока очередь пуста и
    ничего нового не приходило, сообщение не повторяется; новая задача взводит сигнал заново."""
    global _queue_busy, _closed_since_busy
    if _queue_open_count(by):
        _queue_busy = True
        return
    if _queue_busy:                     # было занято, стало пусто — это и есть переход
        ids = sorted(set(_closed_since_busy))
        tail = ("\nЗакрыто: " + ", ".join(str(i) for i in ids)) if ids else ""
        msg = f"🟢 Очередь пуста — в работе 0, ждёт тебя 0, в очереди 0 (обе полосы).{tail}"
        for chunk in _chunks(msg):
            try:
                await context.bot.send_message(chat_id=HQ_CHAT_ID,
                                               message_thread_id=DEVBOT_TOPIC, text=chunk)
                log.info("devbot.report_results: сигнал «очередь пуста» отправлен, закрыто %s",
                         ids or "—")
            except Exception as e:
                log.warning("devbot.report_results: сигнал «очередь пуста» не ушёл (%s)", e)
    _queue_busy = False
    _closed_since_busy = []


# ── НАХОДКА ПО ЗАМОРОЖЕННОМУ КОНТУРУ НЕ РОЖДАЕТ КАРТОЧКУ (06.08.2026) ─────────────────────
# ЖИВОЙ ФАКТ: сводная карточка ревизора 244 копилась 30.3 ч, приехала владельцу списком из 24
# находок и была отклонена кнопкой — подтверждать было нечего: 16 из 24 несут метку
# производителя «[клиентский контур …]», а клиентский контур ЗАМОРОЖЕН решением владельца.
# Решение («что уходит заметкой, что остаётся вопросом») — чистая функция revizor_route; здесь
# только РУКИ: состояние дедупа, суточное окно, артефакт и отправка в ленту.
#
# ПОЧЕМУ СУТОЧНАЯ СВОДКА, А НЕ ЗАМЕТКА НА КАЖДУЮ НАХОДКУ — по замеру, а не по вкусу: 16
# замороженных находок за 30.3 ч = 12.7 в сутки, а лента 829 сегодня несёт 1.9 заметки в сутки
# (замер владельца 05.08, «три источника шума — одна цель»). Заметка на находку подняла бы ленту
# в 7-8 раз и перевалила бы названный владельцем потолок ~10/сут — то есть перенесла бы простыню
# из инбокса в ленту. Поэтому окно СКОЛЬЗЯЩЕЕ, 24 ч: первая находка после тишины уезжает сразу
# (ждать нечего), дальше — не чаще одной сводки в сутки, потолок 1/сут по построению.
_REVIZOR_STATE_LIVE = "/tmp/cc_revizor_frozen.json"   # состояние маршрута (переживает рестарт)
_REVIZOR_NOTE_EVERY = 24 * 3600       # скользящее окно сводки, сек
_REVIZOR_SEEN_CAP = 500               # ~38 суток при измеренных 13 находках/сут
_revizor_silenced = {}                # {номер: генерация} — карточки, целиком уехавшие в ленту


def _revizor_state_path():
    """Путь состояния. Под тест-прогоном боевой файл НЕ трогаем (урок 04.08: тест гейта стёр
    боевой спул ревизора и убил 12 находок владельца) — тест обязан подсунуть свой путь."""
    p = os.getenv("REVIZOR_STATE_FILE") or _REVIZOR_STATE_LIVE
    if p == _REVIZOR_STATE_LIVE and task_metrics.under_test(
            (sys.argv[0] if sys.argv else ""), os.environ, sys.modules):
        return p + ".test"
    return p


def _revizor_load():
    """Состояние маршрута: что уже уехало заметкой, что ждёт сводки, когда была последняя.
    Файла нет/битый → чистое состояние (сводка уйдёт заново — дубль дешевле потери)."""
    st = {}
    try:
        with open(_revizor_state_path(), encoding="utf-8") as f:
            st = json.load(f)
    except Exception:
        st = {}
    if not isinstance(st, dict):
        st = {}
    st.setdefault("seen", [])
    st.setdefault("pending", [])
    st.setdefault("last_note", "")
    return st


def _revizor_save(st):
    try:
        with open(_revizor_state_path(), "w", encoding="utf-8") as f:
            json.dump(st, f, ensure_ascii=False)
        return True
    except Exception as e:
        log.warning("devbot.revizor: состояние маршрута не сохранено (%s)", e)
        return False


def _revizor_frozen():
    """Множество ЗАМОРОЖЕННЫХ контуров. Ручка `CONTOUR_FREEZE` (.env), дефолт `client` =
    сегодняшний факт по решению владельца. `CONTOUR_FREEZE=0` + рестарт → правило мертво,
    карточки идут байт-в-байт как раньше."""
    return revizor_route.frozen_keys(os.getenv("CONTOUR_FREEZE", "client"))


def _revizor_absorb(st, found):
    """Новые находки (которых нет ни в отправленных, ни в ждущих) → в очередь на сводку.
    → список ждущих [(строка, ключ), …] (он же кладётся в состояние)."""
    pend = [(str(x[0]), str(x[1])) for x in (st.get("pending") or [])
            if isinstance(x, (list, tuple)) and len(x) == 2]
    have = set(str(f) for f in (st.get("seen") or []))
    have |= {revizor_route.fingerprint(l) for l, _k in pend}
    for line, key in found:
        fp = revizor_route.fingerprint(line)
        if fp in have:
            continue
        have.add(fp)
        pend.append((line, key))
    st["pending"] = [list(x) for x in pend]
    return pend


def _revizor_due(st, now):
    """Пора ли отдавать сводку: первой — сразу, дальше не чаще раза в сутки."""
    last = _iso_ts(st.get("last_note"))
    return last is None or (now.timestamp() - last) >= _REVIZOR_NOTE_EVERY


def _revizor_window(st, now):
    """Подпись окна сводки. Первая сводка — честно «первая», без выдуманного начала."""
    last = _iso_ts(st.get("last_note"))
    end = now.strftime("%d.%m %H:%M UTC")
    if last is None:
        return f"окно: по {end} (первая сводка)"
    start = datetime.datetime.fromtimestamp(last, datetime.timezone.utc).strftime("%d.%m %H:%M")
    return f"окно: с {start} по {end}"


def _write_revizor_artifact(findings, label, now):
    """Полный список находок → файл (в ленту едет итог, тело — в артефакт). → путь | None.
    FAIL-SAFE: любой сбой записи = None → заметка уходит без пути, находки в ней названы."""
    try:
        d = os.path.join(_reports_dir(), "revizor")
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, now.strftime("%Y-%m-%d-%H%M") + ".md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(revizor_route.artifact_text(findings, label))
        return os.path.relpath(path, ROOT) if path.startswith(ROOT + os.sep) else path
    except Exception as e:
        log.warning("devbot.revizor: артефакт находок не записан (%s)", e)
        return None


async def _route_revizor_frozen(context, it):
    """Находки замороженного контура из сводной карточки ревизора → заметка в ленту 829.

    → разбор revizor_route.route (вызывающий берёт из него текст карточки) либо None.
    None = ВЕСТИ СЕБЯ КАК РАНЬШЕ (карточка целиком, с кнопками): так отвечает и выключенная
    ручка, и карточка без замороженных находок, и ЛЮБОЙ сбой — включая недоставленную заметку.
    Последнее намеренно: гасить вопрос владельцу, не сумев сказать ему иначе, — это молчание,
    а не маршрут."""
    frozen = _revizor_frozen()
    if not frozen:
        return None
    try:
        r = revizor_route.route(_result_body(it, empty=""), frozen)
        if not r["changed"]:
            return None                  # замороженных находок нет — прежний путь до символа
        st = _revizor_load()
        pend = _revizor_absorb(st, r["frozen"])
        now = datetime.datetime.now(datetime.timezone.utc)
        if not pend or not _revizor_due(st, now):
            _revizor_save(st)            # уже уехали ранее / ждут ближайшей суточной сводки
            return r
        label = _revizor_window(st, now)
        art = _write_revizor_artifact(pend, label, now)
        text = revizor_route.note(pend, window_label=label, artifact=art or "")
        ok = await asyncio.to_thread(notify.send_feed, text)
        if not ok:
            _revizor_save(st)            # находки остаются ждущими — повтор на следующем тике
            log.warning("devbot.revizor: сводка о %d находках замороженного контура НЕ ушла в "
                        "ленту — карточка %s идёт владельцу как раньше", len(pend), it.get("id"))
            return None
        st["seen"] = (list(st.get("seen") or []) +
                      [revizor_route.fingerprint(l) for l, _k in pend])[-_REVIZOR_SEEN_CAP:]
        st["pending"] = []
        st["last_note"] = now.isoformat()
        _revizor_save(st)
        log.info("devbot.revizor: %d находок замороженного контура ушли сводкой в ленту "
                 "(карточка %s, артефакт %s)", len(pend), it.get("id"), art or "—")
        return r
    except Exception as e:
        log.warning("devbot.revizor: маршрут находок упал (%s) — карточка идёт как раньше", e)
        return None


async def report_results(context) -> None:
    """Фоновый job (раз в ~45с): приносит в 328 результат задач from=Filipp-328, ставших done/failed.
    Дедуп: _reported (память процесса). Seed-on-start: первый прогон лишь помечает уже-завершённые
    как отрапортованные, чтобы при рестарте не присылать всю историю заново.
    Фикс 02.07: весь опрос очереди — ОДИН прогон в отдельном потоке (to_thread, timeout 15с) —
    event loop не встаёт, бот отвечает на кнопки/сообщения, даже когда Bridge тупит."""
    global _report_seeded
    pb = _get_poll_bridge()
    if pb is None:
        return
    try:
        by = await asyncio.to_thread(_poll_queue_sync, pb)
    except Exception as e:
        log.warning("devbot.report_results: опрос очереди упал (%s)", e)
        return
    if by is None:
        return          # таймаут/ошибка опроса — не страшно, следующий тик через 45с

    finished = [(st, it) for st in ("done", "failed") for it in by[st]]
    finished.sort(key=lambda x: int(x[1].get("id") or 0))   # старые задачи рапортуем первыми

    if not _report_seeded:
        # Seed-on-start гасит ТОЛЬКО историю — задачи, ставшие терминальными ДО старта процесса.
        # Всё, что финишировало ПОСЛЕ старта, проходит ПРИ ЛЮБОМ номере: раньше seed сгребал
        # весь снимок и вместе с историей глушил свежие задачи пересозданной очереди (28.07.2026).
        kept, hushed = [], 0
        for _st, it in finished:
            if _seed_silences(it):
                _mark_seen(_reported, it)
                hushed += 1
            else:
                kept.append(str(it.get("id")))
        _report_seeded = True
        # Журнал взятий перематываем в конец: взятия ДО старта процесса — история. Длинная
        # задача, пережившая рестарт бота, всё равно получит анонс из снимка in_progress ниже.
        _claims_seek_end()
        log.info("devbot.report_results: seed-on-start — погашено %d терминальных из %d; "
                 "рапортуем свежие: %s", hushed, len(finished), kept or "нет")
        return

    # ХВОСТ 1: события «взял в работу» из журнала демона — ПЕРЕД карточками результата, чтобы
    # порядок в теме был хронологическим (взял → завершил) даже у задачи, прожившей 5 секунд.
    for ev in _drain_claim_events():
        if _seen(_inprogress_seen, ev):
            continue                     # снимок in_progress уже отрапортовал эту задачу
        _mark_seen(_inprogress_seen, ev)
        # Карточка-маркер куратора живёт секунду, исполнителя у неё нет, а её вердикт вклеен в
        # карточку задачи — анонс «🔄 в работе» о ней был чистым шумом (22 таких сообщения в 328
        # за 28.07–05.08). Пометку _inprogress_seen оставляем: она гасит и второй путь анонса.
        if _CURATOR_BANNER_RE.match(str(ev.get("task_text") or "")):
            continue
        await _send_inprogress_card(context, ev)

    # Редактировать карточки, ожидающие вердикт куратора (если появился)
    await _check_curator_pending(context, by)

    for st, it in finished:
        qid = it.get("id")
        if _seen(_reported, it):
            continue
        _mark_seen(_reported, it)
        emoji = "✅" if st == "done" else "❌"
        body = _result_body(it)      # + пометка, если исполнитель упёрся в потолок result
        rep = " (повтор)" if _is_repeat_item(it) else ""   # клон возврата ≠ новая задача (инцидент 156)
        task_text = str(it.get("task_text") or "")
        task_from = str(it.get("from") or "")
        # ОДНО СООБЩЕНИЕ НА ЗАДАЧУ: вердикт этого терминала уже уехал СТРОКОЙ в карточке задачи →
        # своя карточка ему не нужна. Пометка ставится только по факту доставки, поэтому «молча
        # съесть» вердикт нечем: не вклеился — идёт сюда и рапортуется целиком, как раньше.
        mcur = _CURATOR_BANNER_RE.match(task_text)
        if mcur and _is_glued((mcur.group(1), int(mcur.group(2)))):
            log.info("devbot.report_results: карточка куратора %s не шлётся — вердикт вклеен в "
                     "карточку %s %s", qid, mcur.group(1), mcur.group(2))
            continue
        # 229 (FACT-верификация, недеструктивно, 20.07.2026): пометка ТОЛЬКО текста карточки 328,
        # сохранённый result в Bridge не трогаем (инвариант «финал байт-в-байт»). См. helper ниже.
        unv = _unverified_card_prefix(st, it)
        banner = _build_banner(qid, task_text, task_from, by)
        # Вердикт куратора успел встать ДО первого рапорта (частый случай: думатель отвечает за
        # ~10с, тик — 45с) → он едет СТРОКОЙ в этой же карточке, и карточка-маркер (её id заведомо
        # больше, а цикл идёт по возрастанию) ниже по циклу промолчит.
        cur_key = cur_line = None
        if not mcur and _curator_on() and task_from in _CURATOR_ELIGIBLE_FROMS:
            k = _curator_key(qid, task_text, task_from)
            card = _curator_card_item(k[0], k[1], by)
            if card is not None:
                cur_line = _curator_line(_result_body(card, empty=""))
                cur_key = k if cur_line else None
        tail = (cur_line + "\n" + banner) if cur_line else banner
        # Тело длиннее порога → в чат едет итог + ссылка, полный текст в артефакт и под кнопку.
        # Короткий отчёт (digest вернул None) идёт БАЙТ-В-БАЙТ прежним путём.
        short = report_digest.digest(body)
        if short is None:
            head = f"{emoji} Задача {qid}{rep} — {st}\n\n{unv}{body}\n{tail}"
        else:
            art = _write_report_artifact(it, st, body)
            link = f"📄 отчёт целиком ({len(body)} симв.) — кнопка «📄 отчёт» ниже"
            if art:
                link += f" · {art}"
            head = f"{emoji} Задача {qid}{rep} — {st}\n\n{unv}{short}\n\n{link}\n{tail}"
        chunks = _chunks(head)
        last_msg_obj = None
        for i, chunk in enumerate(chunks):
            kw = {"chat_id": HQ_CHAT_ID, "message_thread_id": _item_topic(it), "text": chunk}
            if i == len(chunks) - 1:                    # кнопки — на последнем чанке
                if st == "done":                        # 🔄/📋 как были (+📄, если отчёт урезан)
                    kw["reply_markup"] = _kb_done(qid, full=short is not None)
                elif short is not None:                 # failed: кнопка только ради урезанного тела
                    kw["reply_markup"] = _kb_full(qid)
            try:
                m = await context.bot.send_message(**kw)
                if i == len(chunks) - 1:
                    last_msg_obj = m
                # След доставки в splinter.log: «карточка была» доказывается логом, а не памятью
                # процесса (дыра 28.07: карточек не было, а следа их отсутствия — тоже).
                log.info("devbot.report_results: карточка задачи %s (%s, чанк %d/%d) отправлена "
                         "в тему %s, message_id=%s", qid, st, i + 1, len(chunks),
                         _item_topic(it), getattr(m, "message_id", "?"))
            except Exception as e:
                log.warning("devbot.report_results: отправка результата задачи %s упала (%s)", qid, e)
        if cur_key and last_msg_obj is not None:
            _mark_glued(cur_key)         # вердикт доехал внутри карточки → второго сообщения нет
        # Трекинг ожидания куратора: если показали «оценивает» — редактируем потом
        if banner == _CURATOR_THINKING and last_msg_obj is not None:
            last_chunk = chunks[-1]
            base_text = last_chunk.rsplit("\n", 1)[0] if "\n" in last_chunk else last_chunk
            _curator_pending[qid] = (
                HQ_CHAT_ID, _item_topic(it), last_msg_obj.message_id,
                base_text, task_text, task_from, st, time.monotonic(), short is not None,
            )
        _closed_since_busy.append(qid)   # номера для сигнала «очередь пуста» (часть 3)

    # needs_approval (заход 2б-2): задача упёрлась в красную зону — спрашиваем «да N»/«нет N».
    # БЕЗ seed (незакрытый вопрос после рестарта стоит переспросить); дедуп = _asked в памяти процесса.
    # ЕДИНЫЙ ИНБОКС (ст3, часть б): если INBOX_TOPIC_ID задан — approve-карточки ОБЕИХ полос сходятся
    # в тему-инбокс; не задан → прежнее поведение (_item_topic: vps→328, pc→829), без регресса.
    # Кнопки approve/reject/check/next те же — callback тем-агностичен (по id, не по теме).
    # done/failed/heartbeat выше ОСТАЮТСЯ по полосам _item_topic (в инбокс НЕ сводятся).
    inbox = inbox_topic()
    pend = sorted(by["needs_approval"], key=lambda x: int(x.get("id") or 0))
    for it in pend:
        qid = it.get("id")
        # Находки ревизора по ЗАМОРОЖЕННОМУ контуру уходят сводкой в ленту, а не кнопкой в
        # инбокс (06.08.2026). Маршрут считается ДО дедупа `_asked` намеренно: сводная карточка
        # ревизора живёт сутками и ДОПОЛНЯЕТСЯ — находки, приехавшие после первого показа, иначе
        # не увидел бы никто. Карточка при этом показывается по-прежнему один раз.
        route = None
        if str(it.get("from") or "") == QUEUE_FROM_REVIZOR:
            route = await _route_revizor_frozen(context, it)
        if route is not None and route["card"] is None:
            _revizor_silenced[str(qid)] = _gen(it)   # вопроса не осталось — и владельца не ждёт
            continue
        _revizor_silenced.pop(str(qid), None)
        if _seen(_asked, it):
            continue
        _approval_topic = inbox or _item_topic(it)
        # тот же потолок: конверт тоже режется. У карточки ревизора с замороженными находками
        # тело уже отфильтровано маршрутом (и несёт строку о том, сколько уехало в ленту).
        what = (route["card"] if route is not None
                else _result_body(it, empty="(не уточнено)"))
        lane = _item_lane_label(it)
        q = (f"⚠️ Задача {qid} [{lane}] требует подтверждения красной зоны:\n\n{what}\n\n"
             f"Подтвердить? Тапни кнопку ниже — или ответь «да {qid}» / «нет {qid}».")
        chunks = _chunks(q)
        # ФИКС B (тихая потеря TG-карточек, 20.07.2026): пометку «отправлено» (_asked) ставим
        # СТРОГО ПОСЛЕ успешной доставки. Раньше пометка ставилась ДО send_message → при
        # Telegram-исключении карточка молча терялась (qid уже «задан» → след. тик её пропускал).
        ok = await _send_card_with_retry(context, qid, chunks, _approval_topic,
                                         _kb_approval(qid), "вопрос-конверт")
        if ok:
            _mark_seen(_asked, it)   # успех → помечаем; провал → НЕ помечаем, уйдёт на следующий тик

    # in_progress (heartbeat/детект-зависания, части 1-2): «🔄 в работе» один раз + «⚠️ зависла» один раз.
    # Анти-спам: дедуп _inprogress_seen / _stalled — НЕ шлём на каждом 45с-проходе.
    running = sorted(by["in_progress"], key=lambda x: int(x.get("id") or 0))
    for it in running:
        qid = it.get("id")
        if not _seen(_inprogress_seen, it):    # анонс «в работе» — один раз на задачу
            _mark_seen(_inprogress_seen, it)
            await _send_inprogress_card(context, it)
        if not _seen(_stalled, it):            # детект зависания — один раз на задачу (анти-спам)
            age = _task_age_sec(it.get("updated"))
            thr = _stall_threshold_sec(it)     # per-задача: потолок исполнения + люфт (урок 287)
            if age is not None and age > thr:
                _mark_seen(_stalled, it)
                mins = int(age // 60)
                if _is_pc_item(it):
                    hint = "ПК-агент полосы pc не отвечает — проверь агента на ПК."
                else:
                    hint = "демон оркестратора не отвечает.\nПроверь: systemctl status orchestrator-daemon"
                w = (f"⚠️ Задача {qid} зависла — нет heartbeat ~{mins} мин "
                     f"при потолке {thr // 60} мин ({hint})")
                for chunk in _chunks(w):
                    try:
                        await context.bot.send_message(chat_id=HQ_CHAT_ID, message_thread_id=_item_topic(it), text=chunk)
                    except Exception as e:
                        log.warning("devbot.report_results: warn о зависании %s не ушло (%s)", qid, e)

    # Часть 3: обе полосы пусты → РОВНО одно сообщение в 328 на переход в пустоту.
    await _announce_idle(context, by)


# ===================== ЗЕЛЁНЫЕ ЗАДАЧИ (read-only) =====================
def _g_health():
    try:
        r = subprocess.run([PY, os.path.join(ROOT, "health.py")], cwd=ROOT,
                           capture_output=True, text=True, timeout=120)
        return r.stdout.strip() or "health: нет вывода"
    except Exception as e:
        return f"health не запустился: {e}"


def _g_audit(bridge):
    r = bridge.audit_list()
    if not r.get("ok"):
        return f"аудит недоступен: {r.get('error')}"
    items = r.get("items") or []
    opn = [it for it in items if str(it.get("status", "")).lower() in ("new", "open", "", "pending")]
    by = Counter(str(it.get("verdict", "?")) for it in opn)
    out = [f"🔎 Аудит: всего {len(items)}, открытых {len(opn)}"]
    for v, c in by.most_common():
        out.append(f"  {v}: {c}")
    return "\n".join(out)


def _g_writelog(bridge, n=15):
    r = bridge.read_write_log(limit=n)
    if not r.get("ok"):
        return f"боевой_лог недоступен: {r.get('error')}"
    items = r.get("items") or []
    out = [f"⬛ Боевой лог (посл. {len(items)} из {r.get('total')}):"]
    for it in items:
        crit = f" [{it.get('critical')}]" if it.get("critical") else ""
        out.append(f"  {it.get('logged_at')} | {it.get('initiator')} | {it.get('action')} | {it.get('result')}{crit}")
    return "\n".join(out)


def _g_cclog(bridge, n=12):
    r = bridge._call("read_doc", id=CC_LOG_ID)
    if not r.get("ok"):
        return f"cc_log недоступен: {r.get('error')}"
    lines = (r.get("text") or "").splitlines()
    return "📋 cc_log (свежие):\n" + "\n".join(lines[:n])


def _g_errors():
    try:
        with open(os.path.join(ROOT, "splinter.log"), encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except Exception as e:
        return f"splinter.log недоступен: {e}"
    err = sum(1 for l in lines if "[ERROR]" in l)
    warn = sum(1 for l in lines if "[WARNING]" in l)
    tail = [l.rstrip()[:120] for l in lines if "[ERROR]" in l][-5:]
    return (f"🪵 splinter.log: ERROR {err}, WARNING {warn} (строк {len(lines)})\n" +
            "\n".join("  " + t for t in tail))


def _g_brain(bridge):
    out = ["🧠 Brain (латентность чтения):"]
    for name in ("cc_log", "review", "project_state", "knowledge_base"):
        t0 = time.time()
        r = bridge._call("read_doc", name=name)
        dt = time.time() - t0
        out.append(f"  {name}: {dt:.1f}с {'ok' if r.get('ok') else '✗'} ({len(r.get('text') or '')})")
    return "\n".join(out)


def _g_overdue(bridge):
    """Просрочки ТО парка — переиспользуем прод-скан O3 (splinter._o3_overdue_scan, read-only).
    Топ-10 худших строками; «не делалось» помечаем, остальное «+N км».

    НУЛЬ ЗДЕСЬ БОЛЬШЕ НЕ ОТДАЁТСЯ БЕЗ ЗНАМЕНАТЕЛЯ (контракт читателя, 08.08.2026). Прежняя строка
    «🔧 Просрочек ТО нет 👍» печаталась ОДИНАКОВО и на здоровом парке, и на упавшем мосту —
    владелец не мог отличить «проверили 38 байков, всё чисто» от «не проверили ни одного»."""
    import splinter                     # локальный импорт — не плодить связность на уровне модуля
    scan = splinter._o3_overdue_scan(bridge)
    if not scan.ok:
        return ("🔧 Просрочки ТО: ПРОВЕРИТЬ НЕ УДАЛОСЬ — " + scan.say()
                + "\n   нуль просрочек здесь означал бы «не искали», а не «всё чисто».")
    payload = scan.payload or {}
    ov = payload.get("overdue") or []
    unmeas = payload.get("unmeasured") or []
    unchk = payload.get("unchecked") or []
    imp = payload.get("impossible") or []
    c = payload.get("counts") or {}

    # ТРИ ЧИСЛА РАЗДЕЛЬНО (10.08.2026): «не измерено» — это НЕ просрочка и НЕ здоровье. Свернуть
    # его в любое из двух соседних значило бы вернуть ровно тот дефект, ради которого мост учили
    # различать пустую клетку и ноль (12 фантомных просрочек из 35, перепись 08.08).
    out = [f"🔧 ТО парка: {splinter._o3_counts_line(payload)} ({scan.say()})"]
    if not ov:
        out.append("  ✅ просрочек по ЗНАЧЕНИЮ нет — «не измерено» сюда не входит намеренно")
    for o in ov[:10]:
        parts = []
        for it in o["items"]:
            lbl = splinter._MAND_LABEL.get(it["kind"], (str(it["kind"]), str(it["kind"])))[1]
            mark = " ⁉️" if it.get("impossible") else ""
            parts.append(f"{lbl} +{it['over_km']}км{mark}")
        out.append(f"  ⚠️ {splinter._o3_bike_label(o['bike'], o['plate'])} · " + ", ".join(parts))
    if len(ov) > 10:
        out.append(f"  …ещё {len(ov) - 10} просроченных (полный board — /o3board)")

    if unmeas:
        by = c.get("by_kind") or {}
        reg = ", ".join(f"{splinter._MAND_LABEL.get(k, (k, k))[1]} {v.get('unmeasured', 0)}"
                        for k, v in by.items() if v.get("unmeasured"))
        out.append(f"  🔎 НЕ ИЗМЕРЕНО (клетка пуста либо не число) по регистрам: {reg}")
        due = [o for o in unmeas if any(it.get("due_by_mileage") for it in o["items"])]
        if due:
            out.append(f"     из них пробег уже дорос до интервала — у {len(due)} байков: "
                       + ", ".join(o["plate"] for o in due[:10])
                       + (f" …ещё {len(due) - 10}" if len(due) > 10 else ""))
    if unchk:
        out.append(f"  ❔ НЕ УДАЛОСЬ ПРОВЕРИТЬ {c.get('unchecked_items', 0)} клеток у "
                   f"{len(unchk)} байков: {unchk[0]['items'][0]['why']}")
    if imp:
        # НЕ ИСПРАВЛЯЕМ — только называем. Правка Лист1 — решение владельца (🔴 живая таблица).
        out.append(f"  ⁉️ ЗНАЧЕНИЯ, КОТОРЫХ НЕ БЫВАЕТ ({len(imp)}) — не исправлял, только называю:")
        for x in imp[:10]:
            lbl = splinter._MAND_LABEL.get(x["kind"], (x["kind"], x["kind"]))[1]
            out.append(f"     {x['plate']} · {lbl} = {x['value']} — {x['why']}")
        if len(imp) > 10:
            out.append(f"     …ещё {len(imp) - 10}")
    return "\n".join(out)


# === Дайджест кураторских целей (шаг 5/7 родитель 231) ===
# Маркеры куратора продублированы из orchestrator_daemon (демон в процесс бота не импортируем —
# его модуль на import ставит signal.signal; образец REPEAT_MARK): followup-задача несёт
# [куратор цели G, шаг m] (ищем search'ем — маркер жив и под префиксом перерождения самопочинки),
# сводная карточка владельцу начинается с [куратор владельцу цель G]. Дайджест read-only (один
# опрос очереди, записи нет) и живёт ТОЛЬКО в зелёной команде «статус» по запросу — в утреннюю
# авто-сводку НЕ входит (по расписанию не спамим).
_CURATOR_GOAL_RE = re.compile(r"\[куратор цели (\d+), шаг (\d+)\]")
# Хвост «, операция <ключ>» — операционная карточка (класс 251/254/257, 05.08.2026): пункт с
# несколькими операциями разведён по карточкам, по одной на операцию. Для дайджеста они такие же
# «ждёт владельца», как общая карточка, — иначе цель с разведёнными операциями выглядела бы
# закрытой, пока карточки висят в инбоксе.
_CURATOR_HUMAN_RE = re.compile(r"^\[куратор владельцу цель (\d+)(?:, операция [^\]]+)?\]")
_CURATOR_BANNER_RE = re.compile(r"^\[куратор (задача|родитель) (\d+)\]")  # карточка-маркер вердикта
_SUMMARY_PARENT_RE = re.compile(r"^\[сводка родитель (\d+)\]")            # text цепной сводки
_CURATOR_DIGEST_STATUSES = ("new", "in_progress", "approved", "needs_approval", "done", "failed")
_CURATOR_ACTIVE_STATUSES = ("new", "in_progress", "approved")
_UNSET = object()                           # сентинел «items не передали» (звать опрос самому)


def _queue_snapshot(pb):
    """ОДИН read-only опрос очереди по всем статусам ОБЕИХ полос (lane='all') → [items] | None
    (сбой/исключение — вызывающий даёт честную пометку, пульс не валим). Общий снимок для
    сводки системы И дайджеста куратора — очередь на «статус» опрашивается ровно один раз."""
    try:
        fn = getattr(pb, "get_pending_multi", None)
        if fn is not None:
            r = fn(_CURATOR_DIGEST_STATUSES, lane="all")
        else:                               # мок в тестах без multi — по-статусно
            items = []
            for st in _CURATOR_DIGEST_STATUSES:
                rr = pb.get_pending(st, lane="all")
                if not rr.get("ok"):
                    return None
                for it in rr.get("items", []):
                    if isinstance(it, dict):
                        it.setdefault("status", st)
                    items.append(it)
            r = {"ok": True, "items": items}
    except Exception:
        return None
    if not r.get("ok"):
        return None
    return [it for it in r.get("items", []) if isinstance(it, dict)]


def _curator_goals(pb, items=_UNSET):
    """Срез кураторских целей из очереди (полоса vps — куратор живёт только там) →
    {G: {active, wait, done, failed, steps, owner}} | None (очередь не опросилась).
    wait = followup-задача цели упёрлась в красное (needs_approval — ждёт «да» владельца);
    owner = открытая сводная карточка «нужно от владельца» по цели.
    items — готовый снимок _queue_snapshot (не передали → опросим сами; снимок теперь
    несёт ОБЕ полосы, pc-элементы отсеиваются здесь — семантика «только vps» цела)."""
    if items is _UNSET:
        items = _queue_snapshot(pb)
    if items is None:
        return None
    goals = {}

    def _g(gid):
        return goals.setdefault(int(gid), {"active": 0, "wait": 0, "done": 0,
                                           "failed": 0, "steps": 0, "owner": False})
    for it in items:
        if str(it.get("lane") or "") == "pc":   # куратор живёт только на vps
            continue
        txt = str(it.get("task_text") or "")
        st = str(it.get("status") or "")
        m = _CURATOR_HUMAN_RE.match(txt)
        if m:
            if st == "needs_approval":      # закрытая (done) карточка владельцу цель не держит
                _g(m.group(1))["owner"] = True
            continue
        m = _CURATOR_GOAL_RE.search(txt)
        if not m:
            continue
        g = _g(m.group(1))
        g["steps"] = max(g["steps"], int(m.group(2)))
        if st in _CURATOR_ACTIVE_STATUSES:
            g["active"] += 1
        elif st == "needs_approval":
            g["wait"] += 1
        elif st == "failed":
            g["failed"] += 1
        else:
            g["done"] += 1
    return goals


def _curator_digest(pb, items=_UNSET):
    """Дайджест кураторских целей для «статус»: закрыто / в работе / ждёт владельца.
    Кураторских маркеров в очереди нет → None (строка в статус не добавляется);
    очередь не опросилась → короткая честная пометка (пульс не валим)."""
    goals = _curator_goals(pb, items)
    if goals is None:
        return "🧭 кураторские цели: очередь не опросилась — дайджест недоступен"
    return _curator_digest_render(goals)


def _curator_digest_render(goals):
    """Рендер дайджеста из готового среза целей ({} → None, строка не добавляется)."""
    if not goals:
        return None
    counts = {"закрыто": 0, "в работе": 0, "ждёт владельца": 0}
    rows = []
    for gid in sorted(goals):
        g = goals[gid]
        total = g["active"] + g["wait"] + g["done"] + g["failed"]
        if g["owner"] or g["wait"]:
            state, why = "ждёт владельца", ("карточка в инбоксе" if g["owner"]
                                            else f"красный вопрос по {g['wait']} задаче(ам)")
            line = f"  цель {gid}: 🧑 ждёт владельца — {why}"
        elif g["active"]:
            state = "в работе"
            line = f"  цель {gid}: 🔄 в работе — продолжений {total}, активных {g['active']}"
        else:
            state = "закрыто"
            line = (f"  цель {gid}: ✅ закрыто — продолжений {total}" +
                    (f", провалено {g['failed']}" if g["failed"] else ""))
        counts[state] += 1
        rows.append(line)
    head = ("🧭 кураторские цели (" + str(len(goals)) + "): " +
            " · ".join(f"{k} {v}" for k, v in counts.items() if v))
    return "\n".join([head] + rows)


# === Плашка продолжения в done/failed-карточках (задача N) ===
# Дописывается последней строкой каждой done/failed-карточки devbot.
# Данные — из ТОГО ЖЕ by-снимка, что report_results (без лишних Bridge-вызовов).
# Куратор: только для from Filipp-328, -dev, -curator, -dec (vps-цепь);
#   pc-dec и pcloc-dec НЕ входят (_pc_post_summary куратора не вызывает).
_CURATOR_ELIGIBLE_FROMS = frozenset([
    "Filipp-328", "Filipp-328-dev", "Filipp-curator", "Filipp-328-dec",
])


def _curator_on():
    """Флаг CURATOR=1 в .env. Зеркало orchestrator_daemon._curator_on()."""
    return str(os.getenv("CURATOR", "0")).strip() == "1"


def _mark_glued(key):
    """Пометить вердикт как доехавший внутри карточки задачи + подрезать протухшие пометки."""
    now = time.monotonic()
    for k, t in list(_curator_glued.items()):
        if now - t > _CURATOR_GLUED_TTL:
            _curator_glued.pop(k, None)
    _curator_glued[key] = now


def _is_glued(key):
    """Вердикт этого терминала уже доехал внутри карточки задачи (и пометка не протухла)?"""
    t = _curator_glued.get(key)
    return t is not None and (time.monotonic() - t) <= _CURATOR_GLUED_TTL


def _curator_key(qid, task_text, task_from):
    """(вид, id) кураторского терминала для карточки задачи qid:
    одиночка → («задача», qid); цепная сводка (dec) → («родитель», PID из «[сводка родитель N]»).
    Мусорный qid → («задача», 0): совпасть с реальной карточкой такой ключ не может."""
    frm = str(task_from or "")
    if frm in (QUEUE_FROM_DEC, QUEUE_FROM_PC_DEC, QUEUE_FROM_PCLOC_DEC):
        m = _SUMMARY_PARENT_RE.match(str(task_text or ""))
        if m:
            return "родитель", int(m.group(1))
    try:
        return "задача", int(str(qid or 0))
    except (TypeError, ValueError):
        return "задача", 0


def _curator_card_item(kind, key, by):
    """Кураторская карточка-маркер этого терминала из снимка → item | None.
    Ищем в by["done"] (карточка — немедленный done synthetic-задачи «[куратор <вид> <id>]»)."""
    for it in (by or {}).get("done", []) or []:
        m = _CURATOR_BANNER_RE.match(str(it.get("task_text") or ""))
        if m and m.group(1) == kind and int(m.group(2)) == key:
            return it
    return None


def _curator_verdict_exists(qid, task_text, task_from, by):
    """Куратор уже вынес вердикт по задаче qid? (тонкая обёртка над поиском карточки-маркера)."""
    kind, key = _curator_key(qid, task_text, task_from)
    return _curator_card_item(kind, key, by) is not None


# ── ВЕРДИКТ КУРАТОРА = СТРОКА В КАРТОЧКЕ ЗАДАЧИ (05.08.2026) ─────────────────────────────
# Было: итог задачи одним сообщением, вердикт куратора — вторым (synthetic-задача «[куратор …]»
# рапортовалась как обычная). Замер по журналам за 28.07–05.08: 613 сообщений devbot в 328, из них
# 88 (14 %) — кураторские карточки и анонсы «в работе» по ним. Решение владельца: отчёт о
# выполнении — ОДНО сообщение; вердикт вклеивается строкой, продолжение цели называется НОМЕРОМ в
# той же строке; цель закрыта без замечаний → куратор молчит (так и было: verdict=closed карточки
# не рождает вовсе).
# ПАРСИМ ТЕЛО, А НЕ ПЕРЕСКАЗЫВАЕМ ОЧЕРЕДЬ: строка обязана говорить то же, что сказал куратор.
# Формат тела задаёт orchestrator_daemon._curator_card_text — регресс кормит нас ЕГО ЖЕ выводом
# (живой формат, а не идеализированный мок), поэтому расхождение формулировок увидит тест.
_CUR_PLACED_RE = re.compile(r"^\s*\d+\.\s*задача id (\d+)\s*:", re.M)     # «1. задача id 331: …»
_CUR_INBOX_RE = re.compile(r"\(задач[аи]\s+([0-9]+(?:\s*,\s*[0-9]+)*)\s*,\s*инбокс\)")
# Сбои: в строку не влезут — такая карточка идёт целиком. «⚠️» демон ставит РОВНО в одном месте —
# перед заметкой «операции БЕЗ карточки (дожать „тз:“ руками)» при разводе пункта по операциям;
# без этой строки развод выглядел бы полностью удавшимся.
_CUR_KEEP_WHOLE = ("НЕ поставлено", "НЕ встала", "⚠️")


def _curator_line(body):
    """Тело кураторской карточки → ОДНА строка вердикта для карточки задачи | None.

    None = «вклеить нечем» → карточка куратора уходит отдельным сообщением, как раньше. Это
    ГЛАВНЫЙ fail-safe правила: сокращение шума не смеет съесть ни одного слова куратора. В None
    уходят ровно сбойные случаи — «НЕ поставлено» (ТЗ не встало: бюджет/дедуп/enqueue) и «сводная
    карточка НЕ встала»: там текста больше, чем строка вместит, и он владельцу нужен целиком."""
    s = str(body or "")
    if not s.strip():
        return None
    if any(mark in s for mark in _CUR_KEEP_WHOLE):
        return None
    head = s.strip().splitlines()[0]
    if "требует владельца" in head:
        m = _CUR_INBOX_RE.search(s)
        if not m:
            return None
        ids = [x.strip() for x in m.group(1).split(",") if x.strip()]
        word = "карточка" if len(ids) == 1 else "карточки"
        return f"🧭 Куратор: нужен владелец — {word} {', '.join(ids)} в инбоксе"
    if "НЕ закрыта" in head:
        ids = _CUR_PLACED_RE.findall(s)
        if not ids:
            return None
        word = "задача" if len(ids) == 1 else "задачи"
        return f"🧭 Куратор: цель не закрыта — продолжение: {word} {', '.join(ids)}"
    return None


def _curator_followup_id(goal_key, by):
    """Id первой followup-задачи куратора для цели goal_key (int), или None.
    Followup-задачи: from=Filipp-curator, text содержит [куратор цели G, шаг m]."""
    for st in ("new", "in_progress", "approved"):
        for it in by.get(st, []):
            if str(it.get("from") or "") != QUEUE_FROM_CURATOR:
                continue
            m = _CURATOR_GOAL_RE.search(str(it.get("task_text") or ""))
            if m and int(m.group(1)) == goal_key:
                return it.get("id")
    return None


def _build_banner(qid, task_text, task_from, by, curator_wait=True):
    """Плашка продолжения для done/failed-карточки задачи qid.
    Fail-safe: by=None → «недоступно» (НИКОГДА не говорим «завершено» без данных очереди).
    Порядок приоритетов: недоступно > куратор думает > конверты > активные задачи > завершено.

    curator_wait=False — ветку «куратор думает» не входить. Нужна ровно на ФОЛБЭКЕ по таймауту
    (_check_curator_pending): там ждать больше нечего, а прежний код звал эту же функцию, снова
    попадал в ту же ветку и получал ТОТ ЖЕ текст — edit падал «Message is not modified» (405 раз
    в живом журнале), и карточка навсегда оставалась с надписью «вердикт через ~10с», хотя вердикта
    уже не будет. Молчание куратора = verdict closed («цель закрыта, замечаний нет») ЛИБО сбой
    думателя; различить их нечем, поэтому плашка не заявляет ни того, ни другого — показывает
    состояние очереди, которое истинно в обоих случаях."""
    if by is None:
        return "⏳ состояние очереди недоступно — набери \"статус\""

    frm = str(task_from or "")

    # Куратор ещё думает?
    if curator_wait and _curator_on() and frm in _CURATOR_ELIGIBLE_FROMS:
        if not _curator_verdict_exists(qid, task_text, frm, by):
            return _CURATOR_THINKING

    # Считаем активные задачи обеих полос из QUEUE_FROMS
    active_vps, active_pc = [], []
    for st in ("new", "in_progress", "approved"):
        for it in by.get(st, []):
            if str(it.get("from") or "") not in QUEUE_FROMS:
                continue
            (active_pc if _is_pc_item(it) else active_vps).append(it)

    n_approval = sum(1 for it in by.get("needs_approval", [])
                     if str(it.get("from") or "") in QUEUE_FROMS)
    if n_approval > 0:
        return f"✋ Ждёт тебя: {n_approval} конвертов"

    total = len(active_vps) + len(active_pc)
    if total > 0:
        parts = (([f"vps {len(active_vps)}"] if active_vps else []) +
                 ([f"pc {len(active_pc)}"] if active_pc else []))
        ids = (" (" + ", ".join(str(i.get("id")) for i in active_vps + active_pc) + ")"
               if total <= 3 else "")
        return f"⏳ Работа продолжается: {total} (🎭 {' · '.join(parts)}){ids}"

    # Проверить кураторские цели через готовый снимок (без Bridge-вызовов)
    flat = [it for lst in by.values() for it in lst]
    goals = _curator_goals(None, flat) or {}
    if any(g["active"] or g["wait"] or g["owner"] for g in goals.values()):
        return "⏳ Работа продолжается: 0 задач (🧭 куратор активен)"

    return "✅ ВСЁ ЗАВЕРШЕНО — очередь пуста, кураторских целей нет. Это была последняя задача"


# === Сводка системы для «статус» (задача 285, 13.07.2026): одна правда «всё ли завершено» ===
# Read-only, из ТОГО ЖЕ снимка очереди, что дайджест куратора (один опрос на «статус»):
# ⚙️ в работе — активные цепи декомпозера (ТОЛЬКО по живым признакам, зеркало ПК-фикса
# 1403fa2), new/in_progress/approved одиночки обеих полос, кураторские цели в работе;
# 🧑 ждёт тебя — все needs_approval (красные вопросы + сводные карточки владельцу);
# 👁 надзор — последний тик ревизора из cowork_log. Всё пусто → «🟢 ТИХО: в работе 0,
# ждёт тебя 0» = сигнал «всё завершено».
_DEC_FROMS = (QUEUE_FROM_DEC, QUEUE_FROM_PC_DEC, QUEUE_FROM_PCLOC_DEC)
_STEP_MARK_RE = re.compile(r"^\[шаг (\d+)/(\d+) родитель (\d+)\]")   # зеркало демона _STEP_RE
_OWNER_CARD_RE = re.compile(r"^\[(?:куратор|ревизор) владельцу")     # сводные карточки владельцу
_ST_ICON = {"new": "⏳", "in_progress": "🔄", "approved": "▶️"}
_SECTION_TOP = 5                            # телефонный формат: топ-строк на секцию, дальше «…ещё K»
_OPEN_STEP_STATUSES = ("new", "in_progress", "needs_approval", "approved")  # незакрытый шаг = живая цепь
_LIVE_PARENT_STATUSES = ("new", "in_progress")   # живой родитель (план строится / шаги идут)

# Контракт тика ревизора (зеркало ПК-фикса 1403fa2, «честный тик»): тик = NOTE-строка
# cowork_log (журнал ПК-контура, Bridge read_doc) с «ревизор:» сразу после автора NOTE —
# живой формат «NOTE Orchestrator: ревизор: 2 окон с активностью…» (разведка cowork_log
# 13.07.2026). Маркеры очереди «[ревизор дата=…]» — дедуп/бюджет маршрутизации находок,
# НЕ тики (живой призрак 23:10 13.07: они давали «ревизор (время неизвестно)»). Время
# показываем ТОЛЬКО если оно есть в NOTE; NOTE нет → «ревизор: тиков ещё не было».
_REV_NOTE_RE = re.compile(r"^NOTE(?:\s+[^:]{0,40})?:\s*ревизор:\s*(.+)", re.I)
_REV_TIME_RE = re.compile(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}")
_REV_HHMM_RE = re.compile(r"\b\d{1,2}:\d{2}\b")
_REV_WIN_RE = re.compile(r"окон\D{0,3}(\d+)")
_REV_WIN_RE2 = re.compile(r"(\d+)\s*окон")
_REV_FIND_RE = re.compile(r"наход\w*\D{0,3}(\d+)")


def _int0(v):
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def _short(txt, n=60):
    """Одна телефонная строка из текста задачи: без переносов, обрезка с многоточием."""
    s = " ".join(str(txt or "").split())
    return s if len(s) <= n else s[:n - 1] + "…"


def _active_chains(items):
    """Активные цепи декомпозера ТОЛЬКО по живым признакам (зеркало ПК-фикса 1403fa2;
    живой призрак 23:10 13.07: терминальные родители pcloc-dec 194/200/206–208 висели
    «план строится» вечно — цепь целиком на ПК, шагов в Bridge-очереди нет, а done-родитель
    остаётся в снимке): родитель dec-метки (текст БЕЗ ведущего [маркера] — synthetic
    сводки/карточки/коррекции родителями не считаются) в new/in_progress ИЛИ незакрытый
    «[шаг i/d родитель N]» (new/in_progress/needs_approval/approved). Терминальный родитель
    (done/failed) без незакрытых шагов — призрак, НЕ показываем. Ярлык: открытый шаг
    «шаг i/d», иначе «план строится» → [{pid, line}]."""
    parents, open_steps = {}, {}
    for it in items:
        txt = str(it.get("task_text") or "")
        m = _STEP_MARK_RE.match(txt)
        if m:
            if str(it.get("status") or "") in _OPEN_STEP_STATUSES:
                i, d, pid = int(m.group(1)), int(m.group(2)), int(m.group(3))
                if i >= open_steps.get(pid, (0, 0, None))[0]:
                    open_steps[pid] = (i, d, it)
            continue
        if str(it.get("from") or "") in _DEC_FROMS and not txt.startswith("["):
            pid = _int0(it.get("id"))
            if pid:
                parents[pid] = it
    live = {pid for pid, it in parents.items()
            if str(it.get("status") or "") in _LIVE_PARENT_STATUSES}
    out = []
    for pid in sorted(live | set(open_steps)):
        i, d, step = open_steps.get(pid, (0, 0, None))
        prog = f"шаг {i}/{d}" if step else "план строится"
        it = parents.get(pid) or step or {}
        lane = str(it.get("lane") or "") or "vps"
        text = (parents[pid].get("task_text") if pid in parents
                else _STEP_MARK_RE.sub("", str(step.get("task_text") or "")).strip())
        out.append({"pid": pid,
                    "line": f"  ⛓ цепь {pid} [{lane}]: {prog} — {_short(text, 50)}"})
    return out


def _parse_revisor(tick):
    """Строка «👁 надзор: …» из текста тик-NOTE: честное время (ТОЛЬКО если есть в NOTE —
    никакого «время неизвестно»), окна/находки (что распарсилось), иначе короткий текст тика."""
    tm = _REV_TIME_RE.search(tick) or _REV_HHMM_RE.search(tick)
    mw = _REV_WIN_RE.search(tick) or _REV_WIN_RE2.search(tick)
    mf = _REV_FIND_RE.search(tick)
    parts = []
    if mw:
        parts.append(f"окон {mw.group(1)}")
    if mf:
        f = _int0(mf.group(1))
        parts.append(f"находок {f}" + (" ❗" if f else ""))
    return ("👁 надзор: ревизор" + (f" {tm.group(0)}" if tm else "") + " — " +
            (", ".join(parts) if parts else _short(tick)))


def _revisor_line(cowork_fn=None):
    """Последний тик ревизора — свежая NOTE «ревизор: …» в cowork_log (новые сверху, первая
    совпавшая). NOTE нет → честное «тиков ещё не было»; журнал не прочитался → честное
    «недоступен» (отсутствие данных ≠ тишина; сводку в любом случае не валим)."""
    try:
        text = cowork_fn() if cowork_fn else None
    except Exception:
        text = None
    if text is None:
        return "👁 надзор: cowork_log недоступен — тик ревизора неизвестен"
    for line in text.splitlines():
        m = _REV_NOTE_RE.match(line)
        if m:
            return _parse_revisor(m.group(1))
    return "👁 надзор: ревизор: тиков ещё не было"


def _system_summary(items, goals, cowork_fn=None):
    """Сводка «всё ли завершено» из снимка очереди + среза кураторских целей.
    Дедуп с соседними блоками: шаги/родители активных цепей не дублируются одиночками,
    кураторские задачи ([куратор …]) — одной строкой-счётчиком (детали в дайджесте ниже)."""
    chains = _active_chains(items)
    chain_ids = {c["pid"] for c in chains}
    singles, waits = [], []
    for it in items:
        if str(it.get("from") or "") not in QUEUE_FROMS:
            continue
        st = str(it.get("status") or "")
        txt = str(it.get("task_text") or "")
        iid = _int0(it.get("id"))
        if st == "needs_approval":
            waits.append((iid, it, txt))
        elif st in _CURATOR_ACTIVE_STATUSES:
            if txt.startswith(("[куратор", "[сводка", "[ревизор")):
                continue                     # куратор — счётчиком ниже; сводка/тик — технические
            if _STEP_MARK_RE.match(txt) or iid in chain_ids:
                continue                     # шаг/родитель активной цепи — покрыт строкой цепи
            singles.append((iid, it, st, txt))
    cur_work = sum(1 for g in goals.values()
                   if not (g["owner"] or g["wait"]) and g["active"])
    n = len(chains) + len(singles) + cur_work
    m = len(waits)
    if n == 0 and m == 0:
        out = ["🟢 ТИХО: в работе 0, ждёт тебя 0"]
    else:
        out = [f"⚙️ в работе {n}:"]
        for c in chains[:_SECTION_TOP]:
            out.append(c["line"])
        shown = sorted(singles, key=lambda t: -t[0])[:_SECTION_TOP]
        for iid, it, st, txt in shown:
            lane = str(it.get("lane") or "") or "vps"
            out.append(f"  {_ST_ICON.get(st, '🔄')} {iid} [{lane}]: {_short(txt)}")
        hidden = (len(chains) - min(len(chains), _SECTION_TOP)
                  + len(singles) - len(shown))
        if hidden:
            out.append(f"  …ещё {hidden}")
        if cur_work:
            out.append(f"  🧭 цели куратора в работе: {cur_work} (дайджест ниже)")
        out.append(f"🧑 ждёт тебя {m}:" if m else "🧑 ждёт тебя 0")
        for iid, it, txt in sorted(waits, key=lambda t: -t[0])[:_SECTION_TOP]:
            if _OWNER_CARD_RE.match(txt):
                out.append(f"  🧑 карточка {iid}: {_short(txt)}")
            else:
                lane = str(it.get("lane") or "") or "vps"
                out.append(f"  ❓ {iid} [{lane}]: {_short(txt)}")
        if m > _SECTION_TOP:
            out.append(f"  …ещё {m - _SECTION_TOP}")
    out.append(_revisor_line(cowork_fn))
    return "\n".join(out)


def _g_pulse(bridge):
    """Пульс проекта (строка KB_PULSE) + сводка системы (задача 285: в работе / ждёт тебя /
    надзор — одна правда «всё ли завершено») + дайджест кураторских целей (шаг 5/7 родитель
    231, когда цели есть). Очередь опрашивается РОВНО один раз (снимок общий); сбой опроса →
    пульс + честная пометка, ничего не валим."""
    r = bridge._call("read_doc", name="pulse")
    if not r.get("ok"):
        base = f"пульс недоступен: {r.get('error')}"
    else:
        base = "📟 " + (r.get("text") or "").strip()
    items = _queue_snapshot(bridge)
    if items is None:
        return base + "\n\n⚠️ очередь не опросилась — сводка системы недоступна"
    goals = _curator_goals(bridge, items) or {}

    def _cowork_text():
        try:
            rr = bridge._call("read_doc", name="cowork_log")
            return (rr.get("text") or "") if rr.get("ok") else None
        except Exception:
            return None
    blocks = [base, _system_summary(items, goals, _cowork_text)]
    dig = _curator_digest_render(goals)
    if dig:
        blocks.append(dig)
    return "\n\n".join(blocks)


def _g_registry():
    """Реестр знания — сверка карта↔реальность (registry_check.py, read-only: git + read_doc +
    счёт файлов Brain, БЕЗ LLM). Сжатый отчёт для телефона: «✅ СХОДИТСЯ» или список расхождений.
    Подпроцессом (как гейт) — своя LiveWorld/BridgeClient внутри скрипта, изоляция контура цела."""
    try:
        r = subprocess.run([PY, os.path.join(ROOT, "registry_check.py")], cwd=ROOT,
                           capture_output=True, text=True, timeout=120)
        out = (r.stdout or "").strip() or (r.stderr or "").strip() or "(нет вывода)"
        return out if r.returncode == 0 else f"🧭 реестр упал (exit={r.returncode}):\n{out}"
    except subprocess.TimeoutExpired:
        return "🧭 реестр не уложился в 120с (Bridge/сеть тупит) — попробуй позже."
    except Exception as e:
        return f"🧭 реестр не запустился: {e}"


def _g_invariants():
    """Инварианты данных v1 — непрерывные проверки живых данных (read-only).
    Подпроцессом (изоляция контура цела); silent при ✅, флаги при нарушениях."""
    try:
        r = subprocess.run([PY, os.path.join(ROOT, "invariants_check.py")], cwd=ROOT,
                           capture_output=True, text=True, timeout=120)
        out = (r.stdout or "").strip() or (r.stderr or "").strip() or "(нет вывода)"
        return out if r.returncode == 0 else f"⚠️ инварианты упали (exit={r.returncode}):\n{out}"
    except subprocess.TimeoutExpired:
        return "⚠️ инварианты не уложились в 120с (Bridge/сеть тупит) — попробуй позже."
    except Exception as e:
        return f"⚠️ инварианты не запустились: {e}"


def _g_tokens():
    """Аудит красных токенов в файлах проекта (tools/token_audit.py, in-process, read-only).
    Без subprocess/grep — токены из pretool_guard в рантайме, ни одного литерала в скрипте.
    Подпроцессом — своя изоляция; pretool_guard видит скрипт без красных литералов → defer."""
    try:
        r = subprocess.run([PY, os.path.join(ROOT, "tools", "token_audit.py")],
                           cwd=ROOT, capture_output=True, text=True, timeout=60)
        out = (r.stdout or "").strip() or (r.stderr or "").strip() or "(нет вывода)"
        return out if r.returncode == 0 else f"⚠️ токен-аудит упал (exit={r.returncode}):\n{out}"
    except subprocess.TimeoutExpired:
        return "⚠️ токен-аудит не уложился в 60с — попробуй позже."
    except Exception as e:
        return f"⚠️ токен-аудит не запустился: {e}"


def _g_gate():
    """Прогон гейта 4.3 (тесты, ~7с). Зелёный read-only прогон — сам ничего не деплоит."""
    try:
        r = subprocess.run([PY, os.path.join(ROOT, "gate.py")], cwd=ROOT,
                           capture_output=True, text=True, timeout=120)
        out = (r.stdout or "").strip() or (r.stderr or "").strip() or "(нет вывода)"
        return out if r.returncode == 0 else f"🔴 ГЕЙТ КРАСНЫЙ (exit={r.returncode}):\n{out}"
    except Exception as e:
        return f"гейт не запустился: {e}"


def _g_help():
    return ("🤖 Дев-бот — зелёные read-only команды:\n"
            "  health — здоровье системы\n"
            "  аудит — сводка открытых замечаний\n"
            "  боевой / writelog — последние боевые записи\n"
            "  cclog — свежие cc_log\n"
            "  ошибки — сводка splinter.log\n"
            "  мозг / brain — латентность Brain\n"
            "  просрочки — просрочки ТО парка (скан O3, топ-10)\n"
            "  статус / пульс — сводка системы: в работе / ждёт тебя / надзор + KB_PULSE\n"
            "    (всё пусто → «🟢 ТИХО» = всё завершено)\n"
            "  сверься / реестр — сверка карта↔реальность (реестр знания, read-only)\n"
            "  инварианты — проверка данных аренды (масло/сроки/депозит/CLICK125, read-only)\n"
            "  токены — аудит красных токенов в преамбулах/тестах/конфигах (read-only)\n"
            "  гейт — прогон тестов 4.3 (~7с)\n"
            "  помощь\n"
            "\n🎻 Оркестратор (демон исполняет через headless Claude Code):\n"
            "  тз: <что сделать> — дев-ТЗ (до 45 мин): правки кода/тесты/гейт/push/restart splinter\n"
            "    сам (restart — через гейт + проверку старта); настоящее красное — спрошу кнопкой\n"
            "  задача: <что сделать> — быстрая задача (до 10 мин), та же дисциплина\n"
            "  декомпозируй: <крупное ТЗ> — план шагов → шаги отдельными задачами по одному → сводка\n"
            "  да N / нет N — ответ на запрос подтверждения красной зоны по задаче N\n"
            "  (в теме PC-дев те же «тз:»/«задача:»/«декомпозируй:» уходят ПК-театру: план на "
            "VPS, шаги — ПК-агент, полоса lane=pc)\n"
            "  (красную зону демон сам НЕ проходит — спросит кнопкой)\n"
            "Красное (запись в таблицы/деньги/деплой Bridge) сам НЕ делаю — нужно твоё «да».")


# allowlist: набор ключевых слов → зелёная функция (берёт bridge)
_ALLOWLIST = [
    (("health", "хелс", "здоров"), lambda b: _g_health()),
    (("аудит", "audit"), lambda b: _g_audit(b)),
    (("боев", "writelog", "write log"), lambda b: _g_writelog(b)),
    (("cclog", "cc_log", "cc лог", "cc-лог"), lambda b: _g_cclog(b)),
    (("ошибк", "errors", "splinter.log", "лог сплинтер"), lambda b: _g_errors()),
    (("мозг", "brain", "свеж"), lambda b: _g_brain(b)),
    (("просрочк", "overdue"), lambda b: _g_overdue(b)),
    (("статус", "пульс", "pulse", "status"), lambda b: _g_pulse(b)),
    (("сверься", "сверка", "сверить", "реестр", "registry"), lambda b: _g_registry()),
    (("инвариант", "invariant"), lambda b: _g_invariants()),
    (("токен", "token audit", "token_audit"), lambda b: _g_tokens()),
    (("гейт", "gate"), lambda b: _g_gate()),
    (("помощ", "help", "команд"), lambda b: _g_help()),
]


_GREEN_CMD_MAX_CHARS = 32   # зелёная команда = короткое сообщение-команда («покажи статус», «cc лог»)
_GREEN_CMD_MAX_WORDS = 4    # длинный текст со словом команды В ТЕЛЕ — это ТЗ/вопрос, НЕ команда


def _match(text):
    """Зелёная однословная команда срабатывает ТОЛЬКО когда сообщение и ЕСТЬ команда (короткое
    после трима), а НЕ когда её слово встретилось в теле длинного ТЗ. Инцидент 23:49 11.07.2026:
    «пк: декомпозируй: <крупное ТЗ>» угнан словом зелёной команды из тела → простыня журнала
    вместо постановки родителя. Структурированные префиксы (задача:/тз:/декомпозируй:/пк:) —
    абсолютный приоритет: сообщение с ними в зелёное не попадает вообще, даже короткое
    (защита в глубину: обычно их раньше съедает _try_enqueue)."""
    t = (text or "").strip().lower()
    if not t or len(t) > _GREEN_CMD_MAX_CHARS or len(t.split()) > _GREEN_CMD_MAX_WORDS:
        return None
    if t.startswith(_STRUCT_PREFIXES + _PC_TEXT_PREFIXES):
        return None
    for keys, fn in _ALLOWLIST:
        if any(k in t for k in keys):
            return fn
    return None


def _chunks(s, n=3500):
    s = s or ""
    return [s[i:i + n] for i in range(0, len(s), n)] or [""]


# ===================== ТОЧКИ ВХОДА =====================
async def handle_command(msg, context, bridge) -> None:
    """Команда дев-боту в его темах: 328 (полоса vps), PC-дев (полоса pc, env PC_DEV_TOPIC_ID)
    и тема-инбокс (env INBOX_TOPIC_ID, 13.07.2026 — только ответы на карточки «ждут владельца»).
    ТОЛЬКО от Филиппа; в 328 — префиксы + зелёное из allowlist; в PC-дев — ТОЛЬКО «тз:»/«задача:»
    (→ enqueue lane=pc) и ответы «да N»/«нет N»; в инбоксе — ТОЛЬКО «да N»/«нет N» (+кнопки).
    Вне-allowlist/красное → НЕ выполняет, просит «да».
    Зелёное гоняет как origin=agent (без билета): красная запись внутри → токен-замок 4.2."""
    tid = getattr(msg, "message_thread_id", None)
    pc_topic = pc_dev_topic()
    ibx = inbox_topic()
    if tid == DEVBOT_TOPIC:
        lane = "vps"
    elif pc_topic and tid == pc_topic:
        lane = "pc"
    elif ibx and tid == ibx:
        lane = "inbox"   # тема-инбокс «ждут владельца» (13.07.2026): ТОЛЬКО ответы «да N»/«нет N»
    else:
        return   # не наша тема (напр. 205 = pc_agent на ПК) — НЕ реагируем вообще
    if not msg.from_user or msg.from_user.id != DEVBOT_USER:
        return   # чужой — игнор

    # 0) Ответ на запрос подтверждения «да N» / «нет N» — ПЕРВЫМ (специфичный паттерн).
    # Работает из 328, PC-дев И темы-инбокса (13.07.2026: карточки «ждут владельца» сходятся в
    # инбокс — ответ там же). Bridge — через to_thread (фикс 02.07): loop не встаёт, пока /exec тупит.
    # 31.07.2026: сюда же новая форма «да|нет <названный объект>» — привязка по номеру ИЛИ по
    # РЕПЛАЮ на сообщение карточки, поэтому пробрасываем текст сообщения-адресата и полосу.
    _r = getattr(msg, "reply_to_message", None)
    reply_text = (getattr(_r, "text", None) or getattr(_r, "caption", None)) if _r else None
    appr = await asyncio.to_thread(_try_approval_reply, msg.text or "", bridge, reply_text, lane)
    if appr is not None:
        for chunk in _chunks(appr):
            await context.bot.send_message(chat_id=msg.chat_id, message_thread_id=tid, text=chunk)
        return

    # Тема-инбокс: команд/ТЗ/зелёного allowlist там НЕТ — только ответы на карточки.
    # Guard-карточки pretool_guard (интерактивное «жду да») тоже приходят сюда, но их «да» даётся
    # в терминале — «да N» применим только к задачам очереди с номером.
    # 31.07.2026: вместо ОБЩЕЙ справки — конкретное «не принято, потому что …» по форме текста
    # (инцидент карточки 95: два ответа владельца подряд отбиты справкой, причина не названа).
    if lane == "inbox":
        try:
            hint = await asyncio.to_thread(inbox_reject_hint, msg.text or "", bridge)
        except Exception as e:                       # fail-safe: прежняя справка, не молчание
            log.warning("devbot: конкретный отказ инбокса не собрался (%s)", e)
            hint = ("🤖 Это тема-инбокс подтверждений: «да N» / «нет N» или кнопки под карточкой. "
                    "Команды и ТЗ — в теме 328 (полоса vps) или PC-дев.")
        for chunk in _chunks(hint):
            await context.bot.send_message(chat_id=msg.chat_id, message_thread_id=tid, text=chunk)
        return

    # 1) Задача оркестратору (префикс) — проверяем ПЕРЕД allowlist. enqueue_task не красная зона
    #    (служебный лист очереди), origin=human по умолчанию — гейт 4.2 не трогаем.
    enq = await asyncio.to_thread(_try_enqueue, msg.text or "", bridge, lane, _msg_key(msg))
    if enq is not None:
        for chunk in _chunks(enq):
            await context.bot.send_message(chat_id=msg.chat_id, message_thread_id=tid, text=chunk)
        return

    # Полоса pc: зелёный allowlist НЕ гоняем (он про VPS) — только подсказка формата.
    if lane == "pc":
        await context.bot.send_message(
            chat_id=msg.chat_id, message_thread_id=tid,
            text=("🤖 Тема PC-дев (lane=pc): «тз: <ТЗ>» или «задача: <что сделать>» — уйдёт "
                  "ПК-агенту; «декомпозируй: <крупное ТЗ>» — план на VPS, шаги ПК-агенту по "
                  "одному; «да N» / «нет N» — ответ на красный вопрос. "
                  "Зелёные VPS-команды (health/аудит/…) — в теме 328."))
        return

    # 2) Зелёная read-only команда из allowlist
    fn = _match(msg.text or "")
    if fn is None:
        await context.bot.send_message(
            chat_id=msg.chat_id, message_thread_id=tid,
            text=("🤖 Это не зелёная команда (или красное: запись/деплой). Сам НЕ выполняю — нужно твоё «да». "
                  "Зелёное: health / аудит / боевой / cclog / ошибки / мозг / просрочки / статус / сверься / инварианты / токены / гейт / помощь."
                  "Дев-ТЗ: «тз: <что сделать>»."))
        return
    def _run_green():
        with bridge_client.agent_write(None):   # origin=agent, без билета → красная запись будет отклонена
            return fn(bridge)
    try:
        reply = await asyncio.to_thread(_run_green)   # фикс 02.07: не морозим loop на зелёной команде
    except Exception as e:
        reply = f"🤖 ошибка зелёной задачи: {type(e).__name__}: {e}"
    for chunk in _chunks(reply):
        await context.bot.send_message(chat_id=msg.chat_id, message_thread_id=tid, text=chunk)


async def morning_summary(context) -> None:
    """Утренняя авто-сводка в topic 328 (health + открытый аудит + латентность Brain). read-only, agent."""
    bridge = BRIDGE
    if bridge is None:
        log.warning("devbot.morning_summary: BRIDGE не выставлен")
        return
    def _collect():
        with bridge_client.agent_write(None):
            return "\n".join(["🌅 Утренняя сводка дев-бота", "", _g_health(), "",
                              _g_audit(bridge), "", _g_brain(bridge)])
    try:
        text = await asyncio.to_thread(_collect)   # фикс 02.07: сбор сводки не морозит loop
    except Exception as e:
        text = f"🌅 Утренняя сводка: ошибка сбора ({type(e).__name__}: {e})"
    for chunk in _chunks(text):
        await context.bot.send_message(chat_id=HQ_CHAT_ID, message_thread_id=DEVBOT_TOPIC, text=chunk)
