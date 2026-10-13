#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Харнесс мутантов К4 (дело аренды, rental_case): tests/rental_case_mutants.py

DESIGN_K4 §13 «проверки ловят порчу», К4-C20, CONTRACT_K4 §15 п.4: каждый мутант M1–M31 (с M1b, M10b, M11b, M14b,
M31b, M31c) — точечная текстовая порча РЕАЛЬНОГО кода (старый фрагмент → новый) в КОПИИ, затем прогон раннера
tests/run_rental_case_suites.py на этой копии. Мутант убит, если раннер вернул ≠ 0 и хотя бы один набор упал
(FAIL/TIMEOUT); иначе выжил.

Запуск (только stdlib, код разбирается ast.parse(..., feature_version=(3, 8))):

    python tests/rental_case_mutants.py --label <метка> [--only-mutant M1 [--only-mutant M10b ...]] [--jobs N]
                                        [--timeout <с на набор>] [--apply-only] [--base <каталог>]
                                        [--runs-base <каталог>] [--src-root <каталог>] [--runner <файл>]

Порядок работы:
  1. Копия: в <base>/<метка>/<Mid>/ копируются rental_case*.py и tests/*rental_case*.py, а также их НЕИЗМЕНЯЕМЫЕ
     локальные зависимости импорта (замыкание по AST: wa_agent_tools.py, wa_book_read.py, wa_agent_knowledge.py,
     bike_position.py, …) — без них копия не импортируется. Существующий каталог мутанта откладывается
     переименованием (<Mid>.prev-<штамп>), ничего не удаляется.
  2. Порча: каждая правка (файл, старый фрагмент, новый) применяется, только если старый фрагмент встречается в
     исходнике РОВНО ОДИН раз; иначе мутант NOT_APPLIED (а не «убит»). Испорченный файл обязан разбираться
     ast.parse(feature_version=(3, 8)) и компилироваться — иначе NOT_APPLIED (синтаксическая порча — не проверка
     тестов). Дифф порчи кладётся в <base>/<метка>/_diffs/<Mid>.diff.
  3. Контроль: та же копия БЕЗ порчи прогоняется тем же набором наборов; контроль обязан пройти (иначе исходы
     мутантов не судимы: харнесс останавливается, код выхода 2).
  4. Прогон: раннер `--root <копия> --label mut-<метка>-<Mid> --only …` отдельным процессом; его results.json
     (<runs-base>/mut-<метка>-<Mid>/results.json) и журналы наборов разбираются в «by» — упавшие проверки
     (`набор: FAIL|ERROR Класс.тест`, строки ПРОВАЛ/FAIL демо).

Наборы. Каждый мутант гоняется наборами rules, store, accept, seam, demo_A, demo_repeat (SUITES_DEFAULT; какой из них
ловит мутанта — видно в «by»). Исключены через --only:
  hygiene  — статические проверки файлов (LF, разбор 3.8, изоляция, SQL вне хранилища): к поведенческой порче не
             относятся, а синтаксическую порчу харнесс отсекает сам (NOT_APPLIED), так что «убийство» hygiene было бы
             ложным;
  demo_B   — раннер зовёт его без --trace, и демо пишет след в выход-документ
             D:/turbobaby-bot/tmp/k4_0910/out/trace_demo_B.jsonl: след испорченного кода в out/ класть нельзя.
             Вариант Б демо гоняется в demo_repeat (оба варианта, следы в ttmp прогона).

Итог: <base>/<метка>/results.json — {Mid: {"status": KILLED|SURVIVED|NOT_APPLIED, "by": [упавшие проверки], …},
"_meta": {…, "control": …, "summary": …}} и сводка в stdout. Код выхода 0 — только если контроль прошёл и ВСЕ
выбранные мутанты KILLED; 1 — есть SURVIVED/NOT_APPLIED; 2 — ошибка вызова или провал контроля.

Ничего не удаляет: прежние results.json и каталоги мутантов той же метки откладываются переименованием; временные
каталоги наборов остаются в <runs-base>/mut-<метка>-<Mid>/tmp. Сеть харнесс не трогает; наборы запрещают её сами
(tests/rental_case_fakes.py).
"""
import argparse
import ast
import concurrent.futures
import datetime
import difflib
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SRC_ROOT = os.path.dirname(HERE)
DEFAULT_RUNNER = os.path.join(HERE, "run_rental_case_suites.py")
DEFAULT_BASE = "D:/turbobaby-bot/tmp/k4_0910/ttmp/mutants"
DEFAULT_RUNS_BASE = "D:/turbobaby-bot/tmp/k4_0910/ttmp/runs"
DEFAULT_SUITE_TIMEOUT = 300
LABEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,39}$")
SUITES_DEFAULT = ("rules", "store", "accept", "seam", "demo_A", "demo_repeat")
SUITES_EXCLUDED = {
    "hygiene": "статические проверки файлов — к поведенческой порче не относятся; синтаксическую порчу харнесс "
               "отсекает сам (NOT_APPLIED)",
    "demo_B": "раннер зовёт его без --trace — след лёг бы в out/trace_demo_B.jsonl (выход-документ); вариант Б "
              "демо гоняется в demo_repeat",
}
CONTROL_ID = "CONTROL"

RULES = "rental_case_rules.py"
STORE = "rental_case.py"
FAKES = "tests/rental_case_fakes.py"


def L(*lines):
    """Фрагмент из строк (каждая — с переводом строки LF)."""
    return "".join(line + "\n" for line in lines)


def E(path, old, new):
    return (path, old, new)


def M(mid, design, model, edits, suites=SUITES_DEFAULT):
    return {"id": mid, "design": design, "model": model, "edits": tuple(edits), "suites": tuple(suites)}


# ---------------------------------------------------------------------------------------------------------------------
# Мутанты DESIGN_K4 §13 (дословная формулировка — "design"; как она смоделирована на коде кандидата — "model").
# Варианты *_v2/_v3 — вторая/третья ветка той же формулировки, где DESIGN называет её через «или/либо».
# ---------------------------------------------------------------------------------------------------------------------

_M31B_BLOCK_INSERT = L(
    '            _m31 = (self._case_rental_by_id(tx, case_id, rid)',
    '                    if (status == "verified" and kind == "contract_signed") else None)',
    '            if _m31 and _m31["start_day"] and _m31["end_day"]:                       # M31b: срок привязки = покрытие',
    '                tx.x("UPDATE rc_document SET cover_from=?, cover_to=?, cover_basis=\'document\', "',
    '                     "cover_ref=\'binding_at_verify\', cover_at=? WHERE id=?",',
    '                     (_m31["start_day"], _m31["end_day"], tx.now, did))')

_M31B_BLOCK_UPDATE = L(
    '                _m31 = (self._case_rental_by_id(tx, case_id, rid)',
    '                        if kind == "contract_signed" else None)',
    '                if _m31 and _m31["start_day"] and _m31["end_day"]:                   # M31b: срок привязки = покрытие',
    '                    tx.x("UPDATE rc_document SET cover_from=?, cover_to=?, cover_basis=\'document\', "',
    '                         "cover_ref=\'binding_at_verify\', cover_at=? WHERE id=?",',
    '                         (_m31["start_day"], _m31["end_day"], tx.now, ex["id"]))')

_M31C_BLOCK_INSERT = L(
    '            _m31 = (self._case_rental_by_id(tx, case_id, rid)',
    '                    if (status == "verified" and kind == "contract_signed" and bound_by == "human") else None)',
    '            if _m31 and _m31["start_day"] and _m31["end_day"]:                       # M31c: human_binding без дат',
    '                tx.x("UPDATE rc_document SET cover_from=?, cover_to=?, cover_basis=\'human_confirmed\', "',
    '                     "cover_ref=\'human_binding\', cover_by=?, cover_act=?, cover_at=? WHERE id=?",',
    '                     (_m31["start_day"], _m31["end_day"], by.get("id"),',
    '                      _s((human_binding or {}).get("act_ref")) or "human_binding", tx.now, did))')

_M31C_BLOCK_UPDATE = L(
    '                _m31 = (self._case_rental_by_id(tx, case_id, rid)',
    '                        if (kind == "contract_signed" and bound_by == "human") else None)',
    '                if _m31 and _m31["start_day"] and _m31["end_day"]:                   # M31c: human_binding без дат',
    '                    tx.x("UPDATE rc_document SET cover_from=?, cover_to=?, cover_basis=\'human_confirmed\', "',
    '                         "cover_ref=\'human_binding\', cover_by=?, cover_act=?, cover_at=? WHERE id=?",',
    '                         (_m31["start_day"], _m31["end_day"], by.get("id"),',
    '                          _s((human_binding or {}).get("act_ref")) or "human_binding", tx.now, ex["id"]))')

_DOC_INSERT_CALL = L(
    '            did = self._doc_insert(tx, case, kind, ext, status, source, rental_id=rid, sha256=_s(sha) or None,',
    '                                   signed_at=sa, reg_row=rr_no, bound_by=bound_by, why="record_document", extra=extra,',
    '                                   main=True)')
_DOC_UPDATE_EVENT = L(
    '                p = {"document_id": ex["id"], "kind": kind, "ext_id": ext, "sha256": ex["sha256"],')

MUTANTS = (
    M("M1", "M1 `max(date_start)`: аренда выбирается по максимальной дате начала",
      "rules._pick_client(intent=current): кандидат — строка контакта с максимальной датой начала вместо классов "
      "current/current_unactivated (будущая бронь того же клиента выдаётся за текущую)",
      [E(RULES,
         L('        cands = [(r, c) for r, c in pairs if c["cls"] in ("current", "current_unactivated")]'),
         L('        cands = [max(pairs, key=lambda rc: rc[1]["start_day"] or "")] if pairs else []   # M1: max(date_start)'))]),
    M("M1b", "M1b `cand[-1]`: из нескольких кандидатов берётся последний",
      "rules._pick_client(intent=None): при нескольких кандидатах found(cands[-1]) вместо unknown — порядок строк "
      "решает",
      [E(RULES,
         L('            return _pick_unknown("rental_ambiguous", ["which_rental", "intent"], [_cand(r, c) for r, c in cands],',
           '                                 purpose, intent)'),
         L('            return _found(*cands[-1])                                   # M1b: cand[-1]'))]),
    M("M2", "M2 касса по одному байку",
      "rules.bind_cash: совпал номер байка кассы и аренды → bound(plate+day) без дня, претендентов и booking_id",
      [E(RULES,
         L('    same_plate = cplate is not None and cplate == rplate'),
         L('    same_plate = cplate is not None and cplate == rplate',
           '    if same_plate:',
           '        return _bind_out("bound", "plate+day")                     # M2: касса по одному байку'))]),
    M("M3", "M3 версия ответа не сверяется",
      "rules.answer_verdict: шаг 8 (case_ver ожидания ≠ ver дела → reference_stale_version) снят",
      [E(RULES,
         L('        return "reference_stale_version"'),
         L('        pass                                      # M3: версия ответа не сверяется'))]),
    M("M4", "M4 `recover` возвращает `in_flight` в `planned`",
      "Store.recover: захват своей роли in_flight → planned/post вместо flight_unknown (повторная публикация/исполнение)",
      [E(STORE,
         L('                    self._exp_set(tx, e, state="flight_unknown", next_check=nc)'),
         L('                    self._exp_set(tx, e, state="planned", next_check="post")   # M4: in_flight → planned'))]),
    M("M5", "M5 `close_case` без блокеров",
      "Store.close_case: блокеры в транзакции не считаются (bl = [])",
      [E(STORE,
         L('            bl = self._blockers_tx(tx, case)'),
         L('            bl = []                                                   # M5: close_case без блокеров'))]),
    M("M6", "M6 ступень 4 по `staff_answer`",
      "rules.stage_allowed: staff_answer допущен свидетельством ступени 4 (_KIND_STAGES) и снят из _FORBIDDEN_4_5",
      [E(RULES,
         '_KIND_STAGES = {"post": (1,), ',
         '_KIND_STAGES = {"staff_answer": (4,), "post": (1,), '),
       E(RULES,
         '_FORBIDDEN_4_5 = ("staff_answer", "approval_yes", "agent_text", "bike_state")',
         '_FORBIDDEN_4_5 = ("approval_yes", "agent_text", "bike_state")  # M6')]),
    M("M7", "M7 без проверки ключа",
      "Store._mutate: поиск прежнего события по idem_key снят (повтор исполняется заново)",
      [E(STORE,
         L('            if prev is not None:',
           '                out = self._dup_out(tx, prev, sha, dup)'),
         L('            if False:                                                  # M7: без проверки ключа',
           '                out = self._dup_out(tx, prev, sha, dup)'))]),
    M("M8", "M8 CAS не проверяется",
      "Store._check_ver: сравнение expect_ver с версией дела снято",
      [E(STORE,
         L('        if case["ver"] != expect_ver:'),
         L('        if False:                                                      # M8: CAS не проверяется'))]),
    M("M9", "M9 автор по нику",
      "rules.answer_verdict шаг 7: автор не адресат по числовому id, но с ником (author_username) → принят",
      [E(RULES,
         L('    if not _is_int_id(author) or author not in ids:'),
         L('    if (not _is_int_id(author) or author not in ids) and not _s(answer.get("author_username")):   # M9'))]),
    M("M10", "M10 новое дело при смене срока/байка",
      "Store._reconcile_apply: при period_changed/bike_changed рождается новое rc_case с новой привязкой вместо подъёма "
      "версии прежнего дела",
      [E(STORE,
         L('        if res.get("bump_reason"):',
           '            bumped = self._bump(tx, case, res["bump_reason"], sref, source_name=sname)'),
         L('        if res.get("bump_reason") in ("period_changed", "bike_changed"):   # M10: новое дело вместо подъёма',
           '            cid = "RC-" + self.new_id()',
           '            tx.x("INSERT INTO rc_case(case_id, ver, state, link_state, attention, pause_no, origin, created_at, "',
           '                 "created_by, updated_at) VALUES (?,1,\'open\',\'ok\',0,0,?,?,?,?)",',
           '                 (cid, "intake", tx.now, tx.author(), tx.now))',
           '        elif res.get("bump_reason"):',
           '            bumped = self._bump(tx, case, res["bump_reason"], sref, source_name=sname)'))]),
    M("M10b", "M10b перепривязка по новому номеру (ревизия 1 §13: «молчаливая перепривязка по новому номеру»; «добавить "
              "контакт может только crm/одобряющий»)",
      "Store.add_contact: номер от агента/кода/не одобряющего привязывается к делу молча (source_kind=intake) вместо "
      "rejected(contact_source)",
      [E(STORE,
         L('                _stop_rej("contact_source", "контакт добавляет только сверка CRM или одобряющий по id")'),
         L('                sk = "intake"                                         # M10b: новый номер привязан молча'))]),
    M("M10b_v2", "M10b перепривязка по номеру (ветка §13 «superseded-номер → empty»)",
      "Store.resolve(client): _superseded_only и статус контакта в деле не сверяются — номер из U прочитанной строки "
      "привязывает клиента к делу",
      [E(STORE,
         L('                if self._superseded_only(tx, contact):',
           '                    return res("none", reason="contact_superseded")'),
         L('                pass                                                  # M10b: superseded-номер не сверяется')),
       E(STORE,
         L('                st = self._contact_status(tx, cid, contact)'),
         L('                st = "active"                                         # M10b: номер из U строки = привязка'))]),
    M("M11", "M11 аренда договора = только активная",
      "rules._pick_specific (без booking_id) и rules._pick_contract: кандидаты аренды договора — только current/"
      "current_unactivated (прошлая аренда старого договора не находится)",
      [E(RULES,
         L('        cands = [(r, c) for r, c in cands if c["cls"] != "unknown"]   # класс unknown — только по точному booking_id'),
         L('        cands = [(r, c) for r, c in cands if c["cls"] in ("current", "current_unactivated")]   # M11')),
       E(RULES,
         L('    pairs = [(r, c) for r, c in pairs if c["cls"] != "unknown"]'),
         L('    pairs = [(r, c) for r, c in pairs if c["cls"] in ("current", "current_unactivated")]   # M11'))]),
    M("M11b", "M11b `record_document` ставит `verified` без сверки привязки к `rental_id` этого дела (договор, совпавший "
              "одним полем, принят)",
      "Store.record_document(contract_signed): исход conflict (совпадение одним полем) принят как факт, окно договора и "
      "booking_id с привязкой rental_id не сверяются",
      [E(STORE,
         L('                    if oc == "conflict":',
           '                        _stop_rej("doc_conflict", _s(cr.get("reason")))',
           '                    facts = cr.get("facts") or []',
           '                    if oc != "fact" or len(facts) != 1:'),
         L('                    facts = cr.get("facts") or [{"doc_id": ext}]       # M11b: совпавший одним полем принят',
           '                    if len(facts) != 1:')),
       E(STORE,
         L('                    if _s(cr.get("window")) != "%s…%s" % (rr["start_day"], rr["end_day"]):'),
         L('                    if False:                                         # M11b: окно с привязкой не сверяется')),
       E(STORE,
         L('                    if fbk and _s(rr["booking_id"]) and fbk != _s(rr["booking_id"]):'),
         L('                    if False:                                         # M11b: booking_id с привязкой не сверяется'))]),
    M("M12", "M12 пустой `ask`",
      "rules._pick_unknown: ask = '' у любого unknown выбора",
      [E(RULES,
         L('            "ask": ask or ask_for(cands, purpose, intent), "reason": reason}'),
         L('            "ask": "", "reason": reason}                            # M12: пустой ask'))]),
    M("M13", "M13 внимание игнорируется",
      "Store.propose_client_notice: проверка case.attention снята (намерение клиенту при вмешательстве человека)",
      [E(STORE,
         L('            if case["attention"]:') + '                _stop_rej("attention", ',
         L('            if False:                                                 # M13: внимание игнорируется')
         + '                _stop_rej("attention", ')]),
    M("M14", "M14 клетка закрывает деньги",
      "rules.obligation_verdict(cell): клетка со значением > 0 → closed (by=cell) вместо open",
      [E(RULES,
         L('            return {"state": "open", "by": "", "why": "cell_value"}'),
         L('            return {"state": "closed", "by": "cell", "why": "cell_value"}   # M14: клетка закрывает деньги'))]),
    M("M14b", "M14b `write` закрывает деньги одной строкой кассы (при `MONEY_CLOSE_RULE=UNKNOWN` или без второго "
              "источника)",
      "rules._money_write_verdict: MONEY_CLOSE_RULE и второй источник (verified договор той же брони) не проверяются",
      [E(RULES,
         L('    if is_unknown(rule) or rule != "cash_and_second_source":',
           '        return {"state": cur, "by": "", "why": "param_unknown:MONEY_CLOSE_RULE"}'),
         L('    pass                                                            # M14b: правило не сверяется')),
       E(RULES,
         L('    if (not isinstance(second, Mapping) or _s(second.get("kind")) != "contract_signed"',
           '            or _s(second.get("status")) != "verified"',
           '            or _s(second.get("booking_id")) != _s(binding.get("booking_id"))):',
           '        return {"state": cur, "by": "", "why": "second_source_missing"}'),
         L('    pass                                                            # M14b: второй источник не нужен'))]),
    M("M15", "M15 `open_case` без обязательств",
      "Store._open_case_tx: обязательный набор required_obligations не рождается",
      [E(STORE,
         L('        for ob in R.required_obligations(row, self.params):'),
         L('        for ob in []:                                                  # M15: open_case без обязательств'))]),
    M("M16", "M16 `on_readback` пишет 5 без 4",
      "Store.on_readback: проверка ступени 5 считает ступень 4 записанной (prior ∪ {physically_done})",
      [E(STORE,
         L('                    ok, code = self._stage_check(tx, case, task, "result_recorded", ev, by)'),
         L('                    ok, code = self._stage_check(tx, case, task, "result_recorded", ev, by,',
           '                                                 prior=self._stage_names(tx, task["task_id"]) | set(["physically_done"]))   # M16'))]),
    M("M17", "M17 `recover` без учёта роли",
      "Store.recover: условие claimed_by = роль снято в выборках rc_expect и rc_notice (рестарт одной роли трогает "
      "захваты другой)",
      [E(STORE,
         L('            for e in tx.q("SELECT * FROM rc_expect WHERE claimed_by=? AND claim_boot IS NOT NULL AND claim_boot<>? "'),
         L('            for e in tx.q("SELECT * FROM rc_expect WHERE ?<>\'\' AND claim_boot IS NOT NULL AND claim_boot<>? "  # M17')),
       E(STORE,
         L('            for n in tx.q("SELECT * FROM rc_notice WHERE state=\'drafting\' AND claimed_by=? AND claim_boot IS NOT NULL "'),
         L('            for n in tx.q("SELECT * FROM rc_notice WHERE state=\'drafting\' AND ?<>\'\' AND claim_boot IS NOT NULL "  # M17'))]),
    M("M18", "M18 сверка без `observed_at`",
      "Store.reconcile_rental и rules.reconcile: сравнение observed_at чтения с применённым снято (старое чтение после "
      "нового применяется)",
      [E(STORE,
         L('            if obs <= float(b["observed_at"]):'),
         L('            if False:                                                 # M18: сверка без observed_at')),
       E(RULES,
         L('    if prev is not None and (observed_at is None or float(observed_at) <= float(prev)):'),
         L('    if False:                                                       # M18: сверка без observed_at'))]),
    M("M19", "M19 будущие брони выброшены из претендентов кассы",
      "rules.cash_claimants: ветка pre_start (касса до начала незавершённой строки) всегда пропускается",
      [E(RULES,
         L('            if pre_n is not None and (sd - d).days > pre_n:',
           '                continue'),
         L('            continue                                                # M19: будущая бронь не претендент'))]),
    M("M20", "M20 ключ без хеша",
      "Store._dup_out: тот же idem_key с другим payload_sha → duplicate вместо conflict(idem_payload_mismatch)",
      [E(STORE,
         L('        if prev["payload_sha"] != sha:'),
         L('        if False:                                                      # M20: ключ без хеша'))]),
    M("M21", "M21 `return` через `_rental_for`",
      "rules.pick(return/debt): при нескольких «в аренде» берётся самая свежая начавшаяся (семантика "
      "bike_position._rental_for, без упоминания имени) вместо unknown(two_active)",
      [E(RULES,
         L('            return _pick_unknown("two_active", ["which_rental"], [_cand(r, c) for r, c in cands], purpose, intent)'),
         L('            cands = [max(cands, key=lambda rc: rc[1]["start_day"] or "")]   # M21: аренда момента (_rental_for)'))]),
    M("M22", "M22 `client` без фильтра контакта для booking_id",
      "rules._pick_client(intent=specific) с booking_id: поиск по всем строкам двери, а не только по строкам контакта",
      [E(RULES,
         L('        return _pick_specific(all_rows, pairs, query, intent, params)'),
         L('        return _pick_specific(all_rows, classified if query.get("booking_id") else pairs, query, intent,',
           '                              params)                         # M22: booking_id без фильтра контакта'))]),
    M("M23", "M23 `execute` на справке",
      "Store._judge_answer: data.execute = True при «да» на живом ожидании и при справочном вердикте (порча выхода "
      "вызова; та же порча в вычислении колонки execute ловится CHECK rc_answer — это проверка схемы, а не наборов)",
      [E(STORE,
         L('                "decision": out_decision, "execute": bool(execute), "readback_exp_id": rb_id,'),
         L('                "decision": out_decision, "execute": bool(execute) or (decision == "yes" and live),   # M23',
           '                "readback_exp_id": rb_id,'))]),
    M("M24", "M24 `human_mark` со ссылкой ответа",
      "rules.stage_allowed(human_mark): запрет act_ref = chat:msg_id ответа снят (ответ/«да» превращается в ступень 3–4)",
      [E(RULES,
         L('                return False, "evidence_forbidden"            # «да»/ответ не превращается в ступень 3–4 (B3-3)'),
         L('                pass                                          # M24: human_mark со ссылкой ответа'))]),
    M("M25", "M25 `open_case` без проверки продолжения",
      "Store._open_case_tx: rules.continuation не зовётся (новая строка того же клиента — сразу новое дело)",
      [E(STORE,
         L('        cands = [] if force_new else R.continuation(row, bindings, self.params)'),
         L('        cands = []                                                     # M25: без проверки продолжения'))]),
    M("M26", "M26 `tick` не пропускает вопросы дела",
      "подделка staff_ask (tests/rental_case_fakes.py) due()/tick(): пропуск записей managed_by=rental_case снят (S3). "
      "Настоящий tick — staff_ask.py (полоса К5); в К4 сторона tick есть только у подделки шва",
      [E(FAKES,
         L('            if a.get("managed_by") == "rental_case":',
           '                continue'),
         L('            pass                                                     # M26: tick не пропускает вопросы дела'))]),
    M("M27", "M27 `due_expectations` отдаёт ожидание по возрасту при `WAIT_BEFORE_AGENTS=UNKNOWN` (технический срок "
             "вместо бизнес-срока)",
      "Store._business_due: при WAIT_BEFORE_AGENTS/BUSINESS_HOURS = UNKNOWN срок = время поста + 10800 с (3 ч)",
      [E(STORE,
         L('        if wait is None or R.is_unknown(hours) or start is None:',
           '            return None'),
         L('        if start is None:',
           '            return None',
           '        if wait is None or R.is_unknown(hours):',
           '            return float(start) + 10800.0                              # M27: технический срок 3 ч'))]),
    M("M28", "M28 вмешательство текстом на канале без паузы WA не ставит внимания",
      "Store.on_human_intervention (канал ≠ wa): kind=text внимания не ставит",
      [E(STORE,
         L('                attention = True if R.is_unknown(exempt) else (_s(kind) not in set(exempt or ()))'),
         L('                attention = _s(kind) != "text" and (True if R.is_unknown(exempt)',
           '                                                    else (_s(kind) not in set(exempt or ())))   # M28'))]),
    M("M29", "M29 `bike_state` принят свидетельством ступени 4/5",
      "rules.stage_allowed: bike_state допущен свидетельством ступеней 4 и 5 (_KIND_STAGES) и снят из _FORBIDDEN_4_5",
      [E(RULES,
         '_KIND_STAGES = {"post": (1,), ',
         '_KIND_STAGES = {"bike_state": (4, 5), "post": (1,), '),
       E(RULES,
         '_FORBIDDEN_4_5 = ("staff_answer", "approval_yes", "agent_text", "bike_state")',
         '_FORBIDDEN_4_5 = ("staff_answer", "approval_yes", "agent_text")  # M29')]),
    M("M29_v2", "M29 booking_id `bike_state` принят привязкой",
      "Store.record_fact(bike_state): booking_id листа (booking_id_seen) пишется в текущую привязку rc_rental",
      [E(STORE,
         L('            return self._ok(tx, case_id, case["ver"], data={"fact_id": fid, "fkey": fk})'),
         L('            if kind == "bike_state" and _s(value.get("booking_id_seen")):   # M29: booking_id листа — привязкой',
           '                tx.x("UPDATE rc_rental SET booking_id=? WHERE case_id=? AND current=1",',
           '                     (_s(value.get("booking_id_seen")), case_id))',
           '            return self._ok(tx, case_id, case["ver"], data={"fact_id": fid, "fkey": fk})'))]),
    M("M30", "M30 срок 1800 применён к карточке брони",
      "rules.answer_verdict шаг 9: у action=booking срок карточки = 1800 с (как у activate/close)",
      [E(RULES,
         L('        ttl = _sub(_p(params, "APPROVAL_TTL_S"), _s(exp.get("action")))'),
         L('        ttl = _sub(_p(params, "APPROVAL_TTL_S"), _s(exp.get("action")))',
           '        if _s(exp.get("action")) == "booking":',
           '            ttl = 1800                                              # M30: 1800 к карточке брони'))]),
    M("M31", "M31 покрытие периода выводится из даты подписи договора внутри общей (продлённой) аренды вместо доказанного "
             "cover_from/cover_to",
      "Store._documents_for_tx: verified документ, чья дата подписи внутри ТЕКУЩЕЙ (продлённой) привязки, при периоде "
      "внутри неё → covers (договор первоначального срока подходит к периоду продления)",
      [E(STORE,
         L('                res = R.document_coverage(base, (period[0], period[1]))'),
         L('                res = R.document_coverage(base, (period[0], period[1]))',
           '                _sd = _s(d["signed_at"])[:10]',
           '                if (res.get("code") == "unknown" and d["status"] == "verified" and _sd',
           '                        and _s(cur.get("start_day")) <= _sd <= _s(cur.get("end_day"))',
           '                        and _s(cur.get("start_day")) <= _s(period[0]) and _s(period[1]) <= _s(cur.get("end_day"))):',
           '                    res = {"code": "covers", "why": "signed_within_rental"}   # M31: покрытие из даты подписи'))]),
    M("M31b", "M31b `record_document` заполняет `cover_*` сроком привязки на момент записи (откат `binding_at_verify`)",
      "Store.record_document(verified contract_signed): cover_from/cover_to = срок привязки rental_id на момент записи, "
      "cover_basis=document (вставка и перевод unverified → verified)",
      [E(STORE, _DOC_INSERT_CALL, _DOC_INSERT_CALL + _M31B_BLOCK_INSERT),
       E(STORE, _DOC_UPDATE_EVENT, _M31B_BLOCK_UPDATE + _DOC_UPDATE_EVENT)]),
    M("M31c", "M31c покрытие ставится без подтверждения одобряющего с явными датами и источником (ветка «human_binding без "
              "дат»)",
      "Store.record_document(human_binding одобряющего): cover_* = срок привязки rental_id, cover_basis=human_confirmed "
      "без явных дат и источника дат",
      [E(STORE, _DOC_INSERT_CALL, _DOC_INSERT_CALL + _M31C_BLOCK_INSERT),
       E(STORE, _DOC_UPDATE_EVENT, _M31C_BLOCK_UPDATE + _DOC_UPDATE_EVENT)]),
    M("M31c_v2", "M31c (ветка «подтверждение не одобряющим или без source_ref»)",
      "Store.confirm_document_coverage: проверка одобряющего по id и обязательность source_ref/act_ref сняты",
      [E(STORE,
         L('            if not self._approver(by):',
           '                _stop_rej("approver_unknown", "покрытие подтверждает только одобряющий по id")'),
         L('            pass                                                      # M31c: подтверждение не одобряющим')),
       E(STORE,
         L('            if cf is None or ct is None or cf > ct or not _s(source_ref) or not _s(act_ref):'),
         L('            if cf is None or ct is None or cf > ct:                   # M31c: без source_ref/act_ref'))]),
    M("M31c_v3", "M31c (ветка «documents_for(period=None) подставляет срок текущей привязки»)",
      "Store._documents_for_tx: period=None → период = срок текущей привязки",
      [E(STORE,
         L('        valid_period = False'),
         L('        valid_period = False',
           '        if period is None and cur.get("start_day") and cur.get("end_day"):',
           '            period = (cur["start_day"], cur["end_day"])               # M31c: подставлен срок привязки'))]),
)

# Перечень DESIGN §13 (К4-C20): M1–M31 с M1b, M10b, M11b, M14b, M31b, M31c — каждый обязан быть в MUTANTS.
DESIGN_IDS = tuple(["M%d" % i for i in range(1, 32)] + ["M1b", "M10b", "M11b", "M14b", "M31b", "M31c"])


# ---------------------------------------------------------------------------------------------------------------------
# Общие мелочи
# ---------------------------------------------------------------------------------------------------------------------

_PRINT_LOCK = threading.Lock()


def say(msg):
    with _PRINT_LOCK:
        sys.stdout.write(msg + "\n")
        sys.stdout.flush()


def _utc_now():
    return datetime.datetime.now(datetime.timezone.utc)


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _norm(path):
    return os.path.normpath(os.path.abspath(path))


def _fwd(path):
    return path.replace("\\", "/")


def _read_bytes(path):
    with open(path, "rb") as f:
        return f.read()


def _write_bytes(path, data):
    with open(path, "wb") as f:
        f.write(data)


def _write_json(path, obj):
    part = path + ".part"
    with open(part, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(part, path)


def _set_aside(path, stamp, preserved):
    """Отложить существующий файл/каталог переименованием (ничего не удаляется)."""
    if not os.path.lexists(path):
        return
    n = 0
    while True:
        cand = "%s.prev-%s%s" % (path, stamp, ("-%d" % n) if n else "")
        if not os.path.lexists(cand):
            break
        n += 1
    os.rename(path, cand)
    preserved.append({"from": _fwd(path), "to": _fwd(cand)})


def check_inventory():
    """Каждый мутант DESIGN §13 есть в MUTANTS ровно один раз; правки — тройки строк."""
    ids = [m["id"] for m in MUTANTS]
    problems = []
    for mid in DESIGN_IDS:
        if mid not in ids:
            problems.append("нет мутанта %s" % mid)
    for mid in set(ids):
        if ids.count(mid) > 1:
            problems.append("мутант %s повторён" % mid)
    for m in MUTANTS:
        if not m["edits"]:
            problems.append("%s: нет правок" % m["id"])
        for e in m["edits"]:
            if len(e) != 3 or not all(isinstance(x, str) for x in e) or e[1] == e[2] or not e[1]:
                problems.append("%s: правка не вида (файл, старое, новое)" % m["id"])
        for s in m["suites"]:
            if s in SUITES_EXCLUDED:
                problems.append("%s: набор %s исключён (%s)" % (m["id"], s, SUITES_EXCLUDED[s]))
    return problems


# ---------------------------------------------------------------------------------------------------------------------
# Копия и порча
# ---------------------------------------------------------------------------------------------------------------------


def _imported_tops(src):
    tree = ast.parse(src)
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                out.add(a.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            out.add(node.module.split(".")[0])
    return out


def copy_plan(src_root):
    """(основные файлы, зависимости): rental_case*.py и tests/*rental_case*.py + замыкание локальных импортов по AST
    (модули корня <имя>.py, которые импортируют основные файлы или их зависимости)."""
    main = sorted(_fwd(os.path.relpath(p, src_root)) for p in glob.glob(os.path.join(src_root, "rental_case*.py")))
    main += sorted(_fwd(os.path.relpath(p, src_root))
                   for p in glob.glob(os.path.join(src_root, "tests", "*rental_case*.py")))
    seen = set(main)
    deps = []
    queue = list(main)
    while queue:
        rel = queue.pop(0)
        try:
            src = _read_bytes(os.path.join(src_root, rel)).decode("utf-8")
            tops = _imported_tops(src)
        except (OSError, UnicodeDecodeError, SyntaxError):
            continue
        for name in sorted(tops):
            cand = name + ".py"
            if cand in seen or not os.path.isfile(os.path.join(src_root, cand)):
                continue
            seen.add(cand)
            deps.append(cand)
            queue.append(cand)
    return main, sorted(deps)


def make_copy(src_root, dst, files):
    os.makedirs(dst)
    for rel in files:
        target = os.path.join(dst, rel)
        parent = os.path.dirname(target)
        if not os.path.isdir(parent):
            os.makedirs(parent)
        shutil.copyfile(os.path.join(src_root, rel), target)


def apply_edits(root, edits):
    """→ (ok, причина, {файл: (старые байты, новые байты)}). Фрагмент обязан встретиться ровно один раз — и в исходнике,
    и в тексте на момент своей правки; испорченный файл разбирается как 3.8 и компилируется."""
    orig = {}
    cur = {}
    for rel, old, new in edits:
        if rel not in orig:
            path = os.path.join(root, rel)
            if not os.path.isfile(path):
                return False, "нет файла %s в копии" % rel, {}
            raw = _read_bytes(path)
            try:
                orig[rel] = raw.decode("utf-8")
            except UnicodeDecodeError as e:
                return False, "%s не UTF-8: %s" % (rel, e), {}
            cur[rel] = orig[rel]
        n0 = orig[rel].count(old)
        n1 = cur[rel].count(old)
        if n0 != 1 or n1 != 1:
            return False, "фрагмент найден %d раз(а) в исходнике %s (на момент правки — %d); нужен ровно 1: %r" % (
                n0, rel, n1, old[:120]), {}
        cur[rel] = cur[rel].replace(old, new, 1)
    changed = {}
    for rel in orig:
        src = cur[rel]
        if src == orig[rel]:
            return False, "%s: порча не изменила текст" % rel, {}
        if "\r" in src:
            return False, "%s: в порче есть \\r" % rel, {}
        try:
            ast.parse(src, filename=rel, feature_version=(3, 8))
            compile(src, rel, "exec", dont_inherit=True)
        except SyntaxError as e:
            return False, "%s: испорченный файл не разбирается (строка %s: %s)" % (rel, e.lineno, e.msg), {}
        changed[rel] = (orig[rel].encode("utf-8"), src.encode("utf-8"))
    for rel, (_old, new_bytes) in changed.items():
        _write_bytes(os.path.join(root, rel), new_bytes)
    return True, "", changed


def write_diff(path, changed):
    parts = []
    for rel in sorted(changed):
        a, b = changed[rel]
        parts.extend(difflib.unified_diff(a.decode("utf-8").splitlines(True), b.decode("utf-8").splitlines(True),
                                          fromfile="a/" + rel, tofile="b/" + rel, n=2))
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("".join(parts))


# ---------------------------------------------------------------------------------------------------------------------
# Прогон раннера и разбор упавших проверок
# ---------------------------------------------------------------------------------------------------------------------

_UT_FAIL_RE = re.compile(r"^(FAIL|ERROR): (\S+) \(([^)\s]+)\)(.*)$")
_SUITE_PREFIX = {"rules": "test_rental_case_rules.", "store": "test_rental_case_store.",
                 "accept": "test_rental_case_accept.", "seam": "test_rental_case_seam."}


def _read_text(path):
    try:
        data = _read_bytes(path)
    except (OSError, TypeError):
        return ""
    return data.decode("utf-8", "replace").replace("\r\n", "\n").replace("\r", "\n")


def _short(text, n=220):
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[:n - 1] + "…"


def failed_checks(entry):
    """Упавшие проверки набора по его журналу: строки FAIL/ERROR unittest и ПРОВАЛ/ИСКЛЮЧЕНИЕ/FAIL демо."""
    suite = entry.get("suite")
    out = []
    text = _read_text(entry.get("log"))
    for line in text.splitlines():
        m = _UT_FAIL_RE.match(line)
        if m:
            dotted = m.group(3)
            for pref in ("__main__.", _SUITE_PREFIX.get(suite) or "__main__."):
                if dotted.startswith(pref):
                    dotted = dotted[len(pref):]
            out.append("%s: %s %s%s" % (suite, m.group(1), dotted, _short(m.group(4), 80) if m.group(4).strip() else ""))
            continue
        s = line.strip()
        if (s.startswith("DEMO ") and ("ПРОВАЛ" in s or "ИСКЛЮЧЕНИЕ" in s)) or (s.startswith("REPEAT ") and "FAIL" in s):
            out.append("%s: %s" % (suite, _short(s)))
    if not out:
        out.append("%s: %s exit=%s%s" % (suite, entry.get("status"), entry.get("exit"),
                                         (" (" + _short(entry.get("note"), 120) + ")") if entry.get("note") else ""))
    seen, uniq = set(), []
    for x in out:
        if x not in seen:
            seen.add(x)
            uniq.append(x)
    return uniq


def run_runner(args, root, run_label, suites, log_path):
    cmd = [sys.executable, _norm(args.runner), "--root", root, "--label", run_label, "--timeout", str(args.timeout)]
    if args.runs_base:
        cmd += ["--runs-base", args.runs_base]
    for s in suites:
        cmd += ["--only", s]
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    t0 = time.monotonic()
    with open(log_path, "wb") as logf:
        try:
            proc = subprocess.Popen(cmd, cwd=root, env=env, stdin=subprocess.DEVNULL, stdout=logf,
                                    stderr=subprocess.STDOUT)
            rc = proc.wait()
        except OSError as e:
            logf.write(("mutants: cannot start runner: %s\n" % e).encode("utf-8"))
            rc = None
    secs = round(time.monotonic() - t0, 1)
    runs_base = _norm(args.runs_base) if args.runs_base else _norm(DEFAULT_RUNS_BASE)
    res_path = os.path.join(runs_base, run_label, "results.json")
    doc = None
    try:
        with open(res_path, encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError):
        doc = None
    return [_fwd(c) for c in cmd], rc, secs, _fwd(res_path), doc


def judge(rc, doc):
    """→ (status, by, suites, note). KILLED: раннер ≠ 0 и упал набор (FAIL/TIMEOUT); SURVIVED: раннер 0 и все PASS;
    иначе — ошибка раннера (NOT_APPLIED с причиной, «убийством» не считается)."""
    suites = {}
    if doc is not None:
        for e in doc.get("suites") or []:
            suites[e.get("suite")] = e.get("status")
    if doc is None or not doc.get("complete"):
        return "NOT_APPLIED", [], suites, "раннер не дал полного results.json (код %s)" % rc
    failing = [e for e in doc.get("suites") or [] if e.get("status") in ("FAIL", "TIMEOUT")]
    other = [e for e in doc.get("suites") or [] if e.get("status") not in ("PASS", "FAIL", "TIMEOUT")]
    if rc == 0 and not failing and not other:
        return "SURVIVED", [], suites, ""
    if rc not in (0, None) and failing:
        by = []
        for e in failing:
            by.extend(failed_checks(e))
        note = ("и не PASS без провала: %s" % ", ".join("%s=%s" % (e.get("suite"), e.get("status")) for e in other)
                if other else "")
        return "KILLED", by, suites, note
    return "NOT_APPLIED", [], suites, "ошибка раннера: код %s, наборы %s" % (rc, suites)


# ---------------------------------------------------------------------------------------------------------------------
# Один мутант (или контроль)
# ---------------------------------------------------------------------------------------------------------------------


def run_one(args, m, ctx):
    mid = m["id"]
    mdir = os.path.join(ctx["label_dir"], mid)
    entry = {"status": None, "by": [], "design": m["design"], "model": m["model"],
             "edits": [{"file": e[0], "old_sha16": _sha(e[1].encode("utf-8"))[:16], "old_lines": e[1].count("\n") or 1}
                       for e in m["edits"]],
             "files": sorted(set(e[0] for e in m["edits"])), "suites": list(m["suites"]), "root": _fwd(mdir),
             "note": ""}
    _set_aside(mdir, ctx["stamp"], ctx["preserved"])
    try:
        make_copy(ctx["src_root"], mdir, ctx["files"])
    except OSError as e:
        entry.update(status="NOT_APPLIED", note="копия не сделана: %s" % e)
        return mid, entry
    if m["edits"]:
        ok, why, changed = apply_edits(mdir, m["edits"])
        if not ok:
            entry.update(status="NOT_APPLIED", note=why)
            say("%-8s NOT_APPLIED  %s" % (mid, why))
            return mid, entry
        diff_path = os.path.join(ctx["diffs_dir"], mid + ".diff")
        write_diff(diff_path, changed)
        entry["diff"] = _fwd(diff_path)
        entry["mutated_sha256"] = dict((rel, _sha(b)) for rel, (_a, b) in sorted(changed.items()))
    if args.apply_only:
        entry.update(status="APPLIED", note="--apply-only: раннер не запускался")
        say("%-8s APPLIED" % mid)
        return mid, entry
    run_label = "mut-%s-%s" % (args.label, mid)
    log_path = os.path.join(ctx["logs_dir"], mid + ".runner.log")
    cmd, rc, secs, res_path, doc = run_runner(args, mdir, run_label, m["suites"], log_path)
    status, by, suites, note = judge(rc, doc)
    entry.update(status=status, by=by, runner_cmd=cmd, runner_exit=rc, seconds=secs, runner_results=res_path,
                 runner_log=_fwd(log_path), suite_status=suites, note=note)
    shown = status
    if mid == CONTROL_ID:
        shown = "PASS" if status == "SURVIVED" else "FAIL"
    say("%-8s %-11s %6.1fs  %s" % (mid, shown, secs, ("; ".join(by[:2]) + (" …(+%d)" % (len(by) - 2) if len(by) > 2
                                                                           else "")) if by else note))
    return mid, entry


# ---------------------------------------------------------------------------------------------------------------------
# Главное
# ---------------------------------------------------------------------------------------------------------------------


def parse_args(argv):
    p = argparse.ArgumentParser(description="K4 rental_case mutants harness (see module docstring)")
    p.add_argument("--label", required=True, help="метка прогона: каталог <base>/<label>/, раннер mut-<label>-<Mid>")
    p.add_argument("--only-mutant", action="append", default=None,
                   help="Mid (повторяемый; можно через запятую); без него — все мутанты")
    p.add_argument("--jobs", type=int, default=1, help="мутантов параллельно (1)")
    p.add_argument("--timeout", type=float, default=DEFAULT_SUITE_TIMEOUT,
                   help="таймаут набора раннера, с (%d)" % DEFAULT_SUITE_TIMEOUT)
    p.add_argument("--apply-only", action="store_true", help="только копии и порча (проверка фрагментов), без раннера")
    p.add_argument("--base", default=DEFAULT_BASE, help="каталог мутантов (%s)" % DEFAULT_BASE)
    p.add_argument("--runs-base", default=None, help="runs-base раннера (по умолчанию его собственный %s)"
                                                     % DEFAULT_RUNS_BASE)
    p.add_argument("--src-root", default=DEFAULT_SRC_ROOT, help="откуда копировать (по умолчанию родитель tests/)")
    p.add_argument("--runner", default=DEFAULT_RUNNER, help="раннер наборов (по умолчанию tests/run_rental_case_suites.py)")
    return p.parse_args(argv)


def main(argv=None):
    try:
        sys.stdout.reconfigure(errors="backslashreplace")
    except (AttributeError, ValueError):
        pass
    args = parse_args(argv)
    if not LABEL_RE.match(args.label or ""):
        sys.stderr.write("rental_case_mutants: --label must match %s\n" % LABEL_RE.pattern)
        return 2
    if args.jobs < 1 or args.timeout <= 0:
        sys.stderr.write("rental_case_mutants: --jobs >= 1, --timeout > 0\n")
        return 2
    problems = check_inventory()
    if problems:
        sys.stderr.write("rental_case_mutants: перечень мутантов неполон/неверен:\n  %s\n" % "\n  ".join(problems))
        return 2
    by_id = dict((m["id"], m) for m in MUTANTS)
    wanted = []
    for item in args.only_mutant or []:
        for mid in item.split(","):
            mid = mid.strip()
            if mid and mid not in wanted:
                wanted.append(mid)
    unknown = [w for w in wanted if w not in by_id]
    if unknown:
        sys.stderr.write("rental_case_mutants: unknown --only-mutant %s; known: %s\n"
                         % (unknown, ", ".join(m["id"] for m in MUTANTS)))
        return 2
    selected = [m for m in MUTANTS if not wanted or m["id"] in wanted]
    src_root = _norm(args.src_root)
    if not os.path.isfile(os.path.join(src_root, STORE)) or not os.path.isfile(_norm(args.runner)):
        sys.stderr.write("rental_case_mutants: нет %s в --src-root или нет раннера %s\n" % (STORE, args.runner))
        return 2
    base = _norm(args.base)
    if not os.path.isdir(os.path.dirname(base)):
        sys.stderr.write("rental_case_mutants: нет родителя каталога мутантов: %s\n" % os.path.dirname(base))
        return 2

    started = _utc_now()
    stamp = started.strftime("%Y%m%d-%H%M%S")
    label_dir = os.path.join(base, args.label)
    preserved = []
    os.makedirs(label_dir, exist_ok=True)
    results_path = os.path.join(label_dir, "results.json")
    _set_aside(results_path, stamp, preserved)
    diffs_dir = os.path.join(label_dir, "_diffs")
    logs_dir = os.path.join(label_dir, "_logs")
    for d in (diffs_dir, logs_dir):
        _set_aside(d, stamp, preserved)
        os.makedirs(d)
    main_files, deps = copy_plan(src_root)
    files = main_files + deps
    src_sha = dict((rel, _sha(_read_bytes(os.path.join(src_root, rel)))) for rel in files)
    ctx = {"label_dir": label_dir, "stamp": stamp, "preserved": preserved, "src_root": src_root, "files": files,
           "diffs_dir": diffs_dir, "logs_dir": logs_dir}
    meta = {
        "schema": "k4-rental-case-mutants/1",
        "label": args.label,
        "mode": "apply_only" if args.apply_only else "run",
        "harness": _fwd(os.path.abspath(__file__)),
        "harness_sha256": _sha(_read_bytes(os.path.abspath(__file__))),
        "runner": _fwd(_norm(args.runner)),
        "runner_sha256": _sha(_read_bytes(_norm(args.runner))),
        "src_root": _fwd(src_root),
        "copied_main": main_files,
        "copied_deps": deps,
        "src_sha256": src_sha,
        "python": sys.version.split()[0],
        "started_at": _iso(started),
        "finished_at": None,
        "suites_default": list(SUITES_DEFAULT),
        "suites_excluded": SUITES_EXCLUDED,
        "suite_timeout_s": args.timeout,
        "jobs": args.jobs,
        "selected": [m["id"] for m in selected],
        "design_ids": list(DESIGN_IDS),
        "preserved": preserved,
        "control": None,
        "summary": None,
    }
    results = {"_meta": meta}
    _write_json(results_path, results)
    say("mutants: label=%s, мутантов %d, копируются %d файл(а) (+%d зависимост.), наборы %s"
        % (args.label, len(selected), len(main_files), len(deps), ",".join(SUITES_DEFAULT)))

    control = {"id": CONTROL_ID, "design": "контроль: та же копия без порчи", "model": "—", "edits": (),
               "suites": SUITES_DEFAULT}
    _cid, centry = run_one(args, control, ctx)
    if not args.apply_only:
        centry["status"] = "PASS" if (centry.get("status") == "SURVIVED") else "FAIL"
    else:
        centry["status"] = "COPIED"
    meta["control"] = centry
    _write_json(results_path, results)
    if not args.apply_only and centry["status"] != "PASS":
        say("CONTROL FAIL: копия без порчи не проходит наборы — исходы мутантов не судимы (%s; %s)"
            % (centry.get("note"), "; ".join(centry.get("by") or [])))
        for m in selected:
            results[m["id"]] = {"status": "NOT_APPLIED", "by": [], "design": m["design"], "model": m["model"],
                                "note": "контроль не прошёл — мутант не запускался"}
        meta["finished_at"] = _iso(_utc_now())
        meta["summary"] = {"total": len(selected), "killed": 0, "survived": [], "not_applied": [m["id"] for m in selected],
                           "control": "FAIL", "exit_code": 2}
        _write_json(results_path, results)
        return 2

    out = {}
    if args.jobs == 1:
        for m in selected:
            mid, entry = run_one(args, m, ctx)
            out[mid] = entry
            results[mid] = entry
            _write_json(results_path, results)
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
            futs = [pool.submit(run_one, args, m, ctx) for m in selected]
            for fut in concurrent.futures.as_completed(futs):
                mid, entry = fut.result()
                out[mid] = entry
                results[mid] = entry
                _write_json(results_path, results)
    ordered = {"_meta": meta}
    for m in selected:
        ordered[m["id"]] = out[m["id"]]
    results = ordered

    if args.apply_only:
        bad = [m["id"] for m in selected if out[m["id"]]["status"] != "APPLIED"]
        meta["summary"] = {"total": len(selected), "applied": len(selected) - len(bad), "not_applied": bad,
                           "exit_code": 0 if not bad else 1}
    else:
        killed = [m["id"] for m in selected if out[m["id"]]["status"] == "KILLED"]
        survived = [m["id"] for m in selected if out[m["id"]]["status"] == "SURVIVED"]
        not_applied = [m["id"] for m in selected if out[m["id"]]["status"] == "NOT_APPLIED"]
        by_suite = {}
        for mid in killed:
            for s, st in sorted((out[mid].get("suite_status") or {}).items()):
                if st in ("FAIL", "TIMEOUT"):
                    by_suite.setdefault(s, []).append(mid)
        meta["summary"] = {"total": len(selected), "killed": len(killed), "survived": survived,
                           "not_applied": not_applied, "killed_by_suite": by_suite, "control": "PASS",
                           "exit_code": 0 if len(killed) == len(selected) else 1}
    meta["finished_at"] = _iso(_utc_now())
    _write_json(results_path, results)

    say("")
    say("%-8s %-11s %s" % ("Mid", "status", "упавшие проверки (первые) / причина"))
    for m in selected:
        e = out[m["id"]]
        tail = "; ".join(e.get("by")[:3]) + (" …(+%d)" % (len(e["by"]) - 3) if len(e.get("by") or []) > 3 else "")
        say("%-8s %-11s %s" % (m["id"], e["status"], tail or e.get("note") or ""))
    s = meta["summary"]
    if args.apply_only:
        say("mutants --apply-only: применено %d из %d; не применено: %s" % (s["applied"], s["total"],
                                                                          ", ".join(s["not_applied"]) or "—"))
    else:
        say("mutants: убито %d / всего %d; выжили: %s; не применены: %s" % (
            s["killed"], s["total"], ", ".join(s["survived"]) or "—", ", ".join(s["not_applied"]) or "—"))
    say("results: %s" % _fwd(results_path))
    return s["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
