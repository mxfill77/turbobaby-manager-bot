"""service_debt.py — ДОЛГ ПРИНЯТОЙ РАБОТЫ: чистое решение «факты → вердикт».

ЗАЧЕМ. Работа, которую человек объявил сделанной, до 23.08.2026 оставляла след ровно там, где её
записать НЕЛЬЗЯ (пробега нет → заявка `ждёт_факт`), и НЕ оставляла там, где записать можно сейчас
же (пробег есть → показали кнопку и всё). Носителей у такой работы было два, и оба нестойкие:
токен в памяти процесса (`_SVC_TOKENS`, потолок 200, рестарт стирает) и текст сообщения с кнопкой
(его удаляет `_clear_cycle_msgs` на ближайшем терминале другого цикла). Кнопку не нажали — работа
исчезала без единой строки. Живой доказанный случай — NMAX 155 GREY 5960 от 01.08: карточка
подтверждения ушла в 08:06:40, **принято 2 позиции, записано 0**, а к 22.08 самой заявки уже не
существовало (`docs/artifacts/2026-08-22-service-5960-fate.md`, `tok=18`).

ИМПОРТОВ РОВНО НОЛЬ. И «сейчас», и расписку моста, и перечитанную клетку, и пороги приносят руки
(`splinter._sp_debt_open`, `splinter._sp_debt_close`, `splinter.scheduled_service_pending_reminder`).
Будь у решения сеть — оно спросило бы мост САМО, и «записано ли» снова зависело бы от того, КАК
спросили, а не от расписки той самой записи; будь у него запись — рядом с долгом завёлся бы второй
путь в Лист1 мимо «да» доверенного. Страж `SERVICE_DEBT_PURE` (ast, в гейте) это доказывает.

ТРИ ИСХОДА, А НЕ ДВА (канон проекта — О3, `write_fact`, `scan_result`): **висит · закрыт ·
неизвестно**. Третий не запасной и не вежливый синоним закрытия: «проверить не удалось» ≠
«записано». Молчание о долге допускается ТОЛЬКО там, где закрытие ДОКАЗАНО; во всех прочих случаях
долг остаётся видимым. Направление сомнения обратно гарду и намеренно: гард решает, исполнится ли
команда, а здесь решается, УЗНАЕТ ли человек о потерянной работе, — поэтому дырка в фактах не
гасит долг, а оставляет его висеть с честной пометкой.

ЗАКРЫТИЕ РОВНО ПО ТРЁМ ПРИЗНАКАМ, и все три — ответ мира, а не наше намерение:

  1. `BY_WRITE`  — **доказанная запись**: расписка моста сказала `ok`, либо расписки не было и факт
     перечитан (`write_fact`), и клетка показала нашу величину. Намерение записать признаком не
     является: `written.append(k)` без ответа мира долг не закрывает.
  2. `BY_CELL`   — **перечитанная клетка регистра**: в Лист1 стоит величина НЕ МЕНЬШЕ той, с которой
     работа обязана лечь. Это ловит запись мимо бота (владелец внёс рукой). Долг снят ПО ФАКТУ, а
     не по времени — тот же приём, что у `curator_state` и второго окна `deliver_card`.
  3. `BY_HUMAN`  — **явное решение человека**: «работы не было» / «не надо» / закрыл рукой. Человек
     здесь авторитет, а не свидетель, поэтому доказательства сверх его слов не требуется.

ДОЛГ ПРИВЯЗАН К ПОЗИЦИИ, А НЕ К БАЙКУ (23.08.2026, шесть дыр ревизии `930da84`). Признаки решают,
ЗАКРЫТ ли долг; `settle` решает, ЧЬЯ строка и КАКАЯ ИМЕННО позиция гаснет. Разбор — в шапке секции
«ПОЗИЦИОННЫЙ СЛЕД» ниже; коротко: строка «то_заявки» одна на пару тема × байк, поэтому следующий
визит того же байка затирал висящий долг соседа, партия из двух позиций гасла по первой записи,
безусловное закрытие дописывало строку-эхо и гасило чужую открытую строку.

ПО ТАЙМЕРУ ДОЛГ НЕ ГАСНЕТ НИКОГДА, И ЭТО УСТРОЙСТВО, А НЕ ОБЕЩАНИЕ: у `verdict()` параметра
возраста НЕТ ВОВСЕ — передать его физически некуда, поэтому «повисел и рассосался» невыразимо в
этом модуле. Возраст живёт в `voice()`, а `voice()` не умеет вернуть ни один из `CLOSERS`: старый
долг может стать только ГРОМЧЕ, но не тише. Обе границы проверяются тестом по исходнику, а не
доверием к докстрингу.

ЧТО СЧИТАЕТСЯ ПРИНЯТОЙ РАБОТОЙ (замер, а не вкус). За 83 суток `splinter.log` знает 129 прогонов
ТО-трекера, из них `due/overdue` — 55, а записей масла — 8. Заводить долг на КАЖДОМ показе кнопки
масла значило бы получить до 55 долгов, из которых ≥47 висели бы по работе, которую НИКТО не
заявлял: байку просто пришёл срок, а человек прислал фото приборки. Сторож, который держит всегда,
не лучше того, который не держит никогда. Поэтому `accepted()` требует ЗАЯВКИ: у двери столбца это
названная работа (`works`), у двери масла — маркер «замена СДЕЛАНА» (`_is_oil_done_marker`), а не
сам факт срока.
"""

FLAG_ENV = "SERVICE_DEBT"          # ручка отката: `SERVICE_DEBT=0` + рестарт splinter

# Статус строки листа «то_заявки», который И ЕСТЬ долг. Нового терминала не заводим намеренно:
# `ждёт_подтверждения` уже означает «работа принята, записи нет» — второй словарь состояний
# разошёлся бы с мостом молча (мост знает ровно заявлено|ждёт_факт|ждёт_подтверждения|закрыто).
STATUS = "ждёт_подтверждения"

# --- исходы долга -----------------------------------------------------------------------------
OPEN = "висит"
CLOSED = "закрыт"
UNKNOWN = "неизвестно"
STATES = (OPEN, CLOSED, UNKNOWN)

# --- признаки закрытия: РОВНО ТРИ ------------------------------------------------------------
BY_WRITE = "запись"
BY_CELL = "клетка"
BY_HUMAN = "человек"
CLOSERS = (BY_WRITE, BY_CELL, BY_HUMAN)

# --- громкость (это НЕ закрытие; см. voice) ---------------------------------------------------
QUIET = "тихо"
REMIND = "напомнить"
ESCALATE = "эскалация"
VOICES = (QUIET, REMIND, ESCALATE)

# --- кому адресовано ---------------------------------------------------------------------------
# Механик своё сделал: работа названа, кнопка показана. Не нажали её Пым/владелец — значит и
# спрашивать надо их, а не гонять механика «отпишись» по работе, о которой он уже отписался.
TO_MECHANIC = "механик"
TO_KEEPER = "Пым/владелец"
TO_OWNER = "владелец"

# --- двери, на которых рождается долг ---------------------------------------------------------
DOOR_COL = "кнопка столбца"
DOOR_OIL = "кнопка масла"
DOORS = (DOOR_COL, DOOR_OIL)


def enabled(raw):
    """Ветка жива? Пусто/не задано → ДА (дефолт 1). Ровно «0» → нет. Парсер как у `work_name`."""
    return str(raw if raw is not None else "1").strip() not in ("0", "false", "no", "off")


def _int(x):
    """Число или None. Пробелы и запятые — живой формат клетки Лист1, не идеализированный."""
    if x is None or isinstance(x, bool):
        return None
    if isinstance(x, int):
        return x
    try:
        s = str(x).strip().replace(" ", "").replace(",", "").replace(" ", "")
    except Exception:
        return None
    if not s:
        return None
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return None


def accepted(door, kinds, km, oil_hint=False):
    """ПРИНЯТА ли работа — то есть рождается ли долг на этой двери.

    Возвращает (bool, why). Условие одно на обе двери и названо словами: работа должна быть
    ЗАЯВЛЕНА, и её должно быть чем записать (число). Разница дверей только в том, чем заявка
    выражена: у столбца это сам перечень работ, у масла — маркер «замена сделана».
    """
    ks = [str(k).strip() for k in (kinds or []) if str(k).strip()]
    if door not in DOORS:
        return False, f"дверь «{door}» не из числа кнопочных — долг не заводим"
    if not ks:
        return False, "работа не названа — принимать нечего"
    if _int(km) is None:
        return False, "числа нет — работу нечем записать, это ещё не долг"
    if door == DOOR_OIL and not oil_hint:
        # Сам срок ТО принятой работой не является: это НАШ вопрос человеку, а не его заявка.
        return False, "срок ТО подошёл, но замену никто не объявлял — это вопрос, а не долг"
    return True, "работа названа и есть число — долг"


def open_fields(door, kinds, km, oil_hint=False, prev_declared=(), prev_done=()):
    """Поля строки долга для `service_pending_upsert`, или None если работа не принята.

    Перечни СЛИВАЮТСЯ с уже стоящими в открытой строке, а не замещают их: `servicePendingUpsert_`
    кладёт `declared`/`done` целиком, и без слияния второй вид той же партии затёр бы первый
    (место исчезновения №5 разбора 23.08). Порядок сказанного сохранён, дубли сняты.
    """
    ok, why = accepted(door, kinds, km, oil_hint=oil_hint)
    if not ok:
        return None
    ks = [str(k).strip() for k in kinds if str(k).strip()]
    merged_d = _merge(prev_declared, ks)
    merged_w = _merge(prev_done, ks)
    return {"declared": merged_d, "done": merged_w, "odometer": str(_int(km)),
            "status": STATUS, "kinds": ks, "why": why, "door": door}


def _merge(prev, add):
    """Слияние перечней с сохранением порядка и снятием дублей."""
    out = []
    for src in (prev or (), add or ()):
        for k in src:
            k = str(k).strip()
            if k and k not in out:
                out.append(k)
    return out


# ================= ПОЗИЦИОННЫЙ СЛЕД: ДОЛГ ПРИВЯЗАН К ПОЗИЦИИ, А НЕ К БАЙКУ ====================
#
# ПОЧЕМУ ПОНАДОБИЛСЯ (ревизия 23.08.2026, `930da84`, находка Н5). Строка «то_заявки» одна на
# ПАРУ тема × байк: `servicePendingFind_` ищет открытую строку по chat+topic+bike, а
# `servicePendingUpsert_` кладёт `declared`/`done`/`odometer`/`status` ЦЕЛИКОМ (`pick`,
# `bridge_prod/ServicePending.js:55`). Значит СЛЕДУЮЩИЙ ВИЗИТ ТОГО ЖЕ БАЙКА пишет своё поверх
# чужого долга: живой 5960 — 01.08 приняли `abs,pads` при 41357, кнопку не нажали, а 22.08 приезд
# редуктора переписал ту же строку в `gear` при 41641, и висевшие позиции исчезли БЕЗ СЛЕДА.
# Долг, стоящий на полях `done`/`status`, переживает рестарт и удаление сообщения — но не сосед.
#
# ЧТО ИМЕННО ЧИНИТСЯ — НОСИТЕЛЬ, А НЕ ПРИЗНАК. Позиции долга переезжают в `note`, потому что это
# ЕДИНСТВЕННОЕ поле строки, которого новый визит не передаёт, а `pick` сохраняет из `cur`
# (проверено node-харнессом на ЖИВОМ коде моста, не рассуждением). Мост при этом не меняется ни
# на строку — выкладка запрещена, а класс закрывается всё равно.
#
# ФОРМА — ЗЕРКАЛО УЖЕ ЖИВУЩЕГО В ЭТОМ ЖЕ ПОЛЕ СЕГМЕНТА `WORKS:{…}` (`splinter._sp_note_set_works`):
#     `DEBT:{gear@41357; abs@41357} | WORKS:{…} | escalated`
# Соседи по ноте не теряются НИКОГДА (`_rest_of`), иначе лечение одного класса рождало бы другой.
#
# ПУСТОЙ СЕГМЕНТ `DEBT:{}` — НЕ МУСОР, А СЛОВО. Мост читает пустую строку как «поле не передали»
# (`p[k] !== ''`), то есть СТЕРЕТЬ ноту нечем: единственный способ сказать листу «позиций больше
# нет» — написать непустое. Поэтому «сегмент есть и пуст» означает «долг снят», и сторож по этому
# признаку возвращает строку прежнему пути, а не молчит о ней.
LEDGER_KEY = "DEBT"
LEDGER_ODO = "@"
LEDGER_SEP = "; "
LEDGER_EMPTY = LEDGER_KEY + ":{}"
LEDGER_MAX = 12          # потолок позиций: видов ТО всего 8, запас на удвоение


def _word(x):
    """Кусок, безопасный для сегмента: разделители формы внутрь значения не пускаем."""
    s = str(x if x is not None else "")
    for bad in ("{", "}", ";", "|", LEDGER_ODO, "\n", "\r"):
        s = s.replace(bad, "")
    return s.strip()


def _clean(seq):
    out = []
    for k in (seq or ()):
        k = _word(k)
        if k and k not in out:
            out.append(k)
    return out


def _segment(note):
    """(начало, конец, тело) сегмента долга или None. Регулярки нет — импортов ноль."""
    s = str(note or "")
    head = LEDGER_KEY + ":{"
    i = s.find(head)
    if i < 0:
        return None
    j = s.find("}", i + len(head))
    if j < 0:
        return None
    return i, j + 1, s[i + len(head):j]


def ledger_present(note):
    """Сегмент долга в ноте ЕСТЬ (пусть и пустой)? Пустой = «долг снят», а не «долга не было»."""
    return _segment(note) is not None


def ledger_read(note):
    """Открытые позиции долга: [(вид, число-как-строка)]. Порядок сказанного сохранён."""
    seg = _segment(note)
    if seg is None:
        return []
    out = []
    for chunk in seg[2].split(";"):
        k, _, o = chunk.strip().partition(LEDGER_ODO)
        k = _word(k)
        if not k:
            continue
        km = _int(o)
        hit = [i for i, (kk, _o) in enumerate(out) if kk == k]
        if hit:
            # Вид назван дважды — держим БОЛЬШЕЕ требование: закрыть труднее, чем ослабить.
            was = _int(out[hit[0]][1])
            if km is not None and (was is None or km > was):
                out[hit[0]] = (k, str(km))
            continue
        out.append((k, str(km) if km is not None else ""))
    return out[:LEDGER_MAX]


def _rest_of(note):
    """Всё, что в ноте НЕ долг (`WORKS:{…}`, `escalated`, чужой текст), — не теряется никогда."""
    s = str(note or "")
    seg = _segment(s)
    if seg is not None:
        s = s[:seg[0]] + s[seg[1]:]
    return " | ".join(p for p in (x.strip() for x in s.split("|")) if p)


def ledger_note(note, positions):
    """Нота с ПЕРЕПИСАННЫМ сегментом долга; соседние сегменты сохранены дословно."""
    rest = _rest_of(note)
    body = LEDGER_SEP.join((k + LEDGER_ODO + o) if o else k
                           for k, o in list(positions or ())[:LEDGER_MAX])
    seg = (LEDGER_KEY + ":{" + body + "}") if body else ""
    if seg and rest:
        return seg + " | " + rest
    return seg or rest


def ledger_add(note, kinds, km):
    """Долг ЗАВЕДЁН по названным позициям. Требование позиции только РАСТЁТ (берём большее число):
    ослабить его вторым заходом значило бы закрыть долг числом, которое его не покрывает."""
    out = list(ledger_read(note))
    o = _int(km)
    for k in _clean(kinds):
        hit = [i for i, (kk, _o) in enumerate(out) if kk == k]
        if hit:
            was = _int(out[hit[0]][1])
            if o is not None and (was is None or o > was):
                out[hit[0]] = (k, str(o))
        elif len(out) < LEDGER_MAX:
            out.append((k, str(o) if o is not None else ""))
    return ledger_note(note, out)


def ledger_odometer(positions):
    """Число, которым закрываются ВСЕ названные позиции разом, — наибольшее из их требований."""
    best = None
    for _k, o in (positions or ()):
        v = _int(o)
        if v is not None and (best is None or v > best):
            best = v
    return best


def settle(note="", declared=(), done=(), closing=(), batch=(), odometer=None,
           row_terminal=False):
    """ЧТО ДОКАЗАННОЕ ЗАКРЫТИЕ ЗНАЧИТ ДЛЯ СТРОКИ. `verdict` отвечает «долг закрыт ли», эта —
    «какой именно позиции и что с самой строкой»; двух ответов на один вопрос не заводится.

    ТРИ ВЕЩИ, КОТОРЫХ ДО 23.08 НЕ БЫЛО, И КАЖДАЯ — ЖИВАЯ ДЫРА РЕВИЗИИ `930da84`:

      * **строки нет → закрывать нечего** (Н1). Прежде закрытие звалось БЕЗУСЛОВНО, а
        `servicePendingClose_` — это upsert: не найдя открытой строки, мост ДОПИСЫВАЛ пустую
        («ok/row=2/saved», declared и done пусты). Строка-эхо о заявке, которой не было.
      * **чужую строку не гасим** (Н2). Открытая `ждёт_факт` по цепи закрывалась от масляной
        двери, хотя цепь никто не записывал. Своя — та, что НАЗЫВАЕТ хоть одну закрываемую
        позицию (в следе, в `declared` или в `done`); иначе не наша, и мы её не трогаем.
      * **партия гаснет ПОЗИЦИОННО** (Н3). `gear,abs` уходила в закрыто ЦЕЛИКОМ по записи одного
        `gear`. Теперь снимаются РОВНО доказанные позиции, остальные остаются висеть и получают
        голос сторожа.

    СТРОКА ЗАКРЫВАЕТСЯ, только когда за ней не осталось НИ ОДНОГО обязательства: ни позиции
    долга, ни заявленного-без-отписки (`declared` минус `done`). Исключение ровно одно и оно
    названо — `row_terminal`: дверь фазы 2 («да» доверенного) и ЕСТЬ терминал самой заявки, у неё
    «не сделано» — законный исход, а не незакрытый хвост.

    → {"own", "close_row", "note", "changed", "remaining", "why"}
    """
    cur = str(note or "")
    led = ledger_read(cur)
    dec, dn, cl = _clean(declared), _clean(done), _clean(closing)
    bt = _clean(batch) or list(cl)
    if not cl:
        return _st(False, False, cur, False, [k for k, _o in led],
                   "закрывать нечего — ни одна позиция не названа")
    names = set(k for k, _o in led) | set(dec) | set(dn)
    if not (names & set(cl)):
        return _st(False, False, cur, False, [k for k, _o in led],
                   "строка не наша: ни одной закрываемой позиции она не называет")
    if led:
        base = list(led)
    elif set(cl) & set(bt):
        # Следа ещё нет (легаси-строка или дверь фазы 2) — партией считаем то, что дверь
        # ПРИНЕСЛА САМА. Своего перечня работ этот модуль не выдумывает.
        o = _int(odometer)
        base = [(k, str(o) if o is not None else "") for k in bt]
    else:
        return _st(True, False, cur, False, [],
                   "закрываемая позиция вне партии этой двери — след не трогаем")
    remaining = [(k, o) for k, o in base if k not in cl]
    owed = [k for k in dec if k not in dn]
    close_row = (not remaining) and (row_terminal or not owed)
    new = ledger_note(cur, [] if close_row else remaining)
    if not new and cur:
        # Пустую строку мост читает как «поле не передали» → стереть след нечем. Говорим словом.
        new = LEDGER_EMPTY
    if remaining:
        why = ("закрыты позиции " + ",".join(cl) + "; висят " +
               ",".join(k for k, _o in remaining) + " — строка остаётся открытой")
    elif close_row:
        why = "за строкой обязательств не осталось — закрываем её"
    else:
        why = ("позиции долга сняты, но строка ждёт заявленное (" + ",".join(owed) +
               ") — открытой оставляем")
    return _st(True, close_row, new, close_row or (new != cur),
               [k for k, _o in remaining], why)


def _st(own, close_row, note, changed, remaining, why):
    return {"own": bool(own), "close_row": bool(close_row), "note": note,
            "changed": bool(changed), "remaining": list(remaining), "why": why}


def verdict(write=None, cell=None, human=None, odometer=None):
    """ФАКТЫ → ИСХОД ДОЛГА. Возраста среди параметров НЕТ ВОВСЕ — см. шапку.

    write : None (не пробовали) | {"landed": bool, "known": bool, "detail": str}
    cell  : None (не читали)    | {"read": bool, "km": int|None, "detail": str}
    human : None (не решал)     | {"decided": bool, "who": str, "detail": str}
    odometer : величина, с которой работа обязана лечь (нужна ТОЛЬКО признаку клетки)

    → {"state": висит|закрыт|неизвестно, "by": <признак|"">, "why": <строка>, "closed": bool}
    """
    holes = []

    # (1) ЧЕЛОВЕК — авторитет, а не свидетель: его «не надо» доказательств сверх слов не требует.
    if isinstance(human, dict):
        if human.get("decided") is True:
            who = str(human.get("who") or "").strip()
            tail = f" ({who})" if who else ""
            return _v(CLOSED, BY_HUMAN, f"человек закрыл работу решением{tail}", True)
        holes.append("решения человека не было")

    # (2) ЗАПИСЬ — ответ мира, а не наше намерение.
    if isinstance(write, dict):
        if write.get("landed") is True:
            d = str(write.get("detail") or "").strip()
            return _v(CLOSED, BY_WRITE, "запись доказана" + (f": {d}" if d else ""), True)
        if write.get("known") is False:
            holes.append("исход записи неизвестен" + _tail(write))
        else:
            holes.append("запись не легла" + _tail(write))

    # (3) КЛЕТКА РЕГИСТРА — ловит запись мимо бота.
    if isinstance(cell, dict):
        if cell.get("read") is True:
            got, want = _int(cell.get("km")), _int(odometer)
            if want is None:
                holes.append("клетка прочитана, но сверять не с чем — числа у долга нет")
            elif got is None:
                holes.append("клетка прочитана, но величины в ней нет (пусто/не число)")
            elif got >= want:
                return _v(CLOSED, BY_CELL, f"в регистре {got} ≥ {want} — записано мимо нас", True)
            else:
                holes.append(f"в регистре {got} < {want} — работа не легла")
        else:
            holes.append("клетка не перечитана" + _tail(cell))

    if not holes:
        return _v(UNKNOWN, "", "фактов не приносили — судить не на чем", False)

    # Хотя бы один факт сказал «не легло» по существу → долг ВИСИТ (мы смотрели).
    # Все факты — дырки → НЕИЗВЕСТНО (смотреть не удалось). И то и другое оставляет долг видимым.
    solid = [h for h in holes if ("не легла" in h or "не легло" in h or "решения человека" in h)]
    if solid:
        return _v(OPEN, "", "; ".join(holes), False)
    return _v(UNKNOWN, "", "; ".join(holes), False)


def _tail(d):
    s = str((d or {}).get("detail") or "").strip()
    return f": {s}" if s else ""


def _v(state, by, why, closed):
    return {"state": state, "by": by, "why": why, "closed": bool(closed)}


def voice(status, age_h, escalated=False, remind_after_h=6.0, max_age_h=48.0):
    """ЧТО СТОРОЖ ВИСЯКОВ ВПРАВЕ СКАЗАТЬ О СТРОКЕ. Закрыть долг эта функция не умеет ФИЗИЧЕСКИ:
    среди её исходов нет ни одного из `CLOSERS` (проверяется тестом по исходнику).

    До 23.08.2026 статус `ждёт_подтверждения` получал `continue` ДО проверки возраста
    (`splinter.py:7040-7041`), поэтому работа, ждущая кнопки, не получала НИ висяк-напоминания,
    НИ эскалации владельцу: строка жила, и о ней не говорил никто. Теперь проверку возраста
    проходят ВСЕ открытые статусы, а различается только АДРЕСАТ — механику по работе, о которой
    он уже отписался, идти незачем.

    → {"speak": тихо|напомнить|эскалация, "to": <адресат>, "why": <строка>}
    """
    st = str(status or "").strip()
    age = None if age_h is None else _f(age_h)
    debt = (st == STATUS)
    to = TO_KEEPER if debt else TO_MECHANIC

    if age is None:
        # Возраст не прочитан — молчим. Возраст не признак закрытия, но он признак ГРОМКОСТИ,
        # и кричать, не зная его, значило бы кричать по таймеру наугад.
        return {"speak": QUIET, "to": to, "why": "возраст строки не прочитан — судить нечем"}
    if age >= _f(max_age_h):
        if escalated:
            return {"speak": QUIET, "to": TO_OWNER,
                    "why": f"возраст {age:.1f}ч ≥ {_f(max_age_h):.0f}ч, эскалация уже была — повтора нет"}
        return {"speak": ESCALATE, "to": TO_OWNER,
                "why": (f"возраст {age:.1f}ч ≥ {_f(max_age_h):.0f}ч — "
                        + ("кнопку так и не нажали" if debt else "заявка не закрыта"))}
    if age >= _f(remind_after_h):
        return {"speak": REMIND, "to": to,
                "why": (f"возраст {age:.1f}ч ≥ {_f(remind_after_h):.0f}ч — "
                        + ("кнопка висит ненажатой" if debt else "результат не отписан"))}
    return {"speak": QUIET, "to": to, "why": f"возраст {age:.1f}ч — порог напоминания не пройден"}


def _f(x):
    try:
        return float(x)
    except (ValueError, TypeError):
        return 0.0


def line(v, bike="", kinds=()):
    """Строка в журнал. Отдельного вокабуляра не заводит — печатает то, что решил `verdict`."""
    b = f" {bike}" if bike else ""
    k = f" [{','.join(str(x) for x in kinds)}]" if kinds else ""
    by = f" по признаку «{v.get('by')}»" if v.get("by") else ""
    return f"долг ТО{b}{k}: {v.get('state')}{by} — {v.get('why')}"
