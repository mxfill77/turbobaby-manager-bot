# -*- coding: utf-8 -*-
"""restart_handoff — узкая передача ждущих карточек Splinter следующему процессу при ШТАТНОЙ остановке.

Повод: Codex TB-REL-B0392DF-STOP-1610-0459 / TB-CHECK-1610-0742 — рестарт splinter не должен терять уже принятое.
Карточки «ждут да» живут в памяти процесса; post_stop (bot.py) пишет их сюда, post_init следующего процесса —
восстанавливает ДО начала опроса. Здесь только чистые решения: что передавать, как упаковать, как проверить, применять
ли. Руки (файл, метка, журнал) — в splinter (`handoff_write` / `handoff_restore`). Ввода-вывода, сети, часов и
процессов здесь нет: всё приходит аргументами.

Граница — названа прямо:
  * это штатный graceful restart; при SIGKILL/OOM/падении процесса post_stop не исполняется и передачи нет;
  * передаются ТОЛЬКО карточки, ждущие ответа человека: черновик брони `awaiting_approval`, карточки выдачи и
    закрытия `awaiting`. Карточки с исходом в пути или неизвестным (approved / write_unknown / write_failed / error /
    booked / rejected …) не передаются НИКОГДА: вернуть их в «ждёт да» значило бы разрешить запись вслепую;
  * белый список полей — только нужное для продолжения (поля карточки, привязка реплая, статус, исходное время ts,
    идентификаторы дела). Паспортных данных (`passport_ocr`) нет; значения не JSON-простого вида не передаются;
  * восстановление только вписывает состояние в ПУСТЫЕ места — сообщений не шлёт, бизнес-действий не совершает;
    сроки годности прежние: ts исходный, проверку TTL делает тот же код, что и до рестарта.

Откат через штатный рестарт (CLOSEACCRUAL1910 r2, замечание приёмки 20.10) — тоже назван прямо:
  * verify() кода 947953e отвергает ВЕСЬ файл, если у одной записи есть поле вне ЕГО белого списка
    (restart_handoff.py:105@947953e). Записи `entries` поэтому держатся в белом списке 947953e (`KEYS` — его списки,
    без единого добавления): откат кода через штатный рестарт не теряет ни брони, ни выдачи, ни закрытия;
  * поля, выросшие после 947953e (`EXT_KEYS`; у закрытия — km_photo, due_total, acc_*), едут ОТДЕЛЬНЫМ разделом
    верхнего уровня `ext`. verify() 947953e его не читает вовсе: сумма тела у него — по version/written_at/pid/count/
    entries (`_body`), прочие ключи файла он не смотрит. Этот код раздел сверяет (версия, своя сумма, привязка к сумме
    тела `of`, белый список, место записи) и возвращает поля в записи — карточка исполняет ТУ ЖЕ операцию;
  * раздел незнакомой версии пропускается (карточки идут без его полей), а не роняет файл — тот же урок на следующий
    откат: новое поле раздела = новая версия раздела, а не новое поле записи;
  * остаток риска (не закрыт здесь): процесс 947953e раздела не знает — ждущую карточку закрытия он исполняет СВОИМ
    путём (без начисления доплат, «да» без числа — без пробега) и словами 947953e, а при своей остановке пишет файл БЕЗ
    раздела: код, вернувшийся вперёд, получит такую карточку в виде до ручек — без операции начисления, подсказки
    фото и метки происхождения пробега (km_src). RC2010: без метки её km не подтверждён — «да» без числа не закрывает
    (splinter `_close_km_unproven`), а «да <пробег>» закроет аренду без начисления, не назвав этого. Окно — срок
    карточки (_RET_CLOSE_TTL, 30 мин).
"""
import hashlib
import json

VERSION = 1
EXT_VERSION = 1
KIND_INTAKE, KIND_HANDOVER, KIND_CLOSE = "intake", "handover", "close"
KINDS = (KIND_INTAKE, KIND_HANDOVER, KIND_CLOSE)

# Белые списки записей — РОВНО списки 947953e (откат, см. шапку): поле сюда не добавляется НИКОГДА, новое — в EXT_KEYS.
# Черновик брони: поля разбора карточки (схема INTAKE_SYSTEM) + привязка реплая и служебное состояние.
INTAKE_KEYS = ("model", "client", "contacts", "date_start", "date_end", "date_start_iso", "date_end_iso", "term",
               "experience", "deposit_type", "delivery_name", "delivery_url", "helmets",
               "status", "ts", "ic_msg_ids", "ic_edit_asked", "passport_photo", "rc_exp_id", "rc_card_ref")
HANDOVER_KEYS = ("bike", "name", "date_start", "row", "ts", "status")
CLOSE_KEYS = ("bike", "name", "date_start", "row", "km", "paid_total", "ts", "status")
WAITING = {KIND_INTAKE: "awaiting_approval", KIND_HANDOVER: "awaiting", KIND_CLOSE: "awaiting"}
KEYS = {KIND_INTAKE: INTAKE_KEYS, KIND_HANDOVER: HANDOVER_KEYS, KIND_CLOSE: CLOSE_KEYS}
# Раздел `ext` (версия EXT_VERSION). CLOSETRUTH1910 / CLOSEACCRUAL1910: подсказка пробега с фото и «к доплате» карточки
# (km_photo, due_total) и операция начисления доплат (acc_*: id, booking_id, строка брони, день начала, строка листа
# закрытия, четыре части; acc_stop — причина стопа) переходят вместе с карточкой: восстановленная карточка исполняет
# ТУ ЖЕ операцию, а не чеканит новую. Поля есть только у карточек, рождённых при ручках, — без них раздела нет вовсе,
# и файл по виду — файл 947953e.
# RC2010 (Codex TB-CHECK-2010-0742 Q1): km_src — метка происхождения пробега карточки ("text": km из текста
# сотрудника). Положительная: её отсутствие значит «не доказано», поэтому потеря раздела (незнакомая версия, файл
# 947953e) ведёт к переспросу числа, а не к закрытию с непроверенным km. Поле добавлено в раздел ВЕРСИИ 1, а не новой
# версией: раздел родился в срезе 7d62aae и живёт только в кандидате rc-2010, точка отката — 947953e, раздела не
# читающий. Читатель кандидата без этого поля (0e5cb84) такой файл отверг бы целиком — точкой отката он не является;
# после выпуска правило шапки действует: новое поле раздела — новая версия раздела.
CLOSE_EXT_KEYS = ("km_photo", "due_total", "acc_op", "acc_bid", "acc_brow", "acc_ds", "acc_crow", "acc_parts",
                  "acc_stop", "km_src")
EXT_KEYS = {KIND_INTAKE: (), KIND_HANDOVER: (), KIND_CLOSE: CLOSE_EXT_KEYS}

_SCALAR = (str, int, float, bool, type(None))


def _simple(v):
    """JSON-простое значение: скаляр или список скаляров. Прочее (объекты, словари) — не передаётся."""
    if isinstance(v, _SCALAR):
        return True
    return isinstance(v, (list, tuple)) and all(isinstance(x, _SCALAR) for x in v)


def select(intake, handovers, closes):
    """Словари процесса → список записей передачи. Только ждущие статусы, только белый список полей (записи и раздела
    `ext` — здесь вместе: делит их `pack`, сводит обратно `verify`, поэтому перенос carry видит запись целиком)."""
    out = []
    for kind, store in ((KIND_INTAKE, intake), (KIND_HANDOVER, handovers), (KIND_CLOSE, closes)):
        for chat_id in sorted((store or {}), key=str):
            d = store[chat_id]
            if not isinstance(d, dict) or d.get("status") != WAITING[kind] or not isinstance(chat_id, int):
                continue
            data = {}
            for k in KEYS[kind] + EXT_KEYS[kind]:
                if k in d and _simple(d[k]):
                    data[k] = list(d[k]) if isinstance(d[k], tuple) else d[k]
            out.append({"kind": kind, "chat_id": chat_id, "data": data})
    return out


def _canon(entries):
    return json.dumps(entries, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(body):
    """sha256 канонического вида ВСЕГО тела передачи (версия, когда, кем, число, записи). Не одних записей: процесс,
    переписавший то же содержимое при своей штатной остановке, обязан дать НОВЫЙ отпечаток — иначе метка его же
    восстановления совпала бы, и следующий старт молча пропустил бы карточку, ждущую через два рестарта (приёмка C7)."""
    return hashlib.sha256(_canon(body).encode("utf-8")).hexdigest()


def _body(obj):
    return {k: obj.get(k) for k in ("version", "written_at", "pid", "count", "entries")}


def _ext_body(sec):
    return {k: sec.get(k) for k in ("version", "of", "entries")}


def _split(entries):
    """Записи процесса → (записи в белом списке 947953e, записи раздела `ext`). Входные записи не меняются: их же
    держит carry процесса. Поле вне обоих списков остаётся в записи — verify отвергнет его, как и раньше."""
    base, ext = [], []
    for e in entries:
        if not isinstance(e, dict) or not isinstance(e.get("data"), dict):
            base.append(e)                       # не того вида — как есть: verify скажет «не того вида»
            continue
        xk = EXT_KEYS.get(e.get("kind"), ()) if isinstance(e.get("kind"), str) else ()
        data = e["data"]
        base.append(dict(e, data={k: v for k, v in data.items() if k not in xk}))
        x = {k: data[k] for k in xk if k in data}
        if x:
            ext.append({"kind": e.get("kind"), "chat_id": e.get("chat_id"), "data": x})
    return base, ext


def pack(entries, *, written_at, pid):
    """Тело файла передачи: версия, когда и кем записано, записи и sha256 всего тела. Записи — в белом списке 947953e;
    поля сверх него — разделом `ext` со своей суммой и привязкой к сумме тела (`of`). Раздела нет, если полей сверх
    списка нет ни у одной записи: тогда файл тот же, что пишет 947953e."""
    base, ext = _split(entries)
    obj = {"version": VERSION, "written_at": written_at, "pid": pid, "count": len(base), "entries": base}
    obj["sha256"] = digest(obj)
    if ext:
        sec = {"version": EXT_VERSION, "of": obj["sha256"], "entries": ext}
        sec["sha256"] = digest(sec)
        obj["ext"] = sec
    return obj


def _ext_of(obj, entries):
    """Раздел `ext` проверенного тела → ({(вид, chat_id): поля}, причина) | (None, причина). Раздела нет — пусто;
    незнакомая версия — пусто (карточки идут без его полей: так же его не видит и 947953e). Своя версия, но сумма,
    привязка к телу, вид, белый список или место записи не сошлись — файл не наш: None, как у записи вне контракта."""
    if "ext" not in obj:
        return {}, "ok"
    sec = obj.get("ext")
    if not isinstance(sec, dict):
        return None, "раздел ext не словарь"
    if sec.get("version") != EXT_VERSION:
        return {}, "ok: раздел ext версии %r не прочитан — карточки без его полей" % (sec.get("version"),)
    if sec.get("of") != obj.get("sha256"):
        return None, "раздел ext — от другого тела передачи"
    if sec.get("sha256") != digest(_ext_body(sec)):
        return None, "контрольная сумма раздела ext не сошлась"
    rows = sec.get("entries")
    if not isinstance(rows, list):
        return None, "в разделе ext нет списка записей"
    places = {(e["kind"], e["chat_id"]): e["data"] for e in entries}
    out = {}
    for x in rows:
        if not isinstance(x, dict) or x.get("kind") not in KINDS or not isinstance(x.get("chat_id"), int) \
                or isinstance(x.get("chat_id"), bool) or not isinstance(x.get("data"), dict) or not x["data"]:
            return None, "запись раздела ext не того вида"
        kind, place = x["kind"], (x["kind"], x["chat_id"])
        if place not in places:
            return None, "запись раздела ext без своей карточки (%s)" % kind
        if place in out:
            return None, "две записи раздела ext на одно место (%s)" % kind
        if set(x["data"]) - set(EXT_KEYS[kind]) or not all(_simple(v) for v in x["data"].values()):
            return None, "в разделе ext поле вне белого списка (%s)" % kind
        if set(x["data"]) & set(places[place]):
            return None, "поле и в записи, и в разделе ext (%s)" % kind
        out[place] = x["data"]
    return out, "ok"


def verify(obj):
    """→ (записи | None, причина). Не та версия, не тот вид, не сошлась сумма или запись вне контракта → None.
    Записи возвращаются ЦЕЛИКОМ — с полями раздела `ext` (`_ext_of`). Поля `EXT_KEYS` прямо в записи (так писал код
    08e2ead…fbd0a22) тоже принимаются: читатель терпимее писателя, а писатель кладёт их только в раздел."""
    if not isinstance(obj, dict):
        return None, "файл не словарь"
    if obj.get("version") != VERSION:
        return None, "версия %r, ожидалась %d" % (obj.get("version"), VERSION)
    entries = obj.get("entries")
    if not isinstance(entries, list):
        return None, "нет списка записей"
    if obj.get("count") != len(entries):
        return None, "число записей %r не равно %d" % (obj.get("count"), len(entries))
    if obj.get("sha256") != digest(_body(obj)):
        return None, "контрольная сумма не сошлась"
    seen = set()
    for e in entries:
        if not isinstance(e, dict) or e.get("kind") not in KINDS or not isinstance(e.get("chat_id"), int) \
                or isinstance(e.get("chat_id"), bool) or not isinstance(e.get("data"), dict):
            return None, "запись не того вида"
        data, kind = e["data"], e["kind"]
        if data.get("status") != WAITING[kind]:
            return None, "запись не в ждущем статусе (%s)" % kind
        if set(data) - set(KEYS[kind]) - set(EXT_KEYS[kind]) or not all(_simple(v) for v in data.values()):
            return None, "в записи поле вне белого списка (%s)" % kind
        if (kind, e["chat_id"]) in seen:
            return None, "две записи на одно место (%s)" % kind
        seen.add((kind, e["chat_id"]))
    ext, why = _ext_of(obj, entries)
    if ext is None:
        return None, why
    if not ext:
        return entries, why
    return [dict(e, data=dict(e["data"], **ext[(e["kind"], e["chat_id"])])) if (e["kind"], e["chat_id"]) in ext
            else e for e in entries], why


def decide(handoff_sha, marker):
    """Применять ли передачу. Метка применения с ТЕМ ЖЕ sha = ЭТОТ ЖЕ файл уже применил прежний процесс: он мог закрыть
    карточку и упасть без новой передачи — повторное применение оживило бы завершённое. Тогда — нет; иначе — да.
    Штатная остановка всегда пишет НОВЫЙ файл с новым sha (время и pid в теле), поэтому ждущая карточка переходит дальше."""
    if isinstance(marker, dict) and marker.get("sha256") == handoff_sha:
        return False, "уже применена процессом %s" % marker.get("pid")
    return True, "ok"


def plan(entries, intake, handovers, closes):
    """→ (что вписать, счётчики). Только в ПУСТЫЕ места: занятое место процесса не трогается и считается конфликтом."""
    stores = {KIND_INTAKE: intake, KIND_HANDOVER: handovers, KIND_CLOSE: closes}
    todo, counts = [], {KIND_INTAKE: 0, KIND_HANDOVER: 0, KIND_CLOSE: 0, "conflict": 0}
    for e in entries:
        store = stores[e["kind"]]
        if e["chat_id"] in store:
            counts["conflict"] += 1
            continue
        todo.append((store, e["chat_id"], json.loads(json.dumps(e["data"]))))   # своя копия значений
        counts[e["kind"]] += 1
    return todo, counts


def occupied(intake, handovers, closes):
    """Места (вид, chat_id), занятые в памяти процесса ЛЮБОЙ записью — до фильтра статуса. Закрытая (booked) или
    неизвестная (write_unknown) карточка тоже занимает место: перенос старой карточки на него оживил бы её (Codex
    TB-REL-5EC1F65-STOP-1610-1342, п.1)."""
    out = set()
    for kind, store in ((KIND_INTAKE, intake), (KIND_HANDOVER, handovers), (KIND_CLOSE, closes)):
        out.update((kind, chat_id) for chat_id in (store or {}))
    return out


def merge(current, carry, taken):
    """Записи текущей памяти (только ждущие) + перенесённые из неприменённой (проверенной) передачи — ТОЛЬКО на места,
    которых нет в памяти процесса вовсе (`taken` = `occupied(...)`, любой статус). Текущее сильнее всегда."""
    have = set(taken) | {(e["kind"], e["chat_id"]) for e in current}
    return list(current) + [e for e in (carry or []) if (e["kind"], e["chat_id"]) not in have]


def apply(todo):
    """Вписать запланированное. Только присваивание в словари — ни сообщений, ни действий."""
    for store, chat_id, data in todo:
        store[chat_id] = data
