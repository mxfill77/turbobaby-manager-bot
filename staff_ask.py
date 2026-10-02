"""Вопрос сотрудникам офиса (02.10.2026, задание Штаба 0119-77t.0210, SPLDELIVERYASK0210).

Правила владельца (узел мозга business_rules, живое чтение 02.10):
  30.09.2026-4 — вопрос о байке задаётся в теме этого байка («Обслуживание»); в Delivery cooperation —
                 короткая просьба посмотреть вопрос с уровнем срочности («для ясности» / «клиент сейчас
                 интересуется»); тон вежливый, без давления — сотрудники офиса бывают заняты;
  30.09.2026-6 — не могут ответить или сложно → агент уточняет в «TurboBaby · Агенты»;
  30.09.2026-7 п.1 — о ценах, бронях и сложностях, которые решают менеджеры, — сразу в «Агенты»;
                 п.2 — ответы идут в память: у записи автор, время и источник.
Обращение — только @username из `splinter.THAI_HANDLES` (правило 28.06), тексты тайский + русский.

Выключатель `SPLINTER_ASK_STAFF` (по умолчанию ВЫКЛЮЧЕН): выкл. → ни одного поста, ни одной записи в
мозг, файл состояния не создаётся. Чистые части — здесь; Telegram и мост — в `splinter.staff_ask_*`.
Не бросает наружу: сбой → строка-причина в итоге, прежний путь.
"""
import hashlib
import json
import os
import time

FLAG = "SPLINTER_ASK_STAFF"
# СРОК ОТВЕТА 3 ч. Чем обоснован: срок вопроса L о пробеге — тоже 3 ч, и на нём сотрудники офиса
# ответили в срок 20 раз, медиана ≈ 5 мин, максимум 1 ч 37 мин (SPLAGENTMAP0110); окно зова Пыма
# решателем — те же 3 ч (`topic_decider.CALL_WINDOW_S_DEFAULT`). Меньше — давить на занятых
# (правило 30.09.2026-4 п.3), больше — клиент ждёт дольше рабочего полудня. Ручка — `SPLINTER_ASK_STAFF_WAIT_S`.
WAIT_S_DEFAULT = 3 * 3600
DOC_DEFAULT = "splinter_staff_answers"     # узел мозга для ответов (ключ манифеста; заводится ДО включения)

KIND_BIKE = "байк"                          # состояние и готовность байка → сотрудники офиса
KINDS_MANAGERS = ("цена", "бронь", "сложность")   # решают менеджеры и руководство → «Агенты» (30.09.2026-7 п.1)
KINDS = (KIND_BIKE,) + KINDS_MANAGERS

URG_CLARITY = "для ясности"
URG_CLIENT = "клиент интересуется"
URGENCY = {
    URG_CLARITY: ("🟢 ไม่รีบครับ ถามเพื่อความชัดเจน", "🟢 не срочно — для ясности"),
    URG_CLIENT: ("🟠 ตอนนี้ลูกค้ากำลังสนใจอยู่ครับ", "🟠 клиент сейчас интересуется"),
}

PLACE_TOPIC, PLACE_DELIVERY, PLACE_AGENTS = "тема байка", "Delivery cooperation", "Агенты"


def enabled():
    """`SPLINTER_ASK_STAFF=1` → вопросы сотрудникам включены. Нет флага / 0 → выключены (по умолчанию)."""
    return str(os.getenv(FLAG, "0")).strip().lower() in ("1", "true", "yes", "on")


def wait_s():
    try:
        v = float(os.getenv("SPLINTER_ASK_STAFF_WAIT_S", "") or WAIT_S_DEFAULT)
        return v if v > 0 else WAIT_S_DEFAULT
    except (TypeError, ValueError):
        return WAIT_S_DEFAULT


def doc_name():
    return (os.getenv("SPLINTER_ASK_STAFF_DOC") or DOC_DEFAULT).strip() or DOC_DEFAULT


def state_path():
    return os.getenv("SPLINTER_ASK_STAFF_STATE") or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "staff_ask_state.json")


def norm_kind(kind):
    k = str(kind or "").strip().lower()
    return k if k in KINDS else KIND_BIKE


def norm_urgency(urg):
    u = str(urg or "").strip().lower()
    return URG_CLIENT if ("клиент" in u or "client" in u) else URG_CLARITY


def place_for(kind):
    """Место вопроса по виду: байк → тема байка (+ просьба в Delivery); цена/бронь/сложность → «Агенты»."""
    return PLACE_AGENTS if norm_kind(kind) in KINDS_MANAGERS else PLACE_TOPIC


def _handles_line(handles):
    hs = [h if str(h).startswith("@") else "@" + str(h) for h in (handles or []) if str(h).strip("@ ")]
    return " ".join(hs)


def compose_topic_question(handles, bike, q_th, q_ru):
    """ОДИН пост в теме байка: тайский и русский, обращение @username, вежливо и без давления."""
    h = _handles_line(handles)
    return (f"🐀 Splinter\n"
            f"🇹🇭 {h} สวัสดีครับ ขอสอบถามเรื่องรถ {bike} หน่อยครับ\n"
            f"❓ {q_th}\n"
            f"ว่างเมื่อไหร่ค่อยตอบได้เลยครับ — กดตอบกลับ (reply) ที่ข้อความนี้ ขอบคุณครับ 🙏\n"
            f"🇷🇺 {h}, здравствуйте! Вопрос по байку {bike}:\n"
            f"❓ {q_ru}\n"
            f"Ответьте, когда будет минутка, — реплаем на это сообщение. Спасибо 🙏")


def compose_delivery_request(handles, bike, urgency, link=""):
    """Короткая просьба в Delivery cooperation: посмотреть вопрос в теме байка + срочность одной строкой."""
    h = _handles_line(handles)
    th, ru = URGENCY[norm_urgency(urgency)]
    tail = f"\n🔗 {link}" if link else ""
    return (f"🐀 Splinter\n"
            f"🇹🇭 {h} รบกวนช่วยดูคำถามเรื่องรถ {bike} ในหัวข้อของรถคันนี้ด้วยนะครับ\n{th}\n"
            f"🇷🇺 {h}, пожалуйста, посмотрите вопрос по байку {bike} в его теме.\n{ru}{tail}")


def compose_agents_question(kind, bike, q_ru, why="", link=""):
    """Вопрос в «TurboBaby · Агенты» (группа русскоязычная): вид, байк, вопрос, почему сюда."""
    head = f"🐀 Splinter · вопрос ({norm_kind(kind)})"
    lines = [head]
    if bike:
        lines.append(f"Байк: {bike}")
    lines.append(f"❓ {q_ru}")
    if why:
        lines.append(why)
    if link:
        lines.append(f"🔗 {link}")
    lines.append("Ответ — реплаем на это сообщение, он ляжет в память Splinter с источником.")
    return "\n".join(lines)


def topic_link(chat_id, topic_id, mid):
    """Ссылка на сообщение темы форума: https://t.me/c/<id без -100>/<тема>/<mid>."""
    s = str(chat_id)
    if not s.startswith("-100") or mid is None:
        return ""
    return f"https://t.me/c/{s[4:]}/{topic_id}/{mid}" if topic_id else f"https://t.me/c/{s[4:]}/{mid}"


# ---------------------------------------------------------------- состояние (на диске, переживает рестарт)
def load(path=None):
    p = path or state_path()
    try:
        with open(p, encoding="utf-8") as fh:
            st = json.load(fh)
        if isinstance(st, dict) and isinstance(st.get("asks"), dict):
            st.setdefault("by_mid", {})
            return st
    except FileNotFoundError:
        pass
    except Exception:
        pass
    return {"asks": {}, "by_mid": {}}


def save(st, path=None):
    p = path or state_path()
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(st, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, p)


def _key(kind, bike, q_ru):
    return hashlib.sha1(f"{norm_kind(kind)}|{bike}|{str(q_ru).strip().lower()}".encode()).hexdigest()[:12]


def _mid_key(chat, mid):
    return f"{int(chat)}:{int(mid)}"


def _open_same(st, key):
    for qid, a in st["asks"].items():
        if a.get("key") == key and a.get("status") in ("open", "escalated"):
            return qid
    return None


async def ask(send, *, kind, bike, q_ru, q_th, urgency=URG_CLARITY, handles=(), servicing_chat=None,
              topic_id=None, delivery_chat=None, agents_chat=None, reply_to=None, now=None, path=None):
    """Задать вопрос. `send(place, chat_id, text, thread_id, reply_to)` → mid | None (Telegram — снаружи).
    Возврат: {"posted": [места], "qid", "why"}. Выключено → ни одного вызова `send`, файла нет."""
    if not enabled():
        return {"posted": [], "qid": None, "why": "выключено (SPLINTER_ASK_STAFF)"}
    now = time.time() if now is None else now
    kind = norm_kind(kind)
    q_ru, q_th = str(q_ru or "").strip()[:400], str(q_th or "").strip()[:400]
    if not q_ru:
        return {"posted": [], "qid": None, "why": "нет текста вопроса"}
    st = load(path)
    key = _key(kind, bike, q_ru)
    same = _open_same(st, key)
    if same:
        return {"posted": [], "qid": same, "why": "тот же вопрос уже открыт — второго поста нет"}
    qid = f"{int(now)}-{key[:6]}"
    a = {"key": key, "kind": kind, "bike": bike or "", "q_ru": q_ru, "q_th": q_th,
         "urgency": norm_urgency(urgency), "asked_ts": now, "status": "open", "posts": {}, "answers": []}
    posted = []
    if place_for(kind) == PLACE_AGENTS:
        mid = await send(PLACE_AGENTS, agents_chat, compose_agents_question(kind, bike, q_ru), None, None)
        if mid is None:
            return {"posted": [], "qid": None, "why": "«Агенты» не приняли вопрос"}
        a["posts"]["agents"] = [agents_chat, mid]
        a["status"] = "escalated"          # вопрос уже у менеджеров — уточнять дальше некуда
        a["escalated_ts"] = now
        st["by_mid"][_mid_key(agents_chat, mid)] = qid
        posted.append(PLACE_AGENTS)
    else:
        if not q_th:
            return {"posted": [], "qid": None, "why": "нет тайского текста — сотрудникам офиса не пишем"}
        if not topic_id:
            return {"posted": [], "qid": None, "why": f"тема байка {bike or '?'} не найдена"}
        mid = await send(PLACE_TOPIC, servicing_chat, compose_topic_question(handles, bike, q_th, q_ru),
                         topic_id, reply_to)
        if mid is None:
            return {"posted": [], "qid": None, "why": "тема байка не приняла вопрос"}
        a["posts"]["question"] = [servicing_chat, mid, topic_id]
        st["by_mid"][_mid_key(servicing_chat, mid)] = qid
        posted.append(PLACE_TOPIC)
        link = topic_link(servicing_chat, topic_id, mid)
        dmid = await send(PLACE_DELIVERY, delivery_chat,
                          compose_delivery_request(handles, bike, a["urgency"], link), None, None)
        if dmid is not None:
            a["posts"]["delivery"] = [delivery_chat, dmid]
            st["by_mid"][_mid_key(delivery_chat, dmid)] = qid
            posted.append(PLACE_DELIVERY)
    st["asks"][qid] = a
    save(st, path)
    return {"posted": posted, "qid": qid, "why": ""}


def _when(ts):
    g = time.gmtime(ts)
    p = time.gmtime(ts + 7 * 3600)
    return f"{time.strftime('%Y-%m-%d %H:%M', g)} UTC ({time.strftime('%d.%m %H:%M', p)} Пхукет)"


def answer_line(qid, a, *, who, user_id, ts, place, mid, reply_to, text):
    """Строка ответа для мозга: кто, когда, где, на что — и сам ответ. Метка `[staff_ask qid#mid]` —
    ключ идемпотентности (повтор того же реплая второй строки не даёт)."""
    return (f"ОТВЕТ СОТРУДНИКА [staff_ask {qid}#{mid}] · кто: {who or '?'} (id {user_id}) · когда: {_when(ts)}"
            f" · где: {place} #{mid} ↩ на #{reply_to} · на вопрос ({a.get('kind')}, байк {a.get('bike') or '—'},"
            f" задан {_when(a.get('asked_ts') or ts)}): «{a.get('q_ru')}» · ответ: «{str(text).strip()[:600]}»"
            f" · источник: Telegram, реплай на вопрос Splinter")


def _place_of(a, chat, reply_to):
    for name, rec in (a.get("posts") or {}).items():
        if rec and int(rec[0]) == int(chat) and int(rec[1]) == int(reply_to):
            return {"question": PLACE_TOPIC, "delivery": PLACE_DELIVERY, "agents": PLACE_AGENTS}.get(name, name)
    return "?"


def on_reply(brain_append, *, chat, reply_to, mid, user_id, username, is_bot, text, ts=None, path=None):
    """Реплай человека на пост вопроса → строка в мозг с источником. `brain_append(line)` → (ok, why).
    Возврат: {"recorded": bool, "qid", "why"}. Выключено / не наш пост / бот / пусто → ничего не пишется."""
    if not enabled():
        return {"recorded": False, "qid": None, "why": "выключено"}
    if reply_to is None or is_bot or not str(text or "").strip():
        return {"recorded": False, "qid": None, "why": "не ответ человека"}
    st = load(path)
    qid = st["by_mid"].get(_mid_key(chat, reply_to))
    a = st["asks"].get(qid) if qid else None
    if a is None:
        return {"recorded": False, "qid": None, "why": "не реплай на вопрос Splinter"}
    if any(int(x.get("mid", -1)) == int(mid) for x in a["answers"]):
        return {"recorded": False, "qid": qid, "why": "этот ответ уже записан"}
    ts = time.time() if ts is None else ts
    who = ("@" + username) if username else ""
    line = answer_line(qid, a, who=who, user_id=user_id, ts=ts, place=_place_of(a, chat, reply_to),
                       mid=mid, reply_to=reply_to, text=text)
    ok, why = brain_append(line)
    a["answers"].append({"mid": mid, "user_id": user_id, "who": who, "ts": ts, "chat": chat,
                         "brain": "ok" if ok else f"не принят: {why}"})
    a["status"] = "answered"
    save(st, path)
    return {"recorded": bool(ok), "qid": qid, "why": "" if ok else f"мозг не принял: {why}", "line": line}


def due(st, now, wait):
    """Вопросы к сотрудникам без ответа дольше срока и ещё не уточнённые в «Агентах»."""
    return [qid for qid, a in st["asks"].items()
            if a.get("status") == "open" and "question" in (a.get("posts") or {})
            and now - float(a.get("asked_ts") or now) >= wait]


async def tick(send, *, agents_chat, now=None, path=None):
    """Нет ответа к сроку → ОДИН вопрос в «Агенты» на вопрос. Возврат — число уточнений."""
    if not enabled():
        return 0
    now = time.time() if now is None else now
    st = load(path)
    n = 0
    for qid in due(st, now, wait_s()):
        a = st["asks"][qid]
        q = a["posts"]["question"]
        link = topic_link(q[0], q[2] if len(q) > 2 else None, q[1])
        why = f"Сотрудники офиса не ответили за {int(wait_s() // 3600)} ч (срочность: {a.get('urgency')})."
        mid = await send(PLACE_AGENTS, agents_chat,
                         compose_agents_question(a["kind"], a["bike"], a["q_ru"], why, link), None, None)
        if mid is None:
            continue                       # не принято — следующим тактом
        a["posts"]["agents"] = [agents_chat, mid]
        a["status"] = "escalated"
        a["escalated_ts"] = now
        st["by_mid"][_mid_key(agents_chat, mid)] = qid
        n += 1
    if n:
        save(st, path)
    return n
