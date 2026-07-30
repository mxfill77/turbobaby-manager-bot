"""guard_replay.py — инструмент ЗАМЕРА гарда (реплей боевых команд из транскриптов сессий).

Зачем в гейте: замер «карточек владельцу было / станет» требуется каждой правкой гарда, и врать
он не имеет права — иначе правка «на глаз». Проверяем САМ ИНСТРУМЕНТ на синтетическом транскрипте
(разбор .jsonl, окно по времени, раскладка по корзинам hard/card/journal/defer) плюс два живых
контракта: реплей ничего не исполняет и ничего не пишет.
"""
import os, sys
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ["PRETOOL_NOPUSH"] = "1"          # сеть/пуши в тестах не дёргаем никогда

def ok(c, l): print(("  PASS " if c else "  FAIL ") + l); return c
res = []

import guard_replay as GR

print("(1) self-test инструмента (синтетический транскрипт):")
res.append(ok(GR._self_test() == 0, "разбор транскрипта + корзины + окно по времени"))

print("(2) корзины считаются по решению гарда, а не по подстроке:")
res.append(ok(GR.verdict("grep -n foo /root/turbobaby-manager-bot/splinter.py")[0] == "defer",
              "чтение исходника → defer"))
res.append(ok(GR.verdict("git commit -F - <<'MSG'\nтекст про " + "." + "env" + "\nMSG")[0] == "defer",
              "тело сообщения коммита → defer (класс 30.07)"))
res.append(ok(GR.verdict("pkill -9 splinter")[0] == "hard", "боевой процесс → hard"))
res.append(ok(GR.verdict("")[0] == "defer", "пустая команда → defer (не падает)"))

print("(3) реплей — read-only: источника нет → ноль строк, без исключения:")
counts, rows = GR.replay(hours=1.0, root="/tmp/нет-такого-каталога-guard-replay")
res.append(ok(sum(counts.values()) == 0 and rows == [], "несуществующий каталог транскриптов → пусто"))
res.append(ok(set(counts) == set(GR.BUCKETS), "набор корзин стабилен: " + ", ".join(GR.BUCKETS)))

print("\nИТОГ:", "ВСЕ PASS" if all(res) else "ЕСТЬ FAIL (%d/%d)" % (sum(res), len(res)))
sys.exit(0 if all(res) else 1)
