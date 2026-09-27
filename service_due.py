"""СРОК ЗАМЕНЫ — КИЛОМЕТРАЖ ИЛИ ПОЛГОДА, ЧТО РАНЬШЕ (27.09.2026, задание Штаба 0054-74w, слова владельца).

Слова владельца 27.09: «И кстати срок замены везде километраж или полгода»; про подшипники колёс и
рулевой — «встроить как воздушный фильтр после 20к в обязаловку».

Чистая функция «факты → вердикт срока». Импорт ровно один — `datetime` (даты сравниваются, своих
часов у модуля НЕТ: «сегодня» приносят руки, оттого тест пришпиливает время, а не гоняется за живыми
часами). Ни файлов, ни сети, ни моста.

ДВЕ ОСИ, И У КАЖДОЙ СВОИ ИСХОДЫ:
  • километраж — последняя замена + интервал против текущего пробега (как считал `_mand_line`);
  • время — дата последней замены + `MONTHS` месяцев против сегодняшней даты.
К замене — если ЛЮБАЯ ось сказала «пора». Срок — что РАНЬШЕ.

ДАТЫ НЕТ — «НЕ ИЗМЕРЕНО», А НЕ «ПРОСРОЧЕНО» (прямая буква задания). Дата последней замены сегодня не
хранится ни в одном регистре (Лист1 I–L несут только км; Bot Data «обслуживание» — `updated_at`,
который двигает КАЖДОЕ обновление пробега, а не замена). Поэтому ось времени без даты не судит
ничего и НАЗЫВАЕТ это, а километраж судит, как судил.

ПЕРВАЯ ПРОВЕРКА (подшипники). «После 20 000» читается так: нет записи → первая проверка на
пробеге `first_at`; пробег дошёл → к замене; не дошёл → «ещё N км до первой проверки». Прочие
виды без записи остаются «не делалось» — их правило не менялось.
"""
import datetime as _dt

MONTHS = 6                      # полгода — слова владельца 27.09
FIRST_CHECK = {"bearings": 20000}   # виды с первой проверкой на пробеге (нет записи ≠ «не делалось»)

KM_OK, KM_NOW, KM_OVER, KM_UNKNOWN, KM_NEVER, KM_FIRST = "ok", "now", "over", "unknown", "never", "first"
T_OK, T_OVER, T_UNMEASURED = "ok", "over", "unmeasured"


def _int(x):
    try:
        v = int(str(x).replace(" ", "").replace(",", "").split(".")[0])
    except (ValueError, TypeError):
        return None
    return v


def parse_date(s):
    """Дата из строки: `ГГГГ-ММ-ДД[...]`, `ДД.ММ.ГГГГ[...]`, объект date/datetime. Иначе None."""
    if s is None or s == "":
        return None
    if isinstance(s, _dt.datetime):
        return s.date()
    if isinstance(s, _dt.date):
        return s
    t = str(s).strip()
    for fmt, n in (("%Y-%m-%d", 10), ("%d.%m.%Y", 10)):
        try:
            return _dt.datetime.strptime(t[:n], fmt).date()
        except ValueError:
            continue
    return None


def add_months(d, n):
    """Дата + n месяцев (день прижимается к концу короткого месяца)."""
    m = d.month - 1 + n
    y, m = d.year + m // 12, m % 12 + 1
    last = [31, 29 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 28,
            31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
    return _dt.date(y, m, min(d.day, last))


def verdict(kind, last_km, interval, cur_km, last_date=None, today=None, months=MONTHS):
    """Срок одного вида. → dict:
      km:   ok · now · over · unknown (пробег не прочитан) · never (записи нет) · first (до первой проверки)
      rem:  остаток км (может быть < 0) или None
      nxt:  срок по км или None
      time: ok · over · unmeasured (даты нет / сегодня неизвестно / months=0)
      due_date: дата срока по времени или None
      due:  True — к замене (любая ось сказала «пора»)
    """
    iv = _int(interval)
    last = _int(last_km)
    cur = _int(cur_km)
    first_at = FIRST_CHECK.get(kind)
    out = {"kind": kind, "km": KM_UNKNOWN, "rem": None, "nxt": None, "time": T_UNMEASURED,
           "due_date": None, "due": False, "first": False}
    if not last or last <= 0:
        if first_at and iv:
            out["first"] = True
            out["nxt"] = first_at
            if cur is None:
                out["km"] = KM_UNKNOWN
            else:
                out["rem"] = first_at - cur
                out["km"] = KM_FIRST if cur < first_at else (KM_NOW if cur == first_at else KM_OVER)
        else:
            out["km"] = KM_NEVER
    elif iv:
        out["nxt"] = last + iv
        if cur is None:
            out["km"] = KM_UNKNOWN
        else:
            out["rem"] = out["nxt"] - cur
            out["km"] = KM_OK if out["rem"] > 0 else (KM_NOW if out["rem"] == 0 else KM_OVER)
    d = parse_date(last_date)
    t = parse_date(today)
    if d and t and months and months > 0 and not out["first"] and out["km"] != KM_NEVER:
        out["due_date"] = add_months(d, int(months))
        out["time"] = T_OVER if t >= out["due_date"] else T_OK
    out["due"] = out["km"] in (KM_NOW, KM_OVER) or out["time"] == T_OVER
    return out


def fmt_date(d):
    return d.strftime("%d.%m.%Y") if d else ""


def time_words(v, months=MONTHS):
    """(th, ru) — строка оси времени для карточки; пусто, если ось не к месту (нет записи вовсе)."""
    if v.get("first") or v.get("km") == KM_NEVER:
        return "", ""
    if v.get("time") == T_OVER:
        dd = fmt_date(v.get("due_date"))
        return (f"ครบ {months} เดือนแล้ว ({dd})", f"прошло {months} мес. (срок {dd})")
    if v.get("time") == T_OK:
        dd = fmt_date(v.get("due_date"))
        return (f"หรือภายใน {dd}", f"или до {dd}")
    return ("ตามเวลา: ยังไม่ได้วัด (ไม่มีวันที่เปลี่ยน)", "по времени: не измерено (даты замены нет)")
