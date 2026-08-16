"""СУДЬЯ АДРЕСА РЕЗУЛЬТАТА — «по названному адресу и правда лежит продукт шага?» (16.08.2026).

ПУНКТ 2 КОНТРАКТА ТРЕТЬЕГО ИСХОДА. Пункт 1 (`result_ref.py`, `55d2f1d`) завёл МЕСТО, куда шаг
кладёт адрес своего продукта: `[result_ref: <вид> <указатель>]`, виды `commit` · `file` · `row` ·
`brain` · `service_start`. Пункт 2 заводит ЧИТАТЕЛЯ этого адреса — и ничего сверх него.

ОТВЕТОВ ТРИ, И ТРЕТИЙ НЕ ВЕЖЛИВОСТЬ:

    ДОКАЗАН      — по адресу прочитано то, чего адрес требовал;
    НЕ ДОКАЗАН   — по адресу прочитано: пусто либо не то;
    НЕИЗВЕСТНО   — адрес не назван · назван непонятно · источник не прочитан.

«Источник недоступен» — это НЕ «в порядке». Порядок силы взят у прибора О3 дословно
(`expectations.delivery_state`): НЕ ДОКАЗАН > НЕИЗВЕСТНО > ДОКАЗАН, то есть незнание НЕ смеет
перекрыть доказанное отсутствие, а доказанное наличие не смеет перекрыть незнание. Требование
задания «НЕИЗВЕСТНО СИЛЬНЕЕ ДОКАЗАН» содержится в этом порядке целиком.

ОБРАЗЕЦ ВЗЯТ У О3, А НЕ ИЗОБРЕТЁН. Совпадает: три исхода со своими словами вместо булева флага;
порядок силы; РАЗДЕЛЕНИЕ «чистое решение × руки» (`expectations.py` судит — `expectations_run.py`
читает мир; здесь `result_judge.py` судит — `result_judge_facts.py` читает); причина у каждого
исхода называется текстом, а не кодом; свидетель C1 прибора («старт процесса ПОЗЖЕ коммита»)
перенесён в вид `service_start` буквально. Расхождения с О3 названы и объяснены в артефакте
`docs/artifacts/2026-08-16-result-judge.md` §3; коротко их три:
  • О3 собирает факты ВСЕ и сразу (их мало и они общие), здесь источник называет САМ адрес —
    поэтому у судьи есть `plan()`: что именно надо прочитать под этот адрес;
  • у О3 есть четвёртый ярлык «вне доставки» (файл, который доставлять некуда); у адреса такого
    ярлыка нет и быть не может: адрес назван — значит продукт обещан;
  • О3 живёт во времени (порог 4 ч, окно 48 ч, отсрочка), а СУДЬЯ ВРЕМЕНИ НЕ ЗНАЕТ ВОВСЕ —
    см. следующий абзац.

ВРЕМЕНИ У СУДЬИ НЕТ, И ЭТО ГЛАВНОЕ ЕГО СВОЙСТВО. Прежний способ доказывать результат шага —
ОКНО ИСПОЛНЕНИЯ: что попало в интервал работы, то и приписывалось шагу (так считает вес живой
счёт цепочек; так мерил замер `a3cf244`). Приём законный, но он судит СОВПАДЕНИЕ ВО ВРЕМЕНИ:
сдвиг окна на два часа отнимал доказательство у 46 шагов из 71 (замер 15.08, §4.4). Судья адреса
устроен иначе: у `verdict()` нет ни параметра «сейчас», ни окна, ни порога, а единственное
сравнение времён внутри (`service_start`) — это сравнение ДВУХ НАЗВАННЫХ АДРЕСОМ величин между
собой, и сдвиг обеих на любую величину исхода не меняет. Отсюда замок C захода: сдвиг окна на
±2 ч не меняет ни одного вердикта.

НАПРАВЛЕНИЕ СОМНЕНИЯ — В НЕЗНАНИЕ, А НЕ В ЗЕЛЁНОЕ. Указатель не разобран, источник не прочитан,
хеш-указатель короче семи знаков, префикс совпал с двумя коммитами, у узла мозга не с чем сравнить
длину — всё это НЕИЗВЕСТНО. Ошибка судьи обязана стоить лишнего вопроса, а не ложного зелёного:
ровно тем же замком живут О3, `write_fact`, `scan_result` и касса.

УКАЗАТЕЛЬ ГОВОРИТ ДВА СЛОВА ТАМ, ГДЕ ОДНОГО МАЛО. Канон `result_ref` не делит указатель: всё
после вида — указатель целиком. Но «узел содержит НАЗВАННОЕ» и «старт юнита моложе НАЗВАННОГО
коммита» — про две величины, и вторую надо назвать. Подграмматика (её знает только судья, канон
её не касается):

    commit         <хеш>                                    хеш 7…40 знаков
    file           <путь>                                   весь указатель — путь целиком
    row            <база> <таблица> <кол>=<знач>[,<кол>=<знач>]
    brain          <ключ> <ожидаемая подстрока>
    service_start  <юнит> <хеш>

БАЗА У `row` НАЗЫВАЕТСЯ ЯВНО. Умолчание «конечно memory.db» было бы утверждением о мире, которого
никто не проверял: строка живёт в той базе, которую назвал адрес, и в другой её отсутствие ничего
не значит. Условие — только РАВЕНСТВА через запятую, и они уезжают в запрос ПАРАМЕТРАМИ: адрес
приходит из живого текста очереди, который пишут люди и чужая полоса, и пускать его в текст
запроса нельзя (то же правило, по которому гард судит команду, а не слово).

ЧТЕНИЕ НЕ БРОСАЕТ НИКОГДА (правило `result_ref.parse`): кривой указатель — это НЕИЗВЕСТНО с
названной причиной, а не исключение посреди чужого цикла.

ГРАНИЦА ЗАХОДА — УСТРОЙСТВОМ. Судья НИКЕМ НЕ ЗОВОМ: вердикт шага не трогается, движение цепи не
меняется, правила «нет адреса — нет зелёного» нет. Импорт ровно один — `result_ref` (вокабуляр
адреса берётся ГОТОВЫМ, чтобы второе определение формы не завелось рядом; тот же приём, каким
`deliver_card` берёт вокабуляр у `expectations`). Сходить по адресу самому этому модулю НЕЧЕМ:
ни файлов, ни сети, ни подпроцессов, ни базы — страж `RESULT_JUDGE_PURE` (ast) в
`invariants_check.py`, в гейте. Руки живут отдельно (`result_judge_facts.py`) и тоже не зовутся
ниоткуда: доказано замыканием импортов живых точек входа в `tests/test_result_judge.py`.
"""
import result_ref

# ТРИ ИСХОДА словами, как у О3 (`DELIVERED/UNDELIVERED/UNKNOWN`), — не булев флаг и не код.
PROVEN, UNPROVEN, UNKNOWN = "доказан", "не доказан", "неизвестно"

# ПОРЯДОК СИЛЫ — зеркало О3: доказанное отсутствие сильнее незнания, незнание сильнее доказанного
# наличия. Нужен там, где вердиктов несколько (цепочка шагов), а не в одиночном ответе.
RANK = {UNPROVEN: 2, UNKNOWN: 1, PROVEN: 0}

NOT_NAMED = "адрес не назван"
_HEX = "0123456789abcdef"
SHA_MIN = 7          # короче — совпадение префикса перестаёт что-либо доказывать


def strongest(states):
    """Несколько исходов → сильнейший. Пусто → НЕИЗВЕСТНО (пустого зелёного не бывает)."""
    best, rank = UNKNOWN, -1
    for s in states or ():
        r = RANK.get(s, RANK[UNKNOWN])
        if r > rank:
            best, rank = (s if s in RANK else UNKNOWN), r
    return best


def _pair(ref):
    """Адрес в любой форме → (вид, указатель). Разобрать нечем → ('', '')."""
    try:
        k, p = result_ref.as_pair(ref)
    except ValueError:
        return "", ""
    return str(k or "").strip(), str(p or "").strip()


def _sha_ok(s):
    """Похож ли указатель на хеш коммита: 7…40 шестнадцатеричных знаков."""
    s = str(s or "").strip().lower()
    return SHA_MIN <= len(s) <= 40 and all(c in _HEX for c in s)


def _conds(text):
    """«кол=знач,кол=знач» → [(кол, знач)] либо None, если разобрать нечем."""
    out = []
    for chunk in str(text or "").split(","):
        col, sep, val = chunk.partition("=")
        col, val = col.strip(), val.strip()
        if not sep or not col or not val:
            return None
        # Имя колонки в запрос уходит НЕ параметром (идентификатор параметром не бывает),
        # поэтому оно обязано быть именем, а не выражением.
        if not all(ch.isalnum() or ch == "_" for ch in col):
            return None
        out.append((col, val))
    return out or None


def plan(ref):
    """Адрес → ЧТО НАДО ПРОЧИТАТЬ, чтобы его судить. Чистая функция: сама не читает ничего.

    Возврат: {"kind","pointer","ok","why","parts"}. `ok=False` — судить нечем уже по адресу
    (не назван либо не разобран), и `verdict` на тех же фактах ответит НЕИЗВЕСТНО с той же
    причиной: два места не вправе понимать один адрес по-разному."""
    kind, pointer = _pair(ref)
    out = {"kind": kind, "pointer": pointer, "ok": False, "why": "", "parts": {}}
    if not kind and not pointer:
        out["why"] = NOT_NAMED
        return out
    if kind not in result_ref.KINDS:
        out["why"] = "вид «%s» не из контракта — судить нечем" % kind
        return out
    if not pointer:
        out["why"] = "вид «%s» назван, а указатель пуст" % kind
        return out

    if kind == "commit":
        if not _sha_ok(pointer):
            out["why"] = ("указатель «%s» не похож на хеш (нужны 7…40 шестнадцатеричных "
                          "знаков) — совпадение по нему ничего не доказало бы" % pointer)
            return out
        out["parts"] = {"sha": pointer.lower()}
    elif kind == "file":
        out["parts"] = {"path": pointer}
    elif kind == "row":
        db, _, rest = pointer.partition(" ")
        table, _, cond = rest.strip().partition(" ")
        conds = _conds(cond)
        if not db or not table or not conds:
            out["why"] = ("указатель строки читается как «<база> <таблица> <кол>=<знач>», "
                          "а назван «%s»" % pointer)
            return out
        if not all(ch.isalnum() or ch == "_" for ch in table):
            out["why"] = "имя таблицы «%s» не похоже на имя" % table
            return out
        out["parts"] = {"db": db, "table": table, "conds": conds}
    elif kind == "brain":
        key, _, expect = pointer.partition(" ")
        expect = expect.strip()
        if not key or not expect:
            out["why"] = ("указатель узла читается как «<ключ> <ожидаемая подстрока>», а назван "
                          "«%s»: без названного искать в узле нечего" % pointer)
            return out
        out["parts"] = {"key": key, "expect": expect}
    elif kind == "service_start":
        unit, _, sha = pointer.partition(" ")
        sha = sha.strip()
        if not unit or not _sha_ok(sha):
            out["why"] = ("указатель старта читается как «<юнит> <хеш>», а назван «%s»"
                          % pointer)
            return out
        out["parts"] = {"unit": unit, "sha": sha.lower()}
    out["ok"] = True
    return out


# ── чтение фактов ПО ВИДАМ (сами факты приносят руки; форма — ниже, в докстрингах веток) ─────
def _commits(facts):
    return (facts or {}).get("commits") or {}


def _match(sha, commits):
    """Полные хеши origin/main, начинающиеся на указатель. Список, а не флаг: два совпадения —
    это НЕ доказательство, а неоднозначность, и решать её должен вердикт, а не поиск."""
    return [s for s in (commits.get("shas") or ()) if str(s).lower().startswith(sha)]


def _v(state, why):
    return state, why


def _judge_commit(parts, facts):
    c = _commits(facts)
    if not c.get("read"):
        return _v(UNKNOWN, "origin/main не прочитан — сказать о коммите нечего")
    hits = _match(parts["sha"], c)
    if len(hits) == 1:
        return _v(PROVEN, "коммит %s есть в origin/main" % hits[0][:12])
    if not hits:
        return _v(UNPROVEN, "коммита %s в origin/main нет" % parts["sha"])
    return _v(UNKNOWN, "указатель %s совпал с %d коммитами — судить нечем"
              % (parts["sha"], len(hits)))


def _judge_file(parts, facts):
    f = ((facts or {}).get("files") or {}).get(parts["path"]) or {}
    if not f.get("read"):
        return _v(UNKNOWN, "файл не прочитан (%s) — сказать нечего"
                  % (f.get("why") or "источник недоступен"))
    if not f.get("exists"):
        return _v(UNPROVEN, "файла по адресу нет")
    try:
        size = int(f.get("size") or 0)
    except (TypeError, ValueError):
        return _v(UNKNOWN, "размер файла не разобран")
    if size <= 0:
        return _v(UNPROVEN, "файл есть, но пуст")
    return _v(PROVEN, "файл на месте, %d байт" % size)


def _judge_row(parts, facts):
    r = ((facts or {}).get("rows") or {}).get(parts["key"]) or {}
    if not r.get("read"):
        return _v(UNKNOWN, "строку не прочитать (%s)" % (r.get("why") or "источник недоступен"))
    try:
        n = int(r.get("count") or 0)
    except (TypeError, ValueError):
        return _v(UNKNOWN, "ответ базы не разобран")
    if n <= 0:
        return _v(UNPROVEN, "строки по названному условию в таблице «%s» нет" % parts["table"])
    return _v(PROVEN, "строк по условию: %d" % n)


def _judge_brain(parts, facts):
    """Узел мозга: СОДЕРЖИТ названное И ВЫРОС.

    Обе половины обязательны, и вторая не украшение: журнал мозга пишет сам исполнитель, а замер
    15.08 (`a3cf244`) показал, что у 27 % шагов единственный след — их собственная строка в этом
    журнале. «Содержит» без «выросло» не отличает новую запись от той, что лежала там и до шага;
    сравнить не с чем → НЕИЗВЕСТНО, а не зелёное."""
    b = ((facts or {}).get("brain") or {}).get(parts["key"]) or {}
    if not b.get("read"):
        return _v(UNKNOWN, "узел «%s» не прочитан (%s)"
                  % (parts["key"], b.get("why") or "источник недоступен"))
    text = str(b.get("text") or "")
    if parts["expect"] not in text:
        return _v(UNPROVEN, "узел «%s» названного не содержит" % parts["key"])
    before = b.get("len_before")
    if before is None:
        return _v(UNKNOWN, "узел «%s» содержит названное, но длину не с чем сравнить — «уже "
                           "было» отсюда неотличимо" % parts["key"])
    try:
        before = int(before)
    except (TypeError, ValueError):
        return _v(UNKNOWN, "прежняя длина узла «%s» не разобрана" % parts["key"])
    now = int(b.get("len") if b.get("len") is not None else len(text))
    if now > before:
        return _v(PROVEN, "узел «%s» содержит названное и вырос %d → %d"
                  % (parts["key"], before, now))
    return _v(UNPROVEN, "узел «%s» содержит названное, но не вырос (%d → %d) — это могло лежать "
                        "там и до шага" % (parts["key"], before, now))


def _judge_service_start(parts, facts):
    """Старт юнита МОЛОЖЕ названного коммита — свидетель C1 прибора О3, перенесённый дословно.

    Сравниваются ДВЕ величины, названные самим адресом. Ни «сейчас», ни окна тут нет: сдвиг обеих
    на любую величину исхода не меняет, и это проверяется замком C захода."""
    u = ((facts or {}).get("units") or {}).get(parts["unit"]) or {}
    c = _commits(facts)
    if not u.get("read") or u.get("started") is None:
        return _v(UNKNOWN, "юнит %s не наблюдается (%s) — памяти не спросить"
                  % (parts["unit"], u.get("why") or "старт не прочитан"))
    if not c.get("read"):
        return _v(UNKNOWN, "origin/main не прочитан — времени коммита не знаем")
    hits = _match(parts["sha"], c)
    if len(hits) != 1:
        return _v(UNKNOWN, "коммит %s в origin/main %s — времени старта не с чем сравнить"
                  % (parts["sha"], "не найден" if not hits else "неоднозначен"))
    at = (c.get("at") or {}).get(hits[0])
    try:
        started, at = float(u.get("started")), float(at)
    except (TypeError, ValueError):
        return _v(UNKNOWN, "время старта либо коммита не разобрано")
    if started > at:
        return _v(PROVEN, "юнит %s поднят на %d с позже коммита %s"
                  % (parts["unit"], int(started - at), hits[0][:7]))
    return _v(UNPROVEN, "юнит %s поднят на %d с РАНЬШЕ коммита %s — в памяти прежний код"
              % (parts["unit"], int(at - started), hits[0][:7]))


_BY_KIND = {
    "commit": _judge_commit,
    "file": _judge_file,
    "row": _judge_row,
    "brain": _judge_brain,
    "service_start": _judge_service_start,
}


def verdict(ref, facts=None):
    """Адрес + прочитанные факты → {"state","why","kind","pointer"}. Не бросает никогда.

    Времени, окна и порога у этой функции нет ни одного — см. шапку модуля."""
    p = plan(ref)
    if not p["ok"]:
        return {"state": UNKNOWN, "why": p["why"] or NOT_NAMED,
                "kind": p["kind"], "pointer": p["pointer"]}
    parts = dict(p["parts"])
    if p["kind"] == "row":
        parts["key"] = p["pointer"]          # ключ факта — указатель целиком, без пересборки
    try:
        state, why = _BY_KIND[p["kind"]](parts, facts or {})
    except Exception as e:                   # noqa: BLE001 — падение читателя не смеет стать зелёным
        state, why = UNKNOWN, "разбор фактов не удался (%s)" % type(e).__name__
    return {"state": state, "why": why, "kind": p["kind"], "pointer": p["pointer"]}


def of_task(row, facts=None):
    """Строка очереди → вердикт по её адресу. Адреса нет → НЕИЗВЕСТНО «адрес не назван».

    Это удобство для ЧИТАТЕЛЕЙ (замер, тест), а не подключение: вердикт шага здесь не трогается
    и никем отсюда не зовётся."""
    return verdict(result_ref.of_task(row), facts)
