#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ПРИЁМКА ВЫПУСКА CONTRACTREF1510 поверх прода 556e744 (CASESTATE включён флагом WA_AGENT_CONTRACT_STATE=1).
Чёрный ящик по проекту DESIGN_CONTRACTREF1510.md, написан НЕЗАВИСИМО от реализации (её каталог не открывался).

ЦЕЛЬ КЛИЕНТА: агент находит ИМЕННО его актуальный договор и полезно продолжает просьбу; договор, сделанный ФОРМОЙ, не
теряется на пути make_contract(name+date) → no_passport. Здесь проверяется поведение:
  · правильная версия выбирается: последовательность одного дела 34 ПОДПИСАН → 34 ОТОЗВАН + 36 НОВЫЙ → 36 ОТПРАВЛЕН →
    36 ПОДПИСАН — и в чистой функции, и в живом проходе подписи (снимок, блок модели, PDF);
  · чужое и неоднозначное не выбирается: чужой телефон, байк, день, совпадение 9 цифр при другом коде страны, два
    подписанных, ник другого номера; день неизвестен — incomplete;
  · отказ / таймаут / card_deadline чтения реестра — «неизвестно», а не «договора нет»;
  · переподпись того же doc_id с новыми signed_at / pdf_id — новая версия;
  · старая версия не попадает ни в PDF клиенту, ни в блок CASESTATE как текущая;
  · ответ модели сохраняется: текст уходит, даже если PDF отказан;
  · генератор (splinter/bot): booking_id в make_contract при наличии; no_passport → названная версия формы из реестра;
    make_contract для поиска не зовётся никогда (ast-страж и счётчики поддельного моста);
  · флаги ВЫКЛ — поведение прежнее байт-в-байт (база, журнал, двери, процесс без модуля, блобы закреплённых файлов).
У каждого отрицательного случая — близнец-проход (тот же стенд без порчи проходит).

ИНТЕРФЕЙС ВЫПУСКА — ИЗ ПРОЕКТА (расхождение имени правится здесь, не в смысле):
  · `contract_ref.py` — чистые функции, импорты ровно `re` и `wa_agent_tools`: versions(find_resp, binding),
    binding_of_rental(number, rental), binding_of_crm(row), ref_of(find_resp, number, rental), same_version(a, b),
    crm_pick(rows, booking_id=, booking_key=, name=, date_start=) → (строка | None, слова | ""), gen_words(res),
    tail(doc); константы OUTCOMES, ROLES, PENDING_STATUSES, DEAD_STATUSES, GEN_NO_CRM, GEN_MANY_CRM, GEN_CRM_UNREAD,
    GEN_NO_TERM (§3, §6);
  · `wa_agent_attach.AttachCore(..., ref_of=None)` — только при засчитанном cstate; таблица `contract_versions`
    (§4.1); строка журнала сбоя записи — §4.1 дословно; `F_CONTRACT_REF`;
  · `wa_agent_cstate.ContractStateAdapter.ref_on` (по умолчанию False), `read_facts(..., ref=False)`;
  · `wa_contract_state.render` — строка версии по §4.3 (формы A и B, P, PEND);
  · `wa_agent_svc.F_CONTRACT_REF = "WA_AGENT_CONTRACT_REF"` (не в FLAGS), `contract_ref_of(environ, cstate_ok, model)`
    → тройка §4.4; строка старта «сверка версий договора (WA_AGENT_CONTRACT_REF): <слова>»;
  · `splinter.F_CONTRACT_REF_GEN = "CONTRACT_REF_GEN"` (процесс splinter/bot), `splinter._contract_ref_report(bridge,
    row=None, booking_id=None, booking_key=None, name=None, date_start=None)`, ветка «1b» команды «договор <uuid>»;
    `bot.scheduled_contract_km` — booking_id и одна строка журнала при no_passport (§5).

ТОЛКОВАНИЯ (где проект молчит; названы, чтобы расхождение правилось осознанно):
  · `truncated` читается в ЖИВОМ формате двери — `checked.truncated` (bridge_prod/ContractDoor.js:452);
  · слова `reason` у versions() не закрепляются, кроме приставки «реестр не прочитан: » (U) и «привязка не полна» (R3);
    у gen_words incomplete / unknown проверяется рамка текста, а не причина внутри скобок;
  · порядок строк в gen_words ambiguous (rows(signed)) — принимаются оба направления; остальные списки — по row убыв.;
  · привязка без факта аренды: phones не закрепляются (проект: «все поля пусты»), закреплены plate, даты, booking_id;
  · время снимка (`read_at`) = часы ядра при ответе двери = такт стенда (у поддельного реестра нет задержки);
  · у задания contract_km строка CRM передаётся в отчёт целиком — CRM второй раз не читается (`_call` ровно один —
    чтение самого задания); в ветке «1b» — ровно одно чтение CRM на команду;
  · случай «снимок старше версии» строится правкой `signed_cards.ts` во временной базе стенда (единственная прямая
    правка базы); сбой записи снимка — подменённым `core.db`, бросающим ТОЛЬКО на INSERT в contract_versions.

СТЕНДЫ — живые форматы прода (импортом, без копии): tests/test_wa_signed_card.py (World, Registry = форма
`bridge_client.contract_find`, Pdfs, Book), tests/test_wa_agent_svc.py (Bot API, часы), tests/rental_case_fakes.py
(строки двери clients, запрет сети) — последний только в дочернем процессе генератора. Модель блока — НАСТОЯЩИЙ
`ContractStateAdapter`; ядро — `AttachCore` с параметрами службы (cstate, claim_of, ref_of). Генератор (splinter/bot) и
проба «флаг выкл — модуля нет» идут ОТДЕЛЬНЫМИ процессами этого же файла (подмены модулей bot не текут в остальные
случаи; sys.modules чист). Сети нет; мост, модель, Telegram и WhatsApp — подделки; базы временные (tempfile) и не
удаляются. Данные синтетические: номер 79990001122 / 79999966963, байк Honda PCX 160 1234 / NINJA 400СС 6334,
«Тест Тестов», doc вида 1AbCdEf…_DOC34.

Запуск: python tests/test_contractref_accept.py (печать PASS/FAIL по случаю, код 1 при красном).
WA_AGENT_SRC=<каталог> подменяет модули (прогон мутантов)."""
import ast
import asyncio
import copy
import datetime
import hashlib
import inspect
import json
import logging
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
import types

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
if os.environ.get("WA_AGENT_SRC"):
    sys.path.insert(0, os.environ["WA_AGENT_SRC"])

PROBE_ARG = "--probe-ref-off"
PROBE_MARK = "CONTRACTREF_OFF "
GEN_ARG = "--gen-child"
GEN_MARK = "CONTRACTREF_GEN "
CHILD = PROBE_ARG in sys.argv[1:] or GEN_ARG in sys.argv[1:]
NEW_MODULE = "contract_ref"

import wa_agent as A  # noqa: E402
import wa_agent_attach as X  # noqa: E402
import wa_agent_cstate as C  # noqa: E402
import wa_agent_model as M  # noqa: E402
import wa_agent_svc as S  # noqa: E402
import wa_agent_tools as T  # noqa: E402
import wa_contract_state as CS  # noqa: E402
import test_wa_signed_card as SC  # noqa: E402  (стенд живых форматов SIGNEDCARD1410)

CR, CR_ERR = None, "процесс-проба: модуль сверки версий намеренно не импортируется"
if not CHILD:                       # пробы «флаг выкл» обязаны начинаться БЕЗ нового модуля в sys.modules
    try:
        import contract_ref as CR  # noqa: E402
        CR_ERR = None
    except Exception as e:                                           # noqa: BLE001 — назовёт каждый случай
        CR, CR_ERR = None, e

# ══ данные ═════════════════════════════════════════════════════════════════════════════════════════════════════

F_REF = "WA_AGENT_CONTRACT_REF"
F_GEN = "CONTRACT_REF_GEN"
DOCS = {r: "1AbCdEfGhIjKlMnOpQrStUvWx_DOC%d" % r for r in (33, 34, 35, 36, 37, 40)}
TAIL = {r: CS.doc_tail(d) for r, d in DOCS.items()}
SA33, SA34, SA35, SA36, SA37 = ("2026-10-14 16:10", "2026-10-14 17:47", "2026-10-14 18:37", "2026-10-14 19:04",
                                "2026-10-15 09:10")
SA36B = "2026-10-14 20:30"                                       # переподпись той же строки 36 (тот же doc_id)

# чистая функция (§8: номер 79990001122, байк Honda PCX 160 1234, срок 2026-10-14…2026-10-20)
NUM_R = "79990001122"
PHONE_R = "+7 999 000-11-22"
BIKE_R = "Honda PCX 160 1234"
NAME_R = "Тест Тестов"
NICK_R = "@test_nick"
FROM_R, TO_R = "2026-10-14", "2026-10-20"
RENTAL_FACT = {"kind": "rental", "booking_id": "B1234", "bike": BIKE_R, "date_start": FROM_R, "date_end": TO_R,
               "status": "В аренде", "price": 500, "currency": "THB"}
RENTAL_R = {"tool": "rental", "outcome": T.FACT, "source": "снимок броней", "ref": "B1234", "at": 0, "version": "",
            "window": "%s…%s" % (FROM_R, TO_R), "reason": "", "facts": [RENTAL_FACT]}
BIND = {"phones": [{"digits": NUM_R, "intl": True}], "plate": "1234", "date_from": FROM_R, "date_to": TO_R,
        "booking_id": "B1234"}
UUID = "3f2b8c1e-4d5a-4b6c-9e7f-0123456789ab"

# стенд агента (живые форматы test_wa_signed_card: номер 79999966963, байк NINJA 400СС PHUKET 6334, аренда 14…17)
NUM = SC.NUM
T_SIGN, T_START = SC.T_SIGN, SC.T_START
T34 = SC.phuket(2026, 10, 14, 17, 47)
PHUKET = 7 * 3600
PDF34 = SC.k3_pdf_fixture.classic(b"signed contract row 34 CONTRACTREF1510")
PDF36 = SC.PDF36
PDF36B = SC.k3_pdf_fixture.classic(b"re-signed contract row 36 CONTRACTREF1510")
PDF_OTHER = SC.k3_pdf_fixture.classic(b"some other contract bytes CONTRACTREF1510")
SHA34, SHA36, SHA36B = (hashlib.sha256(PDF34).hexdigest(), SC.SHA36, hashlib.sha256(PDF36B).hexdigest())
GAP = X.SIGNED_IDLE + X.SIGNED_EVERY + 60                         # следующий проход заведомо читает реестр снова
RU_TEXT = X.SIGNED_TEXT["ru"]
CLAIM = "Подписал договор"
STAFF = "Даня"
OTHER_BIKE = SC.BIKE2                                            # «PCX 160 WHITE PHUKET 5580» — другой номер байка
SVC_ON = {"WA_AGENT_DRAFTS": "1", "WA_AGENT_CARDS": "1", "WA_SEND": "1", "WA_AGENT_TOOLS": "1",
          "WA_AGENT_BOOK_READ": "1", "WA_AGENT_ATTACH": "1"}
V_COLS = {"number", "doc_id", "row", "read_at", "outcome", "role", "status", "signed", "signed_at", "pdf_id",
          "booking_id", "reason"}
ITEM_KEYS = {"row", "doc_id", "status", "signed", "signed_at", "pdf_id", "contract_date", "role"}
RES_KEYS = {"outcome", "reason", "current", "pending", "superseded", "foreign", "unchecked", "rows", "booking_id"}

# слова проекта ДОСЛОВНО (§4.1, §4.4, §6)
W_REF_NOT = ("не засчитан — флаг 1, но состояние договора для модели (WA_AGENT_CONTRACT_STATE) не засчитано: сверки "
             "версий нет")
W_REF_MOD = "не засчитан — модуль сверки версий не собран (%s)"
W_REF_ON = ("вкл — проход подписи пишет последнее чтение реестра по номеру (contract_versions: doc_id, строка, статус, "
            "подписан, PDF — без имён и телефонов); строка версии в блоке договора модели говорит, действует ли "
            "версия по реестру, и называет текущую или ждущую подписи; PDF, карточки и отправка — как прежде")
LINE_REF = "сверка версий договора (WA_AGENT_CONTRACT_REF): %s"
W_WRITE_FAIL = "сверка версий договора: чтение реестра не записано (%s) — блок модели скажет прежнее"
GEN_NO_CRM = "бронь в CRM не найдена — реестр не читал"
GEN_MANY_CRM = "броней в CRM с этим ключом несколько (строки %s) — реестр не читал"
GEN_CRM_UNREAD = "CRM не прочитан (%s) — реестр не читал, неизвестно"
GEN_NO_TERM = "в строке брони нет номера байка или срока — реестр не читал"
GEN_TAIL = " — мост его не пересоберёт: строки паспорта в Bot Data нет (договор сделан не мостом)"
W_NONE_HEAD = "в реестре по байку и сроку брони подписанного и ждущего подписи нет (строк в сроке: "
W_UNKNOWN_HEAD = "реестр не прочитан ("
W_UNKNOWN_TAIL = " — неизвестно, а не «договора нет»"
W_INC_HEAD = "реестр прочитан не полностью или привязка не сверена ("
W_AMB_HEAD = "в реестре подписанных по этой брони несколько: "
W_AMB_TAIL = " — какой текущий, решает человек"
B_HEAD = "• версия: в базе нет (карточки подписи и сверки ответов)"

# закреплённые файлы: блобы 556e744 (`git ls-tree 556e744 …`) — выпуск их НЕ трогает (§2.2, §8.4)
PINS = {
    "wa_agent.py": "70695c7dc669f2b4d14ff7c000763b915e6121e8",
    "wa_agent_model.py": "868b0c4b3abd75d6f4fca6b1c7021d0f121db3ce",
    "wa_agent_tools.py": "fb70716d09b8b2812c08d40f2b0d66ff18ead9e3",
    "wa_agent_knowledge.py": "d338a3c23fcfa7f8180a6ed75b38a93e6e4200d3",
    "rental_case.py": "3e3cba2f63461ae6fccf1a7d3f044da0c22cbca0",
    "bridge_client.py": "71d290387c95dc283a477f1c44ab4e4c9bedb665",
    "wa_book_read.py": "7329698d797d5b045692f4a9889e830c081ce78d",
    "wa_agent_tg.py": "4f83f9be2819306775e48612d13f7bffa1d209ae",
    "contract_ask.py": "be132d7a099dbb84edadca636989cb16dd19c607",
    "bridge_prod/Archive.js": "3cd8451d609cc100d97be821fa6da884f0d3402b",
    "bridge_prod/Booking.js": "352ffdd9458873c064bf7acef796e6b55d1b29db",
    "bridge_prod/BotData.js": "bc3ccb87a59102a31407d3e905a82628bcfab378",
    "bridge_prod/BrainTrash.js": "e92fe322eb0d28ae19df23059cd0bd1b0266319d",
    "bridge_prod/Bridge.js": "aa67471d5b708288248f8c1ee4a9c82529bcbdb0",
    "bridge_prod/Closing.js": "09f6db1143b231569b5030e39e76b71d31eb9e4c",
    "bridge_prod/Config.js": "a40d88028f72bb2db70116360217e0e716df7537",
    "bridge_prod/Contract.js": "2ca2193d7022d9ae2ac3c6ff34a55919874fd848",
    "bridge_prod/ContractDoor.js": "0d744aa47a3484132cbacee518c068159b9f94d8",
    "bridge_prod/Delivery.js": "9c0d8ed302ff055fa3fbe66155942c6b6ef78f6e",
    "bridge_prod/MIRROR.json": "5f4147f1112bab76753c21d2722bc394767ccb2e",
    "bridge_prod/Passport.js": "6d0afecc0cdefe960303b0c0fc2712edbda16b14",
    "bridge_prod/QuotePrice.js": "6889994d83cdca49a5fb70df2a809fab7519caf4",
    "bridge_prod/ReadClients.js": "406a7115ba8c5bffc452a54d9a429f8129f9e076",
    "bridge_prod/ReadDocs.js": "798fb548beff9a8ecb9d989602653e33686b3d22",
    "bridge_prod/ReadFinance.js": "6b52a58a38b2a892babc76e79b5fa95cea0db40d",
    "bridge_prod/ReadFleet.js": "bcd470b1a30f5a8fc67361119e5301618189cf59",
    "bridge_prod/ServicePending.js": "3c2f31fd7b476eaf3a87c6a4884d0280cde15a9b",
    "bridge_prod/ServiceUndo.js": "cfbf8d0f31beda6a9b5aea36563e32dbf36960f1",
    "bridge_prod/appsscript.json": "8bc733bd40817ff702df5b98811d18a4a2428cc9",
    # существующие наборы — доказательство «флаг выкл — прежнее»: правок в них нет (§2.2, §8.4)
    "tests/k3_pdf_fixture.py": "dd52642ec712d7504c87be3d976f49b075a7b595",
    "tests/rental_case_fakes.py": "74f5e283f39a725e46b146f0be62050a56b3bf93",
    "tests/test_agent_contract_bind.py": "35b0ad49446df70808cab958e05254e94de207d3",
    "tests/test_audit_button.py": "cde60fa41caa4a4ce6de7b6d408a289094b7fa29",
    "tests/test_handover_activation.py": "624537218699449fb488b1818d687d51703f29e0",
    "tests/test_never_silent.py": "a51f5e706dc642bfb145422881a8f08b830743d0",
    "tests/test_rental_case_integ_spl.py": "59b9ace25fc6ba553663133007007df6f85d970d",
    "tests/test_rental_case_integ_wa.py": "8f5db518a9cd1ddf077b925209083778b14b5a72",
    "tests/test_return_close.py": "817fb7c8713eb3c25319fcb14529ea68c0e7f481",
    "tests/test_wa_agent_attach.py": "c54b01f18ee14c7461f742ebf0a1408a6abad796",
    "tests/test_wa_agent_svc.py": "154b2d34bee7d61107d49956ebc1c633bef9a341",
    "tests/test_wa_attach_basis.py": "4921ac2f533b780046c9f18a62155df11fd7361c",
    "tests/test_wa_attach_casepdf.py": "af18c24cc9fdb002b2aac055930239113ccfb4ba",
    "tests/test_wa_attach_casepdf_accept.py": "6ec6e3714a72615d8403b40b8438fa296df2cb31",
    "tests/test_wa_attach_casepdf_fix.py": "ee04bebd3c8a5821f1f3be3d0a33efe8ee6bf632",
    "tests/test_wa_attach_casestate.py": "b4529669fed3c5faeaecbc8a0c6b1c06ac291222",
    "tests/test_wa_attach_casestate_accept.py": "6a2fc49576ae2d4c19461309706c7075bc72b791",
    "tests/test_wa_attach_contract_ask.py": "f2241554c670821aac31ae6dde9f829c50ca24ae",
    "tests/test_wa_attach_cstate.py": "5015c4b008d094f5758e5031b9edde87f3c3ee69",
    "tests/test_wa_attach_expect.py": "4fdac0749eb21f3391596587a108746b3b936b3b",
    "tests/test_wa_attach_svc.py": "d69add04e17cb652663e668a768f5a230dbd02a1",
    "tests/test_wa_signed_card.py": "d92bf213f14e4394382a05d90b69a83452138e4c",
    "tests/test_wa_signed_card_accept.py": "7653b5373d8b75c7747b972e4816d958475a36de",
}
TOOLS_BLOCK_SHA = "175b220824b649ce151ae7f463ac864166265b26e9ccd13d42032a93d850d3d1"
ATTACH_IMPORTS = {"base64", "hashlib", "re", "zlib", "wa_agent", "wa_agent_tools"}
PROD_ATTACH_KW = {"attach", "pdf_fetch", "contract_find", "signed", "signed_lookback_h", "signed_budget", "ask_of",
                  "autosend", "cstate", "claim_of"}
PROD_MAKE_MODEL = ["env", "line", "bridge", "call", "lessons", "book", "cache", "tools", "hints", "cstate"]
SEARCH_FORBIDDEN = {"make_contract", "save_passport", "ocr_passport"}
PURE_FORBIDDEN = {"make_contract", "save_passport", "ocr_passport", "_post", "issue_write_ticket", "agent_write",
                  "create_booking", "open", "os", "sys", "socket", "sqlite3", "subprocess", "urllib", "requests"}
REPORT_FORBIDDEN = {"make_contract", "issue_write_ticket", "agent_write", "_post", "save_passport", "create_booking"}


# ══ общие помощники ════════════════════════════════════════════════════════════════════════════════════════════

def _cr():
    assert CR is not None, "модуля contract_ref нет: %r" % (CR_ERR,)
    return CR


def hm(ts):
    return time.strftime("%H:%M", time.gmtime(ts + PHUKET))


def rows_of(lst):
    return [x["row"] for x in lst or []]


def _blob_ok(path, sha):
    """Git-блоб файла равен закреплённому: байты как есть, а при выдаче с CRLF (autocrlf) — после LF-нормализации."""
    with open(path, "rb") as f:
        raw = f.read()
    for data in (raw, raw.replace(b"\r\n", b"\n")):
        if hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest() == sha:
            return True
    return False


def _tree(path):
    with open(path, encoding="utf-8") as f:
        return ast.parse(f.read())


def _imports(node):
    out = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Import):
            out |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            out.add((n.module or "").split(".")[0])
    return out


def _names(node):
    """Имена кода узла: Name, Attribute, псевдонимы импорта — без строк и комментариев."""
    out = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Name):
            out.add(n.id)
        elif isinstance(n, ast.Attribute):
            out.add(n.attr)
        elif isinstance(n, ast.alias):
            out.add(n.name.split(".")[0])
            if n.asname:
                out.add(n.asname)
    return out


def _module_level_imports(tree):
    """Импорты ВНЕ функций (выполняются при импорте модуля) — ленивые внутри def/async def не считаются."""
    out = set()

    def walk(node, in_fn):
        for ch in ast.iter_child_nodes(node):
            fn = in_fn or isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda))
            if not fn and isinstance(ch, ast.Import):
                out.update(a.name.split(".")[0] for a in ch.names)
            elif not fn and isinstance(ch, ast.ImportFrom):
                out.add((ch.module or "").split(".")[0])
            walk(ch, fn)
    walk(tree, False)
    return out


def tables(path):
    db = sqlite3.connect(path)
    try:
        return {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    finally:
        db.close()


def dump_wo(path, skip=("contract_versions",)):
    """База агента целиком без таблицы снимка: схема и строки всех прочих таблиц (порядок строк не важен)."""
    db = sqlite3.connect(path)
    try:
        out = {"__schema__": sorted((r[0] or "") for r in db.execute("SELECT sql, tbl_name FROM sqlite_master")
                                    .fetchall() if r[1] not in skip)}
        for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall():
            if name not in skip:
                out[name] = sorted(repr(r) for r in db.execute('SELECT * FROM "%s"' % name).fetchall())
        return out
    finally:
        db.close()


def copy_without(src, dst, skip):
    """Копия базы без одной таблицы (новый файл во временном каталоге; исходник не трогается)."""
    s, d = sqlite3.connect(src), sqlite3.connect(dst)
    try:
        for name, sql in s.execute("SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE "
                                   "'sqlite_%'").fetchall():
            if name == skip:
                continue
            d.execute(sql)
            rows = s.execute('SELECT * FROM "%s"' % name).fetchall()
            if rows:
                d.executemany('INSERT INTO "%s" VALUES (%s)' % (name, ",".join("?" * len(rows[0]))), rows)
        for sql, tbl in s.execute("SELECT sql, tbl_name FROM sqlite_master WHERE type='index' AND sql IS NOT NULL"):
            if tbl != skip:
                d.execute(sql)
        d.commit()
    finally:
        s.close()
        d.close()


# ── реестр в живом формате двери contract_find (bridge_prod/ContractDoor.js:326-456) ────────────────────────

def ritem(row, status, signed_at="", pdf_id="", phone=PHONE_R, bike=BIKE_R, date="2026-10-15", on=("phone",),
          doc=None, client=NAME_R, **extra):
    raw = "%s.%s.%s" % (date[8:10], date[5:7], date[:4]) if date else ""
    d = {"row": row, "doc_id": DOCS.get(row, "") if doc is None else doc, "client": client,
         "contract_date": date or None, "contract_date_raw": raw, "created_raw": "",
         "date_src": "contract_date" if date else "none", "status": status, "signed": status == "ПОДПИСАН",
         "signed_at": signed_at, "bike": bike, "phone": phone, "pdf_id": pdf_id, "matched_on": list(on)}
    d.update(extra)
    return d


def fresp(items, outcome=None, undated_items=(), unread=(), truncated=False, phone_last9=None, date_from=FROM_R,
          date_to=TO_R, sort=True, bike=""):
    its = [dict(i) for i in items]
    if sort:
        its.sort(key=lambda x: -int(x["row"]))
    aside = [dict(i) for i in undated_items]
    signed = [i for i in its if i.get("signed")]
    aside_signed = [i for i in aside if i.get("signed")]
    if outcome is None:
        outcome = ("incomplete" if aside_signed and len(signed) <= 1 else "none" if not its else
                   "none_signed" if not signed else "ambiguous" if len(signed) > 1 else "one")
    pick = dict(signed[0], pdf_ready=bool(signed[0].get("pdf_id"))) if outcome == "one" and signed else None
    reason = ({"code": "undated_signed", "rows": [i["row"] for i in aside_signed],
               "message": "подписанный договор под фильтр без известного дня"} if outcome == "incomplete" else None)
    return {"ok": True, "outcome": outcome, "pick": pick, "reason": reason, "items": its, "undated_items": aside,
            "checked": {"sheet": "Реестр", "rows_scanned": 240, "span_from": date_from, "span_to": date_to,
                        "undated": len(aside), "undated_signed": len(aside_signed), "date_unparsed": 0,
                        "unread": list(unread), "complete": not aside and not unread, "matched": len(its),
                        "signed": len(signed), "returned": len(its), "truncated": bool(truncated)},
            "filter": {"phone_last9": T.last9(NUM_R) if phone_last9 is None else phone_last9, "name": "",
                       "bike": bike, "plate": T.plate_of(bike), "date_from": date_from, "date_to": date_to},
            "limit": 20, "limit_max": 100, "config": {"registry": "property"}}


def vers(items, bind=None, **kw):
    return _cr().versions(fresp(items, **kw), copy.deepcopy(BIND if bind is None else bind))


def w_current(row, status, sa):
    return "в реестре есть подписанный договор этой брони: стр. %s · %s %s · doc %s%s" % (row, status, sa, TAIL[row],
                                                                                         GEN_TAIL)


def w_pending(row, status):
    return "в реестре договор этой брони ждёт подписи: стр. %s · %s · doc %s%s" % (row, status, TAIL[row], GEN_TAIL)


# ── стенд агента: ядро с параметрами службы (cstate + claim_of + ref_of) ───────────────────────────────────

class Script:
    """Модель по сценарию: ответы по порядку, последний повторяется; `seen` — user каждого хода."""

    def __init__(self, *answers):
        self.answers = list(answers) or [{"text": "Спасибо!", "handoff": [], "lang": "ru", "why": "приёмка"}]
        self.seen = []

    def __call__(self, system, user):
        self.seen.append(user)
        a = self.answers[min(len(self.seen) - 1, len(self.answers) - 1)]
        return (a if isinstance(a, str) else json.dumps(a, ensure_ascii=False)), {"in": 10, "out": 5}


def _no_cash(**kw):
    return {"ok": False, "error": "касса стенду не нужна"}


def rrow(row, status, signed_at="", pdf_id="", **kw):
    """Строка реестра стенда подписи (форма `SC.reg_row`) с длинным doc_id."""
    r = SC.reg_row(row, status, signed_at, pdf_id, **kw)
    r["doc_id"] = DOCS[row]
    return r


def live_rows_ref():
    return [rrow(34, "ОТОЗВАН", SA34, "P34"), rrow(35, "ОТОЗВАН", SA35, "P35"), rrow(36, "ПОДПИСАН", SA36, "PDF36")]


class RefWorld(SC.World):
    """Стенд SIGNEDCARD1410, ядро собрано как службой при засчитанных WA_AGENT_CONTRACT_STATE (cstate=True, claim_of) и
    WA_AGENT_CONTRACT_REF (ref_of = contract_ref.ref_of — ровно kwargs `contract_ref_of`). ref=False — прод-вызов без
    аргумента; иное значение — передаётся как есть."""

    def __init__(self, ref=True, cstate=True, **kw):
        self.ref, self.cstate_on, self.mlog = ref, cstate, []
        SC.World.__init__(self, **kw)

    def new_core(self):
        kw = dict(log=self.lines.append, clock=self.clock, attach=True, pdf_fetch=self.pdfs,
                  contract_find=self.registry, signed=self.signed, signed_lookback_h=self.lookback_h,
                  ask_of=X.ask_verdict_many, cstate=self.cstate_on,
                  claim_of=CS.signed_claim if self.cstate_on else None)
        if self.ref is True:
            kw["ref_of"] = _cr().ref_of
        elif self.ref not in (False, None):
            kw["ref_of"] = self.ref
        return X.AttachCore(self.dbpath, self.qpath, self.model, self.tg, self.door, **kw)


def set_row(w, row, **upd):
    for r in w.registry.rows:
        if r["row"] == row:
            r.update(upd)
            if "status" in upd:
                r["signed"] = upd["status"] == "ПОДПИСАН"


def state_of(w, did):
    return w.q("SELECT state FROM drafts WHERE id=?", (did,))[0][0]


def card(w, t_in=None, t=None, text=CLAIM):
    """Клиент пишет → такт → ровно одна карточка подписи. → (черновик, время такта)."""
    t_in = T_SIGN + 60 if t_in is None else t_in
    t = t_in + 540 if t is None else t
    w.put(t_in, text)
    w.tick(t)
    sd = w.signed_drafts()
    assert len(sd) == 1, ("карточки подписи нет или их несколько", sd, w.sign_lines()[-6:])
    return sd[0][0], t


def snap_head(w, number=NUM):
    got = w.q("SELECT read_at, outcome, role, status, signed, signed_at, pdf_id, booking_id, reason FROM "
              "contract_versions WHERE number=? AND doc_id='' AND row=0", (number,))
    assert len(got) == 1, ("строки-итога чтения нет", got)
    return got[0]


def snap_items(w, number=NUM):
    """Строки снимка, принадлежащие ПОСЛЕДНЕМУ чтению (read_at итога) — так их берёт читатель блока."""
    head = snap_head(w, number)
    return w.q("SELECT doc_id, row, role, status, signed, signed_at, pdf_id FROM contract_versions WHERE number=? "
               "AND doc_id<>'' AND read_at=? ORDER BY row DESC", (number, head[0]))


def snap_all(w, number=NUM):
    return w.q("SELECT number, doc_id, row, read_at, outcome, role, status, signed, signed_at, pdf_id, booking_id, "
               "reason FROM contract_versions WHERE number=? ORDER BY row DESC", (number,))


def last_in(w, number=NUM):
    q = sqlite3.connect(w.qpath)
    try:
        return q.execute("SELECT MAX(id) FROM wa_inbox WHERE from_number=? AND echo=0 AND msg_type<>'status'",
                         (number,)).fetchone()[0]
    finally:
        q.close()


def reader(w, ref=True, agent_db=None, script=None):
    """НАСТОЯЩИЙ адаптер блока на файлах стенда; ref — значение `ref_on` (None — атрибут не трогается)."""
    ad = C.ContractStateAdapter(w.qpath, script or Script(), book=w.book, clock=w.clock,
                                agent_db=agent_db or w.dbpath, log=w.mlog.append,
                                tools={"cash": _no_cash, "contract": w.registry, "contract_pdf": w.pdfs})
    if ref is not None:
        ad.ref_on = bool(ref)
    return ad


def blk(ad, number, upto, now):
    """Адаптер → (блок | None, user, базовый user, info): блок обязан стоять В НАЧАЛЕ user через пустую строку."""
    s1, u1, i1 = ad.build(number, upto, now=now)
    s0, u0, _i0 = M.ModelAdapter.build(ad, number, upto, now=now)
    assert s1 == s0, "блок не трогает system"
    assert i1.get("user_chars") == len(u1), ("user_chars не пересчитан", i1.get("user_chars"), len(u1))
    if u1 == u0:
        return None, u1, u0, i1
    assert u1.endswith("\n\n" + u0) and len(u1) > len(u0) + 2, ("блок не в начале user", u1[:400])
    b = u1[:len(u1) - len(u0) - 2]
    assert b.startswith("ДОГОВОР КЛИЕНТА"), b[:200]
    return b, u1, u0, i1


def block(w, now, ref=True, number=NUM):
    b, _u, _b0, _i = blk(reader(w, ref), number, last_in(w, number), now)
    assert b is not None, "вопрос о договоре / записи по номеру есть — блок обязан быть"
    return b


def line(b, label):
    got = [ln for ln in b.split("\n") if (label + ":") in ln]
    assert got, ("строки «%s:» в блоке нет" % label, b)
    return got[0]


def vline(w, now, ref=True):
    return line(block(w, now, ref), "версия")


def clean_block(b):
    """Замки блока (test_12 CSTATE + §4.3): ≤ 8 строк и 1200 знаков, строка ≤ LINE_MAX; ни 9+ цифр, ни года, ни
    номеров строк реестра, ни pdf_id, ни полного doc_id; даты только «ДД.ММ ЧЧ:ММ» / «ЧЧ:ММ»; ни имён, ни телефона."""
    rows = b.split("\n")
    assert len(rows) <= CS.BLOCK_LINES and len(b) <= CS.BLOCK_CHARS, (len(rows), len(b))
    for ln in rows[1:]:
        assert len(ln) <= CS.LINE_MAX + 2, (len(ln), ln)
    assert not re.search(r"\d{9,}", b) and "2026" not in b, b
    assert "стр." not in b, b
    for d in DOCS.values():
        assert d not in b, ("полный doc_id в блоке", b)
    for pid in ("P34", "P35", "PDF36", "PDF36B", "PDF37"):
        assert not re.search(r"\b%s\b" % pid, b), ("pdf_id в блоке", pid, b)
    for bad in ("Иван", NAME_R, "999 996", "+7 999", NUM, NUM_R):
        assert bad not in b, (bad, b)
    for d in re.findall(r"\d{1,4}[./-]\d{1,2}(?:[./-]\d{2,4})?", b):
        assert re.fullmatch(r"\d{2}\.\d{2}", d), (d, b)
    assert not re.search(r"\b\d{2}\.\d{2}\b(?! \d{2}:\d{2})", b), ("день без времени", b)


def tools_pdf(row=36, doc=None, pdf="PDF36", sa=SA36, data=PDF36):
    """Итог сверки Т4а (форма `ModelAdapter.last["tools"]`): договор этой аренды и его PDF приняты."""
    rent = {"kind": "rental", "booking_id": "B6334", "bike": SC.BIKE, "date_start": "2026-10-14",
            "date_end": "2026-10-17"}
    return {"state": "done", "results": [
        SC.res("rental", "fact", [rent]),
        SC.res("contract", "fact", [{"kind": "contract", "row": row, "doc_id": doc or DOCS[row], "bike": SC.BIKE,
                                     "signed_at": sa, "pdf_id": pdf, "booking_id": "B6334"}],
               window="2026-10-14…2026-10-17"),
        SC.res("contract_pdf", "fact", [{"kind": "pdf", "id": pdf, "name": "contract_%d.pdf" % row,
                                         "size": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                                         "row": row}])]}


def tools_ambiguous():
    rent = {"kind": "rental", "booking_id": "B6334", "bike": SC.BIKE, "date_start": "2026-10-14",
            "date_end": "2026-10-17"}
    return {"state": "done", "results": [SC.res("rental", "fact", [rent]),
                                         SC.res("contract", "ambiguous", reason="подписанных несколько — выбрать нельзя")]}


def svc(environ, cls=None):
    """Служба `wa_agent_svc.build` на подделках (Bot API, провайдер) с адаптером класса cls и дверями сверки стенда."""
    import test_wa_agent_svc as SV
    cls = cls or C.ContractStateAdapter
    d = tempfile.mkdtemp(prefix="contractref_svc_")
    env = {"queue_db": os.path.join(d, "svc_q.db"), "mirror_db": os.path.join(d, "mirror.db"),
           "agent_db": os.path.join(d, "svc_agent.db"), "tg_token": SV.TOKEN, "show_chat": SV.SHOW,
           "log_path": os.path.join(d, "wa_agent.log")}
    q = sqlite3.connect(env["queue_db"])
    q.execute(SV.QSCHEMA)
    q.commit()
    q.close()
    m = sqlite3.connect(env["mirror_db"])
    m.execute("CREATE TABLE topics (number TEXT PRIMARY KEY, thread_id INTEGER, trigger_id INTEGER, stage TEXT, "
              "ts REAL, name TEXT)")
    m.execute("CREATE TABLE shown (key TEXT PRIMARY KEY, number TEXT, state TEXT, ts REAL, msg_id INTEGER, "
              "solo INTEGER)")
    m.commit()
    m.close()
    clock = SV.Clock(T_START)
    model = cls(env["queue_db"], Script(), book=SC.Book([SC.book_row()]), clock=clock, agent_db=env["agent_db"],
                log=lambda s: None, tools={"cash": _no_cash, "contract": SC.Registry(), "contract_pdf": SC.Pdfs()})
    lines = []
    core, _tg, _flags, _words = S.build(
        env, environ=dict(environ), model=model, http=SV.FakeHttp(clock),
        send=lambda to, text, db_path=None: {"outcome": "not_sent", "reason": "набор не шлёт", "wamid": None},
        send_media=lambda to, media, db_path=None: {"outcome": "not_sent", "reason": "набор не шлёт", "wamid": None},
        clock=clock, line=lines.append)
    return core, lines, model, env


# ══ A · сторона wa-agent (ядро, снимок, блок модели, служба) ═════════════════════════════════════════════════════

def test_a01_case_sequence_block_and_pdf_follow_current_version():
    """Последовательность одного дела при флаге ВКЛ: 34 ПОДПИСАН → 34 ОТОЗВАН + 36 НОВЫЙ → 36 ОТПРАВЛЕН → 36 ПОДПИСАН.
    Снимок реестра и строка версии блока модели идут за реестром (действует → ОТОЗВАН — НЕ текущая + указатель на
    ждущую → действует 36); старая версия 34 в блоке текущей не названа; клиенту уходит PDF 36, PDF 34 — никогда."""
    w = RefWorld(rows=[rrow(34, "ПОДПИСАН", SA34, "P34")])
    w.pdfs.files["P34"] = (34, PDF34)
    d34, t1 = card(w, T34 + 60, T34 + 600)
    assert w.attach(d34)[:7] == ("P34", "contract_34.pdf", len(PDF34), SHA34, 34, DOCS[34], SA34), w.attach(d34)
    head = snap_head(w)
    assert head[0] == t1 and head[1] == "current", head
    assert [(i[1], i[2]) for i in snap_items(w)] == [(34, "current")], snap_items(w)
    b = block(w, t1 + 60)
    assert line(b, "версия") == "• версия: подписан 14.10 17:47 · doc %s · реестр %s: действует" % (TAIL[34], hm(t1)), b
    clean_block(b)
    # ── 34 ОТОЗВАН + 36 НОВЫЙ ───────────────────────────────────────────────────────────────────────────────
    w.registry.revoke(34)
    w.registry.rows.append(rrow(36, "НОВЫЙ"))
    t2 = t1 + GAP
    w.tick(t2)
    assert [r[0] for r in w.signed_drafts()] == [d34] and state_of(w, d34) == A.PENDING, w.signed_drafts()
    head = snap_head(w)
    assert (head[0], head[1]) == (t2, "pending"), head
    assert [(i[1], i[2]) for i in snap_items(w)] == [(36, "pending"), (34, "superseded")], snap_items(w)
    want = ("• версия: подписан 14.10 17:47 · doc %s · реестр %s: ОТОЗВАН — НЕ текущая; новая doc %s не отправлена "
            "на подпись (НОВЫЙ)" % (TAIL[34], hm(t2), TAIL[36]))
    b = block(w, t2 + 60)
    assert line(b, "версия") == want, (line(b, "версия"), want)
    clean_block(b)
    # ── 36 ОТПРАВЛЕН ────────────────────────────────────────────────────────────────────────────────────────
    set_row(w, 36, status="ОТПРАВЛЕН")
    t3 = t2 + GAP
    w.tick(t3)
    assert snap_head(w)[:2] == (t3, "pending"), snap_head(w)
    want = ("• версия: подписан 14.10 17:47 · doc %s · реестр %s: ОТОЗВАН — НЕ текущая; новая doc %s ждёт подписи "
            "(ОТПРАВЛЕН)" % (TAIL[34], hm(t3), TAIL[36]))
    b = block(w, t3 + 60)
    assert line(b, "версия") == want, (line(b, "версия"), want)
    assert len(want) - 2 <= CS.LINE_MAX
    clean_block(b)
    assert w.door.sends == [] and w.door.media == [], "клиенту без нажатия ничего"
    # ── 36 ПОДПИСАН ─────────────────────────────────────────────────────────────────────────────────────────
    set_row(w, 36, status="ПОДПИСАН", signed_at=SA36, pdf_id="PDF36")
    t4 = T_SIGN + 600
    assert t4 > t3 + X.SIGNED_IDLE
    w.tick(t4)
    sd = w.signed_drafts()
    assert len(sd) == 2 and sd[0][0] == d34 and sd[1][1] == A.PENDING, (sd, w.sign_lines()[-6:])
    d36 = sd[1][0]
    assert state_of(w, d34) == A.SUPERSEDED, state_of(w, d34)
    assert w.attach(d36)[:7] == ("PDF36", "contract_36.pdf", len(PDF36), SHA36, 36, DOCS[36], SA36), w.attach(d36)
    assert [v[1:4] for v in w.versions()] == [(DOCS[34], SA34, "P34"), (DOCS[36], SA36, "PDF36")], w.versions()
    assert snap_head(w)[:2] == (t4, "current"), snap_head(w)
    assert [(i[1], i[2]) for i in snap_items(w)] == [(36, "current"), (34, "superseded")], snap_items(w)
    b = block(w, t4 + 60)
    vl = line(b, "версия")
    assert vl == "• версия: подписан 14.10 19:04 · doc %s · реестр %s: действует" % (TAIL[36], hm(t4)), vl
    assert TAIL[34] not in b and "17:47" not in vl, b
    clean_block(b)
    # ── PDF: снятая карточка 34 не уходит, карточка 36 — текст и PDF 36 ───────────────────────────────────────
    old = w.core.press(d34, 1, A.ACT_SEND, STAFF, t4 + 100)
    assert not old.get("ok") and w.door.sends == [] and w.door.media == [], (old, w.door.sends, w.door.media)
    out = w.core.press(d36, 1, A.ACT_SEND, STAFF, t4 + 120)
    assert out.get("ok") and out.get("parts") == {"text": A.SENT, "pdf": A.SENT}, out
    assert w.door.sends == [(NUM, RU_TEXT)], w.door.sends
    assert w.door.media == [(NUM, "document", "application/pdf", "contract_36.pdf", SHA36)], w.door.media


def _story(ref):
    """Та же последовательность дела, финал — «Отправить» карточки 36 (флаг ref вкл/выкл)."""
    w = RefWorld(ref=ref, rows=[rrow(34, "ПОДПИСАН", SA34, "P34")])
    w.pdfs.files["P34"] = (34, PDF34)
    card(w, T34 + 60, T34 + 600)
    t = T34 + 600
    w.registry.revoke(34)
    w.registry.rows.append(rrow(36, "НОВЫЙ"))
    t += GAP
    w.tick(t)
    set_row(w, 36, status="ОТПРАВЛЕН")
    t += GAP
    w.tick(t)
    set_row(w, 36, status="ПОДПИСАН", signed_at=SA36, pdf_id="PDF36")
    w.tick(T_SIGN + 600)
    did = w.signed_drafts()[-1][0]
    out = w.core.press(did, 1, A.ACT_SEND, STAFF, T_SIGN + 720)
    return w, out


def test_a02_flag_off_story_byte_equal_only_snapshot_differs():
    """A1 (а) и близнец: без ref_of таблицы contract_versions нет; с ref_of — вызовы двери (kwargs), drafts,
    signed_cards, contract_expect, pdf_parts, attach, журнал ядра, двери WhatsApp и PDF РАВНЫ прогону без флага;
    отличается ровно contract_versions."""
    w0, out0 = _story(False)
    w1, out1 = _story(True)
    assert "contract_versions" not in tables(w0.dbpath), tables(w0.dbpath)
    assert "contract_versions" in tables(w1.dbpath) and snap_all(w1), "при флаге снимок есть"
    assert out0 == out1, (out0, out1)
    assert w0.registry.calls == w1.registry.calls and len(w0.registry.calls) >= 5, (w0.registry.calls,
                                                                                      w1.registry.calls)
    assert dump_wo(w0.dbpath) == dump_wo(w1.dbpath), "база вне снимка обязана совпасть байт-в-байт"
    assert w0.lines == w1.lines, [x for x in w1.lines if x not in w0.lines][:6]
    assert (w0.door.sends, w0.door.media) == (w1.door.sends, w1.door.media)
    assert w0.pdfs.calls == w1.pdfs.calls and w0.rental_calls == w1.rental_calls and w0.tg.cards == w1.tg.cards


def test_a03_adapter_ref_off_reads_nothing_and_call_form():
    """A1 (б): `ref_on=False` на базе с заполненной contract_versions — build() равен build на копии базы БЕЗ таблицы
    (system, user, info); вызов read_facts прежний (позиционно, без ключа ref — позиционная подделка проходит); при
    `ref_on=True` — тот же вызов с ref=True и другая строка версии (чувствительность). По умолчанию ref_on — False."""
    w, _out = _story(True)
    now = T_SIGN + 800
    upto = last_in(w)
    bare = os.path.join(tempfile.mkdtemp(prefix="contractref_bare_"), "agent_bare.db")
    copy_without(w.dbpath, bare, "contract_versions")
    assert "contract_versions" not in tables(bare) and "contract_versions" in tables(w.dbpath)
    got = reader(w, ref=False).build(NUM, upto, now=now)
    base = reader(w, ref=False, agent_db=bare).build(NUM, upto, now=now)
    assert got == base, "ref_on=False — таблица снимка не читается вовсе"
    v_on, v_off = vline(w, now, ref=True), vline(w, now, ref=False)
    assert "реестр" in v_on and "реестр" not in v_off and v_on != v_off, (v_on, v_off)
    assert v_off == "• версия: подписан 14.10 19:04 · doc %s · карточка подписи" % TAIL[36], v_off
    assert C.ContractStateAdapter(w.qpath, None).ref_on is False
    real, seen = C.read_facts, []

    def spy(*a, **k):
        seen.append((len(a), dict(k)))
        return real(*a, **k)
    C.read_facts = spy
    try:
        reader(w, ref=False).build(NUM, upto, now=now)
        reader(w, ref=True).build(NUM, upto, now=now)
    finally:
        C.read_facts = real
    assert seen[0] == (4, {}), ("выкл — прежний вызов дословно, без ref", seen)
    assert seen[1] == (4, {"ref": True}), ("вкл — ref=True", seen)

    def positional(path, number, at, timeout):
        return dict({k: None for k in C.SOURCES}, read_at=float(at), unread=[], records=0)
    C.read_facts = positional
    try:
        _s, _u, info = reader(w, ref=False).build(NUM, upto, now=now)
    finally:
        C.read_facts = real
    assert "cstate" in info, info.keys()


def test_a04_service_flag_rule_start_line_table():
    """§4.4 и A2: флаг не запрошен — (None, None, None), ни строки, ни таблицы; запрошен при незасчитанном
    WA_AGENT_CONTRACT_STATE — «не засчитан — …» дословно, ref_on False, таблицы нет; модуль не собран — «не засчитан —
    модуль сверки версий не собран (…)»; засчитан — ref_on True, kwargs ядра {ref_of: contract_ref.ref_of}, строка «вкл
    — …» дословно, таблица после старта ядра."""
    cr = _cr()
    assert S.F_CONTRACT_REF == F_REF == X.F_CONTRACT_REF and S.F_CONTRACT_REF not in S.FLAGS
    w = RefWorld(ref=False)
    ad = reader(w, ref=None)
    for environ in ({}, {F_REF: "0"}, {F_REF: ""}, {F_REF: "да"}, {F_REF: "2"}):
        assert S.contract_ref_of(environ, True, ad) == (None, None, None), environ
    assert ad.ref_on is False
    for ok in (False, None):
        got = S.contract_ref_of({F_REF: "1"}, ok, ad)
        assert got == (False, None, W_REF_NOT), got
        assert ad.ref_on is False
    ad2 = reader(w, ref=None)
    saved = sys.modules.get(NEW_MODULE)
    sys.modules[NEW_MODULE] = None                                   # «import contract_ref» упадёт
    try:
        got = S.contract_ref_of({F_REF: "1"}, True, ad2)
    finally:
        if saved is not None:
            sys.modules[NEW_MODULE] = saved
        else:
            sys.modules.pop(NEW_MODULE, None)
    assert got[0] is False and got[1] is None and got[2].startswith(W_REF_MOD.split("(%s)")[0] + "(") \
        and got[2].endswith(")"), got
    assert ad2.ref_on is not True
    for raw in ("1", "true", "YES", " on "):
        ad3 = reader(w, ref=None)
        got = S.contract_ref_of({F_REF: raw}, True, ad3)
        assert got == (True, {"ref_of": cr.ref_of}, W_REF_ON), (raw, got)
        assert ad3.ref_on is True
    # ── служба целиком ──────────────────────────────────────────────────────────────────────────────────────
    core, lines, m, env = svc(dict(SVC_ON, WA_AGENT_SIGNED_CARD="1", WA_AGENT_CONTRACT_STATE="1", **{F_REF: "1"}))
    assert [ln for ln in lines if F_REF in ln] == [LINE_REF % W_REF_ON], [ln for ln in lines if F_REF in ln]
    assert core.cstate and core.ref_of is cr.ref_of and m.ref_on is True, (core.cstate, core.ref_of)
    assert "contract_versions" in tables(env["agent_db"]), tables(env["agent_db"])
    for environ in (dict(SVC_ON, WA_AGENT_SIGNED_CARD="1", **{F_REF: "1"}),
                    dict(SVC_ON, WA_AGENT_CONTRACT_STATE="1", **{F_REF: "1"})):
        core, lines, m, env = svc(environ)
        assert [ln for ln in lines if F_REF in ln] == [LINE_REF % W_REF_NOT], (environ, lines[-6:])
        assert getattr(core, "ref_of", None) is None and m.ref_on is False, environ
        assert "contract_versions" not in tables(env["agent_db"]), environ
    core, lines, m, env = svc(dict(SVC_ON, WA_AGENT_SIGNED_CARD="1", WA_AGENT_CONTRACT_STATE="1"))
    assert core.cstate and not [ln for ln in lines if F_REF in ln or "сверка версий" in ln], lines
    assert getattr(core, "ref_of", None) is None and m.ref_on is False
    assert "contract_versions" not in tables(env["agent_db"])


def _probe_ref_off():
    """Отдельный процесс: служба БЕЗ WA_AGENT_CONTRACT_REF (карточка подписи и состояние договора ВКЛ), проход подписи и
    блок модели прежнего пути → печать: строки, ядро, таблица, модули."""
    out = {}
    try:
        core, lines, model, env = svc(dict(SVC_ON, WA_AGENT_SIGNED_CARD="1", WA_AGENT_CONTRACT_STATE="1"))
        out["lines"] = [ln for ln in lines if F_REF in ln or "сверка версий" in ln]
        out["cstate"] = bool(getattr(core, "cstate", False))
        out["core_ref"] = getattr(core, "ref_of", None) is not None
        out["table"] = "contract_versions" in tables(env["agent_db"])
        out["model_ref_on"] = bool(getattr(model, "ref_on", False))
        w = RefWorld(ref=False, rows=live_rows_ref())
        _did, t = card(w)
        w.tick(t + GAP)
        out["vline"] = vline(w, t + GAP + 60, ref=None)
        out["world_table"] = "contract_versions" in tables(w.dbpath)
        out["mods"] = sorted(m for m in (NEW_MODULE,) if m in sys.modules)
    except BaseException as e:                                       # noqa: BLE001 — назовёт родитель
        out["__crash__"] = "%s: %s" % (type(e).__name__, str(e)[:800])
    sys.stdout.write(PROBE_MARK + json.dumps(out) + "\n")
    sys.stdout.flush()
    return 0


def test_a05_flag_off_process_has_no_new_module():
    """A1 (в): отдельный процесс, служба без WA_AGENT_CONTRACT_REF: contract_ref нет в sys.modules, строки с именем флага
    нет, ядро без ref_of, таблицы нет, строка версии блока прежняя."""
    p = subprocess.run([sys.executable, os.path.abspath(__file__), PROBE_ARG], cwd=ROOT, capture_output=True,
                       timeout=300, env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    text = p.stdout.decode("utf-8", "replace")
    got = [ln for ln in text.splitlines() if ln.startswith(PROBE_MARK)]
    assert p.returncode == 0 and got, (p.returncode, text[-800:], p.stderr.decode("utf-8", "replace")[-1500:])
    r = json.loads(got[-1][len(PROBE_MARK):])
    assert "__crash__" not in r, r
    assert r["lines"] == [] and r["cstate"] is True and r["core_ref"] is False, r
    assert r["table"] is False and r["world_table"] is False and r["model_ref_on"] is False, r
    assert r["vline"] == "• версия: подписан 14.10 19:04 · doc %s · карточка подписи" % TAIL[36], r
    assert r["mods"] == [], r


def test_a06_pins_import_locks_and_signatures():
    """A1 (г): закреплённые файлы и прежние наборы — блобы 556e744; блок инструментов прежний; замки импортов
    wa_agent_attach (весь файл) и wa_contract_state; новый параметр ядра — ровно ref_of (без «rental»); make_model и
    build_followup прежние; contract_ref не импортируется на уровне модуля нигде в процессах."""
    for name, sha in PINS.items():
        assert _blob_ok(os.path.join(ROOT, name), sha), name
    assert hashlib.sha256(T.TOOLS_BLOCK.encode("utf-8")).hexdigest() == TOOLS_BLOCK_SHA
    assert _imports(_tree(X.__file__)) == ATTACH_IMPORTS, _imports(_tree(X.__file__))
    tree = _tree(CS.__file__)
    assert _imports(tree) <= {"re", "datetime"}, _imports(tree)
    bad = {"open", "exec", "eval", "__import__", "input", "os", "sys", "socket", "sqlite3", "subprocess", "time"}
    used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert not used & bad, used & bad
    par = inspect.signature(X.AttachCore.__init__).parameters
    kwonly = {n for n, p in par.items() if p.kind == p.KEYWORD_ONLY}
    assert kwonly == PROD_ATTACH_KW | {"ref_of"}, kwonly ^ (PROD_ATTACH_KW | {"ref_of"})
    assert par["ref_of"].default is None and par["cstate"].default is False
    assert not [n for n in kwonly - PROD_ATTACH_KW if "rental" in n]
    assert list(inspect.signature(S.make_model).parameters) == PROD_MAKE_MODEL
    assert inspect.signature(S.make_model).parameters["cstate"].default is False
    assert "build_followup" not in vars(C.ContractStateAdapter)
    assert "ref" in inspect.signature(C.read_facts).parameters
    assert inspect.signature(C.read_facts).parameters["ref"].default is False
    assert callable(S.contract_ref_of)
    for name in ("wa_agent_attach.py", "wa_agent_cstate.py", "wa_contract_state.py", "wa_agent_svc.py", "splinter.py",
                 "bot.py", "wa_agent.py", "wa_agent_model.py", "wa_agent_tools.py"):
        assert NEW_MODULE not in _module_level_imports(_tree(os.path.join(ROOT, name))), name
    for name in ("wa_agent_attach.py", "wa_contract_state.py"):           # замки импортов §2.3
        assert NEW_MODULE not in _imports(_tree(os.path.join(ROOT, name))), name


def test_a07_snapshot_dedup_columns_no_pii():
    """A3: проход на живых строках → итог current, 36 current, 34 и 35 superseded; колонки ровно §4.1, ключ (number,
    doc_id, row); в значениях нет имени, телефона, ника и байка; второй такой же проход — строк столько же, read_at
    итога и строк новый."""
    w = RefWorld(rows=live_rows_ref())
    _did, t1 = card(w)
    cols = w.q("PRAGMA table_info(contract_versions)")
    assert {c[1] for c in cols} == V_COLS, {c[1] for c in cols} ^ V_COLS
    assert [c[1] for c in sorted((c for c in cols if c[5]), key=lambda c: c[5])] == ["number", "doc_id", "row"]
    head = snap_head(w)
    assert head[0] == t1 and head[1:7] == ("current", "read", None, None, None, None) and head[7] == "B6334", head
    want = [(DOCS[36], 36, "current", "ПОДПИСАН", 1, SA36, "PDF36"),
            (DOCS[35], 35, "superseded", "ОТОЗВАН", 0, SA35, "P35"),
            (DOCS[34], 34, "superseded", "ОТОЗВАН", 0, SA34, "P34")]
    assert snap_items(w) == want, snap_items(w)
    rows = snap_all(w)
    assert len(rows) == 4 and all(r[0] == NUM for r in rows), rows
    for r in rows:
        if r[1]:
            assert r[3] == t1 and r[4] == "current" and r[10] == "B6334" and r[11] is None, r
        text = repr(r[1:])
        for bad in ("Иван", "999 996", NUM, "NINJA", "PHUKET", "+7"):
            assert bad not in text, (bad, r)
    n = len(w.registry.calls)
    t2 = t1 + GAP
    w.tick(t2)
    assert len(w.registry.calls) == n + 1, "второй проход читает реестр"
    rows2 = snap_all(w)
    assert len(rows2) == len(rows), (rows, rows2)
    assert snap_head(w)[0] == t2 and snap_items(w) == want, (snap_head(w), snap_items(w))
    assert all(r[3] == t2 for r in rows2), rows2


def test_a08_registry_unread_is_unknown_never_no_contract():
    """A4: дверь бросает TimeoutError или отдаёт card_deadline → итог unknown, строк с этим read_at нет; карточки,
    ожидание и черновики — как без флага; строка версии «не прочитан — статус неизвестен», без «НЕ текущая» и «нет».
    Близнец: следующее чтение ок → «действует»."""
    for mode in ("timeout", "deadline"):
        runs = {}
        for ref in (True, False):
            w = RefWorld(ref=ref, rows=live_rows_ref())
            _did, t1 = card(w)
            if mode == "timeout":
                w.registry.fail = T.last9(NUM)
            else:
                w.registry.deadline = 1
            t2 = t1 + GAP
            n = len(w.registry.calls)
            w.tick(t2)
            assert len(w.registry.calls) == n + 1, (mode, w.registry.calls)
            runs[ref] = (w, t2)
        w, t2 = runs[True]
        w0, _t = runs[False]
        assert dump_wo(w.dbpath) == dump_wo(w0.dbpath), (mode, "карточки и ожидание — как без флага")
        assert w.lines == w0.lines, (mode, [x for x in w.lines if x not in w0.lines])
        head = snap_head(w)
        assert head[0] == t2 and head[1] == "unknown" and head[2] == "read", (mode, head)
        assert str(head[8] or "").startswith("реестр не прочитан") and len(head[8]) <= 200, (mode, head)
        assert ("TimeoutError" if mode == "timeout" else "card_deadline") in head[8], (mode, head)
        assert snap_items(w) == [], (mode, "строк с read_at неразобранного чтения нет")
        b = block(w, t2 + 60)
        vl = line(b, "версия")
        assert vl == "• версия: подписан 14.10 19:04 · doc %s · реестр %s: не прочитан — статус неизвестен" % (
            TAIL[36], hm(t2)), (mode, vl)
        assert "НЕ текущая" not in b and "подписанного в сроке аренды нет" not in b, (mode, b)
        clean_block(b)
        w.registry.fail, w.registry.deadline = None, 0
        t3 = t2 + GAP
        w.tick(t3)
        assert snap_head(w)[:2] == (t3, "current"), (mode, snap_head(w))
        assert vline(w, t3 + 60) == "• версия: подписан 14.10 19:04 · doc %s · реестр %s: действует" % (
            TAIL[36], hm(t3)), (mode, vline(w, t3 + 60))


def test_a09_snapshot_older_than_version_keeps_old_line():
    """A6: снимок старше `decided_at` версии → строка версии РАВНА прежней CSTATE-строке (с источником); снимок не старше
    (в том числе в ту же секунду) → форма §4.3-A."""
    w = RefWorld(rows=[rrow(34, "ПОДПИСАН", SA34, "P34")])
    w.pdfs.files["P34"] = (34, PDF34)
    _d34, t1 = card(w, T34 + 60, T34 + 600)
    w.registry.revoke(34)
    w.registry.rows.append(rrow(36, "ОТПРАВЛЕН"))
    t2 = t1 + GAP
    w.tick(t2)
    fresh = ("• версия: подписан 14.10 17:47 · doc %s · реестр %s: ОТОЗВАН — НЕ текущая; новая doc %s ждёт подписи "
             "(ОТПРАВЛЕН)" % (TAIL[34], hm(t2), TAIL[36]))
    old = "• версия: подписан 14.10 17:47 · doc %s · карточка подписи" % TAIL[34]
    assert vline(w, t2 + 60) == fresh, vline(w, t2 + 60)
    assert vline(w, t2 + 60, ref=False) == old
    w.x("UPDATE signed_cards SET ts=? WHERE doc_id=?", (t2 + 30, DOCS[34]))       # версию решили ПОСЛЕ снимка
    assert vline(w, t2 + 90) == old, vline(w, t2 + 90)
    w.x("UPDATE signed_cards SET ts=? WHERE doc_id=?", (t2, DOCS[34]))            # та же секунда — снимок применим
    assert vline(w, t2 + 90) == fresh, vline(w, t2 + 90)


def test_a10_resigned_same_doc_is_new_version():
    """A7 + A12: переподпись того же doc_id (новые signed_at и pdf_id). (1) PDF новой версии ещё не читается — карточки
    нет, блок: «переподписан … — эта НЕ текущая», без указателя; старая карточка при нажатии устарела, ничего не ушло.
    (2) близнец: PDF есть — вторая карточка с новым ключом, первая снята; та же версия во втором проходе карточки не
    дала; снимок — одна строка на (doc_id, row); итог карточек равен прогону без флага; уходит PDF новой версии."""
    w = RefWorld(rows=live_rows_ref())
    d36, _t1 = card(w)
    set_row(w, 36, signed_at=SA36B, pdf_id="PDF36B")
    t2 = SC.phuket(2026, 10, 14, 20, 40)
    w.tick(t2)
    assert [r[0] for r in w.signed_drafts()] == [d36] and len(w.versions()) == 1, (w.signed_drafts(), w.versions())
    assert snap_head(w)[:2] == (t2, "current"), snap_head(w)
    assert snap_items(w)[0] == (DOCS[36], 36, "current", "ПОДПИСАН", 1, SA36B, "PDF36B"), snap_items(w)
    vl = vline(w, t2 + 60)
    assert vl == ("• версия: подписан 14.10 19:04 · doc %s · реестр %s: переподписан 14.10 20:30 — эта НЕ текущая"
                  % (TAIL[36], hm(t2))), vl
    out = w.core.press(d36, 1, A.ACT_SEND, STAFF, t2 + 120)
    assert out.get("state") == A.STALE and not out.get("ok"), out
    assert w.door.sends == [] and w.door.media == [], "старая версия клиенту не уходит"

    def run(ref):
        v = RefWorld(ref=ref, rows=live_rows_ref())
        v.pdfs.files["PDF36B"] = (36, PDF36B)
        first, t1 = card(v)
        v.tick(t1 + GAP)                                         # та же версия ещё раз — второй карточки нет
        assert [r[0] for r in v.signed_drafts()] == [first] and v.tg.cards == [first], v.signed_drafts()
        set_row(v, 36, signed_at=SA36B, pdf_id="PDF36B")
        v.tick(t2)
        return v, first
    w2, first = run(True)
    w3, _f = run(False)
    sd = w2.signed_drafts()
    assert len(sd) == 2 and sd[1][1] == A.PENDING and state_of(w2, first) == A.SUPERSEDED, sd
    second = sd[1][0]
    assert [v[1:4] for v in w2.versions()] == [(DOCS[36], SA36, "PDF36"), (DOCS[36], SA36B, "PDF36B")], w2.versions()
    assert w2.tg.cards == [first, second], w2.tg.cards
    assert (w2.versions(), w2.signed_drafts(), w2.tg.cards) == (w3.versions(), w3.signed_drafts(), w3.tg.cards)
    assert len(snap_all(w2)) == 4, ("строк не больше различных (doc_id, row)", snap_all(w2))
    assert snap_items(w2)[0] == (DOCS[36], 36, "current", "ПОДПИСАН", 1, SA36B, "PDF36B"), snap_items(w2)
    vl = vline(w2, t2 + 60)
    assert vl == "• версия: подписан 14.10 20:30 · doc %s · реестр %s: действует" % (TAIL[36], hm(t2)), vl
    assert "19:04" not in vl
    out = w2.core.press(second, 1, A.ACT_SEND, STAFF, t2 + 120)
    assert out.get("ok") and w2.door.media == [(NUM, "document", "application/pdf", "contract_36.pdf", SHA36B)], (
        out, w2.door.media)


def test_a11_no_local_version_lines():
    """A8 (форма B): версии в базе нет. Снимок pending → «… · реестр ЧЧ:ММ: doc …36 ждёт подписи (ОТПРАВЛЕН)»; тот же
    стенд без флага и адаптер с ref_on=False → прежняя строка. Чтение не удалось → «не прочитан — неизвестно, а не
    «договора нет»». Единственная подписанная строка чужая (байк) → «подписанного в сроке аренды нет», указателя
    «подписан doc» на неё нет."""
    t = T_SIGN + 600
    for ref in (True, False):
        w = RefWorld(ref=ref, rows=[rrow(34, "ОТОЗВАН", SA34, "P34"), rrow(36, "ОТПРАВЛЕН")])
        w.put(T_SIGN + 60, CLAIM)
        w.tick(t)
        assert w.signed_drafts() == [] and w.versions() == [], (w.signed_drafts(), w.versions())
        if ref:
            assert snap_head(w)[:2] == (t, "pending"), snap_head(w)
            b = block(w, t + 60)
            assert line(b, "версия") == "%s · реестр %s: doc %s ждёт подписи (ОТПРАВЛЕН)" % (B_HEAD, hm(t), TAIL[36]), b
            clean_block(b)
            assert vline(w, t + 60, ref=False) == B_HEAD
        else:
            assert "contract_versions" not in tables(w.dbpath)
            assert vline(w, t + 60, ref=None) == B_HEAD
    w = RefWorld(rows=live_rows_ref())
    w.registry.fail = T.last9(NUM)
    w.put(T_SIGN + 60, CLAIM)
    w.tick(t)
    assert w.signed_drafts() == [] and snap_head(w)[:2] == (t, "unknown"), snap_head(w)
    b = block(w, t + 60)
    assert line(b, "версия") == "%s · реестр %s: не прочитан — неизвестно, а не «договора нет»" % (B_HEAD, hm(t)), b
    assert "подписанного в сроке аренды нет" not in b, b
    clean_block(b)
    w = RefWorld(rows=[rrow(36, "ПОДПИСАН", SA36, "PDF36", bike=OTHER_BIKE)])
    w.put(T_SIGN + 60, CLAIM)
    w.tick(t)
    assert w.signed_drafts() == [] and snap_head(w)[:2] == (t, "none"), snap_head(w)
    assert [(i[1], i[2]) for i in snap_items(w)] == [(36, "foreign")], snap_items(w)
    vl = vline(w, t + 60)
    assert vl == "%s · реестр %s: подписанного в сроке аренды нет" % (B_HEAD, hm(t)), vl
    assert "подписан doc" not in vl and TAIL[36] not in vl


def test_a12_old_pdf_never_sent_after_new_version():
    """A9: ждущая карточка с PDF 34; реестр стал 34 ОТОЗВАН + 36 ПОДПИСАН → «Отправить» → stale по основанию, дверь
    WhatsApp не звана (ни текста, ни PDF 34); проход подписи даёт карточку 36 с sha PDF36; сверка модели (contract)
    принимает PDF36. Близнец: реестр прежний (34 действует) → текст и PDF 34 уходят."""
    w = RefWorld(rows=[rrow(34, "ПОДПИСАН", SA34, "P34")])
    w.pdfs.files["P34"] = (34, PDF34)
    d34, t1 = card(w, T34 + 60, T34 + 600)
    w.registry.revoke(34)
    w.registry.rows.append(rrow(36, "ПОДПИСАН", SA36, "PDF36"))
    out = w.core.press(d34, 1, A.ACT_SEND, STAFF, t1 + 120)
    assert out.get("state") == A.STALE and not out.get("ok"), out
    assert str(out.get("words") or "").startswith("устарело: основание PDF не подтверждено реестром"), out
    assert w.door.sends == [] and w.door.media == [], (w.door.sends, w.door.media)
    t2 = T_SIGN + 600
    w.tick(t2)
    sd = [r for r in w.signed_drafts() if r[0] != d34]
    assert len(sd) == 1 and w.attach(sd[0][0])[3] == SHA36 and w.attach(sd[0][0])[0] == "PDF36", sd
    assert vline(w, t2 + 60) == "• версия: подписан 14.10 19:04 · doc %s · реестр %s: действует" % (TAIL[36], hm(t2))
    rent = T.rental_result({"ok": True, "rows": [SC.book_row()]}, t2)
    raw = w.registry(phone=NUM, date_from="2026-10-14", date_to="2026-10-17")
    res = T.contract_result(raw, t2, number=NUM, rental=rent)
    assert res["outcome"] == T.FACT and res["facts"][0]["pdf_id"] == "PDF36" and res["facts"][0]["row"] == 36, res
    # близнец: реестр не менялся — 34 действует, уходит
    v = RefWorld(rows=[rrow(34, "ПОДПИСАН", SA34, "P34")])
    v.pdfs.files["P34"] = (34, PDF34)
    e34, s1 = card(v, T34 + 60, T34 + 600)
    out = v.core.press(e34, 1, A.ACT_SEND, STAFF, s1 + 120)
    assert out.get("ok") and out.get("parts") == {"text": A.SENT, "pdf": A.SENT}, out
    assert len(v.door.sends) == 1 and v.door.media == [(NUM, "document", "application/pdf", "contract_34.pdf",
                                                        SHA34)], v.door.media


def test_a13_model_text_kept_when_pdf_refused():
    """A10: ответ модели сохраняется при флаге ВКЛ. Сверка без PDF (35 и 36 подписаны) → attach.file_id NULL с
    причиной, «Отправить» шлёт текст, части PDF нет. PDF отказан ПОСЛЕ текста (sha другой / contract_pdf не ок) → текст
    ушёл, PDF not_sent с причиной. Близнец: годный PDF → обе части ушли."""
    text = "Здравствуйте! Байк можно забрать завтра с 10:00."
    w = RefWorld(rows=[rrow(35, "ПОДПИСАН", SA35, "P35"), rrow(36, "ПОДПИСАН", SA36, "PDF36")],
                 tools_out=tools_ambiguous(), text=text)
    w.put(T_SIGN + 60, "Когда можно забрать байк?")
    w.tick(T_SIGN + 600)
    assert w.q("SELECT id, state, kind, text FROM drafts") == [(1, A.PENDING, None, text)], w.q(
        "SELECT id, state, kind, text FROM drafts")
    a = w.attach(1)
    assert a[0] is None and "ambiguous" in (a[11] or ""), a
    assert w.signed_drafts() == [] and snap_head(w)[1] == "ambiguous", snap_head(w)
    out = w.core.press(1, 1, A.ACT_SEND, STAFF, T_SIGN + 700)
    assert out.get("ok") and out.get("words") == "текст: ушёл", out
    assert w.door.sends == [(NUM, text)] and w.door.media == [], (w.door.sends, w.door.media)
    assert w.q("SELECT COUNT(*) FROM pdf_parts WHERE draft_id=1") == [(0,)]
    for spoil, why in (("sha", "sha256"), ("refused", "not_in_registry"), (None, None)):
        v = RefWorld(rows=live_rows_ref(), tools_out=tools_pdf(), text=text)
        v.put(T_SIGN + 60, "Когда можно забрать байк?")
        v.tick(T_SIGN + 600)
        assert v.attach(1)[0] == "PDF36" and v.signed_drafts() == [], (v.attach(1), v.signed_drafts())
        if spoil == "sha":
            v.pdfs.files["PDF36"] = (36, PDF_OTHER)
        elif spoil == "refused":
            v.pdfs.files = {}
        out = v.core.press(1, 1, A.ACT_SEND, STAFF, T_SIGN + 700)
        assert v.door.sends == [(NUM, text)], (spoil, v.door.sends)
        if spoil is None:
            assert out.get("ok") and out.get("parts") == {"text": A.SENT, "pdf": A.SENT}, out
            assert v.door.media == [(NUM, "document", "application/pdf", "contract_36.pdf", SHA36)], v.door.media
        else:
            assert out.get("parts") == {"text": A.SENT, "pdf": A.NOT_SENT}, (spoil, out)
            assert v.door.media == [], (spoil, v.door.media)
            st = v.q("SELECT state, reason FROM pdf_parts WHERE draft_id=1")[0]
            assert st[0] == A.NOT_SENT and why in (st[1] or ""), (spoil, st)
            assert v.q("SELECT state FROM drafts WHERE id=1") == [(A.SENT,)], "текст ответа модели ушёл"


def test_a14_foreign_row_never_named_current():
    """A11: единственная подписанная строка снимка — другой аренды (байк 5580): локальная версия в этой строке →
    «другой аренды — НЕ текущая; подписанного в сроке аренды нет», указателя «текущая» нет. Близнец: байк снова 6334 →
    «действует»."""
    w = RefWorld(rows=live_rows_ref())
    _d36, t1 = card(w)
    set_row(w, 36, bike=OTHER_BIKE)
    t2 = t1 + GAP
    w.tick(t2)
    assert len(w.signed_drafts()) == 1 and snap_head(w)[:2] == (t2, "none"), snap_head(w)
    assert [(i[1], i[2]) for i in snap_items(w)] == [(36, "foreign"), (35, "superseded"), (34, "superseded")]
    vl = vline(w, t2 + 60)
    assert vl == ("• версия: подписан 14.10 19:04 · doc %s · реестр %s: другой аренды — НЕ текущая; подписанного в "
                  "сроке аренды нет" % (TAIL[36], hm(t2))), vl
    assert "текущая doc" not in vl and "действует" not in vl
    set_row(w, 36, bike=SC.BIKE)
    t3 = t2 + GAP
    w.tick(t3)
    assert vline(w, t3 + 60) == "• версия: подписан 14.10 19:04 · doc %s · реестр %s: действует" % (TAIL[36], hm(t3))


def test_a15_no_make_contract_on_search_paths():
    """A13: в модулях стороны wa-agent и в contract_ref нет Name/Attribute make_contract, save_passport, ocr_passport;
    импорты contract_ref ровно re и wa_agent_tools."""
    cr = _cr()
    for path in (X.__file__, C.__file__, CS.__file__, S.__file__, cr.__file__):
        names = _names(_tree(path))
        assert not names & SEARCH_FORBIDDEN, (os.path.basename(path), names & SEARCH_FORBIDDEN)
    assert _imports(_tree(cr.__file__)) == {"re", "wa_agent_tools"}, _imports(_tree(cr.__file__))


class _FailingDb:
    """Соединение ядра, у которого отказывает ТОЛЬКО запись в contract_versions (диск / блокировка)."""

    def __init__(self, inner):
        self._inner, self.hits = inner, 0

    def _bad(self, sql):
        s = str(sql).lstrip().upper()
        return "CONTRACT_VERSIONS" in s and (s.startswith("INSERT") or s.startswith("REPLACE"))

    def execute(self, sql, *args):
        if self._bad(sql):
            self.hits += 1
            raise sqlite3.OperationalError("стенд: запись снимка отказала")
        return self._inner.execute(sql, *args)

    def executemany(self, sql, *args):
        if self._bad(sql):
            self.hits += 1
            raise sqlite3.OperationalError("стенд: запись снимка отказала")
        return self._inner.executemany(sql, *args)

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def __enter__(self):
        self._inner.__enter__()
        return self

    def __exit__(self, *exc):
        return self._inner.__exit__(*exc)


def test_a16_snapshot_write_failure_one_line_pass_unchanged():
    """A14: запись снимка отказала → ОДНА строка журнала §4.1 дословно (без номера), проход и карточка — как без флага.
    Близнец: без сбоя строки нет, снимок записан."""
    w = RefWorld(rows=live_rows_ref())
    w.core.db = _FailingDb(w.core.db)
    did, _t = card(w)
    w0 = RefWorld(ref=False, rows=live_rows_ref())
    did0, _t0 = card(w0)
    said = [ln for ln in w.lines if ln.startswith("сверка версий договора:")]
    assert said == [W_WRITE_FAIL % "OperationalError"], said
    assert NUM not in said[0] and NUM[-4:] not in said[0] and w.core.db.hits >= 1
    assert (did, w.versions(), w.signed_drafts(), w.registry.calls) == (did0, w0.versions(), w0.signed_drafts(),
                                                                       w0.registry.calls)
    assert [x for x in w.lines if not x.startswith("сверка версий договора:")] == w0.lines
    assert w.q("SELECT COUNT(*) FROM contract_versions") == [(0,)]
    v = RefWorld(rows=live_rows_ref())
    card(v)
    assert not [ln for ln in v.lines if ln.startswith("сверка версий договора")] and len(snap_all(v)) == 4


def _ri(row, role, status, signed_at="", pdf_id="", doc=None):
    return {"doc_id": DOCS[row] if doc is None else doc, "row": row, "role": role, "status": status,
            "signed": status == "ПОДПИСАН", "signed_at": signed_at, "pdf_id": pdf_id}


def test_a17_render_version_line_table_43():
    """§4.3 дословно (render на фактах формы §4.2): форма A — каждая строка таблицы V и P; форма B — каждая строка Q;
    снимок неприменим (старше версии · None · unknown · версия неизвестна · decided_at не число) — строка прежняя."""
    now = T_SIGN + 3600                                          # 14.10 20:04
    t = now - 60                                                 # чтение реестра 20:03
    v = {"signed_at": SA34, "doc": DOCS[34], "file_id": "P34", "sha": "a" * 64, "draft_id": 1, "src": "card",
         "date_to": "2026-10-17", "decided_at": now - 600}

    def ref(outcome, items, local_row=34, read_at=t):
        return {"read_at": read_at, "outcome": outcome, "reason": "", "items": items, "local_row": local_row}

    def vl(version, rf, at=now, **more):
        f = {"read_at": at, "topic": True, "records": 1, "unread": [], "version": version, "pdf": None, "wa": None,
             "human_doc": None, "ask": None, "expect": None}
        if rf != "absent":
            f["ref"] = rf
        f.update(more)
        b = CS.render(f, at)
        out = line(b, "версия")
        assert len(out) <= CS.LINE_MAX + 2 and "2026" not in b and "стр." not in b and DOCS[34] not in b, b
        return out
    a = "• версия: подписан 14.10 17:47 · doc %s · реестр 20:03: " % TAIL[34]
    s34 = _ri(34, "superseded", "ОТОЗВАН", SA34, "P34")
    c36 = _ri(36, "current", "ПОДПИСАН", SA36, "PDF36")
    cases = [
        (ref("current", [_ri(34, "current", "ПОДПИСАН", SA34, "P34")]), "действует"),
        (ref("current", [c36]), "этой строки в чтении нет — статус неизвестен"),
        (ref("none", [_ri(40, "other", "ОШИБКА", doc=DOCS[34]), s34], local_row=None),
         "строка не однозначна — статус неизвестен"),
        (ref("none", [_ri(40, "superseded", "ОТОЗВАН", SA34, "P34", doc=DOCS[34])]),
         "строка не однозначна — статус неизвестен"),
        (ref("none", [_ri(34, "foreign", "ПОДПИСАН", SA34, "P34")]),
         "другой аренды — НЕ текущая; подписанного в сроке аренды нет"),
        (ref("incomplete", [_ri(34, "unchecked", "ПОДПИСАН", SA34, "P34")]), "привязка не сверена — статус неизвестен"),
        (ref("current", [c36, s34]), "ОТОЗВАН — НЕ текущая; текущая doc %s от 14.10 19:04" % TAIL[36]),
        (ref("current", [_ri(34, "current", "ПОДПИСАН", "2026-10-14 19:30", "P34B")]),
         "переподписан 14.10 19:30 — эта НЕ текущая"),
        (ref("ambiguous", [_ri(36, "signed", "ПОДПИСАН", SA36, "PDF36"), _ri(34, "signed", "ПОДПИСАН", SA34, "P34")]),
         "подписанных несколько — выбор за человеком"),
        (ref("incomplete", [_ri(34, "signed", "ПОДПИСАН", SA34, "P34")]), "прочитан не целиком — выбор за человеком"),
        (ref("unknown", []), "не прочитан — статус неизвестен"),
        (ref("pending", [_ri(37, "pending", "ОТПРАВЛЕН"), _ri(36, "pending", "НОВЫЙ"), s34]),
         "ОТОЗВАН — НЕ текущая; новая doc %s ждёт подписи (ОТПРАВЛЕН) и ещё 1" % TAIL[37]),
        (ref("none", [s34]), "ОТОЗВАН — НЕ текущая; подписанного в сроке аренды нет"),
        (ref("ambiguous", [_ri(36, "signed", "ПОДПИСАН", SA36, "PDF36"), _ri(35, "signed", "ПОДПИСАН", SA35, "P35"),
                           s34]), "ОТОЗВАН — НЕ текущая; подписанных несколько — выбор за человеком"),
        (ref("incomplete", [s34]), "ОТОЗВАН — НЕ текущая; прочитан не целиком — выбор за человеком"),
        (ref("none", [_ri(34, "superseded", "ОТКЛОНЁН", SA34, "P34")]),
         "ОТКЛОНЁН — НЕ текущая; подписанного в сроке аренды нет"),
    ]
    for rf, tail in cases:
        got = vl(v, rf)
        assert got == a + tail, (got, a + tail)
        assert "карточка подписи" not in got, "источник версии в форме A не пишется"
    # давность (note) стоит между V и P
    later = now + 2 * 86400
    got = vl(dict(v), ref("current", [c36, s34], read_at=later - 60), at=later)
    assert got == ("• версия: подписан 14.10 17:47 · doc %s · реестр 20:03: ОТОЗВАН — НЕ текущая · 2 сут назад; "
                   "текущая doc %s от 14.10 19:04" % (TAIL[34], TAIL[36])), got
    # форма B: версии в базе нет
    b = B_HEAD + " · реестр 20:03: "
    for rf, tail in (
            (ref("current", [c36, s34]), "подписан doc %s от 14.10 19:04" % TAIL[36]),
            (ref("pending", [_ri(37, "pending", "ОТПРАВЛЕН"), _ri(36, "pending", "НОВЫЙ")]),
             "doc %s ждёт подписи (ОТПРАВЛЕН) и ещё 1" % TAIL[37]),
            (ref("pending", [_ri(36, "pending", "НОВЫЙ")]), "doc %s не отправлена на подпись (НОВЫЙ)" % TAIL[36]),
            (ref("ambiguous", [_ri(36, "signed", "ПОДПИСАН", SA36, "PDF36")]),
             "подписанных несколько — выбор за человеком"),
            (ref("incomplete", []), "прочитан не целиком — выбор за человеком"),
            (ref("none", [_ri(36, "foreign", "ПОДПИСАН", SA36, "PDF36")]), "подписанного в сроке аренды нет"),
            (ref("unknown", []), "не прочитан — неизвестно, а не «договора нет»")):
        got = vl(None, rf)
        assert got == b + tail, (got, b + tail)
    # снимок неприменим — строка прежняя байт-в-байт
    old = "• версия: подписан 14.10 17:47 · doc %s · карточка подписи" % TAIL[34]
    for version, rf in ((v, ref("current", [c36, s34], read_at=now - 900)),    # снимок старше решения версии
                        (v, None), (v, "absent"),
                        (v, {"unknown": "сверка с реестром не прочитана: OperationalError"}),
                        (dict(v, decided_at=None), ref("current", [c36, s34]))):
        assert vl(version, rf) == old, (rf, vl(version, rf))
    for rf in (None, "absent", {"unknown": "сверка с реестром не прочитана: OperationalError"}):
        assert vl(None, rf) == B_HEAD, rf
    assert vl({"unknown": "нет таблиц: signed_cards"}, ref("current", [c36])) == \
        "• версия: неизвестно (нет таблиц: signed_cards)"


def test_a18_ref_needs_cstate_and_callable():
    """§4.1: ref_of засчитывается ТОЛЬКО при засчитанном cstate и вызываемым: иначе core.ref_of None, таблицы нет, проход
    прежний. Близнец: cstate и ref_of — таблица и снимок есть."""
    for kw in (dict(ref=True, cstate=False), dict(ref="не функция", cstate=True)):
        w = RefWorld(rows=live_rows_ref(), **kw)
        assert getattr(w.core, "ref_of", "нет атрибута") is None, kw
        card(w)
        assert "contract_versions" not in tables(w.dbpath), kw
    w = RefWorld(rows=live_rows_ref())
    assert w.core.ref_of is _cr().ref_of
    card(w)
    assert "contract_versions" in tables(w.dbpath) and len(snap_all(w)) == 4


# ══ G · сторона splinter (генератор) — дочерним процессом этого же файла ══════════════════════════════════════════

GEN_STATE_ENV = (("HINT_DEDUP_STATE", "hint_dedup_state.json"), ("DECIDER_LIVE_STATE", "decider_live_state.json"),
                 ("WORKS_PERSIST_STATE", "works_persist_state.json"),
                 ("MILEAGE_Q_STATE", "mileage_question_state.json"), ("SVC_TOKENS_STATE", "svc_tokens.json"),
                 ("TOPIC_FEED_DIR", "topic_feed"), ("SPLINTER_ASK_STAFF_STATE", "staff_ask_state.json"),
                 ("SPLINTER_RULES_SNAP", "business_rules_snap.json"), ("WALLET_CACHE_FILE", "wallet_cache.json"),
                 ("ENQUEUE_DEDUP_FILE", "enqueue_dedup.json"), ("SPEND_LEDGER_FILE", "spend_ledger.json"))
UKAZHI = ("🐀 Splinter\nУкажи бронь: «договор <booking_key>» или «договор <Имя> <дата>», либо отправь после "
          "карточки брони.")
NOPASS = {"ok": False, "error": "no_passport", "message": "строки паспорта нет"}
OK_MAKE = {"ok": True, "name": "Договор Тест", "url": "https://docs.example.invalid/d/contractref", "flags": {}}
BASE_FAIL = "🐀 Splinter\n❌ Договор не сделан: no_passport. строки паспорта нет"
REG_PART = "\n📄 Реестр по этой брони: "
KM_NOPASS = "  📄 contract_km: бронь «%s» — no_passport"
KM_OK = "  📄 contract_km: договор брони «%s» (%s) перегенерён, km_request=None"
KM_DONE = "  📄 contract_km: обновлено договоров в день выдачи: %d"
KM_REF = "  📄 contract_km: строка CRM %s — реестр: %s"
INTAKE_REF = "  🆕 INTAKE: договор не сделан (no_passport) — реестр: %s"
_GSENT = []


class GBridge:
    """Поддельный мост splinter/bot со счётчиками ВСЕХ методов: clients (живой формат rental_case_fakes), реестр
    contract_find по байку и сроку (форма двери), make_contract / issue_write_ticket; прочее — записывается и отказывает."""

    def __init__(self, crm, items=(), make=None, find=None, crm_error=None):
        self.crm = [dict(r) for r in crm]
        self.items = list(items)
        self.make = OK_MAKE if make is None else make
        self.find, self.crm_error, self.calls = find, crm_error, []

    def _rec(self, name, kw):
        self.calls.append((name, dict(kw)))

    def n(self, name):
        return len([1 for c in self.calls if c[0] == name])

    def kw(self, name):
        return [c[1] for c in self.calls if c[0] == name]

    def others(self):
        return [c for c in self.calls if c[0] not in ("_call", "issue_write_ticket", "make_contract", "contract_find")]

    def _call(self, action, **k):
        self._rec("_call", dict(k, action=action))
        if self.crm_error is not None:
            raise self.crm_error
        if action != "clients":
            return {"ok": False, "error": "unknown_action"}
        import rental_case_fakes as F
        return F.clients_reply(self.crm, filter=k.get("filter", "all"))

    def issue_write_ticket(self):
        self._rec("issue_write_ticket", {})
        return {"ok": True, "ticket": "t-contractref"}

    def make_contract(self, **k):
        self._rec("make_contract", k)
        return dict(self.make(k) if callable(self.make) else self.make)

    def contract_find(self, **k):
        self._rec("contract_find", k)
        if isinstance(self.find, BaseException):
            raise self.find
        if isinstance(self.find, dict):
            return dict(self.find)
        bike, frm, to = str(k.get("bike") or ""), str(k.get("date_from") or ""), str(k.get("date_to") or "")
        plate = T.plate_of(bike)
        hit = [i for i in self.items if plate and T.plate_of(i["bike"]) == plate
               and (not frm or (i["contract_date"] or "") >= frm) and (not to or (i["contract_date"] or "") <= to)]
        return fresp(hit, phone_last9="", date_from=frm, date_to=to, bike=bike)

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)

        def other(*a, **k):
            self._rec(name, dict(k, _args=list(a)))
            return {"ok": False, "error": "не предмет набора"}
        return other


class _GUser:
    def __init__(self, uname, uid):
        self.username, self.id, self.is_bot = uname, uid, False


class _GMsg:
    _next = [880000]

    def __init__(self, text, chat_id, uname="turbophuket", uid=504608015):
        _GMsg._next[0] += 1
        self.message_id = _GMsg._next[0]
        self.text, self.caption, self.photo = text, None, None
        self.chat_id, self.message_thread_id = chat_id, None
        self.date = datetime.datetime.now(datetime.timezone.utc)
        self.from_user = _GUser(uname, uid)
        self.reply_to_message = None
        self.media_group_id = None


class _GCtx:
    class _B:
        username, id = "turbobaby_manager_bot", 1
    bot = _B()


class _Cap(logging.Handler):
    def __init__(self):
        logging.Handler.__init__(self, logging.INFO)
        self.msgs = []

    def emit(self, record):
        try:
            self.msgs.append(record.getMessage())
        except Exception:                                            # noqa: BLE001
            self.msgs.append(str(record.msg))


async def _rec_send(context, *, chat_id, text, message_thread_id=None, **k):
    _GSENT.append({"chat_id": chat_id, "text": text, "thread": message_thread_id})
    return types.SimpleNamespace(message_id=900000 + len(_GSENT), chat_id=chat_id, text=text)


def _eq(got, want, ctx=None):
    assert got == want, {"есть": got, "ждали": want, "контекст": ctx}


def _crm(G, row, bid, name=NAME_R, bike=BIKE_R, start=None, end="default", contacts=PHONE_R, status="Бронь"):
    import rental_case_fakes as F
    de = ("%s 10:00" % G.end) if end == "default" else (("%s 10:00" % end) if end else None)
    return F.make_row(row, status, bike, name, "%s 10:00" % (start or G.today), de, contacts=contacts,
                      booking_id=bid)


def _gitem(G, row, status, sa="", pdf=""):
    return ritem(row, status, sa, pdf, date=G.today, on=("bike",))


def _job(G, b):
    G.bot.bridge = b
    G.cap.msgs[:] = []
    asyncio.run(G.bot.scheduled_contract_km(None))
    return [m for m in G.cap.msgs if "contract_km" in m]


def _intake(G, b, text):
    del _GSENT[:]
    G.cap.msgs[:] = []
    asyncio.run(G.S._handle_intake(_GMsg(text, G.S.INTAKE_CHAT), _GCtx(), b, None))
    return [s["text"] for s in _GSENT], [m for m in G.cap.msgs if "INTAKE" in m]


def _find_kw(G, bike=BIKE_R):
    return {"bike": bike, "date_from": G.today, "date_to": G.end, "limit": 100}


def _same(got, want):
    """Те же строки журнала (новая строка реестра — одна; её место относительно прежней строки проект не задаёт)."""
    assert sorted(got) == sorted(want), {"есть": got, "ждали": want}


def _ref_line(km, row):
    head = KM_REF % (row, "")
    got = [x for x in km if x.startswith(head)]
    assert len(got) == 1, ("строка реестра по строке CRM %s — ровно одна" % row, km)
    return got[0]


def _ref_words(line_, row):
    head = KM_REF % (row, "")
    assert line_.startswith(head), (line_, head)
    return line_[len(head):]


# ── случаи генератора: сначала ВСЁ при флаге ВЫКЛ (модуль не должен появиться), потом при ВКЛ ──────────────────

def gcase_flag_rule(G):
    assert G.S.F_CONTRACT_REF_GEN == F_GEN, getattr(G.S, "F_CONTRACT_REF_GEN", None)
    os.environ.pop(F_GEN, None)
    assert G.S._rc_on(G.S.F_CONTRACT_REF_GEN) is False
    for raw, want in (("0", False), ("", False), ("да", False), ("1", True), ("true", True), ("YES", True),
                      ("on", True)):
        os.environ[F_GEN] = raw
        assert G.S._rc_on(G.S.F_CONTRACT_REF_GEN) is want, raw
    os.environ.pop(F_GEN, None)


def gcase_job_off_nopass(G):
    b = GBridge([_crm(G, 7, UUID)], items=[_gitem(G, 36, "ПОДПИСАН", SA36, "PDF36")], make=NOPASS)
    km = _job(G, b)
    _eq(b.kw("make_contract"), [{"name": NAME_R, "date_start": "%s 10:00" % G.today}], b.calls)
    _eq((b.n("contract_find"), b.n("issue_write_ticket"), b.n("_call")), (0, 1, 1), b.calls)
    _eq(km, [KM_NOPASS % NAME_R])
    _eq(b.others(), [])


def gcase_job_off_ok(G):
    tomorrow = (datetime.date.fromisoformat(G.today) + datetime.timedelta(days=1)).isoformat()
    b = GBridge([_crm(G, 7, UUID), _crm(G, 8, "b0000000-0000-4000-8000-000000000008", start=tomorrow),
                 _crm(G, 9, "", status="В аренде")])
    km = _job(G, b)
    _eq(b.kw("make_contract"), [{"name": NAME_R, "date_start": "%s 10:00" % G.today}], b.calls)
    _eq(km, [KM_OK % (NAME_R, BIKE_R), KM_DONE % 1])
    _eq(b.n("contract_find"), 0)


def gcase_intake_off_uuid(G):
    b = GBridge([_crm(G, 7, UUID)])
    replies, _logs = _intake(G, b, "договор " + UUID)
    _eq(replies, [UKAZHI])
    _eq(b.calls, [], "без флага UUID разбирается по-прежнему — make_contract не зовётся")


def gcase_intake_off_key_nopass(G):
    bk = "%s|%s|%s" % (BIKE_R, NAME_R, G.today)
    b = GBridge([_crm(G, 7, UUID)], items=[_gitem(G, 36, "ПОДПИСАН", SA36, "PDF36")], make=NOPASS)
    replies, logs = _intake(G, b, "договор " + bk)
    _eq(b.kw("make_contract"), [{"booking_key": bk, "name": None, "date_start": None}])
    _eq(replies, [BASE_FAIL])
    _eq((b.n("contract_find"), b.n("_call")), (0, 0), b.calls)
    assert not [x for x in logs if "реестр" in x], logs


def gcase_job_on_bid_ok(G):
    os.environ[F_GEN] = "1"
    b = GBridge([_crm(G, 7, UUID)])
    km = _job(G, b)
    _eq(b.kw("make_contract"), [{"booking_id": UUID}], b.calls)
    _eq((b.n("contract_find"), b.n("issue_write_ticket")), (0, 1), b.calls)
    _eq(km, [KM_OK % (NAME_R, BIKE_R), KM_DONE % 1])


def gcase_job_on_empty_bid(G):
    os.environ[F_GEN] = "1"
    b = GBridge([_crm(G, 7, "")])
    km = _job(G, b)
    _eq(b.kw("make_contract"), [{"name": NAME_R, "date_start": "%s 10:00" % G.today}], b.calls)
    _eq(b.n("contract_find"), 0)
    _eq(km, [KM_OK % (NAME_R, BIKE_R), KM_DONE % 1])


def gcase_job_on_bid_nopass(G):
    os.environ[F_GEN] = "1"
    b = GBridge([_crm(G, 7, UUID)], items=[_gitem(G, 36, "ПОДПИСАН", SA36, "PDF36")], make=NOPASS)
    km = _job(G, b)
    _eq(b.kw("make_contract"), [{"booking_id": UUID}], b.calls)
    _eq(b.kw("contract_find"), [_find_kw(G)], b.calls)
    _eq((b.n("_call"), b.n("issue_write_ticket")), (1, 1), b.calls)
    _same(km, [KM_NOPASS % NAME_R, KM_REF % (7, w_current(36, "ПОДПИСАН", SA36))])
    new = _ref_line(km, 7)
    for bad in (NAME_R, "Тест", PHONE_R, "999 000"):
        assert bad not in new, (bad, new)
    _eq(b.others(), [])


def gcase_job_on_two_bookings(G):
    os.environ[F_GEN] = "1"
    bike2 = "Honda PCX 160 4321"
    b = GBridge([_crm(G, 7, UUID), _crm(G, 9, "", name="Тест Второй", bike=bike2)],
                items=[_gitem(G, 36, "ПОДПИСАН", SA36, "PDF36")],
                make=lambda k: OK_MAKE if "booking_id" in k else NOPASS)
    km = _job(G, b)
    _eq(b.kw("make_contract"), [{"booking_id": UUID}, {"name": "Тест Второй", "date_start": "%s 10:00" % G.today}],
        b.calls)
    _eq((b.n("issue_write_ticket"), b.n("_call")), (2, 1), b.calls)
    _eq(b.kw("contract_find"), [_find_kw(G, bike2)], b.calls)
    _same(km, [KM_OK % (NAME_R, BIKE_R), KM_NOPASS % "Тест Второй", KM_REF % (9, W_NONE_HEAD + "0)"), KM_DONE % 1])
    assert km.index(KM_OK % (NAME_R, BIKE_R)) < km.index(KM_NOPASS % "Тест Второй") < km.index(KM_DONE % 1), km


def gcase_job_on_pending(G):
    os.environ[F_GEN] = "1"
    b = GBridge([_crm(G, 7, UUID)], items=[_gitem(G, 34, "ОТОЗВАН", SA34, "P34"), _gitem(G, 36, "ОТПРАВЛЕН")],
                make=NOPASS)
    km = _job(G, b)
    _same(km, [KM_NOPASS % NAME_R, KM_REF % (7, w_pending(36, "ОТПРАВЛЕН"))])
    _eq(b.n("contract_find"), 1)


def gcase_job_on_find_refused(G):
    os.environ[F_GEN] = "1"
    for find, word in (({"ok": False, "error": "timeout"}, "timeout"), (TimeoutError("read timed out"), "TimeoutError"),
                       ({"ok": False, "error": "unknown_action"}, "unknown_action")):
        b = GBridge([_crm(G, 7, UUID)], make=NOPASS, find=find)
        km = _job(G, b)
        _eq(len(km), 2, km)
        assert KM_NOPASS % NAME_R in km, km
        words = _ref_words(_ref_line(km, 7), 7)
        assert words.startswith(W_UNKNOWN_HEAD) and words.endswith(W_UNKNOWN_TAIL) and word in words, words
        assert "подписанного и ждущего подписи нет" not in words, words
        _eq((b.n("contract_find"), b.n("make_contract")), (1, 1), b.calls)


def gcase_job_on_no_term(G):
    os.environ[F_GEN] = "1"
    for row in (_crm(G, 7, UUID, end=None), _crm(G, 7, UUID, bike="Honda PCX")):
        b = GBridge([row], make=NOPASS)
        km = _job(G, b)
        _same(km, [KM_NOPASS % NAME_R, KM_REF % (7, GEN_NO_TERM)])
        _eq(b.n("contract_find"), 0, b.calls)


def gcase_job_toggle(G):
    seq = []
    for flag in (None, "1", None, "on"):
        if flag is None:
            os.environ.pop(F_GEN, None)
        else:
            os.environ[F_GEN] = flag
        b = GBridge([_crm(G, 7, UUID)])
        _job(G, b)
        seq.append(b.kw("make_contract"))
    old = [{"name": NAME_R, "date_start": "%s 10:00" % G.today}]
    _eq(seq, [old, [{"booking_id": UUID}], old, [{"booking_id": UUID}]])


def gcase_intake_on_uuid_ok(G):
    os.environ[F_GEN] = "1"
    for uid in (UUID, UUID.upper()):
        b = GBridge([_crm(G, 7, UUID)])
        replies, _logs = _intake(G, b, "договор " + uid)
        _eq(b.kw("make_contract"), [{"booking_id": uid}], b.calls)
        _eq((b.n("issue_write_ticket"), b.n("contract_find"), b.n("_call")), (1, 0, 0), b.calls)
        assert len(replies) == 1 and replies[0].startswith("🐀 Splinter\n✅ Договор готов: " + OK_MAKE["url"]), replies


def gcase_intake_on_partial_uuid(G):
    os.environ[F_GEN] = "1"
    b = GBridge([_crm(G, 7, UUID)])
    replies, _logs = _intake(G, b, "договор " + UUID[:13])
    _eq(replies, [UKAZHI])
    _eq(b.calls, [])


def gcase_intake_on_uuid_nopass(G):
    os.environ[F_GEN] = "1"
    other = _crm(G, 9, "a0000000-0000-4000-8000-000000000009", name="Тест Другой", bike="Honda PCX 160 4321")
    b = GBridge([_crm(G, 7, UUID), other], items=[_gitem(G, 36, "ПОДПИСАН", SA36, "PDF36")], make=NOPASS)
    replies, logs = _intake(G, b, "договор " + UUID)
    words = w_current(36, "ПОДПИСАН", SA36)
    _eq(b.kw("make_contract"), [{"booking_id": UUID}], b.calls)
    _eq(replies, [BASE_FAIL + REG_PART + words])
    _eq(b.kw("_call"), [{"action": "clients", "filter": "all"}], b.calls)
    _eq(b.kw("contract_find"), [_find_kw(G)], b.calls)
    _eq([x for x in logs if "реестр" in x], [INTAKE_REF % words])
    _eq(b.others(), [])


def gcase_intake_on_key_two(G):
    os.environ[F_GEN] = "1"
    bk = "%s|%s|%s" % (BIKE_R, NAME_R, G.today)
    b = GBridge([_crm(G, 7, UUID), _crm(G, 9, "c0000000-0000-4000-8000-000000000009")],
                items=[_gitem(G, 36, "ПОДПИСАН", SA36, "PDF36")], make=NOPASS)
    replies, logs = _intake(G, b, "договор " + bk)
    _eq(b.kw("make_contract"), [{"booking_key": bk, "name": None, "date_start": None}], b.calls)
    _eq(replies, [BASE_FAIL + REG_PART + GEN_MANY_CRM % "7, 9"])
    _eq((b.n("contract_find"), b.n("_call")), (0, 1), b.calls)
    _eq([x for x in logs if "реестр" in x], [INTAKE_REF % (GEN_MANY_CRM % "7, 9")])


def gcase_intake_on_key_one(G):
    os.environ[F_GEN] = "1"
    bk = "%s|%s|%s" % (BIKE_R, NAME_R, G.today)
    b = GBridge([_crm(G, 7, UUID), _crm(G, 9, "", name="Тест Другой")], items=[_gitem(G, 36, "ПОДПИСАН", SA36, "PDF36")],
                make=NOPASS)
    replies, _logs = _intake(G, b, "договор " + bk)
    _eq(replies, [BASE_FAIL + REG_PART + w_current(36, "ПОДПИСАН", SA36)])
    _eq((b.n("contract_find"), b.n("_call"), b.n("make_contract")), (1, 1, 1), b.calls)
    _eq(b.kw("contract_find"), [_find_kw(G)], b.calls)


def gcase_intake_on_name_date(G):
    os.environ[F_GEN] = "1"
    b = GBridge([_crm(G, 7, UUID)])
    replies, _logs = _intake(G, b, "договор Тест 2026-10-14")
    _eq(b.kw("make_contract"), [{"booking_key": None, "name": "Тест", "date_start": "2026-10-14"}], b.calls)
    assert replies and replies[0].startswith("🐀 Splinter\n✅ Договор готов: "), replies
    _eq((b.n("contract_find"), b.n("_call")), (0, 0), b.calls)


def gcase_report_direct(G):
    os.environ[F_GEN] = "1"
    rep = G.S._contract_ref_report
    row7 = _crm(G, 7, UUID)
    bk = "%s|%s|%s" % (BIKE_R, NAME_R, G.today)
    b = GBridge([row7], items=[_gitem(G, 36, "ПОДПИСАН", SA36, "PDF36")])
    _eq(rep(b, row=row7), w_current(36, "ПОДПИСАН", SA36))
    _eq((b.n("_call"), b.n("contract_find")), (0, 1), b.calls)
    b = GBridge([row7], items=[_gitem(G, 36, "ПОДПИСАН", SA36, "PDF36")])
    _eq(rep(b, booking_key=bk), w_current(36, "ПОДПИСАН", SA36))
    _eq((b.n("_call"), b.n("contract_find")), (1, 1), b.calls)
    b = GBridge([row7], crm_error=RuntimeError("crm down"))
    _eq(rep(b, booking_id=UUID), GEN_CRM_UNREAD % "RuntimeError")
    _eq(b.n("contract_find"), 0)
    b = GBridge([row7])
    _eq(rep(b, booking_id="b0000000-0000-4000-8000-00000000000b"), GEN_NO_CRM)
    b2 = GBridge([])
    _eq(rep(b2, booking_key=bk), GEN_NO_CRM)
    for row in (_crm(G, 7, UUID, end=None), _crm(G, 7, UUID, bike="Honda PCX")):
        b3 = GBridge([row])
        _eq(rep(b3, row=row), GEN_NO_TERM)
        _eq(b3.n("contract_find"), 0)
    b4 = GBridge([row7], find=TimeoutError("read timed out"))
    words = rep(b4, row=row7)
    assert words.startswith(W_UNKNOWN_HEAD) and words.endswith(W_UNKNOWN_TAIL) and "TimeoutError" in words, words
    for x in (b, b2, b3, b4):
        _eq((x.n("make_contract"), x.n("issue_write_ticket"), x.others()), (0, 0, []), x.calls)


GEN_OFF = (gcase_flag_rule, gcase_job_off_nopass, gcase_job_off_ok, gcase_intake_off_uuid, gcase_intake_off_key_nopass)
GEN_ON = (gcase_job_on_bid_ok, gcase_job_on_empty_bid, gcase_job_on_bid_nopass, gcase_job_on_two_bookings,
          gcase_job_on_pending, gcase_job_on_find_refused, gcase_job_on_no_term, gcase_job_toggle,
          gcase_intake_on_uuid_ok, gcase_intake_on_partial_uuid, gcase_intake_on_uuid_nopass, gcase_intake_on_key_two,
          gcase_intake_on_key_one, gcase_intake_on_name_date, gcase_report_direct)


def _gen_stubs():
    """Тяжёлые зависимости bot.py — подделки до импорта (как tests/test_staff_ask.py); мост — НАСТОЯЩИЙ bridge_client."""
    class FakeMem:
        def all_topic_bikes(self):
            return {}

        def all_info_pins(self):
            return {}

        def set_topic_bike(self, *a, **k):
            return None

    class FakeAuditor:
        audit_groups = []

        def __init__(self, *a, **k):
            pass

        def set_audit_config(self, *a, **k):
            pass

        def check_response_text(self, *a, **k):
            return None

    def stub(name, **attrs):
        m = types.ModuleType(name)
        for k, v in attrs.items():
            setattr(m, k, v)
        sys.modules[name] = m
    try:
        import fcntl  # noqa: F401
    except ImportError:
        f = types.ModuleType("fcntl")
        f.LOCK_SH, f.LOCK_EX, f.LOCK_NB, f.LOCK_UN = 1, 2, 4, 8
        f.flock = lambda fd, op: None
        f.lockf = lambda fd, cmd, *rest: None
        sys.modules["fcntl"] = f
    stub("dotenv", load_dotenv=lambda *a, **k: None)
    stub("claude_client", ClaudeClient=lambda *a, **k: None)
    stub("memory", Memory=FakeMem)
    stub("auditor", Auditor=FakeAuditor)
    stub("prompts", SYSTEM_PROMPT="", daily_pulse_prompt=lambda *a, **k: "")


def _gen_child():
    res = {}
    try:
        tmp = tempfile.mkdtemp(prefix="contractref_gen_")
        for k, n in GEN_STATE_ENV:
            os.environ[k] = os.path.join(tmp, n)
        os.environ.update({"BRIDGE_URL": "http://127.0.0.1:9/contractref-test", "BRIDGE_TOKEN": "contractref-test",
                           "BOT_TOKEN": "contractref-test"})
        for f in (F_GEN, "RENTAL_CASE", "RENTAL_CASE_PICK", "RENTAL_CASE_APPROVALS", "RENTAL_CASE_DB"):
            os.environ.pop(f, None)
        _gen_stubs()                                             # до любого импорта моста и bot: .env не читается
        import rental_case_fakes  # noqa: F401 — сеть запрещена с этой строки
        import bot
        from zoneinfo import ZoneInfo
        cap = _Cap()
        for name in ("turbobaby", "splinter"):                 # журналы bot.py и splinter.py — по одному разу
            logging.getLogger(name).setLevel(logging.INFO)
            logging.getLogger(name).addHandler(cap)
        spl = bot.splinter
        spl._send = _rec_send
        now_l = datetime.datetime.now(ZoneInfo(bot.TZ_NAME))
        G = types.SimpleNamespace(bot=bot, S=spl, cap=cap, today=now_l.strftime("%Y-%m-%d"),
                                  end=(now_l + datetime.timedelta(days=6)).strftime("%Y-%m-%d"))
        res["__mods_after_import__"] = sorted(m for m in (NEW_MODULE,) if m in sys.modules)
    except BaseException as e:                                       # noqa: BLE001 — назовут случаи родителя
        sys.stdout.write(GEN_MARK + json.dumps({"__crash__": "сборка процесса генератора: %s: %s" % (
            type(e).__name__, str(e)[:800])}) + "\n")
        return 0

    def run(fn):
        del _GSENT[:]
        cap.msgs[:] = []
        try:
            spl._INTAKE_DRAFTS.clear()
        except Exception:                                            # noqa: BLE001
            pass
        try:
            fn(G)
            res[fn.__name__] = "ok"
        except BaseException as e:                                   # noqa: BLE001
            res[fn.__name__] = "FAIL %s: %s" % (type(e).__name__, str(e)[:900])
        finally:
            os.environ.pop(F_GEN, None)
    for fn in GEN_OFF:
        run(fn)
    res["gcase_off_no_module"] = ("ok" if NEW_MODULE not in sys.modules and res["__mods_after_import__"] == [] else
                                  "FAIL: модуль %s в процессе при флаге ВЫКЛ" % NEW_MODULE)
    for fn in GEN_ON:
        run(fn)
    sys.stdout.write(GEN_MARK + json.dumps(res) + "\n")
    sys.stdout.flush()
    return 0


_GEN_CACHE = {}


def _gen():
    if "r" not in _GEN_CACHE:
        try:
            p = subprocess.run([sys.executable, os.path.abspath(__file__), GEN_ARG], cwd=ROOT, capture_output=True,
                               timeout=600, env=dict(os.environ, PYTHONIOENCODING="utf-8"))
            out = p.stdout.decode("utf-8", "replace")
            got = [ln for ln in out.splitlines() if ln.startswith(GEN_MARK)]
            r = json.loads(got[-1][len(GEN_MARK):]) if got else {
                "__crash__": "rc=%s; stdout: %s; stderr: %s" % (p.returncode, out[-600:],
                                                                p.stderr.decode("utf-8", "replace")[-1500:])}
        except Exception as e:                                       # noqa: BLE001
            r = {"__crash__": "%s: %s" % (type(e).__name__, e)}
        _GEN_CACHE["r"] = r
    return _GEN_CACHE["r"]


def _g(*names):
    r = _gen()
    bad = {n: r.get(n, r.get("__crash__", "случай не исполнялся")) for n in names if r.get(n) != "ok"}
    assert not bad, bad


def test_g01_job_flag_off_old_call_registry_not_read():
    """G1: ФЛАГ ВЫКЛ — scheduled_contract_km на брони с booking_id зовёт make_contract(name=, date_start=) как прежде; на
    no_passport contract_find не зван, строки журнала прежние; в процессе нет contract_ref. Близнец: флаг ВКЛ — §5.1."""
    _g("gcase_job_off_nopass", "gcase_job_off_ok", "gcase_off_no_module", "gcase_job_on_bid_ok")


def test_g02_booking_id_only_when_present():
    """G2: флаг ВКЛ, booking_id пуст → прежний вызов name+date; booking_id есть → make_contract(booking_id=bid) без
    других kwargs."""
    _g("gcase_job_on_empty_bid", "gcase_job_on_bid_ok")


def test_g03_no_passport_one_registry_read_named_version():
    """G3: make_contract ok → contract_find не зван; no_passport → ровно один contract_find(bike, date_from, date_to,
    limit=100), make_contract и issue_write_ticket по разу на бронь; новая строка журнала называет версию (current /
    pending §6.3 дословно) без имени клиента; две брони — счётчики по брони."""
    _g("gcase_job_on_bid_ok", "gcase_job_on_bid_nopass", "gcase_job_on_two_bookings", "gcase_job_on_pending")


def test_g04_registry_refused_is_unknown_not_no_contract():
    """G4: no_passport и contract_find отказал / упал / дверь неизвестна → слова unknown §6.3 («неизвестно, а не
    «договора нет»»); срока или номера байка нет — GEN_NO_TERM без чтения реестра. Близнец: ок → названная версия."""
    _g("gcase_job_on_find_refused", "gcase_job_on_no_term", "gcase_job_on_bid_nopass")


def test_g05_uuid_command():
    """G5: флаг ВЫКЛ — «договор <uuid>» → «Укажи бронь…», make_contract не зван; флаг ВКЛ — make_contract(booking_id=
    <uuid>) (регистр A–F любой); неполный UUID — прежний разбор."""
    _g("gcase_intake_off_uuid", "gcase_intake_on_uuid_ok", "gcase_intake_on_partial_uuid")


def test_g06_intake_no_passport_reply_and_log():
    """G6: флаг ВКЛ, no_passport по booking_key, в CRM две строки того же имени и даты → ответ = прежний текст +
    «📄 Реестр по этой брони: » + GEN_MANY_CRM, contract_find не зван; одна строка → contract_find 1 раз и слова
    версии; по UUID — строка CRM по booking_id. Близнец ВЫКЛ — ответ прежний без реестра; «Имя дата» — прежний вызов."""
    _g("gcase_intake_off_key_nopass", "gcase_intake_on_key_two", "gcase_intake_on_key_one",
       "gcase_intake_on_uuid_nopass", "gcase_intake_on_name_date")


def test_g07_report_read_only_by_construction():
    """G7: ast `splinter._contract_ref_report` — запретных имён §5.3 нет, contract_ref импортируется лениво внутри;
    вживую — ни make_contract, ни билета, не больше одного contract_find и одного чтения CRM; сбои — словами."""
    tree = _tree(os.path.join(ROOT, "splinter.py"))
    fns = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
           and n.name == "_contract_ref_report"]
    assert len(fns) == 1, "функции _contract_ref_report нет"
    assert not _names(fns[0]) & REPORT_FORBIDDEN, _names(fns[0]) & REPORT_FORBIDDEN
    assert NEW_MODULE in _imports(fns[0]), "contract_ref импортируется лениво внутри функции"
    par = list(inspect.signature(lambda bridge, row=None, booking_id=None, booking_key=None, name=None,
                                 date_start=None: None).parameters)
    got = [a.arg for a in fns[0].args.args] + [a.arg for a in fns[0].args.kwonlyargs]
    assert got == par, got
    _g("gcase_report_direct")


def test_g08_flag_toggle_without_reimport():
    """G8: флаг переключён между запусками задания без переимпорта — поведение меняется соответственно."""
    _g("gcase_job_toggle")


def test_g09_flag_name_and_rule():
    """§1: splinter.F_CONTRACT_REF_GEN = "CONTRACT_REF_GEN", правило флага — 1/true/yes/on (иначе ВЫКЛ)."""
    _g("gcase_flag_rule")


# ══ V · чистый модуль contract_ref ═══════════════════════════════════════════════════════════════════════════════

def test_v01_case_sequence_current_pending_superseded():
    """V1: последовательность одной брони (ref_of = versions(binding_of_rental)): 34 ПОДПИСАН → current 34; 34 ОТОЗВАН +
    36 НОВЫЙ → pending [36], superseded [34], current None; 36 ОТПРАВЛЕН → pending [36]; 36 ПОДПИСАН → current 36.
    Близнец живого реестра (34, 35 ОТОЗВАН, 36 ПОДПИСАН) → current 36."""
    cr = _cr()

    def st(items):
        return cr.ref_of(fresp(items), NUM_R, copy.deepcopy(RENTAL_R))
    s = st([ritem(34, "ПОДПИСАН", SA34, "P34")])
    assert s["outcome"] == "current" and s["current"]["row"] == 34 and s["current"]["role"] == "current", s
    assert (s["pending"], s["superseded"], s["foreign"], s["unchecked"]) == ([], [], [], []), s
    assert s["booking_id"] == "B1234", s
    s = st([ritem(34, "ОТОЗВАН", SA34, "P34"), ritem(36, "НОВЫЙ")])
    assert s["outcome"] == "pending" and s["current"] is None, s
    assert rows_of(s["pending"]) == [36] and rows_of(s["superseded"]) == [34], s
    assert [(x["row"], x["role"]) for x in s["rows"]] == [(36, "pending"), (34, "superseded")], s["rows"]
    s = st([ritem(34, "ОТОЗВАН", SA34, "P34"), ritem(36, "ОТПРАВЛЕН")])
    assert s["outcome"] == "pending" and rows_of(s["pending"]) == [36] and s["current"] is None, s
    s = st([ritem(34, "ОТОЗВАН", SA34, "P34"), ritem(36, "ПОДПИСАН", SA36, "PDF36")])
    assert s["outcome"] == "current" and s["current"]["row"] == 36 and rows_of(s["superseded"]) == [34], s
    assert s["current"]["doc_id"] == DOCS[36] and s["current"]["pdf_id"] == "PDF36" and s["current"]["signed_at"] == SA36
    s = st([ritem(34, "ОТОЗВАН", SA34, "P34"), ritem(35, "ОТОЗВАН", SA35, "P35"), ritem(36, "ПОДПИСАН", SA36, "PDF36")])
    assert s["outcome"] == "current" and s["current"]["row"] == 36, s
    assert sorted(rows_of(s["superseded"]), reverse=True) == [35, 34], s


def test_v02_two_signed_ambiguous_never_newest():
    """V2: 35 и 36 ПОДПИСАН, оба привязаны → ambiguous, current None — при любом порядке items и любых signed_at
    («новейший» не выбирается). Близнец: 35 ОТОЗВАН + 36 ПОДПИСАН → current 36."""
    for sa35 in (SA35, "2026-10-15 08:00"):
        a, b = ritem(35, "ПОДПИСАН", sa35, "P35"), ritem(36, "ПОДПИСАН", SA36, "PDF36")
        for items in ([a, b], [b, a]):
            res = vers(items, sort=False)
            assert res["outcome"] == "ambiguous" and res["current"] is None, res
            assert sorted(x["role"] for x in res["rows"]) == ["signed", "signed"], res["rows"]
            assert rows_of(res["rows"]) == [36, 35], "rows — по row убыв."
    res = vers([ritem(35, "ОТОЗВАН", SA35, "P35"), ritem(36, "ПОДПИСАН", SA36, "PDF36")])
    assert res["outcome"] == "current" and res["current"]["row"] == 36, res


def test_v03_phone_foreign_and_same9_other_country():
    """V3: телефон строки +66 990001122 при номере 79990001122 (9 цифр те же, код другой) → foreign, не current (дверь
    сказала «one» — pick остаётся в foreign, исход none); чужой номер целиком → foreign. Близнецы: тот же номер, местная
    запись без кода → current; местная привязка CRM (intl False) кодом страны не судится."""
    assert T.last9("+66 990001122") == T.last9(NUM_R)
    for ph in ("+66 990001122", "+7 916 123-45-67"):
        f = fresp([ritem(36, "ПОДПИСАН", SA36, "PDF36", phone=ph)])
        res = _cr().versions(f, copy.deepcopy(BIND))
        assert res["outcome"] == "none" and res["current"] is None, (ph, res)
        assert rows_of(res["foreign"]) == [36] and res["rows"][0]["role"] == "foreign", (ph, res)
    for ph in (PHONE_R, "+7 999 000 11 22", "8 999 000-11-22", "0990001122", "7 999 000 11 22"):
        res = vers([ritem(36, "ПОДПИСАН", SA36, "PDF36", phone=ph)])
        assert res["outcome"] == "current" and res["current"]["row"] == 36, (ph, res)
    local = dict(BIND, phones=[{"digits": "0990001122", "intl": False}])
    res = vers([ritem(36, "ПОДПИСАН", SA36, "PDF36", phone="+66 990001122")], bind=local)
    assert res["outcome"] == "current", res


def test_v04_bike_foreign_and_homoglyph_same_plate():
    """V4: байк строки «… 5678» → foreign; близнецы «… 1234» и «400СС» кириллицей против «400CC» латиницей → current."""
    res = vers([ritem(36, "ПОДПИСАН", SA36, "PDF36", bike="Honda PCX 160 5678")])
    assert res["outcome"] == "none" and rows_of(res["foreign"]) == [36] and res["current"] is None, res
    assert vers([ritem(36, "ПОДПИСАН", SA36, "PDF36")])["outcome"] == "current"
    rent = copy.deepcopy(RENTAL_R)
    rent["facts"][0]["bike"] = "NINJA 400CC PHUKET 1234"
    res = _cr().ref_of(fresp([ritem(36, "ПОДПИСАН", SA36, "PDF36", bike="NINJA 400СС PHUKET 1234")]), NUM_R, rent)
    assert res["outcome"] == "current" and res["current"]["row"] == 36, res


def test_v05_day_out_of_term_foreign_bounds_inclusive():
    """V5: contract_date вне срока (2026-10-21, 2026-10-13) → foreign; границы 2026-10-14 и 2026-10-20 включительно →
    current."""
    for day in ("2026-10-21", "2026-10-13"):
        res = vers([ritem(36, "ПОДПИСАН", SA36, "PDF36", date=day)])
        assert res["outcome"] == "none" and rows_of(res["foreign"]) == [36], (day, res)
    for day in ("2026-10-14", "2026-10-20"):
        res = vers([ritem(36, "ПОДПИСАН", SA36, "PDF36", date=day)])
        assert res["outcome"] == "current", (day, res)


def test_v06_phone_unchecked_and_nick():
    """V6: подписанная строка без телефона и без ника → unchecked → incomplete. Близнецы: с телефоном → current; ник
    (matched_on nick и filter.phone_last9 = номер) → current; ник, сверенный с другим номером → foreign."""
    res = vers([ritem(36, "ПОДПИСАН", SA36, "PDF36", phone="", on=())])
    assert res["outcome"] == "incomplete" and rows_of(res["unchecked"]) == [36] and res["current"] is None, res
    assert vers([ritem(36, "ПОДПИСАН", SA36, "PDF36")])["outcome"] == "current"
    nick = ritem(36, "ПОДПИСАН", SA36, "PDF36", phone="", on=("nick",))
    res = vers([nick])
    assert res["outcome"] == "current" and res["current"]["row"] == 36, res
    res = vers([nick], phone_last9="916123456")
    assert res["outcome"] == "none" and rows_of(res["foreign"]) == [36], res


def test_v07_door_ambiguous_is_ambiguous():
    """V7: дверь сказала ambiguous → ambiguous (даже если привязана лишь одна строка). Близнец: дверь one → current."""
    res = vers([ritem(36, "ПОДПИСАН", SA36, "PDF36"), ritem(35, "ПОДПИСАН", SA35, "P35", bike="Honda PCX 160 5678")])
    assert res["outcome"] == "ambiguous" and res["current"] is None, res
    res = vers([ritem(36, "ПОДПИСАН", SA36, "PDF36")])
    assert res["outcome"] == "current", res


def test_v08_refusal_timeout_garbage_is_unknown_never_none():
    """V8: card_deadline, timeout, door:TimeoutError, None, строка, {"ok":True} без items/outcome, items не список,
    checked не словарь, исход двери не из списка, ok не True → unknown: rows и списки пусты, current None, причина
    «реестр не прочитан: …», НИКОГДА none. Близнец: тот же реестр с ok → current / none."""
    good = fresp([ritem(36, "ПОДПИСАН", SA36, "PDF36")])
    bad = [({"ok": False, "error": "card_deadline"}, "card_deadline"), ({"ok": False, "error": "timeout"}, "timeout"),
           ({"ok": False, "error": "door:TimeoutError"}, "TimeoutError"), (None, None), ("x", None),
           ({"ok": True}, None), (dict(good, items="x"), None), (dict(good, checked="x"), None),
           (dict(good, outcome="maybe"), None), (dict(good, ok=1), None), (dict(good, ok="true"), None),
           ({"ok": False, "error": "unknown_action"}, "unknown_action")]
    for resp, word in bad:
        res = _cr().versions(copy.deepcopy(resp), copy.deepcopy(BIND))
        assert res["outcome"] == "unknown" and res["current"] is None, (resp, res)
        assert (res["rows"], res["pending"], res["superseded"], res["foreign"], res["unchecked"]) == ([], [], [], [],
                                                                                                    []), res
        assert str(res["reason"]).startswith("реестр не прочитан: "), res["reason"]
        if word:
            assert word in res["reason"], (word, res["reason"])
    assert _cr().versions(good, copy.deepcopy(BIND))["outcome"] == "current"
    assert vers([])["outcome"] == "none"


def test_v09_incomplete_door_reads_never_chosen():
    """V9: unread непуст / не список; undated_signed 1, True, нет поля; truncated True; дверь incomplete → incomplete,
    current None. Близнец: unread [], 0, False → current."""
    base = fresp([ritem(36, "ПОДПИСАН", SA36, "PDF36")])
    spoils = []
    r = copy.deepcopy(base)
    r["checked"]["unread"] = ["лист «Реестр», строки 900–1200"]
    spoils.append(r)
    r = copy.deepcopy(base)
    r["checked"]["unread"] = "лист"
    spoils.append(r)
    for v in (1, True):
        r = copy.deepcopy(base)
        r["checked"]["undated_signed"] = v
        spoils.append(r)
    r = copy.deepcopy(base)
    del r["checked"]["undated_signed"]
    spoils.append(r)
    r = copy.deepcopy(base)
    r["checked"]["truncated"] = True
    spoils.append(r)
    spoils.append(fresp([ritem(36, "ПОДПИСАН", SA36, "PDF36")], outcome="incomplete"))
    for resp in spoils:
        res = _cr().versions(resp, copy.deepcopy(BIND))
        assert res["outcome"] == "incomplete" and res["current"] is None, (resp["checked"], res)
    assert _cr().versions(base, copy.deepcopy(BIND))["outcome"] == "current"


def test_v10_incomplete_binding_never_chosen():
    """V10: привязка без phones, plate, date_from, date_to или с date_from > date_to → incomplete («привязка не полна» для
    пустых полей). Близнец: полная → current."""
    s36 = ritem(36, "ПОДПИСАН", SA36, "PDF36")
    for bad in (dict(BIND, phones=[]), dict(BIND, plate=""), dict(BIND, date_from=""), dict(BIND, date_to="")):
        res = vers([s36], bind=bad)
        assert res["outcome"] == "incomplete" and res["current"] is None, (bad, res)
        assert "привязка не полна" in str(res["reason"]), res["reason"]
    res = vers([s36], bind=dict(BIND, date_from="2026-10-21"))
    assert res["outcome"] == "incomplete" and res["current"] is None and res["reason"], res
    assert vers([s36])["outcome"] == "current"


def test_v11_resigned_same_doc_new_version_same_version():
    """V11: тот же doc_id и строка 36 с новыми signed_at и pdf_id — другая версия (same_version False), current — новая.
    Близнецы: копия — та же версия (с обрезкой пробелов); пустой pdf — не та же; file_id вместо pdf_id принимается."""
    cr = _cr()
    old = {"doc_id": DOCS[36], "signed_at": SA36, "pdf_id": "PDF36"}
    for new in (dict(old, signed_at=SA36B, pdf_id="PDF36B"), dict(old, signed_at=SA36B), dict(old, pdf_id="PDF36B"),
                dict(old, doc_id=DOCS[37])):
        assert cr.same_version(old, new) is False and cr.same_version(new, old) is False, new
    assert cr.same_version(old, dict(old)) is True
    assert cr.same_version(old, {"doc_id": " %s " % DOCS[36], "signed_at": SA36 + " ", "pdf_id": " PDF36"}) is True
    assert cr.same_version({"doc_id": DOCS[36], "signed_at": SA36, "file_id": "PDF36"}, old) is True
    for blank in ({"pdf_id": ""}, {"doc_id": ""}, {"signed_at": ""}, {"pdf_id": None}):
        x = dict(old, **blank)
        assert cr.same_version(x, dict(x)) is False, blank
    res = vers([ritem(36, "ПОДПИСАН", SA36B, "PDF36B")])
    assert res["outcome"] == "current" and (res["current"]["signed_at"], res["current"]["pdf_id"]) == (SA36B, "PDF36B")
    assert cr.same_version(res["current"], old) is False


def test_v12_single_signed_without_key_is_incomplete():
    """V12: единственный подписанный без pdf_id / doc_id / signed_at → incomplete. Близнец: со всеми → current."""
    for kw in ({"pdf_id": ""}, {"doc": ""}, {"signed_at": ""}):
        args = {"signed_at": SA36, "pdf_id": "PDF36"}
        args.update({k: v for k, v in kw.items() if k != "doc"})
        res = vers([ritem(36, "ПОДПИСАН", doc=kw.get("doc"), **args)])
        assert res["outcome"] == "incomplete" and res["current"] is None, (kw, res)
    assert vers([ritem(36, "ПОДПИСАН", SA36, "PDF36")])["outcome"] == "current"


def test_v13_dead_statuses_none_and_undated_incomplete():
    """V13: только ОТОЗВАН, ОТКЛОНЁН, ИСТЁК (Ё=Е) → none, все в superseded, статус дословный; ОШИБКА → other; при
    checked.undated = 1 и без подписанных → incomplete. Близнец: undated 0 → none."""
    items = [ritem(34, "ОТОЗВАН", SA34, "P34"), ritem(35, "ОТКЛОНЁН", SA35, "P35"), ritem(33, "ИСТЁК", SA33, ""),
             ritem(37, "ОШИБКА")]
    res = vers(items)
    assert res["outcome"] == "none" and res["current"] is None, res
    assert sorted(rows_of(res["superseded"]), reverse=True) == [35, 34, 33], res["superseded"]
    assert {x["row"]: x["status"] for x in res["rows"]}[35] == "ОТКЛОНЁН"
    assert {x["row"]: x["role"] for x in res["rows"]}[37] == "other"
    res = vers(items[:2], undated_items=[ritem(33, "НОВЫЙ", date=None)])
    assert res["outcome"] == "incomplete" and res["current"] is None, res
    assert 33 not in rows_of(res["rows"]), "undated_items не классифицируются"
    assert vers(items[:2])["outcome"] == "none"


def test_v14_two_pending_desc():
    """V14: 36 ОТПРАВЛЕН + 37 НОВЫЙ → pending [37, 36], current None."""
    res = vers([ritem(36, "ОТПРАВЛЕН"), ritem(37, "НОВЫЙ")], sort=False)
    assert res["outcome"] == "pending" and rows_of(res["pending"]) == [37, 36] and res["current"] is None, res


def test_v15_pure_module_input_untouched_deterministic():
    """V15: ast — импорты ровно re и wa_agent_tools, запретных имён §3 нет; вход не мутирован; два вызова равны."""
    cr = _cr()
    tree = _tree(cr.__file__)
    assert _imports(tree) == {"re", "wa_agent_tools"}, _imports(tree)
    assert not _names(tree) & PURE_FORBIDDEN, _names(tree) & PURE_FORBIDDEN
    for resp in (fresp([ritem(34, "ОТОЗВАН", SA34, "P34"), ritem(36, "ПОДПИСАН", SA36, "PDF36")]),
                 fresp([ritem(36, "ОТПРАВЛЕН"), ritem(37, "НОВЫЙ")]), {"ok": False, "error": "timeout"},
                 fresp([ritem(36, "ПОДПИСАН", SA36, "PDF36", bike="Honda PCX 160 5678")])):
        r0, b0, n0 = copy.deepcopy(resp), copy.deepcopy(BIND), copy.deepcopy(RENTAL_R)
        first = cr.versions(resp, BIND)
        assert resp == r0 and BIND == b0, "вход versions не мутирован"
        assert cr.versions(resp, BIND) == first
        second = cr.ref_of(resp, NUM_R, RENTAL_R)
        assert resp == r0 and RENTAL_R == n0 and cr.ref_of(resp, NUM_R, RENTAL_R) == second


def test_v16_no_pii_in_result_item_keys_exact():
    """V16: имя, телефон, ник и байк входа не встречаются в repr(versions(...)); ключи item ровно §3.2."""
    cr = _cr()
    extra = {"nick": NICK_R}
    resps = [fresp([ritem(36, "ПОДПИСАН", SA36, "PDF36", **extra)]),
             fresp([ritem(34, "ОТОЗВАН", SA34, "P34", **extra), ritem(36, "ОТПРАВЛЕН", **extra)]),
             fresp([ritem(36, "ПОДПИСАН", SA36, "PDF36", phone="+66 990001122", **extra)]),
             fresp([ritem(35, "ПОДПИСАН", SA35, "P35", **extra), ritem(36, "ПОДПИСАН", SA36, "PDF36", **extra)]),
             fresp([ritem(36, "ПОДПИСАН", SA36, "PDF36", phone="", on=(), **extra)]), {"ok": False, "error": "x"}]
    for resp in resps:
        res = cr.versions(resp, copy.deepcopy(BIND))
        assert RES_KEYS <= set(res), set(res)
        text = repr(res)
        for bad in (NAME_R, "Тест", PHONE_R, "000-11-22", NUM_R, T.last9(NUM_R), "990001122", NICK_R, "test_nick",
                    BIKE_R, "Honda"):
            assert bad not in text, (bad, text[:400])
        items = list(res["rows"]) + list(res["pending"]) + list(res["superseded"]) + list(res["foreign"]) + \
            list(res["unchecked"]) + ([res["current"]] if res["current"] else [])
        for it in items:
            assert set(it) == ITEM_KEYS, set(it) ^ ITEM_KEYS


def test_v17_bindings_rental_and_crm():
    """V17: binding_of_rental — номер, plate «1234», ISO-даты (и из «ДД.ММ.ГГГГ»), booking_id; факт сам — тоже. Без
    факта аренды — plate, даты и booking_id пусты, versions → incomplete. binding_of_crm: «081 234 5678; @nick» →
    intl False; «+66 …» → intl True; «0066 …» → intl True без «00»; срок из date_start/date_end."""
    cr = _cr()
    want = {"phones": [{"digits": NUM_R, "intl": True}], "plate": "1234", "date_from": FROM_R, "date_to": TO_R,
            "booking_id": "B1234"}
    assert cr.binding_of_rental(NUM_R, copy.deepcopy(RENTAL_R)) == want
    assert cr.binding_of_rental(NUM_R, dict(RENTAL_FACT)) == want
    assert cr.binding_of_rental("+7 (999) 000-11-22", copy.deepcopy(RENTAL_R))["phones"] == want["phones"]
    dmy = cr.binding_of_rental(NUM_R, dict(RENTAL_FACT, date_start="14.10.2026", date_end="20.10.2026"))
    assert (dmy["date_from"], dmy["date_to"]) == (FROM_R, TO_R), dmy
    s36 = fresp([ritem(36, "ПОДПИСАН", SA36, "PDF36")])
    for rent in (dict(RENTAL_R, outcome=T.EMPTY, facts=[]), dict(RENTAL_R, facts=[RENTAL_FACT, RENTAL_FACT]),
                 dict(RENTAL_R, outcome=T.AMBIGUOUS), None):
        b = cr.binding_of_rental(NUM_R, copy.deepcopy(rent))
        assert (b["plate"], b["date_from"], b["date_to"], b["booking_id"]) == ("", "", "", ""), (rent, b)
        assert cr.versions(s36, b)["outcome"] == "incomplete"
        assert cr.ref_of(s36, NUM_R, copy.deepcopy(rent))["outcome"] == "incomplete"
    row = {"row": 7, "status": "Бронь", "bike": BIKE_R, "name": NAME_R, "date_start": "2026-10-14 10:00",
           "date_end": "2026-10-20 10:00", "contacts": "081 234 5678; @nick", "booking_id": UUID}
    b = cr.binding_of_crm(dict(row))
    assert b == {"phones": [{"digits": "0812345678", "intl": False}], "plate": "1234", "date_from": FROM_R,
                 "date_to": TO_R, "booking_id": UUID}, b
    assert cr.binding_of_crm(dict(row, contacts="+66 81 234 5678"))["phones"] == [{"digits": "66812345678",
                                                                                   "intl": True}]
    assert cr.binding_of_crm(dict(row, contacts="0066 81 234 5678"))["phones"] == [{"digits": "66812345678",
                                                                                    "intl": True}]
    assert cr.binding_of_crm(dict(row, contacts="+7 999 000-11-22/081 234 5678|@nick"))["phones"] == [
        {"digits": NUM_R, "intl": True}, {"digits": "0812345678", "intl": False}]
    nb = cr.binding_of_crm(dict(row, date_end=None))
    assert nb["date_to"] == "" and cr.versions(s36, nb)["outcome"] == "incomplete", nb


def test_v18_crm_pick_one_many_none():
    """V18: crm_pick — две строки с тем же именем и датой → (None, GEN_MANY_CRM «7, 9»); ноль → GEN_NO_CRM; одна → строка;
    по booking_id — точная строка (имя и дата не нужны)."""
    cr = _cr()

    def crm(row, bid, name, start):
        return {"row": row, "status": "Бронь", "bike": BIKE_R, "name": name, "date_start": start,
                "date_end": "2026-10-20 10:00", "contacts": PHONE_R, "booking_id": bid}
    rows = [crm(7, "uuid-7", NAME_R, "2026-10-14 10:00"), crm(9, "uuid-9", NAME_R, "2026-10-14 12:00"),
            crm(11, "uuid-11", "Тест Другой", "2026-10-14 10:00"), crm(12, "", NAME_R, "2026-10-15 10:00"),
            crm(13, "", NAME_R, None)]
    many = (None, GEN_MANY_CRM % "7, 9")
    assert cr.crm_pick(rows, booking_key="%s|%s|2026-10-14" % (BIKE_R, NAME_R)) == many
    assert cr.crm_pick(rows, name=" тест тестов ", date_start="14.10.2026") == many
    assert cr.crm_pick(rows, name="Нет Такого", date_start="2026-10-14") == (None, GEN_NO_CRM)
    assert cr.crm_pick(rows, name=NAME_R) == (None, GEN_NO_CRM), "дата не названа — совпадения нет"
    assert cr.crm_pick(rows, name=NAME_R, date_start="2026-10-15") == (rows[3], "")
    assert cr.crm_pick(rows, booking_id="uuid-9") == (rows[1], "")
    assert cr.crm_pick(rows, booking_id="uuid-404") == (None, GEN_NO_CRM)
    assert cr.crm_pick([], booking_key="%s|%s|2026-10-14" % (BIKE_R, NAME_R)) == (None, GEN_NO_CRM)


def test_v19_gen_words_each_outcome():
    """V19: gen_words — текст §6.3 для каждого исхода; unknown НЕ утверждает «нет договора»; имени, телефона, ника нет."""
    cr = _cr()

    def g(items, **kw):
        return cr.gen_words(vers(items, **kw))
    assert g([ritem(34, "ОТОЗВАН", SA34, "P34"), ritem(36, "ПОДПИСАН", SA36, "PDF36")]) == w_current(36, "ПОДПИСАН",
                                                                                                       SA36)
    assert g([ritem(34, "ОТОЗВАН", SA34, "P34"), ritem(36, "ОТПРАВЛЕН")]) == w_pending(36, "ОТПРАВЛЕН")
    amb = g([ritem(35, "ПОДПИСАН", SA35, "P35"), ritem(36, "ПОДПИСАН", SA36, "PDF36")])
    assert amb in (W_AMB_HEAD + "стр. 36, стр. 35" + W_AMB_TAIL, W_AMB_HEAD + "стр. 35, стр. 36" + W_AMB_TAIL), amb
    amb4 = g([ritem(r, "ПОДПИСАН", SA36, "PDF%d" % r) for r in (34, 35, 36, 37)])
    assert amb4.startswith(W_AMB_HEAD) and amb4.endswith(W_AMB_TAIL) and amb4.count("стр. ") == 3 \
        and "и ещё 1" in amb4, amb4
    assert g([]) == W_NONE_HEAD + "0)"
    none2 = g([ritem(34, "ОТОЗВАН", SA34, "P34"), ritem(35, "ОТКЛОНЁН", SA35, "P35")])
    assert none2.startswith(W_NONE_HEAD + "2; не текущие: ") and none2.endswith(")"), none2
    assert "стр. 34 ОТОЗВАН" in none2 and "стр. 35 ОТКЛОНЁН" in none2, none2
    inc = cr.gen_words(_cr().versions(fresp([ritem(36, "ПОДПИСАН", SA36, "PDF36")], unread=["лист"]),
                                      copy.deepcopy(BIND)))
    assert inc.startswith(W_INC_HEAD) and ") — версия не названа; строки: " in inc and "стр. 36 ПОДПИСАН" in inc, inc
    inc0 = cr.gen_words(vers([], bind=dict(BIND, plate="")))
    assert inc0.startswith(W_INC_HEAD) and inc0.endswith(") — версия не названа"), inc0
    unk = cr.gen_words(_cr().versions({"ok": False, "error": "timeout"}, copy.deepcopy(BIND)))
    assert unk.startswith(W_UNKNOWN_HEAD) and unk.endswith(W_UNKNOWN_TAIL) and "timeout" in unk, unk
    assert unk.count("договора нет") == 1 and "«договора нет»" in unk, unk
    for text in (amb, amb4, none2, inc, inc0, unk):
        for bad in (NAME_R, PHONE_R, NICK_R, NUM_R, T.last9(NUM_R)):
            assert bad not in text, (bad, text)


def test_v20_tail_equals_block_doc_tail():
    """V20: tail(x) == wa_contract_state.doc_tail(x)."""
    cr = _cr()
    for x in (DOCS[34], "", None, "abc", "1Ab-Cd_Ef!@#ЖЖ12345678", "  x y z  "):
        assert cr.tail(x) == CS.doc_tail(x), (x, cr.tail(x), CS.doc_tail(x))


def test_v21_constants_and_words_verbatim():
    """§6: слова и множества дословно; ref_of = versions(binding_of_rental)."""
    cr = _cr()
    assert (cr.GEN_NO_CRM, cr.GEN_MANY_CRM, cr.GEN_CRM_UNREAD, cr.GEN_NO_TERM) == (GEN_NO_CRM, GEN_MANY_CRM,
                                                                                   GEN_CRM_UNREAD, GEN_NO_TERM)
    assert set(cr.OUTCOMES) == {"current", "pending", "ambiguous", "none", "incomplete", "unknown"}
    assert set(cr.ROLES) == {"current", "signed", "pending", "superseded", "other", "foreign", "unchecked"}
    assert set(cr.PENDING_STATUSES) == {"НОВЫЙ", "ОТПРАВЛЕН"}
    assert set(cr.DEAD_STATUSES) == {"ОТОЗВАН", "ОТКЛОНЕН", "ИСТЕК"}
    for resp in (fresp([ritem(36, "ПОДПИСАН", SA36, "PDF36")]), fresp([ritem(36, "ОТПРАВЛЕН")]), None):
        assert cr.ref_of(copy.deepcopy(resp), NUM_R, copy.deepcopy(RENTAL_R)) == cr.versions(
            copy.deepcopy(resp), cr.binding_of_rental(NUM_R, copy.deepcopy(RENTAL_R)))


def test_v22_day_unknown_is_incomplete():
    """День неизвестен: подписанная строка без дня → unchecked → incomplete; дверь incomplete (подписанный в
    undated_items) → incomplete, undated не классифицируется; у привязки нет дня → incomplete. Близнец: день есть →
    current."""
    s36 = ritem(36, "ПОДПИСАН", SA36, "PDF36")
    nodate = ritem(36, "ПОДПИСАН", SA36, "PDF36", date=None)
    res = vers([nodate])
    assert res["outcome"] == "incomplete" and rows_of(res["unchecked"]) == [36] and res["current"] is None, res
    res = vers([], undated_items=[nodate])
    assert res["outcome"] == "incomplete" and res["rows"] == [] and res["current"] is None, res
    for bind in (dict(BIND, date_from=""), dict(BIND, date_to=""), dict(BIND, date_from="", date_to="")):
        assert vers([s36], bind=bind)["outcome"] == "incomplete", bind
    assert vers([s36])["outcome"] == "current"


# ══ запуск ══════════════════════════════════════════════════════════════════════════════════════════════════════

def main():
    if PROBE_ARG in sys.argv[1:]:
        return _probe_ref_off()
    if GEN_ARG in sys.argv[1:]:
        return _gen_child()
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    bad = 0
    for name, fn in tests:
        try:
            fn()
            print("PASS", name)
        except Exception as e:                                       # noqa: BLE001
            bad += 1
            print("FAIL", name, "—", type(e).__name__, str(e)[:600])
    print("ИТОГ %d/%d" % (len(tests) - bad, len(tests)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
