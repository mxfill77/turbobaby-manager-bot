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
import urllib.request
import urllib.error
from datetime import timezone

REPO = os.path.dirname(os.path.abspath(__file__))

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

    # ── Общие свойства (вычисляем ДО регистрации _SELF_TEST_TEMP — иначе ALL-счёт растёт) ──
    # Чистый мир = ноль нарушений суммарно
    _total_clean = sum(len(r.findings) for r in run_all(_healthy_world()))
    _total_degraded = sum(len(r.findings) for r in run_all(
        FakeWorld(bikes=None, clients=None, queue_ip=None)))

    # Растяжимость — регистрируем ПОСЛЕ предвычислений ALL
    n_before = len(CHECKS)

    @register("_SELF_TEST_TEMP")
    def _tmp(w, r):
        r.flag("тест", "растяжимость работает")

    cases.append(("растяжимость (@register новый инвариант)", 1,
                  _healthy_world, "_SELF_TEST_TEMP"))

    print("=== САМОТЕСТ ИНВАРИАНТОВ ===")
    allpass = True
    for title, expect, factory, cname in cases:
        w = factory() if callable(factory) else factory
        all_runs = run_all(w)
        by_name = {r.name: r for r in all_runs}
        got = len(by_name.get(cname, CheckRun(cname)).findings)
        ok = (got == expect)
        allpass &= ok
        print(f"  {'PASS' if ok else 'FAIL'}  [{cname}] {title}: "
              f"ждали {expect}, поймали {got}")

    # Проверяем предвычисленные ALL-результаты
    for title, got, expect in [
        ("чистый мир — 0 нарушений ВСЕГО (8 инвариантов)", _total_clean, 0),
        ("деградация (всё None) → 0 нарушений суммарно", _total_degraded, 0),
    ]:
        ok = (got == expect)
        allpass &= ok
        print(f"  {'PASS' if ok else 'FAIL'}  [ALL] {title}: ждали {expect}, поймали {got}")

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
