"""Журнальная запись (зона 🟢): NOTE в cc_log ПОД врезкой + pulse — ОДНА операция.
Защита: read → prepend под ═-only-строкой → write ТОЛЬКО если read ok. Бэкап cc_log в /tmp."""
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

NOTE = """NOTE 2026-07-03 00:48 UTC ([шаг 1/7 родитель 33], headless): РАЗВЕДКА расхождений мозг↔реальность после ступени 2 O4 — read-only, правок НЕ делал. Источники: pulse (02.07 23:39), cc_log (сегодняшний блок), KB_MASTER §2/§3/§4/§6/§7, roadmap_master (имени «KB_ROADMAP_v2» в манифесте НЕТ — единственный роадмап = roadmap_master, §5 карты это сам признаёт).
СПИСОК РАСХОЖДЕНИЙ (8):
1) KB_MASTER §4 [O4]: статус «В ПРОЕКТИРОВАНИИ (план в KB_review 03.07, ждёт ревью штаба)» — реально ступень 2 СОБРАНА ЦЕЛИКОМ и в проде: A+B b846c5f («тз:» из 328 через headless CC), Q2 7d840e2 (restart splinter headless-CC делает САМ, преамбула v3), C-декомпозер 2733f17, докс 346a154. Осталась функциональная обкатка (первый живой «декомпозируй:», подхват v3 демоном на следующем «тз:»).
2) KB_MASTER §4 приоритет-блок «…затем декомпозер» и §7 хвост «O4 ДЕКОМПОЗЕР — после обкатки O3» устарели: декомпозер собран 02.07 (2733f17); хвост должен смениться на «обкатка ст2 → ступень 3 полуавтономный».
3) KB_MASTER §2 исполнитель 5 (дев-бот/оркестратор): описана ТОЛЬКО ступень 1 (белый список 7 зелёных команд, 2 авто-op git_push/restart_splinter) — нет «тз:» (QUEUE_FROM_DEV), «декомпозируй:» (QUEUE_FROM_DEC), headless-restart оранжевым циклом. Маршрутизация §2 «чтение кода/recon дев-бот НЕ берёт → СРАЗУ в Termux» устарела: «тз:»/headless CC recon берёт (этот шаг — живой пример).
4) ДОКТРИНА ПОДТВЕРЖДЕНИЙ (02.07, ea92795: ask только там, где владелец добавляет информацию; техника = тесты+гейт, не человеческое «да») — есть в CLAUDE.md + KB_RULES разд.8, в KB_MASTER НЕ отражена (§3 упоминает лишь переклассификацию 0b08816).
5) KB_MASTER §6 чек-лист [4] ссылается на «KB_ROADMAP_v2» — такого имени в манифесте нет; внутреннее противоречие карты (§5 уже говорит «единственный роадмап = roadmap_master»).
6) roadmap_master (актуализация 29.06): дев-бот = «полу-оркестратор ступень 1», в открытых хвостах «O4 декомпозер» — не знает про собранную ступень 2 (A+B+Q2+C), фикс заморозки event loop 3978a91, доктрину подтверждений.
7) TurboControl/328: код зовёт HQ-форум «TurboControl» (splinter.py:3106/3371, bot.py:57, chat -1003853365891, тема 328) — мозг (KB_MASTER §2/§5, roadmap_master) пишет «HQ» без этого имени; унифицировать наименование.
8) KB_MASTER §6 ТРИГГЕР 1 СРАБОТАЛ: веха оси (O4 ступень 2) закрыта → положена полная ревизия [1–8] перед следующей вехой (п.7 = синк CLAUDE.md; якорь плановой ≤11.07.2026).
ДАЛЬШЕ: шаги 2–7 родителя 33 (собственно правки мозга по этому списку).
"""

PULSE = "2026-07-03 00:48 | 🟢 | шаг 1/7 родитель 33: разведка расхождений мозг↔реальность после ст2 O4 — 8 пунктов (KB_MASTER §2/§4/§6/§7 отстают от собранной ст2, roadmap_master устарел, доктрина не в карте, TurboControl не назван, триггер ревизии §6.1 сработал) | ничего не жду, дальше шаги 2–7 | детали→cc_log NOTE «шаг 1/7 родитель 33»"

c = BridgeClient()

r = c._call("read_doc", name="cc_log")
if not r.get("ok"):
    raise SystemExit("read cc_log FAILED — писать НЕ буду: " + str(r))
text = r.get("text", "")
open("/tmp/cclog_bak_step1_o4_20260703.txt", "w").write(text)

lines = text.split("\n")
sep = None
for i, ln in enumerate(lines):
    s = ln.strip()
    if s and set(s) == {"═"}:
        sep = i
        break
if sep is None:
    raise SystemExit("врезка (═-only строка) НЕ найдена — писать НЕ буду")

if "шаг 1/7 родитель 33" in text:
    raise SystemExit("NOTE уже в cc_log (повторный запуск) — не дублирую")

new_text = "\n".join(lines[: sep + 1]) + "\n" + NOTE + "\n" + "\n".join(lines[sep + 1 :])
w = c.write_doc(text=new_text, name="cc_log")
print("write cc_log ok:", w.get("ok"))
if not w.get("ok"):
    raise SystemExit("write cc_log FAILED: " + str(w))

p = c.write_doc(text=PULSE, name="pulse")
print("write pulse ok:", p.get("ok"))

v = c._call("read_doc", name="cc_log")
head = v.get("text", "").split("\n")
print("верификация: строка 2 =", head[2][:80])
