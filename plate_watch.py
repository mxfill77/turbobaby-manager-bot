# -*- coding: utf-8 -*-
"""НОМЕР НА БАЙКЕ ↔ ИМЯ ТЕМЫ ↔ ЗЕЛЁНАЯ КНИГА (25.10.2026, PLATEWATCH2510).

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
  * что делать с темой (`verdict`): карточка «переименовать», предупреждение без переименования
    или ничего — и почему, словами;
  * текст карточки (`card_text`) и мелкие правки памяти (`with_*`).

ПОРОГИ — из слова задания 25.10, а не подобраны:
  * ДВА чтения из РАЗНЫХ отправок за 14 суток (`NEED`, `WINDOW_S`). Одно чтение — ничего: модель
    зрения ошибается в цифре (частые пары 1↔7, 0↔8, 5↔6, 3↔8 — те же, что у одометра), и одна
    ошибка не смеет переименовать тему. Альбом — ОДНА отправка: снимки одного альбома сделаны в
    одну минуту с одного места, и их ошибка в одной цифре — одна ошибка, а не два свидетеля;
  * предупреждение «тема = байк, но не книга» — не чаще раза в 7 суток на тему (`WARN_EVERY_S`);
  * висящая карточка держит тему 7 суток (`CARD_TTL_S`): владелец не ответил — через неделю
    придёт свежая, а не каждая следующая фотография.

НАПРАВЛЕНИЕ СОМНЕНИЯ — В МОЛЧАНИЕ, и это обратно замку подсказок НАМЕРЕННО. Там молчание лишало
человека совета; здесь любая карточка предлагает переименовать тему, то есть сменить имя байка,
которым бот пишет в Лист1. Поэтому любая дырка (чтение смазано · чтения расходятся · в имени темы
нет номера · память не читается) даёт «ничего», а не карточку. Не угадываем.

ГРАНИЦА, КОТОРУЮ ДЕРЖИТ УСТРОЙСТВО: импортов НОЛЬ (страж в `tests/test_plate_watch.py`). Время,
диск, сеть, Telegram и память приносят руки (`splinter._plate_*`).
"""

# --- исходы (словами, а не булевыми) ---------------------------------------------------
OFF = "наблюдение выключено (PLATE_WATCH=0)"
FEW = "мало чтений: нужно два из разных отправок за 14 суток"
SPLIT = "чтения расходятся поровну — не гадаем"
NO_TOPIC_PLATE = "в имени темы нет номера последним словом — сравнивать не с чем"
SAME = "номер на байке совпадает с именем темы и с зелёной книгой"
SAME_NO_BOOK = "номер на байке совпадает с именем темы; зелёной книги по теме нет"
PENDING = "по теме уже висит карточка — вторую не шлём"
DECLINED = "владелец нажал «Оставить» при этом имени и этом номере"
WARN_RECENT = "предупреждение по теме уже было за 7 суток"
RENAME = "номер на байке не совпадает с именем темы"
WARN = "номер на байке совпадает с именем темы, но не с зелёной книгой"

KIND_RENAME = "rename"
KIND_WARN = "warn"

NEED = 2                        # согласных чтений из разных отправок
WINDOW_S = 14 * 86400           # окно согласия
WARN_EVERY_S = 7 * 86400        # предупреждение без переименования — не чаще
CARD_TTL_S = 7 * 86400          # сколько висящая карточка держит тему
KEEP_PER_TOPIC = 12             # чтений в памяти на тему (старше окна уходят и так)

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
    """Строка зелёной книги по номеру темы из `greenbook_plates.json` → {d, series, province, name}
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
    """Память в каноническом виде: всё, что не похоже на неё, отбрасывается, а не чинится."""
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


def add_reading(state, topic_id, rd, mid, group, now):
    """Положить чтение в память темы. Повтор ТОГО ЖЕ сообщения (повтор по «да» ворот) заменяет
    прежнее, а не добавляет второе; чтения старше окна уходят."""
    st = clean(state)
    if not isinstance(rd, dict) or digits(rd.get("d")) is None:
        return st
    k = str(topic_id)
    rows = [r for r in st["readings"].get(k, [])
            if r.get("mid") != mid and now - _ts(r) <= WINDOW_S]
    rows.append({"d": digits(rd["d"]), "series": rd.get("series"), "province": rd.get("province"),
                 "mid": mid, "grp": str(group if group else mid), "ts": float(now)})
    st["readings"][k] = rows[-KEEP_PER_TOPIC:]
    return st


def next_seq(state):
    """Новый номер карточки (адрес кнопок). Номера не повторяются и после перезапуска."""
    st = clean(state)
    st["seq"] += 1
    return st, st["seq"]


def with_card(state, v, n, now, chat_id=None):
    st = clean(state)
    st["cards"][str(v["topic"])] = {"n": int(n), "kind": v["kind"], "topic": v["topic"], "chat": chat_id,
                                    "name": v["name"], "proposed": v.get("proposed"), "d": v["d"],
                                    "g": v.get("g"), "mids": list(v.get("mids") or []), "ts": float(now)}
    return st


def with_warned(state, topic_id, now):
    st = clean(state)
    st["warned"][str(topic_id)] = float(now)
    return st


def without_card(state, topic_id):
    st = clean(state)
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

def verdict(state, topic_id, name, book, now, on=True):
    """Что делать с темой → {kind: "rename" | "warn" | None, why, d, t, g, mids, proposed, …}.

    `name` — имя, которым бот зовёт байк темы; `book` — `book_entry` (None = книги по теме нет)."""
    v = {"kind": None, "why": OFF, "topic": topic_id, "name": name or "", "d": None,
         "t": topic_plate(name), "g": (book or {}).get("d"), "book": book, "mids": [], "proposed": None}
    if not on:
        return v
    st = clean(state)
    k = str(topic_id)
    rows = [r for r in st["readings"].get(k, []) if now - _ts(r) <= WINDOW_S]
    by = {}                                     # номер → {отправка: (mid, чтение)}
    for r in rows:
        by.setdefault(digits(r.get("d")), {})[r.get("grp") or str(r.get("mid"))] = (r.get("mid"), r)
    ranked = sorted(by.items(), key=lambda kv: -len(kv[1]))
    if not ranked or len(ranked[0][1]) < NEED:
        v["why"] = FEW
        return v
    if len(ranked) > 1 and len(ranked[1][1]) == len(ranked[0][1]):
        v["why"] = SPLIT
        return v
    d, sends = ranked[0]
    last = max((r for _mid, r in sends.values()), key=_ts)
    v.update(d=d, mids=sorted(m for m, _r in sends.values() if m is not None),
             series=last.get("series"), province=last.get("province"))
    t, g = v["t"], v["g"]
    if t is None:
        v["why"] = NO_TOPIC_PLATE
        return v
    if d != t:
        card = st["cards"].get(k)
        if card and now - _ts(card) <= CARD_TTL_S:
            v["why"] = PENDING
            return v
        dec = st["declined"].get(k)
        if dec and dec.get("d") == d and dec.get("name") == name:
            v["why"] = DECLINED
            return v
        v.update(kind=KIND_RENAME, why=RENAME, proposed=propose(name, d))
        return v
    if g is None:
        v["why"] = SAME_NO_BOOK
        return v
    if g == d:
        v["why"] = SAME
        return v
    warned = st["warned"].get(k)
    if warned is not None and now - warned < WARN_EVERY_S:
        v["why"] = WARN_RECENT
        return v
    v.update(kind=KIND_WARN, why=WARN)
    return v


# ============================ СЛОВА ============================

def _book_line(v):
    b = v.get("book")
    if not b:
        return "Зелёная книга: по этой теме записи нет"
    plate = " ".join(x for x in (b.get("series"), b.get("d")) if x)
    return f"Зелёная книга: {plate}" + (f" ({b['province']})" if b.get("province") else "")


def _seen_line(v, chat_id):
    mids = v.get("mids") or []
    links = [msg_link(chat_id, v.get("topic"), m) for m in mids]
    plate = " ".join(x for x in (v.get("series"), v.get("d")) if x)
    out = f"На байке: {plate} (сообщения {', '.join(str(m) for m in mids)})"
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
        if g is None:
            lines.append("Сверить с зелёной книгой нечем — записи по теме нет.")
        elif g != v.get("d"):
            lines.append(f"⚠️ Номер на байке не совпадает с зелёной книгой ({g})")
        else:
            lines.append(f"✅ Номер на байке совпадает с зелёной книгой ({g})")
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
