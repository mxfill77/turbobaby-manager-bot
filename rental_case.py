# -*- coding: utf-8 -*-
"""rental_case.py — хранилище дела аренды К4 (TB-FILIPP-K4-CASE-FOUNDATION-0910): ЕДИНСТВЕННЫЙ писатель таблиц rc_*.

Источник истины — out/CONTRACT_K4.md: §1 (исходы, типы), §2 (схема SQLite версии 1), §4 (состояния и переходы), §5
(публичные функции Store), §7 (инварианты I1–I46), §8 (события, тождество факта, факт для агента, состав дела), §10
(параметры), §11 (ключи idem_key), §12 (причины и недостающее). Чистые правила — rental_case_rules.py (их решения Store
исполняет внутри своей транзакции записи). Адреса `файл:строка` — в кандидате f2f7295; выводы по коду, не по живому
состоянию.

Как устроено (коротко):
  * Создание — только Store.create(path): абсолютный путь, BEGIN IMMEDIATE, каждый CREATE отдельным execute, rc_meta.
    Открытие — только существующего файла URI-путём `mode=rw` (`ro` у readonly): нет файла, относительный путь, чужая
    или иная схема, порча, quick_check ≠ ok, SQLite < 3.9, synchronous ≠ FULL → StoreUnavailable (I19, I33).
  * Соединение — одно на поток (threading.local). Мутация — одна транзакция BEGIN IMMEDIATE; idem_key + payload_sha
    проверяются первыми (duplicate / conflict(idem_payload_mismatch)); все предусловия считаются внутри той же
    транзакции на том же соединении (I31); любое исключение → ROLLBACK (I6); занятость дольше busy_timeout_s →
    unknown(store_busy, missing=["retry"]) без записей (I33, I43). Каждое изменение rc_* — событие rc_event той же
    транзакции: главное с idem_key вызова, подсобытия `<ключ>#<n>` (I5, §8.1).
  * Часы (`clock`) и источник id (`new_id`) инжектируются; сети, окружения и конфигов здесь нет (I20). Изменяемых
    глобалей нет: всё несущее — в файле базы (К4-C12).
  * Покрытие периода документом (I46, TB-K4-DOCUMENT-COVERAGE-0910) пишет ТОЛЬКО confirm_document_coverage
    (human_confirmed: одобряющий, явные даты, источник дат, id действия); record_document покрытия не пишет никогда.
  * Версия внешнего источника в деле не хранится и не выдаётся (§8.4 «Основания версии», F2 К3): case_ver — версия
    дела, read_at/observed_at — время НАШИХ чтений, хеши — отпечатки наших аргументов/файлов.

Названные отступления (сверх таблиц контракта, ничего в них не ослабляя):
  * Типы событий сверх §8.1 — у мутаций, которым §8.1 не назвал главного события, и у справочных подсобытий; все
    несут case_id или exp_id: attention_set, link_decided, rental_read, rental_reconciled, facts_refreshed,
    readback_absent, readback_unknown.
  * bump_version не отзывает readback, чьё исполнение уже захвачено (in_flight/waiting/flight_unknown): внешний шаг
    мог случиться, и on_readback обязан его принять (I40; §4.5 строка «cancelled → cancelled … on_readback(landed)»).
  * Ответ (on_staff_answer/on_approval_reply) с уже записанным (chat, msg_id) — duplicate по естественному ключу (§4.7
    п.3) даже при ином хеше аргументов повтора; у duplicate data.decision = None, execute = False.
  * Блокер обязательства несёт сверх {what, id, why} ещё kind и role (видно, что держит закрытие).
  * open_case строки без booking_id и без якоря (имя-заглушка, I-18) — unknown(link_missing, missing=["booking_id"]),
    кроме одобряющего (bound_by=human): дело, которое resolve не найдёт ничем, не рождается молча.
  * Сирота (§4.7 п.2): чат ожидания flight_unknown/escalation_unknown — его chat, чаты его постов и чаты постов его
    мест; если хранилище не знает ни одного (пост не дошёл, места ещё не видело) — реплай боту хранится сиротой
    (I40: ответ не теряется; связывается только точным (chat, reply_to) найденного поста).
"""

import datetime
import hashlib
import json
import os
import pathlib
import re
import sqlite3
import threading
import time
import uuid
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

import rental_case_rules as R

UNKNOWN = R.UNKNOWN
PARAMS_DEFAULT = R.PARAMS_DEFAULT          # подмена — Store(params=…); недостающий ключ берётся отсюда (§10)
SCHEMA_VERSION = "1"

ROLES = ("wa", "splinter", "human", "test")
ORIGINS = ("intake", "wa", "splinter", "human", "test")
AUTHOR_KINDS = ("code", "source", "human", "staff", "agent")
METHODS = ("door", "reply", "readback", "human", "event")
FACT_KINDS = ("rental", "cash", "contract", "contract_ref", "pdf", "staff_answer", "readback", "bike_event",
              "crm_status", "human_mark", "closing", "physical_event", "bike_state")
SCOPES = ("version", "rental", "case")
DOC_KINDS = ("contract_signed", "contract_pdf", "contract_generated", "passport_deposit")
TASK_KINDS = ("readiness", "delivery", "handover", "return", "pickup", "other")
EXPECT_TERMINAL = ("answered", "superseded", "cancelled")
EXPECT_LIVE_ANSWER = ("waiting", "escalating", "escalated", "escalation_unknown")
NOTICE_LIVE = ("intent", "drafting", "draft_unknown", "drafted")
CLOSED_ADD_FACT_KINDS = ("contract", "contract_ref", "pdf")         # closed → closed: только добавление (§4.1)
APPROVAL_ORDER = ("booking", "activate", "close")                    # splinter.py:11788-11789
CONTACT_CHANNELS = ("wa", "tg_id", "tg_username", "phone_crm")
SELF_SOURCE = "rental_case"
AGENT_SOURCE = "дело аренды (rental_case)"
MONEY_NOT_PAYMENT = "закрытие обязательства делом — не подтверждение оплаты (03.10-1 п.1)"
ISO_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Роль обязательства по роли кассы (wa_agent_tools.py:89; CONTRACT §3.4 «Соответствие роли кассы»).
CASH_ROLE_OF_OBLIGATION = (("rent", R.R_RENT), ("deposit", "залог"), ("deposit_refund", "возврат"),
                           ("change", "возврат"))

# Роли обязательств по видам и их направление (CONTRACT §3.4).
OBLIGATION_ROLES = (
    ("money", "rent", "from_client"), ("money", "deposit", "from_client"), ("money", "delivery", "from_client"),
    ("money", "surcharge", "from_client"), ("money", "change", "to_client"),
    ("money", "deposit_refund", "to_client"), ("money", "other", None),
    ("document", "passport_return", "to_client"), ("document", "contract_send", "to_client"),
    ("bike", "handover", "internal"), ("bike", "return", "internal"), ("client", "notify_final", "to_client"),
)

TABLES = frozenset(("rc_meta", "rc_case", "rc_link", "rc_contact", "rc_rental", "rc_fact", "rc_document",
                    "rc_obligation", "rc_task", "rc_stage", "rc_expect", "rc_post", "rc_answer", "rc_reply_unlinked",
                    "rc_notice", "rc_event"))

# ---------------------------------------------------------------------------------------------------------------------
# Схема SQLite версии 1 — дословно CONTRACT §2; каждое предложение исполняется отдельным execute (пакетный вызов
# делал бы COMMIT посреди BEGIN IMMEDIATE).
# ---------------------------------------------------------------------------------------------------------------------

SCHEMA = (
    "CREATE TABLE rc_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL)",
    """CREATE TABLE rc_case(
  case_id     TEXT PRIMARY KEY,
  ver         INTEGER NOT NULL DEFAULT 1 CHECK (ver >= 1),
  state       TEXT NOT NULL DEFAULT 'open' CHECK (state IN ('open','closed','cancelled')),
  link_state  TEXT NOT NULL DEFAULT 'ok' CHECK (link_state IN ('ok','drift','missing','ambiguous')),
  link_exp_id TEXT,
  attention   INTEGER NOT NULL DEFAULT 0 CHECK (attention IN (0,1)),
  pause_no    INTEGER NOT NULL DEFAULT 0 CHECK (pause_no >= 0),
  att_channel TEXT, att_number TEXT, wa_pause_no INTEGER,
  origin      TEXT NOT NULL CHECK (origin IN ('intake','wa','splinter','human','test')),
  created_at  REAL NOT NULL, created_by TEXT NOT NULL, updated_at REAL NOT NULL
)""",
    """CREATE TABLE rc_link(
  id       INTEGER PRIMARY KEY,
  case_id  TEXT NOT NULL REFERENCES rc_case(case_id),
  kind     TEXT NOT NULL CHECK (kind IN ('booking_id','anchor','crm_row')),
  value    TEXT NOT NULL,
  status   TEXT NOT NULL CHECK (status IN ('confirmed','candidate','retired')),
  source   TEXT NOT NULL, ref TEXT, author TEXT NOT NULL, at REAL NOT NULL, case_ver INTEGER NOT NULL,
  CHECK (kind <> 'crm_row' OR status <> 'confirmed'),
  UNIQUE (case_id, kind, value)
)""",
    "CREATE UNIQUE INDEX ux_link_booking ON rc_link(value) WHERE kind='booking_id' AND status='confirmed'",
    "CREATE UNIQUE INDEX ux_link_anchor  ON rc_link(value) WHERE kind='anchor'     AND status='confirmed'",
    """CREATE TABLE rc_contact(
  id          INTEGER PRIMARY KEY,
  case_id     TEXT NOT NULL REFERENCES rc_case(case_id),
  channel     TEXT NOT NULL CHECK (channel IN ('wa','tg_id','tg_username','phone_crm')),
  value       TEXT NOT NULL,
  status      TEXT NOT NULL CHECK (status IN ('active','superseded')),
  source_kind TEXT NOT NULL CHECK (source_kind IN ('crm','human','intake','test')),
  source TEXT NOT NULL, ref TEXT NOT NULL, author TEXT NOT NULL, at REAL NOT NULL, case_ver INTEGER NOT NULL,
  method      TEXT NOT NULL CHECK (method IN ('door','reply','readback','human','event')),
  read_at     REAL NOT NULL, observed_at REAL NOT NULL,
  UNIQUE (case_id, channel, value)
)""",
    "CREATE INDEX ix_contact_value ON rc_contact(channel, value, status)",
    """CREATE TABLE rc_rental(
  id           INTEGER PRIMARY KEY,
  case_id      TEXT NOT NULL REFERENCES rc_case(case_id),
  current      INTEGER NOT NULL CHECK (current IN (0,1)),
  booking_id   TEXT,
  plate        TEXT NOT NULL CHECK (plate <> ''),
  bike_name    TEXT NOT NULL,
  model_req    TEXT,
  name_seen    TEXT NOT NULL,
  name_norm    TEXT,
  start_at     TEXT, end_at TEXT,
  start_day    TEXT, end_day TEXT,
  days         INTEGER,
  status_seen  TEXT NOT NULL,
  crm_row_seen INTEGER,
  bound_by     TEXT NOT NULL CHECK (bound_by IN ('booking_id','anchor','human')),
  source       TEXT NOT NULL, read_at REAL NOT NULL, observed_at REAL NOT NULL,
  ref          TEXT NOT NULL,
  method       TEXT NOT NULL CHECK (method IN ('door','reply','readback','human','event')),
  author       TEXT NOT NULL, case_ver INTEGER NOT NULL,
  CHECK (start_day IS NOT NULL OR booking_id IS NOT NULL),
  UNIQUE (id, case_id)
)""",
    "CREATE UNIQUE INDEX ux_rental_current ON rc_rental(case_id) WHERE current=1",
    "CREATE INDEX ix_rental_booking ON rc_rental(booking_id)",
    "CREATE INDEX ix_rental_plate   ON rc_rental(plate, start_day)",
    """CREATE TABLE rc_fact(
  id          INTEGER PRIMARY KEY,
  case_id     TEXT NOT NULL REFERENCES rc_case(case_id),
  fkey        TEXT NOT NULL,
  kind        TEXT NOT NULL CHECK (kind IN ('rental','cash','contract','contract_ref','pdf','staff_answer','readback',
                                             'bike_event','crm_status','human_mark','closing','physical_event',
                                             'bike_state')),
  value       TEXT NOT NULL,
  source      TEXT NOT NULL, ref TEXT NOT NULL,
  method      TEXT NOT NULL CHECK (method IN ('door','reply','readback','human','event')),
  observed_at REAL NOT NULL, read_at REAL NOT NULL,
  case_ver    INTEGER NOT NULL,
  scope       TEXT NOT NULL CHECK (scope IN ('version','rental','case')),
  state       TEXT NOT NULL CHECK (state IN ('valid','stale','revoked')),
  reason      TEXT,
  idem_key    TEXT NOT NULL UNIQUE
)""",
    "CREATE INDEX ix_fact_case ON rc_fact(case_id, fkey, observed_at)",
    """CREATE TABLE rc_document(
  id        INTEGER PRIMARY KEY,
  case_id   TEXT NOT NULL REFERENCES rc_case(case_id),
  kind      TEXT NOT NULL CHECK (kind IN ('contract_signed','contract_pdf','contract_generated','passport_deposit')),
  ext_id    TEXT NOT NULL, reg_row INTEGER, sha256 TEXT, signed_at TEXT,
  status    TEXT NOT NULL CHECK (status IN ('verified','unverified','revoked')),
  bound_by  TEXT,
  rental_id INTEGER,
  source    TEXT NOT NULL, read_at REAL NOT NULL, author TEXT NOT NULL, case_ver INTEGER NOT NULL, reason TEXT,
  ref       TEXT NOT NULL,
  method    TEXT NOT NULL CHECK (method IN ('door','reply','readback','human','event')),
  observed_at REAL NOT NULL,
  cover_from  TEXT, cover_to TEXT,
  cover_basis TEXT CHECK (cover_basis IN ('document','addendum','human_confirmed')),
  cover_ref   TEXT,
  cover_by    INTEGER,
  cover_act   TEXT, cover_at REAL,
  FOREIGN KEY (rental_id, case_id) REFERENCES rc_rental(id, case_id),
  CHECK (kind <> 'contract_pdf' OR status <> 'verified' OR sha256 IS NOT NULL),
  CHECK (kind NOT IN ('contract_signed','contract_pdf') OR status <> 'verified' OR rental_id IS NOT NULL),
  CHECK ((cover_from IS NULL AND cover_to IS NULL AND cover_basis IS NULL AND cover_ref IS NULL AND cover_by IS NULL
          AND cover_act IS NULL AND cover_at IS NULL)
         OR (kind = 'contract_signed' AND cover_from IS NOT NULL AND cover_to IS NOT NULL AND cover_from <= cover_to
             AND cover_basis IS NOT NULL AND cover_ref IS NOT NULL AND cover_ref <> '' AND cover_at IS NOT NULL
             AND ((cover_basis = 'human_confirmed' AND cover_by IS NOT NULL AND cover_act IS NOT NULL AND cover_act <> '')
                  OR (cover_basis IN ('document','addendum') AND cover_by IS NULL AND cover_act IS NULL))))
)""",
    "CREATE UNIQUE INDEX ux_document ON rc_document(case_id, kind, ext_id, IFNULL(sha256, ''), IFNULL(signed_at, ''))",
    """CREATE TABLE rc_obligation(
  id            INTEGER PRIMARY KEY,
  case_id       TEXT NOT NULL REFERENCES rc_case(case_id),
  kind          TEXT NOT NULL CHECK (kind IN ('money','document','bike','client')),
  role          TEXT NOT NULL,
  direction     TEXT NOT NULL CHECK (direction IN ('from_client','to_client','internal')),
  amount        REAL, currency TEXT,
  outcome       TEXT CHECK (outcome IN ('valid','unknown','incomplete')),
  required      INTEGER NOT NULL DEFAULT 0 CHECK (required IN (0,1)),
  state         TEXT NOT NULL CHECK (state IN ('open','closed','unknown','waived')),
  closed_by     TEXT CHECK (closed_by IN ('write','stage','human')),
  close_ref     TEXT, close_fact_id INTEGER REFERENCES rc_fact(id), close_author TEXT,
  close_second_id INTEGER REFERENCES rc_document(id),
  source        TEXT NOT NULL, ref TEXT NOT NULL,
  method        TEXT NOT NULL CHECK (method IN ('door','reply','readback','human','event')),
  read_at       REAL NOT NULL, observed_at REAL NOT NULL,
  created_at    REAL NOT NULL, updated_at REAL NOT NULL, case_ver INTEGER NOT NULL,
  row_ver       INTEGER NOT NULL DEFAULT 1,
  idem_key      TEXT NOT NULL UNIQUE,
  CHECK (state <> 'closed' OR closed_by IS NOT NULL),
  CHECK (state <> 'waived' OR closed_by = 'human'),
  CHECK (kind <> 'money' OR outcome IS NOT NULL),
  CHECK (kind <> 'money' OR closed_by IS NULL OR closed_by IN ('write','human')),
  CHECK (closed_by <> 'write' OR close_fact_id IS NOT NULL),
  CHECK (closed_by <> 'write' OR (kind = 'money' AND role = 'rent' AND close_second_id IS NOT NULL))
)""",
    "CREATE INDEX ix_obligation_case ON rc_obligation(case_id, state)",
    """CREATE TABLE rc_task(
  task_id    TEXT PRIMARY KEY,
  case_id    TEXT NOT NULL REFERENCES rc_case(case_id),
  kind       TEXT NOT NULL CHECK (kind IN ('readiness','delivery','handover','return','pickup','other')),
  state      TEXT NOT NULL CHECK (state IN ('open','done','cancelled')),
  top_stage  INTEGER NOT NULL DEFAULT 0 CHECK (top_stage BETWEEN 0 AND 6),
  rental_id  INTEGER NOT NULL,
  case_ver   INTEGER NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL,
  row_ver    INTEGER NOT NULL DEFAULT 1,
  idem_key   TEXT NOT NULL UNIQUE,
  reason     TEXT,
  FOREIGN KEY (rental_id, case_id) REFERENCES rc_rental(id, case_id)
)""",
    """CREATE TABLE rc_stage(
  id            INTEGER PRIMARY KEY,
  task_id       TEXT NOT NULL REFERENCES rc_task(task_id),
  case_id       TEXT NOT NULL REFERENCES rc_case(case_id),
  stage         TEXT NOT NULL CHECK (stage IN ('question_sent','answer_received','task_accepted',
                                                'physically_done','result_recorded','client_notified')),
  evidence_kind TEXT NOT NULL,
  evidence_ref  TEXT NOT NULL UNIQUE,
  evidence      TEXT NOT NULL,
  flags         TEXT NOT NULL DEFAULT '[]',
  author        TEXT NOT NULL, at REAL NOT NULL, case_ver INTEGER NOT NULL,
  idem_key      TEXT NOT NULL UNIQUE,
  UNIQUE (task_id, stage)
)""",
    """CREATE TABLE rc_expect(
  exp_id          TEXT PRIMARY KEY,
  case_id         TEXT REFERENCES rc_case(case_id),
  task_id         TEXT REFERENCES rc_task(task_id),
  kind            TEXT NOT NULL CHECK (kind IN ('staff_question','approval','confirm_link','readback')),
  action          TEXT CHECK (action IN ('booking','activate','close','confirm','result')),
  place           TEXT NOT NULL CHECK (place IN ('topic','delivery','agents','intake','crm','sink')),
  chat            TEXT,
  subject         TEXT NOT NULL,
  target          TEXT,
  parent_exp      TEXT REFERENCES rc_expect(exp_id),
  cand_sha        TEXT,
  case_ver        INTEGER,
  state           TEXT NOT NULL CHECK (state IN ('planned','in_flight','waiting','escalating','escalated',
                                                  'escalation_unknown','answered','flight_unknown',
                                                  'superseded','cancelled')),
  next_check      TEXT NOT NULL CHECK (next_check IN ('post','await_post_result','reconcile','execute','readback',
                                                       'await_answer','escalate','await_escalation','await_agents',
                                                       'human_decision','none')),
  waiting_since   REAL, post_at REAL, escalated_at REAL,
  business_due_at REAL,
  due_basis       TEXT NOT NULL CHECK (due_basis IN ('business','none')),
  ext_qid         TEXT, answer_id INTEGER, attempt_no INTEGER NOT NULL DEFAULT 1,
  claimed_by      TEXT, claim_boot TEXT, claim_at REAL,
  created_at      REAL NOT NULL, updated_at REAL NOT NULL,
  row_ver         INTEGER NOT NULL DEFAULT 1,
  idem_key        TEXT NOT NULL UNIQUE,
  reason          TEXT,
  CHECK (case_id IS NOT NULL OR (kind IN ('approval','readback') AND action = 'booking')),
  CHECK ((case_id IS NULL) = (case_ver IS NULL)),
  CHECK (kind <> 'approval' OR action IN ('booking','activate','close')),
  CHECK (kind <> 'confirm_link' OR (action = 'confirm' AND cand_sha IS NOT NULL))
)""",
    "CREATE INDEX ix_expect_state ON rc_expect(state, business_due_at)",
    "CREATE INDEX ix_expect_case  ON rc_expect(case_id, state)",
    """CREATE UNIQUE INDEX ux_confirm_open ON rc_expect(case_id, case_ver, cand_sha)
  WHERE kind='confirm_link' AND state NOT IN ('answered','superseded','cancelled')""",
    """CREATE UNIQUE INDEX ux_approval_await ON rc_expect(chat, action)
  WHERE kind='approval' AND state IN ('planned','in_flight','waiting','flight_unknown')""",
    """CREATE TABLE rc_post(
  chat          TEXT NOT NULL, msg_id TEXT NOT NULL,
  exp_id        TEXT NOT NULL REFERENCES rc_expect(exp_id),
  place         TEXT NOT NULL,
  role          TEXT NOT NULL CHECK (role IN ('question','delivery','agents','escalation','card')),
  thread_id     TEXT, topic_bike TEXT,
  addressee_ids TEXT NOT NULL,
  at            REAL NOT NULL,
  PRIMARY KEY (chat, msg_id)
)""",
    """CREATE TABLE rc_answer(
  id              INTEGER PRIMARY KEY,
  exp_id          TEXT NOT NULL REFERENCES rc_expect(exp_id),
  case_id         TEXT REFERENCES rc_case(case_id),
  chat            TEXT NOT NULL, msg_id TEXT NOT NULL, reply_to TEXT NOT NULL, thread_id TEXT,
  post_role       TEXT NOT NULL,
  author_id       INTEGER, author_username TEXT,
  at              REAL NOT NULL, received_at REAL NOT NULL,
  text            TEXT NOT NULL,
  verdict         TEXT NOT NULL CHECK (verdict IN ('accepted','reference_author_unverified','reference_foreign_author',
                                                    'reference_foreign_place','reference_drift',
                                                    'reference_stale_version','reference_expired','reference_late',
                                                    'reference_superseded','reference_cancelled','reference_answered',
                                                    'reference_unclear','reference_no_reply','reference_restart')),
  decision        TEXT CHECK (decision IN ('yes','no','unclear')),
  execute         INTEGER NOT NULL DEFAULT 0 CHECK (execute IN (0,1)),
  case_ver_at     INTEGER,
  promoted_by     TEXT,
  UNIQUE (chat, msg_id),
  CHECK (execute = 0 OR (verdict = 'accepted' AND decision = 'yes'))
)""",
    """CREATE TABLE rc_reply_unlinked(
  id              INTEGER PRIMARY KEY,
  chat            TEXT NOT NULL, msg_id TEXT NOT NULL, reply_to TEXT NOT NULL, thread_id TEXT,
  author_id       INTEGER, author_username TEXT, at REAL NOT NULL, received_at REAL NOT NULL, text TEXT NOT NULL,
  state           TEXT NOT NULL CHECK (state IN ('orphan','linked','dropped')),
  answer_id       INTEGER REFERENCES rc_answer(id),
  UNIQUE (chat, msg_id)
)""",
    """CREATE TABLE rc_notice(
  notice_id  TEXT PRIMARY KEY,
  case_id    TEXT NOT NULL REFERENCES rc_case(case_id),
  task_id    TEXT REFERENCES rc_task(task_id),
  intent     TEXT NOT NULL,
  facts      TEXT NOT NULL,
  case_ver   INTEGER NOT NULL,
  state      TEXT NOT NULL CHECK (state IN ('intent','drafting','draft_unknown','drafted','delivered',
                                             'superseded','dropped')),
  draft_id   INTEGER, wamid TEXT, delivered_at REAL,
  claimed_by TEXT, claim_boot TEXT, claim_at REAL,
  created_at REAL NOT NULL, updated_at REAL NOT NULL,
  row_ver    INTEGER NOT NULL DEFAULT 1,
  idem_key   TEXT NOT NULL UNIQUE,
  CHECK (state NOT IN ('drafted','delivered') OR draft_id IS NOT NULL),
  CHECK (state <> 'delivered' OR wamid IS NOT NULL)
)""",
    """CREATE TABLE rc_event(
  seq         INTEGER PRIMARY KEY AUTOINCREMENT,
  case_id     TEXT,
  exp_id      TEXT,
  at          REAL NOT NULL,
  type        TEXT NOT NULL,
  ver_before  INTEGER, ver_after INTEGER,
  author      TEXT NOT NULL,
  source      TEXT, ref TEXT,
  payload     TEXT NOT NULL,
  payload_sha TEXT NOT NULL,
  idem_key    TEXT NOT NULL UNIQUE,
  CHECK (case_id IS NOT NULL OR exp_id IS NOT NULL
         OR type IN ('recovered','client_inbound','human_intervention','answer_orphaned'))
)""",
    "CREATE INDEX ix_event_case ON rc_event(case_id, seq)",
    "CREATE TRIGGER rc_event_no_update BEFORE UPDATE ON rc_event BEGIN SELECT RAISE(ABORT, 'rc_event append-only'); END",
    "CREATE TRIGGER rc_event_no_delete BEFORE DELETE ON rc_event BEGIN SELECT RAISE(ABORT, 'rc_event append-only'); END",
)


# ---------------------------------------------------------------------------------------------------------------------
# Исключения и мелкие помощники
# ---------------------------------------------------------------------------------------------------------------------


class StoreUnavailable(Exception):
    """Хранилище недоступно: файла нет, путь не абсолютный при открытии, чужая/иная схема, порча, quick_check ≠ ok,
    SQLite < 3.9, synchronous ≠ FULL, объект закрыт. Вызывающий обязан перевести в «неизвестно» (I19)."""


class _ArgError(ValueError):
    """Нарушение типа/формы аргумента (CONTRACT §1.2: ValueError) — пробрасывается вызывающему после ROLLBACK."""


class _Stop(Exception):
    """Досрочный исход мутации внутри транзакции: rejected/conflict/unknown — ROLLBACK (или COMMIT, если оговорено)."""

    def __init__(self, outcome, commit=False):
        Exception.__init__(self, outcome.get("reason") or outcome.get("code"))
        self.outcome = outcome
        self.commit = commit


def _uuid_hex():
    return uuid.uuid4().hex


def _json_default(obj):
    if isinstance(obj, (set, frozenset)):
        return sorted(obj, key=lambda x: json.dumps(x, ensure_ascii=False, sort_keys=True, default=str))
    if isinstance(obj, (datetime.date, datetime.datetime)):
        return obj.isoformat()
    return str(obj)


def _j(obj):
    """JSON колонок и событий: ensure_ascii=False, sort_keys=True (CONTRACT §1.1)."""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, default=_json_default)


def _sha(obj):
    return hashlib.sha256(_j(obj).encode("utf-8")).hexdigest()


def _jl(text, default=None):
    if text is None:
        return default
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return default


def _s(value):
    return "" if value is None else str(value).strip()


def _num(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def _int_id(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _digits(value):
    return re.sub(r"\D", "", str(value or ""))


def _mask(value):
    d = _digits(value)
    if d:
        return "…" + d[-4:]
    s = _s(value)
    return "…" + s[-3:] if s else ""


def _dm(day):
    """'YYYY-MM-DD' | 'yyyy-MM-dd HH:mm' → «ДД.ММ»; нет — «?»."""
    s = _s(day)
    if len(s) >= 10 and ISO_DAY.match(s[:10]):
        return "%s.%s" % (s[8:10], s[5:7])
    return "?"


def _iso_strict(value):
    if not isinstance(value, str) or not ISO_DAY.match(value):
        return None
    try:
        return datetime.date(int(value[0:4]), int(value[5:7]), int(value[8:10]))
    except ValueError:
        return None


def _pairs_get(pairs, key, default=None):
    for k, v in pairs:
        if k == key:
            return v
    return default


def _is_busy(exc):
    msg = str(exc).lower()
    return "locked" in msg or "busy" in msg


def _abs_path(path):
    if not isinstance(path, str) or not path.strip():
        raise ValueError("rental_case: путь хранилища пуст (I33)")
    if not os.path.isabs(path):
        raise ValueError("rental_case: путь хранилища не абсолютный (I33): %r" % (path,))
    return os.path.normpath(path)


def _uri(path, mode):
    """URI-путь SQLite: file:///…?mode=rw|ro|rwc (спецсимволы пути экранирует pathlib)."""
    try:
        return pathlib.Path(path).as_uri() + "?mode=" + mode
    except ValueError as e:
        raise ValueError("rental_case: путь не выражается URI (I33): %s" % e)


def _need_by(by):
    if not isinstance(by, Mapping) or by.get("kind") not in AUTHOR_KINDS:
        raise _ArgError("by: ожидался Author {kind ∈ %r, id, name}: %r" % (AUTHOR_KINDS, by))
    bid = by.get("id")
    if bid is not None and not _int_id(bid):
        raise _ArgError("by.id: целое или None: %r" % (bid,))
    return by


def _by_key(by):
    return {"kind": by.get("kind"), "id": by.get("id")}


def _author(by):
    return "%s:%s:%s" % (_s(by.get("kind")), "" if by.get("id") is None else by.get("id"), _s(by.get("name")))


def _need_source(source):
    if not isinstance(source, Mapping):
        raise _ArgError("source: ожидался Source {name, ref, method, read_at, observed_at}: %r" % (source,))
    if not _s(source.get("name")) or not _s(source.get("ref")):
        raise _ArgError("source.name и source.ref обязательны: %r" % (source,))
    if source.get("method") not in METHODS:
        raise _ArgError("source.method ∉ %r: %r" % (METHODS, source.get("method")))
    if _num(source.get("read_at")) is None or _num(source.get("observed_at")) is None:
        raise _ArgError("source.read_at и source.observed_at — числа (observed_at обязателен, CONTRACT §1.2)")
    return source


def _src_key(source):
    return {"name": _s(source.get("name")), "ref": _s(source.get("ref")), "method": source.get("method"),
            "read_at": float(source.get("read_at")), "observed_at": float(source.get("observed_at"))}


def _need_idem(idem_key):
    if not isinstance(idem_key, str) or not idem_key.strip():
        raise _ArgError("idem_key — непустая строка (CONTRACT §11)")
    return idem_key


def _out(code, case_id=None, ver=None, data=None, reason="", missing=None, ask="", event_seq=None, **extra):
    """Исход (CONTRACT §1.2)."""
    out = {"code": code, "case_id": case_id, "ver": ver, "data": dict(data or {}), "missing": list(missing or []),
           "ask": ask or "", "reason": reason or "", "expected_ver": None, "current_ver": None,
           "event_seq": event_seq}
    out.update(extra)
    return out


ASK_DEFAULT = (
    ("store_busy", "Хранилище дела занято — повторите тот же вызов с тем же idem_key."),
    ("param_unknown", "Норма для этого шага не принята (параметр UNKNOWN) — решает одобряющий."),
    ("second_source_missing", "Нужен второй независимый источник той же аренды (verified договор этого дела)."),
    ("link_missing", "У привязки аренды нет номера брони — к какой брони относится оплата?"),
    ("link_confirmation", "Привязка аренды под сомнением — это та же аренда? Нужно решение одобряющего."),
    ("possible_continuation", "Новая строка может быть продолжением открытого дела — это та же аренда или новая?"),
    ("which_rental", "К какой аренде это относится (строка, имя, даты)?"),
    ("rental_not_found", "Строку аренды не нашёл — где теперь эта аренда (строка, имя, даты)?"),
    ("contact", "Номер обращения не подтверждён в деле — на какой номер оформлена аренда?"),
)


def _ask_for(reason):
    return _pairs_get(ASK_DEFAULT, reason, "Нужно уточнение человека (%s)." % reason)


def _rejected(reason, words="", data=None, case_id=None, ver=None):
    return _out("rejected", case_id=case_id, ver=ver, data=data, reason=reason + ((": " + words) if words else ""))


def _unknown(reason, missing, ask="", data=None, case_id=None, ver=None, words=""):
    return _out("unknown", case_id=case_id, ver=ver, data=data, reason=reason + ((": " + words) if words else ""),
                missing=list(missing) or [reason], ask=ask or _ask_for(reason))


def _stop_rej(reason, words="", data=None, case_id=None, ver=None):
    raise _Stop(_rejected(reason, words, data, case_id, ver))


def _stop_unk(reason, missing, ask="", data=None, case_id=None, ver=None, words=""):
    raise _Stop(_unknown(reason, missing, ask, data, case_id, ver, words))


def _target_ok(given, tgt):
    """Цель чтения назад в свидетельстве против target ожидания (§3.6 «цель = target ожидания этой задачи», §16.10):
    не задана (ключа нет или None) — её задаёт ожидание; задана — только словарь, равный target ожидания. К4 круг 4:
    цель не словарём (строка, список, список пар, пустые и ложные значения) с target ожидания не сравнима и не
    принимается — раньше она проходила сверку молча. Одна сверка на обе двери (record_stage и on_readback)."""
    if given is None:
        return True
    return isinstance(given, Mapping) and dict(given) == tgt


def _stop_conflict(expected, current, case_id=None, ver=None, row=False):
    o = _out("conflict", case_id=case_id, ver=ver, reason="",
             data={"cas": "row_ver" if row else "case_ver", "expected": expected, "current": current})
    if row:
        o["expected_row_ver"], o["current_row_ver"] = expected, current
    else:
        o["expected_ver"], o["current_ver"] = expected, current
    raise _Stop(o)


def _day_of_moment(t, params):
    tz = R._known_int(R._p(params, "TZ_H"))
    return R.day_of_moment(t, 7 if tz is None else tz)


class _Tx(object):
    """Транзакция одного вызова на соединении потока: чтения, записи и события (главное — с idem_key вызова)."""

    def __init__(self, store, con, key, sha, by, now):
        self.store = store
        self.con = con
        self.key = key
        self.sha = sha
        self.by = by
        self.now = now
        self.n = 0
        self.main_seq = None
        self.events = []

    def q(self, sql, args=()):
        return [dict(r) for r in self.con.execute(sql, tuple(args)).fetchall()]

    def one(self, sql, args=()):
        r = self.con.execute(sql, tuple(args)).fetchone()
        return dict(r) if r is not None else None

    def x(self, sql, args=()):
        return self.con.execute(sql, tuple(args))

    def author(self):
        return _author(self.by) if self.by is not None else "code:%s:" % self.store.role

    def event(self, etype, payload, case_id=None, exp_id=None, ver_before=None, ver_after=None, source=None,
              ref=None, main=False, key=None, sha=None):
        """Запись события §8.1: главное — idem_key вызова и payload_sha аргументов; прочие — `<ключ>#<n>`."""
        if key is None:
            if main:
                key, sha = self.key, self.sha
            else:
                self.n += 1
                key = "%s#%d" % (self.key, self.n)
        if sha is None:
            sha = _sha(payload)
        cur = self.x("INSERT INTO rc_event(case_id, exp_id, at, type, ver_before, ver_after, author, source, ref, "
                     "payload, payload_sha, idem_key) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                     (case_id, exp_id, self.now, etype, ver_before, ver_after, self.author(), source, ref,
                      _j(payload), sha, key))
        seq = cur.lastrowid
        if main:
            self.main_seq = seq
        self.events.append(seq)
        return seq



# ---------------------------------------------------------------------------------------------------------------------
# Store: создание, открытие, транзакции
# ---------------------------------------------------------------------------------------------------------------------


class Store(object):
    """Хранилище дела аренды — единственный писатель rc_* (I23). Один объект на роль в процессе (CONTRACT §5)."""

    @classmethod
    def create(cls, path, *, clock=time.time, new_id=_uuid_hex, journal_mode="wal"):
        """Создание схемы версии 1 (CONTRACT §2): только шаг интеграции и тесты. Абсолютный путь; уже есть таблицы
        rc_* → StoreUnavailable("exists"). → store_id."""
        p = _abs_path(path)
        jm = _s(journal_mode).lower() or "wal"
        if jm not in ("wal", "delete"):
            raise ValueError("journal_mode ∈ {wal, delete}: %r" % (journal_mode,))
        if sqlite3.sqlite_version_info < (3, 9, 0):
            raise StoreUnavailable("SQLite < 3.9: %s" % sqlite3.sqlite_version)
        try:
            con = sqlite3.connect(_uri(p, "rwc"), uri=True, timeout=5.0, isolation_level=None)
        except sqlite3.Error as e:
            raise StoreUnavailable("create: %s" % e)
        try:
            try:
                # Существующую схему не трогаем ничем, даже режимом журнала: сначала проверка, потом PRAGMA.
                have = con.execute("SELECT count(*) FROM sqlite_master WHERE name LIKE 'rc!_%' ESCAPE '!'").fetchone()
                if have and have[0]:
                    raise StoreUnavailable("exists: схема rc_* уже есть (%d объектов)" % have[0])
                got = con.execute("PRAGMA journal_mode=%s" % ("WAL" if jm == "wal" else "DELETE")).fetchone()
                if _s(got[0] if got else "").lower() != jm:
                    raise StoreUnavailable("journal_mode не установлен: %r" % (got,))
                con.execute("PRAGMA synchronous=FULL")
                con.execute("PRAGMA foreign_keys=ON")
                con.execute("BEGIN IMMEDIATE")
                have = [r[0] for r in con.execute(
                    "SELECT name FROM sqlite_master WHERE name LIKE 'rc!_%' ESCAPE '!'").fetchall()]
                if have:
                    con.execute("ROLLBACK")
                    raise StoreUnavailable("exists: схема rc_* уже есть (%d объектов)" % len(have))
                for stmt in SCHEMA:
                    con.execute(stmt)
                store_id = new_id()
                at = clock()
                for k, v in (("schema_version", SCHEMA_VERSION), ("store_id", store_id), ("created_at", repr(at))):
                    con.execute("INSERT INTO rc_meta(key, value) VALUES (?, ?)", (k, v))
                con.execute("COMMIT")
            except sqlite3.Error as e:
                try:
                    con.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
                raise StoreUnavailable("create: %s" % e)
        finally:
            con.close()
        return store_id

    def __init__(self, path, *, role, clock=time.time, new_id=_uuid_hex, params=None, busy_timeout_s=5.0,
                 readonly=False):
        if role not in ROLES:
            raise ValueError("role ∈ %r: %r" % (ROLES, role))
        self.path = _abs_path(path)
        if not os.path.isfile(self.path):
            raise StoreUnavailable("нет файла хранилища (открытие без создания, I33): %s" % self.path)
        if sqlite3.sqlite_version_info < (3, 9, 0):
            raise StoreUnavailable("SQLite < 3.9: %s" % sqlite3.sqlite_version)
        self.role = role
        self.clock = clock
        self.new_id = new_id
        self.readonly = bool(readonly)
        self.busy_timeout_s = float(busy_timeout_s)
        merged = dict(PARAMS_DEFAULT)
        if params:
            merged.update(dict(params))
        self.params = merged
        self._local = threading.local()
        self._cons = []
        self._lock = threading.Lock()
        self._closed = False
        con, meta = self._connect(quick=not self.readonly)       # quick_check — при первом открытии писателем
        self._local.con = con
        self._cons.append(con)
        self.store_id = meta.get("store_id")
        self.schema_version = meta.get("schema_version")
        self.boot_id = new_id()

    # ----- соединения -----

    def _connect(self, quick):
        mode = "ro" if self.readonly else "rw"
        try:
            con = sqlite3.connect(_uri(self.path, mode), uri=True, timeout=self.busy_timeout_s,
                                  isolation_level=None, check_same_thread=True)
        except sqlite3.Error as e:
            raise StoreUnavailable("открытие: %s" % e)
        try:
            con.row_factory = sqlite3.Row
            con.execute("PRAGMA foreign_keys=ON")
            con.execute("PRAGMA synchronous=FULL")
            sync = con.execute("PRAGMA synchronous").fetchone()
            if sync is None or int(sync[0]) != 2:
                raise StoreUnavailable("synchronous ≠ FULL: %r" % (tuple(sync) if sync else None,))
            fk = con.execute("PRAGMA foreign_keys").fetchone()
            if fk is None or int(fk[0]) != 1:
                raise StoreUnavailable("foreign_keys не включены")
            names = set(r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'rc!_%' ESCAPE '!'").fetchall())
            if names != TABLES:
                raise StoreUnavailable("чужая или неполная схема: нет %s; лишние %s" % (
                    sorted(TABLES - names), sorted(names - TABLES)))
            meta = {}
            for r in con.execute("SELECT key, value FROM rc_meta").fetchall():
                meta[r[0]] = r[1]
            if meta.get("schema_version") != SCHEMA_VERSION:
                raise StoreUnavailable("иная версия схемы: %r" % (meta.get("schema_version"),))
            if not meta.get("store_id"):
                raise StoreUnavailable("в rc_meta нет store_id")
            if quick:
                qc = con.execute("PRAGMA quick_check").fetchone()
                if qc is None or _s(qc[0]).lower() != "ok":
                    raise StoreUnavailable("quick_check: %r" % (tuple(qc) if qc else None,))
        except StoreUnavailable:
            con.close()
            raise
        except sqlite3.Error as e:
            con.close()
            raise StoreUnavailable("хранилище не читается: %s" % e)
        return con, meta

    def _con(self):
        if self._closed:
            raise StoreUnavailable("Store закрыт")
        con = getattr(self._local, "con", None)
        if con is None:
            con, _meta = self._connect(quick=False)
            self._local.con = con
            with self._lock:
                self._cons.append(con)
        return con

    def close(self):
        self._closed = True
        with self._lock:
            cons, self._cons = list(self._cons), []
        for con in cons:
            try:
                con.close()
            except Exception:                         # noqa: BLE001 — соединение чужого потока закроет его поток/GC
                pass
        self._local = threading.local()

    # ----- транзакции -----

    def _end(self, con, commit):
        try:
            con.execute("COMMIT" if commit else "ROLLBACK")
            return None
        except sqlite3.Error as e:
            try:
                con.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            return e

    def _busy_out(self):
        return _unknown("store_busy", ["retry"], _ask_for("store_busy"))

    def _mutate(self, idem_key, payload, by, body, dup=None, natural=None):
        """Одна мутация = одна транзакция BEGIN IMMEDIATE (I6, I31): сначала естественный ключ (natural(tx) → исход
        duplicate | None — у ответов, §4.7 п.3), затем idem_key/payload_sha (I7, I32), затем тело с предусловиями;
        _Stop → его исход (ROLLBACK, или COMMIT при commit=True); прочее → ROLLBACK."""
        if self.readonly:
            raise _ArgError("Store(readonly=True) не пишет")
        _need_idem(idem_key)
        sha = _sha(payload)
        con = self._con()
        now = self.clock()
        try:
            con.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError as e:
            if _is_busy(e):
                return self._busy_out()
            return _rejected("internal", "BEGIN: %s" % e)
        tx = _Tx(self, con, idem_key, sha, by, now)
        try:
            if natural is not None:
                out = natural(tx)
                if out is not None:
                    self._end(con, False)
                    return out
            prev = tx.one("SELECT seq, payload_sha, case_id, exp_id, payload FROM rc_event WHERE idem_key=?",
                          (idem_key,))
            if prev is not None:
                out = self._dup_out(tx, prev, sha, dup)
                self._end(con, False)
                return out
            out = body(tx)
            err = self._end(con, True)
            if err is not None:
                return self._busy_out() if _is_busy(err) else _rejected("internal", "COMMIT: %s" % err)
            return out
        except _Stop as st:
            err = self._end(con, st.commit)
            if err is not None:
                return self._busy_out() if _is_busy(err) else _rejected("internal", "COMMIT: %s" % err)
            return st.outcome
        except _ArgError:
            self._end(con, False)
            raise
        except sqlite3.OperationalError as e:
            self._end(con, False)
            if _is_busy(e):
                return self._busy_out()
            return _rejected("internal", "%s: %s" % (type(e).__name__, e))
        except Exception as e:                        # noqa: BLE001 — I6: любой сбой → ROLLBACK и rejected(internal)
            self._end(con, False)
            return _rejected("internal", "%s: %s" % (type(e).__name__, e))

    def _dup_out(self, tx, prev, sha, dup):
        if prev["payload_sha"] != sha:
            return _out("conflict", case_id=prev.get("case_id"), reason="idem_payload_mismatch",
                        data={"event_seq": prev["seq"]})
        data = _jl(prev.get("payload"), {}) or {}
        if not isinstance(data, dict):
            data = {}
        if dup is not None:
            data = dup(data)
        data["duplicate"] = True
        cid = prev.get("case_id") or data.get("case_id")
        ver = None
        if cid:
            c = tx.one("SELECT ver FROM rc_case WHERE case_id=?", (cid,))
            ver = c["ver"] if c else None
        return _out("duplicate", case_id=cid, ver=ver, data=data, event_seq=prev["seq"])

    def _read(self, fn):
        con = self._con()
        now = self.clock()
        con.execute("BEGIN")
        tx = _Tx(self, con, None, None, None, now)
        try:
            return fn(tx)
        except sqlite3.OperationalError as e:
            if _is_busy(e):
                raise StoreUnavailable("store_busy: %s" % e)
            raise
        finally:
            try:
                con.execute("COMMIT")
            except sqlite3.Error:
                pass

    # ----- кто есть кто -----

    def _approver(self, by):
        return isinstance(by, Mapping) and by.get("kind") == "human" and R.approver_ok(by.get("id"), self.params)

    def _p(self, name):
        return R._p(self.params, name)

    # ----- дело -----

    def _case(self, tx, case_id):
        return tx.one("SELECT * FROM rc_case WHERE case_id=?", (case_id,))

    def _need_case(self, tx, case_id, allow_closed=False):
        if not isinstance(case_id, str) or not case_id:
            raise _ArgError("case_id — непустая строка")
        c = self._case(tx, case_id)
        if c is None:
            _stop_rej("case_not_found", data={"case_id": case_id})
        if c["state"] == "cancelled":
            _stop_rej("case_cancelled", case_id=case_id, ver=c["ver"])
        if c["state"] == "closed" and not allow_closed:
            _stop_rej("case_closed", case_id=case_id, ver=c["ver"])
        return c

    def _check_ver(self, case, expect_ver):
        if not _int_id(expect_ver):
            raise _ArgError("expect_ver — целое")
        if case["ver"] != expect_ver:
            _stop_conflict(expect_ver, case["ver"], case_id=case["case_id"], ver=case["ver"])

    def _check_row_ver(self, row, expect_row_ver, case_id=None, ver=None):
        if not _int_id(expect_row_ver):
            raise _ArgError("expect_row_ver — целое")
        if row["row_ver"] != expect_row_ver:
            _stop_conflict(expect_row_ver, row["row_ver"], case_id=case_id, ver=ver, row=True)

    def _case_set(self, tx, case, **cols):
        cols["updated_at"] = tx.now
        names = sorted(cols)
        tx.x("UPDATE rc_case SET %s WHERE case_id=?" % ", ".join("%s=?" % n for n in names),
             [cols[n] for n in names] + [case["case_id"]])
        case.update(cols)

    def _ok(self, tx, case_id=None, ver=None, data=None, reason=""):
        return _out("ok", case_id=case_id, ver=ver, data=data, reason=reason, event_seq=tx.main_seq)

    # ----- привязка аренды -----

    def _rental(self, tx, case_id):
        return tx.one("SELECT * FROM rc_rental WHERE case_id=? AND current=1", (case_id,))

    def _anchor(self, tx, case_id):
        r = tx.one("SELECT value FROM rc_link WHERE case_id=? AND kind='anchor' AND status='confirmed'", (case_id,))
        return r["value"] if r else None

    def _booking(self, tx, case_id):
        r = tx.one("SELECT value FROM rc_link WHERE case_id=? AND kind='booking_id' AND status='confirmed' "
                   "ORDER BY id", (case_id,))
        return r["value"] if r else None

    @staticmethod
    def _anchor_of_rental(r):
        if r and r.get("plate") and r.get("start_day") and r.get("name_norm"):
            return "%s|%s|%s" % (r["plate"], r["start_day"], r["name_norm"])
        return None

    def _contacts(self, tx, case_id, active_only=False):
        sql = "SELECT * FROM rc_contact WHERE case_id=?" + (" AND status='active'" if active_only else "")
        return tx.q(sql + " ORDER BY id", (case_id,))

    def _doc_phone_of_case(self, tx, case_id, phone):
        """К4 круг 2 (C6): телефон договора — активный телефонный контакт дела (хвост KEY_DIGITS цифр, как у номера
        обращения). Телефона в факте нет или он короче хвоста — не доказано (False)."""
        kd = self._p("KEY_DIGITS")
        kd = kd if isinstance(kd, int) and not isinstance(kd, bool) and kd > 0 else 9
        d = _digits(phone)
        if len(d) < kd:
            return False
        for c in self._contacts(tx, case_id, True):
            if c["channel"] in ("wa", "phone_crm"):
                v = _digits(c["value"])
                if len(v) >= kd and v[-kd:] == d[-kd:]:
                    return True
        return False

    def _binding(self, tx, case):
        """Текущая привязка дела в форме правил (rules.reconcile/continuation/bind_cash/stage_allowed)."""
        r = self._rental(tx, case["case_id"])
        if r is None:
            return None
        b = dict(r)
        b["rental_id"] = r["id"]
        b["case_id"] = case["case_id"]
        b["anchor"] = self._anchor(tx, case["case_id"]) or self._anchor_of_rental(r)
        b["contacts"] = [{"channel": c["channel"], "value": c["value"], "status": c["status"],
                          "source_kind": c["source_kind"]} for c in self._contacts(tx, case["case_id"], True)]
        b["return_stage5"] = tx.one(
            "SELECT 1 AS x FROM rc_stage s JOIN rc_task t ON t.task_id=s.task_id WHERE t.case_id=? AND t.kind='return' "
            "AND s.stage='result_recorded'", (case["case_id"],)) is not None
        return b

    def _open_bindings(self, tx, exclude=None, plate=None):
        sql = "SELECT * FROM rc_case WHERE state='open'"
        out = []
        for c in tx.q(sql + " ORDER BY created_at, case_id"):
            if exclude and c["case_id"] == exclude:
                continue
            b = self._binding(tx, c)
            if b is None or (plate is not None and b.get("plate") != plate):
                continue
            out.append(b)
        return out

    def _pseudo_rows(self, bindings):
        """Привязки других дел в форме строки двери (для проверок «в сроке другой строки»)."""
        rows = []
        for b in bindings:
            rows.append({"row": b.get("crm_row_seen"), "bike": b.get("bike_name") or b.get("plate"),
                         "booking_id": b.get("booking_id") or "", "date_start": b.get("start_at") or b.get("start_day"),
                         "date_end": b.get("end_at") or b.get("end_day"), "status": b.get("status_seen"),
                         "name": b.get("name_seen"), "contacts": ""})
        return rows

    def _insert_rental(self, tx, case_id, row, source, bound_by, case_ver, booking_id=None, model_req=None):
        c = R.classify(row, float(source["observed_at"]), self.params)
        bk = booking_id if booking_id is not None else (_s(row.get("booking_id")) or None)
        crm_row = row.get("row") if _int_id(row.get("row")) else None
        tx.x("UPDATE rc_rental SET current=0 WHERE case_id=? AND current=1", (case_id,))
        cur = tx.x("INSERT INTO rc_rental(case_id, current, booking_id, plate, bike_name, model_req, name_seen, name_norm, "
                   "start_at, end_at, start_day, end_day, days, status_seen, crm_row_seen, bound_by, source, read_at, "
                   "observed_at, ref, method, author, case_ver) VALUES (?,1,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (case_id, bk, c["plate"], _s(row.get("bike")), model_req,
                    "" if row.get("name") is None else str(row.get("name")), c["name_norm"],
                    row.get("date_start") if row.get("date_start") is not None else None,
                    row.get("date_end") if row.get("date_end") is not None else None,
                    c["start_day"], c["end_day"], c["days"], _s(row.get("status")), crm_row, bound_by,
                    _s(source["name"]), float(source["read_at"]), float(source["observed_at"]), _s(source["ref"]),
                    source["method"], tx.author(), case_ver))
        return cur.lastrowid

    # ----- ссылки и контакты -----

    def _link_owner(self, tx, kind, value, exclude_case=None):
        r = tx.one("SELECT case_id FROM rc_link WHERE kind=? AND value=? AND status='confirmed'", (kind, value))
        if r is None or (exclude_case and r["case_id"] == exclude_case):
            return None
        return r["case_id"]

    def _link_free(self, tx, case, kind, value):
        """Подтверждение чужого booking_id/якоря — именованный отказ (I-20) с версией дела на этот момент."""
        if value and kind in ("booking_id", "anchor"):
            owner = self._link_owner(tx, kind, value, case["case_id"])
            if owner is not None:
                _stop_rej("booking_taken" if kind == "booking_id" else "anchor_taken", data={"case_id": owner},
                          case_id=case["case_id"], ver=case["ver"])

    def _link_set(self, tx, case, kind, value, status, source_name, ref, why):
        """Ссылка дела: вставка или смена статуса; подтверждение чужого booking_id/якоря — именованный отказ (I-20)."""
        if not value:
            return False
        if status == "confirmed":
            self._link_free(tx, case, kind, value)
        ex = tx.one("SELECT * FROM rc_link WHERE case_id=? AND kind=? AND value=?", (case["case_id"], kind, value))
        if ex is not None and ex["status"] == status:
            return False
        if ex is not None:
            tx.x("UPDATE rc_link SET status=?, source=?, ref=?, author=?, at=?, case_ver=? WHERE id=?",
                 (status, source_name, ref, tx.author(), tx.now, case["ver"], ex["id"]))
        else:
            tx.x("INSERT INTO rc_link(case_id, kind, value, status, source, ref, author, at, case_ver) "
                 "VALUES (?,?,?,?,?,?,?,?,?)", (case["case_id"], kind, value, status, source_name, ref, tx.author(),
                                                tx.now, case["ver"]))
        tx.event("link_retired" if status == "retired" else "link_added",
                 {"kind": kind, "value": value, "status": status, "why": why}, case_id=case["case_id"],
                 source=source_name, ref=ref)
        return True

    def _retire_links(self, tx, case, kinds, statuses, why):
        out = []
        marks = ",".join("?" * len(statuses))
        kmarks = ",".join("?" * len(kinds))
        for l in tx.q("SELECT * FROM rc_link WHERE case_id=? AND kind IN (%s) AND status IN (%s) ORDER BY id"
                      % (kmarks, marks), [case["case_id"]] + list(kinds) + list(statuses)):
            self._link_set(tx, case, l["kind"], l["value"], "retired", SELF_SOURCE, why, why)
            out.append({"kind": l["kind"], "value": l["value"]})
        return out

    @staticmethod
    def _norm_contact(channel, value):
        if channel in ("wa", "phone_crm", "tg_id"):
            return _digits(value)
        if channel == "tg_username":
            return _s(value).lstrip("@").lower()
        return _s(value)

    def _contact_add(self, tx, case, channel, value, source_kind, source, why, main=False):
        value = self._norm_contact(channel, value)
        if not value:
            return False
        ex = tx.one("SELECT * FROM rc_contact WHERE case_id=? AND channel=? AND value=?",
                    (case["case_id"], channel, value))
        if ex is not None and ex["status"] == "active":
            if main:
                tx.event("contact_added", {"channel": channel, "value_masked": _mask(value), "status": "active",
                                           "source_kind": ex["source_kind"], "why": "already_active"},
                         case_id=case["case_id"], source=_s(source["name"]), ref=_s(source["ref"]), main=True)
            return False
        if ex is not None:
            tx.x("UPDATE rc_contact SET status='active', source_kind=?, source=?, ref=?, author=?, at=?, case_ver=?, "
                 "method=?, read_at=?, observed_at=? WHERE id=?",
                 (source_kind, _s(source["name"]), _s(source["ref"]), tx.author(), tx.now, case["ver"],
                  source["method"], float(source["read_at"]), float(source["observed_at"]), ex["id"]))
        else:
            tx.x("INSERT INTO rc_contact(case_id, channel, value, status, source_kind, source, ref, author, at, case_ver, "
                 "method, read_at, observed_at) VALUES (?,?,?,'active',?,?,?,?,?,?,?,?,?)",
                 (case["case_id"], channel, value, source_kind, _s(source["name"]), _s(source["ref"]), tx.author(),
                  tx.now, case["ver"], source["method"], float(source["read_at"]), float(source["observed_at"])))
        tx.event("contact_added", {"channel": channel, "value_masked": _mask(value), "status": "active",
                                   "source_kind": source_kind, "why": why},
                 case_id=case["case_id"], source=_s(source["name"]), ref=_s(source["ref"]), main=main)
        return True

    def _contact_supersede(self, tx, case, channel, value, why, source=None):
        kd = R._known_int(self._p("KEY_DIGITS")) or 9
        value = self._norm_contact(channel, value)
        hit = []
        for c in self._contacts(tx, case["case_id"], True):
            if c["channel"] != channel:
                continue
            if channel in ("wa", "phone_crm"):
                same = len(c["value"]) >= kd and len(value) >= kd and c["value"][-kd:] == value[-kd:]
            else:
                same = c["value"] == value
            if same:
                hit.append(c)
        for c in hit:
            tx.x("UPDATE rc_contact SET status='superseded' WHERE id=?", (c["id"],))
            tx.event("contact_superseded", {"channel": channel, "value_masked": _mask(c["value"]),
                                            "status": "superseded", "source_kind": c["source_kind"], "why": why},
                     case_id=case["case_id"], source=_s((source or {}).get("name")) or None,
                     ref=_s((source or {}).get("ref")) or None)
        return len(hit)

    def _contact_cases(self, tx, contact, open_only=True):
        """Дела активного контакта (канал wa/phone_crm — хвост KEY_DIGITS; tg — точное значение)."""
        if not isinstance(contact, Mapping):
            raise _ArgError("contact — {channel, value}")
        channel = _s(contact.get("channel")) or "wa"
        value = self._norm_contact(channel, contact.get("value"))
        kd = R._known_int(self._p("KEY_DIGITS")) or 9
        out = []
        if not value:
            return out
        rows = tx.q("SELECT c.case_id AS case_id, c.value AS value, c.channel AS channel FROM rc_contact c "
                    "JOIN rc_case k ON k.case_id=c.case_id WHERE c.status='active'%s ORDER BY k.created_at, c.case_id"
                    % (" AND k.state='open'" if open_only else ""))
        for r in rows:
            if channel in ("wa", "phone_crm"):
                if r["channel"] not in ("wa", "phone_crm"):
                    continue
                if not (len(value) >= kd and len(r["value"]) >= kd and r["value"][-kd:] == value[-kd:]):
                    continue
            elif r["channel"] != channel or r["value"] != value:
                continue
            if r["case_id"] not in out:
                out.append(r["case_id"])
        return out

    def _contact_status(self, tx, case_id, contact):
        """active | superseded | none — номер обращения среди контактов дела."""
        channel = _s(contact.get("channel")) or "wa"
        value = self._norm_contact(channel, contact.get("value"))
        kd = R._known_int(self._p("KEY_DIGITS")) or 9
        seen = "none"
        for c in self._contacts(tx, case_id):
            if channel in ("wa", "phone_crm"):
                if c["channel"] not in ("wa", "phone_crm"):
                    continue
                same = len(value) >= kd and len(c["value"]) >= kd and c["value"][-kd:] == value[-kd:]
            else:
                same = c["channel"] == channel and c["value"] == value
            if same:
                if c["status"] == "active":
                    return "active"
                seen = "superseded"
        return seen


    # ----- ожидания -----

    def _unique_idem(self, tx, table, key):
        """Ключ подзаписи (rc_expect/rc_obligation/rc_fact/rc_task …): занят прежней записью — суффикс попытки."""
        k, n = key, 1
        while tx.one("SELECT 1 AS x FROM %s WHERE idem_key=?" % table, (k,)) is not None:
            n += 1
            k = "%s#a%d" % (key, n)
        return k

    def _exp(self, tx, exp_id):
        if not isinstance(exp_id, str) or not exp_id:
            raise _ArgError("exp_id — непустая строка")
        return tx.one("SELECT * FROM rc_expect WHERE exp_id=?", (exp_id,))

    def _need_exp(self, tx, exp_id):
        e = self._exp(tx, exp_id)
        if e is None:
            _stop_rej("expect_state", "ожидания нет", data={"exp_id": exp_id})
        return e

    def _exp_set(self, tx, exp, **cols):
        cols["row_ver"] = exp["row_ver"] + 1
        cols["updated_at"] = tx.now
        names = sorted(cols)
        tx.x("UPDATE rc_expect SET %s WHERE exp_id=?" % ", ".join("%s=?" % n for n in names),
             [cols[n] for n in names] + [exp["exp_id"]])
        exp.update(cols)

    def _skew(self, tx, exp):
        """Часы процесса позади начала ожидания (now < waiting_since): прошедшее время считается 0, и мутация, которая
        его касается, оставляет подсобытие clock_skew (P-m1, §8.1). Порядок решает seq, а не стенные часы (§1.1)."""
        ws = exp.get("waiting_since")
        if ws is not None and tx.now < float(ws):
            tx.event("clock_skew", {"exp_id": exp["exp_id"], "now": tx.now, "waiting_since": ws},
                     case_id=exp.get("case_id"), exp_id=exp["exp_id"])
            return True
        return False

    def _exp_event(self, tx, etype, exp, state_old, why="", main=False, **extra):
        payload = {"exp_id": exp["exp_id"], "kind": exp["kind"], "action": exp.get("action"), "place": exp["place"],
                   "state_old": state_old, "state_new": exp["state"], "why": why}
        payload.update(extra)
        return tx.event(etype, payload, case_id=exp.get("case_id"), exp_id=exp["exp_id"], main=main)

    def _insert_exp(self, tx, case, kind, place, subject, idem_key, state="planned", next_check="post", task_id=None,
                    action=None, chat=None, target=None, parent_exp=None, cand_sha=None, attempt_no=1, reason=None):
        exp_id = "RE-" + self.new_id()
        cid = case["case_id"] if case else None
        cver = case["ver"] if case else None
        tx.x("INSERT INTO rc_expect(exp_id, case_id, task_id, kind, action, place, chat, subject, target, parent_exp, "
             "cand_sha, case_ver, state, next_check, due_basis, attempt_no, created_at, updated_at, row_ver, idem_key, "
             "reason) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,'none',?,?,?,1,?,?)",
             (exp_id, cid, task_id, kind, action, place, chat, _j(subject), None if target is None else _j(target),
              parent_exp, cand_sha, cver, state, next_check, attempt_no, tx.now, tx.now, idem_key, reason))
        return self._exp(tx, exp_id)

    @staticmethod
    def _row_brief(row):
        """Строка-кандидат для вопроса и последующего решения (целиком, как прочитана дверью)."""
        return dict((k, row.get(k)) for k in ("row", "status", "auto_cancel", "bike", "name", "date_start", "date_end",
                                               "contacts", "booking_id", "deposit_raw", "debt", "to_pay", "paid",
                                               "pay_per_day", "note", "type") if k in row)

    def _confirm_link(self, tx, case, rows, cand_sha, question, ctype, why, extra=None, main=False):
        """Одно ожидание confirm_link на (дело, версия, набор кандидатов) (ux_confirm_open, I-11)."""
        ex = tx.one("SELECT * FROM rc_expect WHERE kind='confirm_link' AND case_id=? AND case_ver=? AND cand_sha=? "
                    "AND state NOT IN ('answered','superseded','cancelled')", (case["case_id"], case["ver"], cand_sha))
        if ex is not None:
            return ex, False
        subject = {"question": question, "type": ctype, "why": why,
                   "candidates": [{"row": r.get("row"), "booking_id": _s(r.get("booking_id")) or None,
                                   "anchor": R.anchor_of(r), "bike": _s(r.get("bike")), "name": _s(r.get("name")),
                                   "date_start": r.get("date_start"), "date_end": r.get("date_end"),
                                   "status": _s(r.get("status"))} for r in rows]}
        if extra:
            subject.update(extra)
        target = {"rows": [self._row_brief(r) for r in rows]}
        key = self._unique_idem(tx, "rc_expect", "confirm:%s:%s:%s" % (case["case_id"], case["ver"], cand_sha))
        exp = self._insert_exp(tx, case, "confirm_link", "intake", subject, key, action="confirm", target=target,
                               cand_sha=cand_sha)
        self._exp_event(tx, "expectation_planned", exp, None, why=why, main=main)
        return exp, True

    def _pending_confirm_for_row(self, tx, row):
        """Ожидание confirm_link, чей кандидат — эта строка (booking_id, якорь или номер строки)."""
        bk = _s(row.get("booking_id")) or None
        anchor = R.anchor_of(row)
        for e in tx.q("SELECT * FROM rc_expect WHERE kind='confirm_link' AND state NOT IN ('answered','superseded',"
                      "'cancelled') ORDER BY created_at, exp_id"):
            for c in (_jl(e.get("subject"), {}) or {}).get("candidates") or []:
                if bk and c.get("booking_id") == bk:
                    return e
                if not bk and anchor and c.get("anchor") == anchor:
                    return e
        return None

    def _link_state(self, tx, case, new, exp_id=None, why=""):
        old = case["link_state"]
        new_exp = exp_id if new != "ok" else None
        if old == new and case.get("link_exp_id") == new_exp:
            return False
        self._case_set(tx, case, link_state=new, link_exp_id=new_exp)
        tx.event("link_state_changed", {"old": old, "new": new, "exp_id": exp_id, "why": why}, case_id=case["case_id"])
        return True

    def _confirm_open(self, tx, case_id):
        return tx.one("SELECT exp_id, subject FROM rc_expect WHERE case_id=? AND kind='confirm_link' AND state NOT IN "
                      "('answered','superseded','cancelled') ORDER BY created_at, exp_id", (case_id,))

    # ----- внимание и уведомления -----

    def _attention_on(self, tx, case, channel, why, number=None, wa_pause_no=None):
        cols = {}
        if not case["attention"]:
            cols = {"attention": 1, "pause_no": case["pause_no"] + 1, "att_channel": channel, "att_number": number,
                    "wa_pause_no": wa_pause_no}
        elif wa_pause_no is not None and case.get("wa_pause_no") is None:
            cols = {"wa_pause_no": wa_pause_no}
        if cols:
            self._case_set(tx, case, **cols)
        tx.event("attention_set", {"why": why, "channel": channel, "pause_no": case["pause_no"],
                                   "wa_pause_no": case.get("wa_pause_no"), "changed": bool(cols)},
                 case_id=case["case_id"])
        return bool(cols)

    def _supersede_notices(self, tx, case_id, why, states=("intent", "drafted")):
        out = []
        marks = ",".join("?" * len(states))
        for n in tx.q("SELECT * FROM rc_notice WHERE case_id=? AND state IN (%s) ORDER BY created_at, notice_id"
                      % marks, [case_id] + list(states)):
            tx.x("UPDATE rc_notice SET state='superseded', row_ver=row_ver+1, updated_at=? WHERE notice_id=?",
                 (tx.now, n["notice_id"]))
            tx.event("notice_state", {"notice_id": n["notice_id"], "intent": n["intent"], "state_old": n["state"],
                                      "state_new": "superseded", "why": why}, case_id=case_id)
            out.append(n["notice_id"])
        return out

    # ----- факты -----

    def _fact_insert(self, tx, case, kind, value, fkey, source, scope, idem_key, main=False, why="", ver=None):
        cur = tx.x("INSERT INTO rc_fact(case_id, fkey, kind, value, source, ref, method, observed_at, read_at, case_ver, "
                   "scope, state, reason, idem_key) VALUES (?,?,?,?,?,?,?,?,?,?,?,'valid',NULL,?)",
                   (case["case_id"], _j(list(fkey)), kind, _j(value), _s(source["name"]), _s(source["ref"]),
                    source["method"], float(source["observed_at"]), float(source["read_at"]),
                    case["ver"] if ver is None else ver, scope, idem_key))
        fid = cur.lastrowid
        tx.event("fact_recorded", {"fact_id": fid, "kind": kind, "fkey": list(fkey), "scope": scope, "why": why},
                 case_id=case["case_id"], source=_s(source["name"]), ref=_s(source["ref"]), main=main)
        return fid

    def _fact_latest(self, tx, case_id, fkey):
        return tx.one("SELECT * FROM rc_fact WHERE case_id=? AND fkey=? AND state='valid' "
                      "ORDER BY observed_at DESC, id DESC LIMIT 1", (case_id, _j(list(fkey))))

    def _revoke_fact(self, tx, case, fact, reason, main=False):
        tx.x("UPDATE rc_fact SET state='revoked', reason=? WHERE id=?", (reason, fact["id"]))
        tx.event("fact_revoked", {"fact_id": fact["id"], "kind": fact["kind"], "fkey": _jl(fact["fkey"]),
                                  "scope": fact["scope"], "why": reason}, case_id=case["case_id"], main=main)
        return self._reopen_by(tx, case, "close_fact_id", fact["id"], reason)

    # ----- обязательства -----

    def _obl_payload(self, o, why):
        return {"obligation_id": o["id"], "kind": o["kind"], "role": o["role"], "amount": o.get("amount"),
                "currency": o.get("currency"), "outcome": o.get("outcome"), "state": o.get("state"),
                "closed_by": o.get("closed_by"), "close_ref": o.get("close_ref"),
                "close_fact_id": o.get("close_fact_id"), "close_second_id": o.get("close_second_id"), "why": why}

    def _obl_insert(self, tx, case, kind, role, direction, state, outcome, amount, currency, required, source, idem_key,
                    why, main=False):
        cur = tx.x("INSERT INTO rc_obligation(case_id, kind, role, direction, amount, currency, outcome, required, state, "
                   "source, ref, method, read_at, observed_at, created_at, updated_at, case_ver, row_ver, idem_key) "
                   "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?)",
                   (case["case_id"], kind, role, direction, amount, currency, outcome, 1 if required else 0, state,
                    _s(source["name"]), _s(source["ref"]), source["method"], float(source["read_at"]),
                    float(source["observed_at"]), tx.now, tx.now, case["ver"], idem_key))
        o = tx.one("SELECT * FROM rc_obligation WHERE id=?", (cur.lastrowid,))
        tx.event("obligation_opened", self._obl_payload(o, why), case_id=case["case_id"], source=_s(source["name"]),
                 ref=_s(source["ref"]), main=main)
        return o

    def _obl_set(self, tx, obl, **cols):
        cols["row_ver"] = obl["row_ver"] + 1
        cols["updated_at"] = tx.now
        names = sorted(cols)
        tx.x("UPDATE rc_obligation SET %s WHERE id=?" % ", ".join("%s=?" % n for n in names),
             [cols[n] for n in names] + [obl["id"]])
        obl.update(cols)

    def _reopen_by(self, tx, case, col, ref_id, why):
        """Закрытое по write обязательство, чей факт или второй источник отозван → unknown (P-B3, I45)."""
        out = []
        for o in tx.q("SELECT * FROM rc_obligation WHERE case_id=? AND state='closed' AND closed_by='write' AND %s=?"
                      % col, (case["case_id"], ref_id)):
            old_fact, old_second = o["close_fact_id"], o["close_second_id"]
            self._obl_set(tx, o, state="unknown", closed_by=None, close_fact_id=None, close_second_id=None,
                          close_author=None)
            p = self._obl_payload(o, why)
            p.update(close_fact_id=old_fact, close_second_id=old_second)
            tx.event("obligation_reopened", p, case_id=case["case_id"])
            out.append(o["id"])
        return out

    # ----- подъём версии (DESIGN §4.2, I21) -----

    def _bump(self, tx, case, reason, ref, main=False, source_name=None):
        if reason not in R.BUMP_REASONS:
            raise _ArgError("reason ∉ %r: %r" % (R.BUMP_REASONS, reason))
        cid = case["case_id"]
        vb = case["ver"]
        va = vb + 1
        self._case_set(tx, case, ver=va)
        superseded, qids = [], []
        for e in tx.q("SELECT * FROM rc_expect WHERE case_id=? AND state NOT IN ('answered','superseded','cancelled') "
                      "ORDER BY created_at, exp_id", (cid,)):
            if e["kind"] == "readback" and e["state"] in ("in_flight", "waiting", "flight_unknown"):
                continue                     # исполнение уже захвачено: внешний шаг мог случиться — чтение назад живо
            old = e["state"]
            self._exp_set(tx, e, state="superseded", next_check="none", reason="version:%s" % reason)
            self._exp_event(tx, "expectation_superseded", e, old, why="version_bumped:%s" % reason)
            superseded.append(e["exp_id"])
            if e["kind"] == "staff_question" and e.get("ext_qid"):
                qids.append(e["ext_qid"])
        cancelled = []
        if reason != "new_request":
            for t in tx.q("SELECT * FROM rc_task WHERE case_id=? AND state='open' AND top_stage < 4 "
                          "ORDER BY created_at, task_id", (cid,)):
                tx.x("UPDATE rc_task SET state='cancelled', reason=?, row_ver=row_ver+1, updated_at=? WHERE task_id=?",
                     ("version:%s" % reason, tx.now, t["task_id"]))
                tx.event("task_cancelled", {"task_id": t["task_id"], "kind": t["kind"], "ref": ref,
                                            "why": "version:%s" % reason}, case_id=cid)
                cancelled.append(t["task_id"])
        scopes = ("version",) if reason == "new_request" else ("version", "rental")
        stale = 0
        for f in tx.q("SELECT * FROM rc_fact WHERE case_id=? AND state='valid' AND scope IN (%s) ORDER BY id"
                      % ",".join("?" * len(scopes)), [cid] + list(scopes)):
            tx.x("UPDATE rc_fact SET state='stale', reason=? WHERE id=?", ("version:%s" % reason, f["id"]))
            tx.event("fact_stale", {"fact_id": f["id"], "kind": f["kind"], "fkey": _jl(f["fkey"]),
                                    "scope": f["scope"], "why": "version:%s" % reason}, case_id=cid)
            stale += 1
        notices = self._supersede_notices(tx, cid, "version:%s" % reason)
        data = {"reason": reason, "ref": ref, "superseded": superseded, "cancelled_tasks": cancelled,
                "stale_facts": stale, "superseded_notices": notices, "staff_qids_to_close": qids}
        tx.event("version_bumped", data, case_id=cid, ver_before=vb, ver_after=va, main=main, source=source_name,
                 ref=ref)
        return data

    # ----- ступени задачи (CONTRACT §3.5–§3.6, §4.5) -----

    def _answers_map(self, tx, case_id):
        out = {}
        for a in tx.q("SELECT a.*, e.task_id AS task_id FROM rc_answer a JOIN rc_expect e ON e.exp_id=a.exp_id "
                      "WHERE a.case_id=? ORDER BY a.id", (case_id,)):
            out[a["id"]] = a
        return out

    def _stage_names(self, tx, task_id):
        return set(r["stage"] for r in tx.q("SELECT stage FROM rc_stage WHERE task_id=?", (task_id,)))

    def _stage_check(self, tx, case, task, stage, evidence, by, prior=None):
        binding = self._binding(tx, case) or {}
        others = self._pseudo_rows(self._open_bindings(tx, exclude=case["case_id"], plate=binding.get("plate")))
        ev = dict(evidence)
        kind = R.evidence_kind(ev)                                     # вид — точное слово, одно на Store и правило
        if kind == "human_mark" and isinstance(by, Mapping):
            ev["by"] = {"kind": by.get("kind"), "id": by.get("id")}
        task_d = dict(task)
        task_d["case_id"] = case["case_id"]
        if prior is None:
            prior = self._stage_names(tx, task["task_id"])
        used = set(r["evidence_ref"] for r in tx.q("SELECT evidence_ref FROM rc_stage"))
        answers = self._answers_map(tx, case["case_id"])
        if kind == "human_mark":
            # К4 круг 2 (C26, §3.6, I27): «да»/ответ ЛЮБОГО дела и ответ без дела (карточка брони) — не свидетельство
            # физического выполнения; для сверки act_ref правилу даются все записанные ответы, а не только этого дела
            for a in tx.q("SELECT id, chat, msg_id, case_id FROM rc_answer ORDER BY id"):
                answers.setdefault(a["id"], a)
        return R.stage_allowed(task_d, binding, stage, ev, prior, used, answers, others, self.params)

    def _readback_evidence(self, tx, case, task, evidence):
        """К4 круг 2 (C26): свидетельство readback в record_stage — только чтение назад СВОЕГО ожидания: exp_id
        обязателен, ожидание вида readback этого дела и этой задачи, не отозвано и не отменено; task_id ожидания кладёт
        Store (как on_readback), а не вызывающий. Иные виды свидетельств — без изменений."""
        if R.evidence_kind(evidence) != "readback":
            return evidence
        eid = _s(evidence.get("exp_id"))
        if not eid:
            _stop_rej("evidence_missing", "readback без ожидания чтения назад (exp_id) не свидетельство ступени 5")
        exp = tx.one("SELECT * FROM rc_expect WHERE exp_id=?", (eid,))
        if (exp is None or exp["kind"] != "readback" or exp["case_id"] != case["case_id"]
                or _s(exp["task_id"]) != _s(task["task_id"])):
            _stop_rej("evidence_foreign", "readback не своего ожидания этой задачи", data={"exp_id": eid})
        if exp["state"] in ("superseded", "cancelled"):
            _stop_rej("evidence_foreign", "ожидание чтения назад %s" % exp["state"], data={"exp_id": eid})
        # К4 круг 3 (C26, §3.6 «цель = target ожидания этой задачи»): та же сверка цели, что в on_readback
        tgt = _jl(exp["target"], None)
        if not _target_ok(evidence.get("target"), tgt):
            _stop_rej("readback_mismatch", "цель чтения ≠ цели ожидания этой задачи", data={"exp_id": eid})
        ev = dict(evidence)
        ev["task_id"] = exp["task_id"]
        return ev

    def _post_evidence(self, tx, case, task, evidence):
        """К4 круг 4 (C26, §3.6 post «ожидание этой задачи», §16.10 е): свидетельство post в record_stage — только
        записанный пост ожидания ЭТОЙ задачи: exp_id, chat и msg_id обязательны; ожидание этого дела и этой задачи, не
        отозвано и не отменено; (chat, msg_id) — строка rc_post этого ожидания. task_id ожидания кладёт Store (как
        mark_post_result), а не вызывающий. Иные виды свидетельств — без изменений."""
        if R.evidence_kind(evidence) != "post":
            return evidence
        eid, chat, mid = _s(evidence.get("exp_id")), _s(evidence.get("chat")), _s(evidence.get("msg_id"))
        if not (eid and chat and mid):
            _stop_rej("evidence_missing", "post без ожидания (exp_id) и поста (chat, msg_id) не свидетельство ступени 1")
        exp = tx.one("SELECT * FROM rc_expect WHERE exp_id=?", (eid,))
        if exp is None or exp["case_id"] != case["case_id"] or _s(exp["task_id"]) != _s(task["task_id"]):
            _stop_rej("evidence_foreign", "post не своего ожидания этой задачи", data={"exp_id": eid})
        if exp["state"] in ("superseded", "cancelled"):
            _stop_rej("evidence_foreign", "ожидание поста %s" % exp["state"], data={"exp_id": eid})
        post = tx.one("SELECT exp_id FROM rc_post WHERE chat=? AND msg_id=?", (chat, mid))
        if post is None or post["exp_id"] != eid:
            _stop_rej("evidence_foreign", "пост не записан за этим ожиданием", data={"exp_id": eid})
        ev = dict(evidence)
        ev["task_id"] = exp["task_id"]
        return ev

    def _stage_write(self, tx, case, task, stage, evidence, flags, idem_key, main=False, intent=None, pdf=False):
        n = R.STAGE_NO[stage]
        ref = _s(evidence.get("ref"))
        kind = R.evidence_kind(evidence)
        ev = dict(evidence)
        ev.pop("by", None)
        tx.x("INSERT INTO rc_stage(task_id, case_id, stage, evidence_kind, evidence_ref, evidence, flags, author, at, "
             "case_ver, idem_key) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
             (task["task_id"], case["case_id"], stage, kind, ref, _j(ev), _j(list(flags)),
              tx.author(), tx.now, case["ver"], self._unique_idem(tx, "rc_stage", idem_key)))
        top = task["top_stage"] if task["top_stage"] > n else n
        state = "done" if stage == "result_recorded" else task["state"]
        tx.x("UPDATE rc_task SET top_stage=?, state=?, row_ver=row_ver+1, updated_at=? WHERE task_id=?",
             (top, state, tx.now, task["task_id"]))
        was = task["state"]
        task.update(top_stage=top, state=state, row_ver=task["row_ver"] + 1, updated_at=tx.now)
        tx.event("stage_recorded", {"task_id": task["task_id"], "stage": stage, "evidence_kind": kind,
                                    "evidence_ref": ref, "flags": list(flags)}, case_id=case["case_id"], main=main)
        if state == "done" and was != "done":
            tx.event("task_done", {"task_id": task["task_id"], "kind": task["kind"], "ref": ref, "why": stage},
                     case_id=case["case_id"])
        self._stage_closers(tx, case, task, n, ref, intent=intent, pdf=pdf)

    def _stage_closers(self, tx, case, task, n, ref, intent=None, pdf=False):
        out = []
        for o in tx.q("SELECT * FROM rc_obligation WHERE case_id=? AND state IN ('open','unknown') ORDER BY id",
                      (case["case_id"],)):
            write = {"stage": n, "task_kind": task["kind"], "intent": intent, "pdf": pdf}
            v = R.obligation_verdict(o["kind"], o["role"], {"state": o["state"], "outcome": o["outcome"],
                                                            "amount": o["amount"], "currency": o["currency"],
                                                            "direction": o["direction"]},
                                     write=write, params=self.params)
            if v.get("state") == "closed" and v.get("by") == "stage":
                self._obl_set(tx, o, state="closed", closed_by="stage", close_ref=ref, close_author=tx.author())
                tx.event("obligation_settled", self._obl_payload(o, v.get("why") or "stage"), case_id=case["case_id"])
                out.append(o["id"])
        return out

    # ----- блокеры и намерения (правила над видом из базы) -----

    def _required(self, tx, case_id):
        ev = tx.one("SELECT payload FROM rc_event WHERE case_id=? AND type='case_opened' ORDER BY seq LIMIT 1",
                    (case_id,))
        req = (_jl(ev["payload"], {}) or {}).get("required") if ev else None
        if not isinstance(req, list):
            return None
        return [tuple(x) for x in req if isinstance(x, (list, tuple)) and len(x) == 2]

    def _rules_view(self, tx, case):
        cid = case["case_id"]
        obls = []
        for o in tx.q("SELECT * FROM rc_obligation WHERE case_id=? ORDER BY id", (cid,)):
            d = dict(o)
            if o["closed_by"] == "write":
                f = tx.one("SELECT state FROM rc_fact WHERE id=?", (o["close_fact_id"],)) if o["close_fact_id"] else None
                doc = (tx.one("SELECT status FROM rc_document WHERE id=?", (o["close_second_id"],))
                       if o["close_second_id"] else None)
                d["close_fact_state"] = f["state"] if f else None
                d["close_second_status"] = doc["status"] if doc else None
            obls.append(d)
        rental = self._rental(tx, cid) or {}
        rental = dict(rental)
        if rental:
            rental["rental_id"] = rental.get("id")
        return {"case": {"case_id": cid, "ver": case["ver"], "state": case["state"], "link_state": case["link_state"],
                         "attention": bool(case["attention"])},
                "rental": {"current": rental}, "obligations": obls, "required": self._required(tx, cid),
                "expectations": tx.q("SELECT exp_id, kind, action, state FROM rc_expect WHERE case_id=? "
                                     "ORDER BY created_at, exp_id", (cid,)),
                "notices": tx.q("SELECT notice_id, task_id, state, intent FROM rc_notice WHERE case_id=? "
                                "ORDER BY created_at, notice_id", (cid,)),
                "tasks": tx.q("SELECT task_id, kind, state, top_stage, case_ver FROM rc_task WHERE case_id=? "
                              "ORDER BY created_at, task_id", (cid,)),
                "params": self.params}

    def _blockers_tx(self, tx, case):
        """rules.close_blockers + имя обязательства у его блокера ({what, id, why} §5.5 и ещё kind, role — человеку
        видно, ЧТО держит закрытие, например client/notify_final при FINAL_NOTICE_REQUIRED=UNKNOWN)."""
        view = self._rules_view(tx, case)
        out = R.close_blockers(view)
        names = dict((o["id"], (o["kind"], o["role"])) for o in view["obligations"])
        for b in out:
            if isinstance(b, dict) and b.get("what") == "obligation" and b.get("id") in names:
                b.setdefault("kind", names[b["id"]][0])
                b.setdefault("role", names[b["id"]][1])
        return out

    def _allowed_tx(self, tx, case):
        return R.allowed(self._rules_view(tx, case), self.params)

    # ----- бизнес-срок (I43): только при известных WAIT_BEFORE_AGENTS и BUSINESS_HOURS -----

    def _business_due(self, start):
        """Время поста + WAIT_BEFORE_AGENTS секунд, считая только рабочие часы BUSINESS_HOURS = (час_с, час_до) в зоне
        TZ_H. Любой из двух UNKNOWN или непонятной формы → None (срок не рождается)."""
        wait = _num(self._p("WAIT_BEFORE_AGENTS"))
        hours = self._p("BUSINESS_HOURS")
        if wait is None or R.is_unknown(hours) or start is None:
            return None
        try:
            h_from, h_to = float(hours[0]), float(hours[1])
        except (TypeError, ValueError, IndexError, KeyError):
            return None
        if not (0 <= h_from < h_to <= 24):
            return None
        tz = R._known_int(self._p("TZ_H"))
        tz = 7 if tz is None else tz
        t, remain = float(start), float(wait)
        if remain <= 0:
            return t
        for _i in range(20000):
            local = (datetime.datetime.fromtimestamp(t, datetime.timezone.utc)
                     + datetime.timedelta(hours=tz)).replace(tzinfo=None)
            day0 = datetime.datetime(local.year, local.month, local.day)
            o = day0 + datetime.timedelta(hours=h_from)
            c = day0 + datetime.timedelta(hours=h_to)
            if local < o:
                t += (o - local).total_seconds()
                continue
            if local >= c:
                t += (o + datetime.timedelta(days=1) - local).total_seconds()
                continue
            avail = (c - local).total_seconds()
            if remain <= avail:
                return t + remain
            remain -= avail
            t += avail
        return None


    # =================================================================================================================
    # Рестарт и справки для человека (CONTRACT §5, §4.2, I15, I29, I43)
    # =================================================================================================================

    def recover(self, *, by):
        """Только захваты СВОЕЙ роли с ПРЕЖНИМ boot_id: in_flight → flight_unknown, escalating → escalation_unknown,
        drafting → draft_unknown. Ключ recover:<role>:<boot_id>; захватов нет — ok, изменений 0."""
        _need_by(by)
        key = "recover:%s:%s" % (self.role, self.boot_id)
        payload = {"op": "recover", "role": self.role, "boot_id": self.boot_id}

        def body(tx):
            n_exp = n_esc = n_not = 0
            for e in tx.q("SELECT * FROM rc_expect WHERE claimed_by=? AND claim_boot IS NOT NULL AND claim_boot<>? "
                          "AND state IN ('in_flight','escalating') ORDER BY created_at, exp_id",
                          (self.role, self.boot_id)):
                old = e["state"]
                if old == "in_flight":
                    nc = "readback" if e["kind"] == "readback" else "reconcile"
                    self._exp_set(tx, e, state="flight_unknown", next_check=nc)
                    self._exp_event(tx, "expectation_flight_unknown", e, old, why="recover", boot=e["claim_boot"])
                    n_exp += 1
                else:
                    self._exp_set(tx, e, state="escalation_unknown", next_check="human_decision")
                    self._exp_event(tx, "expectation_escalation_unknown", e, old, why="recover", boot=e["claim_boot"])
                    n_esc += 1
            for n in tx.q("SELECT * FROM rc_notice WHERE state='drafting' AND claimed_by=? AND claim_boot IS NOT NULL "
                          "AND claim_boot<>? ORDER BY created_at, notice_id", (self.role, self.boot_id)):
                tx.x("UPDATE rc_notice SET state='draft_unknown', row_ver=row_ver+1, updated_at=? WHERE notice_id=?",
                     (tx.now, n["notice_id"]))
                tx.event("notice_state", {"notice_id": n["notice_id"], "intent": n["intent"], "state_old": "drafting",
                                          "state_new": "draft_unknown", "why": "recover"}, case_id=n["case_id"])
                n_not += 1
            data = {"expect": n_exp, "escalation": n_esc, "notice": n_not, "role": self.role, "boot_id": self.boot_id}
            if n_exp + n_esc + n_not == 0:
                raise _Stop(_out("ok", data=data))
            tx.event("recovered", data, main=True)
            return self._ok(tx, data=data)

        return self._mutate(key, payload, by, body)

    def stuck(self):
        """Для человека: ожидания *_unknown / human_decision, ждущие и захваченные (возраст числом, без порога и без
        перехода — I43), уведомления drafting/draft_unknown, сироты."""

        def body(tx):
            out = []
            for e in tx.q("SELECT * FROM rc_expect WHERE state NOT IN ('planned','answered','superseded','cancelled') "
                          "ORDER BY created_at, exp_id"):
                ws = None
                if e["waiting_since"] is not None:
                    ws = tx.now - e["waiting_since"]
                    ws = ws if ws > 0 else 0.0
                ca = None
                if e["claim_at"] is not None:
                    ca = tx.now - e["claim_at"]
                    ca = ca if ca > 0 else 0.0
                out.append({"what": "expectation", "exp_id": e["exp_id"], "case_id": e["case_id"], "kind": e["kind"],
                            "action": e["action"], "place": e["place"], "state": e["state"],
                            "next_check": e["next_check"], "waiting_for_s": ws, "claim_age_s": ca,
                            "claimed_by": e["claimed_by"], "claim_boot": e["claim_boot"], "ext_qid": e["ext_qid"]})
            for n in tx.q("SELECT * FROM rc_notice WHERE state IN ('drafting','draft_unknown') "
                          "ORDER BY created_at, notice_id"):
                ca = None if n["claim_at"] is None else (tx.now - n["claim_at"] if tx.now > n["claim_at"] else 0.0)
                out.append({"what": "notice", "notice_id": n["notice_id"], "case_id": n["case_id"], "state": n["state"],
                            "claimed_by": n["claimed_by"], "claim_boot": n["claim_boot"], "claim_age_s": ca})
            for o in tx.q("SELECT * FROM rc_reply_unlinked WHERE state='orphan' ORDER BY id"):
                out.append({"what": "orphan", "orphan_id": o["id"], "chat": o["chat"], "msg_id": o["msg_id"],
                            "reply_to": o["reply_to"], "author_id": o["author_id"], "at": o["at"]})
            return out

        return self._read(body)

    def pending_checks(self, *, role):
        """ЧИТАТЕЛЬ next_check (только чтение): readback с next_check='readback' и уведомления draft_unknown роли."""
        if role not in ROLES:
            raise ValueError("role ∈ %r: %r" % (ROLES, role))

        def body(tx):
            out = []
            for e in tx.q("SELECT * FROM rc_expect WHERE kind='readback' AND state IN ('in_flight','waiting',"
                          "'flight_unknown') AND next_check='readback' AND claimed_by=? ORDER BY created_at, exp_id",
                          (role,)):
                out.append({"what": "readback", "exp_id": e["exp_id"], "case_id": e["case_id"], "task_id": e["task_id"],
                            "action": e["action"], "target": _jl(e["target"], {}), "state": e["state"],
                            "claimed_by": e["claimed_by"], "claim_boot": e["claim_boot"],
                            "written_at": e["post_at"], "parent_exp": e["parent_exp"]})
            for n in tx.q("SELECT * FROM rc_notice WHERE state='draft_unknown' AND claimed_by=? "
                          "ORDER BY created_at, notice_id", (role,)):
                out.append({"what": "notice", "notice_id": n["notice_id"], "case_id": n["case_id"], "target": None,
                            "state": n["state"], "claimed_by": n["claimed_by"], "claim_boot": n["claim_boot"],
                            "intent": n["intent"], "case_ver": n["case_ver"]})
            return out

        return self._read(body)

    # =================================================================================================================
    # Дело и идентичность (CONTRACT §5.1)
    # =================================================================================================================

    def _case_of_row(self, tx, row):
        """Строка → дело: booking_id строки → подтверждённая ссылка booking_id → якорь → подтверждённый якорь.
        → (case_id | None, как, исход unknown | None)."""
        bk = _s(row.get("booking_id")) or None
        anchor = R.anchor_of(row)
        if bk:
            owner = self._link_owner(tx, "booking_id", bk)
            if owner is not None:
                if anchor:
                    aown = self._link_owner(tx, "anchor", anchor)
                    if aown is not None and aown != owner:
                        return None, None, _unknown(
                            "link_confirmation", ["link_confirmation"],
                            "Номер брони строки ведёт в одно дело, а байк, день и имя — в другое: это одна аренда?",
                            data={"cases": [owner, aown]})
                return owner, "booking_id", None
        if anchor:
            aown = self._link_owner(tx, "anchor", anchor)
            if aown is not None:
                obk = self._booking(tx, aown)
                if obk and obk != bk:
                    return None, None, _unknown(
                        "link_confirmation", ["link_confirmation"],
                        "Байк, день и имя строки совпали с делом, у которого другой номер брони — это та же аренда?",
                        data={"case_id": aown})
                return aown, "anchor", None
        return None, None, None

    def _superseded_only(self, tx, contact):
        """Номер обращения есть только как superseded-контакт (ни одного active ни в одном деле)."""
        if self._contact_cases(tx, contact, open_only=False):
            return False
        channel = _s(contact.get("channel")) or "wa"
        value = self._norm_contact(channel, contact.get("value"))
        kd = R._known_int(self._p("KEY_DIGITS")) or 9
        for c in tx.q("SELECT channel, value FROM rc_contact WHERE status='superseded'"):
            if channel in ("wa", "phone_crm") and c["channel"] in ("wa", "phone_crm"):
                if len(value) >= kd and len(c["value"]) >= kd and c["value"][-kd:] == value[-kd:]:
                    return True
            elif c["channel"] == channel and c["value"] == value:
                return True
        return False

    @staticmethod
    def _binding_out(b):
        if not b:
            return None
        out = dict((k, b.get(k)) for k in ("rental_id", "booking_id", "anchor", "plate", "bike_name", "model_req",
                                            "name_seen", "start_at", "end_at", "start_day", "end_day", "days",
                                            "status_seen", "crm_row_seen", "bound_by", "observed_at", "read_at"))
        return out

    def resolve(self, *, purpose, rows, moment, observed_at, intent=None, row=None, contact=None, booking_id=None,
                plate=None, on_day=None, period=None, contract_date=None, cash_day=None):
        """ЕДИНСТВЕННАЯ функция «строка/контакт/номер → дело» (I38). Только чтение."""
        if purpose not in R.PURPOSES:
            raise ValueError("purpose ∈ %r: %r" % (R.PURPOSES, purpose))

        def res(code, **kw):
            out = {"code": code, "case_id": None, "ver": None, "rental": None, "row": None, "pick": None,
                   "missing": [], "ask": "", "reason": "", "candidates": [], "observed_at": observed_at}
            out.update(kw)
            if code == "unknown":
                out["missing"] = list(out["missing"]) or [out["reason"].split(":")[0] or "which_rental"]
                out["ask"] = out["ask"] or _ask_for(out["reason"].split(":")[0])
            return out

        def body(tx):
            if purpose == "client":
                if not isinstance(contact, Mapping) or not _s(contact.get("value")):
                    return res("unknown", reason="contact", missing=["contact"],
                               ask="С какого номера или под каким именем оформлена аренда?")
                if self._superseded_only(tx, contact):
                    return res("none", reason="contact_superseded")
            the_row, pk = row, None
            if the_row is None:
                q = {"purpose": purpose, "intent": intent, "contact": contact, "booking_id": booking_id, "plate": plate,
                     "on_day": on_day, "period": period, "contract_date": contract_date, "cash_day": cash_day}
                pk = R.pick(rows or [], q, moment, self.params)
                if pk.get("code") != "found":
                    return res("unknown", pick=pk, reason=pk.get("reason") or "rental_ambiguous",
                               missing=pk.get("missing") or [], ask=pk.get("ask") or "",
                               candidates=pk.get("candidates") or [])
                the_row = pk.get("row")
            if not isinstance(the_row, Mapping):
                raise ValueError("row — строка двери clients")
            pend = self._pending_confirm_for_row(tx, the_row)
            if pend is not None:
                subj = _jl(pend.get("subject"), {}) or {}
                return res("unknown", row=the_row, pick=pk, reason="link_confirmation", missing=["link_confirmation"],
                           ask=subj.get("question") or _ask_for("link_confirmation"), case_id=None,
                           candidates=[{"case_id": pend["case_id"], "exp_id": pend["exp_id"]}])
            cid, how, bad = self._case_of_row(tx, the_row)
            if bad is not None:
                bad.update(row=the_row, pick=pk, case_id=None, rental=None, candidates=[], observed_at=observed_at)
                return bad
            if cid is None:
                cands = R.continuation(the_row, self._open_bindings(tx), self.params)
                if cands:
                    return res("unknown", row=the_row, pick=pk, reason="link_confirmation",
                               missing=["link_confirmation"], candidates=cands,
                               ask="Строка может быть продолжением открытого дела — это та же аренда или новая?")
                return res("none", row=the_row, pick=pk, reason="")
            case = self._case(tx, cid)
            if purpose == "client":
                st = self._contact_status(tx, cid, contact)
                if st == "superseded":
                    return res("none", row=the_row, pick=pk, reason="contact_superseded")
                if st != "active":
                    return res("unknown", row=the_row, pick=pk, reason="contact", missing=["contact"],
                               ask="Номер обращения не подтверждён в деле этой аренды — на какой номер она оформлена?")
            b = self._binding(tx, case)
            return res("found", case_id=cid, ver=case["ver"], rental=self._binding_out(b), row=the_row, pick=pk,
                       matched_by=how, state=case["state"], link_state=case["link_state"])

        return self._read(body)

    def open_case(self, *, origin, by, idem_key, booking_id=None, rental_row=None, contacts=(), source=None,
                  model_req=None, force_new=False):
        """Дело рождается ровно здесь: case_id = 'RC-' + new_id() (I1); обязательный набор — той же транзакцией (I25)."""
        if origin not in ORIGINS:
            raise ValueError("origin ∈ %r: %r" % (ORIGINS, origin))
        _need_by(by)
        _need_idem(idem_key)
        if not isinstance(rental_row, Mapping):
            raise ValueError("rental_row — строка двери clients (CONTRACT §1.2 Row)")
        _need_source(source)
        cts = []
        for c in contacts or ():
            if not isinstance(c, Mapping) or c.get("channel") not in CONTACT_CHANNELS or not _s(c.get("value")):
                raise ValueError("contacts — [{channel ∈ %r, value}]" % (CONTACT_CHANNELS,))
            cts.append({"channel": c.get("channel"), "value": _s(c.get("value"))})
        row = dict(rental_row)
        payload = {"op": "open_case", "origin": origin, "by": _by_key(by), "booking_id": booking_id, "rental_row": row,
                   "contacts": cts, "source": _src_key(source), "model_req": model_req, "force_new": bool(force_new)}

        def mint():
            return "RC-" + self.new_id()

        def body(tx):
            return self._open_case_tx(tx, origin, by, booking_id, row, cts, source, model_req, bool(force_new), mint)

        return self._mutate(idem_key, payload, by, body, dup=lambda d: dict(d, case_id=d.get("case_id")))

    def _open_case_tx(self, tx, origin, by, booking_id, row, contacts, source, model_req, force_new, mint):
        c = R.classify(row, float(source["observed_at"]), self.params)
        row_bk = _s(row.get("booking_id")) or None
        if booking_id is not None and _s(booking_id) and row_bk and row_bk != _s(booking_id):
            raise _ArgError("booking_id аргумента ≠ Y строки: %r / %r" % (booking_id, row_bk))
        bk = _s(booking_id) or row_bk
        if not c["plate"]:
            _stop_rej("no_plate", "в строке нет номера байка")
        if c["start_day"] is None and bk is None:
            _stop_rej("no_start", "нет даты начала и нет booking_id")
        if force_new and not self._approver(by):
            _stop_rej("approver_unknown", "force_new — только одобряющий по id")
        if bk:
            owner = self._link_owner(tx, "booking_id", bk)
            if owner is not None:
                _stop_rej("booking_taken", data={"case_id": owner})
        anchor = c["anchor"]
        sha = R.cand_sha_of([row])
        if anchor:
            owner = self._link_owner(tx, "anchor", anchor)
            if owner is not None:
                oc = self._case(tx, owner)
                obk = self._booking(tx, owner)
                if oc["state"] == "open" and obk and obk != bk:
                    q = ("Строка %s (%s, %s, «%s») совпала с делом по байку, дню и имени, но номер брони другой — "
                         "это та же аренда?" % (row.get("row"), _s(row.get("bike")), _dm(row.get("date_start")),
                                               _s(row.get("name"))))
                    exp, created = self._confirm_link(tx, oc, [row], sha, q, "anchor_conflict", "link_confirmation",
                                                      main=True)
                    raise _Stop(_unknown("link_confirmation", ["link_confirmation"], q,
                                         data={"case_id": owner, "exp_id": exp["exp_id"]}), commit=created)
                _stop_rej("anchor_taken", data={"case_id": owner})
        bindings = self._open_bindings(tx)
        cands = [] if force_new else R.continuation(row, bindings, self.params)
        if cands:
            created_any, exps, whys = False, [], []
            for cnd in cands:
                oc = self._case(tx, cnd["case_id"])
                ob = self._binding(tx, oc) or {}
                q = ("Бронь %s с %s (%s, строка %s) — продолжение или подмена аренды %s %s–%s, или новая аренда?%s"
                     % (_s(row.get("bike")) or c["plate"], _dm(row.get("date_start")), _s(row.get("name")) or "—",
                        row.get("row"), ob.get("bike_name") or ob.get("plate") or "?", _dm(ob.get("start_day")),
                        _dm(ob.get("end_day")),
                        " (касание днём возврата: CONTINUATION_GAP_DAYS не принят)"
                        if str(cnd.get("why")).startswith("param_unknown") else ""))
                exp, created = self._confirm_link(tx, oc, [row], sha, q, "continuation", cnd.get("why") or "",
                                                  extra={"gap_days": cnd.get("gap_days"),
                                                         "continuation_why": cnd.get("why")},
                                                  main=created_any is False)
                if created:
                    created_any = True
                exps.append({"case_id": cnd["case_id"], "exp_id": exp["exp_id"], "why": cnd.get("why"),
                             "gap_days": cnd.get("gap_days"), "question": q})
                whys.append(_s(cnd.get("why")))
            one = exps[0] if len(exps) == 1 else None
            data = {"case_id": one["case_id"] if one else None, "exp_id": one["exp_id"] if one else None,
                    "cases": [x["case_id"] for x in exps], "exp_ids": [x["exp_id"] for x in exps], "candidates": exps}
            raise _Stop(_unknown("possible_continuation", ["continuation"], " / ".join(x["question"] for x in exps),
                                 data=data, case_id=data["case_id"], words=", ".join(w for w in whys if w)),
                        commit=created_any)
        approver = self._approver(by)
        if not bk and not anchor:
            if not approver:
                _stop_unk("link_missing", ["booking_id"],
                          "У строки нет номера брони и якоря (имя — заглушка): по чему находить это дело? "
                          "Нужен номер брони или решение одобряющего.")
        bound_by = "booking_id" if bk else ("anchor" if anchor else "human")
        case_id = mint()
        tx.x("INSERT INTO rc_case(case_id, ver, state, link_state, attention, pause_no, origin, created_at, created_by, "
             "updated_at) VALUES (?,1,'open','ok',0,0,?,?,?,?)", (case_id, origin, tx.now, tx.author(), tx.now))
        case = self._case(tx, case_id)
        rid = self._insert_rental(tx, case_id, row, source, bound_by, 1, booking_id=bk, model_req=model_req)
        sname, sref = _s(source["name"]), _s(source["ref"])
        tx.event("rental_bound", {"rental_id": rid, "prev_rental_id": None, "booking_id": bk, "anchor": anchor,
                                  "bound_by": bound_by, "why": "open_case"}, case_id=case_id, source=sname, ref=sref)
        if bk:
            self._link_set(tx, case, "booking_id", bk, "confirmed", sname, sref, "open_case")
        if anchor:
            self._link_set(tx, case, "anchor", anchor, "confirmed", sname, sref, "open_case")
        if _int_id(row.get("row")):
            self._link_set(tx, case, "crm_row", str(row.get("row")), "candidate", sname, sref, "open_case")
        for n in R.phones_full(row.get("contacts")):
            self._contact_add(tx, case, "wa", n, "crm", source, "crm_U")
        cand_contacts = []
        for ct in contacts:
            if approver:
                self._contact_add(tx, case, ct["channel"], ct["value"], "human", source, "approver")
            else:
                cand_contacts.append({"channel": ct["channel"], "value_masked": _mask(ct["value"])})
        obligations, documents, required = [], [], []
        for ob in R.required_obligations(row, self.params):
            key = self._unique_idem(tx, "rc_obligation", "%s#obl:%s:%s" % (tx.key, ob["kind"], ob["role"]))
            o = self._obl_insert(tx, case, ob["kind"], ob["role"], ob["direction"], ob["state"], ob.get("outcome"),
                                 ob.get("amount"), ob.get("currency"), True, source, key, ob.get("why") or "required")
            obligations.append(o["id"])
            required.append([ob["kind"], ob["role"]])
            doc = ob.get("document")
            if isinstance(doc, Mapping):
                did = self._doc_insert(tx, case, doc.get("kind"), doc.get("ext_id"), doc.get("status") or "unverified",
                                       source, rental_id=rid, why="deposit_passport")
                documents.append(did)
        big = dict(self.params)
        big["CONTINUATION_GAP_DAYS"] = 10 ** 6
        near = []
        for x in R.continuation(row, bindings, big):
            if x.get("case_id") and x["case_id"] not in near:
                near.append(x["case_id"])
        data = {"case_id": case_id, "rental_id": rid, "obligations": obligations, "documents": documents,
                "near_cases": near}
        tx.event("case_opened", {"case_id": case_id, "origin": origin, "booking_id": bk, "anchor": anchor,
                                 "rental_id": rid, "obligations": obligations, "documents": documents,
                                 "near_cases": near, "required": required, "contact_candidates": cand_contacts,
                                 "force_new": force_new},
                 case_id=case_id, ver_after=1, source=sname, ref=sref, main=True)
        return self._ok(tx, case_id, 1, data=data)

    def _doc_insert(self, tx, case, kind, ext_id, status, source, rental_id=None, sha256=None, signed_at=None,
                    reg_row=None, bound_by=None, why="", extra=None, main=False):
        """Строка rc_document БЕЗ покрытия: cover_* здесь не пишутся никогда (I46; пишет только
        confirm_document_coverage)."""
        cur = tx.x("INSERT INTO rc_document(case_id, kind, ext_id, reg_row, sha256, signed_at, status, bound_by, "
                   "rental_id, source, read_at, author, case_ver, reason, ref, method, observed_at) "
                   "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (case["case_id"], kind, ext_id, reg_row, sha256, signed_at, status, bound_by, rental_id,
                    _s(source["name"]), float(source["read_at"]), tx.author(), case["ver"], None, _s(source["ref"]),
                    source["method"], float(source["observed_at"])))
        did = cur.lastrowid
        payload = {"document_id": did, "kind": kind, "ext_id": ext_id, "sha256": sha256, "signed_at": signed_at,
                   "status": status, "rental_id": rental_id, "bound_by": bound_by, "why": why}
        if extra:
            payload.update(extra)
        tx.event("document_recorded", payload, case_id=case["case_id"], source=_s(source["name"]),
                 ref=_s(source["ref"]), main=main)
        return did

    def decide_link(self, exp_id, *, decision, by, idem_key, expect_ver, row=None, source=None):
        """Решение одобряющего по confirm_link: same — перепривязка на строку кандидата с подъёмом; new — новое дело
        кандидату (open_case force_new); none — ожидание answered, link_state прежний."""
        _need_by(by)
        _need_idem(idem_key)
        if decision not in ("same", "new", "none"):
            raise ValueError("decision ∈ {same, new, none}: %r" % (decision,))
        if row is not None and not isinstance(row, Mapping):
            raise ValueError("row — строка двери clients")
        if source is not None:
            _need_source(source)
        payload = {"op": "decide_link", "exp_id": exp_id, "decision": decision, "by": _by_key(by),
                   "expect_ver": expect_ver, "row": dict(row) if row is not None else None,
                   "source": _src_key(source) if source is not None else None}

        def body(tx):
            if not self._approver(by):
                _stop_rej("approver_unknown", "decide_link — только одобряющий по id")
            exp = self._need_exp(tx, exp_id)
            if exp["kind"] != "confirm_link":
                _stop_rej("bad_transition", "decide_link только для confirm_link")
            case = self._need_case(tx, exp["case_id"])
            self._check_ver(case, expect_ver)
            if exp["state"] in ("superseded", "cancelled"):
                _stop_rej("expect_state", exp["state"])
            if exp["state"] == "answered":
                ans = tx.one("SELECT * FROM rc_answer WHERE id=?", (exp["answer_id"],)) if exp["answer_id"] else None
                if ans is None or ans["verdict"] != "accepted":
                    _stop_rej("expect_state", "ожидание закрыто не принятым ответом")
                if (ans["decision"] == "yes") != (decision == "same"):
                    _stop_rej("bad_transition", "решение не соответствует ответу одобряющего (%s)" % ans["decision"])
            else:
                old = exp["state"]
                self._exp_set(tx, exp, state="answered", next_check="none")
                self._exp_event(tx, "expectation_answered", exp, old, why="decide_link:%s" % decision)
            cand_rows = (_jl(exp.get("target"), {}) or {}).get("rows") or []
            the_row = dict(row) if row is not None else (dict(cand_rows[0]) if len(cand_rows) == 1 else None)
            src = dict(source) if source is not None else {
                "name": "решение одобряющего (decide_link)", "ref": "decide_link:%s" % exp_id, "method": "human",
                "read_at": tx.now, "observed_at": tx.now}
            data = {"exp_id": exp_id, "decision": decision, "case_id": case["case_id"]}
            if decision == "same":
                if the_row is None:
                    _stop_unk("which_rental", ["which_rental"], "Какая строка — та же аренда (кандидатов несколько)?")
                info = self._rebind(tx, case, the_row, src, why="decide_link:same")
                self._link_state(tx, case, "ok", why="decide_link:same")
                data.update(info)
            elif decision == "new":
                if the_row is None:
                    _stop_unk("which_rental", ["which_rental"], "Для какой строки открыть новое дело?")
                data["new_case"] = self._decide_new_case(tx, by, the_row, src, data)
            tx.event("link_decided", data, case_id=case["case_id"], exp_id=exp_id, main=True)
            return self._ok(tx, case["case_id"], case["ver"], data=data)

        return self._mutate(idem_key, payload, by, body)

    def _decide_new_case(self, tx, by, row, src, link_data):
        """decide_link(new): дело кандидату открывается В ТОЙ ЖЕ транзакции (I6) — open_case(force_new) одобряющего с
        ключом `<ключ решения>#open` (главное событие case_opened этого ключа). Отказ или вопрос при открытии
        (booking_taken, anchor_taken, link_confirmation, no_plate/no_start) — исход всего вызова, ROLLBACK целиком:
        решение без дела не записывается наполовину."""
        sub_key = "%s#open" % tx.key
        sub_payload = {"op": "open_case", "origin": "human", "by": _by_key(by), "booking_id": None,
                       "rental_row": dict(row), "contacts": [], "source": _src_key(src), "model_req": None,
                       "force_new": True}
        sub = _Tx(self, tx.con, sub_key, _sha(sub_payload), by, tx.now)
        try:
            op = self._open_case_tx(sub, "human", by, None, dict(row), [], src, None, True,
                                    lambda: "RC-" + self.new_id())
        except _Stop as st:
            o = dict(st.outcome)
            d = dict(o.get("data") or {})
            if st.commit and "exp_id" in d:           # К4 круг 4: вопрос записан в ЭТОЙ транзакции и уходит с ROLLBACK —
                d["exp_id"] = None                    # исход не называет ожидание, которого после вызова нет (§1.2)
            d["decide_link"] = dict(link_data)
            o["data"] = d
            raise _Stop(o, commit=False)
        tx.events.extend(sub.events)
        return {"case_id": op["case_id"], "rental_id": (op.get("data") or {}).get("rental_id"),
                "event_seq": op.get("event_seq"), "idem_key": sub_key}

    def _rebind(self, tx, case, row, source, why, reason=None, main=False):
        """Перепривязка дела на строку (одобряющий): ссылки, подъём, новая привязка current=1, история."""
        cid = case["case_id"]
        old = self._rental(tx, cid)
        c = R.classify(row, float(source["observed_at"]), self.params)
        bk = _s(row.get("booking_id")) or None
        if not c["plate"]:
            _stop_rej("no_plate")
        if c["start_day"] is None and bk is None:
            _stop_rej("no_start")
        anchor = c["anchor"]
        sname, sref = _s(source["name"]), _s(source["ref"])
        retired = []
        for l in tx.q("SELECT * FROM rc_link WHERE case_id=? AND kind IN ('booking_id','anchor') AND status='confirmed' "
                      "ORDER BY id", (cid,)):
            if (l["kind"] == "booking_id" and l["value"] != bk) or (l["kind"] == "anchor" and l["value"] != anchor):
                self._link_set(tx, case, l["kind"], l["value"], "retired", sname, sref, why)
                retired.append({"kind": l["kind"], "value": l["value"]})
        if bk:
            self._link_set(tx, case, "booking_id", bk, "confirmed", sname, sref, why)
        if anchor:
            self._link_set(tx, case, "anchor", anchor, "confirmed", sname, sref, why)
        if _int_id(row.get("row")):
            self._link_set(tx, case, "crm_row", str(row.get("row")), "candidate", sname, sref, why)
        plate_changed = old is not None and old["plate"] != c["plate"]
        period_changed = old is not None and (old["start_day"] != c["start_day"] or old["end_day"] != c["end_day"])
        if reason is None:
            reason = "bike_changed" if plate_changed else ("period_changed" if period_changed else "rental_rebind")
        vb = case["ver"]
        bump = self._bump(tx, case, reason, sref, source_name=sname)
        va = case["ver"]
        rid = self._insert_rental(tx, cid, row, source, "human", va, booking_id=bk,
                                  model_req=old["model_req"] if old else None)
        tx.event("rental_rebound", {"rental_id": rid, "prev_rental_id": old["id"] if old else None, "booking_id": bk,
                                    "anchor": anchor, "bound_by": "human", "why": why, "retired": retired},
                 case_id=cid, ver_before=vb, ver_after=va, source=sname, ref=sref, main=main)
        if plate_changed:
            tx.event("bike_changed", {"rental_id": rid, "old": old["bike_name"], "new": _s(row.get("bike")),
                                      "plate_old": old["plate"], "plate_new": c["plate"], "why": why},
                     case_id=cid, ver_before=vb, ver_after=va, source=sname, ref=sref)
        if period_changed:
            tx.event("period_changed", {"rental_id": rid, "old": [old["start_day"], old["end_day"]],
                                        "new": [c["start_day"], c["end_day"]], "days_old": old["days"],
                                        "days_new": c["days"], "why": why},
                     case_id=cid, ver_before=vb, ver_after=va, source=sname, ref=sref)
        for n in R.phones_full(row.get("contacts")):
            self._contact_add(tx, case, "wa", n, "crm", source, "crm_U:" + why)
        return {"rental_id": rid, "prev_rental_id": old["id"] if old else None, "bumped": reason,
                "superseded": bump["superseded"], "cancelled_tasks": bump["cancelled_tasks"],
                "staff_qids_to_close": bump["staff_qids_to_close"]}

    def find_cases(self, *, booking_id=None, anchor=None, contact=None, plate=None, include_closed=False,
                   include_superseded=False):
        """Поиск для ЧЕЛОВЕКА (не для автоматики, I38)."""

        def body(tx):
            hits = []

            def add(cid, how):
                for h in hits:
                    if h[0] == cid:
                        return
                hits.append((cid, how))

            if booking_id:
                for r in tx.q("SELECT case_id FROM rc_link WHERE kind='booking_id' AND value=? AND status IN "
                              "('confirmed','candidate') ORDER BY id", (_s(booking_id),)):
                    add(r["case_id"], "booking_id")
            if anchor:
                for r in tx.q("SELECT case_id FROM rc_link WHERE kind='anchor' AND value=? ORDER BY id", (anchor,)):
                    add(r["case_id"], "anchor")
            if plate:
                for r in tx.q("SELECT DISTINCT case_id FROM rc_rental WHERE plate=? ORDER BY case_id", (_s(plate),)):
                    add(r["case_id"], "plate")
            if isinstance(contact, Mapping) and _s(contact.get("value")):
                channel = _s(contact.get("channel")) or "wa"
                value = self._norm_contact(channel, contact.get("value"))
                for r in tx.q("SELECT case_id, channel, value, status FROM rc_contact ORDER BY id"):
                    if r["status"] == "superseded" and not include_superseded:
                        continue
                    if channel in ("wa", "phone_crm") and r["channel"] in ("wa", "phone_crm"):
                        if R.contact_match(r["value"], value, R._known_int(self._p("KEY_DIGITS")) or 9) == "none":
                            continue
                    elif r["channel"] != channel or r["value"] != value:
                        continue
                    add(r["case_id"], "contact")
            out = []
            for cid, how in hits:
                c = self._case(tx, cid)
                if c is None or (c["state"] != "open" and not include_closed):
                    continue
                out.append({"case_id": cid, "ver": c["ver"], "state": c["state"], "link_state": c["link_state"],
                            "matched_by": how, "rental": self._binding_out(self._binding(tx, c))})
            return out

        return self._read(body)

    def add_contact(self, case_id, *, channel, value, by, source, idem_key, supersede_value=None):
        """Контакт добавляет только сверка CRM (by.kind=source, источник «клиенты») или одобряющий (I36)."""
        if channel not in CONTACT_CHANNELS:
            raise ValueError("channel ∈ %r: %r" % (CONTACT_CHANNELS, channel))
        if not _s(value):
            raise ValueError("value — непустой")
        if not self._norm_contact(channel, value):                 # К4 круг 4: нет значения контакта — не «ok» (§1.3)
            raise ValueError("value — в канале %s нет значения контакта (номер без цифр)" % channel)
        _need_by(by)
        _need_source(source)
        payload = {"op": "add_contact", "case_id": case_id, "channel": channel, "value": _s(value), "by": _by_key(by),
                   "source": _src_key(source), "supersede_value": supersede_value}

        def body(tx):
            case = self._need_case(tx, case_id)
            sname = _s(source.get("name")).lower()
            if by.get("kind") == "source" and ("клиент" in sname or "clients" in sname or "crm" in sname):
                sk = "crm"
            elif self._approver(by):
                sk = "human"
            else:
                _stop_rej("contact_source", "контакт добавляет только сверка CRM или одобряющий по id")
            sup = 0
            if supersede_value:
                sup = self._contact_supersede(tx, case, channel, supersede_value, "supersede_value", source)
            self._contact_add(tx, case, channel, value, sk, source, "add_contact", main=True)
            return self._ok(tx, case_id, case["ver"], data={"channel": channel, "value_masked": _mask(value),
                                                            "source_kind": sk, "superseded": sup})

        return self._mutate(idem_key, payload, by, body)

    def _others(self, tx, case, rows):
        """Привязки других открытых дел и дела с подтверждённым booking_id строк (rules.reconcile). По номеру байка их
        отбирает само правило — по номеру СТРОКИ дела (rules._period_conflicts): при смене байка он новый, поэтому
        отбор по номеру прежней привязки здесь терял дело на новом байке (К4 круг 4, I-21)."""
        out, seen = [], set()
        for b in self._open_bindings(tx, exclude=case["case_id"]):
            out.append({"case_id": b["case_id"], "booking_id": self._booking(tx, b["case_id"]) or b.get("booking_id"),
                        "plate": b.get("plate"), "start_day": b.get("start_day"), "end_day": b.get("end_day"),
                        "status_seen": b.get("status_seen")})
            seen.add(b["case_id"])
        for r in rows:
            y = _s(r.get("booking_id"))
            if not y:
                continue
            owner = self._link_owner(tx, "booking_id", y, case["case_id"])
            if owner is None or owner in seen:
                continue
            oc = self._case(tx, owner)
            ob = self._rental(tx, owner) or {}
            out.append({"case_id": owner, "booking_id": y, "plate": ob.get("plate"), "start_day": ob.get("start_day"),
                        "end_day": ob.get("end_day"),
                        "status_seen": ob.get("status_seen") if oc and oc["state"] == "open" else "завершена"})
            seen.add(owner)
        return out

    def reconcile_rental(self, case_id, *, rows, source, by, idem_key):
        """Сверка привязки с новым чтением (DESIGN §2.3, rules.reconcile). Не новее применённого — ok(stale_read)."""
        _need_by(by)
        _need_source(source)
        if rows is None or isinstance(rows, (str, bytes)):
            raise ValueError("rows — список строк двери clients")
        rows = [dict(r) for r in rows if isinstance(r, Mapping)]
        payload = {"op": "reconcile_rental", "case_id": case_id, "rows": rows, "source": _src_key(source),
                   "by": _by_key(by)}

        def body(tx):
            case = self._need_case(tx, case_id)
            b = self._binding(tx, case)
            obs = float(source["observed_at"])
            if b is None:
                _stop_rej("rental_not_found", "у дела нет привязки")
            if obs <= float(b["observed_at"]):
                raise _Stop(_out("ok", case_id=case_id, ver=case["ver"], reason="stale_read",
                                 data={"stale_read": True, "applied_observed_at": b["observed_at"]}))
            others = self._others(tx, case, rows)
            res = R.reconcile(b, rows, obs, others, self.params)
            code = res.get("code")
            if code == "stale":
                raise _Stop(_out("ok", case_id=case_id, ver=case["ver"], reason="stale_read",
                                 data={"stale_read": True}))
            if code in ("same", "changed"):
                return self._reconcile_apply(tx, case, b, res, rows, source)
            return self._reconcile_unknown(tx, case, b, res, rows)

        return self._mutate(idem_key, payload, by, body)

    def _reconcile_apply(self, tx, case, b, res, rows, source):
        cid = case["case_id"]
        row = res.get("row") or {}
        changes = res.get("changes") or {}
        sname, sref = _s(source["name"]), _s(source["ref"])
        for l in res.get("link_add") or []:                        # К4 круг 4: чужой номер брони/якорь — отказ ДО
            self._link_free(tx, case, l["kind"], l["value"])       # подъёма: ver отказа — версия дела после вызова
        vb = case["ver"]
        bumped = None
        if res.get("bump_reason"):
            bumped = self._bump(tx, case, res["bump_reason"], sref, source_name=sname)
        va = case["ver"]
        for l in res.get("link_retire") or []:
            self._link_set(tx, case, l["kind"], l["value"], "retired", sname, sref, "reconcile")
        new_bk = b.get("booking_id")
        for l in res.get("link_add") or []:
            self._link_set(tx, case, l["kind"], l["value"], "confirmed", sname, sref, "reconcile")
            if l["kind"] == "booking_id":
                new_bk = l["value"]
        rental_change = bool(set(changes) & set(("plate", "start_day", "end_day", "name_norm", "start_at", "end_at",
                                                   "status_seen", "crm_row_seen"))) or new_bk != b.get("booking_id")
        rid = b["rental_id"]
        if rental_change:
            rid = self._insert_rental(tx, cid, row, source, b["bound_by"], va, booking_id=new_bk,
                                      model_req=b.get("model_req"))
            tx.event("rental_bound", {"rental_id": rid, "prev_rental_id": b["rental_id"], "booking_id": new_bk,
                                      "anchor": R.anchor_of(row), "bound_by": b["bound_by"], "why": "reconcile"},
                     case_id=cid, source=sname, ref=sref)
            if "plate" in changes:
                tx.event("bike_changed", {"rental_id": rid, "old": b.get("bike_name"), "new": _s(row.get("bike")),
                                          "plate_old": changes["plate"]["old"], "plate_new": changes["plate"]["new"]},
                         case_id=cid, ver_before=vb, ver_after=va, source=sname, ref=sref)
            if "start_day" in changes or "end_day" in changes:
                c = R.classify(row, float(source["observed_at"]), self.params)
                tx.event("period_changed", {"rental_id": rid, "old": [b.get("start_day"), b.get("end_day")],
                                            "new": [c["start_day"], c["end_day"]], "days_old": b.get("days"),
                                            "days_new": c["days"]},
                         case_id=cid, ver_before=vb, ver_after=va, source=sname, ref=sref)
            if "status_seen" in changes:
                tx.event("status_seen_changed", {"rental_id": rid, "old": changes["status_seen"]["old"],
                                                 "new": changes["status_seen"]["new"]},
                         case_id=cid, ver_before=vb, ver_after=va, source=sname, ref=sref)
        else:
            tx.x("UPDATE rc_rental SET source=?, ref=?, method=?, read_at=?, observed_at=? WHERE id=?",
                 (sname, sref, source["method"], float(source["read_at"]), float(source["observed_at"]), rid))
            tx.event("rental_read", {"rental_id": rid, "observed_at": float(source["observed_at"]),
                                     "why": res.get("code")}, case_id=cid, source=sname, ref=sref)
        added, superseded = [], []
        for n in res.get("contacts_add") or []:
            if self._contact_add(tx, case, "wa", n, "crm", source, "crm_U_added"):
                added.append(_mask(n))
        for v in res.get("contacts_supersede") or []:
            if self._contact_supersede(tx, case, "wa", v, "crm_U_removed", source):
                superseded.append(_mask(v))
        if res.get("attention"):
            self._attention_on(tx, case, "conflict", "status_drift")
        self._link_state(tx, case, "ok", why="reconcile:%s" % res.get("code"))
        data = {"changes": changes, "bumped": bool(bumped), "bump_reason": res.get("bump_reason"),
                "link_state": case["link_state"], "contacts": {"added": added, "superseded": superseded},
                "rental_id": rid, "attention": bool(res.get("attention"))}
        if bumped:
            data.update(superseded=bumped["superseded"], cancelled_tasks=bumped["cancelled_tasks"],
                        staff_qids_to_close=bumped["staff_qids_to_close"])
        tx.event("rental_reconciled", dict(data, code=res.get("code")), case_id=cid, source=sname, ref=sref, main=True)
        return self._ok(tx, cid, case["ver"], data=data)

    def _reconcile_unknown(self, tx, case, b, res, rows):
        cid = case["case_id"]
        code = res.get("code")
        reason = {"drift": "link_confirmation", "ambiguous": "which_rental"}.get(code, "rental_not_found")
        ids = res.get("candidates") or []
        cand_rows = []
        for r in rows:
            for c in ids:
                if (c.get("row") == r.get("row") and (c.get("booking_id") or None) == (_s(r.get("booking_id")) or None)
                        and c.get("anchor") == R.anchor_of(r)):
                    cand_rows.append(r)
                    break
        ask = res.get("ask") or _ask_for(reason)
        exp, created = self._confirm_link(tx, case, cand_rows, res.get("cand_sha") or R.cand_sha_of(cand_rows), ask,
                                          code, res.get("reason") or code)
        ls = self._link_state(tx, case, res.get("link_state") or "drift", exp["exp_id"], why=res.get("reason") or code)
        att = False
        if res.get("attention"):
            att = self._attention_on(tx, case, "conflict", "rental_conflict") or att
            for oc_id in res.get("conflict_cases") or []:
                if oc_id == cid:
                    continue
                oc = self._case(tx, oc_id)
                if oc is not None and oc["state"] == "open":
                    att = self._attention_on(tx, oc, "conflict", "rental_conflict:%s" % cid) or att
        wrote = created or ls or bool(res.get("attention"))
        data = {"exp_id": exp["exp_id"], "candidates": ids, "link_state": case["link_state"],
                "conflict_cases": res.get("conflict_cases") or [], "why": res.get("reason"),
                "changes": res.get("changes") or {}}
        if wrote:
            tx.event("rental_reconciled", dict(data, code=code), case_id=cid, exp_id=exp["exp_id"], main=True)
        raise _Stop(_unknown(reason, res.get("missing") or [reason], ask, data=data, case_id=cid, ver=case["ver"],
                             words=res.get("reason") or ""), commit=wrote)

    def rebind_rental(self, case_id, *, row, reason, by, source, idem_key, expect_ver):
        """Перепривязка одобряющим (rental_rebind|bike_changed|period_changed); link_state=ok."""
        if reason not in ("rental_rebind", "bike_changed", "period_changed"):
            raise ValueError("reason ∈ {rental_rebind, bike_changed, period_changed}: %r" % (reason,))
        if not isinstance(row, Mapping):
            raise ValueError("row — строка двери clients")
        _need_by(by)
        _need_source(source)
        payload = {"op": "rebind_rental", "case_id": case_id, "row": dict(row), "reason": reason, "by": _by_key(by),
                   "source": _src_key(source), "expect_ver": expect_ver}

        def body(tx):
            case = self._need_case(tx, case_id)
            if not self._approver(by):
                _stop_rej("approver_unknown", "rebind_rental — только одобряющий по id")
            self._check_ver(case, expect_ver)
            info = self._rebind(tx, case, dict(row), source, why="rebind_rental", reason=reason, main=True)
            self._link_state(tx, case, "ok", why="rebind_rental")
            return self._ok(tx, case_id, case["ver"], data=info)

        return self._mutate(idem_key, payload, by, body)

    def bump_version(self, case_id, *, reason, ref, by, idem_key, expect_ver):
        """Подъём версии ровно на 1 с отзывом по DESIGN §4.2 в той же транзакции (I4, I21)."""
        if reason not in R.BUMP_REASONS:
            raise ValueError("reason ∈ %r: %r" % (R.BUMP_REASONS, reason))
        _need_by(by)
        payload = {"op": "bump_version", "case_id": case_id, "reason": reason, "ref": ref, "by": _by_key(by),
                   "expect_ver": expect_ver}

        def body(tx):
            case = self._need_case(tx, case_id)
            if reason == "new_request":
                rule = self._p("NEW_REQUEST_RULE")
                if (R.is_unknown(rule) or not rule) and not self._approver(by):
                    _stop_rej("param_unknown", "NEW_REQUEST_RULE: new_request — только одобряющий по id")
            self._check_ver(case, expect_ver)
            data = self._bump(tx, case, reason, _s(ref), main=True)
            return self._ok(tx, case_id, case["ver"], data=data)

        return self._mutate(idem_key, payload, by, body)

    def cancel_case(self, case_id, *, reason, by, idem_key, expect_ver):
        """open → cancelled: одобряющий; деньги и документы closed/waived; якорь и кандидаты → retired."""
        _need_by(by)
        payload = {"op": "cancel_case", "case_id": case_id, "reason": reason, "by": _by_key(by),
                   "expect_ver": expect_ver}

        def body(tx):
            case = self._need_case(tx, case_id)
            if not self._approver(by):
                _stop_rej("approver_unknown", "cancel_case — только одобряющий по id")
            self._check_ver(case, expect_ver)
            bl = [{"what": "obligation", "id": o["id"], "why": "obligation_%s" % o["state"], "kind": o["kind"],
                   "role": o["role"]}
                  for o in tx.q("SELECT * FROM rc_obligation WHERE case_id=? AND kind IN ('money','document') AND "
                                "state IN ('open','unknown') ORDER BY id", (case_id,))]
            if bl:
                _stop_rej("blockers", "деньги и документы не закрыты", data={"blockers": bl}, case_id=case_id,
                          ver=case["ver"])
            return self._finish_case(tx, case, "cancelled", _s(reason))

        return self._mutate(idem_key, payload, by, body)

    def _finish_case(self, tx, case, state, why):
        cid = case["case_id"]
        retired = self._retire_links(tx, case, ("anchor", "crm_row"), ("confirmed", "candidate"), "case_%s" % state)
        retired += self._retire_links(tx, case, ("booking_id",), ("candidate",), "case_%s" % state)
        exps, qids = [], []
        for e in tx.q("SELECT * FROM rc_expect WHERE case_id=? AND state NOT IN ('answered','superseded','cancelled') "
                      "ORDER BY created_at, exp_id", (cid,)):
            old = e["state"]
            new = "cancelled" if state == "cancelled" else "superseded"
            self._exp_set(tx, e, state=new, next_check="none", reason="case_%s" % state)
            self._exp_event(tx, "expectation_cancelled" if new == "cancelled" else "expectation_superseded", e, old,
                            why="case_%s" % state)
            exps.append(e["exp_id"])
            if e["kind"] == "staff_question" and e.get("ext_qid"):
                qids.append(e["ext_qid"])
        tasks = []
        if state == "cancelled":
            for t in tx.q("SELECT * FROM rc_task WHERE case_id=? AND state='open' ORDER BY created_at, task_id", (cid,)):
                tx.x("UPDATE rc_task SET state='cancelled', reason=?, row_ver=row_ver+1, updated_at=? WHERE task_id=?",
                     ("case_cancelled", tx.now, t["task_id"]))
                tx.event("task_cancelled", {"task_id": t["task_id"], "kind": t["kind"], "ref": why,
                                            "why": "case_cancelled"}, case_id=cid)
                tasks.append(t["task_id"])
        notices = self._supersede_notices(tx, cid, "case_%s" % state)
        self._case_set(tx, case, state=state)
        data = {"why": why, "retired_links": retired, "superseded_notices": notices, "expectations": exps,
                "cancelled_tasks": tasks, "staff_qids_to_close": qids}
        tx.event("case_closed" if state == "closed" else "case_cancelled", data, case_id=cid, main=True)
        return self._ok(tx, cid, case["ver"], data=data)


    # =================================================================================================================
    # Факты, касса, документы, обязательства (CONTRACT §5.2)
    # =================================================================================================================

    @staticmethod
    def _default_fkey(kind, value, source):
        v = value
        if kind == "cash":
            return ["cash", _s(v.get("src")) or "tx_find", v.get("row"), v.get("msg_id") or v.get("link") or ""]
        if kind == "contract":
            return ["contract", v.get("row"), v.get("doc_id")]
        if kind == "contract_ref":
            return ["contract_ref", v.get("ref_booking") or v.get("ref_anchor"), v.get("doc_id")]
        if kind == "pdf":
            return ["pdf", v.get("id")]
        if kind == "readback":
            return ["readback", _s(source.get("name")), _s(source.get("ref"))]
        if kind == "bike_event":
            return ["bike_event", v.get("bike"), v.get("type"), _s(source.get("ref"))]
        if kind == "bike_state":
            return ["bike_state", v.get("bike"), v.get("updated")]
        if kind == "rental":
            if _s(v.get("booking_id")):
                return ["rental", _s(v.get("booking_id"))]
            return ["rental", "", v.get("plate"), v.get("start_day")]
        return [kind, _s(source.get("name")), _s(source.get("ref"))]

    def record_fact(self, case_id, *, kind, value, source, scope, by, idem_key, fkey=None):
        """Факт с источником; observed_at не новее последнего valid того же fkey → ok(stale_read), изменений 0 (I30)."""
        if kind not in FACT_KINDS:
            raise ValueError("kind ∈ %r: %r" % (FACT_KINDS, kind))
        if scope not in SCOPES:
            raise ValueError("scope ∈ %r: %r" % (SCOPES, scope))
        if not isinstance(value, Mapping):
            raise ValueError("value — словарь")
        _need_by(by)
        _need_source(source)
        fk = list(fkey) if fkey is not None else self._default_fkey(kind, value, source)
        payload = {"op": "record_fact", "case_id": case_id, "kind": kind, "value": dict(value),
                   "source": _src_key(source), "scope": scope, "by": _by_key(by), "fkey": fk}

        def body(tx):
            case = self._need_case(tx, case_id, allow_closed=kind in CLOSED_ADD_FACT_KINDS)
            last = self._fact_latest(tx, case_id, fk)
            if last is not None and float(source["observed_at"]) <= float(last["observed_at"]):
                raise _Stop(_out("ok", case_id=case_id, ver=case["ver"], reason="stale_read",
                                 data={"stale_read": True, "fact_id": last["id"]}))
            fid = self._fact_insert(tx, case, kind, dict(value), fk, source, scope,
                                    self._unique_idem(tx, "rc_fact", idem_key), main=True, why="record_fact")
            return self._ok(tx, case_id, case["ver"], data={"fact_id": fid, "fkey": fk})

        return self._mutate(idem_key, payload, by, body)

    def revoke_fact(self, case_id, *, fact_id, reason, by, idem_key):
        _need_by(by)
        payload = {"op": "revoke_fact", "case_id": case_id, "fact_id": fact_id, "reason": reason, "by": _by_key(by)}

        def body(tx):
            case = self._need_case(tx, case_id)
            f = (tx.one("SELECT * FROM rc_fact WHERE id=? AND case_id=?", (fact_id, case_id))
                 if _int_id(fact_id) else None)                    # К4 круг 4: id не целым числом — такого факта нет
            if f is None:
                _stop_rej("evidence_missing", "факта нет в деле")
            if f["state"] != "valid":
                _stop_rej("bad_transition", "факт уже %s" % f["state"])
            reopened = self._revoke_fact(tx, case, f, _s(reason) or "revoked", main=True)
            return self._ok(tx, case_id, case["ver"], data={"fact_id": fact_id, "reopened": reopened})

        return self._mutate(idem_key, payload, by, body)

    @staticmethod
    def _in_window(kind, v, window):
        w = window or {}
        if kind == "cash":
            wb = _s(w.get("booking_id"))
            if wb and _s(v.get("booking_id")) != wb:
                return False
            wp = _s(w.get("plate")) or (R.plate_of_row({"bike": w.get("bike")}) or "" if _s(w.get("bike")) else "")
            if wp and (R.plate_of_row({"bike": v.get("bike")}) or "") != wp:
                return False
            day = _s(v.get("at"))[:10]
        else:
            wp = _s(w.get("plate")) or (R.plate_of_row({"bike": w.get("bike")}) or "" if _s(w.get("bike")) else "")
            if wp and (R.plate_of_row({"bike": v.get("bike")}) or "") != wp:
                return False
            day = _s(v.get("contract_date"))[:10]
        df, dt = _s(w.get("date_from")), _s(w.get("date_to"))
        if df and day and day < df:
            return False
        if dt and day and day > dt:
            return False
        return True

    def refresh_facts(self, case_id, *, kind, window, read, source, by, idem_key):
        """Полное чтение окна: valid-факты окна без ключа или в cancelled → revoked(withdrawn_by_newer_read); закрытое
        ими → unknown (obligation_reopened). Неполное чтение → ok(incomplete), изменений 0."""
        if kind not in ("cash", "contract"):
            raise ValueError("kind ∈ {cash, contract}: %r" % (kind,))
        if not isinstance(window, Mapping) or not isinstance(read, Mapping):
            raise ValueError("window и read — словари")
        _need_by(by)
        _need_source(source)
        payload = {"op": "refresh_facts", "case_id": case_id, "kind": kind, "window": dict(window), "read": dict(read),
                   "source": _src_key(source), "by": _by_key(by)}

        def body(tx):
            case = self._need_case(tx, case_id)
            if read.get("complete") is not True:
                raise _Stop(_out("ok", case_id=case_id, ver=case["ver"], reason="",
                                 data={"incomplete": True, "revoked": []}))
            keys = set(_j(list(k)) for k in read.get("keys") or [] if isinstance(k, (list, tuple)))
            cancelled = set(_j(list(k)) for k in read.get("cancelled") or [] if isinstance(k, (list, tuple)))
            revoked, reopened = [], []
            for f in tx.q("SELECT * FROM rc_fact WHERE case_id=? AND kind=? AND state='valid' ORDER BY id",
                          (case_id, kind)):
                v = _jl(f["value"], {}) or {}
                if not self._in_window(kind, v, window):
                    continue
                if f["fkey"] not in keys or f["fkey"] in cancelled:
                    reopened += self._revoke_fact(tx, case, f, "withdrawn_by_newer_read")
                    revoked.append(f["id"])
            data = {"incomplete": False, "revoked": revoked, "reopened": reopened}
            if not revoked:
                raise _Stop(_out("ok", case_id=case_id, ver=case["ver"], data=data))
            tx.event("facts_refreshed", dict(data, kind=kind, window=dict(window)), case_id=case_id,
                     source=_s(source["name"]), ref=_s(source["ref"]), main=True)
            return self._ok(tx, case_id, case["ver"], data=data)

        return self._mutate(idem_key, payload, by, body)

    def bind_cash(self, case_id, *, cash_fact, rows, source, by, idem_key, human=None):
        """Привязка строки кассы к делу по rules.bind_cash (I18, I35); unknown ожиданий не рождает."""
        if not isinstance(cash_fact, Mapping):
            raise ValueError("cash_fact — факт кассы (wa_agent_tools.cash_result)")
        if rows is None or isinstance(rows, (str, bytes)):
            raise ValueError("rows — ВСЕ строки номера из полного чтения")
        if human is not None and not isinstance(human, Mapping):
            raise ValueError("human — словарь")
        _need_by(by)
        _need_source(source)
        rows = [dict(r) for r in rows if isinstance(r, Mapping)]
        payload = {"op": "bind_cash", "case_id": case_id, "cash_fact": dict(cash_fact), "rows": rows,
                   "source": _src_key(source), "by": _by_key(by), "human": dict(human) if human else None}

        def body(tx):
            case = self._need_case(tx, case_id)
            if human is not None and not self._approver(by):
                _stop_rej("approver_unknown", "привязка кассы решением — только одобряющий по id")
            b = self._binding(tx, case)
            v = R.bind_cash(cash_fact, b, rows, self.params, human)
            if v.get("code") == "unknown":
                _stop_unk(v.get("reason") or "which_rental", v.get("missing") or ["which_rental"], v.get("ask") or "",
                          data={"claimants": v.get("claimants") or []}, case_id=case_id, ver=case["ver"])
            fk = ["cash", _s(cash_fact.get("src")) or "tx_find", cash_fact.get("row"),
                  cash_fact.get("msg_id") or cash_fact.get("link") or ""]
            if v.get("code") == "unbound":
                data = {"bound": False, "reason": v.get("reason"), "row": cash_fact.get("row"),
                        "msg_id": cash_fact.get("msg_id"), "claimants": v.get("claimants") or []}
                tx.event("cash_unbound", data, case_id=case_id, source=_s(source["name"]), ref=_s(source["ref"]),
                         main=True)
                return self._ok(tx, case_id, case["ver"], data=data)
            last = self._fact_latest(tx, case_id, fk)
            if last is not None and float(source["observed_at"]) <= float(last["observed_at"]):
                raise _Stop(_out("ok", case_id=case_id, ver=case["ver"], reason="stale_read",
                                 data={"stale_read": True, "fact_id": last["id"], "bound": True}))
            value = dict(cash_fact)
            value.update(bound_by=v.get("bound_by"), rental_id=b["rental_id"], case_id=case_id)
            fid = self._fact_insert(tx, case, "cash", value, fk, source, "rental",
                                    self._unique_idem(tx, "rc_fact", idem_key), why="bind_cash")
            data = {"fact_id": fid, "role": cash_fact.get("role"), "bound_by": v.get("bound_by"), "bound": True,
                    "row": cash_fact.get("row"), "msg_id": cash_fact.get("msg_id"), "amount": cash_fact.get("amount"),
                    "currency": cash_fact.get("currency")}
            tx.event("cash_bound", data, case_id=case_id, source=_s(source["name"]), ref=_s(source["ref"]), main=True)
            return self._ok(tx, case_id, case["ver"], data=data)

        return self._mutate(idem_key, payload, by, body)

    # ----- документы (принадлежность и покрытие — раздельно, I46) -----

    def _doc_links(self, tx, case_id):
        """(pdf_id договора по id документа, id договора по id PDF) — из событий document_recorded."""
        pdf_of, contract_of = {}, {}
        for e in tx.q("SELECT payload FROM rc_event WHERE case_id=? AND type='document_recorded' ORDER BY seq",
                      (case_id,)):
            p = _jl(e["payload"], {}) or {}
            if p.get("pdf_id") and p.get("document_id") is not None:
                pdf_of[p["document_id"]] = p["pdf_id"]
            if p.get("contract_document_id") is not None and p.get("document_id") is not None:
                contract_of[p["document_id"]] = p["contract_document_id"]
        return pdf_of, contract_of

    def _pdf_contract(self, tx, case, pdf_ext, contract_result):
        """Проверенный договор ЭТОГО дела, чей pdf_id = ext_id PDF (та же сверка, что в documents_for)."""
        pdf_of, _co = self._doc_links(tx, case["case_id"])
        docs = tx.q("SELECT * FROM rc_document WHERE case_id=? AND kind='contract_signed' AND status='verified' "
                    "ORDER BY id", (case["case_id"],))
        for d in docs:
            if pdf_of.get(d["id"]) == pdf_ext:
                return d
        if isinstance(contract_result, Mapping) and contract_result.get("outcome") == "fact":
            facts = contract_result.get("facts") or []
            if len(facts) == 1 and _s(facts[0].get("pdf_id")) == pdf_ext:
                for d in docs:
                    if d["ext_id"] == _s(facts[0].get("doc_id")):
                        return d
        return None

    def _case_rental_by_id(self, tx, case_id, rental_id):
        if not _int_id(rental_id):
            return None
        return tx.one("SELECT * FROM rc_rental WHERE id=? AND case_id=?", (rental_id, case_id))

    def record_document(self, case_id, *, kind, ext_id, status, source, by, idem_key, sha256=None, signed_at=None,
                        reg_row=None, rental_id=None, contract_result=None, pdf_result=None, human_binding=None):
        """ПРИНАДЛЕЖНОСТЬ документа (verified к привязке ЭТОГО дела). Покрытие периода здесь НЕ пишется (I46)."""
        if kind not in DOC_KINDS:
            raise ValueError("kind ∈ %r: %r" % (DOC_KINDS, kind))
        if status not in ("verified", "unverified"):
            raise ValueError("status ∈ {verified, unverified} (отзыв — revoke_document): %r" % (status,))
        if not _s(ext_id):
            raise ValueError("ext_id — непустой")
        if human_binding is not None:
            if not isinstance(human_binding, Mapping):
                raise ValueError("human_binding — {rental_id}")
            extra_keys = [k for k in human_binding if k not in ("rental_id", "detail", "note", "act_ref", "ref")]
            if extra_keys:
                raise ValueError("human_binding несёт только принадлежность {rental_id}; ключи покрытия/периода "
                                 "запрещены (I46: покрытие — только confirm_document_coverage): %r" % (extra_keys,))
        _need_by(by)
        _need_source(source)
        payload = {"op": "record_document", "case_id": case_id, "kind": kind, "ext_id": _s(ext_id), "status": status,
                   "source": _src_key(source), "by": _by_key(by), "sha256": sha256, "signed_at": signed_at,
                   "reg_row": reg_row, "rental_id": rental_id, "contract_result": contract_result,
                   "pdf_result": pdf_result, "human_binding": dict(human_binding) if human_binding else None}

        def body(tx):
            case = self._need_case(tx, case_id, allow_closed=True)
            ext = _s(ext_id)
            rid, bound_by, extra = None, None, {}
            sa, rr_no, sha = signed_at, reg_row, sha256
            if rental_id is not None:
                if self._case_rental_by_id(tx, case_id, rental_id) is None:
                    _stop_rej("doc_foreign_rental", "rental_id не привязка этого дела")
                rid = rental_id
            if status == "verified":
                if human_binding is not None:
                    if not self._approver(by):
                        _stop_rej("approver_unknown", "human_binding — только одобряющий по id")
                    hrid = human_binding.get("rental_id")
                    if self._case_rental_by_id(tx, case_id, hrid) is None:
                        _stop_rej("doc_foreign_rental", "human_binding.rental_id не привязка этого дела")
                    if rental_id is not None and rental_id != hrid:
                        _stop_rej("doc_foreign_rental", "rental_id ≠ human_binding.rental_id")
                    if kind == "contract_pdf" and not _s(sha):
                        _stop_rej("sha_missing")
                    rid, bound_by = hrid, "human"
                elif kind == "contract_signed":
                    cr = contract_result
                    if not isinstance(cr, Mapping):
                        _stop_rej("doc_unknown", "нет доказательства принадлежности (contract_result | human_binding)")
                    oc = _s(cr.get("outcome"))
                    if oc == "conflict":
                        _stop_rej("doc_conflict", _s(cr.get("reason")))
                    facts = cr.get("facts") or []
                    if oc != "fact" or len(facts) != 1:
                        _stop_rej("doc_unknown", "%s: %s" % (oc or "—", _s(cr.get("reason"))))
                    f = facts[0]
                    if _s(f.get("doc_id")) != ext:
                        _stop_rej("doc_conflict", "doc_id факта ≠ ext_id")
                    rr = self._case_rental_by_id(tx, case_id, rental_id)
                    if rr is None:
                        _stop_rej("doc_unknown", "rental_id привязки этого дела не назван")
                    if _s(cr.get("window")) != "%s…%s" % (rr["start_day"], rr["end_day"]):
                        _stop_rej("doc_foreign_rental", "окно договора %s ≠ сроку привязки %s…%s"
                                  % (_s(cr.get("window")), rr["start_day"], rr["end_day"]))
                    fbk = _s(f.get("booking_id"))
                    if fbk and _s(rr["booking_id"]) and fbk != _s(rr["booking_id"]):
                        _stop_rej("doc_foreign_rental", "booking_id договора ≠ booking_id привязки")
                    if not (fbk and fbk == _s(rr["booking_id"])):
                        # К4 круг 2 (C6, I18): без общего booking_id совпавший срок принадлежности не доказывает —
                        # байк договора обязан быть байком привязки, телефон договора — активным контактом дела
                        fplate = R.plate_of_row({"bike": f.get("bike")})
                        if not fplate or fplate != _s(rr["plate"]):
                            _stop_rej("doc_foreign_rental", "байк договора %s ≠ байку привязки %s: без общего "
                                      "booking_id срок принадлежности не доказывает (I18)"
                                      % (fplate or "?", _s(rr["plate"]) or "?"))
                        if not self._doc_phone_of_case(tx, case_id, f.get("phone")):
                            _stop_rej("doc_foreign_rental", "телефон договора не активный контакт дела: без общего "
                                      "booking_id срок и байк принадлежности не доказывают (I18)")
                    bound_by = "%s + %s + %s" % (_s(f.get("bound_by")) or "?",
                                                 R.plate_of_row({"bike": f.get("bike")}) or rr["plate"],
                                                 _s(f.get("contract_date")) or "?")
                    sa = sa if sa is not None else f.get("signed_at")
                    rr_no = rr_no if rr_no is not None else f.get("row")
                    rid = rental_id
                    if _s(f.get("pdf_id")):
                        extra["pdf_id"] = _s(f.get("pdf_id"))
                elif kind == "contract_pdf":
                    if not _s(sha):
                        _stop_rej("sha_missing")
                    pr = pdf_result
                    pfacts = (pr.get("facts") or []) if isinstance(pr, Mapping) else []
                    if not isinstance(pr, Mapping) or _s(pr.get("outcome")) != "fact" or len(pfacts) != 1:
                        _stop_rej("doc_unknown", "pdf_result не FACT")
                    pf = pfacts[0]
                    if _s(pf.get("id")) != ext:
                        _stop_rej("pdf_not_of_contract", "id PDF ≠ ext_id")
                    if _s(pf.get("sha256")) != _s(sha):
                        _stop_rej("doc_conflict", "sha256 PDF расходится")
                    contract = self._pdf_contract(tx, case, ext, contract_result)
                    if contract is None:
                        _stop_rej("pdf_not_of_contract", "PDF не принадлежит проверенному договору этого дела")
                    if rental_id is not None and rental_id != contract["rental_id"]:
                        _stop_rej("doc_foreign_rental", "rental_id PDF ≠ привязке его договора")
                    rid = contract["rental_id"]
                    bound_by = "PDF договора %s" % contract["ext_id"]
                    extra["contract_document_id"] = contract["id"]
                else:
                    _stop_rej("doc_unknown", "verified для %s — только human_binding одобряющего" % kind)
            ex = tx.one("SELECT * FROM rc_document WHERE case_id=? AND kind=? AND ext_id=? AND IFNULL(sha256,'')=? "
                        "AND IFNULL(signed_at,'')=?", (case_id, kind, ext, _s(sha), _s(sa)))
            if ex is not None:
                if ex["status"] == "revoked":
                    _stop_rej("doc_conflict", "эта версия документа отозвана — новая версия = новая строка")
                if ex["status"] == "verified" or status == "unverified":
                    tx.event("document_recorded", {"document_id": ex["id"], "kind": kind, "ext_id": ext,
                                                   "sha256": ex["sha256"], "signed_at": ex["signed_at"],
                                                   "status": ex["status"], "rental_id": ex["rental_id"],
                                                   "bound_by": ex["bound_by"], "why": "already_recorded"},
                             case_id=case_id, source=_s(source["name"]), ref=_s(source["ref"]), main=True)
                    return self._ok(tx, case_id, case["ver"], data={"document_id": ex["id"], "status": ex["status"],
                                                                    "unchanged": True})
                tx.x("UPDATE rc_document SET status='verified', rental_id=?, bound_by=?, source=?, read_at=?, author=?, "
                     "ref=?, method=?, observed_at=?, reg_row=COALESCE(reg_row, ?) WHERE id=?",
                     (rid, bound_by, _s(source["name"]), float(source["read_at"]), tx.author(), _s(source["ref"]),
                      source["method"], float(source["observed_at"]), rr_no, ex["id"]))
                p = {"document_id": ex["id"], "kind": kind, "ext_id": ext, "sha256": ex["sha256"],
                     "signed_at": ex["signed_at"], "status": "verified", "rental_id": rid, "bound_by": bound_by,
                     "why": "verified"}
                p.update(extra)
                tx.event("document_recorded", p, case_id=case_id, source=_s(source["name"]), ref=_s(source["ref"]),
                         main=True)
                return self._ok(tx, case_id, case["ver"], data={"document_id": ex["id"], "status": "verified",
                                                                "rental_id": rid, "bound_by": bound_by})
            did = self._doc_insert(tx, case, kind, ext, status, source, rental_id=rid, sha256=_s(sha) or None,
                                   signed_at=sa, reg_row=rr_no, bound_by=bound_by, why="record_document", extra=extra,
                                   main=True)
            return self._ok(tx, case_id, case["ver"], data={"document_id": did, "status": status, "rental_id": rid,
                                                            "bound_by": bound_by})

        return self._mutate(idem_key, payload, by, body)

    def confirm_document_coverage(self, case_id, *, document_id, cover_from, cover_to, source_ref, act_ref, by,
                                  idem_key):
        """ЕДИНСТВЕННЫЙ в К4 путь записи покрытия (I46): одобряющий, явные даты, источник дат, id действия;
        verified contract_signed этого дела. Те же даты поверх — duplicate; иные — rejected(doc_cover_set)."""
        _need_by(by)
        payload = {"op": "confirm_document_coverage", "case_id": case_id, "document_id": document_id,
                   "cover_from": cover_from, "cover_to": cover_to, "source_ref": source_ref, "act_ref": act_ref,
                   "by": _by_key(by)}

        def body(tx):
            case = self._need_case(tx, case_id, allow_closed=True)
            if not self._approver(by):
                _stop_rej("approver_unknown", "покрытие подтверждает только одобряющий по id")
            cf, ct = _iso_strict(cover_from), _iso_strict(cover_to)
            if cf is None or ct is None or cf > ct or not _s(source_ref) or not _s(act_ref):
                _stop_rej("doc_cover_invalid", "нужны явные даты YYYY-MM-DD (с ≤ по), источник дат и id действия")
            d = (tx.one("SELECT * FROM rc_document WHERE id=? AND case_id=?", (document_id, case_id))
                 if _int_id(document_id) else None)
            if d is None or d["kind"] != "contract_signed" or d["status"] != "verified":
                _stop_rej("doc_unknown", "покрытие — только у verified contract_signed этого дела")
            if d["cover_from"] is not None or d["cover_to"] is not None:
                if (d["cover_from"], d["cover_to"]) == (cover_from, cover_to):
                    prev = None
                    for e in tx.q("SELECT seq, payload FROM rc_event WHERE case_id=? AND "
                                  "type='document_coverage_confirmed' ORDER BY seq", (case_id,)):
                        if (_jl(e["payload"], {}) or {}).get("document_id") == document_id:
                            prev = e["seq"]
                    raise _Stop(_out("duplicate", case_id=case_id, ver=case["ver"], event_seq=prev,
                                     data={"document_id": document_id, "cover_from": d["cover_from"],
                                           "cover_to": d["cover_to"], "duplicate": True}))
                _stop_rej("doc_cover_set", "покрытие уже записано (%s…%s); иное — только revoke_document + новая "
                          "строка" % (d["cover_from"], d["cover_to"]))
            tx.x("UPDATE rc_document SET cover_from=?, cover_to=?, cover_basis='human_confirmed', cover_ref=?, "
                 "cover_by=?, cover_act=?, cover_at=? WHERE id=?",
                 (cover_from, cover_to, _s(source_ref), by.get("id"), _s(act_ref), tx.now, document_id))
            data = {"document_id": document_id, "cover_from": cover_from, "cover_to": cover_to,
                    "cover_basis": "human_confirmed", "cover_ref": _s(source_ref), "cover_by": by.get("id"),
                    "act_ref": _s(act_ref)}
            tx.event("document_coverage_confirmed", data, case_id=case_id, ref=_s(act_ref), main=True)
            return self._ok(tx, case_id, case["ver"], data=data)

        return self._mutate(idem_key, payload, by, body)

    def revoke_document(self, case_id, *, document_id, reason, by, source, idem_key):
        """verified/unverified → revoked; закрытое этим вторым источником (write) → unknown (I45)."""
        _need_by(by)
        _need_source(source)
        payload = {"op": "revoke_document", "case_id": case_id, "document_id": document_id, "reason": reason,
                   "by": _by_key(by), "source": _src_key(source)}

        def body(tx):
            case = self._need_case(tx, case_id)
            d = (tx.one("SELECT * FROM rc_document WHERE id=? AND case_id=?", (document_id, case_id))
                 if _int_id(document_id) else None)
            if d is None:
                _stop_rej("doc_unknown", "документа нет в деле")
            if d["status"] == "revoked":
                _stop_rej("bad_transition", "документ уже отозван")
            tx.x("UPDATE rc_document SET status='revoked', reason=? WHERE id=?", (_s(reason) or "revoked", document_id))
            tx.event("document_revoked", {"document_id": document_id, "kind": d["kind"], "ext_id": d["ext_id"],
                                          "sha256": d["sha256"], "signed_at": d["signed_at"], "status": "revoked",
                                          "rental_id": d["rental_id"], "bound_by": d["bound_by"], "why": _s(reason)},
                     case_id=case_id, source=_s(source["name"]), ref=_s(source["ref"]), main=True)
            reopened = self._reopen_by(tx, case, "close_second_id", document_id, "second_source_revoked")
            return self._ok(tx, case_id, case["ver"], data={"document_id": document_id, "reopened": reopened})

        return self._mutate(idem_key, payload, by, body)

    # ----- обязательства (§3.4, §4.4, I25, I26, I45) -----

    def open_obligation(self, case_id, *, kind, role, direction, source, by, idem_key, amount=None, currency=None,
                        outcome=None):
        """Рождение вне REQUIRED: одобряющий по id; адаптер ClosingPort (by.kind=source) — только money/other в unknown;
        агент и код → rejected(approver_unknown)."""
        fixed = None
        known = False
        for k, r, d in OBLIGATION_ROLES:
            if k == kind and r == role:
                known, fixed = True, d
        if not known:
            raise ValueError("(kind, role) вне §3.4: %r/%r" % (kind, role))
        if direction not in ("from_client", "to_client", "internal") or (fixed is not None and direction != fixed):
            raise ValueError("direction %r не для %s/%s" % (direction, kind, role))
        if outcome not in (None, "valid", "unknown", "incomplete"):
            raise ValueError("outcome ∈ {valid, unknown, incomplete}")
        if amount is not None and _num(amount) is None:
            raise ValueError("amount — число")
        _need_by(by)
        _need_source(source)
        payload = {"op": "open_obligation", "case_id": case_id, "kind": kind, "role": role, "direction": direction,
                   "source": _src_key(source), "by": _by_key(by), "amount": amount, "currency": currency,
                   "outcome": outcome}

        def body(tx):
            case = self._need_case(tx, case_id)
            if self._approver(by):
                if kind == "money":
                    named = amount is not None and _s(currency)
                    oc = outcome or ("valid" if named else "unknown")
                    st = "open" if named else "unknown"
                else:
                    oc, st = None, "open"
                why = "approver"
            elif by.get("kind") == "source" and (kind, role) == ("money", "other"):
                oc, st, why = "incomplete", "unknown", "param_unknown:CLOSING_K_SEMANTICS"
            else:
                _stop_rej("approver_unknown", "обязательство вне обязательного набора рождает только одобряющий по id")
            o = self._obl_insert(tx, case, kind, role, direction, st, oc, amount,
                                 _s(currency).upper() or None, False, source,
                                 self._unique_idem(tx, "rc_obligation", idem_key), why, main=True)
            return self._ok(tx, case_id, case["ver"], data={"obligation_id": o["id"], "state": st, "outcome": oc})

        return self._mutate(idem_key, payload, by, body)

    def settle_obligation(self, case_id, *, obligation_id, by, idem_key, expect_row_ver, write=None, cell=None,
                          human=None):
        """Решение по обязательству — rules.obligation_verdict внутри транзакции; исход — ОДИН код по why (§5.2)."""
        given = [x for x in (write, cell, human) if x is not None]
        if len(given) != 1 or not isinstance(given[0], Mapping):
            raise ValueError("ровно одно из write / cell / human (словарь)")
        _need_by(by)
        payload = {"op": "settle_obligation", "case_id": case_id, "obligation_id": obligation_id, "by": _by_key(by),
                   "expect_row_ver": expect_row_ver, "write": dict(write) if write else None,
                   "cell": dict(cell) if cell else None, "human": dict(human) if human else None}

        def body(tx):
            case = self._need_case(tx, case_id)
            o = (tx.one("SELECT * FROM rc_obligation WHERE id=? AND case_id=?", (obligation_id, case_id))
                 if _int_id(obligation_id) else None)     # К4 круг 4: id не целым числом — такого обязательства нет
            if o is None:
                _stop_rej("obligation_missing", "обязательства нет в деле")
            self._check_row_ver(o, expect_row_ver, case_id, case["ver"])
            if o["state"] in ("closed", "waived"):
                _stop_rej("bad_transition", "обязательство уже %s" % o["state"])
            want = {"state": o["state"], "outcome": o["outcome"], "amount": o["amount"], "currency": o["currency"],
                    "direction": o["direction"]}
            if human is not None:
                return self._settle_human(tx, case, o, want, human, by)
            if cell is not None:
                if o["kind"] != "money":
                    _stop_rej("bad_transition", "клетка листа — только у денег")
                v = R.obligation_verdict(o["kind"], o["role"], want, cell=dict(cell), params=self.params)
                new = v.get("state")
                if new not in ("open", "unknown"):
                    _stop_rej("bad_transition", "клетка денежное обязательство не закрывает (I26)")
                old = o["state"]
                self._obl_set(tx, o, state=new)
                tx.event("obligation_unknown" if new == "unknown" else "obligation_opened",
                         self._obl_payload(o, "%s: %s→%s" % (v.get("why"), old, new)), case_id=case_id, main=True)
                return self._ok(tx, case_id, case["ver"], data={"obligation_id": o["id"], "state": new,
                                                                "why": v.get("why")})
            return self._settle_write(tx, case, o, want, write)

        return self._mutate(idem_key, payload, by, body)

    def _settle_human(self, tx, case, o, want, human, by):
        cid = case["case_id"]
        if not self._approver(by):
            _stop_rej("approver_unknown", "решение по обязательству — только одобряющий по id")
        detail = human.get("detail")
        if isinstance(human.get("want"), Mapping):
            if o["kind"] != "money":
                _stop_rej("bad_transition", "сумма want — только у денег")
            w = human["want"]
            amount, currency = _num(w.get("amount")), _s(w.get("currency")).upper()
            if amount is None or not currency:
                raise _ArgError("human.want — {amount: число, currency}")
            v = R.obligation_verdict(o["kind"], o["role"], want, human=dict(human), params=self.params)
            new = v.get("state") if v.get("state") in ("open", "unknown") else "open"
            self._obl_set(tx, o, state=new, outcome="valid", amount=amount, currency=currency,
                          close_ref=_s(w.get("detail")) or o.get("close_ref"))
            tx.event("obligation_want_set", self._obl_payload(o, "want:%s" % (_s(w.get("detail")) or "approver")),
                     case_id=cid, main=True)
            return self._ok(tx, cid, case["ver"], data={"obligation_id": o["id"], "state": new, "outcome": "valid",
                                                        "amount": amount, "currency": currency})
        v = R.obligation_verdict(o["kind"], o["role"], want, human=dict(human), params=self.params)
        if v.get("state") == "waived":
            self._obl_set(tx, o, state="waived", closed_by="human", close_ref=_s(detail) or "waived",
                          close_author=_author(by))
            tx.event("obligation_waived", self._obl_payload(o, "waived"), case_id=cid, main=True)
        elif v.get("state") == "closed" and v.get("by") == "human":
            self._obl_set(tx, o, state="closed", closed_by="human", close_ref=_s(detail) or "decided",
                          close_author=_author(by))
            tx.event("obligation_settled", self._obl_payload(o, "decided"), case_id=cid, main=True)
        else:
            _stop_rej("bad_transition", "решение человека без decided/waive/want: %s" % v.get("why"))
        return self._ok(tx, cid, case["ver"], data={"obligation_id": o["id"], "state": o["state"],
                                                    "closed_by": o["closed_by"]})

    def _settle_write(self, tx, case, o, want, write):
        cid = case["case_id"]
        if o["kind"] != "money":
            _stop_rej("bad_transition", "write — только у денег")
        rule = self._p("MONEY_CLOSE_RULE")
        if R.is_unknown(rule) or rule != "cash_and_second_source":
            _stop_unk("param_unknown", ["MONEY_CLOSE_RULE"],
                      "Правило закрытия денег кассой (MONEY_CLOSE_RULE) не принято — оплату подтверждает одобряющий; "
                      "строка кассы видна фактом в cash[] обязательства.", words="MONEY_CLOSE_RULE", case_id=cid,
                      ver=case["ver"])
        fid, sid = write.get("cash_fact_id"), write.get("second_document_id")
        f = (tx.one("SELECT * FROM rc_fact WHERE id=? AND case_id=? AND kind='cash'", (fid, cid))
             if _int_id(fid) else None)                   # К4 круг 4: id не целым числом — такого факта кассы нет
        cash = {"state": "missing"}
        if f is not None:
            v = _jl(f["value"], {}) or {}
            cash = {"state": f["state"], "rental_id": v.get("rental_id"), "role": v.get("role"),
                    "amount": v.get("amount"), "currency": v.get("currency"), "case_id": cid}
        d = None
        if _int_id(sid):                                  # К4 круг 4: id не целым числом — такого документа нет
            d = tx.one("SELECT * FROM rc_document WHERE id=? AND case_id=?", (sid, cid))
        second = None
        if d is not None:
            dr = self._case_rental_by_id(tx, cid, d["rental_id"]) if d["rental_id"] is not None else None
            second = {"kind": d["kind"], "status": d["status"], "booking_id": (dr or {}).get("booking_id"),
                      "rental_id": d["rental_id"]}
        b = self._rental(tx, cid) or {}
        wr = {"cash": cash, "second": second, "binding": {"rental_id": b.get("id"), "booking_id": b.get("booking_id")}}
        v = R.obligation_verdict(o["kind"], o["role"], want, write=wr, params=self.params)
        why = _s(v.get("why"))
        if v.get("state") == "closed" and v.get("by") == "write":
            self._obl_set(tx, o, state="closed", closed_by="write", close_fact_id=f["id"], close_second_id=d["id"],
                          close_ref="cash:%s + document:%s" % (f["id"], d["id"]), close_author=tx.author())
            tx.event("obligation_settled", self._obl_payload(o, why), case_id=cid, main=True)
            return self._ok(tx, cid, case["ver"], data={"obligation_id": o["id"], "state": "closed",
                                                        "closed_by": "write", "close_fact_id": f["id"],
                                                        "close_second_id": d["id"]})
        if why.startswith("param_unknown"):
            _stop_unk("param_unknown", ["MONEY_CLOSE_RULE"], words=why, case_id=cid, ver=case["ver"])
        if why == "role_not_rent":
            _stop_rej("bad_transition", "write закрывает только rent (I45)", case_id=cid, ver=case["ver"])
        if why == "second_source_missing":
            _stop_unk("second_source_missing", ["second_source"], case_id=cid, ver=case["ver"])
        if why == "want_not_valid":
            _stop_unk("param_unknown", ["PAYMENT_RECORD_PLACE"],
                      "Сумма аренды не названа одобряющим (клетка листа известной суммой не считается) — какая сумма "
                      "к оплате?", words="want_not_valid", case_id=cid, ver=case["ver"])
        if why == "booking_id_missing":
            _stop_unk("link_missing", ["booking_id"], case_id=cid, ver=case["ver"])
        _stop_rej("closing_fact_invalid", why or "касса не подтверждает оплату", case_id=cid, ver=case["ver"])


    # =================================================================================================================
    # Задачи и ступени (CONTRACT §5.3, §4.5)
    # =================================================================================================================

    def _need_task(self, tx, case_id, task_id):
        if not isinstance(task_id, str) or not task_id:
            raise _ArgError("task_id — непустая строка")
        t = tx.one("SELECT * FROM rc_task WHERE task_id=?", (task_id,))
        if t is None or t["case_id"] != case_id:
            _stop_rej("evidence_foreign", "задача не этого дела", data={"task_id": task_id})
        return t

    def _agent_gate(self, by, what):
        if by.get("kind") == "agent" and self._p("AUTO_ASK") is not True:
            _stop_rej("param_unknown", "AUTO_ASK: %s от агента не принят" % what)

    def open_task(self, case_id, *, kind, ref, by, idem_key, expect_ver):
        if kind not in TASK_KINDS:
            raise ValueError("kind ∈ %r: %r" % (TASK_KINDS, kind))
        _need_by(by)
        payload = {"op": "open_task", "case_id": case_id, "kind": kind, "ref": ref, "by": _by_key(by),
                   "expect_ver": expect_ver}

        def body(tx):
            case = self._need_case(tx, case_id)
            self._agent_gate(by, "задача из обращения")
            self._check_ver(case, expect_ver)
            if case["link_state"] != "ok":
                _stop_rej("link_drift", "привязка аренды не подтверждена (%s)" % case["link_state"])
            r = self._rental(tx, case_id)
            task_id = "RT-" + self.new_id()
            tx.x("INSERT INTO rc_task(task_id, case_id, kind, state, top_stage, rental_id, case_ver, created_at, updated_at, "
                 "row_ver, idem_key, reason) VALUES (?,?,?,'open',0,?,?,?,?,1,?,NULL)",
                 (task_id, case_id, kind, r["id"], case["ver"], tx.now, tx.now,
                  self._unique_idem(tx, "rc_task", idem_key)))
            tx.event("task_opened", {"task_id": task_id, "kind": kind, "ref": _s(ref), "why": "open_task"},
                     case_id=case_id, ref=_s(ref), main=True)
            return self._ok(tx, case_id, case["ver"], data={"task_id": task_id, "rental_id": r["id"]})

        return self._mutate(idem_key, payload, by, body)

    def record_stage(self, case_id, *, task_id, stage, evidence, by, idem_key):
        if stage not in R.STAGES:
            raise ValueError("stage ∈ %r: %r" % (R.STAGES, stage))
        if not isinstance(evidence, Mapping):
            raise ValueError("evidence — Evidence {kind, ref, …}")
        _need_by(by)
        payload = {"op": "record_stage", "case_id": case_id, "task_id": task_id, "stage": stage,
                   "evidence": dict(evidence), "by": _by_key(by)}

        def body(tx):
            case = self._need_case(tx, case_id)
            if stage == "client_notified":
                _stop_rej("bad_transition", "ступень 6 пишет только record_delivery (§4.5)")
            task = self._need_task(tx, case_id, task_id)
            ekind = R.evidence_kind(evidence)          # К4 круг 4: вид — точное слово, одно на Store и правило
            if ekind == "human_mark":
                if not (self._approver(by) and by.get("id") == evidence.get("author_id")):
                    _stop_rej("approver_unknown", "human_mark — только одобряющий по id, author_id = by.id")
            if task["state"] == "done":
                _stop_rej("bad_transition", "задача уже done")
            ev_in = self._readback_evidence(tx, case, task, evidence)      # К4 круг 2 (C26): readback своего ожидания
            if task["state"] == "cancelled":
                if stage not in ("physically_done", "result_recorded"):
                    _stop_rej("task_cancelled", "ступень 1–3 отменённой задачи не пишется")
                n = R.STAGE_NO[stage]
                ok, code = self._stage_check(tx, case, task, stage, ev_in, by, prior=set(R.STAGES[:n - 1]))
                if not ok:
                    _stop_rej(code or "evidence_forbidden")
                ref = _s(evidence.get("ref"))
                src = {"name": "rental_case:record_stage", "ref": ref,
                       "method": "human" if ekind == "human_mark" else "event",
                       "read_at": tx.now, "observed_at": _num(evidence.get("at")) or tx.now}
                fk = ["physical_event", task_id, ref]
                fid = self._fact_insert(tx, case, "physical_event", dict(evidence, stage=stage, task_id=task_id), fk,
                                        src, "case", self._unique_idem(tx, "rc_fact", idem_key), why="task_cancelled")
                self._attention_on(tx, case, "physical", "physical_event:%s" % task_id)
                tx.event("physical_event", {"task_id": task_id, "stage": stage,
                                            "evidence_kind": ekind, "evidence_ref": ref,
                                            "fact_id": fid}, case_id=case_id, main=True)
                return self._ok(tx, case_id, case["ver"], data={"stage": None, "fact_id": fid, "task_id": task_id},
                                reason="task_cancelled")
            if stage == "question_sent":
                ev_in = self._post_evidence(tx, case, task, ev_in)         # К4 круг 4 (C26): пост своего ожидания
            ok, code = self._stage_check(tx, case, task, stage, ev_in, by)
            if not ok:
                _stop_rej(code or "evidence_forbidden", data={"need": stage})
            flags = [code] if code else []
            self._stage_write(tx, case, task, stage, ev_in, flags, idem_key, main=True)
            return self._ok(tx, case_id, case["ver"], data={"stage": stage, "task_id": task_id, "flags": flags,
                                                            "top_stage": task["top_stage"],
                                                            "task_state": task["state"]})

        return self._mutate(idem_key, payload, by, body)

    def cancel_task(self, case_id, *, task_id, reason, by, idem_key):
        _need_by(by)
        payload = {"op": "cancel_task", "case_id": case_id, "task_id": task_id, "reason": reason, "by": _by_key(by)}

        def body(tx):
            case = self._need_case(tx, case_id)
            task = self._need_task(tx, case_id, task_id)
            if task["state"] != "open":
                _stop_rej("bad_transition", "задача %s" % task["state"])
            tx.x("UPDATE rc_task SET state='cancelled', reason=?, row_ver=row_ver+1, updated_at=? WHERE task_id=?",
                 (_s(reason) or "cancel_task", tx.now, task_id))
            tx.event("task_cancelled", {"task_id": task_id, "kind": task["kind"], "ref": _s(reason),
                                        "why": "cancel_task"}, case_id=case_id, main=True)
            return self._ok(tx, case_id, case["ver"], data={"task_id": task_id})

        return self._mutate(idem_key, payload, by, body)

    # =================================================================================================================
    # Ожидания и ответы (CONTRACT §5.4, §4.2, §4.7)
    # =================================================================================================================

    def request_staff_question(self, case_id, *, task_id, staff_kind, q_ru, q_th, urgency, by, idem_key, expect_ver):
        places = R._sub(self._p("STAFF_PLACES"), staff_kind)
        if R.is_unknown(places) or not places:
            raise ValueError("staff_kind ∉ STAFF_PLACES: %r" % (staff_kind,))
        if not _s(q_ru):
            raise ValueError("q_ru — непустой")
        _need_by(by)
        payload = {"op": "request_staff_question", "case_id": case_id, "task_id": task_id, "staff_kind": staff_kind,
                   "q_ru": q_ru, "q_th": q_th, "urgency": urgency, "by": _by_key(by), "expect_ver": expect_ver}

        def body(tx):
            case = self._need_case(tx, case_id)
            self._agent_gate(by, "вопрос сотрудникам")
            plist = list(places)
            if "topic" in plist and not _s(q_th):
                _stop_rej("no_thai", "вопрос в тему байка — с тайским текстом")
            self._check_ver(case, expect_ver)
            if task_id is not None:
                t = self._need_task(tx, case_id, task_id)
                if t["state"] != "open":
                    _stop_rej("bad_transition", "задача %s" % t["state"])
            qn = " ".join(_s(q_ru).lower().split())
            live, done = None, 0
            for e in tx.q("SELECT * FROM rc_expect WHERE case_id=? AND kind='staff_question' ORDER BY created_at, exp_id",
                          (case_id,)):
                s = _jl(e["subject"], {}) or {}
                if s.get("staff_kind") == staff_kind and s.get("q_norm") == qn:
                    if e["state"] in EXPECT_TERMINAL:
                        done += 1
                    elif live is None:
                        live = e
            if live is not None:
                ev = tx.one("SELECT seq FROM rc_event WHERE exp_id=? AND type='expectation_planned' ORDER BY seq LIMIT 1",
                            (live["exp_id"],))
                raise _Stop(_out("duplicate", case_id=case_id, ver=case["ver"], event_seq=ev["seq"] if ev else None,
                                 data={"exp_id": live["exp_id"], "duplicate": True, "why": "same_question_open"}))
            b = self._rental(tx, case_id) or {}
            subject = {"q_ru": q_ru, "q_th": q_th, "staff_kind": staff_kind, "urgency": urgency, "places": plist,
                       "bike": b.get("bike_name"), "plate": b.get("plate"), "q_norm": qn}
            exp = self._insert_exp(tx, case, "staff_question", plist[0], subject,
                                   self._unique_idem(tx, "rc_expect", idem_key), task_id=task_id, attempt_no=done + 1)
            self._exp_event(tx, "expectation_planned", exp, None, why="request_staff_question", main=True)
            return self._ok(tx, case_id, case["ver"], data={"exp_id": exp["exp_id"], "place": plist[0],
                                                            "places": plist, "attempt_no": done + 1})

        return self._mutate(idem_key, payload, by, body)

    def request_approval(self, case_id, *, task_id, action, chat, card, by, idem_key, expect_ver=None):
        if action not in APPROVAL_ORDER:
            raise ValueError("action ∈ %r: %r" % (APPROVAL_ORDER, action))
        if case_id is None and action != "booking":
            raise ValueError("без дела — только карточка брони (action=booking)")
        if not _s(chat):
            raise ValueError("chat — непустой")
        if not isinstance(card, Mapping):
            raise ValueError("card — словарь карточки")
        _need_by(by)
        payload = {"op": "request_approval", "case_id": case_id, "task_id": task_id, "action": action, "chat": _s(chat),
                   "card": dict(card), "by": _by_key(by), "expect_ver": expect_ver}

        def body(tx):
            case = None
            if case_id is not None:
                case = self._need_case(tx, case_id)
                self._check_ver(case, expect_ver)
                if task_id is not None:
                    self._need_task(tx, case_id, task_id)
            superseded = []
            for e in tx.q("SELECT * FROM rc_expect WHERE kind='approval' AND chat=? AND action=? AND state IN "
                          "('planned','in_flight','waiting','flight_unknown') ORDER BY created_at, exp_id",
                          (_s(chat), action)):
                old = e["state"]
                self._exp_set(tx, e, state="superseded", next_check="none", reason="new_card")
                self._exp_event(tx, "expectation_superseded", e, old, why="new_card")
                superseded.append(e["exp_id"])
            target = card.get("target") if isinstance(card.get("target"), Mapping) else {
                "card": card.get("ref"), "action": action, "case_id": case_id}
            exp = self._insert_exp(tx, case, "approval", "intake", dict(card),
                                   self._unique_idem(tx, "rc_expect", idem_key), task_id=task_id, action=action,
                                   chat=_s(chat), target=target)
            self._exp_event(tx, "expectation_planned", exp, None, why="request_approval", main=True,
                            superseded=superseded)
            return self._ok(tx, case_id, case["ver"] if case else None,
                            data={"exp_id": exp["exp_id"], "superseded": superseded})

        return self._mutate(idem_key, payload, by, body)

    def attach_expectation(self, exp_id, *, case_id, by, idem_key):
        _need_by(by)
        payload = {"op": "attach_expectation", "exp_id": exp_id, "case_id": case_id, "by": _by_key(by)}

        def body(tx):
            exp = self._need_exp(tx, exp_id)
            if exp["case_id"] is not None or exp["action"] != "booking" or exp["kind"] != "approval":
                _stop_rej("bad_transition", "привязывается только карточка брони без дела")   # круг 4: §4.2, вид
            case = self._need_case(tx, case_id)
            if exp["task_id"] is not None:        # R5 (C26 XCASE, I27, §3.6): задача карточки — задача дела привязки
                t = tx.one("SELECT case_id FROM rc_task WHERE task_id=?", (exp["task_id"],))
                if t is None or t["case_id"] != case_id:
                    _stop_rej("evidence_foreign", "задача карточки не этого дела",
                              data={"exp_id": exp_id, "task_id": exp["task_id"]})
            attached = []
            for e in [exp] + tx.q("SELECT * FROM rc_expect WHERE parent_exp=? AND case_id IS NULL ORDER BY exp_id",
                                  (exp_id,)):
                old = e["state"]
                self._exp_set(tx, e, case_id=case_id, case_ver=case["ver"])
                self._exp_event(tx, "expectation_attached", e, old, why="attach", main=(e["exp_id"] == exp_id))
                attached.append(e["exp_id"])
            tx.x("UPDATE rc_answer SET case_id=?, case_ver_at=COALESCE(case_ver_at, ?) WHERE exp_id IN (%s) "
                 "AND case_id IS NULL" % ",".join("?" * len(attached)), [case_id, case["ver"]] + attached)
            return self._ok(tx, case_id, case["ver"], data={"exp_id": exp_id, "attached": attached})

        return self._mutate(idem_key, payload, by, body)

    def expect_readback(self, case_id, *, task_id, action, target, by, idem_key, expect_ver):
        if action not in ("booking", "activate", "close", "result"):
            raise ValueError("action ∈ {booking, activate, close, result}: %r" % (action,))
        if not isinstance(target, Mapping):
            raise ValueError("target — словарь цели чтения назад")
        _need_by(by)
        payload = {"op": "expect_readback", "case_id": case_id, "task_id": task_id, "action": action,
                   "target": dict(target), "by": _by_key(by), "expect_ver": expect_ver}

        def body(tx):
            case = self._need_case(tx, case_id)
            self._check_ver(case, expect_ver)
            place = "crm"
            if task_id is not None:
                t = self._need_task(tx, case_id, task_id)
                if action == "result":
                    rp = R._sub(self._p("RESULT_RECORD_PLACE"), t["kind"])
                    place = "crm" if _s(rp).startswith("crm") else "sink"
            elif action == "result":
                place = "sink"
            exp = self._insert_exp(tx, case, "readback", place, {"action": action, "target": dict(target)},
                                   self._unique_idem(tx, "rc_expect", idem_key), next_check="execute",
                                   task_id=task_id, action=action, target=dict(target))
            self._exp_event(tx, "expectation_planned", exp, None, why="expect_readback", main=True)
            return self._ok(tx, case_id, case["ver"], data={"exp_id": exp["exp_id"], "place": place})

        return self._mutate(idem_key, payload, by, body)

    def claim_for_posting(self, *, by, kinds=("staff_question", "approval", "confirm_link"), limit=10):
        """planned → in_flight (CAS по строке): claimed_by = роль, claim_boot = boot_id. flight_unknown не берётся (I15).
        Событие на каждый захват — ключ claim:<exp_id>:<row_ver>."""
        _need_by(by)
        ks = [k for k in kinds or () if k in ("staff_question", "approval", "confirm_link")]
        if not ks or len(ks) != len(list(kinds)):
            raise ValueError("kinds ⊆ {staff_question, approval, confirm_link}: %r" % (kinds,))
        if not _int_id(limit) or limit < 1:
            raise ValueError("limit — целое ≥ 1")
        if self.readonly:
            raise ValueError("Store(readonly=True) не пишет")
        con = self._con()
        now = self.clock()
        try:
            con.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError as e:
            raise StoreUnavailable("store_busy: %s" % e)
        tx = _Tx(self, con, None, None, by, now)
        items = []
        try:
            rows = tx.q("SELECT * FROM rc_expect WHERE state='planned' AND kind IN (%s) ORDER BY created_at, exp_id"
                        % ",".join("?" * len(ks)), ks)
            for e in rows:
                if len(items) >= limit:
                    break
                case = self._case(tx, e["case_id"]) if e["case_id"] else None
                if case is not None and case["state"] != "open":
                    continue
                key = "claim:%s:%d" % (e["exp_id"], e["row_ver"])
                if tx.one("SELECT 1 AS x FROM rc_event WHERE idem_key=?", (key,)) is not None:
                    continue
                self._exp_set(tx, e, state="in_flight", next_check="await_post_result", claimed_by=self.role,
                              claim_boot=self.boot_id, claim_at=now)
                payload = {"exp_id": e["exp_id"], "kind": e["kind"], "action": e["action"], "place": e["place"],
                           "state_old": "planned", "state_new": "in_flight", "claimed_by": self.role,
                           "boot": self.boot_id, "why": "claim_for_posting"}
                tx.event("expectation_claimed", payload, case_id=e["case_id"], exp_id=e["exp_id"], key=key)
                item = dict(e)
                item["subject"] = _jl(e["subject"], {})
                item["target"] = _jl(e["target"], None)
                b = self._rental(tx, e["case_id"]) if e["case_id"] else None
                item["bike"] = (b or {}).get("bike_name")
                item["plate"] = (b or {}).get("plate")
                items.append(item)
            err = self._end(con, True)
            if err is not None:
                raise StoreUnavailable("store_busy: %s" % err)
        except StoreUnavailable:
            raise
        except sqlite3.OperationalError as e:
            self._end(con, False)
            raise StoreUnavailable("store_busy: %s" % e) if _is_busy(e) else StoreUnavailable(str(e))
        except Exception:
            self._end(con, False)
            raise
        return items

    def _addressees(self, place):
        """rc_post.addressee_ids: json int-список | "UNKNOWN" (M3); у карточек/confirm_link — APPROVER_IDS."""
        if place == "intake":
            ids = R._as_id_set(self._p("APPROVER_IDS"))
        else:
            ids = R._as_id_set(R._sub(self._p("STAFF_ADDRESSEES"), place))
        if ids is None:
            return UNKNOWN
        return _j(sorted(ids))

    def _insert_posts(self, tx, exp, posts, default_role, plate):
        out = []
        for p in posts:
            if not isinstance(p, Mapping) or not _s(p.get("chat")) or not _s(p.get("msg_id")):
                raise _ArgError("posted — [{place, chat, msg_id, thread_id, role, at}]")
            chat, mid = _s(p.get("chat")), _s(p.get("msg_id"))
            place = _s(p.get("place")) or exp["place"]
            role = _s(p.get("role")) or default_role
            if role not in ("question", "delivery", "agents", "escalation", "card"):
                role = default_role
            ex = tx.one("SELECT * FROM rc_post WHERE chat=? AND msg_id=?", (chat, mid))
            if ex is not None:
                if ex["exp_id"] != exp["exp_id"]:
                    _stop_rej("bad_transition", "пост %s:%s уже записан за другим ожиданием" % (chat, mid))
                continue
            topic_bike = plate if place in ("topic", "delivery") else None
            addr = self._addressees("agents" if role == "escalation" else place)
            at = _num(p.get("at"))
            at = float(at) if at is not None else tx.now
            thread = None if p.get("thread_id") is None else _s(p.get("thread_id"))
            tx.x("INSERT INTO rc_post(chat, msg_id, exp_id, place, role, thread_id, topic_bike, addressee_ids, at) "
                 "VALUES (?,?,?,?,?,?,?,?,?)", (chat, mid, exp["exp_id"], place, role, thread, topic_bike, addr, at))
            out.append({"chat": chat, "msg_id": mid, "place": place, "role": role, "thread_id": thread,
                        "topic_bike": topic_bike, "at": at})
        return out

    @staticmethod
    def _parse_result(result):
        if not isinstance(result, Mapping):
            raise _ArgError("result — словарь")
        keys = [k for k in ("posted", "unknown", "refused", "deduped") if k in result]
        if len(keys) != 1:
            raise _ArgError("result — ровно одно из posted / unknown / refused / deduped: %r" % (sorted(result),))
        if keys[0] == "posted" and (not isinstance(result["posted"], (list, tuple)) or not result["posted"]):
            raise _ArgError("posted — непустой список постов")
        return keys[0]

    def mark_post_result(self, exp_id, *, result, by, idem_key, expect_row_ver):
        """Итог публикации: posted → waiting (agents → escalated), ступень 1, rc_post с адресатами и темой, связывание
        сирот; unknown → flight_unknown(reconcile); refused/deduped → flight_unknown(human_decision). Пост ожидания
        superseded/cancelled записывается без смены состояния (I40)."""
        _need_by(by)
        rk = self._parse_result(result)
        payload = {"op": "mark_post_result", "exp_id": exp_id, "result": dict(result), "by": _by_key(by),
                   "expect_row_ver": expect_row_ver}

        def body(tx):
            exp = self._need_exp(tx, exp_id)
            self._check_row_ver(exp, expect_row_ver, exp["case_id"])
            if exp["kind"] == "readback":
                _stop_rej("bad_transition", "readback не публикуется")
            return self._post_result(tx, exp, result, rk, by, escalation=False)

        return self._mutate(idem_key, payload, by, body)

    def _post_result(self, tx, exp, result, rk, by, escalation):
        st = exp["state"]
        case = self._case(tx, exp["case_id"]) if exp["case_id"] else None
        plate = (self._rental(tx, exp["case_id"]) or {}).get("plate") if case else None
        if escalation:
            default_role = "escalation"
        elif exp["kind"] in ("approval", "confirm_link"):
            default_role = "card"
        else:
            default_role = {"topic": "question", "delivery": "delivery", "agents": "agents"}.get(exp["place"],
                                                                                                "question")
        if rk == "posted":
            if st in ("superseded", "cancelled"):
                posts = self._insert_posts(tx, exp, result["posted"], default_role, plate)
                tx.event("post_recorded_late", {"exp_id": exp["exp_id"], "state": st, "posts": posts,
                                                "chat": posts[0]["chat"] if posts else None,
                                                "msg_id": posts[0]["msg_id"] if posts else None},
                         case_id=exp["case_id"], exp_id=exp["exp_id"], main=True)
                linked = self._link_orphans(tx, posts)
                return self._ok(tx, exp["case_id"], case["ver"] if case else None,
                                data={"exp_id": exp["exp_id"], "state": st, "posts": len(posts), "late": True,
                                      "linked_orphans": linked})
            allowed = ("escalating", "escalation_unknown") if escalation else ("in_flight", "flight_unknown")
            if st not in allowed:
                _stop_rej("bad_transition", "posted из %s" % st)
            if st in ("flight_unknown", "escalation_unknown") and exp["claimed_by"] and exp["claimed_by"] != self.role:
                _stop_rej("bad_transition", "из %s — только роль захвата (%s)" % (st, exp["claimed_by"]))
            posts = self._insert_posts(tx, exp, result["posted"], default_role, plate)
            ats = [p["at"] for p in posts] or [tx.now]
            first_at = ats[0]
            for a in ats:
                if a < first_at:
                    first_at = a
            old = st
            if escalation:
                self._exp_set(tx, exp, state="escalated", next_check="await_agents", escalated_at=first_at)
                etype = "expectation_escalated"
            elif exp["kind"] == "staff_question" and exp["place"] == "agents":
                self._exp_set(tx, exp, state="escalated", next_check="await_agents", waiting_since=first_at,
                              post_at=first_at, escalated_at=first_at, ext_qid=result.get("qid") or exp["ext_qid"])
                etype = "expectation_posted"
            else:
                due = self._business_due(first_at) if exp["kind"] == "staff_question" else None
                self._exp_set(tx, exp, state="waiting", next_check="await_answer", waiting_since=first_at,
                              post_at=first_at, ext_qid=result.get("qid") or exp["ext_qid"], business_due_at=due,
                              due_basis="business" if due is not None else "none")
                etype = "expectation_posted"
            self._exp_event(tx, etype, exp, old, why=rk, posts=posts, qid=result.get("qid"), main=True)
            stage, reason = None, ""
            if not escalation and exp["task_id"] and case is not None and posts:
                task = tx.one("SELECT * FROM rc_task WHERE task_id=?", (exp["task_id"],))
                if task is not None and task["case_id"] != case["case_id"]:   # R5 (C26 XCASE): второй рубеж
                    reason = "evidence_foreign"   # задача не дела ожидания: ступени 1 нет, пост и переход есть (I40)
                elif task is not None and task["state"] == "open":
                    p0 = posts[0]
                    ev = {"kind": "post", "exp_id": exp["exp_id"], "chat": p0["chat"], "msg_id": p0["msg_id"],
                          "ref": "post:%s:%s" % (p0["chat"], p0["msg_id"]), "task_id": exp["task_id"]}
                    ok, code = self._stage_check(tx, case, task, "question_sent", ev, by)
                    if ok:
                        self._stage_write(tx, case, task, "question_sent", ev, [code] if code else [],
                                          "stage:%s:question_sent" % exp["task_id"])
                        stage = "question_sent"
            linked = self._link_orphans(tx, posts)
            return self._ok(tx, exp["case_id"], case["ver"] if case else None,
                            data={"exp_id": exp["exp_id"], "state": exp["state"], "posts": len(posts), "stage": stage,
                                  "linked_orphans": linked, "business_due_at": exp.get("business_due_at")},
                            reason=reason)
        if st in ("superseded", "cancelled"):
            _stop_rej("expect_state", "ожидание %s: неизвестный исход поста ничего не меняет" % st)
        if escalation:
            if st != "escalating":
                _stop_rej("bad_transition", "%s из %s" % (rk, st))
            old = st
            self._exp_set(tx, exp, state="escalation_unknown", next_check="human_decision")
            self._exp_event(tx, "expectation_escalation_unknown", exp, old, why="%s:%s" % (rk, _s(result.get(rk))),
                            main=True)
        else:
            if st != "in_flight":
                _stop_rej("bad_transition", "%s из %s" % (rk, st))
            old = st
            nc = "reconcile" if rk == "unknown" else "human_decision"
            cols = {"state": "flight_unknown", "next_check": nc}
            if rk == "deduped" and _s(result.get("deduped")):
                cols["ext_qid"] = _s(result.get("deduped"))
            self._exp_set(tx, exp, **cols)
            self._exp_event(tx, "expectation_flight_unknown", exp, old, why="%s:%s" % (rk, _s(result.get(rk))),
                            main=True)
        return self._ok(tx, exp["case_id"], case["ver"] if case else None,
                        data={"exp_id": exp["exp_id"], "state": exp["state"], "next_check": exp["next_check"]})

    def claim_execution(self, exp_id, *, by, idem_key, expect_row_ver, expect_ver=None):
        """readback planned → in_flight; CAS версии дела против parent_exp.case_ver (P-M9): conflict → моста не звать."""
        _need_by(by)
        payload = {"op": "claim_execution", "exp_id": exp_id, "by": _by_key(by), "expect_row_ver": expect_row_ver,
                   "expect_ver": expect_ver}

        def body(tx):
            exp = self._need_exp(tx, exp_id)
            self._check_row_ver(exp, expect_row_ver, exp["case_id"])
            if exp["kind"] != "readback" or exp["state"] != "planned":
                _stop_rej("bad_transition", "claim_execution: %s/%s" % (exp["kind"], exp["state"]))
            ver = None
            if exp["case_id"]:
                case = self._need_case(tx, exp["case_id"])
                ver = case["ver"]
                parent = self._exp(tx, exp["parent_exp"]) if exp["parent_exp"] else None
                base = parent["case_ver"] if parent is not None and parent["case_ver"] is not None else exp["case_ver"]
                if base is not None and case["ver"] != base:
                    _stop_conflict(base, case["ver"], case_id=case["case_id"], ver=case["ver"])
                if expect_ver is not None and expect_ver != case["ver"]:
                    _stop_conflict(expect_ver, case["ver"], case_id=case["case_id"], ver=case["ver"])
            old = exp["state"]
            self._exp_set(tx, exp, state="in_flight", next_check="execute", claimed_by=self.role,
                          claim_boot=self.boot_id, claim_at=tx.now)
            self._exp_event(tx, "expectation_execution_claimed", exp, old, why="claim_execution", main=True,
                            claimed_by=self.role, boot=self.boot_id)
            return self._ok(tx, exp["case_id"], ver, data={"exp_id": exp_id, "state": "in_flight",
                                                           "target": _jl(exp["target"], None)})

        return self._mutate(idem_key, payload, by, body)

    def mark_written(self, exp_id, *, result, by, idem_key, expect_row_ver):
        if not isinstance(result, Mapping):
            raise ValueError("result — {ok, row, written_at} | {unknown} | {error}")
        _need_by(by)
        payload = {"op": "mark_written", "exp_id": exp_id, "result": dict(result), "by": _by_key(by),
                   "expect_row_ver": expect_row_ver}

        def body(tx):
            exp = self._need_exp(tx, exp_id)
            self._check_row_ver(exp, expect_row_ver, exp["case_id"])
            if exp["kind"] != "readback" or exp["state"] != "in_flight":
                _stop_rej("bad_transition", "mark_written: %s/%s" % (exp["kind"], exp["state"]))
            old = exp["state"]
            if result.get("ok") is True:
                wa = _num(result.get("written_at"))
                wa = float(wa) if wa is not None else tx.now
                self._exp_set(tx, exp, state="waiting", next_check="readback", waiting_since=wa, post_at=wa)
                why = "written"
            elif "unknown" in result:
                self._exp_set(tx, exp, state="flight_unknown", next_check="readback")
                why = "unknown:%s" % _s(result.get("unknown"))
            elif "error" in result:
                self._exp_set(tx, exp, state="waiting", next_check="human_decision")
                why = "error:%s" % _s(result.get("error"))
            else:
                raise _ArgError("result — {ok: True, …} | {unknown} | {error}")
            self._exp_event(tx, "expectation_written", exp, old, why=why, main=True, row=result.get("row"))
            case = self._case(tx, exp["case_id"]) if exp["case_id"] else None
            return self._ok(tx, exp["case_id"], case["ver"] if case else None,
                            data={"exp_id": exp_id, "state": exp["state"], "next_check": exp["next_check"]})

        return self._mutate(idem_key, payload, by, body)

    # ----- ответы -----

    def _known_chats(self, tx, e):
        chats = set()
        if e.get("chat"):
            chats.add(e["chat"])
        for p in tx.q("SELECT DISTINCT chat FROM rc_post WHERE exp_id=?", (e["exp_id"],)):
            chats.add(p["chat"])
        if e["kind"] == "staff_question":
            places = list((_jl(e.get("subject"), {}) or {}).get("places") or [e["place"]])
            if e["state"] == "escalation_unknown":
                places.append("agents")
            for p in tx.q("SELECT DISTINCT chat FROM rc_post WHERE place IN (%s)" % ",".join("?" * len(places)),
                          places):
                chats.add(p["chat"])
        elif e["kind"] in ("approval", "confirm_link"):
            for p in tx.q("SELECT DISTINCT chat FROM rc_post WHERE place='intake'"):
                chats.add(p["chat"])
        return chats

    def _orphan_place(self, tx, chat):
        """Есть ли ожидание flight_unknown/escalation_unknown «в этом чате». Чат ожидания неизвестен (пост не дошёл до
        нас, а мест вопроса хранилище ещё не видело) — реплай боту сохраняется сиротой: свершившееся не теряется (I40)."""
        for e in tx.q("SELECT * FROM rc_expect WHERE state IN ('flight_unknown','escalation_unknown') "
                      "ORDER BY created_at, exp_id"):
            chats = self._known_chats(tx, e)
            if not chats or chat in chats:
                return True
        return False

    def _waiting_card(self, tx, chat):
        for action in APPROVAL_ORDER:
            e = tx.one("SELECT * FROM rc_expect WHERE kind='approval' AND chat=? AND action=? AND state='waiting' "
                       "ORDER BY created_at DESC, exp_id DESC LIMIT 1", (chat, action))
            if e is not None:
                return e
        return None

    def _answer_dup(self, tx, chat, mid):
        a = tx.one("SELECT * FROM rc_answer WHERE chat=? AND msg_id=?", (chat, mid))
        o = tx.one("SELECT * FROM rc_reply_unlinked WHERE chat=? AND msg_id=?", (chat, mid))
        if a is None and o is None:
            return None
        ev = tx.one("SELECT seq FROM rc_event WHERE idem_key=?", ("ans:%s:%s" % (chat, mid),))
        # §4.7 п.3 и §5.4: у duplicate data.decision = None и execute = False (I28: исполнение — только вызов, сделавший
        # переход); исход — по естественному ключу (chat, msg_id), а не по хешу аргументов повтора.
        data = {"verdict": a["verdict"] if a else "orphan", "answer_id": a["id"] if a else None,
                "orphan_id": o["id"] if o else None, "exp_id": a["exp_id"] if a else None, "stage": None,
                "decision": None, "execute": False, "readback_exp_id": None, "card_age_s": None, "duplicate": True}
        cid = a["case_id"] if a else None
        ver = None
        if cid:
            c = self._case(tx, cid)
            ver = c["ver"] if c else None
        return _out("duplicate", case_id=cid, ver=ver, data=data, event_seq=ev["seq"] if ev else None,
                    verdict=data["verdict"])

    def _on_reply(self, side, chat, msg_id, reply_to, reply_to_is_bot, thread_id, author_id, author_username, is_bot,
                  text, at, by):
        chat_s, mid_s = _s(chat), _s(msg_id)
        if not chat_s or not mid_s:
            raise ValueError("chat и msg_id — непустые")
        if _num(at) is None:
            raise ValueError("at — время сообщения Telegram (секунды эпохи)")
        _need_by(by)
        rt = _s(reply_to)
        key = "ans:%s:%s" % (chat_s, mid_s)
        payload = {"op": "on_%s_reply" % side, "chat": chat_s, "msg_id": mid_s, "reply_to": rt,
                   "reply_to_is_bot": bool(reply_to_is_bot), "thread_id": None if thread_id is None else _s(thread_id),
                   "author_id": author_id, "author_username": author_username, "is_bot": bool(is_bot), "text": text,
                   "at": float(at)}
        ans = {"chat": chat_s, "msg_id": mid_s, "reply_to": rt, "thread_id": None if thread_id is None else _s(thread_id),
               "author_id": author_id, "author_username": author_username, "text": text, "at": float(at),
               "is_bot": bool(is_bot), "boot_id": self.boot_id}

        def body(tx):
            if is_bot or not _s(text):
                _stop_rej("not_reply", "бот или пустой текст")
            post, exp = None, None
            if not rt:
                if side == "staff":
                    _stop_rej("not_reply", "нет reply_to")
                rule = self._p("APPROVAL_REPLY_REQUIRED")
                if rule is True:
                    _stop_rej("not_reply", "APPROVAL_REPLY_REQUIRED: «да» только реплаем")
                card = self._waiting_card(tx, chat_s)
                dec = R.approval_decision(text, self.params)
                if card is None or (rule is not False and dec == "unclear"):
                    _stop_rej("not_reply", "без реплая и без слова решения к ждущей карточке")
                dup = self._answer_dup(tx, chat_s, mid_s)
                if dup is not None:
                    raise _Stop(dup)
                exp = card
            else:
                post = tx.one("SELECT * FROM rc_post WHERE chat=? AND msg_id=?", (chat_s, rt))
                if post is None:
                    dup = self._answer_dup(tx, chat_s, mid_s)
                    if dup is not None:
                        raise _Stop(dup)
                    if reply_to_is_bot and self._orphan_place(tx, chat_s):
                        cur = tx.x("INSERT INTO rc_reply_unlinked(chat, msg_id, reply_to, thread_id, author_id, "
                                   "author_username, at, received_at, text, state) VALUES (?,?,?,?,?,?,?,?,?,'orphan')",
                                   (chat_s, mid_s, rt, ans["thread_id"], author_id if _int_id(author_id) else None,
                                    author_username, float(at), tx.now, _s(text)))
                        oid = cur.lastrowid
                        tx.event("answer_orphaned", {"orphan_id": oid, "exp_id": None, "chat": chat_s, "msg_id": mid_s,
                                                     "reply_to": rt, "author_id": author_id, "verdict": "orphan",
                                                     "decision": None, "execute": False}, main=True)
                        return _out("ok", data={"verdict": "orphan", "orphan_id": oid, "answer_id": None,
                                                "exp_id": None, "stage": None, "decision": None, "execute": False},
                                    event_seq=tx.main_seq, verdict="orphan")
                    _stop_rej("not_linked", "реплай не на пост ожидания")
                exp = self._exp(tx, post["exp_id"])
            if side == "staff" and exp["kind"] != "staff_question":
                _stop_rej("not_linked", "пост не вопроса сотрудникам")
            if side == "approval" and exp["kind"] not in ("approval", "confirm_link"):
                _stop_rej("not_linked", "пост не карточки одобряющего")
            dup = self._answer_dup(tx, chat_s, mid_s)
            if dup is not None:
                raise _Stop(dup)
            data = self._judge_answer(tx, exp, post, ans, tx.now, main=True)
            case = self._case(tx, exp["case_id"]) if exp["case_id"] else None
            return _out("ok", case_id=exp["case_id"], ver=case["ver"] if case else None, data=data,
                        event_seq=tx.main_seq, verdict=data["verdict"])

        return self._mutate(key, payload, by, body, natural=lambda tx: self._answer_dup(tx, chat_s, mid_s))

    def _judge_answer(self, tx, exp, post, ans, received_at, main):
        """Вердикт ответа (rules.answer_verdict, §4.7) + строка rc_answer + переход ожидания/ступень 2/readback."""
        case = self._case(tx, exp["case_id"]) if exp["case_id"] else None
        cinfo = None
        if case is not None:
            b = self._rental(tx, case["case_id"]) or {}
            cinfo = {"ver": case["ver"], "link_state": case["link_state"], "plate": b.get("plate"),
                     "confirm_open": self._confirm_open(tx, case["case_id"]) is not None}
        verdict = R.answer_verdict(exp, cinfo, post, ans, self.params)
        if verdict in ("not_reply", "not_linked"):
            _stop_rej(verdict)
        kind = exp["kind"]
        if kind in ("approval", "confirm_link"):
            decision = R.approval_decision(ans["text"], self.params)
        else:
            decision = R.accept_decision(ans["text"], self.params)
        live = exp["state"] in EXPECT_LIVE_ANSWER
        if live:
            self._skew(tx, exp)
        # I28 дословно: execute = 1 ⇔ accepted ∧ decision == yes ∧ переход в answered делает ЭТОТ вызов (live).
        execute = 1 if (verdict == "accepted" and decision == "yes" and live) else 0
        post_role = post["role"] if post is not None else "card"
        cur = tx.x("INSERT INTO rc_answer(exp_id, case_id, chat, msg_id, reply_to, thread_id, post_role, author_id, "
                   "author_username, at, received_at, text, verdict, decision, execute, case_ver_at, promoted_by) "
                   "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL)",
                   (exp["exp_id"], exp["case_id"], ans["chat"], ans["msg_id"], ans["reply_to"] or "", ans["thread_id"],
                    post_role, ans["author_id"] if _int_id(ans["author_id"]) else None, ans.get("author_username"),
                    ans["at"], received_at, _s(ans["text"]), verdict, decision, execute,
                    case["ver"] if case else None))
        aid = cur.lastrowid
        stage, rb_id, fact_id = None, None, None
        if verdict == "accepted" and live:
            old = exp["state"]
            self._exp_set(tx, exp, state="answered", next_check="none", answer_id=aid)
            self._exp_event(tx, "expectation_answered", exp, old, why="accepted")
            if kind == "staff_question" and case is not None:
                fact_id, stage = self._staff_answer_effects(tx, case, exp, post, ans, aid, received_at, decision)
            elif kind == "approval" and decision == "yes":
                subj = _jl(exp["subject"], {}) or {}
                tgt = _jl(exp["target"], None) or {"card": subj.get("ref"), "action": exp["action"]}
                rb = self._insert_exp(tx, case, "readback", "crm", {"from_card": exp["exp_id"], "action": exp["action"],
                                                                    "card_ref": subj.get("ref")},
                                      self._unique_idem(tx, "rc_expect", "rb:%s" % exp["exp_id"]),
                                      next_check="execute", task_id=exp["task_id"], action=exp["action"], target=tgt,
                                      parent_exp=exp["exp_id"])
                self._exp_event(tx, "expectation_planned", rb, None, why="approval_yes")
                rb_id = rb["exp_id"]
        out_decision = decision if verdict in ("accepted", "reference_no_reply") else None
        card_age = None
        if kind == "approval" and post is not None and _num(post.get("at")) is not None:
            card_age = ans["at"] - post["at"]
        place = post["place"] if post is not None else None
        tx.event("answer_received", {"answer_id": aid, "exp_id": exp["exp_id"], "chat": ans["chat"],
                                     "msg_id": ans["msg_id"], "reply_to": ans["reply_to"],
                                     "author_id": ans["author_id"], "verdict": verdict, "decision": decision,
                                     "execute": bool(execute), "place": place, "stage": stage},
                 case_id=exp["case_id"], exp_id=exp["exp_id"], main=main)
        return {"verdict": verdict, "answer_id": aid, "exp_id": exp["exp_id"], "stage": stage,
                "decision": out_decision, "execute": bool(execute), "readback_exp_id": rb_id,
                "card_age_s": card_age, "fact_id": fact_id}

    def _staff_answer_effects(self, tx, case, exp, post, ans, aid, received_at, decision):
        src = {"name": "staff_ask:%s" % (post["place"] if post is not None else exp["place"]),
               "ref": "%s:%s" % (ans["chat"], ans["msg_id"]), "method": "reply", "read_at": received_at,
               "observed_at": ans["at"]}
        fk = ["staff_answer", ans["chat"], ans["msg_id"]]
        value = {"text": _s(ans["text"]), "author_id": ans["author_id"], "exp_id": exp["exp_id"], "answer_id": aid,
                 "decision": decision, "place": post["place"] if post is not None else exp["place"],
                 "question": (_jl(exp["subject"], {}) or {}).get("q_ru")}
        fid = self._fact_insert(tx, case, "staff_answer", value, fk, src, "version",
                                self._unique_idem(tx, "rc_fact", "fact:%s:%s" % (case["case_id"], _j(fk))),
                                why="accepted_answer")
        stage = None
        if exp["task_id"]:
            task = tx.one("SELECT * FROM rc_task WHERE task_id=?", (exp["task_id"],))
            if task is not None and task["state"] == "open":
                ev = {"kind": "answer", "answer_id": aid, "ref": "ans:%s:%s" % (ans["chat"], ans["msg_id"])}
                ok, code = self._stage_check(tx, case, task, "answer_received", ev, None)
                if ok:
                    self._stage_write(tx, case, task, "answer_received", ev, [code] if code else [],
                                      "stage:%s:answer_received" % task["task_id"])
                    stage = "answer_received"
        return fid, stage

    def _link_orphans(self, tx, posts):
        """Сироты с reply_to из новых постов связываются и получают вердикт в той же транзакции (I40)."""
        linked = []
        for p in posts:
            for o in tx.q("SELECT * FROM rc_reply_unlinked WHERE state='orphan' AND chat=? AND reply_to=? ORDER BY id",
                          (p["chat"], p["msg_id"])):
                post = tx.one("SELECT * FROM rc_post WHERE chat=? AND msg_id=?", (p["chat"], p["msg_id"]))
                exp = self._exp(tx, post["exp_id"])
                ans = {"chat": o["chat"], "msg_id": o["msg_id"], "reply_to": o["reply_to"], "thread_id": o["thread_id"],
                       "author_id": o["author_id"], "author_username": o["author_username"], "text": o["text"],
                       "at": o["at"], "is_bot": False, "boot_id": self.boot_id}
                try:
                    data = self._judge_answer(tx, exp, post, ans, o["received_at"], main=False)
                except _Stop:
                    continue
                tx.x("UPDATE rc_reply_unlinked SET state='linked', answer_id=? WHERE id=?", (data["answer_id"], o["id"]))
                tx.event("orphan_linked", {"orphan_id": o["id"], "answer_id": data["answer_id"],
                                           "exp_id": exp["exp_id"], "chat": o["chat"], "msg_id": o["msg_id"],
                                           "reply_to": o["reply_to"], "author_id": o["author_id"],
                                           "verdict": data["verdict"], "decision": data["decision"],
                                           "execute": data["execute"]},
                         case_id=exp["case_id"], exp_id=exp["exp_id"])
                linked.append({"orphan_id": o["id"], "answer_id": data["answer_id"], "verdict": data["verdict"],
                               "execute": data["execute"], "readback_exp_id": data["readback_exp_id"]})
        return linked

    def on_staff_answer(self, *, chat, msg_id, reply_to, reply_to_is_bot, thread_id, author_id, author_username,
                        is_bot, text, at, by):
        """Ответ сотрудника (шов S5): вердикт §4.7; справки пишутся строкой rc_answer и ожидание не двигают (I9)."""
        return self._on_reply("staff", chat, msg_id, reply_to, reply_to_is_bot, thread_id, author_id, author_username,
                              is_bot, text, at, by)

    def on_approval_reply(self, *, chat, msg_id, reply_to, reply_to_is_bot, thread_id, author_id, author_username,
                          is_bot, text, at, by):
        """«Да»/«нет» одобряющего на карточку или confirm_link: execute=True ⇔ accepted ∧ yes ∧ переход этим вызовом (I28);
        без реплая при APPROVAL_REPLY_REQUIRED=UNKNOWN — справка reference_no_reply (I16, I39)."""
        return self._on_reply("approval", chat, msg_id, reply_to, reply_to_is_bot, thread_id, author_id,
                              author_username, is_bot, text, at, by)

    def promote_answer(self, answer_id, *, by, idem_key):
        _need_by(by)
        payload = {"op": "promote_answer", "answer_id": answer_id, "by": _by_key(by)}

        def body(tx):
            if not self._approver(by):
                _stop_rej("approver_unknown", "справку принимает только одобряющий по id")
            a = tx.one("SELECT * FROM rc_answer WHERE id=?", (answer_id,)) if _int_id(answer_id) else None
            if a is None:
                _stop_rej("evidence_missing", "ответа нет")
            exp = self._exp(tx, a["exp_id"])
            if exp["state"] not in EXPECT_LIVE_ANSWER:
                _stop_rej("expect_state", "ожидание %s" % exp["state"])
            case = self._need_case(tx, exp["case_id"]) if exp["case_id"] else None
            if case is not None and exp["case_ver"] != case["ver"]:
                _stop_rej("expect_state", "версия дела ушла вперёд (%s → %s)" % (exp["case_ver"], case["ver"]))
            tx.x("UPDATE rc_answer SET promoted_by=? WHERE id=?", (_author(by), answer_id))
            old = exp["state"]
            self._exp_set(tx, exp, state="answered", next_check="none", answer_id=answer_id)
            self._exp_event(tx, "expectation_answered", exp, old, why="promoted")
            stage, fid = None, None
            if exp["kind"] == "staff_question" and case is not None:
                post = tx.one("SELECT * FROM rc_post WHERE chat=? AND msg_id=?", (a["chat"], a["reply_to"]))
                ans = {"chat": a["chat"], "msg_id": a["msg_id"], "reply_to": a["reply_to"], "thread_id": a["thread_id"],
                       "author_id": a["author_id"], "text": a["text"], "at": a["at"]}
                fid, stage = self._staff_answer_effects(tx, case, exp, post, ans, answer_id, a["received_at"],
                                                        a["decision"])
            tx.event("answer_promoted", {"answer_id": answer_id, "exp_id": exp["exp_id"], "stage": stage},
                     case_id=exp["case_id"], exp_id=exp["exp_id"], main=True)
            return self._ok(tx, exp["case_id"], case["ver"] if case else None,
                            data={"answer_id": answer_id, "exp_id": exp["exp_id"], "stage": stage, "fact_id": fid})

        return self._mutate(idem_key, payload, by, body)

    def on_readback(self, exp_id, *, evidence, by, idem_key):
        """Итог чтения назад (словарь write_fact): landed → answered (+ ступень 5 при записанной 4, иначе reason=order);
        absent → waiting/human_decision; unknown → повторное чтение позже (next_check=readback)."""
        if not isinstance(evidence, Mapping) or evidence.get("outcome") not in ("landed", "absent", "unknown"):
            raise ValueError("evidence.outcome ∈ {landed, absent, unknown}")
        _need_by(by)
        payload = {"op": "on_readback", "exp_id": exp_id, "evidence": dict(evidence), "by": _by_key(by)}

        def body(tx):
            exp = self._need_exp(tx, exp_id)
            if exp["kind"] != "readback":
                _stop_rej("bad_transition", "on_readback только для readback")
            if exp["state"] in EXPECT_TERMINAL:
                _stop_rej("expect_state", "ожидание %s" % exp["state"])
            if exp["state"] not in ("in_flight", "waiting", "flight_unknown"):
                _stop_rej("bad_transition", "on_readback из %s" % exp["state"])
            tgt = _jl(exp["target"], None)
            if not _target_ok(evidence.get("target"), tgt):
                _stop_rej("readback_mismatch", "цель чтения ≠ цели ожидания")
            case = self._case(tx, exp["case_id"]) if exp["case_id"] else None
            if case is not None and case["state"] != "open":
                _stop_rej("case_%s" % case["state"], case_id=case["case_id"], ver=case["ver"])
            outcome = evidence.get("outcome")
            old = exp["state"]
            if outcome == "absent":
                self._exp_set(tx, exp, state="waiting", next_check="human_decision")
                self._exp_event(tx, "readback_absent", exp, old, why="absent", main=True)
                return self._ok(tx, exp["case_id"], case["ver"] if case else None,
                                data={"exp_id": exp_id, "state": "waiting", "next_check": "human_decision"})
            if outcome == "unknown":
                self._exp_set(tx, exp, next_check="readback")
                self._exp_event(tx, "readback_unknown", exp, old, why="unknown", main=True)
                return self._ok(tx, exp["case_id"], case["ver"] if case else None,
                                data={"exp_id": exp_id, "state": exp["state"], "next_check": "readback"})
            fid = None
            if case is not None:
                ra = _num(evidence.get("read_at"))
                src = {"name": _s(evidence.get("source")) or "readback", "ref": _s(evidence.get("ref")) or exp_id,
                       "method": "readback", "read_at": float(ra) if ra is not None else tx.now,
                       "observed_at": float(_num(evidence.get("observed_at")) or (ra if ra is not None else tx.now))}
                fk = ["readback", src["name"], src["ref"]]
                last = self._fact_latest(tx, case["case_id"], fk)
                if last is None or float(src["observed_at"]) > float(last["observed_at"]):
                    value = dict((k, v) for k, v in evidence.items() if k != "siblings")
                    value["exp_id"] = exp_id
                    fid = self._fact_insert(tx, case, "readback", value, fk, src, "case",
                                            self._unique_idem(tx, "rc_fact", "fact:%s:%s" % (case["case_id"], _j(fk))),
                                            why="landed")
                else:
                    fid = last["id"]
            self._exp_set(tx, exp, state="answered", next_check="none")
            self._exp_event(tx, "expectation_answered", exp, old, why="landed", main=True)
            stage, reason = None, ""
            if exp["task_id"] and case is not None:
                task = tx.one("SELECT * FROM rc_task WHERE task_id=?", (exp["task_id"],))
                if task is not None and task["case_id"] != case["case_id"]:   # R5 (C26 XCASE): второй рубеж
                    reason = "evidence_foreign"   # задача не дела ожидания — ступени 5 нет, факт readback записан
                elif task is not None and task["state"] == "cancelled":
                    self._attention_on(tx, case, "physical", "readback_of_cancelled_task:%s" % task["task_id"])
                    reason = "task_cancelled"
                elif task is not None and task["state"] == "open":
                    ev = dict(evidence)
                    ev["task_id"] = exp["task_id"]
                    ok, code = self._stage_check(tx, case, task, "result_recorded", ev, by)
                    if ok:
                        self._stage_write(tx, case, task, "result_recorded", ev, [code] if code else [],
                                          "stage:%s:result_recorded" % task["task_id"])
                        stage = "result_recorded"
                    else:
                        reason = code or "order"
                elif task is not None:
                    reason = "order"
            touched = []
            for s in evidence.get("siblings") or []:
                if not isinstance(s, Mapping) or s.get("status_old") == s.get("status_new"):
                    continue
                for oc in tx.q("SELECT k.* FROM rc_case k JOIN rc_rental r ON r.case_id=k.case_id AND r.current=1 "
                               "WHERE k.state='open' ORDER BY k.created_at, k.case_id"):
                    if case is not None and oc["case_id"] == case["case_id"]:
                        continue
                    r = self._rental(tx, oc["case_id"]) or {}
                    if ((s.get("row") is not None and r.get("crm_row_seen") == s.get("row"))
                            or (_s(s.get("booking_id")) and r.get("booking_id") == _s(s.get("booking_id")))):
                        self._attention_on(tx, oc, "readback", "sibling_changed:%s" % exp_id)
                        touched.append(oc["case_id"])
            return self._ok(tx, exp["case_id"], case["ver"] if case else None,
                            data={"exp_id": exp_id, "stage": stage, "fact_id": fid, "siblings_attention": touched},
                            reason=reason)

        return self._mutate(idem_key, payload, by, body)

    def due_expectations(self, *, now=None):
        """staff_question в waiting вне agents, эскалаций не было, business_due_at задан и ≤ now (I43)."""
        def body(tx):
            t = tx.now if now is None else float(now)
            out = []
            for e in tx.q("SELECT * FROM rc_expect WHERE kind='staff_question' AND state='waiting' AND place<>'agents' "
                          "AND escalated_at IS NULL AND business_due_at IS NOT NULL AND business_due_at<=? "
                          "ORDER BY business_due_at, exp_id", (t,)):
                out.append({"exp_id": e["exp_id"], "case_id": e["case_id"], "business_due_at": e["business_due_at"],
                            "ext_qid": e["ext_qid"], "row_ver": e["row_ver"]})
            return out

        return self._read(body)

    def claim_escalation(self, exp_id, *, by, idem_key, expect_row_ver):
        _need_by(by)
        payload = {"op": "claim_escalation", "exp_id": exp_id, "by": _by_key(by), "expect_row_ver": expect_row_ver}

        def body(tx):
            exp = self._need_exp(tx, exp_id)
            self._check_row_ver(exp, expect_row_ver, exp["case_id"])
            if exp["kind"] != "staff_question" or exp["state"] != "waiting" or exp["escalated_at"] is not None:
                _stop_rej("bad_transition", "эскалация из %s/%s" % (exp["kind"], exp["state"]))
            case = self._need_case(tx, exp["case_id"])
            due = exp["business_due_at"]
            if not ((due is not None and due <= tx.now) or self._approver(by)):
                _stop_rej("param_unknown", "WAIT_BEFORE_AGENTS: срока нет — эскалирует одобряющий по id (I43)")
            self._skew(tx, exp)
            old = exp["state"]
            self._exp_set(tx, exp, state="escalating", next_check="await_escalation", claimed_by=self.role,
                          claim_boot=self.boot_id, claim_at=tx.now)
            self._exp_event(tx, "expectation_escalation_claimed", exp, old,
                            why="business_due" if (due is not None and due <= tx.now) else "approver", main=True,
                            claimed_by=self.role, boot=self.boot_id)
            return self._ok(tx, case["case_id"], case["ver"], data={"exp_id": exp_id, "state": "escalating",
                                                                    "ext_qid": exp["ext_qid"]})

        return self._mutate(idem_key, payload, by, body)

    def mark_escalated(self, exp_id, *, result, by, idem_key, expect_row_ver):
        _need_by(by)
        rk = self._parse_result(result)
        payload = {"op": "mark_escalated", "exp_id": exp_id, "result": dict(result), "by": _by_key(by),
                   "expect_row_ver": expect_row_ver}

        def body(tx):
            exp = self._need_exp(tx, exp_id)
            self._check_row_ver(exp, expect_row_ver, exp["case_id"])
            if exp["kind"] != "staff_question":
                _stop_rej("bad_transition", "эскалация только вопроса сотрудникам")
            if exp["state"] not in ("escalating", "escalation_unknown"):
                _stop_rej("bad_transition", "mark_escalated из %s" % exp["state"])
            return self._post_result(tx, exp, result, rk, by, escalation=True)

        return self._mutate(idem_key, payload, by, body)

    def cancel_expectation(self, exp_id, *, reason, by, idem_key):
        _need_by(by)
        payload = {"op": "cancel_expectation", "exp_id": exp_id, "reason": reason, "by": _by_key(by)}

        def body(tx):
            if not self._approver(by):
                _stop_rej("approver_unknown", "отмена ожидания — только одобряющий по id")
            exp = self._need_exp(tx, exp_id)
            if exp["state"] in EXPECT_TERMINAL:
                _stop_rej("expect_state", "ожидание %s" % exp["state"])
            old = exp["state"]
            self._exp_set(tx, exp, state="cancelled", next_check="none", reason=_s(reason) or "cancel_expectation")
            self._exp_event(tx, "expectation_cancelled", exp, old, why=_s(reason), main=True)
            qids = [exp["ext_qid"]] if exp["kind"] == "staff_question" and exp["ext_qid"] else []
            case = self._case(tx, exp["case_id"]) if exp["case_id"] else None
            return self._ok(tx, exp["case_id"], case["ver"] if case else None,
                            data={"exp_id": exp_id, "staff_qids_to_close": qids})

        return self._mutate(idem_key, payload, by, body)


    # =================================================================================================================
    # Уведомление клиента, вмешательство, закрытие (CONTRACT §5.5, §4.3, §4.1)
    # =================================================================================================================

    def _need_notice(self, tx, notice_id):
        if not isinstance(notice_id, str) or not notice_id:
            raise _ArgError("notice_id — непустая строка")
        n = tx.one("SELECT * FROM rc_notice WHERE notice_id=?", (notice_id,))
        if n is None:
            _stop_rej("bad_transition", "намерения нет", data={"notice_id": notice_id})
        return n

    def _notice_set(self, tx, n, **cols):
        cols["row_ver"] = n["row_ver"] + 1
        cols["updated_at"] = tx.now
        names = sorted(cols)
        tx.x("UPDATE rc_notice SET %s WHERE notice_id=?" % ", ".join("%s=?" % k for k in names),
             [cols[k] for k in names] + [n["notice_id"]])
        n.update(cols)

    def _notice_event(self, tx, etype, n, old, why="", main=False, **extra):
        p = {"notice_id": n["notice_id"], "intent": n["intent"], "state_old": old, "state_new": n["state"], "why": why}
        p.update(extra)
        return tx.event(etype, p, case_id=n["case_id"], main=main)

    def propose_client_notice(self, case_id, *, task_id, intent, fact_ids, by, idem_key, expect_ver):
        """Только НАМЕРЕНИЕ (черновик ведёт WA, отправку — человек): задача на ступени 5 текущей версии, внимания нет,
        привязка ok, нет confirm_link, FEEDS_CONNECTED ⊇ {intervention, inbound}."""
        if not _s(intent):
            raise ValueError("intent — непустой")
        ids = list(fact_ids or [])
        if any(not _int_id(i) for i in ids):
            raise ValueError("fact_ids — целые id фактов")
        _need_by(by)
        payload = {"op": "propose_client_notice", "case_id": case_id, "task_id": task_id, "intent": intent,
                   "fact_ids": ids, "by": _by_key(by), "expect_ver": expect_ver}

        def body(tx):
            case = self._need_case(tx, case_id)
            self._check_ver(case, expect_ver)
            task = self._need_task(tx, case_id, task_id)
            if case["attention"]:
                _stop_rej("attention", "стоит внимание (вмешательство человека) — клиентских намерений нет (I24)")
            if task["top_stage"] < 5 or task["state"] != "done" or task["case_ver"] != case["ver"]:
                _stop_rej("order", "задача не на ступени 5 текущей версии")
            if case["link_state"] != "ok" or self._confirm_open(tx, case_id) is not None:
                _stop_rej("link_drift", "привязка аренды не подтверждена")
            feeds = self._p("FEEDS_CONNECTED")
            feeds = set(feeds) if isinstance(feeds, (set, frozenset, list, tuple)) else set()
            if not set(("intervention", "inbound")) <= feeds:
                _stop_rej("feed_unknown", "FEEDS_CONNECTED не включает intervention и inbound")
            live = tx.one("SELECT * FROM rc_notice WHERE case_id=? AND task_id=? AND intent=? AND state IN "
                          "('intent','drafting','draft_unknown','drafted') ORDER BY created_at LIMIT 1",
                          (case_id, task_id, intent))
            if live is not None:
                seq = None                 # К4 круг 4: event_seq первого раза — событие ЭТОГО уведомления (§1.3)
                for e in tx.q("SELECT seq, payload FROM rc_event WHERE type='notice_proposed' AND case_id=? "
                              "ORDER BY seq", (case_id,)):
                    if (_jl(e["payload"], {}) or {}).get("notice_id") == live["notice_id"]:
                        seq = e["seq"]
                        break
                raise _Stop(_out("duplicate", case_id=case_id, ver=case["ver"], event_seq=seq,
                                 data={"notice_id": live["notice_id"], "duplicate": True}))
            facts = []
            for fid in ids:
                f = tx.one("SELECT * FROM rc_fact WHERE id=? AND case_id=?", (fid, case_id))
                if f is None or f["state"] != "valid":
                    _stop_rej("evidence_missing", "факт %s не valid-факт этого дела" % fid)
                facts.append({"fact_id": fid, "kind": f["kind"], "value": _jl(f["value"], {}),
                              "src": {"source": f["source"], "ref": f["ref"], "method": f["method"],
                                      "read_at": f["read_at"], "observed_at": f["observed_at"],
                                      "case_ver": f["case_ver"]}})
            nid = "RN-" + self.new_id()
            tx.x("INSERT INTO rc_notice(notice_id, case_id, task_id, intent, facts, case_ver, state, created_at, "
                 "updated_at, row_ver, idem_key) VALUES (?,?,?,?,?,?,'intent',?,?,1,?)",
                 (nid, case_id, task_id, intent, _j(facts), case["ver"], tx.now, tx.now,
                  self._unique_idem(tx, "rc_notice", idem_key)))
            tx.event("notice_proposed", {"notice_id": nid, "intent": intent, "state_old": None, "state_new": "intent",
                                         "task_id": task_id, "fact_ids": ids}, case_id=case_id, main=True)
            return self._ok(tx, case_id, case["ver"], data={"notice_id": nid, "state": "intent"})

        return self._mutate(idem_key, payload, by, body)

    def claim_notice(self, notice_id, *, by, idem_key, expect_row_ver):
        """intent → drafting (CAS row_ver), до вызова NoticePort.propose; второй черновик невозможен (I42)."""
        _need_by(by)
        payload = {"op": "claim_notice", "notice_id": notice_id, "by": _by_key(by), "expect_row_ver": expect_row_ver}

        def body(tx):
            n = self._need_notice(tx, notice_id)
            case = self._case(tx, n["case_id"])
            self._check_row_ver(n, expect_row_ver, n["case_id"], case["ver"] if case else None)
            if case is None or case["state"] != "open":
                _stop_rej("case_%s" % (case["state"] if case else "not_found"))
            if n["state"] != "intent":
                _stop_rej("bad_transition", "claim_notice из %s (I15)" % n["state"])
            old = n["state"]
            self._notice_set(tx, n, state="drafting", claimed_by=self.role, claim_boot=self.boot_id, claim_at=tx.now)
            self._notice_event(tx, "notice_state", n, old, why="claim_notice", main=True, claimed_by=self.role,
                               boot=self.boot_id)
            return self._ok(tx, n["case_id"], case["ver"], data={"notice_id": notice_id, "state": "drafting",
                                                                 "case_ver": n["case_ver"], "intent": n["intent"],
                                                                 "facts": _jl(n["facts"], [])})

        return self._mutate(idem_key, payload, by, body)

    def mark_notice(self, notice_id, *, state, by, idem_key, expect_row_ver, draft_id=None, why=""):
        """drafted (draft_id от WA) | draft_unknown | dropped — по таблице §4.3."""
        if state not in ("drafted", "draft_unknown", "dropped"):
            raise ValueError("state ∈ {drafted, draft_unknown, dropped}: %r" % (state,))
        if state == "drafted" and not _int_id(draft_id):
            raise ValueError("drafted — с целым draft_id")
        _need_by(by)
        payload = {"op": "mark_notice", "notice_id": notice_id, "state": state, "by": _by_key(by),
                   "expect_row_ver": expect_row_ver, "draft_id": draft_id, "why": why}
        allowed = {"drafted": ("drafting", "draft_unknown"), "draft_unknown": ("drafting",),
                   "dropped": ("drafted", "draft_unknown")}

        def body(tx):
            n = self._need_notice(tx, notice_id)
            case = self._case(tx, n["case_id"])
            self._check_row_ver(n, expect_row_ver, n["case_id"], case["ver"] if case else None)
            if n["state"] not in allowed[state]:
                _stop_rej("bad_transition", "%s → %s" % (n["state"], state))
            old = n["state"]
            cols = {"state": state}
            if state == "drafted":
                cols["draft_id"] = draft_id
            self._notice_set(tx, n, **cols)
            self._notice_event(tx, "notice_state", n, old, why=_s(why) or state, main=True, draft_id=draft_id)
            return self._ok(tx, n["case_id"], case["ver"] if case else None,
                            data={"notice_id": notice_id, "state": state, "draft_id": n.get("draft_id")})

        return self._mutate(idem_key, payload, by, body)

    def record_notice_sent(self, notice_id, *, draft_id, wamid, at, source, by, idem_key):
        """К4 круг 2 (C10): доверенная привязка отправки. Ядро WA (роль wa) после НАСТОЯЩЕЙ отправки черновика
        уведомления сообщает wamid, выданный дверью отправки за этим draft_id; привязка хранится ДО любого статуса
        доставки, состояние уведомления остаётся drafted (sent ≠ delivered). record_delivery принимает только этот
        wamid: статус провайдера сам себя не удостоверяет. Повтор той же привязки — без изменений; другой wamid или
        другой черновик — отказ."""
        if not _s(wamid):
            raise ValueError("wamid — непустой")
        if not _int_id(draft_id):
            raise ValueError("draft_id — целый id черновика WA")
        _need_by(by)
        _need_source(source)
        payload = {"op": "record_notice_sent", "notice_id": notice_id, "draft_id": draft_id, "wamid": _s(wamid),
                   "at": at, "source": _src_key(source), "by": _by_key(by)}

        def body(tx):
            if self.role != "wa":
                _stop_rej("bad_transition", "привязку отправки пишет только ядро WA (роль wa), не %s" % self.role)
            n = self._need_notice(tx, notice_id)
            case = self._case(tx, n["case_id"])
            if n["state"] != "drafted":
                _stop_rej("bad_transition", "привязка отправки из %s" % n["state"])
            if n["draft_id"] != draft_id:
                _stop_rej("evidence_foreign", "черновик %s — не черновик уведомления (%s)" % (draft_id, n["draft_id"]))
            if n["wamid"]:
                if n["wamid"] != _s(wamid):
                    _stop_rej("evidence_foreign", "у черновика уведомления уже записан другой wamid")
                return self._ok(tx, n["case_id"], case["ver"] if case else None,
                                data={"notice_id": notice_id, "state": n["state"], "draft_id": draft_id,
                                      "sent": True, "unchanged": True})
            self._notice_set(tx, n, wamid=_s(wamid))
            self._notice_event(tx, "notice_sent", n, n["state"], why="sent", main=True, draft_id=draft_id,
                               wamid=_s(wamid), at=_num(at), source=_s(source["name"]))
            return self._ok(tx, n["case_id"], case["ver"] if case else None,
                            data={"notice_id": notice_id, "state": n["state"], "draft_id": draft_id, "sent": True})

        return self._mutate(idem_key, payload, by, body)

    def record_delivery(self, notice_id, *, wamid, status, at, source, by, idem_key):
        """drafted → delivered по delivered/read ровно wamid черновика; при notice.case_ver == case.ver — ступень 6
        done-задаче (done → done) и закрыватель stage в той же транзакции (I12, §4.3, §4.5). wamid черновика — только
        из привязки отправки `record_notice_sent`, записанной ДО доставки (К4 круг 2, C10); привязки нет — отказ."""
        if not _s(wamid):
            raise ValueError("wamid — непустой")
        _need_by(by)
        _need_source(source)
        payload = {"op": "record_delivery", "notice_id": notice_id, "wamid": _s(wamid), "status": status, "at": at,
                   "source": _src_key(source), "by": _by_key(by)}

        def body(tx):
            n = self._need_notice(tx, notice_id)
            case = self._need_case(tx, n["case_id"])
            if status not in ("delivered", "read"):
                _stop_rej("not_delivered", "статус %r — не доставлено" % (status,))
            if n["state"] != "drafted":
                _stop_rej("bad_transition", "record_delivery из %s" % n["state"])
            if not n["wamid"]:
                _stop_rej("not_delivered", "привязки отправки нет: wamid черновика не записан ядром WA до доставки "
                                           "(record_notice_sent) — статус сам себя не удостоверяет")
            if n["wamid"] != _s(wamid):
                _stop_rej("not_delivered", "wamid ≠ записанному за черновиком")
            old = n["state"]
            self._notice_set(tx, n, state="delivered", delivered_at=float(_num(at) or tx.now))
            self._notice_event(tx, "notice_delivered", n, old, why=status, main=True, draft_id=n["draft_id"],
                               wamid=_s(wamid))
            stage, reason = None, ""
            if n["case_ver"] != case["ver"]:
                reason = "stale_version"
            elif n["task_id"]:
                task = tx.one("SELECT * FROM rc_task WHERE task_id=?", (n["task_id"],))
                if task is not None and task["state"] == "done" and task["top_stage"] == 5:
                    ev = {"kind": "wa_delivery", "ref": _s(wamid), "notice_id": notice_id, "wamid": _s(wamid),
                          "status": status, "at": _num(at), "expected_wamid": _s(n["wamid"]),
                          "notice_case_ver": n["case_ver"], "case_ver": case["ver"]}
                    ok, code = self._stage_check(tx, case, task, "client_notified", ev, by)
                    if ok:
                        facts = _jl(n["facts"], []) or []
                        pdf = any(isinstance(f, Mapping) and f.get("kind") == "pdf" for f in facts)
                        self._stage_write(tx, case, task, "client_notified", ev, [code] if code else [],
                                          "stage:%s:client_notified" % task["task_id"], intent=n["intent"], pdf=pdf)
                        stage = "client_notified"
                    else:
                        reason = code
                else:
                    reason = "order"
            return self._ok(tx, case["case_id"], case["ver"], data={"notice_id": notice_id, "state": "delivered",
                                                                    "stage": stage}, reason=reason)

        return self._mutate(idem_key, payload, by, body)

    def on_client_inbound(self, *, contact, ref, at, by, idem_key):
        """Входящее клиента: событие во все открытые дела активного контакта; намерения intent/drafted → superseded."""
        if not isinstance(contact, Mapping) or not _s(contact.get("value")):
            raise ValueError("contact — {channel, value}")
        _need_by(by)
        payload = {"op": "on_client_inbound", "contact": {"channel": _s(contact.get("channel")) or "wa",
                                                          "value": _s(contact.get("value"))},
                   "ref": ref, "at": at, "by": _by_key(by)}

        def body(tx):
            cases = self._contact_cases(tx, contact)
            superseded = []
            for cid in cases:
                superseded += self._supersede_notices(tx, cid, "client_inbound:%s" % _s(ref))
                tx.event("client_inbound", {"contact_masked": _mask(contact.get("value")), "ref": _s(ref),
                                            "cases": [cid], "superseded_notices": superseded}, case_id=cid)
            data = {"cases": cases, "superseded_notices": superseded}
            tx.event("client_inbound", {"contact_masked": _mask(contact.get("value")), "ref": _s(ref), "cases": cases,
                                        "superseded_notices": superseded, "at": at}, main=True, ref=_s(ref))
            return self._ok(tx, data=data)

        return self._mutate(idem_key, payload, by, body)

    def on_human_intervention(self, *, contact, kind, channel, ref, at, wa_pause_no, by, idem_key):
        """Вмешательство человека: событие во все открытые дела контакта; внимание — канал wa ⇔ задан wa_pause_no;
        канал ≠ wa — при любом виде, пока NON_WA_MEDIA_EXEMPT = UNKNOWN (I24)."""
        if not isinstance(contact, Mapping) or not _s(contact.get("value")):
            raise ValueError("contact — {channel, value}")
        if not _s(channel):
            raise ValueError("channel — непустой")
        if wa_pause_no is not None and not _int_id(wa_pause_no):
            raise ValueError("wa_pause_no — целое | None")
        _need_by(by)
        payload = {"op": "on_human_intervention", "contact": {"channel": _s(contact.get("channel")) or "wa",
                                                              "value": _s(contact.get("value"))},
                   "kind": kind, "channel": channel, "ref": ref, "at": at, "wa_pause_no": wa_pause_no,
                   "by": _by_key(by)}

        def body(tx):
            if channel == "wa":
                attention = wa_pause_no is not None
            else:
                exempt = self._p("NON_WA_MEDIA_EXEMPT")
                attention = True if R.is_unknown(exempt) else (_s(kind) not in set(exempt or ()))
            cases = self._contact_cases(tx, contact)
            involved = []
            for cid in cases:
                case = self._case(tx, cid)
                if attention:
                    self._attention_on(tx, case, channel, "human_intervention:%s" % _s(kind),
                                       number=_mask(contact.get("value")),
                                       wa_pause_no=wa_pause_no if channel == "wa" else None)
                    self._supersede_notices(tx, cid, "human_intervention:%s" % _s(ref))
                exps = [e["exp_id"] for e in tx.q("SELECT exp_id FROM rc_expect WHERE case_id=? AND kind='staff_question' "
                                                  "AND state NOT IN ('answered','superseded','cancelled')", (cid,))]
                involved += exps
                tx.event("human_intervention", {"kind": kind, "channel": channel, "ref": _s(ref), "cases": [cid],
                                                "pause_no": case["pause_no"], "wa_pause_no": case.get("wa_pause_no"),
                                                "attention": attention, "human_involved_exp": exps}, case_id=cid)
            data = {"cases": cases, "attention": attention}
            tx.event("human_intervention", {"kind": kind, "channel": channel, "ref": _s(ref), "cases": cases,
                                            "pause_no": None, "wa_pause_no": wa_pause_no, "attention": attention,
                                            "human_involved_exp": involved}, main=True, ref=_s(ref))
            return self._ok(tx, data=data)

        return self._mutate(idem_key, payload, by, body)

    def clear_attention(self, case_id, *, by, idem_key, wa_pause_no=None):
        """Снимает только одобряющий по id (PAUSE_RELEASER=UNKNOWN); внимание от паузы WA — только её номером."""
        _need_by(by)
        payload = {"op": "clear_attention", "case_id": case_id, "by": _by_key(by), "wa_pause_no": wa_pause_no}

        def body(tx):
            case = self._need_case(tx, case_id)
            if by.get("kind") != "human":
                _stop_rej("param_unknown", "PAUSE_RELEASER: снимает только человек-одобряющий")
            if not self._approver(by):
                _stop_rej("approver_unknown", "снимает только одобряющий по id")
            if not case["attention"]:
                _stop_rej("bad_transition", "внимания нет")
            if case.get("wa_pause_no") is not None and wa_pause_no != case["wa_pause_no"]:
                _stop_rej("pause_mismatch", "номер паузы WA не совпал")
            pn, wpn = case["pause_no"], case.get("wa_pause_no")
            self._case_set(tx, case, attention=0, att_channel=None, att_number=None, wa_pause_no=None)
            tx.event("attention_cleared", {"pause_no": pn, "wa_pause_no": wpn, "by": _by_key(by)}, case_id=case_id,
                     main=True)
            return self._ok(tx, case_id, case["ver"], data={"pause_no": pn, "attention": 0})

        return self._mutate(idem_key, payload, by, body)

    def close_case(self, case_id, *, by, idem_key, expect_ver):
        """open → closed только при close_blockers == [], посчитанных В ЭТОЙ транзакции (I13, I31)."""
        _need_by(by)
        payload = {"op": "close_case", "case_id": case_id, "by": _by_key(by), "expect_ver": expect_ver}

        def body(tx):
            case = self._need_case(tx, case_id)
            self._check_ver(case, expect_ver)
            bl = self._blockers_tx(tx, case)
            if bl:
                _stop_rej("blockers", "%d блокер(ов)" % len(bl), data={"blockers": bl}, case_id=case_id,
                          ver=case["ver"])
            return self._finish_case(tx, case, "closed", "close_case")

        return self._mutate(idem_key, payload, by, body)

    def blockers(self, case_id):
        """Справочно (решений не принимает): блокеры закрытия по rules.close_blockers."""
        def body(tx):
            case = self._case(tx, case_id)
            if case is None:
                return [{"what": "case", "id": case_id, "why": "case_not_found"}]
            return self._blockers_tx(tx, case)

        return self._read(body)

    def allowed_actions(self, case_id):
        """Разрешённые намерения (ничего не исполняет)."""
        def body(tx):
            case = self._case(tx, case_id)
            if case is None:
                return []
            return self._allowed_tx(tx, case)

        return self._read(body)

    def events(self, case_id, *, after_seq=0, limit=500):
        def body(tx):
            out = []
            for e in tx.q("SELECT * FROM rc_event WHERE case_id=? AND seq>? ORDER BY seq LIMIT ?",
                          (case_id, int(after_seq or 0), int(limit or 500))):
                d = dict(e)
                d["payload"] = _jl(e["payload"], {})
                out.append(d)
            return out

        return self._read(body)


    # =================================================================================================================
    # Чтения: состав дела (§8.4), факт для агента (§8.3), документ на период (§5.5, I46)
    # =================================================================================================================

    @staticmethod
    def _row_src(r):
        """src из колонок строки (rc_rental, rc_contact, rc_document, rc_obligation, rc_fact) — без подстановки (I22)."""
        return {"source": r["source"], "ref": r["ref"], "method": r["method"], "read_at": r["read_at"],
                "observed_at": r["observed_at"], "case_ver": r["case_ver"]}

    @staticmethod
    def _own_src(ref, observed_at, case_ver, now):
        """src собственных строк хранилища по таблице вывода §8.4."""
        return {"source": SELF_SOURCE, "ref": str(ref), "method": "event", "read_at": now, "observed_at": observed_at,
                "case_ver": case_ver}

    def _doc_label(self, tx, d):
        rr = self._case_rental_by_id(tx, d["case_id"], d["rental_id"]) if d.get("rental_id") is not None else None
        bike = (rr or {}).get("bike_name") or (rr or {}).get("plate") or "байк ?"
        signed = _dm(d.get("signed_at")) if d.get("signed_at") else "без даты подписи"
        return "Договор от %s (%s, строка реестра %s)" % (signed, bike, d.get("reg_row") if d.get("reg_row") is not None
                                                           else "?")

    def _documents_for_tx(self, tx, case, period, kinds):
        cid = case["case_id"]
        cur = self._rental(tx, cid) or {}
        _pdf_of, contract_of = self._doc_links(tx, cid)
        pdf_of = _pdf_of
        all_docs = dict((d["id"], d) for d in tx.q("SELECT * FROM rc_document WHERE case_id=? ORDER BY id", (cid,)))
        valid_period = False
        if isinstance(period, (list, tuple)) and len(period) == 2:
            p0, p1 = _iso_strict(period[0]), _iso_strict(period[1])
            valid_period = p0 is not None and p1 is not None and p0 <= p1
        items = []
        for d in all_docs.values():
            if d["kind"] not in tuple(kinds or ()):
                continue
            rr = self._case_rental_by_id(tx, cid, d["rental_id"]) if d["rental_id"] is not None else None
            if d["status"] == "verified" and rr is not None:
                binding = "bound"
            elif d["status"] == "revoked":
                binding = "revoked"
            else:
                binding = "unknown"
            cov, why = None, "period_not_given"
            if valid_period:
                base = d
                if d["kind"] == "contract_pdf":
                    cdoc = all_docs.get(contract_of.get(d["id"]))
                    if cdoc is None:
                        for x in all_docs.values():
                            if x["kind"] == "contract_signed" and pdf_of.get(x["id"]) == d["ext_id"]:
                                cdoc = x
                    ok = cdoc is not None and cdoc["status"] == "verified"
                    base = {"status": d["status"], "kind": "contract_pdf",
                            "cover_from": cdoc["cover_from"] if ok else None,
                            "cover_to": cdoc["cover_to"] if ok else None,
                            "cover_basis": cdoc["cover_basis"] if ok else None}
                res = R.document_coverage(base, (period[0], period[1]))
                cov, why = res.get("code"), res.get("why") or ""
            items.append({"document_id": d["id"], "kind": d["kind"], "ext_id": d["ext_id"], "status": d["status"],
                          "reg_row": d["reg_row"], "signed_at": d["signed_at"], "sha256": d["sha256"],
                          "rental_id": d["rental_id"], "rental_current": d["rental_id"] == cur.get("id"),
                          "bound_by": d["bound_by"], "binding": binding, "coverage": cov,
                          "cover_from": d["cover_from"], "cover_to": d["cover_to"], "cover_basis": d["cover_basis"],
                          "cover_ref": d["cover_ref"], "cover_by": d["cover_by"], "why": why,
                          "src": self._row_src(d)})
        refs = []
        for f in tx.q("SELECT * FROM rc_fact WHERE case_id=? AND kind='contract_ref' AND state='valid' ORDER BY id",
                      (cid,)):
            v = _jl(f["value"], {}) or {}
            refs.append({"fact_id": f["id"], "doc_id": v.get("doc_id"), "ref_booking": v.get("ref_booking"),
                         "ref_anchor": v.get("ref_anchor"), "period": v.get("period"), "signed_at": v.get("signed_at"),
                         "binding": "other_rental", "src": self._row_src(f)})
        out = {"code": "unknown", "pick": None, "documents": items, "refs": refs, "missing": [], "ask": "",
               "reason": "", "case_id": cid, "ver": case["ver"]}
        if not valid_period:
            out.update(reason="period_not_given", missing=["period"], ask="На какой период нужен договор?")
            return out
        pf, pt = _dm(period[0]), _dm(period[1])
        signed = [i for i in items if i["kind"] == "contract_signed" and i["binding"] == "bound"]
        covers = [i for i in signed if i["coverage"] == "covers"]
        unknown_cov = [i for i in signed if i["coverage"] == "unknown"]
        if len(covers) == 1 and not unknown_cov:
            out.update(code="found", pick=covers[0]["document_id"])
            return out
        out["missing"] = ["document_period"]
        if not signed:
            out.update(reason="doc_unknown",
                       ask="Подписанного договора этой аренды в деле нет. Нужен договор на %s–%s — найти подписанный "
                           "договор этой аренды или оформить новый?" % (pf, pt))
        elif len(covers) >= 2 or (covers and unknown_cov):
            out.update(reason="doc_ambiguous",
                       ask="На период %s–%s подходит больше одного договора или покрытие части не подтверждено (%s) — "
                           "какой договор нужен?" % (pf, pt, "; ".join(self._doc_label(tx, all_docs[i["document_id"]])
                                                                    for i in covers + unknown_cov)))
        elif unknown_cov:
            out.update(reason="doc_period_unknown",
                       ask="%s относится к этой аренде, но какой период он покрывает, не подтверждено. Нужен договор на "
                           "%s–%s: какие даты указаны в договоре или допсоглашении (и где) — или оформить новый?"
                           % ("; ".join(self._doc_label(tx, all_docs[i["document_id"]]) for i in unknown_cov), pf, pt))
        else:
            parts = []
            for i in signed:
                d = all_docs[i["document_id"]]
                rr = self._case_rental_by_id(tx, cid, d["rental_id"]) or {}
                parts.append("Подписан договор на %s–%s (подтверждено: %s; %s, строка реестра %s)" % (
                    _dm(d["cover_from"]), _dm(d["cover_to"]), d["cover_ref"], rr.get("bike_name") or rr.get("plate"),
                    d["reg_row"] if d["reg_row"] is not None else "?"))
            out.update(reason="doc_period_not_covered",
                       ask="%s. Нужен договор на %s–%s — оформить новый на продление или прежний его покрывает?"
                           % ("; ".join(parts), pf, pt))
        return out

    def documents_for(self, case_id, *, period=None, kinds=("contract_signed", "contract_pdf")):
        """Запрос документа НА ПЕРИОД (I46): принадлежность (binding) и покрытие (coverage) — раздельно; без периода —
        unknown(period_not_given), срок привязки не подставляется."""
        def body(tx):
            case = self._case(tx, case_id)
            if case is None:
                return {"code": "unknown", "pick": None, "documents": [], "refs": [], "missing": ["document_period"],
                        "ask": "Дело не найдено — по какой аренде нужен договор?", "reason": "case_not_found"}
            return self._documents_for_tx(tx, case, period, kinds)

        return self._read(body)

    def _view_parts(self, tx, case, since=None, period=None):
        now = tx.now
        cid, ver = case["case_id"], case["ver"]
        missing = []
        case_el = {"case_id": cid, "ver": ver, "state": case["state"], "link_state": case["link_state"],
                   "link_exp_id": case["link_exp_id"], "attention": bool(case["attention"]),
                   "att_channel": case["att_channel"], "pause_no": case["pause_no"], "wa_pause_no": case["wa_pause_no"],
                   "origin": case["origin"], "created_at": case["created_at"], "created_by": case["created_by"],
                   "src": self._own_src(cid, case["updated_at"], ver, now)}
        r = self._rental(tx, cid)
        contacts = [{"contact_id": c["id"], "channel": c["channel"], "value_masked": _mask(c["value"]),
                     "status": c["status"], "source_kind": c["source_kind"], "src": self._row_src(c)}
                    for c in self._contacts(tx, cid)]
        client = {"name_seen": r["name_seen"] if r else None, "contacts": contacts,
                  "src": self._row_src(r) if r else self._own_src(cid, case["updated_at"], ver, now)}
        why_of, seq_of = {}, {}
        for e in tx.q("SELECT seq, type, payload FROM rc_event WHERE case_id=? AND type IN ('rental_bound',"
                      "'rental_rebound') ORDER BY seq", (cid,)):
            p = _jl(e["payload"], {}) or {}
            if p.get("prev_rental_id") is not None:
                why_of[p["prev_rental_id"]] = "%s:%s" % (e["type"], p.get("why") or "")
                seq_of[p["prev_rental_id"]] = e["seq"]
        history = []
        for h in tx.q("SELECT * FROM rc_rental WHERE case_id=? AND current=0 ORDER BY id", (cid,)):
            history.append({"rental_id": h["id"], "booking_id": h["booking_id"], "plate": h["plate"],
                            "bike_name": h["bike_name"], "start_day": h["start_day"], "end_day": h["end_day"],
                            "days": h["days"], "status_seen": h["status_seen"], "crm_row_seen": h["crm_row_seen"],
                            "bound_by": h["bound_by"], "why": why_of.get(h["id"]), "seq": seq_of.get(h["id"]),
                            "src": self._row_src(h)})
        current = None
        if r:
            current = {"rental_id": r["id"], "booking_id": r["booking_id"],
                       "anchor": self._anchor(tx, cid) or self._anchor_of_rental(r), "plate": r["plate"],
                       "start_at": r["start_at"], "end_at": r["end_at"], "start_day": r["start_day"],
                       "end_day": r["end_day"], "days": r["days"], "status_seen": r["status_seen"],
                       "crm_row_seen": r["crm_row_seen"], "bound_by": r["bound_by"], "src": self._row_src(r)}
        else:
            missing.append("rental")
        rental = {"current": current, "history": history, "link_state": case["link_state"]}
        if case["link_state"] != "ok":
            co = self._confirm_open(tx, cid)
            rental["reason"] = ((_jl(co["subject"], {}) or {}).get("question") if co else "") or \
                "Привязка аренды не подтверждена (%s)" % case["link_state"]
        bike_hist = []
        for e in tx.q("SELECT * FROM rc_event WHERE case_id=? AND type='bike_changed' ORDER BY seq", (cid,)):
            p = _jl(e["payload"], {}) or {}
            bike_hist.append({"plate_old": p.get("plate_old"), "plate_new": p.get("plate_new"), "at": e["at"],
                              "src": {"source": e["source"] or SELF_SOURCE, "ref": e["ref"] or e["idem_key"],
                                      "method": "event", "read_at": now, "observed_at": e["at"],
                                      "case_ver": e["ver_after"] or ver}})
        state = None
        bike_missing = []
        f = tx.one("SELECT * FROM rc_fact WHERE case_id=? AND kind='bike_state' AND state='valid' "
                   "ORDER BY observed_at DESC, id DESC LIMIT 1", (cid,))
        if f is not None:
            v = _jl(f["value"], {}) or {}
            flags = list(v.get("flags") or [])
            if r:
                item = {"bike": r["bike_name"], "status": v.get("status"), "location": v.get("location"),
                        "booking_id": v.get("booking_id_seen"), "client": v.get("client_seen"),
                        "updated": v.get("updated"), "date_due": v.get("date_due")}
                bsf = R.bike_state_fact(item, {"bike_name": r["bike_name"], "booking_id": r["booking_id"],
                                               "status_seen": r["status_seen"]})
                for fl in bsf.get("flags") or []:
                    if fl not in flags:
                        flags.append(fl)
            state = {"fact_id": f["id"], "status": v.get("status"), "location": v.get("location"),
                     "updated": v.get("updated"), "date_due": v.get("date_due"),
                     "booking_id_seen": v.get("booking_id_seen"), "client_seen": v.get("client_seen"), "flags": flags,
                     "src": self._row_src(f)}
        else:
            bike_missing.append("bike_state")
        bike = None
        if r:
            bike = {"plate": r["plate"], "bike_name": r["bike_name"], "model_req": r["model_req"],
                    "history": bike_hist, "state": state, "missing": bike_missing, "src": self._row_src(r)}
        doc_view = self._documents_for_tx(tx, case, period, DOC_KINDS)
        documents = {"items": doc_view["documents"], "refs": doc_view["refs"],
                     "missing": [] if doc_view["documents"] else ["documents"]}
        cash = tx.q("SELECT * FROM rc_fact WHERE case_id=? AND kind='cash' AND state='valid' ORDER BY id", (cid,))
        opened_why = {}
        for e in tx.q("SELECT payload FROM rc_event WHERE case_id=? AND type='obligation_opened' ORDER BY seq", (cid,)):
            p = _jl(e["payload"], {}) or {}
            opened_why.setdefault(p.get("obligation_id"), p.get("why"))
        money, others = [], []
        for o in tx.q("SELECT * FROM rc_obligation WHERE case_id=? ORDER BY id", (cid,)):
            if o["kind"] != "money":
                others.append({"obligation_id": o["id"], "id": o["id"], "kind": o["kind"], "role": o["role"],
                               "direction": o["direction"], "state": o["state"], "closed_by": o["closed_by"],
                               "close_ref": o["close_ref"], "required": bool(o["required"]),
                               "why": opened_why.get(o["id"]), "src": self._row_src(o)})
                continue
            crole = _pairs_get(CASH_ROLE_OF_OBLIGATION, o["role"])
            cash_items = []
            for c in cash:
                v = _jl(c["value"], {}) or {}
                if crole is not None and v.get("role") == crole:
                    cash_items.append({"fact_id": c["id"], "row": v.get("row"), "msg_id": v.get("msg_id"),
                                       "amount": v.get("amount"), "currency": v.get("currency"), "role": v.get("role"),
                                       "bound_by": v.get("bound_by"), "src": self._row_src(c)})
            close_fact = close_second = None
            if o["closed_by"] == "write":
                cf = tx.one("SELECT * FROM rc_fact WHERE id=?", (o["close_fact_id"],)) if o["close_fact_id"] else None
                if cf is not None:
                    v = _jl(cf["value"], {}) or {}
                    close_fact = {"fact_id": cf["id"], "row": v.get("row"), "msg_id": v.get("msg_id"),
                                  "amount": v.get("amount"), "currency": v.get("currency"), "role": v.get("role"),
                                  "bound_by": v.get("bound_by"), "state": cf["state"], "src": self._row_src(cf)}
                cd = (tx.one("SELECT * FROM rc_document WHERE id=?", (o["close_second_id"],))
                      if o["close_second_id"] else None)
                if cd is not None:
                    close_second = {"document_id": cd["id"], "kind": cd["kind"], "ext_id": cd["ext_id"],   # §8.4 (C36)
                                    "status": cd["status"], "src": self._row_src(cd)}
            money.append({"obligation_id": o["id"], "id": o["id"], "role": o["role"], "direction": o["direction"],
                          "amount": o["amount"], "currency": o["currency"], "outcome": o["outcome"],
                          "state": o["state"], "closed_by": o["closed_by"], "close_ref": o["close_ref"],
                          "required": bool(o["required"]), "why": opened_why.get(o["id"]), "cash": cash_items,
                          "close_fact": close_fact, "close_second": close_second, "src": self._row_src(o)})
        valid, other = [], []
        for fct in tx.q("SELECT * FROM rc_fact WHERE case_id=? ORDER BY id", (cid,)):
            if since is not None and fct["observed_at"] < float(since):
                continue
            el = {"fact_id": fct["id"], "kind": fct["kind"], "value": _jl(fct["value"], {}), "scope": fct["scope"],
                  "fkey": _jl(fct["fkey"], []), "src": self._row_src(fct)}
            if fct["state"] == "valid":
                if case["link_state"] != "ok" and fct["scope"] == "rental":
                    continue
                valid.append(el)
            else:
                el.update(state=fct["state"], reason=fct["reason"])
                other.append(el)
        facts = {"valid": valid, "other": other}
        tasks = []
        for t in tx.q("SELECT * FROM rc_task WHERE case_id=? ORDER BY created_at, task_id", (cid,)):
            stages = []
            for s in tx.q("SELECT * FROM rc_stage WHERE task_id=? ORDER BY id", (t["task_id"],)):
                stages.append({"task_id": t["task_id"], "stage": s["stage"], "evidence_kind": s["evidence_kind"],
                               "evidence_ref": s["evidence_ref"], "flags": _jl(s["flags"], []), "at": s["at"],
                               "src": self._own_src("%s:%s" % (t["task_id"], s["stage"]), s["at"], s["case_ver"],
                                                    now)})
            tasks.append({"task_id": t["task_id"], "kind": t["kind"], "state": t["state"],
                          "top_stage": t["top_stage"], "rental_id": t["rental_id"], "case_ver": t["case_ver"],
                          "created_at": t["created_at"], "reason": t["reason"], "stages": stages,
                          "src": self._own_src(t["task_id"], t["updated_at"], t["case_ver"], now)})
        expectations = []
        for e in tx.q("SELECT * FROM rc_expect WHERE case_id=? ORDER BY created_at, exp_id", (cid,)):
            ws = None
            if e["waiting_since"] is not None and e["state"] not in EXPECT_TERMINAL:
                ws = now - e["waiting_since"]
                ws = ws if ws > 0 else 0.0
            expectations.append({"exp_id": e["exp_id"], "kind": e["kind"], "action": e["action"], "place": e["place"],
                                 "state": e["state"], "next_check": e["next_check"], "task_id": e["task_id"],
                                 "waiting_for_s": ws, "due_basis": e["due_basis"],
                                 "business_due_at": e["business_due_at"], "ext_qid": e["ext_qid"],
                                 "attempt_no": e["attempt_no"], "subject": _jl(e["subject"], {}),
                                 "src": self._own_src(e["exp_id"], e["updated_at"], e["case_ver"] or ver, now)})
        answers = []
        for a in tx.q("SELECT * FROM rc_answer WHERE case_id=? ORDER BY id", (cid,)):
            if since is not None and a["at"] < float(since):
                continue
            exp = self._exp(tx, a["exp_id"])
            post = (tx.one("SELECT * FROM rc_post WHERE chat=? AND msg_id=?", (a["chat"], a["reply_to"]))
                    if a["reply_to"] else None)
            source = ("staff_ask:%s" % post["place"]) if post is not None else "approval:%s" % (exp or {}).get("action")
            answers.append({"answer_id": a["id"], "exp_id": a["exp_id"], "exp_kind": (exp or {}).get("kind"),
                            "task_id": (exp or {}).get("task_id"), "author_id": a["author_id"], "at": a["at"],
                            "verdict": a["verdict"], "decision": a["decision"], "execute": bool(a["execute"]),
                            "promoted_by": a["promoted_by"], "text": a["text"],
                            "place": post["place"] if post is not None else None,
                            "question": (_jl((exp or {}).get("subject"), {}) or {}).get("q_ru"),
                            "src": {"source": source, "ref": "%s:%s" % (a["chat"], a["msg_id"]), "method": "reply",
                                    "read_at": a["received_at"], "observed_at": a["at"],
                                    "case_ver": a["case_ver_at"] or (exp or {}).get("case_ver") or ver}})
        orphans = []
        seen = set()
        for o in tx.q("SELECT u.* FROM rc_reply_unlinked u JOIN rc_answer a ON a.id=u.answer_id WHERE a.case_id=? "
                      "ORDER BY u.id", (cid,)):
            seen.add(o["id"])
            orphans.append(o)
        if tx.one("SELECT 1 AS x FROM rc_expect WHERE case_id=? AND state IN ('flight_unknown','escalation_unknown')",
                  (cid,)) is not None:
            for o in tx.q("SELECT * FROM rc_reply_unlinked WHERE state='orphan' ORDER BY id"):
                if o["id"] not in seen:
                    orphans.append(o)
        orphans = [{"orphan_id": o["id"], "chat": o["chat"], "msg_id": o["msg_id"], "reply_to": o["reply_to"],
                    "state": o["state"], "author_id": o["author_id"], "at": o["at"], "answer_id": o["answer_id"],
                    "src": self._own_src(o["id"], o["received_at"], ver, now)} for o in orphans]
        notices = []
        for n in tx.q("SELECT * FROM rc_notice WHERE case_id=? ORDER BY created_at, notice_id", (cid,)):
            notices.append({"notice_id": n["notice_id"], "task_id": n["task_id"], "intent": n["intent"],
                            "state": n["state"], "draft_id": n["draft_id"], "wamid": n["wamid"],
                            "case_ver": n["case_ver"], "delivered_at": n["delivered_at"],
                            "src": self._own_src(n["notice_id"], n["updated_at"], n["case_ver"], now)})
        return {"case": case_el, "client": client, "rental": rental, "bike": bike, "documents": documents,
                "money": money, "obligations_other": others, "facts": facts, "tasks": tasks,
                "expectations": expectations, "answers": answers, "orphans": orphans, "notices": notices,
                "blockers": self._blockers_tx(tx, case), "allowed_actions": self._allowed_tx(tx, case),
                "read_at": now, "missing": missing, "link_state": case["link_state"], "_doc_view": doc_view}

    def case_view(self, case_id, *, since=None):
        """Состав дела по частям (§8.4, Д2): у каждого элемента полный src (I22)."""
        def body(tx):
            case = self._case(tx, case_id)
            if case is None:
                out = dict((k, None) for k in ("case", "client", "rental", "bike", "documents", "money",
                                               "obligations_other", "facts", "tasks", "expectations", "answers",
                                               "orphans", "notices", "blockers", "allowed_actions"))
                out.update(read_at=tx.now, missing=["case"], reason="case_not_found")
                return out
            parts = self._view_parts(tx, case, since)
            parts.pop("_doc_view", None)
            return parts

        return self._read(body)

    def facts_for_agent(self, case_id, *, since=None, period=None):
        """Результат инструмента агента `case` (§8.3): version = "case_ver:<n>" (версия ДЕЛА, не источника, F2 К3);
        при link_state ≠ ok аренда/байк/деньги/документы не выдаются (I37); деньги — не подтверждение оплаты (I45)."""
        def body(tx):
            now = tx.now
            case = self._case(tx, case_id)
            if case is None:
                return {"tool": "case", "outcome": "unknown", "source": AGENT_SOURCE, "ref": case_id, "at": now,
                        "version": "", "window": "", "reason": "case_not_found", "facts": []}
            parts = self._view_parts(tx, case, since, period=period)
            link_ok = case["link_state"] == "ok"
            facts, reasons = [], []
            c = parts["case"]
            facts.append({"kind": "case", "case_id": c["case_id"], "case_ver": c["ver"], "attention": c["attention"],
                          "state": c["state"], "link_state": c["link_state"], "src": c["src"]})
            cl = parts["client"]
            facts.append({"kind": "case_client", "name_seen": cl["name_seen"], "contacts": cl["contacts"],
                          "src": cl["src"]})
            window = ""
            if link_ok:
                cur = parts["rental"]["current"]
                if cur is not None:
                    el = dict(cur)
                    el["kind"] = "case_rental"
                    el["history"] = parts["rental"]["history"]
                    facts.append(el)
                    window = "%s…%s" % (cur.get("start_day") or "?", cur.get("end_day") or "?")
                b = parts["bike"]
                if b is not None:
                    facts.append({"kind": "case_bike", "plate": b["plate"], "bike_name": b["bike_name"],
                                  "model_req": b["model_req"], "history": b["history"], "state": b["state"],
                                  "src": b["src"]})
                for m in parts["money"]:
                    el = dict(m)
                    el["kind"] = "case_money"
                    el["payment_confirmed"] = False
                    facts.append(el)
                if parts["money"]:
                    reasons.append(MONEY_NOT_PAYMENT)
                dv = parts["_doc_view"]
                for d in dv["documents"]:
                    el = dict(d)
                    el["doc_kind"] = el.pop("kind")
                    el["kind"] = "case_document"
                    if period is None:
                        el["coverage"] = None
                    facts.append(el)
                if period is not None and dv.get("code") != "found":
                    reasons.append(dv.get("ask") or "")
            else:
                reasons.append(parts["rental"].get("reason") or "Привязка аренды не подтверждена")
            for o in parts["obligations_other"]:
                el = dict(o)
                el["obl_kind"] = el.pop("kind")
                el["kind"] = "case_obligation"
                facts.append(el)
            refs_words = []
            for a in parts["answers"]:
                if a["verdict"] == "accepted" or a["promoted_by"]:
                    el = dict(a)
                    el["kind"] = "case_answer"
                    el["answer"] = a["text"]
                    el["task"] = None
                    if a.get("task_id"):
                        t = tx.one("SELECT kind FROM rc_task WHERE task_id=?", (a["task_id"],))
                        el["task"] = t["kind"] if t else None
                    if link_ok or a.get("place") not in ("topic", "delivery"):
                        facts.append(el)
                else:
                    refs_words.append("справка %s (%s)" % (a["verdict"], a["src"]["ref"]))
            for e in parts["expectations"]:
                if e["state"] in EXPECT_TERMINAL:
                    continue
                s = e.get("subject") or {}
                facts.append({"kind": "case_expect", "exp_id": e["exp_id"],
                              "what": s.get("q_ru") or s.get("question") or s.get("text") or e.get("action") or e["kind"],
                              "state": e["state"], "next_check": e["next_check"], "due_basis": e["due_basis"],
                              "waiting_for_s": e["waiting_for_s"], "src": e["src"]})
            for t in parts["tasks"]:
                for s in t["stages"]:
                    facts.append({"kind": "case_stage", "task": t["kind"], "task_id": t["task_id"], "stage": s["stage"],
                                  "at": s["at"], "src": s["src"]})
            if refs_words:
                reasons.append("; ".join(refs_words))
            stale = [f for f in parts["facts"]["other"]]
            if stale:
                reasons.append("устаревших/отозванных фактов: %d" % len(stale))
            return {"tool": "case", "outcome": "fact", "source": AGENT_SOURCE, "ref": case_id, "at": now,
                    "version": "case_ver:%d" % case["ver"], "window": window,
                    "reason": "; ".join(r for r in reasons if r), "facts": facts}

        return self._read(body)
