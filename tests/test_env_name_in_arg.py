# -*- coding: utf-8 -*-
"""ГРАНИЦА ГЕЙТА: ИМЯ СЕКРЕТА В АРГУМЕНТЕ (05.08.2026, фикс 2 из 3).

КЛАСС. Жёсткий блок `env_hard_block` — самый строгий вид решения в контуре: deny, карточка
владельцу НЕ шлётся, approve НЕВОЗМОЖЕН. Вставать он обязан на ОБРАЩЕНИЕ к файлу секретов.
Вставал же он и на ИМЯ СЕКРЕТА, НАЗВАННОЕ В АРГУМЕНТЕ команды: argv .py-скрипта вырезается из
скана как ДАННЫЕ ещё с 24.07.2026 (`_strip_script_cli_args`), но токен, ГДЕ ВСТРЕЧАЛОСЬ
написание `.env`, удерживался под сканом «операндом-уликой» — и журнальная строка
`cclog.py DONE "…запрет cat/grep .env классом в CLAUDE.md…"` получала deny за СЛОВА В ОТЧЁТЕ.

С ДРУГОЙ СТОРОНЫ ТОТ ЖЕ КЛАСС ЗАКРЫТ РАНЬШЕ — в ПРОЗЕ СВОЕГО КОММИТА: payload `-m` вырезается
с 12.07.2026 (`bd5d516`), многострочный heredoc — с 30.07.2026 (`a77c14e`, поводом был боевой
коммит 29.07 08:51:35, получивший deny за слова в сообщении). В аргументе класс оставался живым,
и остаток был ЗАПИСАН — дословно, живой строкой journal'а 02.08.2026 08:00 UTC:
«B-4 это и есть остаток про .env в прозе».

ЗАМЕР (транскрипты сессий, окно 336 ч, 6197 живых команд, реальный классификатор):
жёстких блоков 29 → 24. Освобождены РОВНО 5, и все пять — журнальные строки `cclog.py`
(голдены секции 1 ниже, дословно). Ни одно настоящее чтение файла секретов не освободилось:
24 оставшихся — это `grep`/`cat`/`stat`/`load_dotenv(...)` по пути секретов (голдены секции 2).

ПРАВИЛО — НЕ ЭВРИСТИКА, А СЕМАНТИКА argv: элемент argv доезжает до скрипта ЦЕЛИКОМ. Токен,
который САМ ЕСТЬ путь (`/root/app/.env`, `.env.local`, `--config=/root/app/.env`), скрипт может
открыть — обращение, красное как было. Токен-ПРЕДЛОЖЕНИЕ («…запрет cat/grep .env классом…»)
открыть нельзя ничем — это текст. Решает пробел ВНУТРИ токена, а не длина и не язык строки.

ЧТО ПРОВЕРЯЕТСЯ:
  (1) ДОСЛОВНЫЕ живые команды, освобождённые правкой, — жёсткого блока НЕ дают;
  (2) ДОСЛОВНЫЕ живые команды настоящего ЧТЕНИЯ секретов — блок дают, kind=block, approve НЕТ;
  (3) ФОРМЫ ПУТИ в аргументе (голый, относительный, с каталогом, .env.local, флаг=значение,
      путь среди прозаических аргументов) — блок как прежде;
  (4) FAIL-CLOSED: нет .py-токена, кривые кавычки, подстановка в аргументе, чтение рядом в
      цепи, инлайн-код `-c` — прежнее поведение, скан полный;
  (5) ГРАНИЦЫ НЕ ТРОНУТЫ: прочие улики argv (.db, SQL-write, признак исполнения), шаблон grep,
      текст `git -m`, жёсткий блок процессов и красное живых таблиц — байт-в-байт как были;
  (6) сам предикат `_env_path_arg` поштучно.

ТЕСТ НИЧЕГО НЕ ИСПОЛНЯЕТ И НИЧЕГО НЕ ШЛЁТ: зовутся ЧИСТЫЕ функции (classify/can_approve/
_env_path_arg), main() не вызывается, подпроцессов нет → ни пуша, ни маркера.
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
SECRETS = "/root/turbobaby-manager-bot/.env"     # путь файла секретов (значений здесь нет)
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


# ══ (1) ДОСЛОВНЫЕ ЖИВЫЕ КОМАНДЫ, ОСВОБОЖДЁННЫЕ ПРАВКОЙ ═══════════════════════════════════════
# Все пять взяты из транскриптов ПОБАЙТНО (см. замер в шапке). Общее у них одно: имя секрета
# названо в ПРОЗЕ отчёта, который скрипт пишет в журнал мозга, — файла никто не открывает.
print("\n(1) живые голдены: имя секрета в аргументе — блока НЕТ")

G1 = (PY + ' cclog.py PLAN "класс-фикс подтверждений: 1) guard doctrinal list (ambiguous→defer,'
      ' bash .env/kill9); 2) git -m strip (уже в WIP); 3) NA 24ч+3ч напомин (уже в WIP);'
      ' 4) re-run #279 + chain #274 шаги 6-7; 5) DONE-до-push (уже в WIP). Начало."'
      ' --pulse "🟡 | PLAN guard-class-fix | пишем код + тесты"')
ok(not blocked(G1), "23.07 02:01 PLAN «bash .env/kill9» — журнальная строка, не обращение")

G2 = (PY + ' cclog.py PLAN "задача 309: (1) анализ куратора по коду/логам — read-only;'
      ' (2) env_probe.py — безопасная ручка конфига (задана/не задана/длина, без значения),'
      ' запрет cat/grep .env классом в CLAUDE.md; тесты + гейт + коммит"'
      ' --pulse "🟡 | в работе: задача 309 env_probe + анализ куратора | ничего не жду'
      ' | детали→cc_log PLAN 309"')
ok(not blocked(G2), "23.07 06:39 PLAN «запрет cat/grep .env классом» — отчёт О ЗАПРЕТЕ, не запрос")

G3 = (PY + ' cclog.py DONE "расследование задач 283-289 (23.07.2026, повтор 291 после'
      ' класс-фикса 292). [287-289] избыточные ambiguous-карточки: нечитаемый py-путь,'
      " stdin '-', неизвестный модуль -m — guard выдавал ask вместо defer. Класс-фикс 292:"
      ' (3) bash doctrinal list: cat .env / kill-9 / sctl kill; (4) ТЕСТ-entity hard-block."'
      ' --pulse "2026-07-23 | 🟢 | задача 293 done | детали→cc_log"')
ok(not blocked(G3), "23.07 04:03 DONE «bash doctrinal list: cat .env» — ОПИСАНИЕ правила гарда")

G4 = (PY + ' /root/turbobaby-manager-bot/cclog.py DONE "Проверка отложенного рестарта демона'
      ' (read-only, задача 183). ОСТАЛОСЬ 24: ПК гард 15, ПК демон 5, VPS 4 (B-2, B-4, B-6, B-9;'
      ' B-4 это и есть остаток про .env в прозе, B-9 на этой машине не описан)."'
      ' --pulse "2026-08-02 08:00 | 🟢 | read-only ревизия | детали→cc_log"')
ok(not blocked(G4), "02.08 07:58 DONE — строка, НАЗВАВШАЯ этот самый остаток, и им же убитая")

G5 = ('timeout 300 ' + PY + ' cclog.py DONE "Дежурный по карточкам, фаза 1 (коммит 20ebbc1).'
      ' Дефолт CARD_DUTY=0 — ветка мертва, в прод НЕ включена."'
      ' --pulse "2026-08-04 | 🟢 | дежурный фаза 1 в main | ничего не жду; включение —'
      ' CARD_DUTY=1 в .env + рестарт демона (дефолт 0, ветка мертва) | детали→cc_log" 2>&1'
      ' | tail -12')
ok(not blocked(G5), "04.08 11:56 DONE «CARD_DUTY=1 в .env + рестарт» — инструкция ВЛАДЕЛЬЦУ")

# Освобождение НЕ означает «зелёное во всём»: журнальная строка как шла в defer по остальным
# слоям, так и идёт — правка снимает ровно жёсткий блок, ничего не разрешая.
ok(all(hit_of(g)[0] in ("green", "ambiguous") for g in (G1, G2, G3, G5)),
   "освобождённые строки уходят в defer к слоям settings, а не в красное гарда")


# ══ (2) НАСТОЯЩЕЕ ЧТЕНИЕ ФАЙЛА СЕКРЕТОВ — БЛОК КАК ПРЕЖДЕ ════════════════════════════════════
# Тоже ДОСЛОВНЫЕ живые команды из тех же транскриптов того же окна.
print("\n(2) живые голдены: настоящее чтение секретов — блок остаётся")

for label, cmd in (
    ("grep по флагам конфига (05.08 05:24)",
     'grep -n "^CURATOR\\|^PLAN_ADAPT\\|^STEP_SELFHEAL\\|^CARD_DUTY\\|^TASK_TIMEOUT" ' + SECRETS),
    ("grep -c с ЧИСЛОМ вместо значения (03.08 07:55)",
     'grep -c "^FEED_CHAT_ID=" ' + SECRETS + ' ; echo "---PC_DEV---"'),
    ("grep с маскировкой значения sed (03.08 06:11)",
     'grep -n "FEED_CHAT_ID\\|FEED_" ' + SECRETS + " | sed 's/=.*/=<СКРЫТО>/'"),
    ("grep -rn по двум файлам, секреты вторым (24.07 21:04)",
     'grep -rn "SOFT_ODO" /root/turbobaby-manager-bot/splinter.py ' + SECRETS + " 2>&1 | head -20"),
    ("stat -c по mtime (04.08 12:20)",
     "stat -c '%y %n' /root/turbobaby-manager-bot/card_duty.py " + SECRETS),
    ("load_dotenv в инлайн-коде (30.07 08:40)",
     PY + " -c 'from dotenv import load_dotenv; load_dotenv(\"" + SECRETS + "\")'"),
    ("cat файла секретов",
     "cat " + SECRETS),
):
    ok(blocked(cmd), label)

ok(not PG.can_approve("block", "env_hard_block"),
   "approve по-прежнему НЕВОЗМОЖЕН (жёсткий блок, кнопки нет)")
ok("секрет" in PG._block_reason("env_hard_block", "env_target=" + SECRETS),
   "текст блока про секреты цел и называет цель")


# ══ (3) ФОРМЫ ПУТИ В АРГУМЕНТЕ СКРИПТА — ОБРАЩЕНИЕ, КРАСНОЕ ══════════════════════════════════
print("\n(3) путь к секретам аргументом скрипта — блок")

for label, cmd in (
    ("голден докстринга: dump.py с абсолютным путём", "python3 dump.py /root/app/.env"),
    ("путь аргументом cclog", PY + " cclog.py DONE " + SECRETS),
    ("относительный путь", PY + " tool.py ./.env"),
    ("голое имя файла", PY + " tool.py .env"),
    ("домашний каталог", PY + " tool.py ~/.env"),
    ("вариант файла .env.local", PY + " tool.py --config .env.local"),
    ("флаг=значение", PY + " tool.py --config=/root/app/.env"),
    ("длинный флаг с путём вторым токеном", PY + " tool.py --dotenv /root/app/.env.prod"),
    ("путь СРЕДИ прозаических аргументов", PY + ' cclog.py DONE "правил конфиг" ' + SECRETS),
    ("путь в кавычках", PY + ' tool.py "' + SECRETS + '"'),
):
    ok(blocked(cmd), label)


# ══ (4) FAIL-CLOSED: СОМНЕНИЕ ПО-ПРЕЖНЕМУ РЕШАЕТСЯ В КРАСНОЕ ═════════════════════════════════
print("\n(4) fail-closed: где разбирать нечего — прежний полный скан")

for label, cmd in (
    ("нет .py-токена: argv не вырезается вовсе", PY + " -m runner /root/app/.env"),
    ("инлайн-код -c: тело И ЕСТЬ команда",
     PY + " -c \"open('" + SECRETS + "').read()\""),
    ("подстановка ВНУТРИ аргумента скрипта",
     PY + ' cclog.py DONE "$(cat /root/app/.env)"'),
    ("обратные кавычки в аргументе",
     PY + " cclog.py DONE \"`cat /root/app/.env`\""),
    ("чтение РЯДОМ в цепи, проза в скрипте",
     PY + ' cclog.py DONE "правил .env" && cat /root/app/.env'),
    ("чтение ПЕРЕД скриптом в цепи",
     "cat /root/app/.env ; " + PY + ' cclog.py DONE "готово"'),
    ("кривые кавычки → грубые токены, скан полный",
     PY + ' cclog.py DONE "незакрытая кавычка ' + SECRETS),
    ("heredoc в интерпретатор", PY + " - <<'PY'\nopen('" + SECRETS + "')\nPY"),
    ("аргумент-путь ПОСЛЕ прозы с именем",
     PY + ' cclog.py DONE "поправил .env" --file /root/app/.env'),
):
    ok(blocked(cmd), label)


# ══ (5) ГРАНИЦЫ: ПРОЧИЕ УЛИКИ И СОСЕДНИЕ КЛАССЫ НЕ ТРОНУТЫ ══════════════════════════════════
print("\n(5) границы: соседние классы байт-в-байт")

k, h = hit_of(PY + ' run.py "UPDATE bikes SET km=1" other.db')
ok(k == "red" and h == "sqlite", "улика SQL-write в argv держится (hit=%s)" % (h or "—"))

k, h = hit_of(PY + " tool.py /root/data/clients.db")
ok(h != "env_hard_block", "улика .db — свой класс, к секретам отношения не имеет")

k, h = hit_of('grep -n ".env" /root/turbobaby-manager-bot/bot.py')
ok(h != "env_hard_block", "шаблон grep — данные (класс «данные ≠ команда», был зелёным)")

k, h = hit_of('git commit -m "правка .env форматом"')
ok(h != "env_hard_block", "текст git -m — данные (bd5d516, был зелёным)")

k, h = hit_of("pkill -9 splinter")
ok(k == "block" and h == "proc_hard_block", "жёсткий блок процессов не тронут (hit=%s)" % (h or "—"))

k, h = hit_of(PY + " cclog.py DONE " + SECRETS + " && pkill -9 splinter")
ok(k == "block" and h == "proc_hard_block",
   "порядок жёстких классов цел: процессы судятся ПЕРВЫМИ (hit=%s)" % (h or "—"))

k, h = hit_of("rm -f /root/turbobaby-manager-bot/splinter.py")
ok(k == "red" and h == "delete_file", "класс удаления вне /tmp не тронут (hit=%s)" % (h or "—"))

k, h = hit_of(PY + " cclog.py DONE 'убрал /tmp/tb_scratch/probe.py'")
ok(k in ("green", "ambiguous"), "журнальная строка про уборку черновика — не красное")


# ══ (6) ПРЕДИКАТ ПОШТУЧНО ═══════════════════════════════════════════════════════════════════
print("\n(6) _env_path_arg: путь — да, предложение — нет")

# Предикат берётся через getattr НАМЕРЕННО: этот же файл гоняется по ДО-правочному дереву
# (доказательство «красный до, зелёный после»), где функции ещё нет. Падение с AttributeError
# дало бы обрыв прогона вместо ЧИСЛА — а число здесь и есть предмет доказательства.
_pred = getattr(PG, "_env_path_arg", None)

for tok, want, label in (
    (".env", True, "голое имя"),
    ("/root/app/.env", True, "абсолютный путь"),
    ("./.env", True, "относительный путь"),
    (".env.local", True, "вариант файла"),
    (".env.production", True, "вариант с длинным суффиксом"),
    ("--config=/root/app/.env", True, "флаг=значение"),
    ('"/root/app/.env"', True, "в кавычках (грубая токенизация)"),
    ("правил .env, добавил флаг", False, "предложение с именем и запятой"),
    ("запрет cat/grep .env классом в CLAUDE.md", False, "предложение живого голдена"),
    ("CARD_DUTY=1 в .env + рестарт демона", False, "инструкция владельцу"),
    ("bash .env/kill9", False, "перечисление классов через слэш без пробела вокруг"),
    ("splinter.py", False, "посторонний путь без имени секрета"),
    ("DONE", False, "обычное слово"),
    ("", False, "пустой токен"),
    (None, False, "None не роняет предикат"),
):
    if _pred is None:
        ok(False, "%s → предиката _env_path_arg в дереве НЕТ" % label)
        continue
    got = _pred(tok)
    ok(got is want or got == want, "%s → %s" % (label, "операнд" if want else "данные"))

# «bash .env/kill9» — единственная форма голдена, где имя стоит без пробела ПОСЛЕ себя: это
# перечисление классов доктрины, а не путь. Пробел ВНУТРИ токена решает раньше, чем basename,
# поэтому весь аргумент-предложение уходит в данные целиком — проверено строкой выше и G1.

print("\nИТОГ: %d/%d" % (res.count(True), len(res)))
if res.count(False):
    print("КРАСНЫХ: %d" % res.count(False))
    sys.exit(1)
print("Все проверки зелёные.")
