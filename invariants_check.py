#!/usr/bin/env python3
"""РЕЕСТР ДАННЫХ v1 — непрерывные инварианты живых данных TurboBaby. READ-ONLY.

Зачем: автоматически ловить нарушения бизнес-инвариантов в живых таблицах —
прежде чем их заметит Пым или клиент. Дополняет registry_check.py (мозг↔реальность),
но проверяет данные АРЕНДЫ, а не метаданные доков.

ГРАНИЦЫ:
- READ-ONLY ПОЛНОСТЬЮ: только чтение fleet/clients/queue через Bridge.
- Ничего не пишет в таблицы, CRM, Лист1, Зарплаты, деньги.
- Деградация (Bridge не отвечает) → note, НЕ ложное расхождение.

РАСТЯЖИМАЯ АРХИТЕКТУРА: @register("ИМЯ") → fn(world, run).
Добавить новый инвариант = одна функция.

ЗАПУСК:
  venv/bin/python3 invariants_check.py              # отчёт в stdout
  venv/bin/python3 invariants_check.py --push       # + пуш в тему 328 при нарушениях
  venv/bin/python3 invariants_check.py --json       # машинный вывод
  venv/bin/python3 invariants_check.py --self-test  # самотест (без сети)

ЖИВЫЕ ФОРМАТЫ (урок 08.07.2026): мок-данные в тестах используют РЕАЛЬНЫЙ формат ячеек:
  - oil_last_km/gear_last_km: число из parseNumber (0 = пусто/нечисловое)
  - date_end: "2026-07-14 14:00" (yyyy-MM-dd HH:mm из Apps Script formatDate, Bangkok TZ)
  - deposit_raw: строка из col S сырьём — "7000" | "passport" | "" | смешанное
  - bike name: "HONDA CLICK 125 5580" (точное название из Лист1 col C)
  - queue updated: ISO строка "2026-07-15T08:30:00+00:00"
"""
import os
import re
import sys
import json
import datetime
import subprocess
import urllib.request
import urllib.error
from datetime import timezone

REPO = os.path.dirname(os.path.abspath(__file__))

# Injectable root СТАТИЧЕСКИХ ФС-инвариантов (SCRATCHPAD_WRITERS + SCRATCH_UNTRACKED);
# None → REPO (переопределяется в тестах одним knob'ом на оба).
_SCRATCHPAD_ROOT = None
# Injectable поставщик git-отслеживаемых имён для SCRATCH_UNTRACKED: callable(root) → set|None.
# None → живой `git ls-files`. Мок нужен только самотесту (тесты в tests/ гоняют РЕАЛЬНЫЙ git).
_TRACKED_PROVIDER = None
# Паттерн прямой записи в мозг: .write_doc( или ._call("write_doc"
_BRAIN_WRITE_RE = re.compile(r'\.write_doc\s*\(|_call\s*\(\s*[\'"]write_doc[\'"]')

# HARD_MAX_KM — нереальный пробег замены масла (> 300к km для тайского проката невозможно):
# ловит случайные набросы типа «35200» прочитанное как «352000» или иные ошибки ввода.
HARD_MAX_KM = 300_000
# OVERDUE_DAYS — просрочка возврата более этого числа дней → флаг.
OVERDUE_DAYS = 2
# Активные статусы, для которых проверяем booking_id и депозит.
_ACTIVE_ST = {"В аренде", "Бронь"}
# Паттерн HONDA CLICK 125 (бизнес-правило: не сдаём).
_CLICK125_RE = re.compile(r"honda\s+click\s+125", re.IGNORECASE)
# Суффиксы from-метки долгих задач (dev/dec/curator → TASK_TIMEOUT_DEV).
_DEV_SUFFIXES = ("-dev", "-dec", "-curator")
# Наличие цифры в строке депозита.
_DIGIT_RE = re.compile(r"\d")
# 4-значный номер байка в имени («PCX160 4234» → '4234').
_PLATE_RE = re.compile(r"\b(\d{4})\b")

# OIL_VS_CURRENT_ODO: |oil_last_km − current_km (Bot Data)| ≤ N → подозрение «фото-одометр».
OIL_PHOTO_DELTA = 100    # km
# Маркер свежести: Bot Data updated_at < N секунд → ТО только что занесено, не флагуем.
OIL_FRESH_SECS = 7200    # s (2 часа)
# BOT_DATA_VS_SHEET: расхождение oil/gear Лист1 I/J vs Bot Data last_service_km > N → флаг.
BOT_DATA_OIL_DELTA = 200  # km


# ============================================================================================
#  МИР (World) — то, что детектор ЧИТАЕТ. Живой = Bridge; фейковый = мок для тестов.
# ============================================================================================
class World:
    """Интерфейс источника правды. Все методы → данные или None (недоступны → note, не флаг)."""
    def fleet_bikes(self):
        """list[dict] (bike rows из ReadFleet.js) или None."""
        raise NotImplementedError

    def clients_all_active(self):
        """list[dict] (CRM клиенты, filter=all_active) или None."""
        raise NotImplementedError

    def queue_in_progress(self):
        """list[dict] (очередь orc-ra, status=in_progress, lane=vps) или None."""
        raise NotImplementedError

    def task_timeout(self):
        """int: TASK_TIMEOUT из .env (дефолт 600с) — для нормальных задач."""
        raise NotImplementedError

    def task_timeout_dev(self):
        """int: TASK_TIMEOUT_DEV из .env (дефолт 2700с) — для dev/dec задач."""
        raise NotImplementedError

    def service_records(self):
        """list[dict] (Bot Data ТО-трекер «обслуживание») или None."""
        raise NotImplementedError

    def now_utc(self):
        """datetime: текущее UTC-время (инъекция в тестах)."""
        raise NotImplementedError


class LiveWorld(World):
    """Живой мир: данные через Bridge (read-only _call/_post), .env из диска."""
    def __init__(self):
        from dotenv import load_dotenv
        load_dotenv(os.path.join(REPO, ".env"))
        from bridge_client import BridgeClient
        self._c = BridgeClient(timeout=45)
        self._fleet = False   # False = «ещё не запрошено»; None = «запрошено, не получено»
        self._clients = False
        self._queue = False
        self._services = False

    def fleet_bikes(self):
        if self._fleet is False:
            r = self._c.fleet()
            self._fleet = (r.get("data", {}).get("bikes") or []) if r.get("ok") else None
        return self._fleet

    def clients_all_active(self):
        if self._clients is False:
            r = self._c.clients(filter="all_active")
            self._clients = (r.get("clients") or []) if r.get("ok") else None
        return self._clients

    def queue_in_progress(self):
        if self._queue is False:
            r = self._c.get_pending(status="in_progress", lane="vps")
            self._queue = (r.get("items") or []) if r.get("ok") else None
        return self._queue

    def service_records(self):
        if self._services is False:
            r = self._c.service_list()
            self._services = (r.get("items") or []) if r.get("ok") else None
        return self._services

    def task_timeout(self):
        try:
            return int(os.getenv("TASK_TIMEOUT", "600") or 600)
        except Exception:
            return 600

    def task_timeout_dev(self):
        try:
            return int(os.getenv("TASK_TIMEOUT_DEV", "2700") or 2700)
        except Exception:
            return 2700

    def now_utc(self):
        return datetime.datetime.now(timezone.utc)


class FakeWorld(World):
    """Фейковый мир для тестов и самотеста. Инъекция данных через конструктор."""
    def __init__(self, bikes=None, clients=None, queue_ip=None,
                 task_timeout=600, task_timeout_dev=2700, now=None, services=None):
        self._bikes = bikes      # None = «Bridge не ответил»
        self._clients = clients
        self._queue = queue_ip
        self._services = services
        self._tt = task_timeout
        self._ttd = task_timeout_dev
        self._now = now or datetime.datetime(2026, 7, 15, 12, 0, 0, tzinfo=timezone.utc)

    def fleet_bikes(self): return self._bikes
    def clients_all_active(self): return self._clients
    def queue_in_progress(self): return self._queue
    def service_records(self): return self._services
    def task_timeout(self): return self._tt
    def task_timeout_dev(self): return self._ttd
    def now_utc(self): return self._now


# ============================================================================================
#  КАРКАС ПРОВЕРОК (растяжимый список)
# ============================================================================================
class CheckRun:
    """Результат одной проверки: расхождения (flag) + служебные заметки (note)."""
    def __init__(self, name):
        self.name = name
        self.findings = []   # list[(says, reality)]
        self.notes = []

    def flag(self, says, reality):
        """Нарушение инварианта: says = что нарушено (адрес), reality = суть нарушения."""
        self.findings.append((says, reality))

    def note(self, text):
        """Служебная заметка (пропуск/деградация) — НЕ нарушение."""
        self.notes.append(text)


CHECKS = []   # [(имя, fn(world, run))]


def register(name):
    """Декоратор: @register("ИМЯ") регистрирует fn в CHECKS."""
    def deco(fn):
        CHECKS.append((name, fn))
        return fn
    return deco


# --------------------------------------------------------------------------------------------
#  ИНВАРИАНТ 1: FLEET_OIL_GEAR
#  Лист1 Байки: oil_last (I) и gear (J) не пусты у байков «В аренде»
#  + не превышают HARD_MAX_KM (явная ошибка ввода).
#  ЖИВОЙ ФОРМАТ: oil_last_km/gear_last_km = число из parseNumber; 0 = пусто/нечисловое.
#  ПРИМЕЧАНИЕ: полноценная проверка oil/gear ≤ текущий одометр требует col Q из CRM
#  («текущий пробег», формула Booking.js BOOKING.COL.ODO=17) — он НЕ экспортируется текущим
#  fleet endpoint (ReadFleet.js читает A3:X, col Q в CRM совсем другая таблица).
# --------------------------------------------------------------------------------------------
@register("FLEET_OIL_GEAR")
def check_fleet_oil_gear(world, run):
    bikes = world.fleet_bikes()
    if bikes is None:
        run.note("fleet() не вернул данные — FLEET_OIL_GEAR пропущена")
        return
    rented = [b for b in bikes if str(b.get("status") or "").strip() == "В аренде"]
    if not rented:
        run.note("нет байков «В аренде» в Лист1 — нулевая выборка (нормально вне сезона)")
        return
    for b in rented:
        name = b.get("name", "?")
        # Живой формат: parseNumber вернул число; 0 = пусто/нечисловое
        oil = b.get("oil_last_km") or 0
        gear = b.get("gear_last_km") or 0
        if not oil:
            run.flag(
                f"Лист1 Байки/«{name}» (В аренде) col I: oil_last_km = 0 (пусто)",
                "байк в аренде без записи замены масла — ТО не зафиксировано или не введено",
            )
        elif oil > HARD_MAX_KM:
            run.flag(
                f"Лист1 Байки/«{name}» (В аренде) col I: oil_last_km = {oil}",
                f"нереальный пробег замены масла (>{HARD_MAX_KM} км) — вероятно ошибка ввода",
            )
        if not gear:
            run.flag(
                f"Лист1 Байки/«{name}» (В аренде) col J: gear_last_km = 0 (пусто)",
                "байк в аренде без записи замены gear oil — ТО не зафиксировано или не введено",
            )
        elif gear > HARD_MAX_KM:
            run.flag(
                f"Лист1 Байки/«{name}» (В аренде) col J: gear_last_km = {gear}",
                f"нереальный пробег замены gear oil (>{HARD_MAX_KM} км) — вероятно ошибка ввода",
            )
    run.note(
        f"одометр-сравнение: col Q (текущий пробег) недоступен через fleet endpoint — "
        f"full check требует CRM clients с col Q"
    )


# --------------------------------------------------------------------------------------------
#  ИНВАРИАНТ 2: CRM_OVERDUE
#  CRM «клиенты»: «В аренде» с date_end в прошлом больше OVERDUE_DAYS дней → флаг.
#  ЖИВОЙ ФОРМАТ date_end: "2026-07-14 14:00" (yyyy-MM-dd HH:mm, Bangkok TZ ≈UTC+7;
#  сравниваем как UTC — погрешность ±7ч несущественна при пороге 2 суток).
# --------------------------------------------------------------------------------------------
def _parse_date_end(val):
    """Парс date_end из CRM: '2026-07-14 14:00' → datetime (UTC) или None."""
    if not val:
        return None
    s = str(val).strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})\s+(\d{1,2}):(\d{2})$", s)
    if m:
        try:
            return datetime.datetime(
                int(m.group(1)), int(m.group(2)), int(m.group(3)),
                int(m.group(4)), int(m.group(5)), 0, tzinfo=timezone.utc,
            )
        except Exception:
            return None
    m2 = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", s)
    if m2:
        try:
            return datetime.datetime(
                int(m2.group(1)), int(m2.group(2)), int(m2.group(3)),
                23, 59, 0, tzinfo=timezone.utc,
            )
        except Exception:
            return None
    return None


@register("CRM_OVERDUE")
def check_crm_overdue(world, run):
    clients = world.clients_all_active()
    if clients is None:
        run.note("clients(all_active) не вернул данные — CRM_OVERDUE пропущена")
        return
    now = world.now_utc()
    for c in clients:
        if str(c.get("status") or "").strip() != "В аренде":
            continue
        date_end = _parse_date_end(c.get("date_end"))
        if date_end is None:
            continue
        days = (now - date_end).total_seconds() / 86400
        if days > OVERDUE_DAYS:
            bike = c.get("bike", "?")
            name = c.get("name", "?")
            row = c.get("row", "?")
            run.flag(
                f"CRM клиенты/строка {row}/«{bike}»/«{name}»: date_end={c.get('date_end')} "
                f"(col F), статус «В аренде»",
                f"просрочка возврата {days:.1f} дней — байк не сдан, а дата истекла",
            )


# --------------------------------------------------------------------------------------------
#  ИНВАРИАНТ 3: CRM_NO_BOOKING_ID
#  «В аренде»/«Бронь» без booking_id (col Y) — договор/Галка не работают.
#  ЖИВОЙ ФОРМАТ: booking_id — строка uuid или '' (пусто = ещё не присвоен).
# --------------------------------------------------------------------------------------------
@register("CRM_NO_BOOKING_ID")
def check_crm_no_booking_id(world, run):
    clients = world.clients_all_active()
    if clients is None:
        run.note("clients(all_active) не вернул данные — CRM_NO_BOOKING_ID пропущена")
        return
    for c in clients:
        st = str(c.get("status") or "").strip()
        if st not in _ACTIVE_ST:
            continue
        bid = str(c.get("booking_id") or "").strip()
        if not bid:
            bike = c.get("bike", "?")
            name = c.get("name", "?")
            row = c.get("row", "?")
            run.flag(
                f"CRM клиенты/строка {row}/«{bike}»/«{name}»: статус «{st}», "
                f"booking_id (col Y) пуст",
                "активная аренда/бронь без booking_id — договор и Галка v1 не работают",
            )


# --------------------------------------------------------------------------------------------
#  ИНВАРИАНТ 4: CRM_DEPOSIT
#  Депозит col S: одновременно содержит И цифру И слово «passport» — противоречит правилу.
#  ЖИВОЙ ФОРМАТ: deposit_raw = строка из S сырьём (О3-3c): "7000" | "passport" | "" | мусор.
# --------------------------------------------------------------------------------------------
@register("CRM_DEPOSIT")
def check_crm_deposit(world, run):
    clients = world.clients_all_active()
    if clients is None:
        run.note("clients(all_active) не вернул данные — CRM_DEPOSIT пропущена")
        return
    for c in clients:
        st = str(c.get("status") or "").strip()
        if st not in _ACTIVE_ST:
            continue
        dep_raw = str(c.get("deposit_raw") or "").strip()
        if not dep_raw:
            continue
        low = dep_raw.lower()
        if bool(_DIGIT_RE.search(low)) and "passport" in low:
            bike = c.get("bike", "?")
            name = c.get("name", "?")
            row = c.get("row", "?")
            run.flag(
                f"CRM клиенты/строка {row}/«{bike}»/«{name}»: deposit (col S) = «{dep_raw}»",
                "депозит содержит И сумму И «passport» — правило: либо деньги, либо паспорт, не оба",
            )


# --------------------------------------------------------------------------------------------
#  ИНВАРИАНТ 5: FLEET_CLICK_125
#  HONDA CLICK 125 в статусе «В аренде» — нарушение бизнес-правила «не сдаём».
#  ЖИВОЙ ФОРМАТ: name = точное название из Лист1 col C, напр. "HONDA CLICK 125 5580".
# --------------------------------------------------------------------------------------------
@register("FLEET_CLICK_125")
def check_fleet_click_125(world, run):
    bikes = world.fleet_bikes()
    if bikes is None:
        run.note("fleet() не вернул данные — FLEET_CLICK_125 пропущена")
        return
    for b in bikes:
        if str(b.get("status") or "").strip() != "В аренде":
            continue
        name = str(b.get("name") or "")
        if _CLICK125_RE.search(name):
            run.flag(
                f"Лист1 Байки/«{name}»: статус «В аренде» (col B)",
                "HONDA CLICK 125 не сдаётся (бизнес-правило CLAUDE.md) — проверить немедленно",
            )


# --------------------------------------------------------------------------------------------
#  ИНВАРИАНТ 6: QUEUE_LONG_IP
#  Очередь оркестратора: in_progress старше 2×TASK_TIMEOUT — страховка реапера.
#  ЖИВОЙ ФОРМАТ updated: ISO строка "2026-07-15T08:30:00+00:00" или "…Z".
#  Порог: 2×TASK_TIMEOUT_DEV для dev/dec/curator; 2×TASK_TIMEOUT для быстрых.
# --------------------------------------------------------------------------------------------
@register("QUEUE_LONG_IP")
def check_queue_long_ip(world, run):
    items = world.queue_in_progress()
    if items is None:
        run.note("get_pending(in_progress) не вернул данные — QUEUE_LONG_IP пропущена")
        return
    now = world.now_utc()
    t_norm = world.task_timeout()
    t_dev = world.task_timeout_dev()
    for it in items:
        frm = str(it.get("from") or "")
        tid = it.get("id", "?")
        upd_raw = str(it.get("updated") or "")
        if not upd_raw:
            continue
        try:
            updated = datetime.datetime.fromisoformat(upd_raw.replace("Z", "+00:00"))
        except Exception:
            continue
        age = (now - updated).total_seconds()
        is_dev = any(frm.endswith(s) for s in _DEV_SUFFIXES)
        threshold = t_dev if is_dev else t_norm
        if age > 2 * threshold:
            mins = int(age / 60)
            run.flag(
                f"Очередь оркестратора/задача {tid} (from={frm}): in_progress, "
                f"updated {mins} мин назад (col updated)",
                f"задача висит >2×{threshold}с={2*threshold}с — реапер должен был закрыть; "
                f"возможен Bridge-сбой или клин демона",
            )


# --------------------------------------------------------------------------------------------
#  Вспомогательные функции для инвариантов 7 и 8
# --------------------------------------------------------------------------------------------
def _extract_plate(name):
    """4-значный номер байка из имени («PCX160 4234» → '4234') или None."""
    m = _PLATE_RE.search(str(name))
    return m.group(1) if m else None


def _parse_iso_dt(val):
    """ISO datetime (updated_at Bot Data) → datetime UTC или None."""
    if not val:
        return None
    try:
        return datetime.datetime.fromisoformat(str(val).replace("Z", "+00:00"))
    except Exception:
        return None


# --------------------------------------------------------------------------------------------
#  ИНВАРИАНТ 7: OIL_VS_CURRENT_ODO
#  Лист1 col I (oil_last_km) ≈ current_km из Bot Data ТО-трекера → подозрение
#  «км взят из фото одометра, а не из реальной замены масла» (класс инцидента 2478).
#  Порог OIL_PHOTO_DELTA = 100 км: |oil_last_km − current_km| ≤ N → подозрительно.
#  Маркер свежести OIL_FRESH_SECS = 2 ч: Bot Data обновлён < 2ч назад → ТО только что
#  занесено (oil = текущий пробег в момент замены, норма) — не флагуем.
#  ЖИВОЙ ФОРМАТ Bot Data: updated_at = ISO строка (Date из Apps Script → JSON); current_km = число.
# --------------------------------------------------------------------------------------------
@register("OIL_VS_CURRENT_ODO")
def check_oil_vs_current_odo(world, run):
    bikes = world.fleet_bikes()
    services = world.service_records()
    if bikes is None:
        run.note("fleet() не вернул данные — OIL_VS_CURRENT_ODO пропущена")
        return
    if services is None:
        run.note("service_list() не вернул данные — OIL_VS_CURRENT_ODO пропущена")
        return
    now = world.now_utc()
    # Индекс Bot Data: номер байка → oil-запись
    oil_svc = {}
    for svc in services:
        if str(svc.get("service_type") or "").strip() != "oil":
            continue
        plate = _extract_plate(svc.get("bike") or "")
        if plate:
            oil_svc[plate] = svc
    if not oil_svc:
        run.note("Bot Data «обслуживание» не содержит oil-записей — OIL_VS_CURRENT_ODO пропущена")
        return
    for b in bikes:
        name = b.get("name", "?")
        oil_last_km = b.get("oil_last_km") or 0
        if not oil_last_km:
            continue  # пустой col I — покрывается FLEET_OIL_GEAR
        plate = _extract_plate(name)
        if not plate:
            continue
        svc = oil_svc.get(plate)
        if not svc:
            continue
        cur_km = svc.get("current_km") or 0
        if not cur_km:
            continue
        if abs(oil_last_km - cur_km) > OIL_PHOTO_DELTA:
            continue  # нормальный разрыв: байк проехал с момента последней замены
        # Маркер свежести: Bot Data только что обновлён → ТО занесено сейчас
        upd_dt = _parse_iso_dt(svc.get("updated_at"))
        if upd_dt is not None:
            if (now - upd_dt).total_seconds() <= OIL_FRESH_SECS:
                continue  # свежая запись — не флагуем
        run.flag(
            f"Лист1 Байки/«{name}» col I: oil_last_km={oil_last_km}, "
            f"Bot Data current_km={cur_km} (|diff|≤{OIL_PHOTO_DELTA}км)",
            f"подозрение класс 2478: col I совпадает с текущим одометром — "
            f"возможно км взят из фото одометра, а не из реальной замены масла",
        )


# --------------------------------------------------------------------------------------------
#  ИНВАРИАНТ 8: BOT_DATA_VS_SHEET
#  Bot Data «обслуживание» last_service_km ↔ Лист1 I (oil) / J (gear) расходятся
#  более чем на BOT_DATA_OIL_DELTA = 200 км → флаг «источники ТО не синхронизированы».
#  ЖИВОЙ ФОРМАТ: last_service_km = число из Bot Data (num_); 0/'' = не задано.
# --------------------------------------------------------------------------------------------
@register("BOT_DATA_VS_SHEET")
def check_bot_data_vs_sheet(world, run):
    bikes = world.fleet_bikes()
    services = world.service_records()
    if bikes is None:
        run.note("fleet() не вернул данные — BOT_DATA_VS_SHEET пропущена")
        return
    if services is None:
        run.note("service_list() не вернул данные — BOT_DATA_VS_SHEET пропущена")
        return
    fleet = {}
    for b in bikes:
        plate = _extract_plate(b.get("name") or "")
        if plate:
            fleet[plate] = b
    for svc in services:
        stype = str(svc.get("service_type") or "").strip()
        if stype not in ("oil", "gear"):
            continue
        bike_name = svc.get("bike") or "?"
        plate = _extract_plate(bike_name)
        if not plate:
            continue
        b = fleet.get(plate)
        if not b:
            continue
        last_svc_km = svc.get("last_service_km") or 0
        if not last_svc_km:
            continue  # Bot Data не хранит предыдущее значение — пропуск
        col, sheet_km = ("I", b.get("oil_last_km") or 0) if stype == "oil" \
            else ("J", b.get("gear_last_km") or 0)
        if not sheet_km:
            continue  # пустой col → покрывается FLEET_OIL_GEAR
        diff = abs(sheet_km - last_svc_km)
        if diff > BOT_DATA_OIL_DELTA:
            run.flag(
                f"Лист1 Байки/«{b.get('name', bike_name)}» col {col}: "
                f"{stype}_last_km={sheet_km} ↔ Bot Data last_service_km={last_svc_km} "
                f"(расхождение {diff}км)",
                f"источники ТО расходятся на {diff}км (порог {BOT_DATA_OIL_DELTA}км) — "
                f"Лист1 {col} и Bot Data «обслуживание» не синхронизированы",
            )


# --------------------------------------------------------------------------------------------
#  ИНВАРИАНТ 9: SCRATCHPAD_WRITERS
#  _*.py в корне репо: прямые вызовы write_doc (минуя write_cclog/cclog.py) → флаг с адресом.
#  Правило (CLAUDE.md R16): единственный путь записи в журнал мозга — write_cclog() / cclog.py;
#  прямая запись из scratchpad-скриптов вне tools/ запрещена.
#  Реализация: in-process скан (os.listdir + file.read), без subprocess — по образцу token_audit.
#  Тестируем через _SCRATCHPAD_ROOT (injectable); None → REPO.
# --------------------------------------------------------------------------------------------
@register("SCRATCHPAD_WRITERS")
def check_scratchpad_writers(world, run):
    root = _SCRATCHPAD_ROOT if _SCRATCHPAD_ROOT is not None else REPO
    try:
        entries = sorted(os.listdir(root))
    except OSError as e:
        run.note(f"каталог репо недоступен: {e}")
        return
    for fn in entries:
        if not (fn.startswith("_") and fn.endswith(".py")):
            continue
        path = os.path.join(root, fn)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8", errors="ignore") as f:
                for lineno, line in enumerate(f, 1):
                    if _BRAIN_WRITE_RE.search(line):
                        run.flag(
                            f"scratchpad/{fn}:{lineno}",
                            "прямой вызов write_doc — канонический путь: write_cclog() или cclog.py",
                        )
        except OSError:
            pass


# --------------------------------------------------------------------------------------------
#  ИНВАРИАНТ 10: SCRATCH_UNTRACKED
#  Разведочные скрипты `_*.py`, лежащие в КОРНЕ репо и НЕ отслеживаемые git → флаг.
#  Правило (CLAUDE.md R17): место разведки — временный каталог, не корень репо.
#  ЗАЧЕМ ДЕТЕКТОР, а не `git status`: с 24.07.2026 `_*.py` стоит в .gitignore («scratch /
#  throwaway») → накопление НЕВИДИМО для `git status` (цель 36: 33 таких файла нашлись только
#  ручным ls). Отслеживаемость берём из `git ls-files` — ignore-правила на tracked не влияют.
#  TRACKED НЕ ФЛАГУЕМ: файл в индексе = осознанный, отревьюенный код репо (напр. _envfix_probe.py),
#  а не разведочный мусор; правило про мусор, не про имя.
#  FAIL-SAFE: git недоступен / не репо / ошибка → note, НЕ флаг (деградация ≠ нарушение).
# --------------------------------------------------------------------------------------------
def _git_tracked_top_level(root):
    """Имена файлов ВЕРХНЕГО уровня, отслеживаемых git в root. → set | None (git недоступен).
    ЖИВОЙ ФОРМАТ: `git ls-files -z` отдаёт NUL-разделённые пути ОТНОСИТЕЛЬНО root;
    вложенные несут '/' → отсекаем (инвариант только про корень)."""
    if _TRACKED_PROVIDER is not None:
        return _TRACKED_PROVIDER(root)
    try:
        p = subprocess.run(["git", "-C", root, "ls-files", "-z"],
                           capture_output=True, timeout=20)
        if p.returncode != 0:
            return None
        names = p.stdout.decode("utf-8", "replace").split("\0")
        return {n for n in names if n and "/" not in n}
    except Exception:
        return None


@register("SCRATCH_UNTRACKED")
def check_scratch_untracked(world, run):
    root = _SCRATCHPAD_ROOT if _SCRATCHPAD_ROOT is not None else REPO
    try:
        entries = sorted(os.listdir(root))
    except OSError as e:
        run.note(f"каталог репо недоступен: {e}")
        return
    on_disk = [fn for fn in entries
               if fn.startswith("_") and fn.endswith(".py")
               and os.path.isfile(os.path.join(root, fn))]
    if not on_disk:
        return
    tracked = _git_tracked_top_level(root)
    if tracked is None:
        run.note("git недоступен (не репо / ошибка) — отслеживаемость _*.py не проверена")
        return
    for fn in on_disk:
        if fn in tracked:
            continue
        run.flag(
            f"{fn} (корень репо, untracked)",
            "разведочный скрипт копится в корне: _*.py в .gitignore → невидим для git status; "
            "место разведки — временный каталог (/tmp/tb_scratch), а не корень репо",
        )


# --------------------------------------------------------------------------------------------
#  ИНВАРИАНТ 11: CARD_DUTY_PURE
#  Дежурный по карточкам (card_duty.py) решает, снимать ли вопрос владельцу. Его граница —
#  «не может выдать себе прав и не может переписать свои правила» — держится НЕ докстрингом, а
#  отсутствием инструментов: в модуле ровно один импорт (`re`), ни файлов, ни сети, ни
#  подпроцессов, ни моста. Этот инвариант разбирает файл через ast и краснеет, если инструмент
#  появился: новый импорт вне списка, вызов записи/исполнения, слово «approved» в коде.
#  ПОЧЕМУ AST, А НЕ ГРЕП ПО ТЕКСТУ: имя в комментарии, строке и докстринге кодом не является —
#  ровно то правило, которым 02.08 переписаны денежная и удаляющая ветви гарда.
#  FAIL-CLOSED: файла нет / не парсится → ФЛАГ (а не note): нечитаемый дежурный доверия не имеет.
# --------------------------------------------------------------------------------------------
_CARD_DUTY_PATH = None          # подменяется САМОТЕСТОМ; None → боевой card_duty.py в репо
_DUTY_ALLOWED_IMPORTS = frozenset(("re",))
# ГОЛЫЕ встроенные имена, дающие руки. Именно голые: `compile` — это исполнение, а `re.compile`
# — сборка регулярки, и различает их ПОЗИЦИЯ, а не слово (то же правило исполняющей позиции, что
# в гарде, 04.08). Метод объекта (`f.get`, `m.group`) сюда не попадает по построению.
_DUTY_FORBIDDEN_CALLS = frozenset((
    "open", "exec", "eval", "compile", "__import__", "input", "globals", "vars", "setattr",
))
# Модули, через которые руки приходят. Импорты и так ограничены списком выше, поэтому это
# второй рубеж — на случай отложенного/переименованного импорта внутри функции.
_DUTY_FORBIDDEN_ATTR_ROOTS = frozenset((
    "os", "sys", "subprocess", "shutil", "socket", "requests", "urllib",
    "pathlib", "tempfile", "sqlite3", "bridge_client", "notify", "bc", "builtins",
))


def _duty_ast_findings(src, allowed=None):
    """→ список (адрес, чем плохо). Пустой список = дежурный чист. Разбор — ast, не подстрока.

    `allowed` — какие корни импорта законны ИМЕННО для этого модуля. По умолчанию список
    дежурного (`re`), и тогда поведение БАЙТ-В-БАЙТ прежнее для всех, кто звал функцию до
    появления параметра. Своя ручка нужна там, где чистый модуль стоит на ДРУГОМ чистом
    модуле: `fleet_cell` держится на контракте `scan_result`, у которого импортов ноль вовсе,
    — разрешить ему `re` и запретить `scan_result` значило бы судить по имени, а не по тому,
    даёт ли импорт руки."""
    import ast
    allowed = _DUTY_ALLOWED_IMPORTS if allowed is None else allowed
    out = []
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                root = a.name.split(".")[0]
                if root not in allowed:
                    out.append((f"строка {node.lineno}", f"импорт «{a.name}» вне списка "
                                f"{sorted(allowed)} — у решения появились руки"))
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root not in allowed:
                out.append((f"строка {node.lineno}", f"импорт из «{node.module}» вне списка — "
                            f"у решения появились руки"))
        elif isinstance(node, ast.Call):
            fn = node.func
            # ГОЛОЕ имя в исполняющей позиции — только оно; `re.compile` это НЕ `compile`.
            if isinstance(fn, ast.Name) and fn.id in _DUTY_FORBIDDEN_CALLS:
                out.append((f"строка {node.lineno}", f"вызов «{fn.id}» — запись/исполнение/сеть "
                            f"в модуле, который обязан быть чистым решением"))
            if isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name) \
                    and fn.value.id in _DUTY_FORBIDDEN_ATTR_ROOTS:
                out.append((f"строка {node.lineno}",
                            f"обращение к «{fn.value.id}.{fn.attr}» — модуль решения не смеет "
                            f"трогать мир"))
        elif isinstance(node, ast.Name) and node.id == "approved":
            out.append((f"строка {node.lineno}",
                        "имя «approved» в коде дежурного: одобрять он не вправе ни при каких "
                        "условиях — вердиктов ровно два, HOLD и CLOSE"))
    return out


@register("CARD_DUTY_PURE")
def check_card_duty_pure(world, run):
    # Путь НЕ берём из _SCRATCHPAD_ROOT: самотест уводит тот корень во временные каталоги ради
    # других инвариантов, и дежурный там честно отсутствовал бы → ложный флаг. Своя ручка.
    path = _CARD_DUTY_PATH or os.path.join(REPO, "card_duty.py")
    try:
        with open(path, encoding="utf-8") as f:
            src = f.read()
    except OSError as e:
        run.flag("card_duty.py", f"модуль решения не читается ({e}) — чистота не доказана")
        return
    try:
        findings = _duty_ast_findings(src)
    except SyntaxError as e:
        run.flag("card_duty.py", f"модуль решения не разбирается ({e}) — чистота не доказана")
        return
    for where, why in findings:
        run.flag(f"card_duty.py:{where}", why)


# --------------------------------------------------------------------------------------------
#  ИНВАРИАНТ 12: CURATOR_EVENT_PURE
#  Тождество СОБЫТИЯ между целями (curator_event.py) решает, ставить ли кураторское продолжение.
#  Его граница та же, что у дежурного: модуль ОТВЕЧАЕТ «одно ли это событие» и НЕ ходит в мир —
#  ни очереди, ни моста, ни файлов; ставит и отказывает только orchestrator_daemon. Держится это
#  не докстрингом, а отсутствием инструментов: ровно один импорт (`re`). Разбор — тот же ast, что
#  у дежурного (имя в комментарии/строке кодом не является).
#  FAIL-CLOSED: файла нет / не парсится → ФЛАГ: нечитаемое правило доверия не имеет.
# --------------------------------------------------------------------------------------------
_CURATOR_EVENT_PATH = None      # подменяется САМОТЕСТОМ; None → боевой curator_event.py в репо


@register("CURATOR_EVENT_PURE")
def check_curator_event_pure(world, run):
    path = _CURATOR_EVENT_PATH or os.path.join(REPO, "curator_event.py")
    try:
        with open(path, encoding="utf-8") as f:
            src = f.read()
    except OSError as e:
        run.flag("curator_event.py", f"модуль тождества не читается ({e}) — чистота не доказана")
        return
    try:
        findings = _duty_ast_findings(src)
    except SyntaxError as e:
        run.flag("curator_event.py", f"модуль тождества не разбирается ({e}) — чистота не доказана")
        return
    for where, why in findings:
        run.flag(f"curator_event.py:{where}", why)


# --------------------------------------------------------------------------------------------
#  ИНВАРИАНТ 12а: CURATOR_CLAIM_PURE
#  Позиция ЗАЯВКИ (curator_claim.py) решает, считать ли названное имя просьбой владельцу. Граница
#  та же, что у дежурного и тождества событий: модуль ОТВЕЧАЕТ по тексту и НЕ ходит в мир — ни
#  очереди, ни моста, ни файлов. Это важно вдвойне, потому что правило умеет ТОЛЬКО снимать
#  развод (карточку оно снять не может по устройству вызывающего кода): руки сделали бы из
#  «умеет меньше» — «умеет что угодно». Держится отсутствием инструментов: импорт ровно один
#  (`re`). Разбор — тот же ast, что у дежурного (имя в комментарии/строке кодом не является).
#  FAIL-CLOSED: файла нет / не парсится → ФЛАГ: нечитаемое правило доверия не имеет.
# --------------------------------------------------------------------------------------------
_CURATOR_CLAIM_PATH = None      # подменяется САМОТЕСТОМ; None → боевой curator_claim.py в репо


@register("CURATOR_CLAIM_PURE")
def check_curator_claim_pure(world, run):
    path = _CURATOR_CLAIM_PATH or os.path.join(REPO, "curator_claim.py")
    try:
        with open(path, encoding="utf-8") as f:
            src = f.read()
    except OSError as e:
        run.flag("curator_claim.py", f"модуль позиции заявки не читается ({e}) — чистота не "
                                     f"доказана")
        return
    try:
        findings = _duty_ast_findings(src)
    except SyntaxError as e:
        run.flag("curator_claim.py", f"модуль позиции заявки не разбирается ({e}) — чистота не "
                                     f"доказана")
        return
    for where, why in findings:
        run.flag(f"curator_claim.py:{where}", why)


# --------------------------------------------------------------------------------------------
#  ИНВАРИАНТ 12ж: CURATOR_STATE_PURE
#  Сверка пункта с живым состоянием (curator_state.py) решает, показывать ли пункт владельцу
#  вообще. Это единственное правило контура, умеющее ЗАКРЫТЬ вопрос владельца, — поэтому границу
#  ему держит не докстринг, а отсутствие инструментов: импорт ровно один (`re`), ни файлов, ни
#  сети, ни моста, ни очереди. Факты о мире собирает и приносит ТОЛЬКО orchestrator_daemon, судит
#  их сам прибор О3, а этот модуль лишь складывает ответ. Своего мнения о мире у него нет физически:
#  спросить мир ему нечем, значит выдумать «состоялось» он не может даже ошибкой в логике фактов.
#  Разбор — тот же ast, что у дежурного (имя в комментарии и в строке кодом не является).
#  FAIL-CLOSED: файла нет / не парсится → ФЛАГ: нечитаемое правило доверия не имеет.
# --------------------------------------------------------------------------------------------
_CURATOR_STATE_PATH = None      # подменяется САМОТЕСТОМ; None → боевой curator_state.py в репо


@register("CURATOR_STATE_PURE")
def check_curator_state_pure(world, run):
    path = _CURATOR_STATE_PATH or os.path.join(REPO, "curator_state.py")
    try:
        with open(path, encoding="utf-8") as f:
            src = f.read()
    except OSError as e:
        run.flag("curator_state.py", f"модуль сверки состояния не читается ({e}) — чистота не "
                                     f"доказана")
        return
    try:
        findings = _duty_ast_findings(src)
    except SyntaxError as e:
        run.flag("curator_state.py", f"модуль сверки состояния не разбирается ({e}) — чистота не "
                                     f"доказана")
        return
    for where, why in findings:
        run.flag(f"curator_state.py:{where}", why)


# --------------------------------------------------------------------------------------------
#  ИНВАРИАНТ 12б: REVIZOR_ROUTE_PURE
#  Маршрут находок ревизора (revizor_route.py) решает, что уходит заметкой в ленту, а что
#  остаётся вопросом владельцу. Граница та же, что у дежурного и тождества событий: модуль
#  ОТВЕЧАЕТ, а руки (лента, артефакт, состояние, очередь) — у devbot. Держится это отсутствием
#  инструментов: импорт ровно один (`re`), ни файлов, ни сети, ни моста, ни Telegram. Значит
#  правило не может ни отправить что-то от своего имени, ни погасить карточку молча — оно
#  умеет ТОЛЬКО вернуть разбор текста. Разбор — тот же ast, что у дежурного (имя в комментарии
#  и в строке кодом не является).
#  FAIL-CLOSED: файла нет / не парсится → ФЛАГ: нечитаемое правило доверия не имеет.
# --------------------------------------------------------------------------------------------
_REVIZOR_ROUTE_PATH = None      # подменяется САМОТЕСТОМ; None → боевой revizor_route.py в репо


@register("REVIZOR_ROUTE_PURE")
def check_revizor_route_pure(world, run):
    path = _REVIZOR_ROUTE_PATH or os.path.join(REPO, "revizor_route.py")
    try:
        with open(path, encoding="utf-8") as f:
            src = f.read()
    except OSError as e:
        run.flag("revizor_route.py", f"модуль маршрута не читается ({e}) — чистота не доказана")
        return
    try:
        findings = _duty_ast_findings(src)
    except SyntaxError as e:
        run.flag("revizor_route.py", f"модуль маршрута не разбирается ({e}) — чистота не доказана")
        return
    for where, why in findings:
        run.flag(f"revizor_route.py:{where}", why)


# --------------------------------------------------------------------------------------------
#  ИНВАРИАНТ 12г: DOC_STATE_PURE
#  Перепись утверждений о состоянии (doc_state_claims.py) решает, привязано ли объявление в
#  стоячем документе к дате и живому факту. Граница та же, что у дежурного: модуль ОТВЕЧАЕТ по
#  переданному тексту, а руки (чтение документов, разрешение путей и коммитов, красный гейт) —
#  в tests/test_doc_state_claims.py. Держится отсутствием инструментов: импорт ровно один
#  (`re`), ни файлов, ни сети, ни подпроцессов. Это важно вдвойне: правило судит ДОКУМЕНТ, то
#  есть текст, которым сама система себя описывает, — модуль с руками мог бы «согласовать»
#  документ, переписав его вместо того, чтобы назвать расхождение.
#  FAIL-CLOSED: файла нет / не парсится → ФЛАГ: нечитаемое правило доверия не имеет.
# --------------------------------------------------------------------------------------------
_DOC_STATE_PATH = None          # подменяется САМОТЕСТОМ; None → боевой doc_state_claims.py


@register("DOC_STATE_PURE")
def check_doc_state_pure(world, run):
    path = _DOC_STATE_PATH or os.path.join(REPO, "doc_state_claims.py")
    try:
        with open(path, encoding="utf-8") as f:
            src = f.read()
    except OSError as e:
        run.flag("doc_state_claims.py", f"модуль переписи не читается ({e}) — чистота не доказана")
        return
    try:
        findings = _duty_ast_findings(src)
    except SyntaxError as e:
        run.flag("doc_state_claims.py", f"модуль переписи не разбирается ({e}) — чистота не "
                                        f"доказана")
        return
    for where, why in findings:
        run.flag(f"doc_state_claims.py:{where}", why)


# --------------------------------------------------------------------------------------------
#  ИНВАРИАНТ 12д: CHAIN_SERIES_PURE
#  Счёт серии цепочек (chain_series.py) отвечает на вопросы «чья это цепочка», «какого сорта
#  вмешательство» и «какая сейчас серия». Граница та же, что у дежурного: модуль ОТВЕЧАЕТ по
#  переданным фактам и НЕ ходит в мир — ни очереди, ни моста, ни файла состояния, ни git, ни
#  systemd. Здесь это важно особо: счёт — ПРИБОР, по которому судят о фазе, и прибор, умеющий
#  писать, мог бы «улучшить» показание вместо того, чтобы его назвать. Держится отсутствием
#  инструментов: импорт ровно один (`re`); руки — в orchestrator_daemon и chain_series_report.
#  FAIL-CLOSED: файла нет / не парсится → ФЛАГ: нечитаемый прибор доверия не имеет.
# --------------------------------------------------------------------------------------------
_CHAIN_SERIES_PATH = None       # подменяется САМОТЕСТОМ; None → боевой chain_series.py


@register("CHAIN_SERIES_PURE")
def check_chain_series_pure(world, run):
    path = _CHAIN_SERIES_PATH or os.path.join(REPO, "chain_series.py")
    try:
        with open(path, encoding="utf-8") as f:
            src = f.read()
    except OSError as e:
        run.flag("chain_series.py", f"счётчик серии не читается ({e}) — чистота не доказана")
        return
    try:
        findings = _duty_ast_findings(src)
    except SyntaxError as e:
        run.flag("chain_series.py", f"счётчик серии не разбирается ({e}) — чистота не доказана")
        return
    for where, why in findings:
        run.flag(f"chain_series.py:{where}", why)


# --------------------------------------------------------------------------------------------
#  ИНВАРИАНТ 12в: FLEET_CELL_PURE
#  Контракт клетки Лист1 (fleet_cell.py) отвечает на один вопрос — ЧТО лежало в клетке ТО:
#  ЗНАЧЕНИЕ / ПУСТО / НЕ-ЧИСЛО, и четвёртым исходом честно говорит «источник не прочитан», пока
#  мост не прислал разметку. Он ТРАНСПОРТ, а не толкователь: не чинит значения (−5000 км и
#  настоящий ноль доезжают как есть) и не ходит за ними сам — читает мост, зовёт bridge_client.
#  Появись у него руки — он смог бы «дочитать» клетку в обход моста, и тогда ответ про клетку
#  зависел бы от того, кто спросил, а не от того, что в клетке. Держится это отсутствием
#  инструментов: импорт РОВНО ОДИН — сам контракт `scan_result` (у которого импортов ноль),
#  ни файлов, ни сети, ни моста, ни подпроцессов. Разбор — тот же ast, что у дежурного:
#  имя в комментарии, строке и докстринге кодом не является.
#  FAIL-CLOSED: файла нет / не парсится → ФЛАГ: нечитаемый контракт доверия не имеет.
# --------------------------------------------------------------------------------------------
_FLEET_CELL_PATH = None         # подменяется САМОТЕСТОМ; None → боевой fleet_cell.py в репо
_FLEET_CELL_ALLOWED_IMPORTS = frozenset(("scan_result",))


@register("FLEET_CELL_PURE")
def check_fleet_cell_pure(world, run):
    path = _FLEET_CELL_PATH or os.path.join(REPO, "fleet_cell.py")
    try:
        with open(path, encoding="utf-8") as f:
            src = f.read()
    except OSError as e:
        run.flag("fleet_cell.py", f"контракт клетки не читается ({e}) — чистота не доказана")
        return
    try:
        findings = _duty_ast_findings(src, allowed=_FLEET_CELL_ALLOWED_IMPORTS)
    except SyntaxError as e:
        run.flag("fleet_cell.py", f"контракт клетки не разбирается ({e}) — чистота не доказана")
        return
    for where, why in findings:
        run.flag(f"fleet_cell.py:{where}", why)


# --------------------------------------------------------------------------------------------
#  ИНВАРИАНТ 12г: WRITE_FACT_PURE
#  Решение «легло / не легло / неизвестно» (write_fact.py) отвечает на один вопрос: стоит ли в
#  перечитанной клетке ИМЕННО наша величина. Оно судит ПРИНЕСЁННОЕ и обязано быть слепым к миру:
#  появись у него руки — оно смогло бы сходить за клеткой само, и тогда «записано» зависело бы от
#  того, КАК спросили, а не от того, что в клетке. Хуже того, руками можно было бы ДОПИСАТЬ
#  недостающее и назвать это фактом — ровно тот подлог, против которого модуль и стоит.
#  Импорт РОВНО ОДИН — контракт `scan_result` (у которого импортов ноль): исходы клетки берутся
#  готовыми, второго словаря о тех же смыслах здесь не заводится. Разбор — тот же ast, что у
#  дежурного: имя в комментарии, строке и докстринге кодом не является.
#  FAIL-CLOSED: файла нет / не парсится → ФЛАГ: нечитаемое решение доверия не имеет.
# --------------------------------------------------------------------------------------------
_WRITE_FACT_PATH = None         # подменяется САМОТЕСТОМ; None → боевой write_fact.py в репо
_WRITE_FACT_ALLOWED_IMPORTS = frozenset(("scan_result",))


@register("WRITE_FACT_PURE")
def check_write_fact_pure(world, run):
    path = _WRITE_FACT_PATH or os.path.join(REPO, "write_fact.py")
    try:
        with open(path, encoding="utf-8") as f:
            src = f.read()
    except OSError as e:
        run.flag("write_fact.py", f"решение о факте записи не читается ({e}) — чистота не доказана")
        return
    try:
        findings = _duty_ast_findings(src, allowed=_WRITE_FACT_ALLOWED_IMPORTS)
    except SyntaxError as e:
        run.flag("write_fact.py", f"решение о факте записи не разбирается ({e}) — чистота "
                                  f"не доказана")
        return
    for where, why in findings:
        run.flag(f"write_fact.py:{where}", why)


# --------------------------------------------------------------------------------------------
#  ИНВАРИАНТ 12з: CARD_DEADLINE_PURE
#  Общий дедлайн сборки карточки «Инфо» (card_deadline.py) отвечает на один вопрос — сколько
#  бюджета осталось и влезает ли в него ещё одно плечо. Он ОБЯЗАН быть слеп к миру: узнай он
#  время сам — и «сколько осталось» перестало бы зависеть от того, когда открыли бюджет; получи
#  он сеть или файл — и решение о потолке могло бы само стоить секунд, которые считает. Держится
#  это отсутствием инструментов: импортов НОЛЬ (ни времени, ни сети, ни файлов, ни подпроцессов).
#  Руки живут отдельно: `bridge_client.card_budget` (кто открывает бюджет и режет лестницы) и
#  `splinter._build_bike_card` (кто собирает карточку) — их проверяет tests/test_info_card_deadline.py.
#  FAIL-CLOSED: файла нет / не парсится → ФЛАГ: недоказанная чистота доверия не имеет.
# --------------------------------------------------------------------------------------------
_CARD_DEADLINE_PATH = None      # подменяется САМОТЕСТОМ; None → боевой card_deadline.py в репо


@register("CARD_DEADLINE_PURE")
def check_card_deadline_pure(world, run):
    path = _CARD_DEADLINE_PATH or os.path.join(REPO, "card_deadline.py")
    try:
        with open(path, encoding="utf-8") as f:
            src = f.read()
    except OSError as e:
        run.flag("card_deadline.py", f"решение дедлайна не читается ({e}) — чистота не доказана")
        return
    try:
        findings = _duty_ast_findings(src, allowed=frozenset())
    except SyntaxError as e:
        run.flag("card_deadline.py", f"решение дедлайна не разбирается ({e}) — чистота не доказана")
        return
    for where, why in findings:
        run.flag(f"card_deadline.py:{where}", why)


# --------------------------------------------------------------------------------------------
#  ИНВАРИАНТ 12и: EXPECT_JOURNAL_PURE
#  Адрес наблюдения (expect_journal.py) отвечает на один вопрос: уходит ли эта строка только в
#  мозг или ещё и владельцу. Он ОБЯЗАН быть слеп к миру, и по той же причине, что и остальные
#  решения слоя: узнай он время сам — и «пережил ли эпизод отсрочку» перестало бы зависеть от
#  переданных фактов; получи он сеть или файл — и модуль, решающий про АДРЕС, смог бы сам по
#  этому адресу и отправить, то есть перестал бы быть решением и стал бы рукой.
#  Разрешён ровно один импорт — `datetime`, и только ради метки UTC в строке журнала: локальная
#  метка врёт (класс 17.07, Bangkok UTC+7), а без метки строка непригодна для поиска по времени.
#  FAIL-CLOSED: файла нет / не парсится → ФЛАГ: недоказанная чистота доверия не имеет.
# --------------------------------------------------------------------------------------------
_EXPECT_JOURNAL_PATH = None     # подменяется САМОТЕСТОМ; None → боевой expect_journal.py в репо


# --------------------------------------------------------------------------------------------
#  ИНВАРИАНТ 12к: BALANCE_FACT_PURE
#  Решение кассы (balance_fact.py) отвечает на два вопроса: свеж ли показанный баланс и стоит ли
#  наша проводка в листе. Оно ОБЯЗАНО быть слепым к миру ровно потому, ради чего написано: появись
#  у него сеть — оно смогло бы спросить мост САМО, и «сверено» стало бы зависеть от того, КАК
#  спросили, а не от того, что ответил лист; появись файл — оно прочло бы кэш само и снова начало
#  бы выдавать кэш за свежее число, то есть воскресило бы подмену, против которой стоит.
#  Импорт РОВНО ОДИН — `write_fact` (у него свой один, `scan_result`): вокабуляр исходов записи и
#  решение «перечитывать ли после этого ответа» берутся готовыми, второго словаря о тех же
#  смыслах здесь не заводится. Разбор — тот же ast: имя в комментарии, строке и докстринге кодом
#  не является (модуль о мосте и кэше ГОВОРИТ, и это законно).
#  FAIL-CLOSED: файла нет / не парсится → ФЛАГ: нечитаемое решение доверия не имеет.
# --------------------------------------------------------------------------------------------
_BALANCE_FACT_PATH = None       # подменяется САМОТЕСТОМ; None → боевой balance_fact.py в репо


@register("BALANCE_FACT_PURE")
def check_balance_fact_pure(world, run):
    path = _BALANCE_FACT_PATH or os.path.join(REPO, "balance_fact.py")
    try:
        with open(path, encoding="utf-8") as f:
            src = f.read()
    except OSError as e:
        run.flag("balance_fact.py", f"решение кассы не читается ({e}) — чистота не доказана")
        return
    try:
        findings = _duty_ast_findings(src, allowed=frozenset(("write_fact",)))
    except SyntaxError as e:
        run.flag("balance_fact.py", f"решение кассы не разбирается ({e}) — чистота не доказана")
        return
    for where, why in findings:
        run.flag(f"balance_fact.py:{where}", why)


# --------------------------------------------------------------------------------------------
#  ИНВАРИАНТ 12м: REVIZOR_AGE_PURE
#  Возраст тика на доске (revizor_age.py) отвечает на один вопрос: сколько прошло с момента,
#  НАЗВАННОГО В ШТАМПЕ, и стар ли этот тик по порогу владельца. Слепота к миру здесь и есть
#  предмет: появись у модуля способ спросить время или прочитать журнал САМОМУ — «возраст»
#  снова стал бы зависеть от того, КОГДА и ЧЕМ спросили, а не от штампа, а голдены доски
#  поехали бы за живыми часами (тот же класс, что «мок, переставший задевать ветку»).
#  Импорт РОВНО ОДИН — `datetime`: разобрать штамп и вычесть его из ПРИНЕСЁННОГО «сейчас».
#  FAIL-CLOSED: файла нет / не парсится → ФЛАГ: недоказанная чистота доверия не имеет.
# --------------------------------------------------------------------------------------------
_REVIZOR_AGE_PATH = None        # подменяется САМОТЕСТОМ; None → боевой revizor_age.py в репо


@register("REVIZOR_AGE_PURE")
def check_revizor_age_pure(world, run):
    path = _REVIZOR_AGE_PATH or os.path.join(REPO, "revizor_age.py")
    try:
        with open(path, encoding="utf-8") as f:
            src = f.read()
    except OSError as e:
        run.flag("revizor_age.py", f"решение возраста тика не читается ({e}) — чистота не доказана")
        return
    try:
        findings = _duty_ast_findings(src, allowed=frozenset(("datetime",)))
    except SyntaxError as e:
        run.flag("revizor_age.py",
                 f"решение возраста тика не разбирается ({e}) — чистота не доказана")
        return
    for where, why in findings:
        run.flag(f"revizor_age.py:{where}", why)


# --------------------------------------------------------------------------------------------
#  ИНВАРИАНТ 12л: SERVICE_RECEIPT_PURE
#  Квитанция ТО (service_receipt.py) отвечает на один вопрос: что случилось с записью и как это
#  звучит на обоих языках. Она ОБЯЗАНА быть слепа к миру ровно потому, ради чего написана: появись
#  у неё сеть — она смогла бы спросить мост САМА, и «записано» снова стало бы зависеть от того,
#  КАК спросили, а не от того, что ответил лист; появись отправка — половины опять поехали бы
#  врозь, потому что рядом с рендером завёлся бы второй путь наружу.
#  Импорт РОВНО ОДИН — `write_fact` (у него свой один, `scan_result`): вокабуляр определённых
#  отказов берётся готовым, второго словаря о тех же смыслах не заводится.
#  FAIL-CLOSED: файла нет / не парсится → ФЛАГ: недоказанная чистота доверия не имеет.
# --------------------------------------------------------------------------------------------
_SERVICE_RECEIPT_PATH = None    # подменяется САМОТЕСТОМ; None → боевой service_receipt.py в репо


@register("SERVICE_RECEIPT_PURE")
def check_service_receipt_pure(world, run):
    path = _SERVICE_RECEIPT_PATH or os.path.join(REPO, "service_receipt.py")
    try:
        with open(path, encoding="utf-8") as f:
            src = f.read()
    except OSError as e:
        run.flag("service_receipt.py", f"решение квитанции не читается ({e}) — чистота не доказана")
        return
    try:
        findings = _duty_ast_findings(src, allowed=frozenset(("write_fact",)))
    except SyntaxError as e:
        run.flag("service_receipt.py", f"решение квитанции не разбирается ({e}) — чистота не доказана")
        return
    for where, why in findings:
        run.flag(f"service_receipt.py:{where}", why)


@register("EXPECT_JOURNAL_PURE")
def check_expect_journal_pure(world, run):
    path = _EXPECT_JOURNAL_PATH or os.path.join(REPO, "expect_journal.py")
    try:
        with open(path, encoding="utf-8") as f:
            src = f.read()
    except OSError as e:
        run.flag("expect_journal.py", f"решение адреса не читается ({e}) — чистота не доказана")
        return
    try:
        findings = _duty_ast_findings(src, allowed=frozenset(("datetime",)))
    except SyntaxError as e:
        run.flag("expect_journal.py", f"решение адреса не разбирается ({e}) — чистота не доказана")
        return
    for where, why in findings:
        run.flag(f"expect_journal.py:{where}", why)


# --------------------------------------------------------------------------------------------
#  ИНВАРИАНТ 13: PROD_DRIFT_READONLY
#  Детектор дрейфа прода (prod_drift.py) видит, что живой процесс отстал от origin/main, и
#  ГОВОРИТ об этом. Решение владельца — «детектор без рестарта»: автоматики перезапуска живых
#  процессов нет ни в каком виде. Это обязано держаться устройством, а не докстрингом, поэтому
#  инвариант доказывает три «не умеет» разом:
#    • НЕ ЗАПУСКАЕТ: единственная внешняя команда — `git`; первый элемент argv обязан быть
#      литералом «git», `shell=True` запрещён, из subprocess разрешён только `run`;
#    • НЕ ПИШЕТ: `open` только на чтение, ни одной пишущей/удаляющей ручки `os`;
#    • НЕ ОТПРАВЛЯЕТ: импорты по списку — ни моста, ни notify, ни сети.
#  Плюс словарь: слова, которыми в этой системе перезапускают процессы (`systemctl`,
#  `systemd-run`, `pkill`, …), не смеют встречаться в КОДЕ модуля.
#  ПОЧЕМУ ДОКСТРИНГИ ИСКЛЮЧЕНЫ ИЗ СЛОВАРЯ: документация обязана уметь НАЗВАТЬ то, чего модуль
#  не делает («юнит берём из /proc/<pid>/cgroup, а не из вывода systemctl») — иначе честное
#  объяснение границы стало бы нарушением границы. Исполнить докстринг всё равно нечем: голова
#  argv проверена отдельным правилом, и она литерал.
#  FAIL-CLOSED: файла нет / не парсится → ФЛАГ (нечитаемый детектор доверия не имеет).
# --------------------------------------------------------------------------------------------
_PROD_DRIFT_PATH = None         # подменяется САМОТЕСТОМ; None → боевой prod_drift.py в репо
_DRIFT_ALLOWED_IMPORTS = frozenset(("ast", "os", "subprocess", "time"))
# Ручки os, которыми пишут, удаляют, убивают и исполняют. Читающие (`os.stat`, `os.listdir`,
# `os.sysconf`, `os.path.*`, `os.environ`) не перечислены намеренно — детектор ими и живёт.
_DRIFT_FORBIDDEN_OS = frozenset((
    "system", "popen", "kill", "killpg", "remove", "unlink", "rmdir", "removedirs", "rename",
    "renames", "replace", "mkdir", "makedirs", "chmod", "chown", "truncate", "write", "fork",
    "forkpty", "abort", "setsid", "execv", "execve", "execl", "execlp", "execvp", "spawnv",
    "spawnl", "spawnlp", "spawnvp",
))
# Модули, через которые приходят руки. Импорты и так по списку — это второй рубеж на случай
# отложенного или переименованного импорта внутри функции.
_DRIFT_FORBIDDEN_ROOTS = frozenset((
    "shutil", "signal", "socket", "requests", "urllib", "http", "smtplib", "sqlite3", "ctypes",
    "multiprocessing", "pathlib", "tempfile", "bridge_client", "notify", "telegram", "builtins",
))
_DRIFT_FORBIDDEN_CALLS = frozenset(("exec", "eval", "compile", "__import__", "input", "setattr"))
# Слова, которыми перезапускают процессы. В КОДЕ детектора их быть не может (см. шапку).
_DRIFT_FORBIDDEN_WORDS = ("systemctl", "systemd-run", "pkill", "killall", "supervisorctl",
                          "reboot", "shutdown", "initctl", "telinit")
_DRIFT_WRITE_MODES = ("w", "a", "x", "+")


def _drift_docstring_ids(tree):
    """id() строковых узлов, которые являются ДОКСТРИНГАМИ (модуля, функции, класса)."""
    import ast as _ast
    out = set()
    for node in _ast.walk(tree):
        if not isinstance(node, (_ast.Module, _ast.FunctionDef, _ast.AsyncFunctionDef,
                                 _ast.ClassDef)):
            continue
        body = getattr(node, "body", None) or []
        if body and isinstance(body[0], _ast.Expr) and isinstance(body[0].value, _ast.Constant) \
                and isinstance(body[0].value.value, str):
            out.add(id(body[0].value))
    return out


def _drift_cmd_head(node):
    """Голова argv у subprocess.run: первый элемент списка (слева от любых «+»). → строка | None."""
    import ast as _ast
    cur = node
    while isinstance(cur, _ast.BinOp) and isinstance(cur.op, _ast.Add):
        cur = cur.left
    if isinstance(cur, (_ast.List, _ast.Tuple)) and cur.elts:
        first = cur.elts[0]
        if isinstance(first, _ast.Constant) and isinstance(first.value, str):
            return first.value
    return None


def _drift_ast_findings(src):
    """→ список (адрес, чем плохо). Пустой список = детектор доказанно read-only."""
    import ast as _ast
    out = []
    tree = _ast.parse(src)
    docs = _drift_docstring_ids(tree)
    for node in _ast.walk(tree):
        if isinstance(node, _ast.Import):
            for a in node.names:
                if a.name.split(".")[0] not in _DRIFT_ALLOWED_IMPORTS:
                    out.append((f"строка {node.lineno}", f"импорт «{a.name}» вне списка "
                                f"{sorted(_DRIFT_ALLOWED_IMPORTS)} — у детектора появились руки"))
        elif isinstance(node, _ast.ImportFrom):
            if (node.module or "").split(".")[0] not in _DRIFT_ALLOWED_IMPORTS:
                out.append((f"строка {node.lineno}", f"импорт из «{node.module}» вне списка — "
                            f"детектор обязан только читать"))
        elif isinstance(node, _ast.Constant) and isinstance(node.value, str) \
                and id(node) not in docs:
            low = node.value.lower()
            for w in _DRIFT_FORBIDDEN_WORDS:
                if w in low:
                    out.append((f"строка {node.lineno}", f"слово «{w}» в коде детектора: "
                                f"перезапускать он не вправе ни при каких условиях"))
                    break
        elif isinstance(node, _ast.Call):
            fn = node.func
            if isinstance(fn, _ast.Name) and fn.id in _DRIFT_FORBIDDEN_CALLS:
                out.append((f"строка {node.lineno}", f"вызов «{fn.id}» — исполнение в модуле, "
                            f"которому разрешено только чтение"))
            if isinstance(fn, _ast.Name) and fn.id == "open":
                mode = None
                if len(node.args) > 1 and isinstance(node.args[1], _ast.Constant):
                    mode = node.args[1].value
                for kw in node.keywords:
                    if kw.arg == "mode" and isinstance(kw.value, _ast.Constant):
                        mode = kw.value.value
                if isinstance(mode, str) and any(m in mode for m in _DRIFT_WRITE_MODES):
                    out.append((f"строка {node.lineno}", f"open(…, «{mode}») — детектор не пишет "
                                f"ничего и никуда: состояние держат руки демона"))
            if isinstance(fn, _ast.Attribute) and isinstance(fn.value, _ast.Name):
                root, attr = fn.value.id, fn.attr
                if root in _DRIFT_FORBIDDEN_ROOTS:
                    out.append((f"строка {node.lineno}", f"обращение к «{root}.{attr}» — "
                                f"детектор не смеет ни писать, ни отправлять"))
                elif root == "os" and attr in _DRIFT_FORBIDDEN_OS:
                    out.append((f"строка {node.lineno}", f"«os.{attr}» — запись/удаление/"
                                f"исполнение в read-only модуле"))
                elif root == "subprocess":
                    if attr != "run":
                        out.append((f"строка {node.lineno}", f"«subprocess.{attr}» — из subprocess "
                                    f"разрешён только run(git …)"))
                    head = _drift_cmd_head(node.args[0]) if node.args else None
                    if head != "git":
                        out.append((f"строка {node.lineno}", f"внешняя команда «{head}» — "
                                    f"словарь детектора состоит ровно из читающего git"))
                    for kw in node.keywords:
                        if kw.arg == "shell" and not (isinstance(kw.value, _ast.Constant)
                                                      and kw.value.value is False):
                            out.append((f"строка {node.lineno}", "shell=True — оболочка исполняет "
                                        "что угодно, а не только git"))
    return out


@register("PROD_DRIFT_READONLY")
def check_prod_drift_readonly(world, run):
    path = _PROD_DRIFT_PATH or os.path.join(REPO, "prod_drift.py")
    try:
        with open(path, encoding="utf-8") as f:
            src = f.read()
    except OSError as e:
        run.flag("prod_drift.py", f"детектор дрейфа не читается ({e}) — read-only не доказан")
        return
    try:
        findings = _drift_ast_findings(src)
    except SyntaxError as e:
        run.flag("prod_drift.py", f"детектор дрейфа не разбирается ({e}) — read-only не доказан")
        return
    for where, why in findings:
        run.flag(f"prod_drift.py:{where}", why)


# --------------------------------------------------------------------------------------------
#  ИНВАРИАНТ 14: EXPECTATIONS_PURE
#  Слой ожиданий (expectations.py) решает, нарушено ли ожидание, и возвращает вердикт СПИСКОМ.
#  Граница владельца — «заметка и, если держится, задача; живые процессы, данные и инфраструктуру
#  не трогать» — обязана держаться устройством, а не докстрингом, поэтому здесь доказывается
#  сильнейшая форма: модуль НЕ УМЕЕТ НИЧЕГО, кроме арифметики над переданными фактами.
#    • импорты РОВНО из белого списка (re, datetime) — ни os, ни subprocess, ни сети, ни моста,
#      ни notify: собрать факты и отнести текст в канал он не может физически;
#    • ни одной ручки ввода-вывода: open/exec/eval/__import__ запрещены как имена вызовов;
#    • слова, которыми в этой системе перезапускают процессы, не смеют встречаться в КОДЕ.
#  ПОЧЕМУ ДОКСТРИНГИ ИСКЛЮЧЕНЫ (то же решение, что у PROD_DRIFT_READONLY): документация обязана
#  уметь НАЗВАТЬ то, чего модуль не делает, иначе честное объяснение границы стало бы её
#  нарушением. Исполнить докстринг нечем — вызовов в модуле нет вовсе.
#  FAIL-CLOSED: файла нет / не парсится → ФЛАГ (нечитаемое решение доверия не имеет).
# --------------------------------------------------------------------------------------------
_EXPECT_PATH = None                     # подменяется САМОТЕСТОМ; None → боевой expectations.py
_EXPECT_ALLOWED_IMPORTS = frozenset(("re", "datetime"))
_EXPECT_FORBIDDEN_CALLS = frozenset(("open", "exec", "eval", "compile", "__import__", "input",
                                     "setattr", "delattr"))
# Те же слова, что у детектора дрейфа: наблюдатель не перезапускает ничего ни при каких условиях.
_EXPECT_FORBIDDEN_WORDS = _DRIFT_FORBIDDEN_WORDS


def _expect_ast_findings(src):
    """→ список (адрес, чем плохо). Пустой список = решение доказанно без рук."""
    import ast as _ast
    out = []
    tree = _ast.parse(src)
    docs = _drift_docstring_ids(tree)
    for node in _ast.walk(tree):
        if isinstance(node, _ast.Import):
            for a in node.names:
                if a.name.split(".")[0] not in _EXPECT_ALLOWED_IMPORTS:
                    out.append((f"строка {node.lineno}", f"импорт «{a.name}» вне списка "
                                f"{sorted(_EXPECT_ALLOWED_IMPORTS)} — у решения появились руки"))
        elif isinstance(node, _ast.ImportFrom):
            if (node.module or "").split(".")[0] not in _EXPECT_ALLOWED_IMPORTS:
                out.append((f"строка {node.lineno}", f"импорт из «{node.module}» вне списка — "
                            f"слой ожиданий обязан быть чистой функцией фактов"))
        elif isinstance(node, _ast.Constant) and isinstance(node.value, str) \
                and id(node) not in docs:
            low = node.value.lower()
            for w in _EXPECT_FORBIDDEN_WORDS:
                if w in low:
                    out.append((f"строка {node.lineno}", f"слово «{w}» в коде слоя ожиданий: "
                                f"реакция информационная, перезапускать он не вправе"))
                    break
        elif isinstance(node, _ast.Call):
            fn = node.func
            if isinstance(fn, _ast.Name) and fn.id in _EXPECT_FORBIDDEN_CALLS:
                out.append((f"строка {node.lineno}", f"вызов «{fn.id}» — ввод-вывод в модуле, "
                            f"которому разрешена только арифметика над фактами"))
            if isinstance(fn, _ast.Attribute) and isinstance(fn.value, _ast.Name):
                root, attr = fn.value.id, fn.attr
                if root in ("os", "subprocess", "shutil", "socket", "requests", "urllib",
                            "bridge_client", "notify", "smtplib", "sqlite3", "pathlib",
                            "tempfile", "signal", "multiprocessing", "ctypes"):
                    out.append((f"строка {node.lineno}", f"обращение к «{root}.{attr}» — решение "
                                f"не собирает факты и не носит текст в канал, это дело рук"))
    return out


@register("EXPECTATIONS_PURE")
def check_expectations_pure(world, run):
    path = _EXPECT_PATH or os.path.join(REPO, "expectations.py")
    try:
        with open(path, encoding="utf-8") as f:
            src = f.read()
    except OSError as e:
        run.flag("expectations.py", f"слой ожиданий не читается ({e}) — чистота не доказана")
        return
    try:
        findings = _expect_ast_findings(src)
    except SyntaxError as e:
        run.flag("expectations.py", f"слой ожиданий не разбирается ({e}) — чистота не доказана")
        return
    for where, why in findings:
        run.flag(f"expectations.py:{where}", why)


# --------------------------------------------------------------------------------------------
#  ИНВАРИАНТ 15: INBOX_SINGLE_DOOR
#  Инбокс 1160 держит РОВНО одно свойство — «всё здесь ждёт меня». Держится оно дверью
#  `notify.send_inbox(text, answerable)`: адрес выбирает признак «ждёт ли сообщение ответа», а не
#  автор сообщения. Дверь была заведена 05.08.2026, но остатком там же записано честно: она
#  «контракт, а не забор» — ничто не мешало следующей функции в notify.py взять адрес инбокса
#  самой и уехать туда мимо признака. Этот инвариант делает дверь ЕДИНСТВЕННОЙ по устройству:
#    • `_inbox_dest` (единственный источник адреса инбокса) зовётся ТОЛЬКО из `_send_inbox_card`;
#    • `_send_inbox_card` (единственный, кто этот адрес применяет) зовётся ТОЛЬКО из `send_inbox`;
#    • `_send_message` (единственный выход в Telegram) зовётся только из трёх известных мест —
#      новая функция с собственной отправкой обязана быть замечена, а не «просто заработать»;
#    • у двери есть параметр `answerable` — признак маршрута ровно один и он назван.
#  ПОЧЕМУ ЗАБОР ЖИВЁТ ТОЛЬКО ВНУТРИ notify.py: инбокс законно адресуют ещё два модуля — devbot
#  (карточки needs_answer с кнопками ✅/❌) и bot.post_audit_card (contradiction/HIGH). Запретить
#  им обращение к теме значило бы запретить сам инбокс, поэтому там граница держится ЗАМКОМ в
#  коде доставки (`devbot._inbox_lock_topic`) и тестами обоих направлений, а не этим стражем.
#  FAIL-CLOSED: файла нет / не парсится / у правила пропал предмет → ФЛАГ.
# --------------------------------------------------------------------------------------------
_NOTIFY_PATH = None                     # подменяется САМОТЕСТОМ; None → боевой notify.py в репо
_DOOR_NAME = "send_inbox"               # дверь: признак «ждёт ответа» → адрес
_DOOR_CARD = "_send_inbox_card"         # тело маршрута инбокса
_DOOR_DEST = "_inbox_dest"              # источник адреса инбокса (chat, thread)
_DOOR_SEND = "_send_message"            # единственный выход в Telegram внутри notify.py
_DOOR_SEND_OK = frozenset(("notify", "_send_inbox_card", "send_feed"))


def _door_callers(src):
    """{имя вызываемого: {имена функций, из ТЕЛ которых он зовётся}} по ast.

    Считается БЛИЖАЙШАЯ объемлющая функция (вложенная не приписывается внешней), имя в
    комментарии и в строке вызовом не является — тот же приём, что у остальных стражей.
    """
    import ast as _ast
    out = {}

    def walk(node, fname):
        for child in _ast.iter_child_nodes(node):
            if isinstance(child, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
                walk(child, child.name)
                continue
            if isinstance(child, _ast.Call) and isinstance(child.func, _ast.Name):
                out.setdefault(child.func.id, set()).add(fname)
            walk(child, fname)

    tree = _ast.parse(src)
    walk(tree, "<модуль>")
    return tree, out


def _door_ast_findings(src):
    """→ список (адрес, чем плохо). Пустой список = в инбокс ведёт ровно одна дверь."""
    import ast as _ast
    out = []
    tree, callers = _door_callers(src)

    def only(callee, allowed, what):
        got = callers.get(callee) or set()
        if not got:                       # предмет пропал: правило больше нечего охранять
            out.append((callee, f"{what} не зовётся ниоткуда — правило потеряло предмет, "
                                f"проверь, не переименована ли дверь"))
            return
        extra = sorted(got - {allowed})
        if extra:
            out.append((callee, f"{what} зовётся мимо двери из {extra} — в инбокс обязан вести "
                                f"единственный путь «{allowed}»"))

    only(_DOOR_DEST, _DOOR_CARD, "адрес инбокса")
    only(_DOOR_CARD, _DOOR_NAME, "маршрут инбокса")

    sends = callers.get(_DOOR_SEND) or set()
    extra = sorted(sends - set(_DOOR_SEND_OK))
    if extra:
        out.append((_DOOR_SEND, f"отправка в Telegram появилась в {extra} — новый выход мимо "
                                f"двери; известны только {sorted(_DOOR_SEND_OK)}"))

    door = next((n for n in _ast.walk(tree)
                 if isinstance(n, (_ast.FunctionDef, _ast.AsyncFunctionDef))
                 and n.name == _DOOR_NAME), None)
    if door is None:
        out.append((_DOOR_NAME, "двери в инбокс нет вовсе — признак маршрута не назван"))
    else:
        args = [a.arg for a in list(door.args.args) + list(door.args.kwonlyargs)]
        if "answerable" not in args:
            out.append((f"{_DOOR_NAME}:строка {door.lineno}",
                        "у двери пропал параметр «answerable» — признак маршрута обязан быть "
                        "ОДИН и назван явно, иначе адрес снова выбирает автор сообщения"))
    return out


@register("INBOX_SINGLE_DOOR")
def check_inbox_single_door(world, run):
    path = _NOTIFY_PATH or os.path.join(REPO, "notify.py")
    try:
        with open(path, encoding="utf-8") as f:
            src = f.read()
    except OSError as e:
        run.flag("notify.py", f"канал уведомлений не читается ({e}) — единственность двери в "
                              f"инбокс не доказана")
        return
    try:
        findings = _door_ast_findings(src)
    except SyntaxError as e:
        run.flag("notify.py", f"канал уведомлений не разбирается ({e}) — единственность двери в "
                              f"инбокс не доказана")
        return
    for where, why in findings:
        run.flag(f"notify.py:{where}", why)


# ============================================================================================
#  ТОЧКА РАСШИРЕНИЯ (будущие инварианты):
#    @register("CRM_DATES")   — date_end < date_start (логическая ошибка брони)
#    @register("FLEET_DEBT")  — долг col X в CRM пересчитывается формулой, не вводится вручную
#  Каждый — одна @register-функция fn(world, run); CHECKS не переписывать.
# ============================================================================================


def run_all(world):
    """Прогнать ВСЕ зарегистрированные инварианты. → list[CheckRun]."""
    runs = []
    for name, fn in CHECKS:
        r = CheckRun(name)
        try:
            fn(world, r)
        except Exception as e:
            r.note(f"инвариант упал: {e!r}")
        runs.append(r)
    return runs


def format_report(runs, ts=None):
    """Форматированный отчёт для телефона (тема 328)."""
    if ts is None:
        ts = datetime.datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    findings = [(r.name, s, rl) for r in runs for (s, rl) in r.findings]
    notes = [(r.name, t) for r in runs for t in r.notes]
    out = [f"🔍 ИНВАРИАНТЫ ДАННЫХ — проверка  ({ts} UTC)"]
    if not findings:
        out.append(f"✅ СХОДИТСЯ — {len(runs)} инвариантов, 0 нарушений")
    else:
        out.append(f"⚠️ {len(findings)} НАРУШЕНИЙ ({len(runs)} инвариантов):")
        for i, (name, says, reality) in enumerate(findings, 1):
            out.append(f"{i}. [{name}]")
            out.append(f"   адрес: {says}")
            out.append(f"   суть:  {reality}")
    for name, t in notes:
        out.append(f"· заметка [{name}]: {t}")
    return "\n".join(out)


# ============================================================================================
#  PUSH В ТЕМУ 328 (только при нарушениях; silent при ✅)
# ============================================================================================
def _push_to_328(text):
    """Отправить нарушения в тему 328 HQ. Best-effort, не кидает. → bool."""
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(REPO, ".env"))
        token = os.getenv("BOT_TOKEN")
        if not token:
            return False
        hq_chat = -1003853365891
        thread = 328
        url = "https://api.telegram.org/bot" + token + "/sendMessage"
        payload = json.dumps({"chat_id": hq_chat, "message_thread_id": thread,
                              "text": text}).encode()
        req = urllib.request.Request(url, data=payload,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            resp = json.load(r)
        return bool(resp.get("ok"))
    except Exception as e:
        print(f"push к 328 не отправлен: {e}", file=sys.stderr)
        return False


# ============================================================================================
#  САМОТЕСТ — синтетические заведомые нарушения (без сети; standalone без pytest)
# ============================================================================================
def _now():
    return datetime.datetime(2026, 7, 15, 12, 0, 0, tzinfo=timezone.utc)


def _healthy_world():
    """Чистый мир: ни одного нарушения ни в одном инварианте (8 инвариантов)."""
    bikes = [
        # Байк в аренде с корректными данными
        {"name": "PCX160 4234", "status": "В аренде",
         "oil_last_km": 35200, "gear_last_km": 34000, "mileage": 25000},
        # Байк дома — не проверяем (нет в аренде)
        {"name": "NMAX155 5001", "status": "ДОМА",
         "oil_last_km": 0, "gear_last_km": 0, "mileage": 12000},
        # HONDA CLICK 125 дома (правило: не сдаём; дома = ок)
        {"name": "HONDA CLICK 125 5580", "status": "ДОМА",
         "oil_last_km": 10000, "gear_last_km": 9500, "mileage": 8000},
    ]
    # date_end — живой формат yyyy-MM-dd HH:mm (Bangkok TZ, разведка CRM 23:04 08.07.2026)
    clients = [
        {"row": 5, "status": "В аренде", "bike": "PCX160 4234", "name": "John Smith",
         "date_end": "2026-07-20 14:00",          # срок ещё не истёк
         "booking_id": "abc-123-uuid",
         "deposit_raw": "7000"},
        {"row": 6, "status": "Бронь", "bike": "NMAX155 5001", "name": "Jane Doe",
         "date_end": "2026-07-25 10:00",
         "booking_id": "def-456-uuid",
         "deposit_raw": "passport"},
    ]
    # Очередь: свежая in_progress (только что взята)
    fresh_upd = (_now() - datetime.timedelta(seconds=100)).isoformat()
    queue = [
        {"id": 1, "from": "Filipp-328", "task_text": "тест",
         "status": "in_progress", "updated": fresh_upd},
    ]
    # Bot Data service records: нет расхождений (NOW=2026-07-15 12:00)
    # PCX160 4234: масло на 35200 (= col I), current_km=36000 (≠ col I → нет флага OIL_VS_CURRENT_ODO)
    # Bot Data last_service_km=35200 (= col I → diff=0 ≤ 200, нет флага BOT_DATA_VS_SHEET)
    # Запись не свежая: 2026-07-14T06:00 = 30ч назад > OIL_FRESH_SECS(7200с) → релевантна
    _old_ts = "2026-07-14T06:00:00+00:00"
    services = [
        {"updated_at": _old_ts, "bike": "PCX160 4234", "service_type": "oil",
         "current_km": 36000, "last_service_km": 35200,
         "interval_km": 3000, "next_km": 38200, "status": "ok"},
        {"updated_at": _old_ts, "bike": "PCX160 4234", "service_type": "gear",
         "current_km": 36000, "last_service_km": 34000,
         "interval_km": 10000, "next_km": 44000, "status": "ok"},
    ]
    return FakeWorld(bikes=bikes, clients=clients, queue_ip=queue,
                     task_timeout=600, task_timeout_dev=2700, now=_now(),
                     services=services)


def _runs_by_name(world):
    return {r.name: r for r in run_all(world)}


def _self_test():
    cases = []
    # Удобная обёртка: (title, ожидаем флагов в этом инварианте, фабрика мира, имя инварианта)

    # ── 1. FLEET_OIL_GEAR ────────────────────────────────────────────────────────────────
    cases.append(("OIL_GEAR чистый", 0, _healthy_world, "FLEET_OIL_GEAR"))

    w = _healthy_world()
    w._bikes[0]["oil_last_km"] = 0           # масло пусто
    cases.append(("OIL пустой у «В аренде»", 1, lambda _w=w: _w, "FLEET_OIL_GEAR"))

    w2 = _healthy_world()
    w2._bikes[0]["gear_last_km"] = 0         # gear пустой
    cases.append(("GEAR пустой у «В аренде»", 1, lambda _w=w2: _w, "FLEET_OIL_GEAR"))

    w3 = _healthy_world()
    w3._bikes[0]["oil_last_km"] = 999_999    # нереальный пробег
    cases.append(("OIL > HARD_MAX_KM", 1, lambda _w=w3: _w, "FLEET_OIL_GEAR"))

    w4 = _healthy_world()
    w4._bikes[0]["status"] = "ДОМА"          # не В аренде → не проверяем
    w4._bikes[0]["oil_last_km"] = 0
    cases.append(("OIL пусто но байк ДОМА — не флаг", 0, lambda _w=w4: _w, "FLEET_OIL_GEAR"))

    cases.append(("OIL_GEAR bridge None → note", 0,
                  lambda: FakeWorld(bikes=None, clients=[], queue_ip=[]), "FLEET_OIL_GEAR"))

    # ── 2. CRM_OVERDUE ────────────────────────────────────────────────────────────────────
    cases.append(("OVERDUE чистый (срок не истёк)", 0, _healthy_world, "CRM_OVERDUE"))

    w5 = _healthy_world()
    # date_end — живой формат; 5 дней назад (NOW=2026-07-15 12:00, end=2026-07-10 14:00)
    w5._clients[0]["date_end"] = "2026-07-10 14:00"
    cases.append(("OVERDUE >2 дней", 1, lambda _w=w5: _w, "CRM_OVERDUE"))

    w6 = _healthy_world()
    w6._clients[0]["date_end"] = "2026-07-14 14:00"  # 1 день назад < 2 дней
    cases.append(("OVERDUE <2 дней — не флаг", 0, lambda _w=w6: _w, "CRM_OVERDUE"))

    w7 = _healthy_world()
    w7._clients[0]["date_end"] = None         # нет даты → пропускаем
    cases.append(("OVERDUE нет даты → не флаг", 0, lambda _w=w7: _w, "CRM_OVERDUE"))

    cases.append(("OVERDUE bridge None → note", 0,
                  lambda: FakeWorld(bikes=[], clients=None, queue_ip=[]), "CRM_OVERDUE"))

    # ── 3. CRM_NO_BOOKING_ID ────────────────────────────────────────────────────────────
    cases.append(("BOOKING_ID чистый", 0, _healthy_world, "CRM_NO_BOOKING_ID"))

    w8 = _healthy_world()
    w8._clients[0]["booking_id"] = ""        # В аренде без booking_id
    cases.append(("NO_BOOKING_ID В аренде", 1, lambda _w=w8: _w, "CRM_NO_BOOKING_ID"))

    w9 = _healthy_world()
    w9._clients[1]["booking_id"] = ""        # Бронь без booking_id
    cases.append(("NO_BOOKING_ID Бронь", 1, lambda _w=w9: _w, "CRM_NO_BOOKING_ID"))

    w10 = _healthy_world()
    # Завершена без booking_id — не активный статус → не флаг
    w10._clients[0]["status"] = "Завершена"
    w10._clients[0]["booking_id"] = ""
    cases.append(("NO_BOOKING_ID Завершена — не флаг", 0, lambda _w=w10: _w, "CRM_NO_BOOKING_ID"))

    # ── 4. CRM_DEPOSIT ────────────────────────────────────────────────────────────────────
    cases.append(("DEPOSIT чистый", 0, _healthy_world, "CRM_DEPOSIT"))

    w11 = _healthy_world()
    # Живой формат: смешанная строка с цифрой и "passport"
    w11._clients[0]["deposit_raw"] = "7000 passport"
    cases.append(("DEPOSIT И сумма И passport", 1, lambda _w=w11: _w, "CRM_DEPOSIT"))

    w12 = _healthy_world()
    w12._clients[0]["deposit_raw"] = "Passport 5000"   # регистр нечувствительный
    cases.append(("DEPOSIT Passport+число (uppercase) — флаг", 1, lambda _w=w12: _w, "CRM_DEPOSIT"))

    w13 = _healthy_world()
    w13._clients[0]["deposit_raw"] = "passport"   # только паспорт — нормально
    cases.append(("DEPOSIT только passport — не флаг", 0, lambda _w=w13: _w, "CRM_DEPOSIT"))

    w14 = _healthy_world()
    w14._clients[0]["deposit_raw"] = "5000"   # только сумма — нормально
    cases.append(("DEPOSIT только сумма — не флаг", 0, lambda _w=w14: _w, "CRM_DEPOSIT"))

    # ── 5. FLEET_CLICK_125 ────────────────────────────────────────────────────────────────
    cases.append(("CLICK_125 чистый (дома)", 0, _healthy_world, "FLEET_CLICK_125"))

    w15 = _healthy_world()
    w15._bikes[2]["status"] = "В аренде"     # CLICK 125 → В аренде (нарушение!)
    cases.append(("CLICK_125 в аренде — флаг", 1, lambda _w=w15: _w, "FLEET_CLICK_125"))

    w16 = _healthy_world()
    # PCX не CLICK 125 — не флаг даже в аренде
    cases.append(("CLICK_125 PCX в аренде — не флаг", 0, _healthy_world, "FLEET_CLICK_125"))

    # ── 6. QUEUE_LONG_IP ──────────────────────────────────────────────────────────────────
    cases.append(("QUEUE_LONG_IP чистый (свежая задача)", 0, _healthy_world, "QUEUE_LONG_IP"))


    now = _now()
    old_upd = (now - datetime.timedelta(seconds=3000)).isoformat()   # 50 мин > 2×600с
    w17 = _healthy_world()
    w17._queue = [{"id": 99, "from": "Filipp-328", "task_text": "t",
                   "status": "in_progress", "updated": old_upd}]
    cases.append(("QUEUE_LONG_IP нормальная старая задача", 1, lambda _w=w17: _w, "QUEUE_LONG_IP"))

    old_dev = (now - datetime.timedelta(seconds=6000)).isoformat()   # 100 мин > 2×2700с
    w18 = _healthy_world()
    w18._queue = [{"id": 88, "from": "Filipp-328-dev", "task_text": "т",
                   "status": "in_progress", "updated": old_dev}]
    cases.append(("QUEUE_LONG_IP dev старая задача", 1, lambda _w=w18: _w, "QUEUE_LONG_IP"))

    young_dev = (now - datetime.timedelta(seconds=1000)).isoformat()  # 17 мин < 2×2700с
    w19 = _healthy_world()
    w19._queue = [{"id": 77, "from": "Filipp-328-dev", "task_text": "т",
                   "status": "in_progress", "updated": young_dev}]
    cases.append(("QUEUE_LONG_IP dev молодая — не флаг", 0, lambda _w=w19: _w, "QUEUE_LONG_IP"))

    # ── 7. OIL_VS_CURRENT_ODO ────────────────────────────────────────────────────────────
    cases.append(("OIL_VS_CURRENT_ODO чистый (current_km ≠ oil_last_km)", 0,
                  _healthy_world, "OIL_VS_CURRENT_ODO"))

    # ГОЛДЕН КЛАСС 2478: oil_last_km (col I) = current_km = 24997 (не свежая запись → флаг)
    w20 = _healthy_world()
    w20._bikes[0]["oil_last_km"] = 24997
    w20._services[0]["current_km"] = 24997       # совпадает с col I
    w20._services[0]["updated_at"] = "2026-07-14T06:00:00+00:00"  # старая запись
    cases.append(("OIL_VS_CURRENT_ODO голден 2478: oil=odo, старая запись — флаг", 1,
                  lambda _w=w20: _w, "OIL_VS_CURRENT_ODO"))

    # Свежая запись (< 2ч): ТО только что занесено — не флаг
    w21 = _healthy_world()
    w21._bikes[0]["oil_last_km"] = 24997
    w21._services[0]["current_km"] = 24997
    # NOW=2026-07-15 12:00, свежая = 1ч назад = 11:00
    w21._services[0]["updated_at"] = "2026-07-15T11:00:00+00:00"
    cases.append(("OIL_VS_CURRENT_ODO свежая запись (<2ч) — не флаг", 0,
                  lambda _w=w21: _w, "OIL_VS_CURRENT_ODO"))

    # Bridge None → note
    cases.append(("OIL_VS_CURRENT_ODO Bridge None → note", 0,
                  lambda: FakeWorld(bikes=[], clients=[], queue_ip=[], services=None),
                  "OIL_VS_CURRENT_ODO"))

    # ── 8. BOT_DATA_VS_SHEET ────────────────────────────────────────────────────────────
    cases.append(("BOT_DATA_VS_SHEET чистый (last_svc_km = col I)", 0,
                  _healthy_world, "BOT_DATA_VS_SHEET"))

    # oil расхождение > 200 км → флаг
    w22 = _healthy_world()
    w22._services[0]["last_service_km"] = 34000   # diff с col I(35200) = 1200 > 200
    cases.append(("BOT_DATA_VS_SHEET oil расхождение >200км — флаг", 1,
                  lambda _w=w22: _w, "BOT_DATA_VS_SHEET"))

    # gear расхождение > 200 км → флаг
    w23 = _healthy_world()
    w23._services[1]["last_service_km"] = 31000   # diff с col J(34000) = 3000 > 200
    cases.append(("BOT_DATA_VS_SHEET gear расхождение >200км — флаг", 1,
                  lambda _w=w23: _w, "BOT_DATA_VS_SHEET"))

    # Маленькое расхождение ≤ 200 км → не флаг
    w24 = _healthy_world()
    w24._services[0]["last_service_km"] = 35100   # diff с col I(35200) = 100 ≤ 200
    cases.append(("BOT_DATA_VS_SHEET расхождение ≤200км — не флаг", 0,
                  lambda _w=w24: _w, "BOT_DATA_VS_SHEET"))

    # Bridge None → note
    cases.append(("BOT_DATA_VS_SHEET Bridge None → note", 0,
                  lambda: FakeWorld(bikes=[], clients=[], queue_ip=[], services=None),
                  "BOT_DATA_VS_SHEET"))

    # ── Общие свойства: предвычисляем ДО регистрации _SELF_TEST_TEMP ─────────────────────────
    # SCRATCHPAD_WRITERS — static-инвариант (использует _SCRATCHPAD_ROOT, не world).
    # Для ALL-тестов указываем пустой temp (→ 0 находок SCRATCHPAD_WRITERS).
    import tempfile, shutil
    global _SCRATCHPAD_ROOT
    _old_scratch_root = _SCRATCHPAD_ROOT
    _all_clean_dir = tempfile.mkdtemp()
    try:
        _SCRATCHPAD_ROOT = _all_clean_dir  # пустой → 0 SCRATCHPAD_WRITERS
        _total_clean = sum(len(r.findings) for r in run_all(_healthy_world()))
        _total_degraded = sum(len(r.findings) for r in run_all(
            FakeWorld(bikes=None, clients=None, queue_ip=None)))
    finally:
        shutil.rmtree(_all_clean_dir, ignore_errors=True)
        _SCRATCHPAD_ROOT = _old_scratch_root

    # Растяжимость — регистрируем ПОСЛЕ предвычислений ALL
    n_before = len(CHECKS)

    @register("_SELF_TEST_TEMP")
    def _tmp(w, r):
        r.flag("тест", "растяжимость работает")

    cases.append(("растяжимость (@register новый инвариант)", 1,
                  _healthy_world, "_SELF_TEST_TEMP"))

    print("=== САМОТЕСТ ИНВАРИАНТОВ ===")
    allpass = True

    # Основной цикл (SCRATCHPAD_WRITERS видит пустой _all_clean_dir → 0 находок)
    _loop_clean_dir = tempfile.mkdtemp()
    _SCRATCHPAD_ROOT = _loop_clean_dir
    try:
        for title, expect, factory, cname in cases:
            w = factory() if callable(factory) else factory
            all_runs = run_all(w)
            by_name = {r.name: r for r in all_runs}
            got = len(by_name.get(cname, CheckRun(cname)).findings)
            ok = (got == expect)
            allpass &= ok
            print(f"  {'PASS' if ok else 'FAIL'}  [{cname}] {title}: "
                  f"ждали {expect}, поймали {got}")
    finally:
        shutil.rmtree(_loop_clean_dir, ignore_errors=True)
        _SCRATCHPAD_ROOT = _old_scratch_root

    # ── 9. SCRATCHPAD_WRITERS (запускаем отдельно с temp-каталогами) ─────────────────────────
    _sw_clean_dir = tempfile.mkdtemp()
    _sw_dirty_dir = tempfile.mkdtemp()
    try:
        # Грязный dir: _*.py с прямым .write_doc( → флаг; _*.py без → нет флага
        with open(os.path.join(_sw_dirty_dir, "_bad_writer.py"), "w") as _f:
            _f.write("bc.write_doc(text='x', name='cc_log')\n")
        with open(os.path.join(_sw_dirty_dir, "_ok_no_write.py"), "w") as _f:
            _f.write("# cclog.py handles this\n")

        for _sw_title, _sw_expect, _sw_root in [
            ("SCRATCHPAD чистый (нет _*.py)", 0, _sw_clean_dir),
            ("SCRATCHPAD прямой write_doc → флаг", 1, _sw_dirty_dir),
        ]:
            _SCRATCHPAD_ROOT = _sw_root
            _sw_runs = run_all(_healthy_world())
            _sw_by_name = {r.name: r for r in _sw_runs}
            _sw_got = len(_sw_by_name.get("SCRATCHPAD_WRITERS",
                                           CheckRun("SCRATCHPAD_WRITERS")).findings)
            _sw_ok = (_sw_got == _sw_expect)
            allpass &= _sw_ok
            print(f"  {'PASS' if _sw_ok else 'FAIL'}  [SCRATCHPAD_WRITERS] {_sw_title}: "
                  f"ждали {_sw_expect}, поймали {_sw_got}")
    finally:
        shutil.rmtree(_sw_clean_dir, ignore_errors=True)
        shutil.rmtree(_sw_dirty_dir, ignore_errors=True)
        _SCRATCHPAD_ROOT = _old_scratch_root

    # ── 10. SCRATCH_UNTRACKED (temp-каталоги + мок git-индекса) ──────────────────────────────
    # Здесь мок tracked-множества (быстро, без сети/git); РЕАЛЬНЫЙ git проверяется в
    # tests/test_invariants_check.py (живой формат запуска — правило 8 CLAUDE.md).
    global _TRACKED_PROVIDER
    _old_tracked = _TRACKED_PROVIDER
    _su_empty_dir = tempfile.mkdtemp()
    _su_dir = tempfile.mkdtemp()
    try:
        for _n in ("_recon.py", "_probe.py"):
            with open(os.path.join(_su_dir, _n), "w") as _f:
                _f.write("# разведка\n")
        with open(os.path.join(_su_dir, "notes.py"), "w") as _f:
            _f.write("# обычный модуль, не разведка\n")

        for _su_title, _su_expect, _su_root, _su_prov in [
            ("SCRATCH пусто (нет _*.py)", 0, _su_empty_dir, lambda r: set()),
            ("SCRATCH 2 untracked _*.py → 2 флага", 2, _su_dir, lambda r: set()),
            ("SCRATCH оба tracked → не флагуем", 0, _su_dir,
             lambda r: {"_recon.py", "_probe.py"}),
            ("SCRATCH смесь: tracked не флагуем, untracked флагуем", 1, _su_dir,
             lambda r: {"_probe.py"}),
            ("SCRATCH git недоступен → note, не флаг (fail-safe)", 0, _su_dir,
             lambda r: None),
        ]:
            _SCRATCHPAD_ROOT = _su_root
            _TRACKED_PROVIDER = _su_prov
            _su_by_name = {r.name: r for r in run_all(_healthy_world())}
            _su_got = len(_su_by_name.get("SCRATCH_UNTRACKED",
                                          CheckRun("SCRATCH_UNTRACKED")).findings)
            _su_ok = (_su_got == _su_expect)
            allpass &= _su_ok
            print(f"  {'PASS' if _su_ok else 'FAIL'}  [SCRATCH_UNTRACKED] {_su_title}: "
                  f"ждали {_su_expect}, поймали {_su_got}")
    finally:
        shutil.rmtree(_su_empty_dir, ignore_errors=True)
        shutil.rmtree(_su_dir, ignore_errors=True)
        _SCRATCHPAD_ROOT = _old_scratch_root
        _TRACKED_PROVIDER = _old_tracked

    # ── 11. CARD_DUTY_PURE (голдены на ДОСЛОВНОМ коде, а не на пересказе) ───────────────────
    # Живой модуль обязан быть чист; каждая «рука» обязана краснеть. Позиция важнее слова:
    # `re.compile` и `f.get(...)` — законны, голый `compile`/`os.remove` — нет.
    global _CARD_DUTY_PATH
    _old_duty_path = _CARD_DUTY_PATH
    _cd_dir = tempfile.mkdtemp()
    try:
        _cd_cases = [
            ("DUTY живой модуль чист", 0, None),
            ("DUTY re.compile и .get законны (позиция, не слово)", 0,
             "import re\n_R = re.compile('x')\ndef f(d):\n    return d.get('a') or _R.match('b')\n"),
            ("DUTY импорт вне списка → флаг", 1, "import re\nimport os\n"),
            ("DUTY from-импорт вне списка → флаг", 1, "from notify import send_feed\n"),
            ("DUTY голый open() → флаг", 1, "import re\nf = open('/tmp/x')\n"),
            ("DUTY os.remove → флаг (импорт + вызов)", 2, "import os\nos.remove('/tmp/x')\n"),
            ("DUTY имя approved в коде → флаг", 1, "import re\napproved = 1\n"),
            ("DUTY слово approved в СТРОКЕ и комментарии — не флаг", 0,
             "import re\n# approved тут только словом\nS = 'approved'\n"),
            ("DUTY модуль не парсится → флаг (fail-closed)", 1, "def broken(:\n"),
        ]
        for _cd_title, _cd_expect, _cd_src in _cd_cases:
            if _cd_src is None:
                _CARD_DUTY_PATH = None                       # боевой card_duty.py
            else:
                _cd_p = os.path.join(_cd_dir, "card_duty.py")
                with open(_cd_p, "w", encoding="utf-8") as _f:
                    _f.write(_cd_src)
                _CARD_DUTY_PATH = _cd_p
            _cd_run = CheckRun("CARD_DUTY_PURE")
            check_card_duty_pure(_healthy_world(), _cd_run)
            _cd_got = len(_cd_run.findings)
            _cd_ok = (_cd_got == _cd_expect)
            allpass &= _cd_ok
            print(f"  {'PASS' if _cd_ok else 'FAIL'}  [CARD_DUTY_PURE] {_cd_title}: "
                  f"ждали {_cd_expect}, поймали {_cd_got}")
        # отдельно: отсутствующий файл = флаг, а не тишина
        _CARD_DUTY_PATH = os.path.join(_cd_dir, "нет-такого.py")
        _cd_run = CheckRun("CARD_DUTY_PURE")
        check_card_duty_pure(_healthy_world(), _cd_run)
        _cd_ok = (len(_cd_run.findings) == 1)
        allpass &= _cd_ok
        print(f"  {'PASS' if _cd_ok else 'FAIL'}  [CARD_DUTY_PURE] DUTY файла нет → флаг "
              f"(fail-closed): ждали 1, поймали {len(_cd_run.findings)}")
    finally:
        shutil.rmtree(_cd_dir, ignore_errors=True)
        _CARD_DUTY_PATH = _old_duty_path

    # ── 11а. FLEET_CELL_PURE (тот же приём, но список импортов у модуля СВОЙ) ────────────────
    # Смысл секции: доказать, что страж судит НЕ ПО СЛОВУ, а по тому, даёт ли строка руки.
    # `scan_result` — законный импорт (контракт, у которого импортов ноль вовсе), `re` — нет:
    # у этого модуля разрешён РОВНО ОДИН импорт, и расширять список значит решать заново.
    global _FLEET_CELL_PATH
    _old_fc_path = _FLEET_CELL_PATH
    _fc_dir = tempfile.mkdtemp()
    try:
        _fc_cases = [
            ("CELL живой модуль чист", 0, None),
            ("CELL импорт контракта законен", 0,
             "from scan_result import ScanResult\ndef r(c):\n    return ScanResult(1, 1)\n"),
            ("CELL .get и isinstance законны (позиция, не слово)", 0,
             "from scan_result import ScanResult\n"
             "def r(b):\n    return b.get('cells') if isinstance(b, dict) else None\n"),
            ("CELL посторонний импорт → флаг (у модуля ровно один)", 1,
             "from scan_result import ScanResult\nimport re\n"),
            ("CELL импорт моста → флаг (за клеткой он ходить не вправе)", 1,
             "import bridge_client\n"),
            ("CELL голый open() → флаг", 1, "from scan_result import ScanResult\nf = open('/tmp/x')\n"),
            ("CELL os.remove → флаг (импорт + вызов)", 2, "import os\nos.remove('/tmp/x')\n"),
            ("CELL имя моста в ДОКСТРИНГЕ и комментарии — не флаг", 0,
             '"""разметку клеток шлёт bridge_client — сам модуль за ней не ходит"""\n'
             "from scan_result import ScanResult\n# bridge_client тут только словом\n"),
            ("CELL модуль не парсится → флаг (fail-closed)", 1, "def broken(:\n"),
        ]
        for _fc_title, _fc_expect, _fc_src in _fc_cases:
            if _fc_src is None:
                _FLEET_CELL_PATH = None                      # боевой fleet_cell.py
            else:
                _fc_p = os.path.join(_fc_dir, "fleet_cell.py")
                with open(_fc_p, "w", encoding="utf-8") as _f:
                    _f.write(_fc_src)
                _FLEET_CELL_PATH = _fc_p
            _fc_run = CheckRun("FLEET_CELL_PURE")
            check_fleet_cell_pure(_healthy_world(), _fc_run)
            _fc_got = len(_fc_run.findings)
            _fc_ok = (_fc_got == _fc_expect)
            allpass &= _fc_ok
            print(f"  {'PASS' if _fc_ok else 'FAIL'}  [FLEET_CELL_PURE] {_fc_title}: "
                  f"ждали {_fc_expect}, поймали {_fc_got}")
        _FLEET_CELL_PATH = os.path.join(_fc_dir, "нет-такого.py")
        _fc_run = CheckRun("FLEET_CELL_PURE")
        check_fleet_cell_pure(_healthy_world(), _fc_run)
        _fc_ok = (len(_fc_run.findings) == 1)
        allpass &= _fc_ok
        print(f"  {'PASS' if _fc_ok else 'FAIL'}  [FLEET_CELL_PURE] CELL файла нет → флаг "
              f"(fail-closed): ждали 1, поймали {len(_fc_run.findings)}")
        # список дежурного НЕ пострадал от появления своей ручки у контракта клетки
        _fc_duty_ok = (len(_duty_ast_findings("import re\n")) == 0
                       and len(_duty_ast_findings("import os\n")) == 1)
        allpass &= _fc_duty_ok
        print(f"  {'PASS' if _fc_duty_ok else 'FAIL'}  [FLEET_CELL_PURE] список дежурного по "
              f"умолчанию прежний (re законен, os — флаг)")
    finally:
        shutil.rmtree(_fc_dir, ignore_errors=True)
        _FLEET_CELL_PATH = _old_fc_path

    # ── 11б. WRITE_FACT_PURE (решение о факте записи: судит принесённое, за клеткой не ходит) ─
    # Смысл секции: доказать, что страж ловит РУКИ, а не слова. У модуля разрешён РОВНО ОДИН
    # импорт — `scan_result`; мост в докстринге законен (модуль о нём ГОВОРИТ), мост в импорте —
    # нет (тогда он смог бы сходить за клеткой сам, и «записано» перестало бы быть фактом).
    global _WRITE_FACT_PATH
    _old_wf_path = _WRITE_FACT_PATH
    _wf_dir = tempfile.mkdtemp()
    try:
        _wf_cases = [
            ("FACT живой модуль чист", 0, None),
            ("FACT импорт контракта законен", 0,
             "from scan_result import OUTCOME_EMPTY\ndef v(c):\n    return OUTCOME_EMPTY\n"),
            ("FACT getattr/isinstance законны (судит принесённое)", 0,
             "from scan_result import OUTCOME_EMPTY\n"
             "def v(c):\n    return getattr(c, 'ok', False) if isinstance(c, object) else None\n"),
            ("FACT посторонний импорт → флаг (у модуля ровно один)", 1,
             "from scan_result import OUTCOME_EMPTY\nimport re\n"),
            ("FACT импорт моста → флаг (за клеткой ходить не вправе)", 1,
             "import bridge_client\n"),
            ("FACT голый open() → флаг", 1,
             "from scan_result import OUTCOME_EMPTY\nf = open('/tmp/x')\n"),
            ("FACT bc.set_fleet_oil → флаг (импорт + рука в живую таблицу)", 2,
             "import bridge_client as bc\nbc.set_fleet_oil(number='1', oil_km=1)\n"),
            ("FACT имя моста в ДОКСТРИНГЕ и комментарии — не флаг", 0,
             '"""клетку приносит bridge_client — сам модуль за ней не ходит"""\n'
             "from scan_result import OUTCOME_EMPTY\n# bridge_client тут только словом\n"),
            ("FACT модуль не парсится → флаг (fail-closed)", 1, "def broken(:\n"),
        ]
        for _wf_title, _wf_expect, _wf_src in _wf_cases:
            if _wf_src is None:
                _WRITE_FACT_PATH = None                      # боевой write_fact.py
            else:
                _wf_p = os.path.join(_wf_dir, "write_fact.py")
                with open(_wf_p, "w", encoding="utf-8") as _f:
                    _f.write(_wf_src)
                _WRITE_FACT_PATH = _wf_p
            _wf_run = CheckRun("WRITE_FACT_PURE")
            check_write_fact_pure(_healthy_world(), _wf_run)
            _wf_got = len(_wf_run.findings)
            _wf_ok = (_wf_got == _wf_expect)
            allpass &= _wf_ok
            print(f"  {'PASS' if _wf_ok else 'FAIL'}  [WRITE_FACT_PURE] {_wf_title}: "
                  f"ждали {_wf_expect}, поймали {_wf_got}")
        _WRITE_FACT_PATH = os.path.join(_wf_dir, "нет-такого.py")
        _wf_run = CheckRun("WRITE_FACT_PURE")
        check_write_fact_pure(_healthy_world(), _wf_run)
        _wf_ok = (len(_wf_run.findings) == 1)
        allpass &= _wf_ok
        print(f"  {'PASS' if _wf_ok else 'FAIL'}  [WRITE_FACT_PURE] FACT файла нет → флаг "
              f"(fail-closed): ждали 1, поймали {len(_wf_run.findings)}")
    finally:
        shutil.rmtree(_wf_dir, ignore_errors=True)
        _WRITE_FACT_PATH = _old_wf_path

    # ── 12. PROD_DRIFT_READONLY (голдены на ДОСЛОВНОМ коде: каждая «рука» обязана краснеть) ──
    # Смысл секции: доказать, что страж ловит именно РУКИ, а не слова. Поэтому рядом стоят пары
    # «законное чтение → 0» и «то же самое, но с рукой → флаг»; докстринг, называющий границу,
    # остаётся зелёным намеренно (иначе честная документация стала бы нарушением).
    global _PROD_DRIFT_PATH
    _old_drift_path = _PROD_DRIFT_PATH
    _pd_dir = tempfile.mkdtemp()
    try:
        _pd_cases = [
            ("DRIFT живой модуль read-only", 0, None),
            ("DRIFT читающий git законен", 0, "import subprocess\nsubprocess.run(['git', 'log'])\n"),
            ("DRIFT чужая команда → флаг", 1, "import subprocess\nsubprocess.run(['clasp', 'push'])\n"),
            ("DRIFT рестарт живого процесса → 2 флага (слово + голова argv)", 2,
             "import subprocess\nsubprocess.run(['systemctl', 'restart', 'splinter'])\n"),
            ("DRIFT shell=True → флаг", 1,
             "import subprocess\nsubprocess.run(['git', 'log'], shell=True)\n"),
            ("DRIFT subprocess.Popen → флаг (разрешён только run)", 1,
             "import subprocess\nsubprocess.Popen(['git'])\n"),
            ("DRIFT open на чтение — не флаг", 0, "f = open('/tmp/x')\ng = open('/tmp/y', 'r')\n"),
            ("DRIFT open на запись → флаг", 1, "f = open('/tmp/x', 'w')\n"),
            ("DRIFT os.remove → флаг", 1, "import os\nos.remove('/tmp/x')\n"),
            ("DRIFT импорт notify → флаг (отправлять он не вправе)", 1, "import notify\n"),
            ("DRIFT слово рестарта в ДОКСТРИНГЕ — не флаг", 0,
             '"""юнит берём из /proc/<pid>/cgroup, а не из вывода systemctl"""\n'),
            ("DRIFT слово рестарта в обычной строке → флаг", 1, "S = 'systemctl restart splinter'\n"),
            ("DRIFT модуль не парсится → флаг (fail-closed)", 1, "def broken(:\n"),
        ]
        for _pd_title, _pd_expect, _pd_src in _pd_cases:
            if _pd_src is None:
                _PROD_DRIFT_PATH = None                      # боевой prod_drift.py
            else:
                _pd_p = os.path.join(_pd_dir, "prod_drift.py")
                with open(_pd_p, "w", encoding="utf-8") as _f:
                    _f.write(_pd_src)
                _PROD_DRIFT_PATH = _pd_p
            _pd_run = CheckRun("PROD_DRIFT_READONLY")
            check_prod_drift_readonly(_healthy_world(), _pd_run)
            _pd_got = len(_pd_run.findings)
            _pd_ok = (_pd_got == _pd_expect)
            allpass &= _pd_ok
            print(f"  {'PASS' if _pd_ok else 'FAIL'}  [PROD_DRIFT_READONLY] {_pd_title}: "
                  f"ждали {_pd_expect}, поймали {_pd_got}")
        _PROD_DRIFT_PATH = os.path.join(_pd_dir, "нет-такого.py")
        _pd_run = CheckRun("PROD_DRIFT_READONLY")
        check_prod_drift_readonly(_healthy_world(), _pd_run)
        _pd_ok = (len(_pd_run.findings) == 1)
        allpass &= _pd_ok
        print(f"  {'PASS' if _pd_ok else 'FAIL'}  [PROD_DRIFT_READONLY] DRIFT файла нет → флаг "
              f"(fail-closed): ждали 1, поймали {len(_pd_run.findings)}")
    finally:
        shutil.rmtree(_pd_dir, ignore_errors=True)
        _PROD_DRIFT_PATH = _old_drift_path

    # Проверяем предвычисленные ALL-результаты
    for _all_title, _all_got, _all_expect in [
        ("чистый мир — 0 нарушений ВСЕГО (все зарегистрированные инварианты)", _total_clean, 0),
        ("деградация (всё None) → 0 нарушений суммарно", _total_degraded, 0),
    ]:
        ok = (_all_got == _all_expect)
        allpass &= ok
        print(f"  {'PASS' if ok else 'FAIL'}  [ALL] {_all_title}: "
              f"ждали {_all_expect}, поймали {_all_got}")

    # Очищаем временный инвариант
    CHECKS[:] = [c for c in CHECKS if c[0] != "_SELF_TEST_TEMP"]
    assert len(CHECKS) == n_before

    print("ИТОГ:", "ВСЕ PASS ✅" if allpass else "ЕСТЬ FAIL ❌")
    return 0 if allpass else 1


def main(argv):
    if "--self-test" in argv:
        return _self_test()

    world = LiveWorld()
    runs = run_all(world)
    ts = datetime.datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")

    if "--json" in argv:
        payload = {
            "ts": ts,
            "checks": [{"name": r.name,
                         "findings": [{"says": s, "reality": rl}
                                       for (s, rl) in r.findings],
                         "notes": r.notes} for r in runs],
            "total_findings": sum(len(r.findings) for r in runs),
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    report = format_report(runs, ts=ts)
    print(report)

    if "--push" in argv:
        has_violations = any(r.findings for r in runs)
        if has_violations:
            ok = _push_to_328(report)
            print(f"[push] {'отправлен в 328' if ok else 'НЕ отправлен (см. stderr)'}")
        # При ✅ — тихо (silent = designed)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
