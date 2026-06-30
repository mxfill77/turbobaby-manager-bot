"""Моки: разделитель _with_separator (централизованно в _send) + двуязычные служебные."""
import os, sys, asyncio, re
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL","http://x"); os.environ.setdefault("BRIDGE_TOKEN","x")
import splinter as S
def ok(c,l): print(("  PASS " if c else "  FAIL ")+l); return c
def th_clean(m):
    inth=False
    for l in m.split("\n"):
        if l.lstrip().startswith("🇷🇺"): inth=False
        if l.lstrip().startswith("🇹🇭"): inth=True
        if inth and re.search(r"[А-Яа-яЁё]",l): return False
    return True
res=[]

# 1) _with_separator: вставляет линию между слипшимися 🇹🇭/🇷🇺
m=S._with_separator("🐀 X\n🇹🇭 สวัสดี\n🇷🇺 привет")
print("(1) вставка линии:")
res.append(ok(S._SEP in m and m.index("🇹🇭")<m.index(S._SEP)<m.index("🇷🇺"), "линия между 🇹🇭 и 🇷🇺"))

# 2) идемпотентность: повтор не дублирует
res.append(ok(S._with_separator(m).count(S._SEP)==1, "повтор не дублирует"))

# 3) денежное (_bilingual, пустая строка) → пустая заменена на линию, без дублей
money=S._with_separator(S._bilingual("Money",["ยอด 100"],["Баланс 100"]))
res.append(ok(money.count(S._SEP)==1 and "\n\n🇷🇺" not in money, "денежное: пустая строка → линия, без двойного"))

# 4) одноязычное — не трогаем
res.append(ok(S._with_separator("🇷🇺 только русский")=="🇷🇺 только русский", "одноязычное не тронуто (нет 🇹🇭)"))
res.append(ok(S._with_separator("🇹🇭 เฉพาะไทย")=="🇹🇭 เฉพาะไทย", "одноязычное не тронуто (нет 🇷🇺)"))

# 5) ИНТЕГРАЦИЯ: реальный _send применяет разделитель (context.bot.send_message ловит text)
CAP=[]
class Bot:
    async def send_message(s,**kw): CAP.append(kw.get("text","")); return type("M",(),{"message_id":1})()
class Ctx:
    def __init__(s): s.bot=Bot()
loop=asyncio.new_event_loop()
acc={"current_km":"37823","works":["замена масляного фильтра"],"works_km":"37823","oil":{"km":37823,"next":42823,"status":"ok"},"cols":[]}
loop.run_until_complete(S._send(Ctx(),chat_id=-1,text=S.msg_service_summary("NINJA 6334",acc)))
loop.run_until_complete(S._send(Ctx(),chat_id=-1,text=S.msg_bike_card("NINJA 6334","37823",[],None,[{"work":"масляный фильтр","km":"37823"}])))
print("(5) _send централизованно:")
res.append(ok(all(S._SEP in t for t in CAP), "сводка И карточка через _send → с разделителем"))
res.append(ok(all(th_clean(t) for t in CAP), "🇹🇭 без кириллицы (разделитель нейтрален)"))
loop.close()

# 6) «Кнопка устарела» — двуязычная (проверяем содержимое исходника)
src=open("/root/turbobaby-manager-bot/splinter.py",encoding="utf-8").read()
print("(6) служебные двуязычны:")
res.append(ok("ปุ่มหมดอายุ" in src and "Кнопка устарела (перезапуск бота)" in src, "«Кнопка устарела» 🇹🇭+🇷🇺"))
res.append(ok("กำลังบันทึก… · Записываю…" in src and "ยืนยันโดย {PYM_HANDLE}/เจ้าของ · Подтверждает" in src, "тосты двуязычны (адресация тайца через PYM_HANDLE)"))

print("\nИТОГ:", "ВСЕ PASS" if all(res) else f"ЕСТЬ FAIL ({sum(res)}/{len(res)})")
sys.exit(0 if all(res) else 1)
