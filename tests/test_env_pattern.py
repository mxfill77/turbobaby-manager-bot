# -*- coding: utf-8 -*-
"""ГРАНИЦА ГЕЙТА: РАЗРЯД СЕКРЕТОВ СРАБАТЫВАЛ НА ШАБЛОН ПОИСКА (07.08.2026).

КЛАСС. `env_hard_block` — самое строгое решение контура: deny, карточка владельцу НЕ шлётся,
approve НЕВОЗМОЖЕН. Вставать он обязан на ОБРАЩЕНИЕ к файлу секретов. Вырез поискового ШАБЛОНА
живёт с 23.07.2026 (класс «данные ≠ команда»), но МЕСТО шаблона считалось ПО ПОРЯДКУ позиционных
аргументов, а флаг СО ЗНАЧЕНИЕМ этот счёт сбивал: в `grep -A 2 "<имя>" dir` шаблоном признавалось
«2», а НАСТОЯЩИЙ шаблон становился операндом и получал жёсткий блок. Тем же ломались `-m N`,
rg-шные `-g/-t`, awk-овы `-F sep`/`-v var=val`, форма `--regexp=<шаблон>` и поиск через `git grep`.

ЖИВОЙ ПОВОД — карточка 389 (07.08): команда искала упоминания секретов в СВОИХ ЖЕ пробных
скриптах через `grep -l` по временному каталогу; содержимого не печатала, к файлу секретов не
обращалась — красной её сделали слова ВНУТРИ ШАБЛОНА. ЧЕСТНО: задача 389 шла на полосе ПК, её
транскрипты на этой машине отсутствуют (последние — 11.07), поэтому ДОСЛОВНАЯ строка недоступна;
голдены секции (1) — формы ТОГО ЖЕ вида, снятые живой батареей по коду гарда. Код ПК-гарда в
снимке 24.07 (`/root/_twotails_20260726/pretool_guard.py`, стр. 115-116, 639-648) СОВПАДАЕТ с
VPS-овым до строки — значит на ПК течёт то же место.

ЗАМЕР (транскрипты сессий, ЖИВОЙ классификатор, два дерева на ОДНОМ корпусе):
  окно 168 ч — 4095 живых команд, 3659 уникальных: блоков секретов 9 → 9, освобождено 0;
  весь корпус (2400 ч) — 13014 команд, 10995 уникальных: блоков 113 → 113, освобождено 0,
  вновь заблокировано 0, иных смен решения 0, исключений разбора 0.
  ВСЕ 113 блоков — настоящие обращения (имя стоит ТОКЕНОМ сегмента: grep 74, python3 18,
  cp 4, git 4, cat 3, sed 3, stat 2, ls 2, прочие 3). Из шаблонов поиска за 7 суток — НОЛЬ.
  ПОВЕРХНОСТЬ класса при этом реальна: 252 уникальные живые команды — поиск с флагом СО
  ЗНАЧЕНИЕМ, 13 — `git grep`; разбор шаблона у них у всех был неверным, просто ни одна не
  назвала имя секрета.

ЧТО ПРОВЕРЯЕТСЯ:
  (1) формы класса — шаблон с флагом-значением, `--regexp=`, `git grep`: блока НЕТ;
  (2) НАСТОЯЩЕЕ чтение файла секретов — блок как прежде (ЗЕЛЁНОЕ В ОБОИХ ПРОГОНАХ);
  (3) поведение БЕЗ флагов со значением — байт-в-байт прежнее (ЗЕЛЁНОЕ В ОБОИХ);
  (4) FAIL-CLOSED: незнакомый флаг, ошибка таблицы, файл шаблонов `-f`, подстановка;
  (5) соседние классы и жёсткие блоки не ослаблены (ЗЕЛЁНОЕ В ОБОИХ);
  (6) разборщик поштучно: `_search_head` и `_strip_search_pattern`.

ТЕСТ НИЧЕГО НЕ ИСПОЛНЯЕТ И НИЧЕГО НЕ ШЛЁТ: зовутся ЧИСТЫЕ функции, main() не вызывается.
"""
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["PRETOOL_NOPUSH"] = "1"           # страховка: даже случайный пуш упрётся в мут

_fake_notify = types.ModuleType("notify")    # страховка №2 — до импорта гарда
_fake_notify.send_card = lambda card, **kw: (111, 222)
_fake_notify.edit_card = lambda mid, card, **kw: None
sys.modules.setdefault("notify", _fake_notify)

import pretool_guard as PG  # noqa: E402

PY = "venv/bin/python3"
NAME = "." + "env"                                # имя файла секретов (значений здесь нет)
SECRETS = "/root/turbobaby-manager-bot/" + NAME   # путь к нему
TMP = "/root/turbobaby-manager-bot/_scratch_probe_0807/"   # «свой пробный каталог» из повода
res = []


def ok(c, label):
    print(("  PASS " if c else "  FAIL ") + label)
    res.append(bool(c))
    return bool(c)


def hit_of(cmd):
    kind, hit, _blob = PG.classify(cmd, ROOT)
    return kind, hit


def blocked(cmd):
    kind, hit = hit_of(cmd)
    return kind == "block" and hit == "env_hard_block"


# ══ (1) ФОРМЫ КЛАССА: ИМЯ СЕКРЕТА В ШАБЛОНЕ ПОИСКА — БЛОКА НЕТ ═══════════════════════════════
# Общее у всех: утилита читает имя как РЕГУЛЯРКУ, файла по нему не открывает; операнд — свой
# пробный каталог. До правки красными были ровно эти строки.
print("\n(1) имя секрета в шаблоне поиска — жёсткого блока НЕТ")

for label, cmd in (
    ("grep -A N: число не шаблон, шаблон не операнд",
     'grep -rl -A 2 "%s" %s' % (NAME, TMP)),
    ("grep -B N", 'grep -rl -B 3 "%s" %s' % (NAME, TMP)),
    ("grep -C N", 'grep -rl -C 1 "%s" %s' % (NAME, TMP)),
    ("grep -m N (max-count)", 'grep -rl -m 1 "%s" %s' % (NAME, TMP)),
    ("grep --max-count длинной формой", 'grep -rl --max-count 1 "%s" %s' % (NAME, TMP)),
    ("grep -d skip (directories)", 'grep -rl -d skip "%s" %s' % (NAME, TMP)),
    ("форма --regexp=ШАБЛОН", 'grep -rl --regexp="%s" %s' % (NAME, TMP)),
    ("форма --regexp=ШАБЛОН без кавычек", 'grep -rl --regexp=%s %s' % (NAME, TMP)),
    ("rg -g glob перед шаблоном", 'rg -l -g "*.py" "%s" %s' % (NAME, TMP)),
    ("rg -t type перед шаблоном", 'rg -l -t py "%s" %s' % (NAME, TMP)),
    ("rg --max-depth", 'rg -l --max-depth 2 "%s" %s' % (NAME, TMP)),
    ("awk -F sep перед программой", "awk -F : '/%s/{print FILENAME}' %s" % (NAME, TMP + "a.py")),
    ("awk -v var=val перед программой",
     "awk -v n=1 '/%s/{print NR}' %s" % (NAME, TMP + "a.py")),
    ("git grep — поиск по содержимому подкомандой", 'git grep -l "%s"' % NAME),
    ("git grep с каталогом", 'git grep -ln "%s" -- %s' % (NAME, TMP)),
    ("grep -n -r: -n значения не берёт", 'grep -n -r "%s" %s' % (NAME, TMP)),
    ("grep -E -r: -E значения не берёт", 'grep -E -r "%s" %s' % (NAME, TMP)),
):
    ok(not blocked(cmd), label)

# Освобождение НЕ означает «зелёное во всём»: команда как уходила к слоям settings, так и уходит.
ok(hit_of('grep -rl -m 1 "%s" %s' % (NAME, TMP))[0] in ("green", "ambiguous"),
   "освобождённый поиск уходит в defer к слоям settings, а не в красное гарда")


# ══ (2) НАСТОЯЩЕЕ ЧТЕНИЕ ФАЙЛА СЕКРЕТОВ — БЛОК КАК ПРЕЖДЕ (ЗЕЛЁНОЕ В ОБОИХ ПРОГОНАХ) ═════════
print("\n(2) настоящее обращение к файлу секретов — блок остаётся")

for label, cmd in (
    ("cat файла секретов", "cat " + SECRETS),
    ("grep с файлом секретов ОПЕРАНДОМ", 'grep -n TOKEN ' + SECRETS),
    ("grep -A N и файл секретов операндом", 'grep -n -A 2 TOKEN ' + SECRETS),
    ("grep -m N и файл секретов операндом", 'grep -m 1 TOKEN ' + SECRETS),
    ("rg -g glob и файл секретов операндом", 'rg -g "*" TOKEN ' + SECRETS),
    ("git grep по файлу секретов", 'git grep -l TOKEN -- ' + SECRETS),
    ("шаблон-имя И файл секретов операндом", 'grep -rl "%s" %s' % (NAME, SECRETS)),
    ("stat по пути секретов", "stat -c '%y %n' " + SECRETS),
    ("чтение рядом в цепи", 'grep -rl "%s" %s ; cat %s' % (NAME, TMP, SECRETS)),
    ("подстановка читает секреты", 'grep -rl "$(cat %s)" %s' % (SECRETS, TMP)),
    ("load_dotenv в инлайн-коде",
     PY + " -c 'from dotenv import load_dotenv; load_dotenv(\"" + SECRETS + "\")'"),
    ("sed по файлу секретов", "sed -n '1,5p' " + SECRETS),
    ("копирование файла секретов", "cp " + SECRETS + " " + SECRETS + ".bak-x"),
):
    ok(blocked(cmd), label)

ok(not PG.can_approve("block", "env_hard_block"),
   "approve у жёсткого блока по-прежнему НЕВОЗМОЖЕН")
ok((PG.decision("block", "env_hard_block", "x") or {}).get(
    "hookSpecificOutput", {}).get("permissionDecision") == "deny",
   "решение хука на блоке секретов — deny, а не ask")


# ══ (3) БЕЗ ФЛАГОВ СО ЗНАЧЕНИЕМ — ПОВЕДЕНИЕ БАЙТ-В-БАЙТ ПРЕЖНЕЕ (ЗЕЛЁНОЕ В ОБОИХ) ═══════════
print("\n(3) формы без флагов со значением — как было")

for label, cmd, want_block in (
    ("простой grep -rl по каталогу", 'grep -rl "%s" %s' % (NAME, TMP), False),
    ("grep -n по постороннему файлу", 'grep -n "%s" %s' % (NAME, ROOT + "/gate.py"), False),
    ("grep -e шаблон", 'grep -rl -e "%s" %s' % (NAME, TMP), False),
    ("два -e, имя во втором", 'grep -rl -e TOKEN -e "%s" %s' % (NAME, TMP), False),
    ("шаблон без кавычек", 'grep -rl %s %s' % (NAME, TMP), False),
    ("sed-программа с именем", "sed -n '/%s/p' %sa.py" % (NAME, TMP), False),
    ("awk-программа с именем", "awk '/%s/{print}' %sa.py" % (NAME, TMP), False),
    ("шаблон в конце цепи с head", 'grep -rl "%s" %s | head -20' % (NAME, TMP), False),
    ("xargs grep", 'find %s -name "*.py" | xargs grep -l "%s"' % (TMP, NAME), False),
    ("полный путь секретов как ШАБЛОН (без флагов-значений)",
     'grep -rl "%s" %s' % (SECRETS, TMP), False),
    ("--include с именем: речь о том, КАКИЕ ФАЙЛЫ открыть — красное намеренно",
     'grep -rl TOKEN %s --include="*%s"' % (TMP, NAME), True),
    ("find -name по имени секрета — не поиск по содержимому, красное намеренно",
     'find %s -name "*%s*"' % (TMP, NAME), True),
):
    ok(blocked(cmd) is want_block, label)


# ══ (4) FAIL-CLOSED И НАПРАВЛЕНИЕ СОМНЕНИЯ ═══════════════════════════════════════════════════
print("\n(4) fail-closed: сомнение решается краснее")

# Незнакомый флаг считается флагом БЕЗ значения — как и было. Если он на самом деле берёт
# значение, значение будет принято за шаблон; чтобы это не стоило жёсткого блока, позиционный
# после съеденного значения не вырезается, когда он назван ПУТЁМ с каталогом.
ok(blocked('rg -E utf8 TOKEN ' + SECRETS),
   "ошибка таблицы не открывает секреты: путь с каталогом после съеденного значения остаётся")
ok(blocked('grep -m 1 TOKEN ' + SECRETS + ' ' + TMP),
   "секреты первым операндом среди нескольких — блок")
ok(not blocked('grep -rl -m 1 "%s"' % NAME),
   "голое имя как единственный позиционный — это шаблон, не путь")

# Файл ШАБЛОНОВ (-f) утилита ОТКРЫВАЕТ: до правки его значение съедалось как «шаблон» и
# `grep -f <файл секретов>` проходил молча. ЭТО НОВОЕ КРАСНОЕ (до правки было зелёным).
ok(blocked('grep -rl -f %s %s' % (SECRETS, TMP)),
   "grep -f <файл секретов> — чтение файла шаблонов, теперь блок (было молча)")
ok(not blocked('grep -rl -f /tmp/tb_scratch/pats.txt %s' % TMP),
   "обычный файл шаблонов блока не даёт")
ok(blocked('awk -f %s %sa.py' % (SECRETS, TMP)),
   "awk -f <файл секретов> — программа читается из файла секретов, блок")

# Признак ИСПОЛНЕНИЯ внутри шаблона не вырезается и раскрывается отдельным сегментом.
ok(blocked('grep -rl "`cat %s`" %s' % (SECRETS, TMP)),
   "обратные кавычки внутри шаблона — по-прежнему блок")


# ══ (5) СОСЕДНИЕ КЛАССЫ НЕ ОСЛАБЛЕНЫ (ЗЕЛЁНОЕ В ОБОИХ ПРОГОНАХ) ══════════════════════════════
print("\n(5) границы: соседние классы как были")

k, h = hit_of("pkill -9 splinter")
ok(k == "block" and h == "proc_hard_block", "жёсткий блок процессов цел")
k, h = hit_of("systemd-run --on-active=1s systemctl stop orchestrator-daemon")
ok(k == "block" and h == "proc_hard_block", "отложенная остановка боевого процесса цела")
ok(hit_of('grep -rl -m 1 "add_transaction" %s' % TMP)[0] != "red",
   "имя операции в шаблоне поиска красного не даёт (класс данных цел)")
ok(hit_of("rm -f /root/turbobaby-manager-bot/bot.py")[0] == "red",
   "удаление вне временных каталогов остаётся красным")
ok(hit_of("rm -f /tmp/tb_scratch/x.py")[0] != "red",
   "уборка своего черновика в /tmp остаётся зелёной")
ok(hit_of('grep -rl -m 1 "TOKEN" /root/turbobaby-manager-bot/memory.db')[0] != "block",
   "класс БД шаблоном не сбивается: .db остаётся операндом под сканом")
ok(blocked('grep -rl -m 1 "TOKEN" %s' % SECRETS),
   "и с флагом-значением файл секретов операндом — блок")


# ══ (6) РАЗБОРЩИК ПОШТУЧНО ═══════════════════════════════════════════════════════════════════
print("\n(6) разборщик: роль токена, а не его номер")

_head = getattr(PG, "_search_head", None)
_strip = getattr(PG, "_strip_search_pattern", None)

if _head is None:
    ok(False, "_search_head в дереве ОТСУТСТВУЕТ")
else:
    ok(_head(["grep", "-rl", "x"], 0) == 0, "голова grep — она сама")
    ok(_head(["git", "grep", "-l", "x"], 0) == 1, "у `git grep` голова поиска — подкоманда")
    ok(_head(["git", "commit", "-q"], 0) is None, "у прочих подкоманд git поиска нет")
    ok(_head(["cat", "f"], 0) is None, "не поисковая утилита — головы нет")
    ok(_head(["grep"], None) is None, "None на входе не роняет разбор")

if _strip is None:
    ok(False, "_strip_search_pattern в дереве ОТСУТСТВУЕТ")
else:
    keep, dropped = _strip(["grep", "-rl", "-A", "2", NAME, TMP], 0)
    ok(dropped == [NAME] and "2" in keep and TMP in keep,
       "флаг-значение пропущено, вырезан ШАБЛОН, операнд и число остались")
    keep, dropped = _strip(["grep", "-rl", "--regexp=" + NAME, TMP], 0)
    ok(dropped == [NAME] and TMP in keep,
       "форма флаг=шаблон: из токена вырезан ШАБЛОН, операнд остался")
    keep, dropped = _strip(["grep", "-rl", "-f", SECRETS, TMP], 0)
    ok(dropped == [] and SECRETS in keep,
       "файл шаблонов не вырезается вовсе — он под сканом")
    keep, dropped = _strip(["rg", "-l", "-r", "X", NAME, TMP], 0)
    ok(dropped == [NAME], "у rg `-r` берёт значение (замена), шаблон найден верно")
    keep, dropped = _strip(["grep", "-rl", "-r", NAME, TMP], 0)
    ok(dropped == [NAME], "у grep `-r` значения НЕ берёт — семьи не путаются")
    keep, dropped = _strip(["grep", "-rl", "-m", "1", SECRETS, TMP], 0)
    ok(dropped == [] and SECRETS in keep,
       "fail-closed: путь с каталогом после съеденного значения не вырезается")
    keep, dropped = _strip(["grep", "-rl", "-m", "1", NAME, TMP], 0)
    ok(dropped == [NAME], "голое имя после съеденного значения — шаблон, вырезается")
    keep, dropped = _strip(["cat", SECRETS], 0)
    ok(dropped == [] and SECRETS in keep, "не поисковая утилита — не режем ничего")

print("\nИТОГ: %d/%d" % (res.count(True), len(res)))
if res.count(False):
    print("КРАСНЫХ: %d" % res.count(False))
    sys.exit(1)
print("Все проверки зелёные.")
