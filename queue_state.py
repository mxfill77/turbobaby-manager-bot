#!/usr/bin/env python3
"""СЛЕПОК СОСТОЯНИЯ ОЧЕРЕДИ ДЛЯ МОЗГА (14.08.2026). Чистая функция: «факты → писать ли и чем».

ПОВОД (решение владельца 14.08). Владелец не должен быть проводом между Штабом и системой.
Штаб читает мозг сам, но СОСТОЯНИЯ очереди там нет: в журнал попадает только ИТОГ задачи, а
между «взял» и «сдал» — пустота. За трое суток из этой пустоты родились четыре дубля:
отправитель не видел, что задача уже идёт или уже закрыта. У исполнителя защита от повтора
есть, у Штаба её нет — и появиться ей неоткуда, пока состояние не написано там, куда он смотрит.

ЧТО ЗДЕСЬ РЕШАЕТСЯ, А ЧТО НЕ РЕШАЕТСЯ. Здесь — ТРИ вопроса: сменилось ли состояние (то есть
стоит ли вообще писать), каким текстом состояние выглядит и что стало с задачей, ушедшей из
открытых. Здесь НЕ решается ничего про сами задачи: очередь не трогается ни одним вызовом —
у модуля нет ни сети, ни файлов, ни времени (импорт РОВНО ОДИН — `datetime`, и только ради
меток UTC; страж QUEUE_STATE_PURE в invariants_check.py, ast, в гейте).

ПОЧЕМУ ПО СМЕНЕ СОСТОЯНИЯ, А НЕ КАЖДЫЙ ТИК. ЗАМЕР (реплей живым кодом, 15 суток 30.07–14.08,
источники — живой снимок очереди и METRICS-строки журнала демона): 1174 события, но тактов, в
которых состояние менялось, — 885, то есть **59.0 записи в сутки**; 289 событий схлопнулись,
попав в один такт с соседом. Запись каждый тик дала бы **1440 записей в сутки** — в 22 раза
больше, и поиск по теме в журнале мозга перестал бы работать в тот же день.

ПОЧЕМУ ОТПЕЧАТОК НЕ ВКЛЮЧАЕТ ЗАКРЫТЫЕ. Слепок — ФОТОГРАФИЯ с названным временем, а не живая
лента: «закрыто за сутки» верно НА МОМЕНТ СНЯТИЯ, и это написано в самом разделе. Включи мы
список закрытых в отпечаток — каждое старение записи за 24 ч рождало бы отдельную запись ни о
чём (+31 в сутки на нынешнем темпе). Уход задачи из открытых отпечаток и так меняет: строка
исчезла из карты «id → статус».

ЗАМОК: СЛЕПОК НЕ ВРЁТ СВЕЖЕСТЬЮ. Исходов ТРИ, а не два (тот же замок против ложного зелёного,
что у кассы `balance_fact`, у О3 и у `scan_result`):
  · СВЕРЕНО — очередь прочитана, в шапке стоит время снятия;
  · НЕ СВЕРЕНО, прошлое есть — очередь прочитать не удалось: шапка говорит это прямо, называет
    ПРИЧИНУ и АБСОЛЮТНОЕ время последнего верного снимка, а ниже лежит ТОТ снимок с пометкой,
    что по нему нельзя решать «свободно/занято»;
  · НЕ СВЕРЕНО, прошлого нет — печатаем незнание и НИ ОДНОЙ строки состояния: пустой список
    читался бы как «очередь пуста», а это ложь громче молчания (правило кассы, 13.08).
Все времена в слепке АБСОЛЮТНЫЕ. Замороженный в документе относительный возраст («2 ч назад»)
сам стал бы той же ложью о свежести, ради которой замок и написан: возраст стареет вместе с
документом, а метка UTC — нет. Единственное исключение названо в самом тексте — возраст строк
внутри разделов, и он подписан «на момент снятия».
"""
import datetime

FORM = "3"                      # версия формы слепка: сменилась → первый же прогон перепишет док
#   "3" (19.08.2026) — у упавшей строки появилась строка «ОТВЕТ ВНЕШНЕЙ СИСТЕМЫ, дословно».
#   Форму поднимают ИМЕННО затем, что карта строк при этом не меняется: без метки документ так и
#   остался бы с прежним текстом, где чужих слов нет, — то есть врал бы полнотой.
TAG = "СОСТОЯНИЕ ОЧЕРЕДИ"
DOC_KEY = "queue_state"         # ключ манифеста мозга: read_doc(name=queue_state)
UNVERIFIED_FP = "не-сверено"    # отпечаток ветки «очередь не прочитана» — один на весь отказ

OPEN_STATUSES = ("new", "in_progress", "needs_approval", "approved")
WORKING = ("in_progress",)
WAITING_OWNER = ("needs_approval", "approved")
QUEUED = ("new",)

KEEP_SEC = 172800.0             # сколько держать закрытую задачу в реестре (48 ч), показываем 24 ч
SHOW_SEC = 86400.0              # окно раздела «закрыто за сутки»
CLOSED_FLOOR_SEC = 3600.0       # предел старения реестра закрытых, если закрытий не случалось
HEAD_MAX = 90                   # сколько символов первой строки цели показываем
WHY_MAX = 160                   # сколько символов причины падения показываем
# Дословный ответ внешней системы (19.08.2026). Он НЕ заменяет строку «почему» и не режет её:
# идёт ОТДЕЛЬНОЙ строкой рядом. Причина падения — наш разбор, а это чужие слова, и путать их
# нельзя: по ним владелец отличает перегрузку сервера от кончившегося способа оплаты, а сама
# система их не различает (см. failure_text.py). Снимает строку тот, у кого тело ЦЕЛОЕ, —
# `expectations_run._failed_row`; сюда она приезжает готовой полем `ext`.
EXT_MAX = 200                   # тот же потолок, что у failure_text.TEXT_MAX и у показа О8

_STATUS_RU = {"in_progress": "в работе", "needs_approval": "ждёт «да»",
              "approved": "одобрено, ждёт исполнения", "new": "стоит в очереди"}


# ─────────────────────────────── мелкая арифметика (без часов) ───────────────────────────────
def utc(ts):
    """Эпоха → «2026-08-14 11:23:07 UTC». Своих часов у модуля нет: «сейчас» приносят руки."""
    try:
        t = datetime.datetime.fromtimestamp(float(ts), datetime.timezone.utc)
    except (TypeError, ValueError, OSError, OverflowError):
        return "время неизвестно"
    return t.strftime("%Y-%m-%d %H:%M:%S UTC")


def age(sec):
    """«17 мин» / «3 ч 04 мин» / «1 сут 10 ч». Ноль дробей: слепок читают с телефона."""
    try:
        s = max(0, int(float(sec)))
    except (TypeError, ValueError):
        return "возраст неизвестен"
    d, rest = divmod(s, 86400)
    h, rest = divmod(rest, 3600)
    m = rest // 60
    if d:
        return "%d сут %d ч" % (d, h)
    if h:
        return "%d ч %02d мин" % (h, m)
    return "%d мин" % m


def head(text):
    """ПЕРВАЯ СТРОКА цели — та, по которой отправитель узнаёт свою задачу. Пусто → так и скажем."""
    for line in str(text or "").splitlines():
        line = line.strip()
        if line:
            return line[:HEAD_MAX] + ("…" if len(line) > HEAD_MAX else "")
    return "(цель пуста)"


def _with_ext(rec, row):
    """Дописать записи реестра ДОСЛОВНЫЙ ответ внешней системы, если он у строки есть.

    Своего разбора здесь нет ни одной буквы: поле приходит готовым от того, кто держал тело
    ЦЕЛЫМ (тут его уже урезали). Нет поля — запись БАЙТ-В-БАЙТ прежняя, и это и есть ответ
    отрицательного теста (б): наша причина ничего не приобретает и внешней не притворяется."""
    ext = str((row or {}).get("ext") or "").strip()
    if ext:
        rec["ext"] = ext[:EXT_MAX]
    return rec


def lane_of(row):
    """Полоса строки. Пустая ячейка = vps — то же правило, что у моста (`queueLane_`)."""
    return str((row or {}).get("lane") or "vps").strip() or "vps"


def _rid(row):
    return str((row or {}).get("id") or "").strip()


# ─────────────────────────────── отпечаток состояния ───────────────────────────────
def fingerprint(rows, seeded=False):
    """Карта «полоса·номер·статус» открытых строк → строка сравнения. Порядок не важен, поэтому
    сортируем: перестановка строк в ответе моста сменой состояния НЕ является.

    В отпечаток входят ещё два факта О САМОМ ДОКУМЕНТЕ, и оба по одной причине: отпечаток
    сторожит не только очередь, но и то, ЧТО НАПЕЧАТАНО. Сменилась ФОРМА (`FORM`) или реестр
    закрытых стал полным (`seeded`) — текст изменится, а карта строк может остаться прежней, и
    без этих меток документ так и остался бы с прежней, уже неверной, фразой."""
    parts = []
    for r in (rows or []):
        rid = _rid(r)
        if not rid:
            continue
        parts.append("%s·%s·%s" % (lane_of(r), rid, str(r.get("status") or "?")))
    return "v%s%s|%s" % (FORM, "s" if seeded else "", ";".join(sorted(parts)))


# ─────────────────────────────── реестр закрытых ───────────────────────────────
def needs_closed(prev_open, rows, closed_at, now, floor=CLOSED_FLOOR_SEC):
    """Нужно ли в ЭТОМ прогоне спрашивать мост про упавшие задачи.

    Дорогой вопрос задаётся не «на всякий случай», а по факту: (1) реестра нет вовсе;
    (2) строка, которую мы видели открытой, из открытых ушла — значит закрылась, и мы обязаны
    узнать ЧЕМ; (3) реестр старше предела (`floor`) — тогда обновим, раз уж пишем.
    ЗАМЕР цены: ответ моста на `failed` обеих полос — 301 КБ; на `done,failed` — 2745 КБ,
    поэтому спрашиваем ТОЛЬКО упавших, а «закрыто» выводим из своего наблюдения."""
    if closed_at is None:
        return True
    seen = {_rid(r) for r in (rows or []) if _rid(r)}
    for rid in (prev_open or {}):
        if str(rid) not in seen:
            return True
    try:
        return (float(now) - float(closed_at)) >= float(floor)
    except (TypeError, ValueError):
        return True


def needs_seed(since):
    """Засевался ли реестр хоть раз. Реестр строится ИЗ НАБЛЮДЕНИЯ (кто ушёл из открытых), а
    наблюдение начинается с первого прогона — значит без засева раздел «закрыто за сутки» на
    первые сутки жизни был бы ПУСТ ПРИ 26 РЕАЛЬНО ЗАКРЫТЫХ (живой случай 14.08 11:24). Пустой
    раздел читался бы как «ничего не закрылось» — тот самый ложный нуль, против которого
    написан весь модуль. Поэтому один раз платим дорогой вопрос (2745 КБ на 14.08) и знаем
    сутки целиком; дальше реестр ведётся наблюдением и дорогой вопрос не повторяется."""
    return since is None


def seed(closed_rows, now, window=SHOW_SEC):
    """Разовый засев реестра из закрытых строк очереди → записи за окно. Исход берётся из
    СТАТУСА строки: тут гадать не о чем, очередь его и хранит."""
    out = []
    for r in (closed_rows or []):
        rid = _rid(r)
        at = r.get("at")
        try:
            at = float(at)
        except (TypeError, ValueError):
            continue
        if not rid or (float(now) - at) > float(window):
            continue
        fell = str(r.get("status") or "") == "failed"
        rec = {"id": rid, "lane": lane_of(r), "head": head(r.get("task_text")),
               "at": at, "outcome": "упала" if fell else "сдана",
               "why": head(r.get("result"))[:WHY_MAX] if fell else ""}
        out.append(_with_ext(rec, r) if fell else rec)
    out.sort(key=lambda r: float(r.get("at") or 0), reverse=True)
    return out


def ledger(prev_gone, prev_open, rows, failed, now, keep=KEEP_SEC):
    """Реестр закрытых: что ушло из открытых и ЧЕМ кончилось. → новый список записей.

    ИСХОД ЗАДАЧИ УЗНАЁТСЯ БЕЗ ДОРОГОГО ВОПРОСА: строка ушла из открытых → она закрыта (иных
    терминальных статусов у очереди нет); нашлась среди упавших → `упала` и причина оттуда;
    не нашлась, а список упавших у нас на руках → `сдана`. Списка упавших нет (мост не ответил
    или его не спрашивали) → исход `не сверен`, и он так и назван: выдать незнание за «сдана»
    значило бы спрятать падение — ровно то, ради чего раздел и заведён.

    ПАДЕНИЕ, КОТОРОГО МЫ НЕ ВИДЕЛИ ОТКРЫТЫМ, тоже попадает в реестр — из самого списка упавших
    (задача может родиться и упасть между двумя прогонами наблюдателя)."""
    out = []
    known = set()
    for rec in (prev_gone or []):
        rid = str((rec or {}).get("id") or "")
        if not rid or rid in known:
            continue
        try:
            if (float(now) - float(rec.get("at") or 0)) > float(keep):
                continue
        except (TypeError, ValueError):
            continue
        known.add(rid)
        out.append(dict(rec))

    fmap = {}
    for f in (failed or []):
        rid = _rid(f)
        if rid:
            fmap[rid] = f

    seen = {_rid(r) for r in (rows or []) if _rid(r)}
    for rid, was in (prev_open or {}).items():
        rid = str(rid)
        if rid in seen or rid in known:
            continue
        was = was if isinstance(was, dict) else {}
        f = fmap.get(rid)
        if f is not None:
            outcome, why = "упала", head(f.get("result"))[:WHY_MAX]
        elif failed is None:
            outcome, why = "не сверен", ""
        else:
            outcome, why = "сдана", ""
        known.add(rid)
        rec = {"id": rid, "lane": str(was.get("lane") or "vps"),
               "head": str(was.get("head") or head(was.get("text"))),
               "at": float(now), "outcome": outcome, "why": why}
        out.append(_with_ext(rec, f))

    for rid, f in fmap.items():          # упавшие, которых наблюдатель открытыми не застал
        if rid in known:
            continue
        at = f.get("at")
        try:
            at = float(at)
        except (TypeError, ValueError):
            continue
        if (float(now) - at) > float(keep):
            continue
        known.add(rid)
        out.append(_with_ext({"id": rid, "lane": lane_of(f), "head": head(f.get("task_text")),
                              "at": at, "outcome": "упала",
                              "why": head(f.get("result"))[:WHY_MAX]}, f))

    out.sort(key=lambda r: float(r.get("at") or 0), reverse=True)
    return out


def open_map(rows):
    """Открытые строки → память для следующего прогона (что мы видели и как оно называлось)."""
    m = {}
    for r in (rows or []):
        rid = _rid(r)
        if rid:
            m[rid] = {"lane": lane_of(r), "status": str(r.get("status") or ""),
                      "head": head(r.get("text"))}
    return m


# ─────────────────────────────── тело слепка ───────────────────────────────
def _rows_of(rows, statuses):
    out = [r for r in (rows or []) if str((r or {}).get("status") or "") in statuses]
    out.sort(key=lambda r: (lane_of(r), -_num(r.get("id"))))
    return out


def _num(v):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return 0


def _line(r, now):
    since = r.get("since")
    a = age(float(now) - float(since)) if since not in (None, "") else "возраст неизвестен"
    return "  %-3s · #%s · %s · %s · %s" % (lane_of(r), _rid(r) or "?",
                                            _STATUS_RU.get(str(r.get("status")), str(r.get("status"))),
                                            a, head(r.get("text")))


def _section(title, rows, now, empty):
    body = [title]
    if not rows:
        body.append("  %s" % empty)
    else:
        body += [_line(r, now) for r in rows]
    return body


def body(rows, gone, now, closed_at=None, lane="VPS", since=None):
    """Тело слепка: что в работе, что ждёт владельца, что стоит, что закрылось за сутки.

    `since` — с какого момента раздел закрытых ПОЛОН. Он не украшение: реестр знает ровно то,
    что наблюдал, и пустой раздел обязан отличаться от «ничего не закрылось» ровно так же, как
    у надзора «тиков не было» отличается от «не разобрал» (205c00b), а у кассы «не сверено» от
    нуля. Не полон → так и сказано, и «за сутки не закрылось ничего» НЕ печатается вовсе."""
    work = _rows_of(rows, WORKING)
    wait = _rows_of(rows, WAITING_OWNER)
    queued = _rows_of(rows, QUEUED)
    out = []
    out += _section("В РАБОТЕ (%d):" % len(work), work, now,
                    "никто не работает — обе полосы свободны")
    out.append("")
    out += _section("ЖДЁТ ВЛАДЕЛЬЦА (%d):" % len(wait), wait, now,
                    "владельца никто не ждёт")
    out.append("")
    out += _section("СТОИТ В ОЧЕРЕДИ (%d):" % len(queued), queued, now,
                    "очередь пуста")
    out.append("")

    fresh = []
    for rec in (gone or []):
        try:
            if (float(now) - float(rec.get("at") or 0)) <= SHOW_SEC:
                fresh.append(rec)
        except (TypeError, ValueError):
            continue
    fell = [r for r in fresh if r.get("outcome") == "упала"]
    unsure = [r for r in fresh if r.get("outcome") == "не сверен"]
    done = [r for r in fresh if r.get("outcome") == "сдана"]
    try:
        full = since is not None and (float(now) - float(since)) >= SHOW_SEC
    except (TypeError, ValueError):
        full = False
    out.append("ЗАКРЫТО ЗА СУТКИ — на момент снятия (%d: сдано %d, упало %d, исход не сверен %d):"
               % (len(fresh), len(done), len(fell), len(unsure)))
    if not full:
        out.append("  ⚠️ СПИСОК НЕ ПОЛОН: сданные известны только с %s — раньше этого момента"
                   % (utc(since) if since is not None else "начала наблюдения (ещё не начато)"))
        out.append("     наблюдения не было, и о закрытых до него этот файл НЕ ЗНАЕТ.")
    if not fresh:
        out.append("  за сутки не закрылось ничего" if full else
                   "  из известного наблюдателю — ничего")
    else:
        if done:
            out.append("  сдано: " + " ".join("#%s" % r.get("id") for r in done))
        for r in fell:
            out.append("  УПАЛА · %s · #%s · %s · %s" % (str(r.get("lane") or "vps"),
                                                         r.get("id"), utc(r.get("at")),
                                                         r.get("head")))
            out.append("      почему: %s" % (r.get("why") or "причина не записана"))
            # ДОСЛОВНО И ОТДЕЛЬНОЙ СТРОКОЙ. Строка «почему» — НАШ разбор (её первые слова обычно
            # пересказ думателя), а это слова ЧУЖИЕ, и в одну строку их сводить нельзя. Показ тот
            # же, что у О8 («внешняя система ответила дословно: «…»»): один факт — один вид.
            if r.get("ext"):
                out.append("      ОТВЕТ ВНЕШНЕЙ СИСТЕМЫ, дословно: «%s»" % r.get("ext"))
        for r in unsure:
            out.append("  ИСХОД НЕ СВЕРЕН · %s · #%s · %s · %s"
                       % (str(r.get("lane") or "vps"), r.get("id"), utc(r.get("at")),
                          r.get("head")))
    # УПАВШИЕ ЧИТАЮТСЯ ИЗ САМОЙ ОЧЕРЕДИ, а не из наблюдения, поэтому их половина полна за сутки
    # с первого же прогона — и это сказано отдельно, чтобы неполнота сданных не бросала тень на
    # тех, о ком спрашивали прибор.
    out.append("  (упавшие сверены с очередью %s — эта половина за сутки ПОЛНА)" % utc(closed_at)
               if closed_at is not None else
               "  (упавшие в этом снимке НЕ сверены — исход ушедших задач может быть неточен)")
    return "\n".join(out)


_FOOTER = (
    "ЧТО ЭТО ЗА ФАЙЛ. Слепок состояния очереди Bot Data — СОСТОЯНИЕ, а не история: каждая\n"
    "запись затирает файл целиком, прошлых слепков здесь нет. История — в cc_log.\n"
    "Пишется ПО СМЕНЕ СОСТОЯНИЯ (взял · сдал · упал · ждёт владельца · встал в очередь), а не\n"
    "по таймеру: на нынешнем темпе это ~59 записей в сутки против 1440 при записи каждый тик.\n"
    "Снимает слой ожиданий (expectations.timer, раз в 10 минут) — он живёт ОТДЕЛЬНО от демона\n"
    "и потому видит «в работе» ПОКА задача идёт, а не после её конца.\n"
    "ПЕРЕД ОТПРАВКОЙ ЗАДАЧИ: сверься с временем снятия в шапке. Оно старше 15 минут — считай\n"
    "состояние неизвестным и спроси очередь напрямую, а не по этому файлу."
)


def render(rows, gone, now, closed_at=None, lane="VPS", since=None):
    """ВЕРНЫЙ слепок: шапка со временем снятия + тело + подпись."""
    return "\n".join([
        "%s · слепок, заменяется целиком" % TAG,
        "снято: %s   ← ВОЗРАСТ СЧИТАТЬ ОТ ЭТОГО ВРЕМЕНИ" % utc(now),
        "снял: слой ожиданий, полоса %s · возраст строк ниже — на момент снятия" % lane,
        "",
        body(rows, gone, now, closed_at, lane, since),
        "",
        _FOOTER,
    ])


def render_unverified(prev_text, prev_at, now, why, lane="VPS"):
    """НЕ СВЕРЕНО. Прошлый слепок есть → он показывается ЦЕЛИКОМ, но назван устаревшим и с
    АБСОЛЮТНЫМ временем; прошлого нет → печатаем незнание и НИ ОДНОЙ строки состояния."""
    top = [
        "%s · ⚠️ НЕ СВЕРЕНО" % TAG,
        "попытка снять: %s" % utc(now),
        "почему не вышло: %s" % (str(why or "очередь не прочитана")[:200]),
    ]
    if prev_text:
        top += [
            "последний ВЕРНЫЙ снимок: %s — по нему НЕЛЬЗЯ решать «свободно/занято»,"
            % utc(prev_at),
            "он мог устареть; ниже лежит именно он, слово в слово.",
            "",
            "──────────── ниже — УСТАРЕВШИЙ слепок от %s ────────────" % utc(prev_at),
            "",
            str(prev_text),
        ]
    else:
        top += [
            "верного снимка не было НИ РАЗУ — состояние очереди НЕИЗВЕСТНО.",
            "ни одной строки состояния здесь не печатаем намеренно: пустой список читался бы",
            "как «работы нет», а это ложь громче молчания.",
            "",
            _FOOTER,
        ]
    return "\n".join(top)


# ─────────────────────────────── вердикт ───────────────────────────────
def verdict(prev, queue, gone, now, closed_at=None, lane="VPS", since=None):
    """ФАКТЫ → «писать ли и чем». `prev` — что мы публиковали в прошлый раз (из состояния рук).

    Пишем в ТРЁХ случаях и ни в одном другом: (1) публикации ещё не было; (2) карта открытых
    строк изменилась; (3) состояние перешло между «сверено» и «не сверено». Ничего не менялось →
    write=False, и мост в этом прогоне не трогается вовсе."""
    prev = prev if isinstance(prev, dict) else {}
    queue = queue if isinstance(queue, dict) else {}
    was = prev.get("fp")
    if not queue.get("ok"):
        text = render_unverified(prev.get("text"), prev.get("at"), now, queue.get("err"), lane)
        return {"write": was != UNVERIFIED_FP, "fp": UNVERIFIED_FP, "verified": False,
                "text": text,
                "why": "очередь не прочитана" if was != UNVERIFIED_FP else
                       "очередь не прочитана, о чём уже сказано"}
    rows = queue.get("rows") or []
    fp = fingerprint(rows, since is not None)
    text = render(rows, gone, now, closed_at, lane, since)
    if was is None:
        why = "первая публикация состояния"
    elif was == UNVERIFIED_FP:
        why = "очередь снова читается — состояние сверено"
    elif was != fp:
        why = "состояние сменилось"
    else:
        why = "состояние не менялось"
    return {"write": was is None or was != fp, "fp": fp, "verified": True,
            "text": text, "why": why}
