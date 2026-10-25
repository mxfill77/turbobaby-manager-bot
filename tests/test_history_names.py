"""ИСТОРИЯ ОБСЛУЖИВАНИЯ НАЗЫВАЕТ РАБОТУ, ДЕНЬ И КИЛОМЕТРЫ (25.10.2026, HISTNAMES2510).

ЖИВЫЕ СЛУЧАИ, на которых стоят голдены (чат «Обслуживание» -1002751134848):
  * XADV 750 BLACK 3902, тема 82: 13.10 владелец — «Услуга называется,чистка тормозных
    цилиндров»; решатель «записать» → `sp_confirm_from_brain` → заявка «прочие» БЕЗ слов;
    21.10 «Сделано: прочие работы», в историю «прочие работы — 29859 км» — ни слова, ни дня.
  * тема 13072, 21.10: «Замена масла на 1200» → карточка «Сделано: прочие работы».
  * NMAX RED WHITE 9548: «замена аккумулятора» → «прочие работы — 36474 км» (14.08).
  * VULCAN 650 S 5065: слова Пыма «заменили моторное масло и топливный фильтр… цепь
    отрегулировали и смазали» — фраза с «фильтром» внутри, живой классификатор её не узнаёт.

Что доказывается:
  (1) СТРОКА   «<работа> — <км> км · ДД.ММ.ГГГГ»: дата ПОСЛЕ км, слова режутся первыми под
               NOTE_CAP, живой `_SVC_HIST_RE` строку по-прежнему разбирает;
  (2) СЛОВА    из одной фразы человека — да; голое число, план, вопрос, «готово» — нет;
  (3) ХРАНЕНИЕ `sp_confirm_from_brain` кладёт слова в ноту заявки на ОБОИХ путях (с одометром и
               без), карточка Пыму и просьба одометра называют работу словами;
  (4) ЗАПИСЬ   сквозь живые двери: история получает слова и день работы, квитанция — слова;
  (5) ЯРЛЫКА НЕТ «прочие» без единого слова в историю не идут: заявка открыта, «какие работы
               сделали?» уходит один раз; слова пришли — кнопка Пыму, и строка ложится;
  (6) ОТКАТ    `WORK_NAME=0` → прежний ярлык байт-в-байт.

Каждая проверка и каждое действие обёрнуты: на коде ДО правки (замер «до/после» через
`git stash`) сьют не падает на первой отсутствующей функции, а честно считает красные.
"""
import asyncio
import datetime
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != "/root/turbobaby-manager-bot"] \
    if ROOT != "/root/turbobaby-manager-bot" else sys.path
sys.path.insert(0, ROOT)
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ.setdefault("NOTIFY_COUNT_FILE", "/tmp/tb_histnames_notify_count.txt")
os.environ.pop("WORK_NAME", None)
os.environ["SERVICE_UNDO"] = "0"            # соседний механизм (кнопка отмены) — не предмет сьюта
os.environ["BATCH_ODO"] = "0"               # третья кнопка карточки — не предмет сьюта

import work_name as W
import splinter as S
import service_receipt

CHAT = -1002751134848
TOPIC = 82
BIKE = "XADV 750 BLACK PHUKET 3902"

#: ДОСЛОВНО из живых сообщений (см. шапку).
W_3902 = "чистка тормозных цилиндров"
W_1200 = "Замена масла на 1200"
W_9548 = "замена аккумулятора"
W_VULCAN = "заменили моторное масло и топливный фильтр… цепь отрегулировали и смазали"

OK = FAIL = 0


def check(name, fn):
    """Проверка — функция без аргументов: исключение внутри = FAIL, а не обрыв сьюта."""
    global OK, FAIL
    try:
        cond = bool(fn())
    except Exception as e:
        cond = False
        name += f"  [исключение: {type(e).__name__}: {e}]"
    if cond:
        OK += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}")


def act(fn):
    """Действие (вызов живой двери): упало — сказано вслух, проверки ниже честно покраснеют."""
    try:
        return fn()
    except Exception as e:
        print(f"  ERR   действие упало: {type(e).__name__}: {e}")
        return None


def parse(note):
    """Живой разбор карточки: `_SVC_HIST_RE` через `_parse_service_items`."""
    out = S._parse_service_items([{"notes": note}], limit=6)
    return out[0] if out else None


# ═══════════════ (1) СТРОКА ИСТОРИИ: ДАТА ПОСЛЕ КМ, РАЗБОР ЦЕЛ ═══════════════
print("\n(1) строка истории: «<работа> — <км> км · ДД.ММ.ГГГГ», разбор карточки цел")

check("3902: строка со словами, км и днём работы",
      lambda: W.note_line(W_3902, 29859, "2026-10-13") == "чистка тормозных цилиндров — 29859 км · 13.10.2026")
check("3902: живой _SVC_HIST_RE разбирает строку с датой (работа и км)",
      lambda: parse(W.note_line(W_3902, 29859, "2026-10-13")) == {"work": W_3902, "km": "29859"})
check("день из created_at моста (ISO с временем) тоже читается",
      lambda: W.note_line("x", 1, "2026-10-13T07:59:40Z").endswith(" · 13.10.2026"))
check("день уже человеческий — не портится", lambda: W.date_human("13.10.2026") == "13.10.2026")
check("нет дня → строка БАЙТ-В-БАЙТ прежняя",
      lambda: W.note_line(W_9548, 36474, "") == "замена аккумулятора — 36474 км")
check("мусор вместо дня датой не становится",
      lambda: W.note_line(W_9548, 36474, "вчера") == "замена аккумулятора — 36474 км")

LONG = "замена аккумулятора " + "и подрамника " * 30
check("длинные слова урезаны под NOTE_CAP", lambda: len(W.note_line(LONG, 29859, "2026-10-13")) <= W.NOTE_CAP)
check("урезаются СЛОВА: км и день целы в хвосте",
      lambda: W.note_line(LONG, 29859, "2026-10-13").endswith(" — 29859 км · 13.10.2026"))
check("урезанная строка всё ещё разбирается карточкой",
      lambda: parse(W.note_line(LONG, 29859, "2026-10-13"))["km"] == "29859")
check("history_note: слова + день",
      lambda: W.history_note("other", [W_9548], 36474, S._SP_KIND_LABEL, S._service_kind,
                             date="2026-08-14")["text"] == "замена аккумулятора — 36474 км · 14.08.2026")


# ═══════════════ (2) СЛОВА ИЗ ФРАЗЫ ЧЕЛОВЕКА ═══════════════
print("\n(2) слова из одной фразы: работа — да; число, план, вопрос, «готово» — нет")

check("«Замена масла на 1200» → «Замена масла» (предлог при числе снят)",
      lambda: W.words_from_text(W_1200) == ["Замена масла"])
check("«замена аккумулятора» → как сказано", lambda: W.words_from_text(W_9548) == [W_9548])
check("VULCAN: фраза из нескольких работ — целиком", lambda: W.words_from_text(W_VULCAN) == [W_VULCAN])
for para, want in (("Поменяли аккумулятор, пробег 36474", "Поменяли аккумулятор"),
                   ("Почистили тормозные цилиндры", "Почистили тормозные цилиндры"),
                   ("поставили новый аккумулятор 29859 км", "поставили новый аккумулятор"),
                   ("เปลี่ยนแบตเตอรี่แล้ว", "เปลี่ยนแบตเตอรี่แล้ว")):
    check(f"парафраз «{para}» → «{want}»", lambda: W.words_from_text(para) == [want])
for neg in ("29859", "пробег 29859 км", "Одометр 45220", "нужно заменить колодки",
            "Надо поменять аккумулятор", "И заменить жидкость тормозную сразу можно",
            "Скажи пожалуйста менялось масло?", "готово", "Сделал, 29859", "@Pleummmm",
            "เสร็จแล้วครับ", "ต้องเปลี่ยนผ้าเบรก", ""):
    check(f"негатив «{neg}» → слов нет", lambda: W.words_from_text(neg) == [])


# ═══════════════ живые руки: мост, отправка ═══════════════
SENDS = []


async def _rec_send(context, *, chat_id=None, text="", message_thread_id=None, **kw):
    SENDS.append({"text": text, "kb": kw.get("reply_markup")})


S._send = _rec_send
S._send_retry = _rec_send
S._TOPIC_BIKE_OVERRIDE[(CHAT, TOPIC)] = BIKE
S._odo_known_fresh = lambda bridge, bike, *a, **k: {"use": False, "why": "тест: свежего числа нет"}


class Ctx:
    class B:
        username = "turbobaby_manager_bot"
    bot = B()


class FakeBridge:
    """Одна строка то_заявки (как у моста: открытая по теме/байку) + история событий."""

    def __init__(self, sp=None):
        self.sp = dict(sp) if sp else None
        self.closed = False
        self.upserts, self.events = [], []

    def service_pending_get(self, chat_id, topic_id, bike):
        if self.sp is not None and not self.closed:
            return {"ok": True, "item": dict(self.sp)}
        return {"ok": False, "error": "not_found"}

    def service_pending_upsert(self, **kw):
        if self.sp is None or self.closed:
            self.sp = {"declared": "", "done": "", "status": "заявлено", "odometer": "", "note": "",
                       "created_at": "2026-10-13T07:59:40Z"}
            self.closed = False
        for k, v in kw.items():
            if v not in (None, ""):        # мост берёт поле, только если оно !== ''
                self.sp[k] = v
        self.upserts.append(dict(kw))
        return {"ok": True}

    def service_pending_close(self, **kw):
        self.closed = True
        return {"ok": True}

    def service_pending_list(self, **kw):
        return {"ok": True, "items": []}

    def add_event(self, **kw):
        self.events.append(dict(kw))
        return {"ok": True, "saved": True}

    def find_bike(self, q):
        return {"name": BIKE}

    def fleet(self, cells=False):
        return {"ok": True, "data": {"bikes": []}}

    def set_fleet_oil(self, number, oil_km, confirmed=False):
        return {"ok": True, "number": number, "old_oil": 1, "new_oil": oil_km}

    def set_fleet_service(self, number, kind, km, confirmed=False):
        return {"ok": True, "number": number, "old_km": 1, "new_km": km}

    def service_upsert(self, **kw):
        return {"ok": True}

    def service_list(self, *a, **k):
        return {"ok": True, "items": []}


def reset():
    SENDS.clear()
    for name in ("_SVC_TOKENS", "_SP_ASK_TS", "_SP_WORKS_ASK", "_SVC_SAID", "_SVC_LEDGER",
                 "_PENDING_WORKS", "_AWAITING_REPLY", "_HINT_SEEN"):
        try:
            getattr(S, name).clear()
        except Exception:
            pass                           # на коде «до» части накопителей ещё нет


def run(c):
    return asyncio.run(c)


def texts():
    return [s["text"] for s in SENDS]


def joined():
    return "\n".join(texts())


def card_token():
    """Метка кнопки «Подтвердить запись» последней карточки Пыму → данные метки."""
    for s in reversed(SENDS):
        kb = s.get("kb")
        for row in (kb.inline_keyboard if kb else []):
            for b in row:
                m = re.match(r"svc:done:(\d+)$", b.callback_data or "")
                if m:
                    return S._SVC_TOKENS.get(int(m.group(1)))
    return None


def _call_compat(fn, *a, **kw):
    """Новые именованные аргументы, а на коде «до» (их там нет) — прежняя подпись: замер «до»
    обязан мерить ПОВЕДЕНИЕ двери, а не одно лишь отсутствие параметра."""
    try:
        return run(fn(*a, **kw))
    except TypeError as e:
        if "unexpected keyword" not in str(e):
            raise
        for k in ("said", "msg_date", "work_date"):
            kw.pop(k, None)
        return run(fn(*a, **kw))


def brain(b, kind, km=None, said=None, day="2026-10-13"):
    act(lambda: _call_compat(S.sp_confirm_from_brain, Ctx(), b, CHAT, TOPIC, BIKE, kind, km,
                             said=said, msg_date=day))


def write(b, tok=None, works=None):
    tok = tok or {}
    done = tok.get("done") or S._sp_split((b.sp or {}).get("done"))
    odo = tok.get("odo") or (b.sp or {}).get("odometer") or "29859"
    r = act(lambda: _call_compat(S._sp_write_done, Ctx(), b, CHAT, TOPIC, BIKE, done, odo,
                                 confirmed_by="@Pleummmm", ceiling_ok=True, works=works,
                                 work_date=tok.get("wdate")))
    return r if r else (None, None)


def note_of(b):
    return (b.sp or {}).get("note")


# ═══════════════ (3) СЛОВА ХРАНЯТСЯ НА ОБОИХ ПУТЯХ ═══════════════
print("\n(3) sp_confirm_from_brain: слова в ноту заявки — с одометром и без")

reset(); b = FakeBridge()
brain(b, W_3902, 29859, said="Услуга называется,чистка тормозных цилиндров")
check("3902 с одометром: слова в ноте заявки", lambda: W_3902 in S._sp_works_from_note(note_of(b)))
check("3902: день работы в ноте (WDATE 13.10)", lambda: "WDATE:{2026-10-13}" in note_of(b))
check("3902: заявка ждёт Пыма", lambda: b.sp.get("status") == "ждёт_подтверждения")
check("3902: карточка Пыму называет работу словами", lambda: "Сделано: чистка тормозных цилиндров" in joined())
check("3902: ни «прочие работы», ни подменного ярлыка «тормозные колодки» в карточке",
      lambda: joined() and "прочие работы" not in joined() and "тормозные колодки" not in joined())
check("3902: день работы едет в метке кнопки", lambda: card_token().get("wdate") == "2026-10-13")

reset(); b = FakeBridge()
brain(b, W_3902, None)
check("3902 без одометра: слова в ноте", lambda: W_3902 in S._sp_works_from_note(note_of(b)))
check("3902 без одометра: заявка ждёт факт", lambda: b.sp.get("status") == "ждёт_факт")
check("3902 без одометра: просьба одометра называет работу словами",
      lambda: "Для записи (чистка тормозных цилиндров)" in joined())

reset(); b = FakeBridge()
brain(b, "замена масла", 1200, said=W_1200)
check("«Замена масла на 1200»: карточка «Сделано: моторное масло», не «прочие работы»",
      lambda: "Сделано: моторное масло" in joined() and "прочие работы" not in joined())
check("«Замена масла на 1200»: слова всё равно в ноте",
      lambda: "замена масла" in S._sp_works_from_note(note_of(b)))

reset(); b = FakeBridge()
brain(b, W_9548, 36474)
check("9548: карточка «Сделано: замена аккумулятора»", lambda: "Сделано: замена аккумулятора" in joined())

reset(); b = FakeBridge()
brain(b, W_VULCAN, 45220)
check("VULCAN: карточка несёт слова Пыма", lambda: f"Сделано: {W_VULCAN}" in joined())
check("VULCAN: «прочие работы» в карточке нет", lambda: joined() and "прочие работы" not in joined())


# ═══════════════ (4) ЗАПИСЬ СКВОЗЬ ЖИВЫЕ ДВЕРИ ═══════════════
print("\n(4) запись: история получает слова и день работы, квитанция — слова")

reset(); b = FakeBridge()
brain(b, W_3902, 29859)
written, failed = write(b, act(card_token))            # дверь кнопки: слова читаются из заявки
ev = b.events[0] if b.events else {}
check("3902: запись состоялась", lambda: written == ["pads"] and not failed)
check("3902: в историю ушло «чистка тормозных цилиндров — 29859 км · 13.10.2026»",
      lambda: ev.get("notes") == "чистка тормозных цилиндров — 29859 км · 13.10.2026")
check("3902: msg_date строки = день работы, а не день «да»", lambda: ev.get("msg_date") == "2026-10-13")
check("3902: ключ строки контентный и без даты (дедуп прежний)",
      lambda: str(ev.get("msg_id", "")).startswith("info:3902:") and "2026" not in str(ev.get("msg_id")))
check("3902: строка истории разбирается карточкой",
      lambda: parse(ev.get("notes", "")) == {"work": W_3902, "km": "29859"})
check("3902: квитанция называет работу словами",
      lambda: service_receipt.receipt(written, failed, "29859", S._svc_labels_take(CHAT, TOPIC))["ru"]
      .startswith("✅ Записано: чистка тормозных цилиндров на 29859 км"))
check("квитанция без слов (колоночная партия) — прежний словарь",
      lambda: S._svc_labels_take(CHAT, TOPIC) is S._SP_KIND_LABEL)

reset(); b = FakeBridge()
brain(b, W_VULCAN, 45220, day="2026-10-16")
write(b, act(card_token))
check("VULCAN: строка истории — слова Пыма, км и день",
      lambda: b.events[0].get("notes") == f"{W_VULCAN} — 45220 км · 16.10.2026")

# Соседняя дверь (буфер, прямая запись, партия) — тот же хвост дня.
b2, b3 = FakeBridge(), FakeBridge()
act(lambda: S._write_info_works(b2, "обслуживание", TOPIC, BIKE, [W_9548], "36474", "", msg_date="2026-08-14"))
act(lambda: S._write_info_works(b3, "обслуживание", TOPIC, BIKE, [W_9548], "36474", ""))
TODAY = datetime.datetime.now(datetime.timezone.utc).strftime("%d.%m.%Y")
check("_write_info_works: день сообщения в строке и в msg_date",
      lambda: b2.events[0]["notes"] == "замена аккумулятора — 36474 км · 14.08.2026"
      and b2.events[0]["msg_date"] == "2026-08-14")
check("_write_info_works без дня → день записи, строка не остаётся без даты",
      lambda: b3.events[0]["notes"] == f"замена аккумулятора — 36474 км · {TODAY}")
check("тот же ключ при другом дне — дедуп моста не сломан",
      lambda: b2.events[0]["msg_id"] == b3.events[0]["msg_id"])


# ═══════════════ (5) ЯРЛЫКА «ПРОЧИЕ РАБОТЫ» В ИСТОРИИ НЕТ ═══════════════
print("\n(5) «прочие» без слов: не пишутся, заявка открыта, вопрос один раз, слова → запись")

ASK = "Какие работы сделали?"

reset(); b = FakeBridge()
brain(b, "other", 29859, said="29859")                 # ключ мозга + сообщение из одного числа
check("ключ мозга + голое число: карточки «Сделано: прочие работы» НЕТ",
      lambda: "Сделано: прочие работы" not in joined())
check("ключ мозга + голое число: кнопки Пыму нет", lambda: card_token() is None)
check("ключ мозга + голое число: спрошено «Какие работы сделали?»", lambda: ASK in joined())
check("заявка открыта и ждёт факт",
      lambda: b.sp.get("status") == "ждёт_факт" and "other" in S._sp_split(b.sp.get("done")))
check("пробег запомнен — второй раз его не спросят", lambda: S._sp_works_ask_odo(CHAT, TOPIC) == "29859")
n_ask = len([t for t in texts() if ASK in t])
brain(b, "other", 29859, said="29859")
check("повтор того же — вопрос не дублируется (замок повторов)",
      lambda: len([t for t in texts() if ASK in t]) == n_ask == 1)

reset(); b = FakeBridge()
brain(b, "", 29859, said="нужно заменить аккумулятор")
check("план «нужно заменить…» работой не стал: вопрос, а не карточка",
      lambda: card_token() is None and ASK in joined())

reset(); b = FakeBridge()
brain(b, "", 36474, said="Поменяли аккумулятор")
check("слов от решателя нет → «прочие» названы словами сообщения",
      lambda: "Сделано: Поменяли аккумулятор" in joined() and card_token() is not None)

reset(); b = FakeBridge()
brain(b, "wheel_paint", 36474, said="масло в норме")
check("фраза ДРУГОГО вида вид заявки не меняет и «прочие» не называет (вопрос, не масло)",
      lambda: card_token() is None and "моторное масло" not in joined() and ASK in joined())

# Дверь записи (страховка): «прочие» без слов — строки нет, вопрос, заявка жива.
LEGACY = {"declared": "other", "done": "other", "status": "ждёт_подтверждения", "odometer": "29859",
          "note": "", "created_at": "2026-10-13T07:59:40Z"}
reset(); b = FakeBridge(sp=LEGACY)
written, failed = write(b, {"done": ["other"], "odo": "29859"})
check("запись: «прочие работы» без слов в историю НЕ легли", lambda: b.events == [])
check("запись: ничего не названо записанным и ничего — потерянным", lambda: written == [] and failed == [])
check("запись: заявка снова ждёт факт", lambda: b.sp.get("status") == "ждёт_факт" and not b.closed)
check("запись: спрошено «Какие работы сделали?» с уже известным одометром",
      lambda: any(ASK in t and "29859" in t for t in texts()))


class FakeClaude:
    def __init__(self, works):
        self.works = works

    def quick(self, system, text, **kw):
        return json.dumps({"works": self.works, "mileage": None})


class U:
    username = "pym_test"
    is_bot = False
    id = 7


class Msg:
    def __init__(self, text):
        self.text, self.caption, self.photo = text, None, None
        self.chat_id, self.message_thread_id = CHAT, TOPIC
        self.date = datetime.datetime(2026, 10, 21, 9, 24, tzinfo=datetime.timezone.utc)
        self.message_id, self.from_user, self.reply_to_message = 13069, U(), None


def answer(b, words):
    SENDS.clear()
    try:
        S._SP_ASK_TS.clear()
    except Exception:
        pass
    return act(lambda: run(S.handle_service_result(Msg(words[0]), Ctx(), b, FakeClaude(words), words[0])))


# Слова пришли → кнопка Пыму с названием и запомненным пробегом → строка ложится.
reset(); b = FakeBridge()
brain(b, "other", 29859, said="29859")
took = answer(b, [W_9548])
check("ответ словами: перехвачен фазой 2", lambda: took is True)
check("ответ словами: карточка Пыму «Сделано: замена аккумулятора» на запомненном 29859",
      lambda: "Сделано: замена аккумулятора" in joined() and "Одометр 29859 км" in joined())
b.events.clear()
write(b, act(card_token))
check("ответ словами: строка истории со словами и днём ответа",
      lambda: [e.get("notes") for e in b.events] == ["замена аккумулятора — 29859 км · 21.10.2026"])

reset(); b = FakeBridge()
brain(b, "other", 29859, said="29859")
answer(b, [W_3902])
check("ответ другим видом: место «прочих» отдано названной работе (одна позиция)",
      lambda: "Сделано: чистка тормозных цилиндров" in joined() and "прочие работы" not in joined())
check("ответ другим видом: в сделанном заявки «прочих» больше нет",
      lambda: S._sp_split(b.sp.get("done")) == ["pads"])

# Напоминания и перечни тоже говорят словами.
check("перечень (напоминание висяка, эскалация) называет работу словами, а не ярлыком",
      lambda: S._sp_labels_ru(["other"], [W_9548]) == "замена аккумулятора")
check("колоночный вид остаётся своим ярлыком (человек подтверждает регистр)",
      lambda: S._sp_labels_ru(["oil"], ["замена масла"]) == "моторное масло")
check("слов нет → ярлык, как было", lambda: S._sp_labels_ru(["other"], []) == "прочие работы")


# ═══════════════ (6) ОТКАТ ═══════════════
print("\n(6) откат WORK_NAME=0: прежний ярлык байт-в-байт")
os.environ["WORK_NAME"] = "0"
try:
    reset(); b = FakeBridge(sp=LEGACY)
    write(b, {"done": ["other"], "odo": "29859"})
    check("откат: «прочие работы — 29859 км», как до правки",
          lambda: [e.get("notes") for e in b.events] == ["прочие работы — 29859 км"])
    b4 = FakeBridge()
    act(lambda: S._write_info_works(b4, "обслуживание", TOPIC, BIKE, [W_9548], "36474", "",
                                    msg_date="2026-08-14"))
    check("откат: соседняя дверь без дня в строке",
          lambda: b4.events[0]["notes"] == "замена аккумулятора — 36474 км")
finally:
    os.environ.pop("WORK_NAME", None)

print(f"\nИТОГ: {OK} PASS, {FAIL} FAIL")
if FAIL:
    sys.exit(1)
