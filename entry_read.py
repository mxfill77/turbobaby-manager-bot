#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ENTRY_READ r1 — читатель ТЕКУЩЕГО входа и состояния splinter, только чтение (RCFIX2010c, READER_SPEC r2; build3, круг 3).

Запуск на сервере только потоком с ПК, файла на сервере не создаётся:
    ssh … "cd / && python3 -I -S -B - --sha <40> --state release|truth_off|base --label <L> --not-before <ct>
           --db-sha <64> --du-sha <64> [--expect-run K] [--prev-run K] [--expect-wa K] [--guard unpark]" < entry_read_<b12>.py
    … python3 -I -S -B - --recheck --sha <RB> --label <L> --db-sha <64> --du-sha <64> --expect-run K0 --expect-wa KWA1
           --against "<квитанция --guard>"
stdout — ровно одна строка (квитанция ENTRY_READ r1 …, строка USAGE или строка повторной сверки), stderr пуст.
Коды: 0 CLEAN (в --guard — PASS) · 51 PARKED · 52 NOPOLL · 53 DOWN · 54 MIXED · 55 ARMED · 58 --guard REFUSED ·
59 UNKNOWN (в том числе internal) · 50 USAGE · 63 --recheck: дрейф или неполнота (строка UNPARK_END refused recheck=<поле>).

Что читает (каждый вызов процесса — через World.run, argv сверяется с белым списком _ARGV_OK в самой функции; у каждого
вызова тайм-аут, срыв — «не прочитано», а не ноль): `systemctl show` splinter и wa-agent (личность — три чтения S0/S1/S2,
конфигурация), /proc/<pid>/stat и /proc/<pid>/cgroup, boot_id, adjtimex(modes=0), пояс СВОЕГО процесса и
readlink /etc/localtime, git по R (rev-parse, status, ls-tree, hash-object без -w), ls-remote origin, два своих drop-in
(lstat + sha256, каталог не листается), splinter.log одним ограниченным проходом.
Чего НЕ читает никогда (READER_SPEC r2 п.1, Codex TB-REVIEW-2110-RECOVERY-V :16): свойство Environment юнита, окружение
процессов, их командные строки, файлы окружения, ключи, клиентские базы. Окружение детей собрано из констант (_CHILD_ENV),
собственное окружение процесса модуль не читает. git — с GIT_OPTIONAL_LOCKS=0, hash-object без -w.

ls-remote (r2 п.2, Codex :16 «только уже доверенный транспорт», build2 M1 линзы безопасности). Транспорт — только ssh
(GIT_ALLOW_PROTOCOL=ssh: https с помощником учётных данных, file://, ext:: отвергаются самим git → origin «?»), ключ хоста —
только уже доверенный. Опции ssh (SSH_OPTS, замок теста — на ПОЛНЫЙ набор) закрывают каждую запись клиента OpenSSH, которую
закрывает флаг командной строки (флаг -o сильнее любого ssh_config — первое полученное значение побеждает, ssh_config(5)):
  · StrictHostKeyChecking=yes — неизвестный или изменённый ключ → отказ без добавления; BatchMode=yes — без вопросов;
  · UpdateHostKeys=no — без ротации ключей хоста в known_hosts (расширение hostkeys-00@openssh.com);
  · CheckHostIP=no — без дописывания в known_hosts записи IP для ключа, уже известного по имени (sshconnect.c: HOST_OK при
    ip_status HOST_NEW → add_host_to_hostfile, «Permanently added … for IP address»; умолчание yes до OpenSSH 8.5);
  · ControlMaster=no, ControlPath=none — без сокета мультиплексирования из ssh_config;
  · PermitLocalCommand=no — без LocalCommand; ClearAllForwardings=yes — без форвардов из конфига (и сокетов unix-форвардов);
  · ForwardAgent=no, ForwardX11=no (без xauth во временном каталоге), Tunnel=no (без tun-устройства).
  Пределы (флагом не закрываются, названы): ProxyCommand / ProxyJump / KnownHostsCommand / Match exec / Include из
  пользовательского и системного ssh_config исполняют программы, и что они пишут, модуль не знает — выключить их значило бы
  сломать законный транспорт, а KnownHostsCommand=none неизвестен OpenSSH < 8.5 и уронил бы чтение; ssh сам создаёт ~/.ssh,
  если каталога нет (без -F; -F /dev/null отключил бы конфиг ключа origin; без каталога нет и ключа — чтение падает, origin
  «?»); core.fsmonitor у git status и фильтры hash-object из конфигурации git сервера не нейтрализуются (m4 линзы
  безопасности). Версия OpenSSH, ssh_config и .gitconfig сервера не читались: опции выбраны из известных OpenSSH ≥ 6.8.
  Локальный ref вместо ls-remote НЕ взят: refs/remotes/origin/main показывает последний fetch, а не origin, и условие CLEAN
  «origin = sha» ослабло бы до «последний fetch = sha». Сбой ls-remote — origin «?» → CLEAN блокирован (UNKNOWN rd_origin).

Журнал (READER_SPEC §8 + r2 п.3). Один проход по месту: читается РОВНО префикс размера на открытии (потолок LOG_CAP_BYTES;
больше — UNKNOWN log_cap); прочитано меньше — log_short; файл подменён (другой inode по пути) или стал короче, или изменился
mtime при прежнем размере — log_rot. Рост файла за проход ротацией НЕ считается (толкование r2 п.3 ПРИНЯТО К3 21.10:
читается неизменный префикс, смену процесса за проход ловит третье чтение личности S2). Строки не хранятся, текст журнала
наружу не выходит. Сегмент — от последней по месту записи a (bot.py:94) уровня INFO до конца.
Правила записей — health r6 (ПРИНЯТО К3 21.10: действуют на ВЕСЬ текущий запуск по времени, и ниже f, как у
health._run_verdict) и правило pend health r7 (build3; health рабочей копии rcfix2010 sha256 1a8ba76f… :663, :692–696,
:728 — r7 · verify8 K3/K4). «Не зеленее health» — факт тестов, а не вывод: сетка B (с вставками pend_win / pend_seg) и
b4 с оракулом ENTRY_READ_HEALTH = health r7 (1a8ba76f…) — нарушений 0; оракул по умолчанию — health дерева f64ee79 (r5),
на pend он мягче r7, и там читатель строже:
  · запись — только ТОЧНЫЙ формат bot.py:73, как health r6 _REC_RE: уровень — одно из пяти имён logging (LEVELS), имя —
    точечный идентификатор (_NAME_B); иная раскладка с той же меткой («[I]», «имя:номер») — строка с меткой неизвестной формы;
  · метка неизвестной формы, неразобранная метка записи, байты не UTF-8 в текущем запуске → stamp / utf8; запись раньше уже
    прочитанной больше чем на 120 с → clock_step;
  · pend (health r7): метка неизвестной формы с собственной датой ≥ старта ДО начала запуска → stamp, если после неё не было
    ЗАПИСИ ИСТОРИИ — записи с меткой < старт − 2 с (WIN_BACK_S) по месту ДО первой записи с меткой ≥ старта. Запись в окне
    [старт − 2 с, старт) и любая запись ниже начала запуска (вставка сообщением, шаг часов назад, чужая запоздалая) pend не
    снимают (r6 снимал любой записью < старта — у читателя build2 это давало CLEAN при health r7 UNKNOWN);
  · НЕОДНОЗНАЧНОСТЬ ОКНА (health r6, verify7 M1; build2 M2 линзы атаки) — по ВСЕМУ журналу, мимо выбора сегмента: записей
    загрузки (a) или записей входа (c) ЛЮБОГО уровня с меткой ≥ EMS − 2 с (WIN_BACK_S) больше одной → UNKNOWN win_many.
  Предел (1) health r6, общий с читателем: в окне ровно одна запись загрузки и не больше одной записи входа, и они ЧУЖИЕ
  (текущий завис до bot.py:94, а цепочку написал второй писатель). Закрыто там, где противоречие видно по коду: при
  --state release|truth_off чужая цепочка базы над кодом V с code=OK — UNKNOWN gen_contra (зеркально: цепочка кандидата
  при --state base и code=OK), а законное M-CODE всегда несёт code_newer. Остаётся пределом: чужая полная цепочка
  кандидата при --state release|truth_off (health r6 — тоже OK) и чужая цепочка базы при --state base (у health для базы
  вердикта OK нет вовсе: «polling без строки входа» → UNKNOWN по построению, сравнивать не с чем) — 0e и V3 тогда CLEAN.

CLEAN — проверенная структура и согласованность запуска (READER_SPEC r2 п.7): не отзывчивость, не непрерывное здоровье, не
отсутствие потерь и не клиентский результат; 300 с — технический порог. Квитанция — факт, а не GO. CLEAN выводится
ПОЛОЖИТЕЛЬНО (build3, MAJOR-1 линзы code круга 2): нет ни одного кода И _clean_proven по ФАКТАМ чтений (не по отсутствию
кодов) подтвердил все условия: строки таблицы §9.3 и её общие условия — «личность перечитана» (S0 = S1 = S2, boot0 =
boot2, birth0 = birth1, wa-agent S0 = S2, всё прочитано), ho, tb, часы SYNC, пояс UTC, ndr=no/no — и условия §5/§6/§8,
которые в build2 держали только коды: юнит active/running и InvocationID, рождение/cgroup/AE, --expect-run/--expect-wa/
--prev-run, not-before / шаг часов / метки впереди, факты прохода журнала (счётчики меток неизвестной формы, неразобранных
меток, шагов назад и байт не UTF-8 в запуске; открытая метка pend; потолок строк сегмента; счёт по окну) и структура
сегмента (посылка окна a, «выше сегмента», двойники, порядок, остановка, d/e/f уровня INFO). Кодов нет, а условие не
подтверждено → UNKNOWN clean_gate. Факты прохода журнала записываются отдельными строками, независимо от кодов. Что это
даёт — факт теста h8b, а не обещание на любой вход: мутант «строка → pass» по КАЖДОЙ строке добавления кода
(codes.add, generic.add, codes |=, self.pend = True, self.cap = True) и каждой строке факта ворот (self.cnt[…] += 1,
self.ahead_at, self.lines_max) на наборе сценариев, где эта строка исполняется (у каждой строки такой сценарий есть), —
ни одного CLEAN.

Отличия от текста READER_SPEC r1 и r2 (названы; блок r2 приоритетен):
  · tz=<UTC|NOTUTC|?>:<link|file|none|?> — второе поле теперь источник пояса системы (readlink /etc/localtime), а не счёт
    TZ в Environment (r2 п.1: Environment не читается; кода rd_env нет);
  · аргументы r2 п.5 (ПРИНЯТЫ К3 21.10): --expect-wa K, режим --recheck с --against <квитанция --guard>, коды log_cap,
    log_rot (r2 п.3) и выход 63. build2: --expect-wa годен в ЛЮБОМ режиме (Codex :12 «сверять KWA1 в V2a/V3»): ключ wa-agent
    S2 ≠ K → UNKNOWN expect_wa; при --guard он ОБЯЗАТЕЛЕН (USAGE guard_needs_expect_wa);
  · --prev-run K (build2, по находке линзы code): NRestarts текущего запуска = 0, а не = K.nr. Ручной `systemctl restart`
    счётчик ОБНУЛЯЕТ (systemd service.c: service_stop ставит forbid_restart, service_enter_dead без автоперезапуска —
    flush_n_restarts, service_start при нём — n_restarts = 0; по памяти исходников, на сервере не сверено). При K.nr = 0
    обе семантики совпадают; если сервер счётчик не обнуляет, V3 при K.nr > 0 даёт UNKNOWN prev_run — отказ, а не CLEAN;
  · «над сегментом» считается от целой секунды метки systemd, а не от ⌊EMS точный⌋, — строже; нижняя граница окна записей
    начала — max(⌊EMS точный⌋, EMS текстом) (build2: при дрожании −5 мс…0 окно не шире health «старт ≤ метка»);
  · у простоя (PARKED) коды цепочки старта gen/state/state_src/fv/handoff/tb_start не ставятся (судятся только при POLLING
    и NOPOLL): слово флагов и вход — причина простоя, а не расхождение (RECOVERY_PATH §1 E-PARK: why ⊆ {park, dropin_armed});
  · EMS_EPS_S: нижняя граница «EMS точный − EMS текстом» — −5 мс (дрожание пары часов на чтении), а не 0 (§6);
  · D = {DU} при L = ∅ → BAD (строже §9.1, где BAD только next(L) = {DU});
  · квитанция несёт dpaths=<sha256[:12] строки DropInPaths> (только пути, без тел); --recheck сверяет его — чужой drop-in,
    подложенный с daemon-reload между охраной и рестартом, даёт отказ dropin (содержимое юнита и чужих drop-in не читается:
    там Environment, — их правка с daemon-reload в окне остаётся пределом §16 п.2);
  · --recheck в конце перечитывает и wa-agent; квитанция охраны годна только при dropin=OK;
  · аргументы и квитанция сверяются fullmatch (значение с конечным «\\n» формы не проходит).
"""
import errno
import hashlib
import os
import re
import stat
import subprocess
import sys
import time

TAG = "r1"
# --- пути сервера (READER_SPEC §2; в тесте подменяется весь фасад World) -------------------------------------------------
R = "/root/turbobaby-manager-bot"                       # = шаг 0 r11 :67
LOG = R + "/splinter.log"                               # = r3c :93
UNIT = "splinter"
WA = "wa-agent"
DD = "/etc/systemd/system/splinter.service.d"           # = R0 r7 :162–164
DB = DD + "/zz-k3-closetruth.conf"
DU = DD + "/zz-k3-closetruth.undo.conf"
BOOT_ID = "/proc/sys/kernel/random/boot_id"
LOCALTIME = "/etc/localtime"
BASE_BOT_BLOB = "6d18b487aa9b8f8a786e6cd0932538670110d771"      # = git rev-parse 947953e:bot.py
BASE_SPL_BLOB = "37ed9a8e02c3181592b1e84ef195b6a7e3e6bf44"      # = git rev-parse 947953e:splinter.py

# --- пороги ---------------------------------------------------------------------------------------------------------------
START_SKEW_S = 300          # окно записей начала [max(⌊EMS точный⌋, EMS), EMS + 300] и возраст запуска (= SC_START_SKEW, health)
WIN_BACK_S = 2              # счёт записей начала по окну [EMS − 2 с, …) мимо сегмента (= health r6 _WIN_BACK_S)
BIRTH_TOL_S = 2.0           # |starttime/CLK_TCK − EMSmono| (рождение PID этим стартом)
AE_TOL_S = 2.0              # |ActiveEnterMono − ExecMainStartMono|
MAXERR_US = 16000000        # adjtimex maxerror: критерий ntp_synced() systemd (U3)
EMS_STEP_S = 1.5            # 0 ≤ EMS точный − EMS текстом < 1,5 с (метка systemd обрезана до секунды)
EMS_EPS_S = 0.005           # дрожание пары «стенные часы / монотонные» на чтении (две стенные метки вокруг одной монотонной)
OFFSET_DRIFT_S = 0.5        # сдвиг пары стенные−монотонные между t0 и t2 больше — шаг часов во время прогона
AHEAD_S = 2                 # метка журнала / старт юнита позже t2 + 2 с — часы журнала впереди
BACK_S = 120                # запись журнала раньше уже прочитанной записи текущего запуска больше чем на 120 с (= health)
T_CMD_S = 15                # тайм-аут systemctl / git
T_ORIGIN_S = 60             # тайм-аут ls-remote (сеть)
LOG_CAP_BYTES = 256 << 20   # потолок splinter.log: ≈2,8 × живого размера ≈90 МБ (verify5, 21.10)
RUN_LINES_CAP = 3000000     # потолок строк одного сегмента (≈ LOG_CAP_BYTES / 85 байт средней строки)
CHUNK = 1 << 13             # кусок чтения журнала — 8 КиБ (как health._READ_CHUNK)
CHUNK_GROW_MAX = 1 << 22    # без b"\n" кусок растёт до 4 МиБ (как health._READ_GROW_MAX)
SMALL_CAP = 1 << 16         # потолок малых файлов (/proc, boot_id, drop-in)
RECEIPT_MAX = 2048          # потолок длины квитанции (полный словарь why ≈ 750 знаков)

CODE = {"CLEAN": 0, "PARKED": 51, "NOPOLL": 52, "DOWN": 53, "MIXED": 54, "ARMED": 55, "UNKNOWN": 59}
RC_USAGE = 50
RC_REFUSED = 58
RC_RECHECK = 63

# --- словарь причин: порядок = приоритет класса (READER_SPEC §9.2 + r2 п.3 + build2) ---------------------------------------
WHY_UNKNOWN = ("rd_unit", "rd_wa", "rd_proc", "rd_boot", "rd_cfg", "rd_dropin", "rd_git", "rd_log", "log_short",
               "log_cap", "log_rot", "ident_changed", "boot_changed", "wa_ident", "expect_run", "expect_wa", "prev_run",
               "birth", "cgroup", "ae_ems", "unit_transient", "clock_rd", "clock_unsync", "clock_past", "clock_step",
               "clock_ahead", "zone", "premise", "win_many", "chain_dup", "chain_order", "chain_partial",
               "entry_grammar", "flags_grammar", "flags_entry", "stamp", "utf8", "stop_line", "park_contra", "gen_contra",
               "young", "clean_gate", "internal", "rd_origin")
WHY_MIXED = ("gen", "state", "state_src", "fv", "head", "origin", "dirty", "blob", "code_newer", "base_blob",
             "handoff", "tb_start", "wa_down", "wa_newer", "dropin_bad")
WHY_ARMED = ("dropin_armed", "ndr")
GUARD_WHY = ("guard_park", "guard_run", "guard_code", "guard_ndr", "guard_dropin", "guard_wa", "guard_clock")
ORDER = WHY_UNKNOWN + ("down", "park", "nopoll") + WHY_MIXED + WHY_ARMED
CLASS_OF = dict([(c, "UNKNOWN") for c in WHY_UNKNOWN] + [("down", "DOWN"), ("park", "PARKED"), ("nopoll", "NOPOLL")]
                + [(c, "MIXED") for c in WHY_MIXED] + [(c, "ARMED") for c in WHY_ARMED])

# --- литералы журнала (bot.py вершины :94/:106/:109/:1662/:1665/:1778/:1346/:1353/:1537; база :90/:101/:103/:1749/:1340/
# :1347; сверяет тест A) ------------------------------------------------------------------------------------------------------
LOGGER = "turbobaby"
SCHED_LOGGER = "apscheduler.scheduler"
A_MSG = "  Auditor: ✅ подключён к splinter._send (надзор за языком исходящих)"
B_HEAD = "  🧩 флаги выпуска: "
C_HEAD = "  🚦 вход выпуска: "
D_MSG = "Bot polling started. Press Ctrl+C to stop."
E_MSG = "TurboBaby Manager Bot — STARTING"
F_HEAD = "  🔁 передача карточек: "
STOP_HEAD = "  🛑 дренаж остановки: "
SHUT_MSG = "Scheduler has been shut down"
PARK_TAIL = "обработчики не зарегистрированы, опрос не начат — процесс ждёт остановки"
ENTRY_LIST = "перечень выпуска release | truth_off"
TB_LINE = "Traceback (most recent call last):"
INTAKE_NEEDLES = ("Splinter [intake] ", "🆕 INTAKE", "карточка активации во Входящие", "карточка закрытия во Входящие")
FLAG_KEYS = ("INTAKE_CONFIRM_STRICT", "CONTRACT_REF_GEN", "CLOSE_TRUTH", "CLOSE_ACCRUAL", "HANDOVER_FACTS")
BASE_KEYS = ("INTAKE_CONFIRM_STRICT", "CONTRACT_REF_GEN")
KEY_ABBR = {"INTAKE_CONFIRM_STRICT": "STRICT", "CONTRACT_REF_GEN": "GEN", "CLOSE_TRUTH": "TRUTH",
            "CLOSE_ACCRUAL": "ACCR", "HANDOVER_FACTS": "HOF"}
_W_ON = ("ВКЛ (задан)", "ВКЛ (не задан)")
_W_OFF = ("ВЫКЛ (задан)", "ВЫКЛ (не задан)")
ENTRY_STATES = (("release", (_W_ON, _W_OFF, _W_ON, _W_OFF, _W_OFF)),          # = splinter.RELEASE_ENTRY_STATES (слова)
                ("truth_off", (_W_ON, _W_OFF, ("ВЫКЛ (задан)",), _W_OFF, _W_OFF)))
WORD_TOKEN = (("ВКЛ (задан)", "1z"), ("ВКЛ (не задан)", "1n"), ("ВЫКЛ (задан)", "0z"), ("ВЫКЛ (не задан)", "0n"))
# Шаблоны строки флагов — ДОСЛОВНО правые части SC_FLAGS_RE_RELEASE / SC_FLAGS_RE_TRUTH_OFF (srv_splinter_checks_rc2010.sh
# :52–53, sha 4afe3e88…) и SC_FLAGS_RE (srv_splinter_checks.sh 5db211d1 :23); байтовую сверку делает адресная проверка §15.
FLAGS_RE = {
    "release": r"🧩 флаги выпуска: INTAKE_CONFIRM_STRICT=ВКЛ \((не )?задан\) · CONTRACT_REF_GEN=ВЫКЛ \((не )?задан\) · CLOSE_TRUTH=ВКЛ \((не )?задан\) · CLOSE_ACCRUAL=ВЫКЛ \((не )?задан\) · HANDOVER_FACTS=ВЫКЛ \((не )?задан\)$",
    "truth_off": r"🧩 флаги выпуска: INTAKE_CONFIRM_STRICT=ВКЛ \((не )?задан\) · CONTRACT_REF_GEN=ВЫКЛ \((не )?задан\) · CLOSE_TRUTH=ВЫКЛ \(задан\) · CLOSE_ACCRUAL=ВЫКЛ \((не )?задан\) · HANDOVER_FACTS=ВЫКЛ \((не )?задан\)$",
}
BASE_FLAGS_RE = r"🧩 флаги выпуска: INTAKE_CONFIRM_STRICT=ВКЛ \((не )?задан\) · CONTRACT_REF_GEN=ВЫКЛ \((не )?задан\)$"

_ENTRY_OK = re.compile("^OK — состояние (release|truth_off) · " + " · ".join(re.escape(k) + " OK" for k in FLAG_KEYS)
                       + "$")
_ENTRY_PARK = re.compile("^(MISMATCH|UNKNOWN) — .*; " + re.escape(PARK_TAIL) + "$")
_ENTRY_BAD = re.compile("(" + "|".join(re.escape(k) for k in FLAG_KEYS) + ") (MISMATCH|UNKNOWN)")
_NOTREAD = re.compile(r"^НЕ ПРОЧИТАНЫ \([A-Za-z_][A-Za-z0-9_]*\)$")
_HO_APPLIED = re.compile(r"^применена \(sha [0-9a-f]{8}\): брони ([0-9]+) · выдачи ([0-9]+) · закрытия ([0-9]+)"
                         r" · занятых мест ([0-9]+)$")
# запись ЛЮБОГО логгера ТОЧНОГО формата bot.py:73 (= health r6 _REC_RE: уровень — одно из пяти имён logging, имя — точечный
# идентификатор) и метко-подобный префикс (= health._STAMPISH_RE); байты, цифры только ASCII
LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
_NAME_B = rb"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*"
_REC_B = re.compile(rb"(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2}),(\d{3}) \[(" + "|".join(LEVELS).encode("ascii")
                    + rb")\] (" + _NAME_B + rb"): ")
_STAMPISH_B = re.compile(rb"(\d{4})[-/.](\d{2})[-/.](\d{2})[T ](\d{2}):(\d{2}):(\d{2})")
_A_B, _D_B, _E_B, _SHUT_B = A_MSG.encode(), D_MSG.encode(), E_MSG.encode(), SHUT_MSG.encode()
_B_B, _C_B, _F_B, _STOP_B = B_HEAD.encode(), C_HEAD.encode(), F_HEAD.encode(), STOP_HEAD.encode()
_TB_B = TB_LINE.encode()
_INTAKE_B = tuple(x.encode() for x in INTAKE_NEEDLES)
_LOGGER_B, _SCHED_B = LOGGER.encode(), SCHED_LOGGER.encode()
CHAIN = ("a", "b", "c", "d", "e", "f")
_RANK = {"a": 0, "b": 1, "c": 2, "d": 3, "e": 4, "f": 5}

# --- systemd ---------------------------------------------------------------------------------------------------------------
ID_PROPS = ("MainPID", "ExecMainStartTimestamp", "ExecMainStartTimestampMonotonic", "ActiveEnterTimestamp",
            "ActiveEnterTimestampMonotonic", "NRestarts", "ActiveState", "SubState", "InvocationID")
CFG_SP = ("LoadState", "NeedDaemonReload", "DropInPaths")
CFG_WA = ("LoadState", "NeedDaemonReload")
ACTIVE_STATES = ("active", "reloading", "inactive", "failed", "activating", "deactivating", "maintenance", "refreshing")
SUB_STATES = ("dead", "condition", "start-pre", "start", "start-post", "running", "exited", "reload", "reload-signal",
              "reload-notify", "stop", "stop-watchdog", "stop-sigterm", "stop-sigkill", "stop-post", "final-watchdog",
              "final-sigterm", "final-sigkill", "failed", "dead-before-auto-restart", "failed-before-auto-restart",
              "dead-resources-pinned", "auto-restart", "auto-restart-queued", "cleaning")
_SD_TS = re.compile(r"^(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun) ([0-9]{4})-([0-9]{2})-([0-9]{2}) ([0-9]{2}):([0-9]{2}):([0-9]{2}) UTC$")
_BOOT_ID = re.compile(rb"^([0-9a-f]{8})-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\n?$")
_UTC_LINK = re.compile(r"(?:^|/)(?:Etc/)?(?:UTC|UCT|Universal|Zulu|GMT|GMT0|GMT\+0|GMT-0|Greenwich)$")

# --- белый список процессов (READER_SPEC §4; ни одного restart/start/stop/daemon-reload/fetch/reset/merge/push/-w) ----------
ARGV_SHOW_SP = ("systemctl", "show", UNIT, "--property=" + ",".join(ID_PROPS))
ARGV_SHOW_WA = ("systemctl", "show", WA, "--property=" + ",".join(ID_PROPS))
ARGV_CFG_SP = ("systemctl", "show", UNIT, "--property=" + ",".join(CFG_SP))
ARGV_CFG_WA = ("systemctl", "show", WA, "--property=" + ",".join(CFG_WA))
ARGV_HEAD = ("git", "-C", R, "rev-parse", "HEAD")
ARGV_STATUS = ("git", "-C", R, "status", "--porcelain", "--untracked-files=no")
ARGV_LSTREE = ("git", "-C", R, "ls-tree", "HEAD")
ARGV_ORIGIN = ("git", "-C", R, "ls-remote", "origin", "refs/heads/main")
ARGV_HASH = ("git", "-C", R, "hash-object", "--")          # хвост — только имена *.py корня из ls-tree
_ARGV_OK = (ARGV_SHOW_SP, ARGV_SHOW_WA, ARGV_CFG_SP, ARGV_CFG_WA, ARGV_HEAD, ARGV_STATUS, ARGV_LSTREE, ARGV_ORIGIN)
_PY_NAME = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]*\.py$")
# ssh ls-remote: только уже доверенный ключ хоста и ни одной записи клиента, закрываемой флагом (шапка, «ls-remote»)
SSH_OPTS = ("BatchMode=yes", "StrictHostKeyChecking=yes", "UpdateHostKeys=no", "CheckHostIP=no", "ControlMaster=no",
            "ControlPath=none", "PermitLocalCommand=no", "ClearAllForwardings=yes", "ForwardAgent=no", "ForwardX11=no",
            "Tunnel=no")
_CHILD_ENV = {"PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C", "TZ": "UTC",
              "HOME": "/root", "GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0", "GIT_ALLOW_PROTOCOL": "ssh",
              "GIT_SSH_COMMAND": "ssh " + " ".join("-o " + x for x in SSH_OPTS)}

# --- аргументы (закрытый набор; argparse не используется; сверка — fullmatch) ---------------------------------------------
_K_RE = re.compile(r"[0-9a-f]{8}\.(?:[0-9a-f]{32}|-)\.[1-9][0-9]*\.[0-9]+\.[0-9]+")
_ARG_FORM = {"--sha": re.compile(r"[0-9a-f]{40}"), "--state": re.compile(r"(?:release|truth_off|base)"),
             "--label": re.compile(r"[A-Za-z0-9_./-]{1,80}"), "--not-before": re.compile(r"[0-9]{1,12}"),
             "--db-sha": re.compile(r"[0-9a-f]{64}"), "--du-sha": re.compile(r"[0-9a-f]{64}"),
             "--expect-run": _K_RE, "--prev-run": _K_RE, "--expect-wa": _K_RE, "--guard": re.compile(r"unpark"),
             "--against": re.compile(r"ENTRY_READ r1 [ -~]{1,%d}" % RECEIPT_MAX)}
_FLAGS = ("--recheck",)
_NORMAL_REQ = ("--sha", "--state", "--label", "--not-before", "--db-sha", "--du-sha")
_RECHECK_REQ = ("--sha", "--label", "--db-sha", "--du-sha", "--expect-run", "--expect-wa", "--against")

# --- квитанция -------------------------------------------------------------------------------------------------------------
_KQ = r"[0-9a-f]{8}\.(?:[0-9a-f]{32}|-)\.[0-9]+\.[0-9]+\.[0-9]+"
_AB = r"(?:STRICT|GEN|TRUTH|ACCR|HOF)\.[MU]"
_TK = r"(?:1z|1n|0z|0n|0d|\?u|xx)"
RECEIPT_RE = re.compile(
    r"^ENTRY_READ r1 class=(CLEAN|PARKED|NOPOLL|DOWN|MIXED|ARMED|UNKNOWN) want=(release|truth_off|base)@([0-9a-f]{40})"
    r" label=([A-Za-z0-9_./-]{1,80}) run=(" + _KQ + r"|\?) unit=([a-z-]{1,32}|\?)/([a-z-]{1,32}|\?)"
    r" ems=([0-9]+|\?) ae=([0-9]+|\?) birth=([+-][0-9]+|\?) age=(-?[0-9]+|\?)"
    r" clock=(SYNC|UNSYNC|\?):([0-9]+|\?) tz=(UTC|NOTUTC|\?):(link|file|none|\?)"
    r" git=([0-9a-f]{12}|\?)/([0-9a-f]{12}|\?)/([0-9]+|\?) code=(OK|NEWER|BLOB|\?):([0-9]+|\?)/([0-9]+|\?)"
    r" gen=(cand|base|\?) proc=(POLLING|PARKED|NOPOLL|DOWN|\?) entry=(release|truth_off|MISMATCH|UNKNOWN|NONE|\?)"
    r" ebad=(" + _AB + r"(?:," + _AB + r")*|-) flags=(" + _TK + r"(?:\." + _TK + r"){1,4}|NOTREAD|NONE|\?)"
    r" ho=(none|applied:[0-9]+|repeat|notapplied|other|NONE|\?) tb=([0-9]+|\?) intake=([0-9]+|\?)"
    r" dropin=(OK|ARMED|BAD|\?):([b?-][u?-])/([b?-][u?-]) dpaths=([0-9a-f]{12}|\?) ndr=(no|yes|\?)/(no|yes|\?)"
    r" wa=(ok|newer|down|\?):(" + _KQ + r"|\?) guard=(-|PASS|REFUSED) why=([a-z0-9_]+(?:,[a-z0-9_]+)*)$")
RECEIPT_FIELDS = ("class", "want_state", "want_sha", "label", "run", "unit_a", "unit_s", "ems", "ae", "birth", "age",
                  "clock", "maxerr", "tz", "tzsrc", "head", "origin", "dirty", "code", "code_k", "code_n", "gen", "proc",
                  "entry", "ebad", "flags", "ho", "tb", "intake", "dropin", "dl", "dd", "dpaths", "ndr_sp", "ndr_wa", "wa",
                  "wa_key", "guard", "why")
# префикс для ПК (тот же текст стоит в lifecycle_er_r1.sh: PFX_ERE; grep -E -x под LC_ALL=C)
RECEIPT_PREFIX_ERE = r"^ENTRY_READ r1 class=(CLEAN|PARKED|NOPOLL|DOWN|MIXED|ARMED|UNKNOWN) want=(release|truth_off|base)@[0-9a-f]{40} label=[A-Za-z0-9_./-]{1,80} run=([0-9a-f]{8}\.([0-9a-f]{32}|-)\.[0-9]+\.[0-9]+\.[0-9]+|\?) [ -~]* guard=(-|PASS|REFUSED) why=[a-z0-9_,]+$"
RECHECK_RE = re.compile(r"^ENTRY_RECHECK r1 PASS label=([A-Za-z0-9_./-]{1,80}) run=(" + _KQ + r") wa=(" + _KQ
                        + r") head=([0-9a-f]{40}) dropin=([b-][u-])/([b-][u-]) ndr=no/no$")
RECHECK_FIELDS = ("against", "rd_unit", "rd_boot", "run", "rd_wa", "wa", "rd_git", "head", "dirty", "rd_cfg", "ndr",
                  "rd_dropin", "dropin", "internal")


class Usage(Exception):
    pass


# ============================================ фасад ввода-вывода =============================================================
class World:
    """Все чтения модуля. Только чтение; тест подменяет фасад целиком (FakeWorld)."""

    def run(self, argv, timeout):
        """→ (rc, stdout bytes). argv вне белого списка — исключение ДО запуска процесса."""
        argv = tuple(argv)
        if not argv_ok(argv):
            raise PermissionError(errno.EPERM, "argv вне белого списка")
        p = subprocess.run(list(argv), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                           timeout=timeout, env=dict(_CHILD_ENV), cwd="/")
        return p.returncode, p.stdout

    def read_small(self, path):
        with open(path, "rb") as fh:
            data = fh.read(SMALL_CAP + 1)
        if len(data) > SMALL_CAP:
            raise OSError(errno.EFBIG, "файл больше потолка", path)
        return data

    def lstat(self, path):
        return os.lstat(path)

    def hash_file(self, path):
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0))
        try:
            data = os.read(fd, SMALL_CAP + 1)
        finally:
            os.close(fd)
        if len(data) > SMALL_CAP:
            raise OSError(errno.EFBIG, "drop-in больше потолка", path)
        return hashlib.sha256(data).hexdigest()

    def mtime(self, name):
        return os.stat(R + "/" + name).st_mtime_ns // 1000000000

    def log_open(self):
        return open(LOG, "rb", buffering=0)

    def log_fstat(self, fh):
        s = os.fstat(fh.fileno())
        return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns)

    def log_pstat(self):
        s = os.stat(LOG)
        return (s.st_dev, s.st_ino)

    def wall(self):
        return time.time()

    def mono(self):
        return time.monotonic()

    def clk_tck(self):
        return os.sysconf("SC_CLK_TCK")

    def adjtimex(self):
        """adjtimex(modes=0) — только чтение. Раскладка заголовка uapi/linux/timex.h (общая 64-битная) годна при x86_64 /
        aarch64 и sizeof(long) = 8; иначе None (→ clock_rd)."""
        import ctypes
        if os.uname().machine not in ("x86_64", "aarch64") or ctypes.sizeof(ctypes.c_long) != 8:
            return None

        class _Timex(ctypes.Structure):
            _fields_ = [("modes", ctypes.c_uint), ("offset", ctypes.c_long), ("freq", ctypes.c_long),
                        ("maxerror", ctypes.c_long), ("esterror", ctypes.c_long), ("status", ctypes.c_int),
                        ("_tail", ctypes.c_byte * 512)]
        tx = _Timex()
        tx.modes = 0
        rc = ctypes.CDLL(None, use_errno=True).adjtimex(ctypes.byref(tx))
        return {"rc": int(rc), "maxerror": int(tx.maxerror), "status": int(tx.status)}

    def zone(self):
        """Пояс СВОЕГО процесса без TZ: снять TZ у себя (unsetenv), tzset → (timezone, altzone, daylight)."""
        os.unsetenv("TZ")
        time.tzset()
        return (time.timezone, time.altzone, time.daylight)

    def readlink(self, path):
        return os.readlink(path)


def argv_ok(argv):
    """Белый список: ровно одна из фиксированных форм, либо hash-object с хвостом из имён *.py корня."""
    argv = tuple(argv)
    if argv in _ARGV_OK:
        return True
    n = len(ARGV_HASH)
    return (len(argv) > n and argv[:n] == ARGV_HASH and all(isinstance(x, str) and _PY_NAME.match(x) for x in argv[n:]))


# ============================================ разбор =========================================================================
def _mdays(y, mo):
    if mo == 2:
        return 29 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 28
    return 30 if mo in (4, 6, 9, 11) else 31


def _epoch(y, mo, d, h, mi, s):
    """Календарная дата-время, принятая за UTC → эпоха (целые секунды) или None (невозможная дата, как datetime)."""
    if not (1 <= y <= 9999 and 1 <= mo <= 12 and 1 <= d <= _mdays(y, mo) and h < 24 and mi < 60 and s < 60):
        return None
    y2 = y - (1 if mo <= 2 else 0)
    era = y2 // 400
    yoe = y2 - era * 400
    doy = (153 * ((mo + 9) % 12) + 2) // 5 + d - 1
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
    return (era * 146097 + doe - 719468) * 86400 + h * 3600 + mi * 60 + s


def _sd_epoch(text):
    """Метка systemctl show под TZ=UTC → эпоха; пусто / n/a → -1; иная форма → None."""
    if text in ("", "n/a"):
        return -1
    m = _SD_TS.match(text)
    if m is None:
        return None
    return _epoch(*(int(g) for g in m.groups()))


def _parse_show(rc, out, keys):
    """Вывод systemctl show → {ключ: значение}, каждый ключ ровно один раз, лишних нет; иначе None."""
    if rc != 0 or not isinstance(out, bytes):
        return None
    try:
        text = out.decode("utf-8")
    except UnicodeDecodeError:
        return None
    got = {}
    for ln in text.split("\n"):
        if ln == "":
            continue
        k, sep, v = ln.partition("=")
        if not sep or k not in keys or k in got:
            return None
        got[k] = v
    return got if len(got) == len(keys) else None


def _ident(p):
    """Свойства личности → словарь или None (любое поле не по форме)."""
    if p is None:
        return None
    num = ("MainPID", "ExecMainStartTimestampMonotonic", "ActiveEnterTimestampMonotonic", "NRestarts")
    if not all(p[k].isdigit() and p[k].isascii() for k in num):
        return None
    inv = p["InvocationID"]
    if inv != "" and not re.match(r"^[0-9a-f]{32}$", inv):
        return None
    if not (re.match(r"^[a-z-]{1,32}$", p["ActiveState"]) and re.match(r"^[a-z-]{1,32}$", p["SubState"])):
        return None
    ems, ae = _sd_epoch(p["ExecMainStartTimestamp"]), _sd_epoch(p["ActiveEnterTimestamp"])
    if ems is None or ae is None:
        return None
    return {"pid": int(p["MainPID"]), "ems": ems, "emsm": int(p["ExecMainStartTimestampMonotonic"]), "ae": ae,
            "aem": int(p["ActiveEnterTimestampMonotonic"]), "nr": int(p["NRestarts"]), "act": p["ActiveState"],
            "sub": p["SubState"], "inv": inv}


def run_key(boot8, u):
    return "%s.%s.%d.%d.%d" % (boot8, u["inv"] or "-", u["pid"], u["emsm"], u["nr"])


def _split_key(k):
    b, inv, pid, emsm, nr = k.split(".")
    return {"boot": b, "inv": "" if inv == "-" else inv, "pid": int(pid), "emsm": int(emsm), "nr": int(nr)}


def _token(word):
    for w, t in WORD_TOKEN:
        if word == w:
            return t
    if word.startswith("ВЫКЛ (задан; ") and word.endswith(")"):
        return "0d"
    if word.startswith("НЕИЗВЕСТНО"):
        return "?u"
    return "xx"


def _ho(body):
    if body == "передачи нет":
        return "none"
    m = _HO_APPLIED.match(body)
    if m is not None:
        return "applied:%d" % sum(int(x) for x in m.groups())
    if body.startswith("повторно не применяю: "):
        return "repeat"
    if body.startswith("НЕ применена: "):
        return "notapplied"
    return "other"


def parse_b(level, msg):
    """Тело строки флагов → {"form": "words"|"notread", "keys", "words", "line"} или {"form": "bad"}."""
    try:
        s = msg.decode("utf-8")
    except UnicodeDecodeError:
        return {"form": "bad"}
    body = s[len(B_HEAD):]
    if level == "WARNING" and _NOTREAD.match(body):
        return {"form": "notread", "keys": (), "words": (), "line": s}
    if level != "INFO":
        return {"form": "bad"}
    keys, words = [], []
    for pair in body.split(" · "):
        k, sep, w = pair.partition("=")
        if not sep or not w:
            return {"form": "bad"}
        keys.append(k)
        words.append(w)
    if tuple(keys) not in (FLAG_KEYS, BASE_KEYS):
        return {"form": "bad"}
    return {"form": "words", "keys": tuple(keys), "words": tuple(words), "line": s}


def parse_c(level, msg):
    """Тело строки входа → {"form": "ok", "state"} | {"form": "park", "verdict", "bad"} | {"form": "bad"}."""
    try:
        body = msg.decode("utf-8")[len(C_HEAD):]
    except UnicodeDecodeError:
        return {"form": "bad"}
    if level == "INFO":
        m = _ENTRY_OK.match(body)
        if m is not None:
            return {"form": "ok", "state": m.group(1)}
    elif level == "ERROR":
        m = _ENTRY_PARK.match(body)
        if m is not None:
            return {"form": "park", "verdict": m.group(1), "bad": tuple(_ENTRY_BAD.findall(body))}
    return {"form": "bad"}


# ============================================ журнал: один проход ===========================================================
def _kind(m, ln):
    name, msg = m.group(9), ln[m.end():]
    if name == _LOGGER_B:
        if msg == _A_B:
            return "a"
        if msg.startswith(_B_B):
            return "b"
        if msg.startswith(_C_B):
            return "c"
        if msg == _D_B:
            return "d"
        if msg == _E_B:
            return "e"
        if msg.startswith(_F_B):
            return "f"
        if msg.startswith(_STOP_B):
            return "stop"
    elif name == _SCHED_B and msg == _SHUT_B:
        return "stop"
    return None


def _utf8_ok(ln):
    try:
        ln.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


class Scanner:
    """Один проход журнала ПОТОКОМ: feed(строка) по мере чтения, result() — факты; строки не хранятся.
    lo_run — старт юнита целыми секундами (метка systemd: граница «текущего запуска» health); w_lo/w_hi — окно записей
    начала [max(⌊EMS точный⌋, EMS), EMS + 300]. Строка — байты без перевода строки (bytes.splitlines, как health._read_log).
    Четыре слоя фактов:
      · общие правила health r6 ПО ВРЕМЕНИ (всё, что после первой записи с меткой ≥ lo_run): метка неизвестной формы
        (в том числе раскладка, которую грамматика записи r6 не принимает), неразобранная метка записи, байты не UTF-8 →
        stamp / utf8; запись раньше уже прочитанной больше чем на 120 с → clock_step; метка неизвестной формы ≥ lo_run до
        запуска → stamp (pend), если её не сняла запись истории — health r7: метка < lo_run − WIN_BACK_S и по месту ДО
        первой записи с меткой ≥ lo_run (in_run);
      · счёт по окну (health r6 verify7 M1) мимо сегмента: записи a и c любого уровня с меткой ≥ lo_run − WIN_BACK_S;
      · «над сегментом»: записи a–f (любого уровня) с меткой ≥ lo_run выше последней записи a → chain_dup;
      · сегмент по месту — от последней записи a уровня INFO до конца: первые вхождения b…f, повторы, порядок, окно,
        остановка, intake (весь сегмент), Traceback (от a до f включительно).
    Факты для ворот CLEAN (build3) пишутся ОТДЕЛЬНЫМИ строками рядом с кодами, а не выводятся из них: cnt — счётчики
    правил запуска (stamp / unparsed / back / utf8), ahead_at / hist_at — номера строк последней метки неизвестной формы с
    датой ≥ lo_run и последней снявшей её записи истории (pend открыт ⇔ ahead_at > hist_at), lines_max — наибольшая длина
    сегмента; потеря строки кода или строки факта по отдельности CLEAN не даёт (тест h8b)."""

    def __init__(self, lo_run, w_lo, w_hi):
        self.lo, self.w_lo, self.w_hi = lo_run, w_lo, w_hi
        self.generic = set()
        self.stamped = False
        self.pend = False
        self.in_run = False                             # r7: запуск начался ПО МЕСТУ (запись с меткой ≥ lo_run)
        self.nl = 0                                     # номер строки прохода
        self.ahead_at = self.hist_at = 0                # факты pend для ворот (независимо от self.pend)
        self.cnt = {"stamp": 0, "unparsed": 0, "back": 0, "utf8": 0}
        self.lines_max = 0
        self.max_cur = None
        self.above = 0
        self.cap = False
        self.cur = self.hi = None
        self.pend_hi = 0
        self.seg = None
        self.win = {"a": 0, "c": 0}
        self.dcache = {}

    def _rec_ts(self, m, ln):
        day = self.dcache.get(ln[:10])
        if day is None:
            day = self.dcache[ln[:10]] = (_epoch(int(m.group(1)), int(m.group(2)), int(m.group(3)), 0, 0, 0),)
        h, mi, s = int(m.group(4)), int(m.group(5)), int(m.group(6))
        if day[0] is None or h > 23 or mi > 59 or s > 59:
            return None
        return day[0] + h * 3600 + mi * 60 + s

    def feed(self, ln):
        self.nl += 1
        m = _REC_B.match(ln)
        ts = kind = None
        if m is None:
            sm = _STAMPISH_B.match(ln)
            if sm is not None:                          # метка неизвестной формы (= health, правило r3/r5/r6)
                self.stamped = True
                if self.cur is not None and self.cur >= self.lo:
                    self.generic.add("stamp")
                    self.cnt["stamp"] += 1
                own = _epoch(*(int(g) for g in sm.groups()))
                if not self.pend and own is not None and own >= self.lo:
                    self.pend = True
                if own is not None and own >= self.lo:
                    self.ahead_at = self.nl
                self._segment(ln, None, None, None)
                return
        else:
            self.stamped = True
            ts = self._rec_ts(m, ln)
            if ts is None and self.cur is not None and self.cur >= self.lo:
                self.generic.add("stamp")
                self.cnt["unparsed"] += 1
            if ts is not None and self.hi is not None and ts < self.hi - BACK_S:
                self.generic.add("clock_step")
                self.cnt["back"] += 1
            # r7 · verify8 K3/K4 (= health рабочей копии 1a8ba76f… :692–696): pend снимает ТОЛЬКО запись истории — метка
            # < старт − 2 с (запись в окне [старт − 2 с, старт) может быть записью текущего запуска, как у счёта по окну)
            # и по месту ДО начала запуска; ниже начала запуска запись с меткой < старта историей не бывает
            if ts is not None and ts < self.lo - WIN_BACK_S and not self.in_run:
                self.pend = False
                self.hist_at = self.nl
        if ts is not None:
            self.cur = ts
        if self.cur is not None and self.cur >= self.lo:
            self.in_run = True
            if ts is not None and (self.hi is None or ts > self.hi):
                self.hi = ts
            if self.max_cur is None or self.cur > self.max_cur:
                self.max_cur = self.cur
            if not _utf8_ok(ln):
                self.generic.add("utf8")
                self.cnt["utf8"] += 1
        if ts is not None:
            kind = _kind(m, ln)
        if kind in self.win and ts >= self.lo - WIN_BACK_S:
            self.win[kind] += 1                         # счёт по окну мимо сегмента (health r6: загрузка и вход)
        if kind == "a" and m.group(8) == b"INFO":
            self.above += self.pend_hi                  # всё, что было выше этой записи a, — над сегментом
            self.pend_hi = 0
            self.seg = {"rec": {}, "dup": False, "order": False, "win_a": True, "win_bf": False, "stop": False,
                        "intake": 0, "tb": 0, "lines": 0, "f_done": False, "last_rank": -1, "last_ts": None,
                        "start": True}
        if kind in _RANK and ts >= self.lo:
            self.pend_hi += 1
        self._segment(ln, m, ts, kind)

    def _segment(self, ln, m, ts, kind):
        seg = self.seg
        if seg is None:
            return
        seg["lines"] += 1
        if seg["lines"] > RUN_LINES_CAP:
            self.cap = True
        if seg["lines"] > self.lines_max:
            self.lines_max = seg["lines"]
        for nd in _INTAKE_B:
            if nd in ln:
                seg["intake"] += 1
        if not seg["f_done"] and ln.startswith(_TB_B):
            seg["tb"] += 1
        if kind == "stop":
            seg["stop"] = True
        elif kind in _RANK:
            tms = ts + int(m.group(7)) / 1000.0
            if seg["start"]:
                seg["start"] = False
                seg["rec"]["a"] = (tms, "INFO", ln[m.end():])
                seg["win_a"] = self.w_lo <= tms <= self.w_hi
                seg["last_rank"], seg["last_ts"] = 0, tms
            elif kind in seg["rec"]:
                seg["dup"] = True
            else:
                if _RANK[kind] <= seg["last_rank"] or tms < seg["last_ts"]:
                    seg["order"] = True
                if not (self.w_lo <= tms <= self.w_hi):
                    seg["win_bf"] = True
                seg["rec"][kind] = (tms, m.group(8).decode("ascii"), ln[m.end():])
                seg["last_rank"] = max(seg["last_rank"], _RANK[kind])
                seg["last_ts"] = max(seg["last_ts"], tms)
            if kind == "f":
                seg["f_done"] = True

    def result(self):
        return {"generic": set(self.generic), "pend": self.pend, "stamped": self.stamped, "max_cur": self.max_cur,
                "above": self.above, "cap": self.cap, "seg": self.seg, "win": dict(self.win), "cnt": dict(self.cnt),
                "ahead_at": self.ahead_at, "hist_at": self.hist_at, "lines_max": self.lines_max}


def scan_lines(lines, lo_run, w_lo, w_hi):
    """Чистый разбор готовых строк (тест, сетка A) — тот же Scanner, что у живого прохода."""
    s = Scanner(lo_run, w_lo, w_hi)
    for ln in lines:
        s.feed(ln)
    return s.result()


def read_log_lines(w, sink):
    """Один ограниченный проход: ровно префикс размера на открытии, кусками; строки → sink(line) по одной.
    → None (прочитан) или код причины: rd_log · log_cap · log_short · log_rot."""
    try:
        fh = w.log_open()
    except Exception:   # noqa: BLE001 — нет файла / нет прав / каталог: «не прочитан», а не «пуст»
        return "rd_log"
    try:
        dev0, ino0, size0, mt0 = w.log_fstat(fh)
        if size0 > LOG_CAP_BYTES:
            return "log_cap"
        got, tail, size, left = 0, [], CHUNK, size0
        while left > 0:
            chunk = fh.read(min(size, left))
            if not chunk:
                break
            got += len(chunk)
            left -= len(chunk)
            cut = chunk.rfind(b"\n") + 1
            if cut:
                tail.append(chunk[:cut])
                for ln in b"".join(tail).splitlines():
                    sink(ln)
                tail = [chunk[cut:]]
                size = CHUNK
            else:
                tail.append(chunk)
                size = min(size * 2, CHUNK_GROW_MAX)
        rest = b"".join(tail)
        if rest:
            for ln in rest.splitlines():
                sink(ln)
        dev1, ino1, size1, mt1 = w.log_fstat(fh)
        pdev, pino = w.log_pstat()
    except Exception:   # noqa: BLE001 — ошибка ввода-вывода посреди прохода
        return "rd_log"
    finally:
        try:
            fh.close()
        except Exception:   # noqa: BLE001
            pass
    if (dev1, ino1) != (dev0, ino0) or (pdev, pino) != (dev0, ino0) or size1 < size0 or (size1 == size0 and mt1 != mt0):
        return "log_rot"
    if got < size0:
        return "log_short"
    return None


def scan_log(w, lo_run, w_lo, w_hi):
    """→ (факты Scanner | None, код сбоя | None). Строки идут в разбор по мере чтения — в памяти один кусок."""
    s = Scanner(lo_run, w_lo, w_hi)
    err = read_log_lines(w, s.feed)
    if err is not None:
        return None, err
    return s.result(), None


# ============================================ чтения ========================================================================
def _show(w, argv, keys):
    try:
        rc, out = w.run(argv, T_CMD_S)
    except Exception:   # noqa: BLE001 — запуск / тайм-аут / белый список: «не прочитано», а не «пусто»
        return None
    return _parse_show(rc, out, keys)


def _boot(w):
    try:
        raw = w.read_small(BOOT_ID)
    except Exception:   # noqa: BLE001
        return None
    m = _BOOT_ID.match(raw)
    return m.group(1).decode("ascii") if m else None


def _birth(w, u, svc):
    """(starttime тиков, cgroup юнита да/нет) главного процесса или None (не прочитано / не по форме)."""
    try:
        st = w.read_small("/proc/%d/stat" % u["pid"])
        cg = w.read_small("/proc/%d/cgroup" % u["pid"])
    except Exception:   # noqa: BLE001
        return None
    i = st.rfind(b")")
    fields = st[i + 1:].split() if i >= 0 else []
    if len(fields) < 20 or not fields[19].isdigit():
        return None
    suffix = ("/" + svc + ".service").encode()
    own = False
    for x in cg.splitlines():
        parts = x.split(b":", 2)
        if len(parts) == 3 and parts[2].rstrip().endswith(suffix):
            own = True
    return (int(fields[19]), own)


def _git(w, argv, timeout=T_CMD_S):
    try:
        rc, out = w.run(argv, timeout)
    except Exception:   # noqa: BLE001
        return None
    if rc != 0 or not isinstance(out, bytes):
        return None
    try:
        return out.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _read_git(w):
    """→ {"head", "dirty", "tree": {имя: блоб}, "work": {имя: блоб}, "mtime": {имя: ⌊с⌋}} или None (любой сбой)."""
    head = _git(w, ARGV_HEAD)
    status = _git(w, ARGV_STATUS)
    tree_txt = _git(w, ARGV_LSTREE)
    if head is None or status is None or tree_txt is None or not re.match(r"^[0-9a-f]{40}\n$", head):
        return None
    tree = {}
    for ln in tree_txt.split("\n"):
        if ln == "":
            continue
        m = re.match(r"^([0-7]{6}) (blob|tree|commit) ([0-9a-f]{40})\t(.+)$", ln)
        if m is None:
            return None
        if m.group(2) == "blob" and m.group(4).endswith(".py"):
            if not _PY_NAME.match(m.group(4)):
                return None
            tree[m.group(4)] = m.group(3)
    names = sorted(tree)
    if not names:
        return None
    hashed = _git(w, ARGV_HASH + tuple(names))
    if hashed is None:
        return None
    hv = hashed.split("\n")
    if hv[-1] == "":
        hv = hv[:-1]
    if len(hv) != len(names) or not all(re.match(r"^[0-9a-f]{40}$", x) for x in hv):
        return None
    mt = {}
    try:
        for n in names:
            mt[n] = int(w.mtime(n))
    except Exception:   # noqa: BLE001
        return None
    return {"head": head.strip(), "dirty": len([x for x in status.split("\n") if x != ""]), "tree": tree,
            "work": dict(zip(names, hv)), "mtime": mt}


def _read_origin(w):
    txt = _git(w, ARGV_ORIGIN, T_ORIGIN_S)
    if txt is None:
        return None
    rows = [x for x in txt.split("\n") if x != ""]
    if len(rows) != 1:
        return None
    m = re.match(r"^([0-9a-f]{40})\trefs/heads/main$", rows[0])
    return m.group(1) if m else None


def _read_cfg(w):
    sp, wa = _show(w, ARGV_CFG_SP, CFG_SP), _show(w, ARGV_CFG_WA, CFG_WA)
    if sp is None or wa is None:
        return None
    for p in (sp, wa):
        if p["NeedDaemonReload"] not in ("yes", "no") or not re.match(r"^[a-z-]{1,32}$", p["LoadState"]):
            return None
    paths = sp["DropInPaths"].split()
    return {"ndr_sp": sp["NeedDaemonReload"], "ndr_wa": wa["NeedDaemonReload"], "load_sp": sp["LoadState"],
            "load_wa": wa["LoadState"], "cnt_b": paths.count(DB), "cnt_u": paths.count(DU),
            "dp": hashlib.sha256(sp["DropInPaths"].encode("utf-8")).hexdigest()[:12]}


def _read_dropin(w, path, pin):
    """→ "absent" | "ok" | "bad" (ссылка / не обычный файл / тело не по пину) или None (сбой чтения)."""
    try:
        st = w.lstat(path)
    except FileNotFoundError:
        return "absent"
    except Exception:   # noqa: BLE001
        return None
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
        return "bad"
    try:
        h = w.hash_file(path)
    except Exception:   # noqa: BLE001
        return None
    return "ok" if h == pin else "bad"


def _pair(w):
    a = w.wall()
    m = w.mono()
    b = w.wall()
    return ((a + b) / 2.0, m)


def _adj(w):
    try:
        x = w.adjtimex()
    except Exception:   # noqa: BLE001 — нет ctypes / нет вызова: часы не прочитаны
        return None
    if not isinstance(x, dict) or not isinstance(x.get("rc"), int) or x["rc"] < 0:
        return None
    return x


def _zone(w):
    """→ (UTC|NOTUTC, link|file|none) или None (не прочитано)."""
    try:
        tz = w.zone()
    except Exception:   # noqa: BLE001
        return None
    try:
        tgt = w.readlink(LOCALTIME)
        src = "link"
    except FileNotFoundError:
        tgt, src = None, "none"
    except OSError as e:
        if e.errno != errno.EINVAL:
            return None
        tgt, src = None, "file"
    except Exception:   # noqa: BLE001
        return None
    zero = tuple(tz) == (0, 0, 0)
    if src == "link" and not _UTC_LINK.search(tgt):
        return ("NOTUTC", src)
    return ("UTC" if zero else "NOTUTC", src)


def read_current(w, a):
    """Все чтения в порядке READER_SPEC §5 → факты (только данные, без суждений)."""
    f = {}
    f["t0"] = _pair(w)
    f["sp0"] = _ident(_show(w, ARGV_SHOW_SP, ID_PROPS))
    f["wa0"] = _ident(_show(w, ARGV_SHOW_WA, ID_PROPS))
    f["boot0"] = _boot(w)
    run0 = f["sp0"] is not None and f["sp0"]["pid"] > 0
    f["birth0"] = _birth(w, f["sp0"], UNIT) if run0 else None
    f["wbirth0"] = _birth(w, f["wa0"], WA) if (f["wa0"] is not None and f["wa0"]["pid"] > 0) else None
    f["adj0"] = _adj(w)
    f["zone"] = _zone(w)
    f["git"] = _read_git(w)
    f["origin"] = _read_origin(w)
    f["sp1"] = _ident(_show(w, ARGV_SHOW_SP, ID_PROPS))
    f["scan"], f["log_err"] = None, None
    u = f["sp0"]
    if u is not None and u == f["sp1"] and u["act"] == "active" and u["sub"] == "running" and u["ems"] >= 0:
        ems_precise = f["t0"][0] - (f["t0"][1] - u["emsm"] / 1e6)
        f["ems_precise"] = ems_precise
        f["scan"], f["log_err"] = scan_log(w, u["ems"], max(int(ems_precise // 1), u["ems"]), u["ems"] + START_SKEW_S)
    f["cfg"] = _read_cfg(w)
    f["d_b"], f["d_u"] = _read_dropin(w, DB, a["--db-sha"]), _read_dropin(w, DU, a["--du-sha"])
    f["birth1"] = _birth(w, f["sp0"], UNIT) if run0 else None
    f["wbirth1"] = _birth(w, f["wa0"], WA) if (f["wa0"] is not None and f["wa0"]["pid"] > 0) else None
    f["adj1"] = _adj(w)
    f["sp2"] = _ident(_show(w, ARGV_SHOW_SP, ID_PROPS))
    f["wa2"] = _ident(_show(w, ARGV_SHOW_WA, ID_PROPS))
    f["boot2"] = _boot(w)
    f["t2"] = _pair(w)
    try:
        f["tck"] = int(w.clk_tck())
    except Exception:   # noqa: BLE001
        f["tck"] = None
    return f


# ============================================ суждение (чистое) =============================================================
def derive_chain(sc, state, age):
    """Факты прохода → поля цепочки и коды (READER_SPEC §8 п.1–9). Чистая. Сегмент не доказан своим (посылка окна, двойник,
    порядок, остановка, неоднозначность окна) — proc «?»: класс по чужой или нарушенной цепочке не выносится."""
    d = _derive_chain(sc, state, age)
    if d["codes"] & {"premise", "win_many", "chain_dup", "chain_order", "stop_line"}:
        d["proc"] = "?"
    return d


def _derive_chain(sc, state, age):
    d = {"gen": "?", "proc": "?", "entry": "?", "ebad": "-", "flags": "?", "ho": "?", "tb": None, "intake": None,
         "fv": True, "codes": set()}
    codes = d["codes"]
    codes |= sc["generic"]
    if sc["pend"]:
        codes.add("stamp")
    if sc["cap"]:
        codes.add("log_cap")
    if sc["win"]["a"] > 1 or sc["win"]["c"] > 1:
        codes.add("win_many")
    seg = sc["seg"]
    if seg is None:
        codes.add("premise")
        return d
    d["tb"], d["intake"] = seg["tb"], seg["intake"]
    if not seg["win_a"]:
        codes.add("premise")
    if sc["above"] > 0 or seg["dup"]:
        codes.add("chain_dup")
    if seg["order"] or seg["win_bf"]:
        codes.add("chain_order")
    if seg["stop"]:
        codes.add("stop_line")
    rec = seg["rec"]
    b = parse_b(rec["b"][1], rec["b"][2]) if "b" in rec else None
    c = parse_c(rec["c"][1], rec["c"][2]) if "c" in rec else None
    for k in ("d", "e", "f"):
        if k in rec and rec[k][1] != "INFO":
            codes.add("chain_partial")
    if b is None:
        d["flags"] = "NONE"
    elif b["form"] == "bad":
        codes.add("flags_grammar")
    elif b["form"] == "notread":
        d["flags"] = "NOTREAD"
    else:
        d["flags"] = ".".join(_token(x) for x in b["words"])
    if b is not None and b["form"] != "bad":
        tmpl = BASE_FLAGS_RE if state == "base" else FLAGS_RE[state]
        d["fv"] = re.search(tmpl, b["line"]) is None
    if c is None:
        d["entry"] = "NONE"
    elif c["form"] == "bad":
        codes.add("entry_grammar")
    elif c["form"] == "ok":
        d["entry"] = c["state"]
    else:
        d["entry"] = c["verdict"]
        bad = ["%s.%s" % (KEY_ABBR[k], v[0]) for k, v in c["bad"]]
        d["ebad"] = ",".join(bad) if bad else "-"
    if "f" in rec:
        try:
            d["ho"] = _ho(rec["f"][2].decode("utf-8")[len(F_HEAD):])
        except UnicodeDecodeError:
            d["ho"] = "other"
    else:
        d["ho"] = "NONE"
    words = b is not None and b["form"] == "words"
    if c is not None or (words and len(b["keys"]) == 5):
        d["gen"] = "cand"
    elif words and len(b["keys"]) == 2:
        d["gen"] = "base"
    elif b is not None and b["form"] == "notread" and "d" in rec:
        d["gen"] = "base"
    if c is not None and c["form"] != "bad" and words and len(b["keys"]) != 5:
        codes.add("flags_entry")
    if c is not None and c["form"] == "ok" and b is not None and b["form"] != "bad":
        allowed = dict(ENTRY_STATES)[c["state"]]
        if not words or len(b["words"]) != 5 or any(x not in allowed[i] for i, x in enumerate(b["words"])):
            codes.add("flags_entry")
    young = age < START_SKEW_S
    if c is not None and c["form"] == "park":
        if "d" in rec or "e" in rec or "f" in rec or seg["intake"] > 0:
            codes.add("park_contra")
        elif b is None:
            codes.add("chain_partial")
        else:
            d["proc"] = "PARKED"
        return d
    if c is not None and c["form"] == "bad":
        return d
    if d["gen"] == "?":
        codes.add("young" if young else "chain_partial")
        return d
    need_c = d["gen"] == "cand"
    full = (b is not None and ("c" in rec) == need_c and all(k in rec for k in ("d", "e", "f")))
    nopoll = (b is not None and "e" not in rec and "f" not in rec and not (need_c and c is None and "d" in rec))
    if full:
        if young:
            codes.add("young")
        else:
            d["proc"] = "POLLING"
    elif nopoll:
        if young:
            codes.add("young")
        else:
            d["proc"] = "NOPOLL"
    else:
        codes.add("young" if young else "chain_partial")
    return d


def _unit_kind(us):
    """Три чтения юнита → "run" | "down" | "transient"."""
    if all(u["act"] == "active" and u["sub"] == "running" for u in us):
        return "run"
    if all(u["act"] in ("inactive", "failed") and u["pid"] == 0 for u in us):
        return "down"
    return "transient"


_L_CLEAN = {"release": (frozenset(), frozenset("bu")), "truth_off": (frozenset("b"),)}


def _clean_proven(P):
    """Положительная таблица CLEAN по ФАКТАМ чтений P, а не по отсутствию кодов (build3, MAJOR-1 линзы code круга 2) →
    список НЕвыполненных условий (пусто — все выполнены явно). Чистая. Условия: строки READER_SPEC §9.3 и её общие условия
    («личность перечитана», ho, tb, часы, пояс, ndr) и условия §5/§6/§8, которые прежде держали только коды. Зовётся, когда
    кодов нет: любое невыполненное условие — потеря кода, класс — UNKNOWN clean_gate, а не CLEAN."""
    st = P["state"]
    ho = P["ho"]
    sp, boot, wa, bi = P["sp"], P["boot"], P["wa_id"], P["birth"]
    u = sp[2]
    t0, t2 = P["t0"], P["t2"]
    sc = P["scan"]
    seg = sc["seg"] if sc is not None else None
    rec = seg["rec"] if seg is not None else {}
    k = _split_key(P["prev_run"]) if P["prev_run"] is not None else None
    # «личность перечитана» (§5, общее условие §9.3): все чтения есть и совпали — S0 = S1 = S2, boot0 = boot2,
    # birth0 = birth1, wa-agent S0 = S2
    ident = (None not in sp and sp[0] == sp[1] == sp[2] and None not in boot and boot[0] == boot[1]
             and None not in wa and wa[0] == wa[1] and None not in bi and bi[0] == bi[1])
    run = (ident and all(x["act"] == "active" and x["sub"] == "running" for x in sp) and u["inv"] != ""
           and P["key"] is not None)
    conds = (
        ("ident", ident),
        ("run", run),
        ("birth", run and bool(P["tck"]) and abs(bi[0][0] / float(P["tck"]) - u["emsm"] / 1e6) <= BIRTH_TOL_S
         and bi[0][1] and bi[1][1] and abs(u["aem"] - u["emsm"]) / 1e6 <= AE_TOL_S),
        ("expect", (P["expect_run"] is None or P["key"] == P["expect_run"])
         and (P["expect_wa"] is None or P["wa_key"] == P["expect_wa"])
         and (k is None or (u is not None and boot[1] == k["boot"] and u["pid"] != k["pid"] and u["emsm"] > k["emsm"]
                            and u["nr"] == 0))),
        ("clock", P["clock"] == "SYNC" and P["tz"] == "UTC"),
        ("time", t0[0] >= P["nb"] and t2[0] >= t0[0] and abs((t2[0] - t2[1]) - (t0[0] - t0[1])) <= OFFSET_DRIFT_S
         and u is not None and P["ems_dd"] is not None and -EMS_EPS_S <= P["ems_dd"] < EMS_STEP_S
         and u["ems"] <= t2[0] + AHEAD_S and (sc is None or sc["max_cur"] is None or sc["max_cur"] <= t2[0] + AHEAD_S)),
        ("log", P["log_err"] is None and sc is not None and not any(sc["cnt"].values())
         and sc["ahead_at"] <= sc["hist_at"] and sc["lines_max"] <= RUN_LINES_CAP
         and sc["win"]["a"] <= 1 and sc["win"]["c"] <= 1),
        ("chain", P["chain"] and seg is not None and seg["win_a"] and sc["above"] == 0 and not seg["dup"]
         and not seg["order"] and not seg["win_bf"] and not seg["stop"] and "b" in rec
         and all(x in rec and rec[x][1] == "INFO" for x in ("d", "e", "f"))),
        ("proc", P["proc"] == "POLLING"),
        ("gen", P["gen"] == ("base" if st == "base" else "cand")),
        ("entry", P["entry"] == ("NONE" if st == "base" else st)),
        ("flags", P["fv"] is False),
        ("ho", ho in ("none", "repeat") or (ho.startswith("applied:") and ho[8:].isdigit())),
        ("tb", P["tb"] == 0),
        ("age", P["age"] is not None and P["age"] >= START_SKEW_S),
        ("git", P["head"] == P["sha"] and P["origin"] == P["sha"] and P["dirty"] == 0),
        ("code", P["nblob"] == 0 and P["nnew"] == 0),
        ("base_blob", st != "base" or P["base_blob"] is True),
        ("wa", P["wa"] == "ok" and P["wa_key"] != "?"),
        ("ndr", P["ndr"] == ("no", "no")),
        ("dropin", P["dropin"] == "OK" and P["lset"] is not None and P["lset"] == P["dset"]
         and (st not in _L_CLEAN or P["lset"] in _L_CLEAN[st])),
    )
    return [name for name, ok in conds if not ok]


def judge(f, a):
    """Факты + аргументы → вердикт: {"class", "why", "guard", поля квитанции}. Чистая (READER_SPEC §5–§9, §11)."""
    v = {"fields": {}}
    codes = set()
    F = v["fields"]
    state = a["--state"]
    want_gen = "base" if state == "base" else "cand"
    sp = (f["sp0"], f["sp1"], f["sp2"])
    wa = (f["wa0"], f["wa2"])
    boot = (f["boot0"], f["boot2"])
    t0, t2 = f["t0"], f["t2"]
    if any(x is None for x in sp):
        codes.add("rd_unit")
    if any(x is None for x in wa):
        codes.add("rd_wa")
    if any(x is None for x in boot):
        codes.add("rd_boot")
    if all(x is not None for x in boot) and boot[0] != boot[1]:
        codes.add("boot_changed")
    if all(x is not None for x in wa) and wa[0] != wa[1]:
        codes.add("wa_ident")
    kind = None
    u = f["sp2"]
    if all(x is not None for x in sp):
        if not (sp[0] == sp[1] == sp[2]):
            codes.add("ident_changed")
        kind = _unit_kind(sp)
        if kind == "transient":
            codes.add("unit_transient")
        if kind == "run" and u["inv"] == "":
            codes.add("rd_unit")
    key = run_key(boot[1], u) if (u is not None and boot[1] is not None) else None
    w2 = f["wa2"]
    wkey = run_key(boot[1], w2) if (w2 is not None and boot[1] is not None) else None
    F["run"] = key or "?"
    F["unit"] = ((u["act"] if u["act"] in ACTIVE_STATES else "x") + "/" + (u["sub"] if u["sub"] in SUB_STATES else "x")) \
        if u is not None else "?/?"
    F["ems"] = str(u["ems"]) if (u is not None and u["ems"] >= 0) else "?"
    F["ae"] = str(u["ae"]) if (u is not None and u["ae"] >= 0) else "?"
    run = kind == "run" and "ident_changed" not in codes
    # --- рождение, AE/EMS, ключи ожидания
    F["birth"] = "?"
    if run:
        b0, b1, tck = f["birth0"], f["birth1"], f["tck"]
        if b0 is None or b1 is None or not tck:
            codes.add("rd_proc")
        else:
            if b0 != b1:
                codes.add("ident_changed")
            delta = b0[0] / float(tck) - u["emsm"] / 1e6
            F["birth"] = "%+d" % int(round(delta * 1000))
            if abs(delta) > BIRTH_TOL_S:
                codes.add("birth")
            if not (b0[1] and b1[1]):
                codes.add("cgroup")
        if abs(u["aem"] - u["emsm"]) / 1e6 > AE_TOL_S:
            codes.add("ae_ems")
    if a.get("--expect-run") is not None and key != a["--expect-run"]:
        codes.add("expect_run")
    if a.get("--expect-wa") is not None and wkey != a["--expect-wa"]:
        codes.add("expect_wa")
    if a.get("--prev-run") is not None:
        k = _split_key(a["--prev-run"])
        if not (u is not None and boot[1] == k["boot"] and u["pid"] != k["pid"] and u["emsm"] > k["emsm"]
                and u["nr"] == 0):
            codes.add("prev_run")
    # --- часы и пояс
    adj = (f["adj0"], f["adj1"])
    if any(x is None for x in adj):
        codes.add("clock_rd")
        F["clock"], F["maxerr"] = "?", "?"
    else:
        mx = max(x["maxerror"] for x in adj)
        F["maxerr"] = str(max(mx, 0) // 1000)
        F["clock"] = "SYNC" if mx < MAXERR_US else "UNSYNC"
        if mx >= MAXERR_US:
            codes.add("clock_unsync")
    if t0[0] < int(a["--not-before"]):
        codes.add("clock_past")
    if t2[0] < t0[0] or abs((t2[0] - t2[1]) - (t0[0] - t0[1])) > OFFSET_DRIFT_S:
        codes.add("clock_step")
    if run:
        dd = f.get("ems_precise", t0[0] - (t0[1] - u["emsm"] / 1e6)) - u["ems"]
        if not (-EMS_EPS_S <= dd < EMS_STEP_S):
            codes.add("clock_step")
        if u["ems"] > t2[0] + AHEAD_S:
            codes.add("clock_ahead")
    z = f["zone"]
    F["tz"], F["tzsrc"] = (z[0], z[1]) if z is not None else ("?", "?")
    if z is None or z[0] != "UTC":
        codes.add("zone")
    # --- журнал и цепочка
    ch = None
    age = (t0[0] - u["ems"]) if (u is not None and u["ems"] >= 0) else None
    F["age"] = str(int(age // 1)) if age is not None else "?"
    if run:
        if f["log_err"] is not None:
            codes.add(f["log_err"])
        elif f["scan"] is not None:
            ch = derive_chain(f["scan"], state, age)
            codes |= ch["codes"]
            if f["scan"]["max_cur"] is not None and f["scan"]["max_cur"] > t2[0] + AHEAD_S:
                codes.add("clock_ahead")
        else:
            codes.add("rd_log")
    for k in ("gen", "proc", "entry", "ebad", "flags", "ho"):
        F[k] = ch[k] if ch is not None else ("-" if k == "ebad" else "?")
    F["tb"] = str(ch["tb"]) if (ch is not None and ch["tb"] is not None) else "?"
    F["intake"] = str(ch["intake"]) if (ch is not None and ch["intake"] is not None) else "?"
    if kind == "down" and "ident_changed" not in codes:
        F["proc"] = "DOWN"
        codes.add("down")
    proc = F["proc"]
    if proc == "PARKED":
        codes.add("park")
    if proc == "NOPOLL":
        codes.add("nopoll")
    # --- код и git
    g, origin, sha = f["git"], f["origin"], a["--sha"]
    F["head"] = g["head"][:12] if g else "?"
    F["origin"] = origin[:12] if origin else "?"
    F["dirty"] = str(g["dirty"]) if g else "?"
    nblob = nnew = wnew = None
    base_ok = None
    if g is None:
        codes.add("rd_git")
        F["code"], F["code_k"], F["code_n"] = "?", "?", "?"
    else:
        n = len(g["tree"])
        nblob = len([x for x in g["tree"] if g["work"].get(x) != g["tree"][x]])
        if g["head"] != sha:
            codes.add("head")
        if origin is not None and origin != sha:
            codes.add("origin")
        if g["dirty"] > 0:
            codes.add("dirty")
        if nblob:
            codes.add("blob")
        base_ok = g["tree"].get("bot.py") == BASE_BOT_BLOB and g["tree"].get("splinter.py") == BASE_SPL_BLOB
        if state == "base" and not base_ok:
            codes.add("base_blob")
        if u is not None and u["ems"] >= 0 and kind == "run":
            nnew = len([x for x in g["mtime"] if g["mtime"][x] > u["ems"]])
            if nnew:
                codes.add("code_newer")
        if nblob:
            F["code"], F["code_k"] = "BLOB", str(nblob)
        elif nnew:
            F["code"], F["code_k"] = "NEWER", str(nnew)
        elif nnew is None:
            F["code"], F["code_k"] = "?", "?"
        else:
            F["code"], F["code_k"] = "OK", "0"
        F["code_n"] = str(n)
    # --- wa-agent: любое неполное чтение — код (READER_SPEC §9.2 «не прочитал → не нет»; build2 M1 линзы атаки)
    F["wa_key"] = wkey or "?"
    F["wa"] = "?"
    if w2 is not None and "wa_ident" not in codes and "rd_wa" not in codes:
        if not all(x["act"] == "active" and x["sub"] == "running" for x in wa):
            codes.add("wa_down")
            F["wa"] = "down"
        else:
            wb0, wb1, tck = f["wbirth0"], f["wbirth1"], f["tck"]
            if wb0 is None or wb1 is None or wb0 != wb1 or not tck or not (wb0[1] and wb1[1]) \
                    or w2["inv"] == "" or abs(wb0[0] / float(tck) - w2["emsm"] / 1e6) > BIRTH_TOL_S:
                codes.add("wa_ident")
            elif w2["ems"] < 0:
                codes.add("wa_ident")          # метка старта wa не прочитана (пусто / n/a): mtime не с чем сравнить
            elif g is not None:
                wnew = len([x for x in g["mtime"] if g["mtime"][x] > w2["ems"]])
                if wnew:
                    codes.add("wa_newer")
                F["wa"] = "newer" if wnew else "ok"
            # g is None: код rd_git уже стоит, поле wa — «?»
    # --- конфигурация и свои drop-in (READER_SPEC §9.1)
    cfg, db, du = f["cfg"], f["d_b"], f["d_u"]
    F["dl"] = F["dd"] = "??"
    F["dropin"], F["ndr_sp"], F["ndr_wa"] = "?", "?", "?"
    F["dpaths"] = cfg["dp"] if cfg is not None else "?"
    lset = dset = None
    if cfg is None:
        codes.add("rd_cfg")
    else:
        F["ndr_sp"] = "yes" if (cfg["ndr_sp"] == "yes" or cfg["load_sp"] != "loaded") else "no"
        F["ndr_wa"] = "yes" if (cfg["ndr_wa"] == "yes" or cfg["load_wa"] != "loaded") else "no"
        if "yes" in (F["ndr_sp"], F["ndr_wa"]):
            codes.add("ndr")
        lset = frozenset(x for x, c in (("b", cfg["cnt_b"]), ("u", cfg["cnt_u"])) if c >= 1)
        F["dl"] = ("b" if "b" in lset else "-") + ("u" if "u" in lset else "-")
    if db is None or du is None:
        codes.add("rd_dropin")
    else:
        dset = frozenset(x for x, s in (("b", db), ("u", du)) if s != "absent")
        F["dd"] = ("b" if "b" in dset else "-") + ("u" if "u" in dset else "-")
    if lset is not None and dset is not None:
        bad = (cfg["cnt_b"] > 1 or cfg["cnt_u"] > 1 or "bad" in (db, du) or lset == frozenset("u")
               or dset == frozenset("u"))
        nxt = "truth_off" if lset == frozenset("b") else "release"
        armed = (lset != dset or cfg["ndr_sp"] == "yes"
                 or (F["gen"] == "cand" and proc == "POLLING" and F["entry"] == "release" and nxt != "release"))
        if bad:
            codes.add("dropin_bad")
            F["dropin"] = "BAD"
        elif armed:
            codes.add("dropin_armed")
            F["dropin"] = "ARMED"
        else:
            F["dropin"] = "OK"
    # --- коды цепочки для идущего процесса (у простоя слово флагов и вход — причина простоя, а не расхождение)
    if ch is not None and proc in ("POLLING", "NOPOLL"):
        if F["gen"] != want_gen:
            codes.add("gen")
            if g is not None and "code_newer" not in codes:
                codes.add("gen_contra")        # код на диске не новее процесса, а поколение цепочки — чужое (шапка)
        if F["gen"] == "cand" and state != "base" and F["entry"] in ("release", "truth_off") and F["entry"] != state:
            codes.add("state")
        if F["entry"] == "truth_off" and lset is not None and lset != frozenset("b"):
            codes.add("state_src")
        if ch["fv"]:
            codes.add("fv")
        if F["ho"] in ("notapplied", "other"):
            codes.add("handoff")
        if ch["tb"]:
            codes.add("tb_start")
    # факты для положительных ворот CLEAN (build3): сырые чтения и аргументы, а не коды
    v["proof"] = P = {"state": state, "sha": sha, "sp": sp, "boot": boot, "wa_id": wa,
                      "birth": (f["birth0"], f["birth1"]), "tck": f["tck"], "key": key,
                      "expect_run": a.get("--expect-run"), "expect_wa": a.get("--expect-wa"),
                      "prev_run": a.get("--prev-run"), "t0": t0, "t2": t2, "nb": int(a["--not-before"]),
                      "ems_dd": ((f.get("ems_precise", t0[0] - (t0[1] - u["emsm"] / 1e6)) - u["ems"])
                                 if u is not None else None),
                      "scan": f["scan"], "log_err": f["log_err"], "chain": ch is not None,
                      "clock": F["clock"], "tz": F["tz"], "proc": F["proc"], "gen": F["gen"], "entry": F["entry"],
                      "fv": ch["fv"] if ch is not None else None, "ho": F["ho"],
                      "tb": ch["tb"] if ch is not None else None, "age": age,
                      "head": g["head"] if g else None, "origin": origin, "dirty": g["dirty"] if g else None,
                      "nblob": nblob, "nnew": nnew, "base_blob": base_ok, "wa": F["wa"], "wa_key": F["wa_key"],
                      "ndr": (F["ndr_sp"], F["ndr_wa"]), "dropin": F["dropin"], "lset": lset, "dset": dset}
    why = [c for c in ORDER if c in codes]
    if not why and origin is None:
        why = ["rd_origin"]                 # origin не прочитан блокирует ТОЛЬКО CLEAN; прочие классы он не меняет
    if not why and _clean_proven(P):
        why = ["clean_gate"]                # кодов нет, а условие §9.3 не доказано: потерян код — UNKNOWN, а не CLEAN
    v["class"] = CLASS_OF[why[0]] if why else "CLEAN"
    v["why"] = why or ["ok"]
    v["guard"] = "-"
    if a.get("--guard") == "unpark":
        gw = []
        if not (v["class"] == "PARKED" and F["gen"] == "cand"):
            gw.append("guard_park")
        if key is None or key != a.get("--expect-run"):
            gw.append("guard_run")
        if g is None or g["head"] != sha or g["dirty"] != 0 or nblob or "base_blob" in codes:
            gw.append("guard_code")
        if cfg is None or F["ndr_sp"] != "no" or F["ndr_wa"] != "no":
            gw.append("guard_ndr")
        if lset is None or dset is None or lset != dset or F["dropin"] == "BAD" or F["dropin"] == "?":
            gw.append("guard_dropin")
        if F["wa"] != "ok" or F["wa_key"] != a.get("--expect-wa"):
            gw.append("guard_wa")
        if F["clock"] != "SYNC":
            gw.append("guard_clock")
        v["guard"] = "REFUSED" if gw else "PASS"
        v["why"] = v["why"] + gw
    return v


def exit_code(v):
    if v["guard"] == "PASS":
        return 0
    if v["guard"] == "REFUSED":
        return RC_REFUSED
    return CODE[v["class"]]


def render(v, a):
    F = v["fields"]
    parts = ["ENTRY_READ r1", "class=" + v["class"], "want=%s@%s" % (a["--state"], a["--sha"]), "label=" + a["--label"],
             "run=" + F.get("run", "?"), "unit=" + F.get("unit", "?/?"), "ems=" + F.get("ems", "?"), "ae=" + F.get("ae", "?"),
             "birth=" + F.get("birth", "?"), "age=" + F.get("age", "?"),
             "clock=%s:%s" % (F.get("clock", "?"), F.get("maxerr", "?")), "tz=%s:%s" % (F.get("tz", "?"), F.get("tzsrc", "?")),
             "git=%s/%s/%s" % (F.get("head", "?"), F.get("origin", "?"), F.get("dirty", "?")),
             "code=%s:%s/%s" % (F.get("code", "?"), F.get("code_k", "?"), F.get("code_n", "?")),
             "gen=" + F.get("gen", "?"), "proc=" + F.get("proc", "?"), "entry=" + F.get("entry", "?"),
             "ebad=" + F.get("ebad", "-"), "flags=" + F.get("flags", "?"), "ho=" + F.get("ho", "?"),
             "tb=" + F.get("tb", "?"), "intake=" + F.get("intake", "?"),
             "dropin=%s:%s/%s" % (F.get("dropin", "?"), F.get("dl", "??"), F.get("dd", "??")),
             "dpaths=" + F.get("dpaths", "?"), "ndr=%s/%s" % (F.get("ndr_sp", "?"), F.get("ndr_wa", "?")),
             "wa=%s:%s" % (F.get("wa", "?"), F.get("wa_key", "?")), "guard=" + v["guard"], "why=" + ",".join(v["why"])]
    return " ".join(parts)


def internal_verdict(a):
    v = {"class": "UNKNOWN", "why": ["internal"], "guard": "-", "fields": {}}
    if a.get("--guard") == "unpark":
        v["guard"] = "REFUSED"
        v["why"] = ["internal", "guard_park"]
    return v


# ============================================ аргументы ======================================================================
def parse_args(argv):
    """Закрытый набор (READER_SPEC §3 + r2 п.5 + build2). Ошибка → Usage(<класс>)."""
    a, i = {}, 0
    argv = list(argv)
    if not argv:
        raise Usage("no_args")
    while i < len(argv):
        k = argv[i]
        if k in _FLAGS:
            if k in a:
                raise Usage("repeat")
            a[k] = True
            i += 1
            continue
        if k not in _ARG_FORM:
            raise Usage("unknown")
        if k in a:
            raise Usage("repeat")
        if i + 1 >= len(argv):
            raise Usage("missing_value")
        val = argv[i + 1]
        if not isinstance(val, str) or not _ARG_FORM[k].fullmatch(val):
            raise Usage("form_" + k[2:].replace("-", "_"))
        a[k] = val
        i += 2
    if a.get("--recheck"):
        for k in _RECHECK_REQ:
            if k not in a:
                raise Usage("missing_" + k[2:].replace("-", "_"))
        for k in a:
            if k not in _RECHECK_REQ and k != "--recheck":
                raise Usage("recheck_extra")
        return a
    for k in _NORMAL_REQ:
        if k not in a:
            raise Usage("missing_" + k[2:].replace("-", "_"))
    if "--against" in a:
        raise Usage("against_without_recheck")
    if "--guard" in a:
        if "--expect-run" not in a:
            raise Usage("guard_needs_expect_run")
        if "--expect-wa" not in a:
            raise Usage("guard_needs_expect_wa")
        if a["--state"] != "base":
            raise Usage("guard_needs_base")
        if "--prev-run" in a:
            raise Usage("guard_with_prev_run")
    return a


# ============================================ повторная сверка перед эффектом (r2 п.5) ======================================
def parse_receipt(line):
    m = RECEIPT_RE.fullmatch(line) if isinstance(line, str) and len(line) <= RECEIPT_MAX else None
    return dict(zip(RECEIPT_FIELDS, m.groups())) if m else None


def recheck(w, a):
    """Быстрая повторная сверка в том же ssh сразу перед systemctl restart: без журнала и без сети, только systemctl show,
    boot_id и git по R. → None (всё совпало) или имя поля дрейфа/неполноты. Поля (r2 п.5): полная K0 (boot_id,
    InvocationID, MainPID, EMSmono, NRestarts), полный KWA1, HEAD = RB, чистые index и worktree, NDR и LoadState обеих
    служб, набор и тела своих drop-in и отпечаток DropInPaths; в конце — повторное чтение splinter, wa-agent и boot_id.
    Атомарной связка read→restart не называется: окно между этой сверкой и рестартом (доли секунды) — предел."""
    r = parse_receipt(a["--against"])
    if (r is None or r["class"] != "PARKED" or r["guard"] != "PASS" or r["want_state"] != "base"
            or r["want_sha"] != a["--sha"] or r["label"] != a["--label"] or r["run"] != a["--expect-run"]
            or r["wa"] != "ok" or r["wa_key"] != a["--expect-wa"] or r["dropin"] != "OK"
            or r["dl"] != r["dd"] or "?" in r["dl"] or r["dpaths"] == "?" or (r["ndr_sp"], r["ndr_wa"]) != ("no", "no")
            or r["head"] != a["--sha"][:12] or r["dirty"] != "0"):
        return "against"
    sp, boot = _ident(_show(w, ARGV_SHOW_SP, ID_PROPS)), _boot(w)
    if sp is None:
        return "rd_unit"
    if boot is None:
        return "rd_boot"
    if sp["act"] != "active" or sp["sub"] != "running" or run_key(boot, sp) != a["--expect-run"]:
        return "run"
    wa = _ident(_show(w, ARGV_SHOW_WA, ID_PROPS))
    if wa is None:
        return "rd_wa"
    if wa["act"] != "active" or wa["sub"] != "running" or run_key(boot, wa) != a["--expect-wa"]:
        return "wa"
    head, status = _git(w, ARGV_HEAD), _git(w, ARGV_STATUS)
    if head is None or status is None:
        return "rd_git"
    if head.strip() != a["--sha"]:
        return "head"
    if [x for x in status.split("\n") if x != ""]:
        return "dirty"
    cfg = _read_cfg(w)
    if cfg is None:
        return "rd_cfg"
    if (cfg["ndr_sp"], cfg["ndr_wa"], cfg["load_sp"], cfg["load_wa"]) != ("no", "no", "loaded", "loaded"):
        return "ndr"
    db, du = _read_dropin(w, DB, a["--db-sha"]), _read_dropin(w, DU, a["--du-sha"])
    if db is None or du is None:
        return "rd_dropin"
    live_l = ("b" if cfg["cnt_b"] == 1 else ("?" if cfg["cnt_b"] else "-")) + \
        ("u" if cfg["cnt_u"] == 1 else ("?" if cfg["cnt_u"] else "-"))
    live_d = ("b" if db == "ok" else ("?" if db == "bad" else "-")) + ("u" if du == "ok" else ("?" if du == "bad" else "-"))
    if live_l != r["dl"] or live_d != r["dd"] or cfg["dp"] != r["dpaths"]:
        return "dropin"
    sp2, wa2, boot2 = _ident(_show(w, ARGV_SHOW_SP, ID_PROPS)), _ident(_show(w, ARGV_SHOW_WA, ID_PROPS)), _boot(w)
    if sp2 is None:
        return "rd_unit"
    if boot2 is None:
        return "rd_boot"
    if sp2 != sp or boot2 != boot:
        return "run"
    if wa2 is None:
        return "rd_wa"
    if wa2 != wa:
        return "wa"
    return None


def run_recheck(w, a, out):
    """Режим --recheck: одна строка — ENTRY_RECHECK r1 PASS … (0) или UNPARK_END refused recheck=<поле> (63)."""
    try:
        field = recheck(w, a)
    except Exception:   # noqa: BLE001 — сбой самой сверки: отказ, а не «совпало»
        field = "internal"
    if field is not None:
        out.write("UNPARK_END refused recheck=%s\n" % field)
        out.flush()
        return RC_RECHECK
    r = parse_receipt(a["--against"])
    out.write("ENTRY_RECHECK r1 PASS label=%s run=%s wa=%s head=%s dropin=%s/%s ndr=no/no\n"
              % (a["--label"], a["--expect-run"], a["--expect-wa"], a["--sha"], r["dl"], r["dd"]))
    out.flush()
    return 0


# ============================================ точка входа ====================================================================
def main(argv=None, world=None, out=None):
    out = sys.stdout if out is None else out
    try:
        a = parse_args(sys.argv[1:] if argv is None else argv)
    except Usage as e:
        out.write("ENTRY_READ_USAGE %s\n" % e.args[0])
        out.flush()
        return RC_USAGE
    w = World() if world is None else world
    if a.get("--recheck"):
        return run_recheck(w, a, out)
    try:
        v = judge(read_current(w, a), a)
        line = render(v, a)
        if len(line) > RECEIPT_MAX or not RECEIPT_RE.fullmatch(line):
            raise ValueError("квитанция вне грамматики")
    except Exception:   # noqa: BLE001 — любое исключение: UNKNOWN internal, а не падение без квитанции
        v = internal_verdict(a)
        line = render(v, a)
    out.write(line + "\n")
    out.flush()
    return exit_code(v)


if __name__ == "__main__":
    sys.exit(main())
