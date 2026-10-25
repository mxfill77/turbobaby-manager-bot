# -*- coding: utf-8 -*-
"""НОМЕР НА БАЙКЕ ↔ ИМЯ ТЕМЫ ↔ ЗЕЛЁНАЯ КНИГА (25.10.2026, PLATEWATCH2510; ревью r2 — 25.10).

ПРАВИЛО ВЛАДЕЛЬЦА 25.10: имя темы обслуживания идёт за номером, который ФИЗИЧЕСКИ стоит на байке,
а расхождение этого номера с зелёной книгой (เล่มทะเบียน) — ПРЕДУПРЕЖДЕНИЕ владельцу.

ПОВОД. 24.10 все имена тем и Лист1 перевели на номера из зелёных книг. Снимки в темах показывают,
что часть байков до сих пор ездит со СТАРОЙ табличкой: тема 83 (фото 13.10) — на байке 2478, в
книге 9286; 1190 — 9315 при 8676; 62 — 5849 при 5662; 66 — 9011 при 461. Мост (v96) сам переводит
старый номер в новый для записей в Лист1, но механик в теме видит на байке одно, а бот зовёт байк
другим — и никто об этом не узнаёт, пока не перепутают байк.

ЧТО РЕШАЕТ МОДУЛЬ — и только это:
  * какое чтение таблички со снимка годится (`reading`): только `legible: true` и только цифры;
  * какой номер у темы (`topic_plate`): ПОСЛЕДНЕЕ слово имени, если оно из цифр;
  * можно ли верить имени, которым бот зовёт тему (`name_trusted`);
  * что делать с темой (`verdict`): карточка «переименовать», предупреждение без переименования
    или ничего — и почему, словами; жива ли ещё висящая карточка (`card_valid`);
  * текст карточки (`card_text`) и мелкие правки памяти (`with_*`).

ПОРОГИ:
  * из слова задания 25.10: ДВА чтения из РАЗНЫХ отправок за 14 суток (`NEED`, `WINDOW_S`). Одно
    чтение — ничего: модель зрения ошибается в цифре (частые пары 1↔7, 0↔8, 5↔6, 3↔8 — те же, что
    у одометра), и одна ошибка не смеет переименовать тему. Альбом — ОДНА отправка;
  * из ревью r2 (рассуждение, НЕ замер): свидетели НЕЗАВИСИМЫ — один и тот же снимок
    (`file_unique_id`, пересылка) = один свидетель, а два свидетеля разнесены не меньше чем на
    6 часов (`MIN_GAP_S`) — то есть с разных заходов к байку, а не две фотографии одной минуты при
    одном свете, чья ошибка в одной цифре одна и та же. Чтения окна обязаны сойтись ВСЕ: одно
    несогласное — уже сомнение (`SPLIT`);
  * предупреждение «тема = байк, но не книга» — не чаще раза в 7 суток на тему (`WARN_EVERY_S`);
  * висящая карточка держит тему 7 суток (`CARD_TTL_S`) и старше них не исполняется.

НАПРАВЛЕНИЕ СОМНЕНИЯ — В МОЛЧАНИЕ, и это обратно замку подсказок НАМЕРЕННО. Там молчание лишало
человека совета; здесь любая карточка предлагает переименовать тему, то есть сменить имя байка,
которым бот пишет в Лист1, а владелец жмёт кнопки, не читая. Поэтому любая дырка даёт «ничего», а
не карточку: чтение смазано · чтения расходятся · свидетели не независимы · номер — номер ДРУГОГО
байка парка · номер на одну цифру от номера темы или книги · номер — часть номера темы или книги
(или наоборот) · номер = объём двигателя · имени бота не верим (не сверено с названием темы) ·
тема привязана руками (/bike) · в имени темы нет номера · память не читается. Не угадываем.

ГРАНИЦА, КОТОРУЮ ДЕРЖИТ УСТРОЙСТВО: импортов НОЛЬ (страж в `tests/test_plate_watch.py`). Время,
диск, сеть, Telegram и память приносят руки (`splinter._plate_*`).
"""

# --- исходы (словами, а не булевыми) ---------------------------------------------------
OFF = "наблюдение выключено (PLATE_WATCH=0)"
FEW = "мало независимых чтений: нужно два (разные отправки и снимки, не ближе 6 ч) за 14 суток"
SPLIT = "чтения за 14 суток расходятся — не гадаем"
NO_TOPIC_PLATE = "в имени темы нет номера последним словом — сравнивать не с чем"
MANUAL = "тема привязана к байку руками (/bike) — имя ведёт владелец, переименование темы его не сменит"
UNTRUSTED = "имя, которым бот зовёт тему, не сверено с названием темы — сравнивать не с чем"
SAME = "номер на байке совпадает с именем темы и с зелёной книгой"
SAME_NO_BOOK = "номер на байке совпадает с именем темы; зелёной книги по теме нет"
ENGINE = "номер на байке совпадает с объёмом двигателя — это не номер"
PARTIAL = "номер на байке — часть номера темы или книги (или наоборот) — похоже на неполное чтение"
NEAR = "номер на байке на одну цифру отличается от номера темы или книги — похоже на ошибку чтения"
OTHER_BIKE = "номер на байке — номер другого байка парка"
PENDING = "по теме уже висит карточка — вторую не шлём"
DECLINED = "владелец нажал «Оставить» при этом имени и этом номере"
WARN_RECENT = "предупреждение по теме уже было за 7 суток"
BRIDGE_BLIND = "предложенное имя мост не узнает: номер из имени не равен номеру на байке"
RENAME = "номер на байке не совпадает с именем темы"
WARN = "номер на байке совпадает с именем темы, но не с зелёной книгой"
CARD_OLD = "карточка старше 7 суток"

KIND_RENAME = "rename"
KIND_WARN = "warn"

NEED = 2                        # независимых согласных чтений
WINDOW_S = 14 * 86400           # окно согласия
MIN_GAP_S = 6 * 3600            # два свидетеля — с разных заходов к байку (ревью r2, рассуждение)
WARN_EVERY_S = 7 * 86400        # предупреждение без переименования — не чаще
CARD_TTL_S = 7 * 86400          # сколько висящая карточка держит тему и сколько она исполнима
KEEP_PER_TOPIC = 12             # чтений в памяти на тему (старше окна уходят и так)

#: Объёмы двигателя парка — зеркало `splinter._CC_PLATE` (страж равенства — tests/test_plate_watch.py):
#: «300» на снимке — скорее надпись объёма, чем номер, и мост такой номер из имени не возьмёт.
ENGINE_CC = frozenset(("125", "150", "155", "300", "350", "400", "500", "650", "700", "750", "900"))

#: Откуда у бота имя темы (поле `source` строки memory.db `topic_bike`, ревью r2).
SRC_EVENT = "forum_event"       # событие создания/переименования на САМОМ сообщении — с 25.10 r2
SRC_REPLY = "forum_reply"       # reply на сообщение создания: ПЕРВОЕ имя темы, только заполняет пустое
SRC_PLATE = "plate_rename"      # кнопка «Переименовать тему» этой ветки
SRC_MANUAL = "manual"           # /bike — ручная привязка владельца
#: Прежняя метка 'forum_created' писалась И событием, И reply (дрейф имени до 25.10) — по ней не
#: различить, поэтому она в доверенные НЕ входит: такому имени верим, только если оно равно имени книги.
TRUSTED_SRC = frozenset((SRC_EVENT, SRC_PLATE))

#: тайские цифры на табличке встречаются редко, но модель вправе вернуть их как есть
_THAI_DIGITS = {"๐": "0", "๑": "1", "๒": "2", "๓": "3", "๔": "4",
                "๕": "5", "๖": "6", "๗": "7", "๘": "8", "๙": "9"}
_ASCII_DIGITS = "0123456789"


def digits(v):
    """Номер таблички → строка цифр без ведущих нулей, либо None.

    ТРИ-ЧЕТЫРЕ цифры. Тайский номер бывает и короче, но имя байка с номером из двух цифр мост не
    узнает: строку Лист1 он ищет по `plateFromName_` (ReadFleet.js; зеркало — `splinter._plate_from_name`),
    а тот берёт последнее число от ТРЁХ цифр. Во всём парке зелёных книг номера — 3–4 цифры (440, 461,
    372 … 9890). Пробел и дефис внутри снимаются («24 78»), тайские цифры переводятся. Всё прочее
    (буквы, пять цифр, пусто, булево) — None: это не номер, а догадка."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, int):
        s = str(v)
    elif isinstance(v, str):
        s = "".join(_THAI_DIGITS.get(c, c) for c in v if c not in (" ", "-", chr(0xA0)))
    else:
        return None
    s = s.lstrip("0")
    if not (3 <= len(s) <= 4) or any(c not in _ASCII_DIGITS for c in s):
        return None
    return s


def _txt(v):
    return v.strip() if isinstance(v, str) and v.strip() else None


def reading(vis):
    """Чтение таблички из разбора снимка (`splinter.VISION_BIKE_SYSTEM`, поле `plate`) → {d, series,
    province} либо None.

    Берётся ТОЛЬКО `legible: true` — строго булево «да», не строка и не «наверное». Табличка байка
    на фоне промпт велит не возвращать вовсе; вернула модель её с `legible: false` — тоже мимо."""
    p = vis.get("plate") if isinstance(vis, dict) else None
    if not isinstance(p, dict) or p.get("legible") is not True:
        return None
    d = digits(p.get("digits"))
    if d is None:
        return None
    return {"d": d, "series": _txt(p.get("series")), "province": _txt(p.get("province"))}


def topic_plate(name):
    """Номер темы — ПОСЛЕДНЕЕ слово имени, если оно из цифр («XADV 750 BLACK 5104» → «5104»).

    Именно последнее: «750» в середине — объём, а не номер. Имя без номера в конце («XADV 750
    BLACK») — None, и тогда сравнивать не с чем."""
    if not isinstance(name, str):
        return None
    parts = name.split()
    if len(parts) < 2:
        return None
    last = parts[-1]
    if any(c not in _ASCII_DIGITS for c in last):
        return None
    return digits(last)


def propose(name, d):
    """Предлагаемое имя: прежнее имя, у которого номер последним словом заменён на `d`."""
    if topic_plate(name) is None or digits(d) is None:
        return None
    head = name.rstrip().rsplit(None, 1)[0]
    return f"{head} {digits(d)}"


def book_entry(doc, topic_id):
    """Строка зелёной книги по номеру темы из `plate_watch_book.json` → {d, series, province, name}
    либо None (книги нет, темы в ней нет, номер не читается)."""
    bikes = doc.get("bikes") if isinstance(doc, dict) else None
    if not isinstance(bikes, list):
        return None
    for b in bikes:
        if not isinstance(b, dict):
            continue
        try:
            same = int(b.get("topic_id")) == int(topic_id)
        except (TypeError, ValueError):
            same = False
        if not same:
            continue
        d = digits(b.get("plate_digits"))
        if d is None:
            return None
        return {"d": d, "series": _txt(b.get("plate_series")), "province": _txt(b.get("province")),
                "name": _txt(b.get("name"))}
    return None


def book_topic(doc, d):
    """Тема, у которой в зелёной книге номер `d` → int, либо None (нет книги, нет номера, номер у двух тем)."""
    bikes = doc.get("bikes") if isinstance(doc, dict) else None
    want = digits(d)
    if not isinstance(bikes, list) or want is None:
        return None
    hits = set()
    for b in bikes:
        if isinstance(b, dict) and digits(b.get("plate_digits")) == want:
            try:
                hits.add(int(b.get("topic_id")))
            except (TypeError, ValueError):
                continue
    return hits.pop() if len(hits) == 1 else None


def fleet_numbers(doc, names, topic_id):
    """Номера ДРУГИХ тем парка → {номер: тема}: номер из зелёной книги и номер из имени темы.

    `names` — {тема: имя}, которыми бот зовёт темы (кэш, memory.db, карта тем). Своя тема не входит:
    против неё сверка идёт отдельно (`t`, `g`)."""
    out = {}
    try:
        me = int(topic_id)
    except (TypeError, ValueError):
        me = None
    bikes = doc.get("bikes") if isinstance(doc, dict) else None
    for b in bikes if isinstance(bikes, list) else []:
        if not isinstance(b, dict):
            continue
        try:
            tid = int(b.get("topic_id"))
        except (TypeError, ValueError):
            continue
        d = digits(b.get("plate_digits"))
        if d and tid != me:
            out.setdefault(d, tid)
    for tid, name in (names or {}).items():
        try:
            tid = int(tid)
        except (TypeError, ValueError):
            continue
        d = topic_plate(name)
        if d and tid != me:
            out.setdefault(d, tid)
    return out


def _norm(s):
    return " ".join(s.split()).casefold() if isinstance(s, str) else None


def name_trusted(name, src, book):
    """Верим ли имени, которым бот зовёт тему (M3 ревью r2).

    Telegram не даёт боту прочитать название темы — бот знает его только по событиям. До 25.10 reply
    на сообщение создания возвращал теме ПЕРВОЕ имя с той же меткой 'forum_created', что и событие,
    поэтому имя с этой меткой может быть дрейфом, а не названием. Верим, когда:
      * имя пришло событием темы после правки (`forum_event`) или кнопкой этой ветки (`plate_rename`);
      * либо оно равно имени из зелёной книги — его темам дали 24.10, и дрейф его не повторит."""
    if src in TRUSTED_SRC:
        return True
    bn = _norm((book or {}).get("name"))
    return bool(bn) and bn == _norm(name)


def _near(a, b):
    """Отличаются ли номера РОВНО одной цифрой на одном месте (2478 ↔ 2473, 4248 ↔ 4246)."""
    return len(a) == len(b) and sum(1 for x, y in zip(a, b) if x != y) == 1


def _part(a, b):
    """Один номер — другой без одной цифры (286 ↔ 9286, 1461 ↔ 461): неполное или слипшееся чтение."""
    short, long_ = (a, b) if len(a) < len(b) else (b, a)
    if len(long_) != len(short) + 1:
        return False
    it = iter(long_)
    return all(c in it for c in short)


def msg_link(chat_id, topic_id, mid):
    """Ссылка на сообщение темы форума: владельцу — открыть снимок одним нажатием."""
    try:
        c = str(int(chat_id))
        if not c.startswith("-100"):
            return None
        return f"https://t.me/c/{c[4:]}/{int(topic_id)}/{int(mid)}"
    except (TypeError, ValueError):
        return None


# ============================ ПАМЯТЬ (чистые правки) ============================

def clean(state):
    """Память в каноническом виде: всё, что не похоже на неё, отбрасывается, а не чинится.

    Чтение памяти с диска НЕ идёт через `clean` при сбое: руки отличают «файла нет» (пустая память)
    от «файл не читается» (ветка замолкает до перезапуска) — `splinter._plate_load`."""
    st = state if isinstance(state, dict) else {}
    out = {"seq": 0, "readings": {}, "cards": {}, "warned": {}, "declined": {}}
    try:
        out["seq"] = max(0, int(st.get("seq") or 0))
    except (TypeError, ValueError):
        out["seq"] = 0
    for key in ("readings", "cards", "warned", "declined"):
        src = st.get(key)
        if not isinstance(src, dict):
            continue
        for k, v in src.items():
            if key == "readings":
                rows = [dict(r) for r in v if isinstance(r, dict) and digits(r.get("d"))] \
                    if isinstance(v, list) else []
                if rows:
                    out[key][str(k)] = rows
            elif key == "warned":
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    out[key][str(k)] = float(v)
            elif isinstance(v, dict):
                out[key][str(k)] = dict(v)
    return out


def _ts(r):
    v = r.get("ts") if isinstance(r, dict) else None
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0.0


def add_reading(state, topic_id, rd, mid, group, now, fu=None):
    """Положить чтение в память темы. Повтор ТОГО ЖЕ сообщения (повтор по «да» ворот) заменяет
    прежнее, а не добавляет второе; чтения старше окна уходят. `fu` — `file_unique_id` снимка:
    один и тот же снимок, присланный дважды или пересланный, — один свидетель."""
    st = clean(state)
    if not isinstance(rd, dict) or digits(rd.get("d")) is None:
        return st
    k = str(topic_id)
    rows = [r for r in st["readings"].get(k, [])
            if r.get("mid") != mid and now - _ts(r) <= WINDOW_S]
    rows.append({"d": digits(rd["d"]), "series": rd.get("series"), "province": rd.get("province"),
                 "mid": mid, "grp": str(group if group else mid), "fu": fu or None, "ts": float(now)})
    st["readings"][k] = rows[-KEEP_PER_TOPIC:]
    return st


def next_seq(state, floor=0):
    """Новый номер карточки (адрес кнопок) — не ниже `floor` (руки дают миллисекунды часов).

    Номер растёт и после ПОТЕРИ памяти: прежний счётчик с нуля выдал бы новой карточке номер старой,
    и кнопка старой карточки исполнила бы новую (ревью r2, S3)."""
    st = clean(state)
    try:
        fl = int(floor)
    except (TypeError, ValueError):
        fl = 0
    st["seq"] = max(st["seq"] + 1, fl)
    return st, st["seq"]


def with_card(state, v, n, now, chat_id=None):
    """Карточка заводится ДО отправки (место занято — вторая сверка той же темы её видит); куда она
    легла, дописывает `with_card_msg` после отправки."""
    st = clean(state)
    st["cards"][str(v["topic"])] = {"n": int(n), "kind": v["kind"], "topic": v["topic"], "chat": chat_id,
                                    "name": v["name"], "proposed": v.get("proposed"), "d": v["d"],
                                    "g": v.get("g"), "mids": list(v.get("mids") or []), "ts": float(now),
                                    "msg": None, "msg_chat": None}
    return st


def with_card_msg(state, topic_id, n, mid, chat):
    """Где карточка легла (сообщение, чат) — законное место нажатия её кнопок."""
    st = clean(state)
    c = st["cards"].get(str(topic_id))
    if c and c.get("n") == n:
        c["msg"], c["msg_chat"] = mid, (chat or None)
    return st


def with_warned(state, topic_id, now):
    st = clean(state)
    st["warned"][str(topic_id)] = float(now)
    return st


def without_card(state, topic_id, n=None):
    """Снять карточку темы; с `n` — только если висит именно она (а не уже заменившая её)."""
    st = clean(state)
    c = st["cards"].get(str(topic_id))
    if c is not None and (n is None or c.get("n") == n):
        st["cards"].pop(str(topic_id), None)
    return st


def with_declined(state, card, now):
    """«Оставить»: при ЭТОМ имени и ЭТОМ номере на байке тема больше не спрашивается. Сменится
    имя темы или чтения сойдутся на другом номере — вопрос снова законен."""
    st = without_card(state, card.get("topic"))
    st["declined"][str(card.get("topic"))] = {"d": card.get("d"), "name": card.get("name"), "ts": float(now)}
    return st


def find_card(state, n):
    """Карточка по номеру кнопки → (тема, карточка) либо (None, None)."""
    st = clean(state)
    for k, c in st["cards"].items():
        if c.get("n") == n:
            return k, c
    return None, None


# ============================ РЕШЕНИЕ ============================

def _witnesses(rows):
    """Чтения → независимые свидетели: альбом (одна отправка) и один и тот же снимок (`fu`) сливаются
    в одного. → список (самый ранний ts свидетеля)."""
    groups = []                                  # [{"keys": set, "ts": float}]
    for r in rows:
        keys = {("g", r.get("grp") or str(r.get("mid")))}
        if r.get("fu"):
            keys.add(("f", r.get("fu")))
        hit = [g for g in groups if g["keys"] & keys]
        merged = {"keys": set(keys), "ts": _ts(r)}
        for g in hit:
            merged["keys"] |= g["keys"]
            merged["ts"] = min(merged["ts"], g["ts"])
            groups.remove(g)
        groups.append(merged)
    return sorted(g["ts"] for g in groups)


def _judge(st, topic_id, name, book, now, src, others):
    """Решение по памяти БЕЗ учёта висящей карточки (её судит `verdict` / `card_valid`)."""
    v = {"kind": None, "why": FEW, "topic": topic_id, "name": name or "", "d": None,
         "t": topic_plate(name), "g": (book or {}).get("d"), "book": book, "mids": [], "proposed": None,
         "detail": ""}
    k = str(topic_id)
    rows = [r for r in st["readings"].get(k, []) if now - _ts(r) <= WINDOW_S]
    seen = sorted({digits(r.get("d")) for r in rows})
    if len(seen) > 1:
        v.update(why=SPLIT, detail="прочитано: " + ", ".join(seen))
        return v
    wit = _witnesses(rows)
    if len(wit) < NEED or wit[-1] - wit[0] < MIN_GAP_S:
        return v
    d = seen[0]
    last = max(rows, key=_ts)
    v.update(d=d, mids=sorted({r.get("mid") for r in rows if r.get("mid") is not None}),
             series=last.get("series"), province=last.get("province"))
    if src == SRC_MANUAL:
        v["why"] = MANUAL
        return v
    if not name_trusted(name, src, book):
        bn = (book or {}).get("name")
        v.update(why=UNTRUSTED, detail=f"имя «{name or '—'}» (источник: {src or 'неизвестен'}) "
                                       + (f"не совпадает с именем из зелёной книги «{bn}»" if bn
                                          else "и зелёной книги по теме нет"))
        return v
    t, g = v["t"], v["g"]
    if t is None:
        v["why"] = NO_TOPIC_PLATE
        return v
    if d == t:
        if g is None:
            v["why"] = SAME_NO_BOOK
        elif g == d:
            v["why"] = SAME
        else:
            warned = st["warned"].get(k)
            if warned is not None and now - warned < WARN_EVERY_S:
                v["why"] = WARN_RECENT
            else:
                v.update(kind=KIND_WARN, why=WARN)
        return v
    if d in ENGINE_CC:
        v["why"] = ENGINE
        return v
    for label, x in (("имени темы", t), ("книги", g)):
        if x and x != d and _part(d, x):
            v.update(why=PARTIAL, detail=f"{d} ↔ {x} ({label})")
            return v
        if x and _near(d, x):
            v.update(why=NEAR, detail=f"{d} ↔ {x} ({label})")
            return v
    other = (others or {}).get(d)
    if other is not None:
        v.update(why=OTHER_BIKE, detail=f"номер {d} — у темы {other}")
        return v
    dec = st["declined"].get(k)
    if dec and dec.get("d") == d and dec.get("name") == name:
        v["why"] = DECLINED
        return v
    v.update(kind=KIND_RENAME, why=RENAME, proposed=propose(name, d))
    return v


def verdict(state, topic_id, name, book, now, on=True, src=None, others=None):
    """Что делать с темой → {kind: "rename" | "warn" | None, why, detail, d, t, g, mids, proposed,
    drop_card, …}.

    `name` — имя, которым бот зовёт байк темы; `book` — `book_entry` (None = книги по теме нет);
    `src` — откуда у бота это имя (`SRC_*` либо прежняя метка; None = неизвестно); `others` —
    `fleet_numbers` (номера других тем парка).

    Висящая карточка темы: та же правка (номер, имя, предложение) и моложе 7 суток → `PENDING`;
    иначе `drop_card=True` — нынешние чтения её не подтверждают (номер сменился, сошёлся с именем,
    имени больше не верим), и руки её снимают, а решение идёт как без неё."""
    if not on:
        return {"kind": None, "why": OFF, "topic": topic_id, "name": name or "", "d": None,
                "t": topic_plate(name), "g": (book or {}).get("d"), "book": book, "mids": [],
                "proposed": None, "detail": ""}
    st = clean(state)
    k = str(topic_id)
    card = st["cards"].pop(k, None)
    v = _judge(st, topic_id, name, book, now, src, others)
    if card is not None:
        same = (v["kind"] == KIND_RENAME and v["d"] == card.get("d") and v["name"] == card.get("name")
                and v["proposed"] == card.get("proposed"))
        if same and now - _ts(card) <= CARD_TTL_S:
            v.update(kind=None, why=PENDING)
        else:
            v["drop_card"] = True
    return v


def card_valid(state, card, name, book, now, src=None, others=None):
    """Можно ли ИСПОЛНИТЬ карточку сейчас (нажатие владельца) → (да/нет, почему словами).

    Карточку проверяют в момент нажатия, а не верят ей: за дни, пока она висела, на байк могли
    поставить верную табличку, тему могли переименовать, привязать руками. Исполняется только та,
    что моложе 7 суток и которую нынешние чтения повторили бы слово в слово."""
    if not isinstance(card, dict):
        return False, "карточки нет"
    if now - _ts(card) > CARD_TTL_S:
        return False, CARD_OLD
    if (name or "") != card.get("name"):
        return False, f"тема уже зовётся «{name or '—'}»"
    st = without_card(state, card.get("topic"))
    v = _judge(st, card.get("topic"), name, book, now, src, others)
    if v["kind"] != KIND_RENAME:
        return False, v["why"] + (f" ({v['detail']})" if v.get("detail") else "")
    if v["d"] != card.get("d") or v["proposed"] != card.get("proposed"):
        return False, f"чтения теперь дают {v['d']}, а карточка предлагала {card.get('d')}"
    return True, ""


# ============================ СЛОВА ============================

def _book_line(v):
    b = v.get("book")
    if not b:
        return "Зелёная книга: по этой теме записи нет — сверить нечем"
    plate = " ".join(x for x in (b.get("series"), b.get("d")) if x)
    return f"Зелёная книга: {plate}" + (f" ({b['province']})" if b.get("province") else "")


def _seen_line(v, chat_id):
    mids = v.get("mids") or []
    links = [msg_link(chat_id, v.get("topic"), m) for m in mids]
    plate = " ".join(x for x in (v.get("series"), v.get("d")) if x)
    out = f"На байке: {plate}" + (f" (сообщения {', '.join(str(m) for m in mids)})" if mids else "")
    if any(links):
        out += "\n" + "\n".join(x for x in links if x)
    return out


def card_text(v, chat_id=None):
    """Текст карточки владельцу. Карточка уходит ТОЛЬКО владельцу и никогда — в тему байка."""
    g = v.get("g")
    if v.get("kind") == KIND_RENAME:
        lines = ["🔢 Номер на байке не совпадает с именем темы",
                 f"Тема {v.get('topic')}: «{v.get('name')}»",
                 _seen_line(v, chat_id),
                 _book_line(v),
                 f"Предлагаю имя: «{v.get('proposed')}»"]
        if g is not None and g != v.get("d"):
            lines.append(f"⚠️ Номер на байке не совпадает с зелёной книгой ({g})")
        elif g is not None:
            lines.append(f"✅ Номер на байке совпадает с зелёной книгой ({g})")
        # что сделает нажатие, кроме имени (ревью r2, S10)
        lines.append("После переименования: в теме появится служебная строка Telegram о новом имени; бот "
                     f"будет звать байк «{v.get('proposed')}»" + (
                         f" и писать ТО в Лист1 по номеру {v.get('d')} — в строку книги {g} их сведёт только "
                         f"карта старых номеров моста (v96); нет в ней {v.get('d')} — запись строку не найдёт."
                         if g is not None and g != v.get("d") else "."))
        lines.append("Переименовать тему — бот будет звать байк новым именем; Оставить — больше не спрошу "
                     "про этот номер при этом имени.")
        return "\n".join(lines)
    if v.get("kind") == KIND_WARN:
        return "\n".join([f"⚠️ Номер на байке не совпадает с зелёной книгой ({g})",
                          f"Тема {v.get('topic')}: «{v.get('name')}» — имя темы совпадает с номером на байке",
                          _seen_line(v, chat_id),
                          _book_line(v),
                          "Переименовывать нечего. Сверить табличку или книгу руками; "
                          "напомню не раньше чем через 7 дней."])
    return ""
