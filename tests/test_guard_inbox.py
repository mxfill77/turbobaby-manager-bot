"""Guard-карточки pretool_guard → тема-инбокс HQ (INBOX_TOPIC_ID, прод 1160), личка — фолбэк
(пульт «ждут владельца», 13.07.2026). Проверяем:
(1) send_card: инбокс задан → карточка в HQ -1003853365891 / thread из env, возврат (mid, chat);
(2) фолбэк: форум недоступен (отправка в HQ не прошла) → карточка уходит в личку 504608015;
(3) инбокс выключен (INBOX_TOPIC_ID=0) → сразу личка, форум не дёргается (старое поведение);
(4) edit_card: правка идёт в ТОТ ЖЕ чат (chat_id); без chat_id → личка (легаси-записи стора);
(5) pretool_guard._edit: распаковка [mid, chat] из дедуп-стора + легаси голый int → личка;
    _dedup_save_mid/_dedup_bump: (mid, chat) переживает round-trip через JSON-стор;
(6) devbot.handle_command: «да N»/«нет N» ИЗ ТЕМЫ-ИНБОКСА работают (approve/reject как из 328),
    не-approval текст → подсказка (enqueue/зелёное НЕ зовутся), чужой → игнор, env выключен →
    тема чужая; регресс: «да N» из 328 работает как раньше;
(7) тест-контуры целы: PRETOOL_NOPUSH → мут (сеть не дёргается), NOTIFY_COUNT_FILE → счётчик.
Сеть замокана (_send_message/_edit_message/_get_token), реальных пушей НОЛЬ.
"""
import os, sys, json, asyncio, tempfile, shutil

sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")

import notify as N
import pretool_guard as PG
import devbot as DB

HQ = -1003853365891
INBOX = 1160
LICHKA = 504608015


def ok(c, l): print(("  PASS " if c else "  FAIL ") + l); return c
res = []

# Тест-моды глушат send_card ДО сети — для мок-проверок маршрута снимаем их явно
# (импорт notify как тест-entrypoint ставит PRETOOL_NOPUSH через setdefault).
os.environ.pop("PRETOOL_NOPUSH", None)
os.environ.pop("NOTIFY_COUNT_FILE", None)
os.environ["INBOX_TOPIC_ID"] = str(INBOX)   # override: load_dotenv существующий env НЕ перекрывает

SENT = []      # (chat_id, thread_id, text)
EDITS = []     # (chat_id, mid, text)
FAIL_HQ = {"on": False}


def fake_send(token, text, chat_id=None, thread_id=None):
    chat = chat_id if chat_id else N.CHAT_ID
    SENT.append((chat, thread_id, text))
    if FAIL_HQ["on"] and chat == HQ:
        return False, None   # форум недоступен
    return True, 111 + len(SENT)


def fake_edit(token, mid, text, chat_id=None):
    EDITS.append((chat_id if chat_id else N.CHAT_ID, mid, text))
    return True


N._send_message = fake_send
N._edit_message = fake_edit
N._get_token = lambda: "tok"

# ===== (1) карточка уходит в тему-инбокс 1160 =====
print("(1) send_card → тема-инбокс HQ:")
SENT.clear()
r = N.send_card("🔴 КРАСНОЕ guard-карточка")
res.append(ok(len(SENT) == 1, "ровно одна отправка (личку не дублируем)"))
res.append(ok(SENT[0][0] == HQ and SENT[0][1] == INBOX, f"чат HQ и thread {INBOX}: {SENT[0][:2]}"))
res.append(ok(isinstance(r, tuple) and r[1] == HQ and r[0], f"возврат (mid, chat=HQ): {r}"))

# ===== (2) фолбэк: форум недоступен → личка =====
print("(2) фолбэк в личку при недоступном форуме:")
SENT.clear(); FAIL_HQ["on"] = True
r = N.send_card("🔴 карточка при упавшем форуме")
FAIL_HQ["on"] = False
res.append(ok(len(SENT) == 2 and SENT[0][0] == HQ, "сначала попытка в инбокс"))
res.append(ok(SENT[1][0] == LICHKA and not SENT[1][1], "фолбэк — личка Филиппа, без thread"))
res.append(ok(isinstance(r, tuple) and r[1] == LICHKA and r[0], f"возврат (mid, chat=личка): {r}"))

# ===== (3) инбокс выключен → сразу личка =====
print("(3) INBOX_TOPIC_ID=0 → старое поведение (личка):")
SENT.clear(); os.environ["INBOX_TOPIC_ID"] = "0"
r = N.send_card("🔴 карточка без инбокса")
res.append(ok(len(SENT) == 1 and SENT[0][0] == LICHKA and not SENT[0][1],
              f"одна отправка, личка: {SENT}"))
res.append(ok(isinstance(r, tuple) and r[1] == LICHKA, "возврат (mid, chat=личка)"))
os.environ["INBOX_TOPIC_ID"] = str(INBOX)

# ===== (4) edit_card правит В ТОМ ЖЕ чате =====
print("(4) edit_card: чат карточки уважается:")
EDITS.clear()
N.edit_card(777, "×2", chat_id=HQ)
N.edit_card(778, "×2 легаси")            # без chat_id → личка (записи стора до 13.07)
res.append(ok(EDITS[0] == (HQ, 777, "×2"), f"правка в инбоксе: {EDITS[0]}"))
res.append(ok(EDITS[1][0] == LICHKA and EDITS[1][1] == 778, f"легаси без чата → личка: {EDITS[1]}"))

# ===== (5) pretool_guard: распаковка стора + round-trip =====
print("(5) pretool_guard._edit и дедуп-стор:")
EDITS.clear()
PG._edit([555, HQ], "повтор ×2")
PG._edit(556, "повтор легаси")
res.append(ok(EDITS[0] == (HQ, 555, "повтор ×2"), f"[mid, chat] из стора → правка в инбоксе: {EDITS[0]}"))
res.append(ok(EDITS[1][0] == LICHKA and EDITS[1][1] == 556, f"голый int (легаси) → личка: {EDITS[1]}"))
tmp = tempfile.mkdtemp(prefix="guard_inbox_dedup_")
_orig_dir = PG._DEDUP_DIR
PG._DEDUP_DIR = tmp
try:
    c1, m1 = PG._dedup_bump("s-gi", "cmd-x")
    PG._dedup_save_mid("s-gi", "cmd-x", (999, HQ))
    c2, m2 = PG._dedup_bump("s-gi", "cmd-x")
    res.append(ok(c1 == 1 and m1 is None and c2 == 2, f"счётчик 1→2: {(c1, c2)}"))
    res.append(ok(list(m2 or []) == [999, HQ], f"(mid, chat) пережил JSON-стор: {m2}"))
finally:
    PG._DEDUP_DIR = _orig_dir
    shutil.rmtree(tmp, ignore_errors=True)

# ===== (6) devbot: «да N»/«нет N» из темы-инбокса =====
print("(6) devbot.handle_command в теме-инбоксе:")
SENDS = []

class FakeBot:
    async def send_message(self, chat_id, message_thread_id=None, text="", reply_markup=None):
        SENDS.append((chat_id, message_thread_id, text))

class Ctx:
    bot = FakeBot()

class FakeUser:
    def __init__(s, uid): s.id = uid

class FakeMsg:
    def __init__(s, text, topic, uid=DB.DEVBOT_USER):
        s.text = text
        s.message_thread_id = topic
        s.from_user = FakeUser(uid)
        s.chat_id = DB.HQ_CHAT_ID

class ApprBridge:
    def __init__(s): s.approved = []; s.completed = []
    def approve_task(s, qid, who): s.approved.append((qid, who)); return {"ok": True}
    def complete_task(s, qid, status, result=""): s.completed.append((qid, status, result)); return {"ok": True}
    def enqueue_task(s, *a, **k): raise AssertionError("enqueue из темы-инбокса зваться НЕ должен")

b = ApprBridge(); SENDS.clear()
asyncio.run(DB.handle_command(FakeMsg("да 77", INBOX), Ctx(), b))
res.append(ok(b.approved == [(77, "Filipp")], f"«да 77» из инбокса → approve_task: {b.approved}"))
res.append(ok(SENDS and SENDS[0][1] == INBOX and "77" in SENDS[0][2],
              f"ответ в ТУ ЖЕ тему-инбокс: {SENDS[:1]}"))
b2 = ApprBridge(); SENDS.clear()
asyncio.run(DB.handle_command(FakeMsg("нет 78", INBOX), Ctx(), b2))
res.append(ok(b2.completed and b2.completed[0][:2] == (78, "failed"),
              f"«нет 78» из инбокса → reject (failed): {b2.completed}"))
DB._forget_seen(DB._reported, 78)   # не мусорим модульному состоянию других проверок
b3 = ApprBridge(); SENDS.clear()
asyncio.run(DB.handle_command(FakeMsg("тз: собери что-нибудь", INBOX), Ctx(), b3))
res.append(ok(b3.approved == [] and b3.completed == [], "не-approval в инбоксе: очередь не тронута"))
res.append(ok(len(SENDS) == 1 and "инбокс" in SENDS[0][2] and SENDS[0][1] == INBOX,
              f"подсказка про инбокс (не зелёный allowlist): {SENDS}"))
b4 = ApprBridge(); SENDS.clear()
asyncio.run(DB.handle_command(FakeMsg("да 77", INBOX, uid=111), Ctx(), b4))
res.append(ok(b4.approved == [] and SENDS == [], "чужой юзер в инбоксе → полный игнор"))
os.environ["INBOX_TOPIC_ID"] = "0"
b5 = ApprBridge(); SENDS.clear()
asyncio.run(DB.handle_command(FakeMsg("да 77", INBOX), Ctx(), b5))
res.append(ok(b5.approved == [] and SENDS == [], "инбокс выключен env → тема чужая, игнор"))
os.environ["INBOX_TOPIC_ID"] = str(INBOX)
b6 = ApprBridge(); SENDS.clear()
asyncio.run(DB.handle_command(FakeMsg("да 5", DB.DEVBOT_TOPIC), Ctx(), b6))
res.append(ok(b6.approved == [(5, "Filipp")] and SENDS and SENDS[0][1] == DB.DEVBOT_TOPIC,
              "регресс: «да N» из 328 работает как раньше"))

# ===== (7) тест-контуры send_card целы =====
print("(7) мут и мок-счётчик не сломаны:")
SENT.clear(); os.environ["PRETOOL_NOPUSH"] = "1"
res.append(ok(N.send_card("тестовая карточка") is None and SENT == [],
              "PRETOOL_NOPUSH=1 → мут, сети нет"))
res.append(ok(PG._push("тестовая карточка") is None, "pretool_guard._push под мутом → None"))
os.environ.pop("PRETOOL_NOPUSH", None)
cntf = tempfile.mktemp(prefix="guard_inbox_cnt_")
os.environ["NOTIFY_COUNT_FILE"] = cntf
try:
    r = N.send_card("счётная карточка")
    with open(cntf, encoding="utf-8") as f:
        lines = [l for l in f.read().splitlines() if l]
    res.append(ok(r == (-1, 0) and len(lines) == 1 and SENT == [],
                  f"NOTIFY_COUNT_FILE → попытка в счётчик, сети нет, псевдо-возврат: {r}"))
finally:
    os.environ.pop("NOTIFY_COUNT_FILE", None)
    try: os.remove(cntf)
    except OSError: pass

print("\nИТОГ:", "ВСЕ PASS" if all(res) else "ЕСТЬ FAIL (%d/%d)" % (sum(res), len(res)))
sys.exit(0 if all(res) else 1)
