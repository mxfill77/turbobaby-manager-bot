"""
TurboBaby Bridge HTTP клиент.
Дёргает Apps Script Web App для чтения данных из Google Sheets.
"""

import os
import re
import sys
import json
import time
import fcntl
import random
import logging
import contextlib
import contextvars
import unicodedata
import requests
import task_metrics                 # общий детектор тест-прогона (стор дедупа: проба ≠ бой)
import fleet_cell                   # контракт клетки Лист1: исход вместо голого нуля
import card_deadline                # общий дедлайн сборки карточки: решение (у модуля ноль импортов)
import result_ref as _result_ref    # адрес результата шага: форма поля очереди (импорт ровно один — re)
from typing import Optional
from urllib.parse import urljoin

log = logging.getLogger(__name__)

# FIXTURE-GUARD (класс 193, 17.07.2026): тест-фикстуры утекали в ЖИВУЮ очередь — демон исполнял
# заглушки по-настоящему (16.07 21:36–21:50: «конверт 999 "сделать нечто"» ×5, «проверь X» ×4,
# «сделай X» шага родителя 10, «task»). Правило класса: тестам — ТОЛЬКО мок-очередь либо явный
# префикс TEST-. Паттерны НАМЕРЕННО узкие (канонические тексты фикстур дословно), чтобы живой
# конверт «[конверт одобренной заявки 999] …» с реальной заявкой через годы НЕ попал под гард:
# фикстурный конверт опознаётся по хвосту «сделать нечто», шаг «родителя 10» — по «сделай X».
# Два рубежа: enqueue_task (клиент, до сети) и process_new демона (фильтр перед claude -p).
FIXTURE_TASK_RE = re.compile(
    r"^\s*TEST-"                                                     # доктрина: явный тест-префикс
    r"|\[конверт одобренной заявки 999\][^\n]{0,80}сделать нечто"    # канонический фикстур-конверт
    r"|\[шаг \d+/\d+ родитель 10\]\s*сделай X"                       # фикстурная цепь «родитель 10»
    r"|^\s*(?:проверь X|сделай X|task|тест|нечто)\s*\.?\s*$",         # голые заглушки целиком
    re.I)

# ЮНИКОД-НОРМАЛИЗАЦИЯ (класс 193, продолжение 17.07.2026): тест «тask» (Кирилл.т + ASCII ask)
# прошёл 02:16 — re.I не знает о конфузиках (Кирилл.т ≠ Latin.t разные кодпоинты). Решение:
# NFC + casefold + узкая карта Кирилл.→Latin-омоглифов. Проверяем ОБА: оригинал (чтобы не сломать
# чисто-кирилл. паттерны «проверь X»/«тест» после map'а) и нормализованный (чтобы поймать тask).
_FIXTURE_CYR2LAT = str.maketrans("аАеЕоОрРсСтТхХ", "aAeEoOpPcCtTxX")


def _fixture_norm(text: str) -> str:
    """NFC + casefold + Кирилл.→Latin lookalike map — для детекции mixed-script заглушек.
    «тask» (Кирилл.т + ASCII ask) → «task» → совпадает паттерном task.
    Чистые кирилл. паттерны ломаются при map'е → проверяются отдельно по оригиналу."""
    t = unicodedata.normalize("NFC", text).casefold()
    return t.translate(_FIXTURE_CYR2LAT)


# СЕТЕВОЙ ЗАПРЕТ В ТЕСТ-РЕЖИМЕ (класс 193, 17.07.2026, рубеж 3): gate.py ставит ORCH_TEST_MODE=1
# всем тестам. При импорте bridge_client с этим флагом патчим requests.Session.send — любая попытка
# дотянуться до нелокального URL поднимает RuntimeError ДО открытия сокета.
# Тесты, корректно мокирующие _post или заменяющие _session своим FakeSession, под гард не попадают
# (до .send() дойти не могут). Localhost разрешён: test_wa_webhook запускает локальный сервер.
# Обход: BRIDGE_ALLOW_NETWORK=1 (транспорт-тесты test_bridge_durable, если когда-то понадобится).
_LOCALHOST_PREFIXES = ("http://127.", "https://127.", "http://[::1]",
                       "https://[::1]", "http://localhost", "https://localhost")


def _install_test_network_ban() -> None:
    """Патчит requests.Session.send, запрещая нелокальные TCP-соединения в тест-режиме."""
    _orig = requests.Session.send

    def _banned(self_sess, request, **kw):
        if os.getenv("BRIDGE_ALLOW_NETWORK") == "1":
            return _orig(self_sess, request, **kw)
        url = str(getattr(request, "url", "") or "")
        if not any(url.startswith(p) for p in _LOCALHOST_PREFIXES):
            raise RuntimeError(
                f"🚫 ТЕСТ ДЁРНУЛ СЕТЬ [{url[:80]}] "
                "(ORCH_TEST_MODE=1) — замокай _post/_session или поставь BRIDGE_ALLOW_NETWORK=1"
            )
        return _orig(self_sess, request, **kw)

    requests.Session.send = _banned


if os.getenv("ORCH_TEST_MODE") == "1":
    _install_test_network_ban()

# HTTP-коды редиректа script.google.com/exec → script.googleusercontent.com (echo-слой)
_REDIRECT_CODES = (301, 302, 303, 307, 308)

# === ТОКЕН-ЗАМОК боевой записи (4.2) ===
# origin записи: 'human' (по умолчанию — люди/кнопки, замок СПИТ) | 'agent' (автономный процесс).
# Сегодня agent НЕ ставится нигде → все записи human → 0 отклонений. Будущий оркестратор/дев-бот
# оборачивает свои вызовы в agent_write(ticket) → origin=agent + билет; Bridge проверит билет.
WRITE_ORIGIN = contextvars.ContextVar("write_origin", default="human")
WRITE_TICKET = contextvars.ContextVar("write_ticket", default=None)


@contextlib.contextmanager
def agent_write(ticket: str):
    """Контекст автономной (agent) боевой записи: origin=agent + одноразовый билет.
    Для БУДУЩЕГО оркестратора/дев-бота. Сегодня не используется (замок спит)."""
    t1 = WRITE_ORIGIN.set("agent")
    t2 = WRITE_TICKET.set(ticket)
    try:
        yield
    finally:
        WRITE_ORIGIN.reset(t1)
        WRITE_TICKET.reset(t2)


# === ДЕДУП ПОСТАНОВКИ ЗАДАЧИ (класс дублей 164/165 и 167/168, 02.08.2026) ===
# ФОРМА — ТА ЖЕ, что у транзакций и событий: запись несёт ключ ПРОИСХОЖДЕНИЯ, и повтор с тем же
# ключом второй строки не рождает. У моста это msg_id (addTransaction/addEvent, BotData.js:468/508
# → {ok:true, duplicate:true} вместо appendRow); у enqueueTask_ (BotData.js:290) ключа НЕТ ВОВСЕ —
# поэтому живая сверка 02.08 (журнал ПК-контура 17:12 UTC) нашла реальные дубли РОВНО там: две
# пары задач (164/165 — 43 с порознь, 167/168 — 46 с), при НУЛЕ денежных дублей, хотя пересылка
# била по всем каналам одинаково. Ключ держал деньги; у постановки держать было нечем.
#
# КЛЮЧ, А НЕ «ТЕКСТ В ОКНЕ». 43 и 46 с — ровно тот масштаб, на котором владелец руками повторяет
# упавшую задачу; дедуп по совпадению текста в окне съел бы этот повтор МОЛЧА. Ключ отвечает на
# другой вопрос — «это то же САМОЕ сообщение или новое?». Осознанный повтор = новое сообщение =
# другой ключ → задача ставится всегда, хоть через секунду. Собирает ключ devbot из (чат, id
# сообщения) + отпечаток самой постановки (метка+текст) — см. devbot._dedup_key.
#
# ОКНО (ENQUEUE_DEDUP_WINDOW, деф. 600с) — НЕ различитель, а срок жизни записи в сторе: 13× от
# наблюдавшихся 43/46 с, с запасом на всю цепочку клиента (одна отправка ~45 с + verify + повтор
# _enqueue_reliable). Различает по-прежнему ключ, окно только не даёт стору расти вечно.
#
# ЧЕСТНЫЙ ПРЕДЕЛ: стор КЛИЕНТСКИЙ — ловит повторный ВЫЗОВ (реплей апдейта Telegram, ретрай
# надёжной постановки, рестарт devbot). Пересылку ВНУТРИ одного вызова закрыл d78d5fa (write-POST
# не пересылается); чтобы её ловил и мост, ключ уже уходит в теле полем dedup_key — enqueueTask_
# его сегодня игнорирует (читает from/task_text/lane), сверка ключа на мосту = отдельная правка
# Apps Script (красная зона, деплой владельцем). Тесты tests/test_enqueue_dedup.py (в гейте).
_DEDUP_ROOT = os.path.dirname(os.path.abspath(__file__))
_DEDUP_WINDOW_DEFAULT = 600.0


def _dedup_file() -> str:
    """Путь стора ключей. ENQUEUE_DEDUP_FILE — явная подмена (тесты, временные каталоги).
    ИЗОЛЯЦИЯ ПРОБ (класс 01.08): тест-прогон метит в ОТДЕЛЬНЫЙ файл — тестовый ключ не должен
    схлопнуть живую постановку. Признак берём общий (task_metrics.under_test), тесты вдобавок
    подставляют свой путь — два независимых пояса."""
    p = (os.environ.get("ENQUEUE_DEDUP_FILE") or "").strip()
    if p:
        return p
    name = "enqueue_dedup.json"
    try:
        if task_metrics.under_test(sys.argv[0] if sys.argv else "", os.environ, sys.modules):
            name = "enqueue_dedup.test.json"
    except Exception:
        pass
    return os.path.join(_DEDUP_ROOT, name)


def _dedup_window() -> float:
    """Срок жизни ключа, сек. Мусор в env → дефолт (в сторону прежнего поведения)."""
    try:
        return max(0.0, float(os.environ.get("ENQUEUE_DEDUP_WINDOW") or _DEDUP_WINDOW_DEFAULT))
    except (TypeError, ValueError):
        return _DEDUP_WINDOW_DEFAULT


class _DedupLock:
    """flock на lock-файле — атомарность read-modify-write стора (форма spend_ledger._Lock)."""

    def __init__(self, path):
        self.path, self.f = path + ".lock", None

    def __enter__(self):
        try:
            self.f = open(self.path, "w")
            fcntl.flock(self.f, fcntl.LOCK_EX)
        except Exception:
            self.f = None
        return self

    def __exit__(self, *a):
        try:
            if self.f:
                fcntl.flock(self.f, fcntl.LOCK_UN)
                self.f.close()
        except Exception:
            pass


def _dedup_lookup(key: str):
    """id задачи, уже поставленной по этому ключу в пределах окна → id | None.
    Любой сбой стора → None: дедуп молча выключается, постановка идёт как прежде (fail-open —
    потерять задачу владельца хуже, чем продублировать)."""
    try:
        with open(_dedup_file(), encoding="utf-8") as f:
            rec = (json.load(f) or {}).get(key)
        if not isinstance(rec, dict):
            return None
        if time.time() - float(rec.get("ts") or 0) > _dedup_window():
            return None
        return rec.get("id")
    except Exception:
        return None


def _dedup_remember(key: str, task_id) -> None:
    """Запомнить «ключ → id» (атомарно tmp+os.replace; протухшее выметается тем же проходом).
    Запоминается ТОЛЬКО успешная постановка: у неизвестного исхода повтор должен уходить в мост."""
    path = _dedup_file()
    try:
        with _DedupLock(path):
            try:
                with open(path, encoding="utf-8") as f:
                    store = json.load(f)
            except Exception:
                store = {}
            if not isinstance(store, dict):
                store = {}
            now, win = time.time(), _dedup_window()
            fresh = {k: v for k, v in store.items()
                     if isinstance(v, dict) and now - float(v.get("ts") or 0) <= win}
            fresh[key] = {"id": task_id, "ts": now}
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(fresh, f, ensure_ascii=False)
            os.replace(tmp, path)
    except Exception as e:
        log.debug("дедуп постановки: стор не обновлён (%s) — постановка не затронута", e)


# ============ ОБЩИЙ ДЕДЛАЙН СБОРКИ ОДНОЙ КАРТОЧКИ (13.08.2026, замер 06:53) ============
# Решение — чистый `card_deadline` (у него ноль импортов, он не умеет ни узнать время, ни сходить
# в сеть). Здесь — РУКИ: кто открывает бюджет и кто режет по нему три вложенные лестницы повторов
# (полные попытки `_durable_request` × хопы редиректа `_exchange` × попытки эхо `_fetch_redirect_
# target`). Потолок — на ВСЮ карточку: лестницы остаются, но исчерпать бюджет целиком не могут.
#
# ContextVar, а не поле клиента: клиент один на процесс и его делят разные потоки/задачи, а бюджет
# принадлежит ОДНОЙ сборке. Вне открытого бюджета значение None → все проверки ниже пропускают,
# то есть путь БАЙТ-В-БАЙТ прежний (демон, аудитор, health моста дедлайна не видят вовсе).
_CARD_BUDGET = contextvars.ContextVar("bridge_card_budget", default=None)

# Плечо, ВЫДАННОЕ последнему HTTP-обмену этого контекста (см. `BridgeClient._timeout_said`).
# Диагностическая величина: её пишет `_leg_timeout`, читает журнал таймаута — и никто больше.
_LAST_LEG = contextvars.ContextVar("bridge_last_leg", default=None)

CARD_DEADLINE_ERROR = "card_deadline"

# Ошибки, после которых источник считается НЕ ПРОЧИТАННЫМ — карточка обязана сказать это вслух.
# Семантический отказ моста сюда НЕ входит: `service_pending_get` отвечает `not_found`, когда
# открытой заявки просто НЕТ, — источник ответил, и ответ «пусто». Смешать их значило бы кричать
# «не прочитано» на каждой здоровой карточке, а крик, звучащий всегда, перестают слышать.
UNREAD_ERRORS = frozenset((
    "timeout", "request_failed", "json_parse_error", "unauthorized",
    "receipt_unknown", "unknown_action", CARD_DEADLINE_ERROR,
))


class CardBudgetExpired(Exception):
    """Общий бюджет карточки исчерпан — новое HTTP-плечо не начинаем.
    Ловится в `_one_exchange` и превращается в честный контракт {ok:false, error:'card_deadline'}:
    наружу уходит ОТВЕТ, а не исключение, — сборка карточки продолжается и досказывает остальное."""


class CardBudget:
    """Состояние одной сборки: до какого момента она вправе идти и что не успела прочитать.

    Копит НЕ ПРОЧИТАННОЕ по ходу дела, потому что спросить об этом задним числом уже не у кого:
    `find_bike` на сбое моста отдаёт `{}` — ровно то же, что при «байка нет в парке». Отличить
    молчание источника от честной пустоты может только тот, кто видел ответ, — то есть это место."""

    def __init__(self, budget, started, deadline, label="карточки"):
        self.budget = budget
        self.started = started
        self.deadline = deadline
        # Чей это бюджет — словом, для журнала. Механизм общий (его открыл и опрос очереди
        # devbot, 15.08.2026), а строка «общий бюджет карточки» о заходе опроса просто врала бы
        # читателю журнала. Умолчание «карточки» → путь карточки байт-в-байт прежний.
        self.label = label
        self.unread = {}        # действие → ошибка, из-за которой источник не прочитан
        self.answered = set()   # действия, ответившие ХОТЬ ЧЕМ-ТО (в т.ч. честным «not_found»)
        self.deadline_hit = False

    def note(self, action, data):
        """Записать исход действия. `ok` или семантический отказ → источник ответил."""
        err = str((data or {}).get("error") or "")
        if (data or {}).get("ok") or err not in UNREAD_ERRORS:
            self.answered.add(action)
            self.unread.pop(action, None)
            return
        self.unread[action] = err
        if err == CARD_DEADLINE_ERROR:
            self.deadline_hit = True

    def note_deadline(self):
        self.deadline_hit = True

    def missing(self):
        """Источники, которые НЕ ответили. Действие, ответившее хоть раз, отсюда уходит: карточка
        показывает его данные, и жаловаться на него — врать в другую сторону."""
        return [a for a in self.unread if a not in self.answered]

    def spent(self, now):
        return float(now) - float(self.started)


@contextlib.contextmanager
def card_budget(budget, now=None, label="карточки"):
    """Открыть общий бюджет на сборку одной карточки. `budget<=0` → дедлайна нет (откат
    `INFO_CARD_BUDGET_SEC=0`), но учёт непрочитанного остаётся: он не стоит ни запроса, ни секунды.

    `label` — чей это заход, для журнала (опрос очереди devbot зовёт то же самое, 15.08.2026)."""
    now = time.monotonic() if now is None else now
    state = CardBudget(budget, now, card_deadline.deadline_at(now, budget), label=label)
    token = _CARD_BUDGET.set(state)
    try:
        yield state
    finally:
        _CARD_BUDGET.reset(token)


def current_card_budget():
    """Бюджет текущей сборки или None (вне карточки)."""
    return _CARD_BUDGET.get()


class BridgeClient:
    """Клиент к Apps Script Bridge Web App."""

    # POST-действия, безопасные для ПОЛНОГО повтора (re-POST): read-only/идемпотентные.
    # Write-действия (enqueue/claim/complete/set_fleet_*/транзакции/...) сюда НЕ добавлять —
    # слепой re-POST даёт дубль записи (enqueue покрыт _enqueue_reliable verify-паттерном).
    _IDEMPOTENT_POST_ACTIONS = {
        "read_write_log", "get_balance", "tx_summary",
        "closing_get", "closing_list", "service_list",
        "service_pending_get", "service_pending_list",
        "important_list", "important_due", "audit_list",
        "state_get", "state_list", "task_heartbeat",
    }

    def __init__(self, url: str = None, token: str = None, timeout: int = 60):
        self.url = url or os.getenv("BRIDGE_URL")
        self.token = token or os.getenv("BRIDGE_TOKEN")
        self.timeout = timeout

        if not self.url or not self.token:
            raise ValueError("BRIDGE_URL и BRIDGE_TOKEN обязательны (см. .env)")

        # DURABLE-слой (фикс intermittent 404 Google, 07.07.2026): ретраи + анти-клин.
        def _env_num(name, default, cast):
            try:
                return cast(os.getenv(name, "") or default)
            except (TypeError, ValueError):
                return default
        self.retry_attempts = _env_num("BRIDGE_RETRY_ATTEMPTS", 3, int)   # попыток всего (1 = без ретраев)
        self.retry_base = _env_num("BRIDGE_RETRY_BASE", 0.6, float)       # base экспоненциальной паузы, сек
        self.retry_jitter = _env_num("BRIDGE_RETRY_JITTER", 0.4, float)   # верх jitter, сек
        self.wedge_limit = _env_num("BRIDGE_WEDGE_LIMIT", 3, int)         # N подряд транспорт-сбоев → новая сессия
        self._session = requests.Session()
        self._consec_transport_fails = 0

    # === DURABLE HTTP-слой (единая точка всех клиентов Bridge) ===

    def _new_session(self):
        """Анти-клин: пересоздать HTTP-сессию (заклинившие keep-alive соединения — в мусор)."""
        old = getattr(self, "_session", None)
        try:
            if old is not None:
                old.close()
        except Exception:
            pass
        self._session = requests.Session()

    def _note_transport(self, failed: bool):
        """Счётчик подряд идущих транспорт-сбоев (timeout/request_failed). Порог → новая сессия."""
        if not failed:
            self._consec_transport_fails = 0
            return
        self._consec_transport_fails += 1
        if self._consec_transport_fails >= self.wedge_limit:
            log.warning(f"Bridge: {self._consec_transport_fails} подряд транспорт-сбоев — "
                        f"пересоздаю HTTP-сессию (анти-клин)")
            self._new_session()
            self._consec_transport_fails = 0

    def _backoff(self, attempt: int):
        """Экспоненциальная пауза + jitter перед повтором (attempt с 0)."""
        time.sleep(self.retry_base * (2 ** attempt) + random.uniform(0, self.retry_jitter))

    # --- ОБЩИЙ ДЕДЛАЙН КАРТОЧКИ: три ручки, которыми режутся все три лестницы повторов ---

    def _leg_timeout(self):
        """Бюджет ОДНОГО HTTP-плеча с оглядкой на общий дедлайн карточки.
        Без этого плечо, начатое за 2 с до дедлайна, честно провисит все 60 и перекроет общий
        потолок в 30 раз — то есть потолок остался бы на бумаге.

        Выданное число ЗАПОМИНАЕТСЯ (`_LAST_LEG`): журнал таймаута обязан назвать его, а не
        настроенное плечо (класс 15.08.2026, см. `_timeout_said`)."""
        state = _CARD_BUDGET.get()
        if state is None:
            issued = self.timeout
        else:
            issued = card_deadline.leg_timeout(state.deadline, time.monotonic(), self.timeout)
        _LAST_LEG.set(issued)
        return issued

    # --- ЖУРНАЛ ТАЙМАУТА НАЗЫВАЕТ ВЫДАННОЕ ПЛЕЧО, А НЕ НАСТРОЕННОЕ (15.08.2026) ---
    #
    # КЛАСС. Строка `Bridge timeout (>Ns)` печатала `self.timeout` — НАСТРОЕННОЕ плечо, — тогда
    # как запросу выдавался `_leg_timeout()`, урезанный остатком общего бюджета. В журнале стояло
    # «>45s» там, где плечо реально прождало ~14 с: замер по splinter.log читал настройку вместо
    # факта и завышал время ожидания. Родня класса — «нуль по неразбору» (`scan_result`) и
    # «баланс из кэша молча» (`balance_fact`): число печатается, а откуда оно — умалчивается.
    #
    # ПОЧЕМУ ContextVar, А НЕ ПОЛЕ КЛИЕНТА: клиент один на процесс и его делят потоки (опрос
    # очереди живёт в `asyncio.to_thread`), а выданное плечо принадлежит ОДНОМУ обмену. Поле
    # клиента дало бы чужое число из соседнего потока — ту же ложь с другой стороны. У контекстных
    # переменных контекст свой на поток, поэтому разойтись им негде; ровно этим уже живёт
    # `_CARD_BUDGET` двадцатью строками выше.
    #
    # ФОРМА ГОЛОВЫ СТРОКИ НЕ ТРОНУТА: `Bridge timeout (>Ns) for action=…` — по ней ходят разборщики
    # журнала; пометка урезки клеится ПОСЛЕ, отдельным хвостом. Когда урезки не было, строка
    # БАЙТ-В-БАЙТ прежняя (число печатает `card_deadline._num`: 45.0 → «45», как печаталось int'ом).
    _LEG_CUT_NOTE = "выдано остатком общего бюджета"

    def _timeout_said(self):
        """(число для журнала, хвост-пометка) о плече, которое сейчас истекло.

        Правило одно: пометка объясняет, ПОЧЕМУ число не равно настроенному, — поэтому она
        появляется ровно тогда, когда числа РАЗЛИЧАЮТСЯ на глаз. Плечо не записано (никто не
        звал `_leg_timeout` — так бывает только у подменённой сессии) → прежнее поведение
        байт-в-байт: печатаем настройку."""
        issued = _LAST_LEG.get()
        base = self.timeout
        if issued is None:
            return card_deadline._num(base), ""
        said, want = card_deadline._num(issued), card_deadline._num(base)
        if said == want:
            return said, ""
        return said, f" — {self._LEG_CUT_NOTE} {self._card_label()} (настроено {want}s)"

    def _card_room(self, what: str = "плечо"):
        """Есть ли в бюджете карточки место ещё на одно плечо. Нет → CardBudgetExpired."""
        state = _CARD_BUDGET.get()
        if state is None:
            return
        if not card_deadline.may_start_leg(state.deadline, time.monotonic()):
            state.note_deadline()
            raise CardBudgetExpired(
                f"общий бюджет {state.label} {card_deadline._num(state.budget)} с исчерпан — {what} не начинаю")

    def _card_label(self) -> str:
        """Чей бюджет сейчас открыт — словом, для журнала. Вне бюджета — «карточки»: так строка
        остаётся прежней у пути, ради которого механизм и заведён."""
        state = _CARD_BUDGET.get()
        return state.label if state is not None else "карточки"

    def _card_may_wait(self, pause: float) -> bool:
        """Влезает ли в бюджет карточки пауза backoff И плечо после неё. Ждать, чтобы потом
        упереться в исчерпанный бюджет, — чистая потеря времени человека у кнопки."""
        state = _CARD_BUDGET.get()
        if state is None:
            return True
        return card_deadline.may_wait(state.deadline, time.monotonic(), pause)

    def _fetch_redirect_target(self, url: str):
        """GET на Location redirect-echo слоя googleusercontent с backoff-ретраями на
        404/5xx/timeout. Ретраить БЕЗОПАСНО даже после write-POST: сам POST уже исполнен
        Apps Script'ом, этот GET лишь забирает готовый ответ (ночной инцидент 07.07:
        claim долетел, а ответ терялся на 404 echo-слоя)."""
        last_err = None
        for attempt in range(max(1, self.retry_attempts)):
            if attempt:
                # ЛЕСТНИЦА 3 (эхо-слой) под общим дедлайном карточки: не влезает пауза + плечо —
                # выходим с последней ошибкой, а не жжём остаток на заведомо бесполезный повтор.
                if not self._card_may_wait(self.retry_base * (2 ** (attempt - 1))):
                    log.warning("Bridge: echo-ретрай отменён — общий бюджет %s не вмещает его",
                                self._card_label())
                    break
                log.warning(f"Bridge: echo-слой сбоит ({last_err}) — ретрай {attempt + 1}/{self.retry_attempts}")
                self._backoff(attempt - 1)
            self._card_room("плечо эхо-слоя")
            try:
                r = self._session.get(url, timeout=self._leg_timeout(), allow_redirects=False)
            except requests.exceptions.RequestException as e:
                last_err = e
                continue
            if r.status_code == 404 or r.status_code >= 500:
                last_err = requests.exceptions.HTTPError(
                    f"HTTP {r.status_code} на redirect-echo", response=r)
                continue
            return r
        if isinstance(last_err, requests.exceptions.RequestException):
            raise last_err
        raise requests.exceptions.RequestException(str(last_err))

    def _exchange(self, method: str, params: dict = None, body: dict = None):
        """Один HTTP-обмен с Bridge: явный follow-redirect-as-GET. POST/GET на /exec идёт с
        allow_redirects=False; 3xx → GET на Location руками (не полагаемся на авто-follow
        requests, который на редиректе терял тело/токен). Возвращает финальный Response."""
        self._card_room("обмен с мостом")
        if method == "GET":
            r = self._session.get(self.url, params=params, timeout=self._leg_timeout(),
                                  allow_redirects=False)
        else:
            r = self._session.post(self.url, json=body, timeout=self._leg_timeout(),
                                   allow_redirects=False)
        cur_url, hops = self.url, 0
        while r.status_code in _REDIRECT_CODES and hops < 6:
            # ЛЕСТНИЦА 2 (хопы редиректа) под общим дедлайном карточки: шесть хопов, каждый со
            # своей лестницей эхо, — второй множитель потолка 57 плеч.
            self._card_room("хоп редиректа")
            loc = r.headers.get("Location") or r.headers.get("location")
            if not loc:
                break
            cur_url = urljoin(cur_url, loc)
            r = self._fetch_redirect_target(cur_url)
            hops += 1
        return r

    def _one_exchange(self, method: str, action: str, params: dict = None, body: dict = None) -> dict:
        """Обмен + разбор ответа в прежний контракт {ok, error, message}. Служебный флаг
        _unauthorized (токен не дошёл/отвергнут) снимается в _durable_request, наружу не уходит."""
        try:
            r = self._exchange(method, params=params, body=body)
        except CardBudgetExpired as e:
            # Наружу — ОТВЕТ, а не исключение: сборка карточки идёт дальше и досказывает то, что
            # уже прочитано, а этот источник честно помечается «не прочитан» (третий исход).
            log.warning(f"Bridge {action}: {e}")
            return {"ok": False, "error": CARD_DEADLINE_ERROR, "message": str(e)}
        except requests.exceptions.Timeout:
            said, cut = self._timeout_said()
            log.error(f"Bridge timeout (>{said}s) for action={action}{cut}")
            return {"ok": False, "error": "timeout", "message": f"Timeout >{said}s{cut}"}
        except requests.exceptions.RequestException as e:
            log.error(f"Bridge request error ({action}): {e}")
            return {"ok": False, "error": "request_failed", "message": str(e)}
        if r.status_code == 401:
            return {"ok": False, "error": "unauthorized", "message": "HTTP 401",
                    "_unauthorized": True}
        if r.status_code >= 400 or r.status_code in _REDIRECT_CODES:
            log.error(f"Bridge request error ({action}): HTTP {r.status_code}")
            return {"ok": False, "error": "request_failed",
                    "message": f"HTTP {r.status_code}"}
        try:
            data = r.json()
        except ValueError as e:
            text = str(getattr(r, "text", "") or "")
            if "invalid or missing token" in text.lower():
                return {"ok": False, "error": "unauthorized",
                        "message": "Invalid or missing token", "_unauthorized": True}
            log.error(f"Bridge JSON parse error ({action}): {e}")
            return {"ok": False, "error": "json_parse_error", "message": str(e)}
        if not isinstance(data, dict):
            return {"ok": False, "error": "json_parse_error", "message": "не-dict ответ"}
        if not data.get("ok"):
            log.warning(f"Bridge returned error: {data.get('error')} — {data.get('message')}")
            err = str(data.get("error", "")).lower()
            msg = str(data.get("message", "")).lower()
            if err == "unauthorized" or "invalid or missing token" in msg:
                data["_unauthorized"] = True
        return data

    # ОТПЕЧАТОК ПЛЕЧА РАСПИСКИ (класс 02.08.2026). Отказ по токену приходит от ДВУХ разных
    # обработчиков, и различает их ТЕЛО, а не код ответа (Apps Script код не ставит — он в теле):
    #   · doGet  (Bridge.js:28-32) → {ok:false, error:'unauthorized', message:'Invalid or missing token'}
    #   · doPost (Bridge.js:234)   → {ok:false, error:'unauthorized'}            ← message'а НЕТ
    # Расписка С message пришла от doGet: POST по цепочке 302 стал голым GET без тела, и мост
    # честно сказал «токена нет» — а плечо doPost к этому моменту УЖЕ отработало.
    _DOGET_REFUSAL_MARK = "invalid or missing token"

    def _receipt_leg(self, data: dict) -> str:
        """Какое плечо ответило отказом: 'doGet' (тело несёт message моста) | '?' (не опознано)."""
        return "doGet" if self._DOGET_REFUSAL_MARK in str(data.get("message") or "").lower() else "?"

    def _receipt_unknown(self, action: str, data: dict) -> dict:
        """Отказ расписки на write-POST: пересылки НЕТ, исход НЕИЗВЕСТЕН — читать факт.
        Наружу уходит явный контракт: ok=False, outcome='unknown' + что делать дальше."""
        leg = self._receipt_leg(data)
        hint = ("плечо расписки doGet — тело отказа несёт message моста, значит запрос ушёл "
                "по цепочке 302 голым GET'ом, а плечо doPost к тому моменту уже отработало"
                if leg == "doGet" else "плечо расписки не опознано")
        log.error(f"Bridge {action}: отказ расписки на write-POST ({hint}). Пересылки НЕТ — "
                  f"она положила бы ВТОРУЮ запись. Исход неизвестен: перечитай факт.")
        return {
            "ok": False, "error": "receipt_unknown", "outcome": "unknown",
            "bridge_error": data.get("error"), "receipt_leg": leg,
            "message": (f"write-POST «{action}»: расписка пришла отказом по токену ({hint}). "
                        f"Пересылки НЕТ — вторая отправка положила бы вторую запись. Исход "
                        f"НЕИЗВЕСТЕН: перечитай факт (статус строки / содержимое документа / "
                        f"наличие проводки), повторять запрос вслепую нельзя."),
        }

    def _durable_request(self, method: str, action: str, params: dict = None,
                         body: dict = None, retry_full: bool = False) -> dict:
        """Durable-запрос к Bridge. retry_full=True (read-only GET / идемпотентные POST) —
        до retry_attempts полных повторов на timeout/request_failed. retry_full=False
        (write-POST) — РОВНО одна отправка (дубль записи страшнее потери ответа); durability
        write-пути даёт echo-ретрай внутри _exchange.
        ОТКАЗ РАСПИСКИ (unauthorized) — по той же границе, что и транспорт-повтор.
        Прежняя посылка «Bridge проверяет токен ДО исполнения, значит запрос НЕ исполнен»
        ОПРОВЕРГНУТА замером (артефакт 2026-08-02-bridge-receipt-leg-not-token.md, отпечаток
        плеча — см. _receipt_leg выше): write_doc исполнился, а отказ пришёл вторым плечом,
        и пересылка положила бы ВТОРУЮ запись (для кассы — дубль проводки). Поэтому:
        GET и идемпотентный POST — пересылка с токеном как была (чтение/повтор безопасны);
        write-POST — пересылки НЕТ, наружу outcome='unknown' + «перечитай факт»
        (verify-паттерны вызывающего кода: _enqueue_reliable, _claim_task_verified).
        ОБЩИЙ ДЕДЛАЙН КАРТОЧКИ (13.08.2026) — ЕДИНАЯ ДВЕРЬ: любой запрос к мосту идёт через это
        место, поэтому здесь же и записывается исход (кто ответил, кто нет), и здесь же бюджет
        обрывает работу ДО сети. Обойти дверь нельзя: у `_call` и `_post` иного пути наружу нет.
        Тесты tests/test_post_receipt_no_resend.py и tests/test_info_card_deadline.py (в гейте)."""
        state = _CARD_BUDGET.get()
        if state is not None and card_deadline.expired(state.deadline, time.monotonic()):
            # Бюджет уже исчерпан — сети не касаемся ВОВСЕ. Именно это делает потолок потолком
            # ВСЕЙ карточки: оставшиеся действия не начинают своих лестниц, а честно молчат.
            state.note_deadline()
            data = {"ok": False, "error": CARD_DEADLINE_ERROR,
                    "message": (f"общий бюджет {state.label} {card_deadline._num(state.budget)} с исчерпан — "
                                f"«{action}» не запрашивался")}
            log.warning(f"Bridge {action}: {data['message']}")
            state.note(action, data)
            return data
        data = self._durable_request_impl(method, action, params=params, body=body,
                                          retry_full=retry_full)
        if state is not None:
            state.note(action, data)
        return data

    def _durable_request_impl(self, method: str, action: str, params: dict = None,
                              body: dict = None, retry_full: bool = False) -> dict:
        """Тело durable-запроса (см. `_durable_request` — там дверь бюджета и запись исхода)."""
        max_attempts = max(1, self.retry_attempts) if retry_full else 1
        auth_resend_left = 1 if retry_full else 0
        attempt = 0
        while True:
            attempt += 1
            data = self._one_exchange(method, action, params=params, body=body)
            unauthorized = bool(data.pop("_unauthorized", False))
            err = data.get("error")
            self._note_transport(failed=err in ("timeout", "request_failed"))
            if data.get("ok"):
                return data
            if unauthorized and auth_resend_left > 0 and self._card_may_wait(self.retry_base):
                auth_resend_left -= 1
                log.warning(f"Bridge {action}: unauthorized (токен потерян на редиректе?) — "
                            f"пересылаю запрос с токеном заново")
                self._backoff(0)
                continue
            if unauthorized and not retry_full:
                return self._receipt_unknown(action, data)
            if err in ("timeout", "request_failed") and attempt < max_attempts:
                # ЛЕСТНИЦА 1 (полные попытки) под общим дедлайном карточки — первый множитель
                # потолка 57 плеч: не влезает пауза + плечо → отдаём то, что есть.
                if not self._card_may_wait(self.retry_base * (2 ** (attempt - 1))):
                    log.warning(f"Bridge {action}: backoff-ретрай отменён — общий бюджет "
                                f"{self._card_label()} не вмещает его")
                    return data
                log.warning(f"Bridge {action}: {err} — backoff-ретрай "
                            f"{attempt + 1}/{max_attempts}")
                self._backoff(attempt - 1)
                continue
            return data

    def _call(self, action: str, **params) -> dict:
        """Выполняет GET запрос к Bridge (read-only → полный ретрай безопасен)."""
        query = {"token": self.token, "action": action, **params}
        log.debug(f"Bridge call: action={action} params={params}")
        return self._durable_request("GET", action, params=query, retry_full=True)

    # === Удобные методы для отдельных endpoint'ов ===

    def ping(self) -> dict:
        return self._call("ping")

    def fleet(self, cells: bool = False) -> dict:
        """Парк из Лист1 «Байки».

        cells=True — попросить у моста РАЗМЕТКУ клеток ТО: у каждого байка появится поле
        `cells`, где про каждую клетку сказано, ЧТО в ней лежало (значение / пусто / не число),
        см. `fleet_cell`. Без параметра запрос и ответ БАЙТ-В-БАЙТ прежние — поэтому все
        сегодняшние потребители (`find_bike`, `_o3_overdue_scan`, тул `get_fleet`, инварианты)
        не видят ни одного лишнего байта, а разметку получает только тот, кто её спросил.

        Старый деплой моста параметр просто игнорирует: `cells` не придёт, и `fleet_cell.read`
        честно скажет «источник не прочитан» вместо выдуманного «пусто»."""
        if cells:
            return self._call("fleet", cells=1)
        return self._call("fleet")

    @staticmethod
    def cell(bike: dict, field: str):
        """Клетка строки парка → ScanResult (исход, а не голое число). См. `fleet_cell`."""
        return fleet_cell.read(bike, field)

    def find_bike(self, query: str) -> dict:
        """Найти байк в парке по НОМЕРУ (последние 3-4 цифры названия).
        Игнорирует кубатуру (300/350/650/750/125/155) — это не номер."""
        if not query:
            return {}
        import re
        # кубатуры моторов — НЕ номера байков
        CC = {"125", "150", "155", "300", "350", "400", "500", "650", "700", "750", "900"}

        def plate(text):
            """Последнее число, не являющееся кубатурой = номерной знак байка."""
            nums = re.findall(r"\d{3,}", str(text).lower())
            nums = [n for n in nums if n not in CC]
            return nums[-1] if nums else None

        q_plate = plate(query)
        try:
            bikes = self.fleet().get("data", {}).get("bikes", [])
        except Exception:
            return {}

        # 1) точное совпадение по номеру байка — самое надёжное
        if q_plate:
            for b in bikes:
                if plate(b.get("name", "")) == q_plate:
                    return b
        # 2) запасной вариант — вхождение очищенного названия
        q = str(query).lower()
        for b in bikes:
            name = str(b.get("name", "")).lower()
            if q and (q in name or name in q):
                return b
        return {}

    def clients(self, filter: str = "active") -> dict:
        return self._call("clients", filter=filter)

    def anomalies(self) -> dict:
        return self._call("anomalies")

    def client_history(self, phone: Optional[str] = None, name: Optional[str] = None) -> dict:
        params = {}
        if phone:
            params["phone"] = phone
        if name:
            params["name"] = name
        return self._call("client_history", **params)

    def finance(self, period: str = "month") -> dict:
        return self._call("finance", period=period)

    def returns_soon(self, days: int = 3) -> dict:
        return self._call("returns_soon", days=days)

    def daily_pulse(self) -> dict:
        return self._call("daily_pulse")

    def quote_price(self, bike: str, date_start: str, date_end: str) -> Optional[dict]:
        """Read-only расчёт цены аренды через Bridge (QuotePrice.gs), ничего не пишет.
        Даты: dd.mm.yyyy | dd-mm-yyyy | yyyy-mm-dd.
        → dict {bike, model, days, day_price, total, deposit, available, conflicts,
        season, cap_price, cap_active, text} при ok; None при любой ошибке
        (таймаут/не-ok/кривой JSON) — вызывающий код не роняет.
        cap_price/cap_active — кап-акция low season из блока капов «Календаря
        бронирования» (05.07.2026); подмену цены делает userbot, не эта обёртка.
        Старый Bridge без капов этих полей не шлёт — вызывающему коду брать через .get()."""
        try:
            data = self._call("quote_price", bike=bike,
                              date_start=date_start, date_end=date_end)
            if not isinstance(data, dict) or not data.get("ok"):
                return None
            return data
        except Exception as e:
            log.error(f"quote_price wrapper error: {e}")
            return None


    # === ЧЁРНЫЙ ЯЩИК боевых записей (4.1): какие действия логируем в боевой_лог ===
    _REDZONE_ACTIONS = {
        "set_fleet_oil", "set_fleet_service",   # Байки H/I/J/K/L
        "set_caps", "toggle_cap",                # блок капов «Календарь бронирования» Z3:AB15 (живая таблица)
        "add_transaction", "void_last",          # касса (проводки + отмена)
        "create_booking", "activate_booking", "close_booking",  # CRM «клиенты»
        "delete_event",                          # удаление
        "edit_event",                            # правка строки НА МЕСТЕ (затирает прежнее значение)
        "ocr_passport", "save_passport", "upload_passport_photo",  # B2: EdenAI + Drive + Bot Data
        "make_contract",                         # B3: договор (Drive-запись + чтение CRM)
        "closing_upsert",                        # Лист закрытия (деньги-доплаты → аудит 4.1, НЕ 4.2)
        "service_upsert",                        # ТО-трекер «обслуживание» (часть пути записи ТО → аудит 4.1, НЕ 4.2)
        "trash_brain_file",                      # удаление файла в Brain (housekeeping → аудит 4.1)
        "register_brain_doc",                    # регистрация ключа в BRAIN_MANIFEST (конфиг → аудит 4.1)
        "service_delete",                        # удаление service-строки «обслуживание» (необратимо → аудит 4.1)
    }
    _BRIEF_KEYS = ("number", "bike", "amount", "currency", "kind", "oil_km", "km",
                   "row", "name", "group", "msg_id", "confirmed", "confirmed_by",
                   # правка/исправление: без этих полей в журнале останется «правил кто-то,
                   # зачем-то» — то есть след, по которому ничего не восстановить.
                   "fix_reason", "fixed_by", "new_msg_id")

    def _post(self, action: str, **fields) -> dict:
        """POST запрос к Bridge (запись данных Splinter)."""
        body = {"token": self.token, "action": action, **fields}
        # Токен-замок 4.2: помечаем origin (дефолт human). Для agent — прикладываем билет.
        origin = WRITE_ORIGIN.get()
        body["origin"] = origin
        if origin == "agent":
            tk = WRITE_TICKET.get()
            if tk:
                body["ticket"] = tk
        log.debug(f"Bridge POST: action={action}")
        # Полный re-POST — ТОЛЬКО идемпотентным (read-like) действиям; write шлётся один раз
        # (durability write-пути — echo-ретрай + verify-паттерны вызывающего кода).
        data = self._durable_request("POST", action, body=body,
                                     retry_full=action in self._IDEMPOTENT_POST_ACTIONS)
        self._blackbox_log(action, fields, data)   # 4.1: лог постфактум, НЕ блокирует
        return data

    def _blackbox_log(self, action: str, fields: dict, data: dict) -> None:
        """Чёрный ящик: атомарный appendRow в боевой_лог для красных экшенов. НИКОГДА не бросает
        (try/except) — если лог упал, боевая операция всё равно прошла. Reentrancy-guard от самолога."""
        if action not in self._REDZONE_ACTIONS:
            return
        if getattr(self, "_in_blackbox", False):
            return
        try:
            self._in_blackbox = True
            # Токен-замок 4.2: agent-запись отклонена Bridge (no_ticket) — Bridge УЖЕ залогировал
            # rejected server-side; клиент не дублирует лог, только шлёт ПУШ Филиппу (тревога).
            if data.get("error") == "no_ticket":
                self._push_blackbox(f"🔴 ОТКЛОНЕНО (токен-замок 4.2): agent-запись «{action}» без "
                                    f"валидного билета. В боевой_лог: rejected.")
                return
            initiator = str(fields.get("confirmed_by") or fields.get("sender") or "bot")
            parts = [f"{k}={fields[k]}" for k in self._BRIEF_KEYS
                     if fields.get(k) not in (None, "")]
            args = ", ".join(parts)[:480]
            result = "ok" if data.get("ok") else ("fail:" + str(data.get("error", "")))
            # логируемое действие шлём как 'act' — ключ 'action' занят маршрутизацией _post.
            self._post("log_write", initiator=initiator, act=action, args=args,
                       result=result, critical="")
        except Exception as e:
            log.warning(f"  → чёрный ящик: лог не записан ({e}) — боевая операция не затронута")
        finally:
            self._in_blackbox = False

    def log_write(self, **fields) -> dict:
        """Записать строку в боевой_лог (чёрный ящик). Обычно зовётся хуком _blackbox_log,
        но доступен и для memory-записей из claude_client."""
        return self._post("log_write", **fields)

    def read_write_log(self, limit: int = 50) -> dict:
        """Прочитать последние записи боевого лога (для проверки с сайта/Claude Code)."""
        return self._post("read_write_log", limit=limit)

    def issue_write_ticket(self) -> dict:
        """Выдать одноразовый билет (TTL ~120с) на санкционированную agent-запись (токен-замок 4.2)."""
        return self._post("issue_write_ticket")

    def consume_write_ticket(self, ticket: str) -> dict:
        """Проверить+погасить билет (для client-side гейта памяти). {ok:true/false}."""
        return self._post("consume_write_ticket", ticket=ticket or "")

    # === ОЧЕРЕДЬ ОРКЕСТРАТОРА (ступень 1, заход 1 — служебный лист, НЕ боевые данные) ===
    # lane (вторая полоса 04.07.2026): 'vps' — демон на VPS, 'pc' — агент на ПК. Во всех методах
    # lane ОПЦИОНАЛЕН: None → параметр НЕ шлётся (старый Bridge не ломается; новый дефолтит vps).
    # 'all' в get_pending = обе полосы (опрос devbot).

    def enqueue_task(self, from_: str, task_text: str, lane: str = None,
                     dedup_key: str = None, result_ref=None) -> dict:
        """Положить задачу в очередь → {ok, id}. status=new. lane: None=vps (дефолт Bridge) | 'pc'.
        result_ref (16.08.2026, пункт 1 контракта третьего исхода): АДРЕС РЕЗУЛЬТАТА шага —
        пара (вид, указатель) либо словарь того же вида, что отдаёт `result_ref.parse`. Виды —
        `result_ref.KINDS`. Форма в очереди — КАНОН обеих полос `[result_ref: <вид>
        <указатель>]` (разделитель ПРОБЕЛ: указатель вправе нести двоеточие внутри себя).
        Кладётся строкой в task_text ПЕРВЫМ действием, до fixture-guard и
        дедупа: адрес — часть СОЗДАВАЕМОГО шага, а не приписка после. None (сегодня — все
        вызовы) → ни одной новой строки не исполняется, тело запроса БАЙТ-В-БАЙТ прежнее
        (тот же приём, что у lane=None). Названный криво адрес бросает ValueError ДО сети —
        молча съеденный адрес вернул бы класс, против которого писан контракт.
        FIXTURE-GUARD (класс 193): канонические тест-заглушки в живую очередь НЕ пишутся —
        мгновенный {ok:False, fixture_guard:True} БЕЗ сети. Обход для легитимных тест-контуров
        (транспорт-тесты на фейковом URL): BRIDGE_ALLOW_FIXTURES=1 ставит сам тест.
        dedup_key (02.08.2026): ключ ПРОИСХОЖДЕНИЯ постановки — та же форма, что msg_id у
        транзакций и событий. Повтор с тем же ключом в окне НЕ шлёт вторую отправку и отдаёт
        {ok:True, id:<та же задача>, duplicate:True}. Пусто → дедупа нет, поведение прежнее
        байт-в-байт (как `if (!msgId) return false` на мосту). Разбор — блок «ДЕДУП ПОСТАНОВКИ
        ЗАДАЧИ» выше."""
        if result_ref is not None:
            _rk, _rp = _result_ref.as_pair(result_ref)
            task_text = _result_ref.attach(task_text, _rk, _rp)
        _ftxt = str(task_text or "")
        if (FIXTURE_TASK_RE.search(_ftxt) or FIXTURE_TASK_RE.search(_fixture_norm(_ftxt))) \
                and os.environ.get("BRIDGE_ALLOW_FIXTURES") != "1":
            log.warning("fixture-guard: enqueue заблокирован (тест-фикстура): %.60r", task_text)
            return {"ok": False, "fixture_guard": True,
                    "error": "fixture_guard: тест-фикстура не пишется в живую очередь "
                             "(класс 193; тестам — мок-очередь либо TEST-/BRIDGE_ALLOW_FIXTURES=1)"}
        key = str(dedup_key or "").strip()
        if key:
            prev = _dedup_lookup(key)
            if prev is not None:
                log.warning("enqueue: тот же ключ постановки (%s) — задача %s уже стоит, "
                            "вторую не создаём", key, prev)
                return {"ok": True, "id": prev, "duplicate": True, "dedup_key": key}
        kw = {"from": from_, "task_text": task_text}
        if lane is not None:
            kw["lane"] = lane
        if key:
            kw["dedup_key"] = key      # мосту на будущее; без ключа тело запроса прежнее
        r = self._post("enqueue_task", **kw)
        if key and r.get("ok") and r.get("id") is not None:
            _dedup_remember(key, r.get("id"))
        return r

    def get_pending(self, status: str = "new", lane: str = None) -> dict:
        """Задачи по статусу (деф. new), newest-first → {ok, items}. Дешёвое чтение (GET).
        lane: None → Bridge-дефолт vps; 'pc' — полоса ПК; 'all' — обе полосы."""
        kw = {"status": status}
        if lane is not None:
            kw["lane"] = lane
        return self._call("get_pending", **kw)

    def get_pending_multi(self, statuses, lane: str = None) -> dict:
        """Задачи по НЕСКОЛЬКИМ статусам ОДНИМ вызовом (status=CSV), склейка 02.07.2026 →
        {ok, items} — у каждого item есть 'status'. Новый Bridge понимает CSV и подтверждает
        полем 'statuses'; старый (до redeploy) CSV не матчит и отдаёт items=[] БЕЗ 'statuses' →
        тихий фоллбэк на по-статусные вызовы (кэшируется, CSV-проба не гоняется каждый раз).
        Ошибка склеенного вызова (timeout и пр.) → возвращаем как есть, фоллбэком Bridge
        в окно деградации НЕ добиваем."""
        statuses = [str(s).strip() for s in statuses if str(s).strip()]
        lane_kw = {} if lane is None else {"lane": lane}
        if not statuses:
            return {"ok": True, "items": []}
        if len(statuses) == 1:
            return self._call("get_pending", status=statuses[0], **lane_kw)
        if getattr(self, "_pending_multi_supported", None) is not False:
            r = self._call("get_pending", status=",".join(statuses), **lane_kw)
            if not r.get("ok"):
                return r
            if r.get("statuses"):
                self._pending_multi_supported = True
                return r
            self._pending_multi_supported = False   # старый Bridge — дальше сразу по-статусно
        items = []
        for st in statuses:
            rr = self._call("get_pending", status=st, **lane_kw)
            if not rr.get("ok"):
                return rr
            for it in rr.get("items", []):
                if isinstance(it, dict):
                    it.setdefault("status", st)
                items.append(it)
        return {"ok": True, "items": items}

    def claim_task(self, task_id, lane: str = None) -> dict:
        """Атомарно new→in_progress → {ok, task} | {ok:false, error:'already_claimed'/'wrong_lane'/...}.
        lane (опц. guard): новый Bridge не отдаст задачу чужой полосы даже по прямому id."""
        kw = {"id": task_id}
        if lane is not None:
            kw["lane"] = lane
        return self._post("claim_task", **kw)

    def complete_task(self, task_id, status: str, result: str = "") -> dict:
        """Финал задачи: status='done'|'failed' + result → {ok}."""
        return self._post("complete_task", id=task_id, status=status, result=result)

    def task_heartbeat(self, task_id) -> dict:
        """Heartbeat задачи in_progress: бьёт updated=now (только если ещё in_progress) → {ok}.
        Бьётся фоновым потоком демона, пока claude -p блокирующе исполняется (детект зависания)."""
        return self._post("task_heartbeat", id=task_id)

    def set_needs_approval(self, task_id, what: str) -> dict:
        """Задача упёрлась в красную зону: status=needs_approval + result=<что собирается> → {ok}."""
        return self._post("set_needs_approval", id=task_id, what=what)

    def approve_task(self, task_id, approved_by: str) -> dict:
        """Филипп дал «да»: needs_approval→approved + approved_by → {ok}."""
        return self._post("approve_task", id=task_id, approved_by=approved_by)

    def _push_blackbox(self, text: str) -> None:
        """Пуш Филиппу о событии чёрного ящика (отклонение токен-замка). Best-effort, не бросает."""
        try:
            import notify
            notify.notify(text)
        except Exception:
            pass

    # === Запись (Splinter) ===

    def add_transaction(self, **fields) -> dict:
        """Записать приход/расход. Поля: msg_date, group, sender, amount,
        currency, category, bike, deposit, description, raw, msg_id,
        booking_id (опционально, col N — привязка к брони; старый Bridge молча игнорирует)."""
        return self._post("add_transaction", **fields)

    def add_event(self, **fields) -> dict:
        """Записать событие по байку. Поля: msg_date, group, bike, event_type,
        fuel, mileage, photos, notes, msg_id.

        КЛЮЧ СООБЩЕНИЯ ОБЯЗАТЕЛЕН (02.08.2026, класс «строка без свидетеля»; форма — от
        постановки задачи, 667d314). Сверка ключа на мосту при ПУСТОМ ключе возвращает ложь
        (`botMsgExists_`: `if (!msgId) return false`, BotData.js:449-450), поэтому запись без
        ключа ложится в лист СРАЗУ БЕЗ ДВУХ ВЕЩЕЙ: без защиты от дубля (вторая такая же строка
        ляжет рядом) и без СВИДЕТЕЛЯ (две одинаковые строки потом не отличить от двух настоящих
        событий — ровно этим неразрешим остался случай из разбора дублей 02.08, §5 артефакта).
        Такую строку нельзя ни сверить, ни отозвать: `delete_event` тоже работает ТОЛЬКО по
        точному ключу и без него отказывает (BotData.js:549) — здесь тот же принцип ставится
        на вход, а не только на удаление.

        РАЗНИЦА С ПОСТАНОВКОЙ НАМЕРЕННАЯ. У `enqueue_task` пустой ключ = «дедупа нет, поведение
        прежнее» (fail-open: потерять задачу владельца хуже, чем продублировать). Здесь наоборот,
        fail-closed: анонимная строка в живом листе хуже ненаписанной, потому что она НЕОБРАТИМА
        по ключу и навсегда портит сверку. Отказ при этом НЕ МОЛЧАЛИВЫЙ — суть события уходит в
        журнал: «не прошло» обязано быть отличимо от «прошло», иначе событие теряется бесследно.

        ЗАКОННАЯ АВТОМАТИКА НЕ СЛОМАНА. Записи не от сообщения владельца в проде уже есть, и все
        они несут СИНТЕТИЧЕСКИЙ КОНТЕНТНЫЙ ключ: `info:<номер>:<работа>:<км>` (splinter:2062),
        `odo_audit:<чат>:<тема>:<км>` (splinter:2849), `sp:<чат>:<тема>:<вид>:<км>` (splinter:5861).
        Это и есть замена свидетеля для автоматики: ключ строится из СОДЕРЖАНИЯ события, повтор
        того же факта даёт тот же ключ и схлопывается мостом. Новому автоматическому писателю
        брать эту же форму, а не пустоту.

        ЧЕСТНЫЙ ПРЕДЕЛ: проверка КЛИЕНТСКАЯ. Сам мост пустой ключ по-прежнему примет (`p.msg_id
        || ''` → appendRow), так что зеркало `if (!msgId) return {ok:false,error:'no_msg_id'}` в
        `addEvent` — отдельная правка Apps Script (красная зона, деплой владельцем). Сегодня это
        закрывает вход полностью: живой писатель событий один — splinter."""
        key = str(fields.get("msg_id") or "").strip()
        if not key:
            # СВИДЕТЕЛЬ: называем суть события, чтобы потерянное можно было восстановить руками.
            log.error("событие БЕЗ ключа сообщения НЕ пишется (нет ни защиты от дубля, ни "
                      "свидетеля): group=%r bike=%r event_type=%r mileage=%r notes=%.120r",
                      fields.get("group"), fields.get("bike"), fields.get("event_type"),
                      fields.get("mileage"), fields.get("notes"))
            return {"ok": False, "error": "no_msg_id",
                    "message": "ключ сообщения обязателен: без него строка события не сверяется "
                               "и не отзывается (автоматике — синтетический ключ вида "
                               "info:/odo_audit:/sp:, см. splinter)"}
        return self._post("add_event", **fields)

    def delete_event(self, msg_id: str = "", group: str = "", max: int = 50) -> dict:
        """Удалить строки листа «события» ТОЛЬКО по точному ключу (msg_id и/или group).
        Защита на стороне Bridge: без ключа / широкий фильтр / больше лимита → отказ.
        Возвращает {ok, deleted, rows:[...]} — сверять по return/логу, НЕ по кэш-экспорту."""
        return self._post("delete_event", msg_id=msg_id, group=group, max=max)

    def read_events(self, bike: str, limit: int = 8) -> dict:
        """Последние обслуживания байка из листа «события» (read-only, сервис-на-пробеге для карточки).
        Резолв по номеру, newest-first. → {ok, bike, items:[{recorded_at,msg_date,event_type,mileage,notes}]}."""
        return self._call("read_events", bike=bike, limit=limit)

    def check_balance(self, currency: str, pym_balance, group: str = "", note: str = "") -> dict:
        """Сверить баланс кошелька (group) с названным Пымом."""
        return self._post("check_balance", currency=currency,
                           pym_balance=pym_balance, group=group, note=note)

    def get_balance(self, group: str = "") -> dict:
        """Баланс кошелька (group) или всех кошельков если group пустой."""
        return self._post("get_balance", group=group)

    def tx_summary(self, period: str = "today") -> dict:
        return self._post("tx_summary", period=period)

    def void_last(self, group: str = "") -> dict:
        """Отменить последнюю активную запись (группы group, если задана)."""
        return self._post("void_last", group=group)

    # === Мозг (Brain): синк git → Drive ===
    def write_doc(self, text: str, name: Optional[str] = None, id: Optional[str] = None) -> dict:
        """Перезаписать тело Google Doc «мозга» (KB_*) новым текстом — синк git→Drive.
        Указывать name (логическое имя из BRAIN_MANIFEST, напр. 'park_list') ИЛИ id (doc id).
        Только перезапись существующего дока; doc_id и манифест не меняются.
        Пустой text запрещён на стороне Bridge (защита от затирки)."""
        fields = {"text": text}
        if name:
            fields["name"] = name
        if id:
            fields["id"] = id
        return self._post("write_doc", **fields)

    # === Бронирование (предв.бронь → активация после выдачи) ===
    def create_booking(self, **fields) -> dict:
        """Поставить предварительную бронь (статус 'Бронь' в листе 'клиенты').
        Поля: bike, name (обяз.); date_start, date_end, pay_day, pay_month,
        deposit (число или 'passport'), helmets, contacts, note, initial_pay, km.
        Долг по брони НЕ начисляется, пока не вызван activate_booking."""
        return self._post("create_booking", **fields)

    def activate_booking(self, bike: str, name: str, date_start: Optional[str] = None) -> dict:
        """Активировать бронь: 'Бронь' → 'В аренде'. Вызывать после фото выдачи (этап 6).
        С этого момента формулы долга/оплаты начинают считать.
        date_start (опц., O3-2a) — уточнение при двух бронях одного клиента на один байк
        (матч по дню; без даты — прежнее поведение: первая подходящая)."""
        if date_start:
            return self._post("activate_booking", bike=bike, name=name, date_start=date_start)
        return self._post("activate_booking", bike=bike, name=name)

    def close_booking(self, bike: str, name: str, date_start: Optional[str] = None,
                      km_end=None, paid_total=None) -> dict:
        """Закрыть аренду: 'В аренде' → 'Завершена' (O3-3b, возврат байка).
        date_start (опц.) — уточнение строки по дню при двух арендах bike+name;
        km_end (опц.) — пробег на сдаче (→ N; Bridge отклонит odometer_back, если
        меньше текущего Q); paid_total (опц.) — итог оплаты (→ K; без него K не трогается).
        Опциональные поля шлются только при наличии (обратная совместимость)."""
        fields = {"bike": bike, "name": name}
        if date_start:
            fields["date_start"] = date_start
        if km_end is not None:
            fields["km_end"] = km_end
        if paid_total is not None:
            fields["paid_total"] = paid_total
        return self._post("close_booking", **fields)

    # === Паспорт (этап B2): OCR через EdenAI + хранение в Bot Data «паспорта». КРАСНАЯ зона. ===
    def upload_passport_photo(self, image_b64: str, filename: str = "passport", mime: str = "image/jpeg") -> dict:
        """Залить фото паспорта (base64) в папку Drive «Паспорта» → {ok, file_id, url}."""
        return self._post("upload_passport_photo", image_b64=image_b64, filename=filename, mime=mime)

    def ocr_passport(self, file_id: str = None, image_b64: str = None) -> dict:
        """Распознать паспорт через EdenAI (provider microsoft). Передать file_id (Drive) ИЛИ image_b64.
        Страны как EdenAI. → {ok, fields:{...}} | {ok:false, error:'no_api_key'/'ocr_failed'/'edenai_error'}."""
        fields = {}
        if file_id:
            fields["file_id"] = file_id
        if image_b64:
            fields["image_b64"] = image_b64
        return self._post("ocr_passport", **fields)

    def save_passport(self, **fields) -> dict:
        """Сохранить/обновить строку в листе «паспорта» (upsert по booking_key). Поля: booking_key
        (или bike+name+date_start), bike, name, drive_file_id, last_name, given_names, full_name,
        document_id, nationality, country, birth_date, expire_date, ocr_status."""
        return self._post("save_passport", **fields)

    # === Договор (этап B3): шаблон → replaceText → папка договоров. КРАСНАЯ зона (Drive + чтение CRM). ===
    def make_contract(self, booking_id: str = None, booking_key: str = None, bike: str = None,
                      name: str = None, date_start: str = None) -> dict:
        """Сгенерировать/перегенерировать договор (один живой Doc на бронь). Ключ: booking_id (кол.Y,
        предпочтительно) ЛИБО booking_key/name+date_start (фоллбэк). → {ok, file_id, url, regenerated}."""
        fields = {}
        if booking_id:
            fields["booking_id"] = booking_id
        if booking_key:
            fields["booking_key"] = booking_key
        if bike:
            fields["bike"] = bike
        if name:
            fields["name"] = name
        if date_start:
            fields["date_start"] = date_start
        return self._post("make_contract", **fields)

    # === Лист закрытия (расчёт доплат перед закрытием; Bot Data, НЕ CRM; аудит 4.1) ===
    def closing_upsert(self, **fields) -> dict:
        """Создать/обновить строку закрытия (merge; total_due пересчитывается). Поля: booking_id (или
        bike), name, date_return, fuel_level, surcharge_days, surcharge_fuel, damage, other,
        deposit_action, status, note. → {ok, row, total_due}."""
        return self._post("closing_upsert", **fields)

    def closing_get(self, booking_id: str = None, bike: str = None) -> dict:
        """Строка закрытия по booking_id или bike. → {ok, item} | {ok:false, error:'not_found'}."""
        f = {}
        if booking_id:
            f["booking_id"] = booking_id
        if bike:
            f["bike"] = bike
        return self._post("closing_get", **f)

    def closing_list(self, status: str = None) -> dict:
        """Список закрытий (фильтр по status, опц.). → {ok, items}."""
        return self._post("closing_list", **({"status": status} if status else {}))

    # === ТО-трекер ===
    def service_upsert(self, **fields) -> dict:
        """Обновить/создать запись ТО байка. None-поля не шлём (чтобы не затирать существующие)."""
        clean = {k: v for k, v in fields.items() if v is not None}
        return self._post("service_upsert", **clean)

    def service_list(self) -> dict:
        """Все записи ТО + те что требуют внимания (due/overdue)."""
        return self._post("service_list")

    def service_set_pin(self, **fields) -> dict:
        """Записать pinned_msg_id / last_reminded_at для записи ТО."""
        return self._post("service_set_pin", **fields)

    def service_delete(self, bike, service_type, updated_at) -> dict:
        """Удалить ОДНУ строку «обслуживание» по якорю (bike+type+updated_at). Необратимо.
        not_found если 0, ambiguous (без удаления) если >1, удаляет только при ровно 1 матче."""
        return self._post("service_delete", bike=str(bike),
                          service_type=str(service_type), updated_at=str(updated_at))

    # === ТО-заявки (двухфазный сервис, Bot Data «то_заявки» — своя таблица, НЕ redzone) ===
    def service_pending_upsert(self, **fields) -> dict:
        """Создать/обновить открытую заявку ТО (merge). None-поля не шлём."""
        clean = {k: v for k, v in fields.items() if v is not None}
        return self._post("service_pending_upsert", **clean)

    def service_pending_get(self, chat_id, topic_id, bike) -> dict:
        """Открытая заявка по chat_id+topic_id+bike, или {ok:false, error:'not_found'}."""
        return self._post("service_pending_get", chat_id=chat_id, topic_id=topic_id, bike=bike)

    def service_pending_list(self, **fields) -> dict:
        """Список заявок: status / open=true / older_than_min (для висяка)."""
        return self._post("service_pending_list", **fields)

    def service_pending_close(self, **fields) -> dict:
        """Закрыть заявку (status='закрыто')."""
        return self._post("service_pending_close", **fields)

    # === Состояние байка (Этап 1 трекинга — bot-owned слой «состояние_байка», НЕ CRM/Лист1) ===
    def state_set(self, **fields) -> dict:
        """Upsert состояния байка по bike (точное название = ключ). Переданные поля
        перезаписывают, остальные сохраняются. status ∈ {в аренде/к возврату/дома/офис/ремонт}
        (валидируется на Bridge). Поля: bike(обяз.), status, location, booking_id, client,
        date_out, date_due, date_back, service_name, last_event_msg_id."""
        return self._post("state_set", **fields)

    def state_get(self, bike: str) -> dict:
        """Состояние одного байка по точному названию. → {ok, item} | {ok:false, error:'not_found'}."""
        return self._post("state_get", bike=bike)

    def state_list(self) -> dict:
        """Срез состояния всего парка (кто где сейчас). → {ok, items, total}."""
        return self._post("state_list")

    def trash_brain_file(self, id) -> dict:
        """Удалить (в корзину) файл ВНУТРИ Brain-папки по id. not_in_brain если файл вне Brain."""
        return self._post("trash_brain_file", id=str(id))

    def move_brain_file(self, id, folder: str = "_archive") -> dict:
        """Переместить файл из Brain-папки в подпапку (по умолч. _archive). Обратимо (файл цел).
        not_in_brain если файл не лежит прямо в Brain-папке."""
        return self._post("move_brain_file", id=str(id), folder=str(folder))

    def register_brain_doc(self, name, id, overwrite: bool = False) -> dict:
        """Зарегистрировать Brain-файл в BRAIN_MANIFEST (ключ name→id, мерж). Существующий ключ
        не меняется без overwrite=True. Файл должен быть в Brain-папке."""
        return self._post("register_brain_doc", name=str(name), id=str(id), overwrite=bool(overwrite))

    def create_brain_plain(self, name, key: str = "", text: str = "") -> dict:
        """Создать НОВЫЙ plain-text файл в папке Brain и (опц.) зарегистрировать ключ манифеста.
        → {ok, name, key, id, chars}. Маршрут прода @79 (`createBrainPlain_`), деплой не нужен.

        Заводить новый узел мозга — шаг РЕДКИЙ и осознанный (правило гигиены: штаб не плодит
        файлы россыпью). Он законен там, где у документа СВОЁ свойство, несовместимое с
        существующими: слепок состояния очереди (`queue_state`) ЗАМЕНЯЕТСЯ целиком, а журналы
        только копятся. Обратимо: `unregister_brain_doc` + `trash_brain_file`."""
        fields = {"name": str(name), "text": str(text)}
        if key:
            fields["key"] = str(key)
        return self._post("create_brain_plain", **fields)

    def set_fleet_oil(self, number, oil_km, confirmed: bool = False,
                      fix_reason: str = "", fixed_by: str = "", trusted: bool = False) -> dict:
        """GUARDED: записать «ТО Oil» (Лист1 Байки, колонка I) по НОМЕРУ байка.
        Резолв только по номеру (last 3-4 цифры, как find_bike). Пишет одну ячейку (col I).
        Требует confirmed=True. Откат (новое<старого) и неоднозначный номер — отказ без записи.
        Ошибки: missing_number / bad_oil_km / not_confirmed / not_found / ambiguous /
        oil_decreasing / write_failed.

        ВЕТКА «ИСПРАВЛЕНИЕ ОШИБКИ» (04.08.2026). Сторож `oil_decreasing` на ОБЫЧНОМ пути
        остаётся: одометр не убывает, молчаливое понижение почти всегда ошибка распознавания.
        Но у ошибки, УЖЕ ЛЕЖАЩЕЙ в живой таблице, штатного лечения не было вовсе — оставалась
        ручная правка ячейки, а владелец рулит с телефона. Ветку открывает ТОЛЬКО ПАРА
        `fix_reason` + `fixed_by`: полумера ветку не открывает (иначе признак исправления
        заводился бы сам собой), и клиент такую полумеру на мост даже не шлёт — `fix_incomplete`.

        `trusted=True` — «понижение подтвердил Пым или владелец». Нужен, когда понижение БОЛЬШЕ
        500 км (правило владельца; порог зеркалит `_SOFT_ODO_THRESHOLD` в splinter). Ставить его
        имеет право только код, который РЕАЛЬНО проверил, кто подтвердил: сам по себе признак —
        второй рубеж, а не первый.

        Успех исправления несёт `correction:{reason,by,drop,trusted}`, `rollback_oil` (число, к
        которому вернёт откат тем же вызовом) и `audit_logged`. След в боевом журнале у этой
        ветки FAIL-CLOSED: журнал не записался → мост ОТКАТЫВАЕТ запись (`audit_failed`), потому
        что исправление без следа в живой таблице неотличимо от порчи данных."""
        fix_reason = str(fix_reason or "").strip()
        fixed_by = str(fixed_by or "").strip()
        if bool(fix_reason) != bool(fixed_by):
            log.error("исправление пробега БЕЗ полной пары «причина+автор» не шлётся: "
                      "number=%r oil_km=%r fix_reason=%r fixed_by=%r",
                      number, oil_km, fix_reason, fixed_by)
            return {"ok": False, "error": "fix_incomplete",
                    "message": "исправление требует И причину, И автора — иначе это обычная "
                               "запись, и понижение упрётся в сторож oil_decreasing"}
        extra = {}
        if fix_reason:
            extra["fix_reason"] = fix_reason
            extra["fixed_by"] = fixed_by
            if trusted:
                extra["trusted"] = True
        return self._post("set_fleet_oil", number=str(number),
                          oil_km=oil_km, confirmed=bool(confirmed), **extra)

    #: поля строки «события», которые правка имеет право менять (зеркало EVENT_FIX_FIELDS моста).
    #: recorded_at и msg_id сюда НЕ входят: метка времени записи не правится вовсе, ключ — через
    #: new_msg_id (явно и с проверкой на конфликт).
    EVENT_FIX_FIELDS = ("msg_date", "group", "bike", "event_type", "fuel",
                        "mileage", "photos", "notes", "status", "sender")

    def edit_event(self, msg_id: str = "", fields: dict = None, new_msg_id: str = "",
                   reason: str = "", fixed_by: str = "", group: str = "") -> dict:
        """Править строку листа «события» НА МЕСТЕ — БЕЗ удаления и пересоздания.

        ЗАЧЕМ. Починка «удалить + добавить заново» теряет `recorded_at` (метку времени ЗАПИСИ):
        новая строка встаёт с новым временем и уезжает в конец листа — история перестаёт быть
        историей. Правка меняет СОДЕРЖИМОЕ, не момент записи; кол.A мост не пишет ни одной
        веткой, поэтому сохранность метки доказывается устройством, а не аккуратностью вызова.

        КЛЮЧ ПРИВОДИТСЯ К СОДЕРЖИМОМУ. У автоматики ключ синтетический и КОНТЕНТНЫЙ
        (`info:<номер>:<работа>:<км>` и т.п., см. add_event). Поправить число и оставить прежний
        ключ — значит оставить дедуп сверять строку по отпечатку, которого в ней уже нет:
        правильная запись легла бы ВТОРОЙ строкой, а ошибочный отпечаток продолжал бы гасить
        повторы. Поэтому `new_msg_id` — часть той же операции; мост проверяет, что новый ключ не
        занят чужой строкой (`key_conflict`).

        ФЕЙЛ-КЛОУЗД ВХОД — как у `add_event`: без ключа, без причины, без автора запрос на мост
        НЕ УХОДИТ ВОВСЕ. Анонимная правка живой строки хуже ненаписанной: её нельзя ни сверить,
        ни отозвать, а прежнее значение она уже стёрла. Причина и автор — это и есть аудит-след
        («что было, что стало, кто исправил»), мост кладёт его В САМУ СТРОКУ (notes/status) и
        строкой в боевой журнал.

        Ключ строки берётся из `read_events` (с 04.08 отдаёт `msg_id`/`group`/`status`).
        Успех несёт `before`/`after`, `audit` и ГОТОВЫЙ `rollback` — обратный вызов той же
        операции. Ошибки: no_key / no_reason / no_author / not_confirmed / bad_field /
        nothing_to_change / not_found / ambiguous / key_conflict / verify_failed / write_failed.
        """
        key = str(msg_id or "").strip()
        reason = str(reason or "").strip()
        author = str(fixed_by or "").strip()
        new_key = str(new_msg_id or "").strip()
        payload_fields = dict(fields or {})

        def _refuse(err: str, msg: str) -> dict:
            log.error("правка строки события НЕ отправлена (%s): msg_id=%r fields=%r "
                      "new_msg_id=%r reason=%r fixed_by=%r",
                      err, key, payload_fields, new_key, reason, author)
            return {"ok": False, "error": err, "message": msg}

        if not key:
            return _refuse("no_key", "нужен точный ключ правимой строки (msg_id из read_events): "
                                     "без него правка не сверяется и не отзывается")
        if not reason:
            return _refuse("no_reason", "правка без НАЗВАННОЙ причины не принимается — причина "
                                        "и есть половина аудит-следа")
        if not author:
            return _refuse("no_author", "правка без автора не принимается — «кто исправил» "
                                        "обязательная часть следа")
        if not payload_fields and not new_key:
            return _refuse("nothing_to_change", "не названо ни одно поле и не задан новый ключ")
        bad = [f for f in payload_fields if f not in self.EVENT_FIX_FIELDS]
        if bad:
            return _refuse("bad_field", f"править можно только {', '.join(self.EVENT_FIX_FIELDS)}; "
                                        f"метка времени записи не правится вовсе, ключ — через "
                                        f"new_msg_id (лишние: {', '.join(bad)})")

        body = {"msg_id": key, "fields": payload_fields, "reason": reason,
                "fixed_by": author, "confirmed": True}
        if new_key:
            body["new_msg_id"] = new_key
        if str(group or "").strip():
            body["group"] = str(group).strip()
        return self._post("edit_event", **body)

    def set_fleet_service(self, number, kind, km, confirmed: bool = False) -> dict:
        """GUARDED: записать регламент ТО группы B в Лист1 Байки по НОМЕРУ:
        kind='gear'→кол.J, 'abs'→кол.K, 'airfilter'→кол.L. Зеркало set_fleet_oil; кол.I (масло) и H
        НЕ трогает. Требует confirmed=True. Ошибки: missing_number / bad_kind / bad_km / not_confirmed /
        not_found / ambiguous / km_decreasing / write_failed."""
        return self._post("set_fleet_service", number=str(number), kind=str(kind),
                          km=km, confirmed=bool(confirmed))

    def service_undo(self, act, by: str = "", confirmed: bool = False) -> dict:
        """GUARDED: отменить ПОСЛЕДНЮЮ запись регистра ТО по ССЫЛКЕ НА АКТ (ServiceUndo.js
        serviceUndo_, маршрут Bridge.js:465, в проде с @83 от 23.08.2026).

        ЧИСЛА СНАРУЖИ ДВЕРЬ НЕ ПРИНИМАЕТ ВОВСЕ — это её главный замок: прежнее значение мост
        достаёт из СВОЕЙ строки боевого журнала, написанной в момент вытеснения, и возвращает
        только если в клетке ДО СИХ ПОР ровно то число, которое записал названный акт. Поэтому
        отмена отличима от скрутки, а `act` — единственный адрес операции. Ключ акта отдаёт
        расписка любой записи регистра (`act`/`act_logged`), читает её `undo_last.position`,
        а тело этого вызова собирает `undo_last.request` из ответа владельца.

        Требует confirmed=True (без него — not_confirmed, ни одной записи). Возвращаются ОБЕ
        базы: живой Лист1 и зеркало «обслуживание»; вторая не вернулась → отказ ЦЕЛИКОМ с
        компенсацией первой. Ошибки: need_act / not_confirmed / journal_unavailable /
        act_not_found / undo_of_undo / raw_not_restorable / already_undone / not_last /
        not_found / ambiguous / cell_changed / write_failed / verify_failed / mirror_changed /
        mirror_failed / mirror_unavailable / undo_audit_failed / undo_failed."""
        return self._post("service_undo", act=str(act), by=str(by or ""),
                          confirmed=bool(confirmed))

    def set_caps(self, caps, confirmed: bool = False) -> dict:
        """GUARDED: записать блок капов в «Календарь бронирования» (QuotePrice.js setCaps, адрес
        CAPS_ANCHOR Z3:AB15). caps = [{model, cap, active}, ...]. Требует confirmed=True.
        Ответ проводится наверх БЕЗ потери: при пост-записи-верификации Bridge возвращает
        verified/full_address (успех) либо ok:false + error='verify_failed' + full_address
        (запись не подтвердилась чтением обратно). Ошибки: not_confirmed / missing_caps /
        too_many_caps / bad_cap_row / verify_failed / write_failed."""
        return self._post("set_caps", caps=caps, confirmed=bool(confirmed))

    def toggle_cap(self, model, on, confirmed: bool = False) -> dict:
        """GUARDED: включить/выключить кап одной модели (QuotePrice.js toggleCap). Требует
        confirmed=True. Ответ (verified/full_address/verify_failed) проводится наверх без потери.
        Ошибки: not_confirmed / missing_model / bad_on / no_cap_block / model_not_found /
        verify_failed / write_failed."""
        return self._post("toggle_cap", model=str(model), on=on, confirmed=bool(confirmed))

    # === Архивация журнала cc_log (Archive.gs на Bridge) ===
    def prune_cc_log(self) -> dict:
        """Разовый прогон автопрореживания cc_log на стороне Bridge: если cc_log > порога
        (Script Property CCLOG_MAX_BYTES, дефолт 50000) — старые записи уходят в архив
        KB_claude_code_log_archive. Идемпотентно (no-op если уже компактный). Читает/пишет
        доки локально в Apps Script. Регулярно вызывается time-trigger (см. setupPruneTrigger)."""
        return self._post("prune_cc_log")

    def prune_review(self, keep_headers: list) -> dict:
        """Разовое прореживание KB_review на стороне Bridge: записи, чья первая строка ∈ keep_headers,
        остаются; остальные (закрытые/задеплоенные) → KB_claude_review_archive (бутстрап + ключ
        review_archive в манифесте). Делёж локальный (DocumentApp), без HTTP-флапа. Гард: если хоть
        один keep_header не найден — НИЧЕГО не пишет (отказ). Зона: только Brain-доки review/архив."""
        return self._post("prune_review", keep_headers=keep_headers)

    def prune_review_size(self) -> dict:
        """Разовый прогон БАЙТОВОГО автопрореживания KB_review (зеркало prune_cc_log): если review
        > REVIEW_MAX_BYTES — новейшие записи остаются, старые → KB_claude_review_archive. Идемпотентно."""
        return self._post("prune_review_size")

    def setup_review_prune_trigger(self) -> dict:
        """Установить ежедневный триггер автопрореживания KB_review по размеру (~13:10 UTC).
        Засевает REVIEW_MAX_BYTES (дефолт 50000) и регистрирует review_archive в манифесте."""
        return self._post("setup_review_prune_trigger")

    def setup_prune_trigger(self) -> dict:
        """Установить ежедневный time-trigger прореживания. ПРИМ.: требует scope script.scriptapp —
        из веб-аппа НЕ проходит; запускать setupPruneTrigger() ИЗ РЕДАКТОРА Apps Script (как setupBrain)."""
        return self._post("setup_prune_trigger")

    # === Надзиратель важного ===
    def important_add(self, **fields) -> dict:
        """Добавить важный пункт (ДТП, ремонт, просрочка). Статус open."""
        return self._post("important_add", **fields)

    def important_list(self, status: str = "") -> dict:
        """Список важного. status='open'/'done' или пусто (все)."""
        return self._post("important_list", status=status)

    def important_due(self, days: int = 3) -> dict:
        """Открытые пункты, которым пора напомнить (прошло >= days дней)."""
        return self._post("important_due", days=days)

    def important_touch(self, row: int, pinned_msg_id=None) -> dict:
        """Отметить что напомнили (обновить дату, опц. новый msg_id закрепа)."""
        return self._post("important_touch", row=row, pinned_msg_id=pinned_msg_id)

    def important_close(self, row: int, confirmed_by: str = "") -> dict:
        """Закрыть важный пункт (выполнено)."""
        return self._post("important_close", row=row, confirmed_by=confirmed_by)

    # === Аудитор ===
    def audit_log(self, **fields) -> dict:
        """Записать действие бота + вердикт надзора в журнал аудита."""
        return self._post("audit_log", **fields)

    def audit_list(self, verdict: str = "", status: str = "", since: str = "") -> dict:
        """Список записей аудита (фильтры опц)."""
        return self._post("audit_list", verdict=verdict, status=status, since=since)

    def audit_update(self, row: int, status: str = "") -> dict:
        """Обновить статус записи аудита."""
        return self._post("audit_update", row=row, status=status)

    # === Зоны доставки ===

    def delivery_zones_get(self) -> dict:
        """Read-only: зоны доставки + конфиг из листа «Доставка» книги Календарь бронирования."""
        return self._call("delivery_zones_get")

    def delivery_zones_init(self) -> dict:
        """Одноразовый init листа «Доставка» (идемпотентен — лист уже есть → отказ без перезаписи).
        Красная зона: пишет в книгу Календарь бронирования — только для владельца."""
        return self._post("delivery_zones_init")


# === Тест запуск ===
if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    client = BridgeClient()

    print("=== PING ===")
    print(json.dumps(client.ping(), indent=2, ensure_ascii=False))

    print("\n=== DAILY PULSE (summary) ===")
    pulse = client.daily_pulse()
    if pulse.get("ok"):
        s = pulse["data"]["summary"]
        print(f"  Активные аренды: {s['active_rentals']}")
        print(f"  Просрочки:       {s['overdue_returns']}")
        print(f"  Общий долг:      {s['total_debt']:,.0f} ฿")
        print(f"  Дома:            {s['bikes_home']}")
        print(f"  В аренде:        {s['bikes_rented']}")
        print(f"  Аномалий:        {pulse['data']['anomalies_count']}")
    else:
        print("ERROR:", pulse)
