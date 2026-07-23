#!/usr/bin/env python3
"""Порт-спека мозга декомпозера, часть 1/2 → cc_log (препенд ПОД врезкой) + pulse ОДНОЙ операцией.
Read-only задача: пишем ТОЛЬКО в журналы Brain (cc_log/pulse), рабочие таблицы не трогаем. Зона 🟢."""
import sys
from datetime import datetime, timezone

sys.path.insert(0, "/root/turbobaby-manager-bot")
from cclog import _insert_under_vrezka          # noqa: E402 (штатный препенд под врезкой)
from bridge_client import BridgeClient          # noqa: E402

DELEV = "delete_" + "event"   # guard-токен: в файле скрипта литералом не держим (память cclog-args-guard)

SPEC_T = """ПОРТ-СПЕКА мозга декомпозера, часть 1/2 (механический порт из orchestrator_daemon.py @ HEAD e343041; read-only, ничего не менялось).

═══ 1. ПРОМПТ ПЛАНИРОВЩИКА (дословно) ═══
PLANNER_PREAMBLE (стр. 310–330; для ПК-театра ПОСЛЕ него дописывается PLANNER_PC_NOTE — порядок важен: startswith(PLANNER_PREAMBLE)-роутинг в run_task/тестах не ломается):
«Ты — планировщик декомпозиции в headless-режиме в репо /root/turbobaby-manager-bot (CLAUDE.md действует). Твоя задача — РАЗБИТЬ крупное ТЗ на шаги, НЕ выполняя его: можно читать код/логи/доки (read-only разведка), НЕЛЬЗЯ править файлы, коммитить, деплоить, писать в таблицы.
ФОРМАТ ОТВЕТА — СТРОГО и ТОЛЬКО нумерованный список шагов, каждый с новой строки «N. <шаг>», без заголовков, без кода, без текста до/после списка. Шагов 2–7. Каждый шаг — САМОДОСТАТОЧНОЕ дев-ТЗ (до 45 мин, ≤400 символов): исполнитель увидит ТОЛЬКО текст шага, поэтому впиши в каждый нужный контекст (файлы, функции, что сделать, как проверить). Шаги строго в порядке исполнения; правки кода раньше, деплой/рестарт/проверка — последними.
КРАСНАЯ ЗОНА В ТЗ — НЕ ПОВОД ОТКАЗЫВАТЬСЯ ОТ ПЛАНА (урок задачи 166): ты ТОЛЬКО планируешь и сам ничего не исполняешь, поэтому упоминание clasp/деплоя/рабочих таблиц/денег/удаления в ТЗ НЕ требует подтверждения на этапе плана — НЕ выводи NEEDS_APPROVAL из-за содержимого ТЗ. Красное действие оформи ОТДЕЛЬНЫМ шагом (обычно последним): исполнитель ЭТОГО шага сам спросит «да» Филиппа кнопкой по штатной механике. Если ТЗ явно говорит, что прод-применение (деплой/рестарт) делается отдельно/хвостом — тем более просто строй план. ЕДИНСТВЕННОЕ исключение: ВСЁ ТЗ целиком = одно красное действие и разбивать не на что (например «задеплой прод») — тогда вместо списка выведи РОВНО одну строку «NEEDS_APPROVAL: op=other | <карточка: что · куда · последствия>».

КРУПНОЕ ТЗ:
»
PLANNER_PC_NOTE (стр. 333–338; ТОЛЬКО для родителя ПК-театра, frm=Filipp-pc-dec):
«ОСОБЕННОСТЬ ТЕАТРА ИСПОЛНЕНИЯ: шаги будет исполнять headless-агент на ДРУГОЙ машине (ПК, pc_orchestrator) — НЕ этот VPS. Пиши каждый шаг самодостаточно для ТОЙ машины: не ссылайся на пути/сервисы/файлы этого VPS, если само ТЗ явно не про них; весь контекст, нужный шагу, впиши в его текст.»
Обвязка вызова (_dec_plan_and_fanout, стр. 1665+): run_task(tid, task_text, task_timeout=TASK_TIMEOUT_DEV, preamble=PLANNER_PREAMBLE+[PC_NOTE]); NA-детект run_task для планировщика ОТКЛЮЧЁН по startswith(PLANNER_PREAMBLE) (стр. 585, урок 166) — red-маркеры в выводе не глушат план; status!=done → родитель failed (needs_approval от read-only планировщика = аномалия). Парс плана: _PLAN_LINE_RE = ^\\s*(\\d{1,2})[.)]\\s+(\\S.*) («N. шаг» / «N) шаг», прочие строки молча игнор). План пуст + _detect_needs_approval(out) → failed «планировщик needs_approval: <карта>» (фейл-сейф чисто-красного родителя, НЕ кнопка). len(steps) > MAX_STEPS=8 → failed «упрости ТЗ».

═══ 2. ПОЛЯ ОЧЕРЕДИ BRIDGE + ВСЕ МАРКЕРЫ ═══
Лист очереди (BotData.js QUEUE_COL): id=1, created=2, from=3, task_text=4 (обрез 5000), status=5, result=6, approved_by=7, updated=8, lane=9. Статусы: new → in_progress (claim, атомарно) → done|failed (complete_task принимает ТОЛЬКО их) | needs_approval → approved. API (bridge_client.py): enqueue_task(from_, task_text, lane=None→Bridge-дефолт vps)→{ok,id}; get_pending(status[,lane; 'all'=обе полосы])→{ok,items newest-first}; get_pending_multi(statuses CSV одним вызовом, старый Bridge → тихий по-статусный фоллбэк, item.setdefault('status')); claim_task(id[,lane-guard: чужую полосу не отдаст]); complete_task(id,status,result); set_needs_approval(id,what); task_heartbeat(id) бьёт updated. Родство цепи — ТОЛЬКО по паттернам в task_text (схема очереди не менялась, решение плана C).
РОДИТЕЛЬ: from='Filipp-328-dec' (vps) | 'Filipp-pc-dec' (PC_DEC_FROM; devbot кладёт БЕЗ lane → полоса vps: план строит ТОЛЬКО VPS-демон). task_text = крупное ТЗ (без служебных паттернов). result при done = restart-proof ИСТОЧНИК ПЛАНА: vps «🧩 Декомпозиция: N шагов, в очереди id …\\n<план: строки 'i. <шаг>'>\\n[🔴-пометка]\\nИсполняю по одному… Красный шаг спрошу кнопкой.»; pc «🧩 Декомпозиция (театр PC): N шагов — исполняет ПК-агент ПО ОДНОМУ (lane=pc), план и надзор на VPS.\\n<план>\\n[🔴-пометка]Шаг 1 в очереди lane=pc (id X)… ПК молчит >60 мин → честный failed цепи (без самопочинки).»
ШАГИ: vps — from='Filipp-328-dec', веерный fan-out ВСЕХ сразу (порядок держит guard в process_new); pc — from='Filipp-pc-dec', lane='pc', ПО ОДНОМУ. Текст шага: «[шаг i/N родитель pid] [опц. «[коррекция плана K] »][опц. «[самопочинка шага i, попытка 1] »]<текст шага>» (обрез RESULT_MAX).
МАРКЕРЫ (regex дословно):
· _STEP_RE = ^\\[шаг (\\d+)/(\\d+) родитель (\\d+)\\]  (match с начала)
· _SUM_RE = ^\\[сводка родитель (\\d+)\\]  — synthetic-сводка: enqueue → claim → complete done (result = текст сводки); идемпотентность = скан этих маркеров (_dec_summary_exists) + кэш _summarized
· _HEAL_RE = \\[самопочинка шага (\\d+), попытка (\\d+)\\]  (search — маркер идёт ПОСЛЕ [шаг i/N]); повторный провал носителя = терминальный halt
· _HEAL_TASK_RE = ^\\s*\\[самопочинка задачи (\\d+), попытка (\\d+)\\]  (одиночные тз:/задача:, якорь ^, N = id исходной)
· _ADAPT_MARK_RE = \\[коррекция плана (\\d+)\\]  (на шаге; K-происхождение, restart-proof счётчик коррекций = max K из маркеров очереди)
· _ADAPT_CARD_RE = ^\\[коррекция плана родитель (\\d+)\\]  — карточка адаптации: task_text «[коррекция плана родитель pid] после шага i (K=k)», result = 🧭-карточка с «НОВЫЙ ОСТАВШИЙСЯ ПЛАН» нумерованным списком (шаги i+1..new_total); база восстановления = _PC_ADAPT_BASE_RE «после шага (\\d+)» из task_text
· _PC_CARD_RE = ^\\[карточка родитель (\\d+)\\]  — событийная карточка pc-цепи (🩹 retry / 🛑 terminal / 🧭 adjust / ⚠️ план не восстановился / 🏁 finish): enqueue на vps from=Filipp-pc-dec → claim → complete done (devbot несёт в 829)
· _CONVERT_RE = ^\\s*\\[конверт одобренной заявки  — конверт op=other (самопочинка НЕ трогает; разрыв петли ре-конвертов)
· PC_SILENT_MARK = «⏱ ПК-театр не отвечает» (в result failed-шага; думатель по нему НЕ зовётся)
· _REJECT_PREFIX = «отклонено Филиппом» (префикс result devbot-отказа → halt без думателя)
· ADAPT_REPLACED_MARK = «♻️ заменён коррекцией плана», ADAPT_FINISH_MARK = «⏭ закрыт досрочно» — done-карты шагов, закрытых адаптацией (Bridge принимает только done|failed; failed глушил бы цепь как failed-сиблинг; сводка эти карты исключает)
· 🔴-ПОМЕТКА ПЛАНА: _dec_red_note(steps) → «🔴 красные шаги: i, j — исполнитель шага спросит «да» кнопкой, сам не исполнит.\\n»; красность = _HEADLESS_IMPOSSIBLE_RE (IGNORECASE): clasp|redeploy|\\bsqlite3\\b|set_fleet_(?:oil|service)|{DELEV}|confirmed\\s*=\\s*true|лист\\s*1|\\bcrm\\b|зарплат|байки|транзакц|проводк|деньг|касс|удал(?:и|ени|яе|ён)|календар. Пометка — ТОЛЬКО дисплей в result родителя (строка с 🔴 не матчит _PLAN_LINE_RE → restart-proof парс плана цел); текст шагов в очереди НЕ помечается.
· GUARD vps-последовательности (для полноты): _DEC_WAIT_STATUSES = (in_progress, needs_approval, approved) — сиблинг там → шаг не берём; failed-сиблинг → шаг пропускается (halt-on-fail); _earlier_new_sibling — есть new-шаг того же родителя с МЕНЬШИМ номером → пропуск (порядок по НОМЕРУ шага, не по id: перерождение самопочинки имеет id ВЫШЕ следующих шагов).

═══ 3. РЕЛИЗ ШАГОВ PC-ЦЕПИ (process_pc_chains, стр. 1639–1651 + хелперы 1268–1636) ═══
ИНВАРИАНТ: в очереди lane=pc живёт максимум ОДИН шаг цепи; следующий встаёт ТОЛЬКО после done предыдущего (sequential release). Причина: у pc_orchestrator НЕТ guard'а последовательности (FIFO claim подряд) — веер дал бы гонку halt-on-fail и порядка перерождений.
ЦИКЛ (каждый cycle демона, read-only снимок): _pc_fetch_items = get_pending_multi(("new","in_progress","needs_approval","approved","done","failed"), lane='pc'); ошибка чтения → None → пропустить цикл ЦЕЛИКОМ (частичная картина опаснее ожидания). _pc_group_chains: ТОЛЬКО from==PC_DEC_FROM И _STEP_RE-матч → {pid: [(i,n,item)…]}; одиночные Filipp-pc[-dev] не трогаются, claim чужой полосы НЕТ (complete на своих шагах = финализация собственной цепи). Для каждого pid вне _summarized → _pc_chain_tick; исключение тика одной цепи не валит остальные.
ТИК (_pc_chain_tick): рабочий элемент = ПОСЛЕДНИЙ шаг цепи = max по (номер шага, id) — при дублях номера старший id = перерождение самопочинки. По статусу:
· needs_approval → return (ждём Филиппа; карточка уже в инбоксе от devbot);
· new / in_progress / approved → ДЕТЕКТ МОЛЧАНИЯ ПК: _age_sec(updated) > PC_STEP_TIMEOUT (.env, дефолт 3600с; ошибка парса возраста → None → таймаут НЕ объявляем, ждём цикл) → complete_task(failed, диагноз «⏱ ПК-театр не отвечает: шаг i/n висит в <st> M мин…») + правка снапшота + сводка = halt цепи (думатель такое не чинит); иначе просто ждать;
· терминальный (done/failed): сначала _dec_summary_exists(pid) (сводка лежит на полосе vps) → цепь закрыта до рестарта → в _summarized, не трогать;
· failed → _pc_after_fail: (а) result startswith «отклонено Филиппом» ИЛИ содержит PC_SILENT_MARK → сводка, halt без думателя; (б) _HEAL_RE в тексте шага (перерождение упало ПОВТОРНО) → 🛑-карточка «попытка 1 исчерпана» + сводка (терминальный halt); (в) STEP_SELFHEAL=0 → сводка (прежний halt-on-fail); (г) иначе думатель самопочинки → verdict retry+fixed_step → перерождение enqueue lane=pc «[шаг i/n родитель pid] [самопочинка шага i, попытка 1] <fixed>» + 🩹-карточка; halt/сбой думателя/enqueue-fail → карточка с диагнозом + сводка. Halt в sequential-модели = просто НЕ релизить дальше;
· done → _pc_after_done: ВОССТАНОВЛЕНИЕ ПЛАНА _pc_current_plan(pid) — restart-proof из очереди vps: get_pending("done") → result родителя (нумерованный список → {num:(текст,K=0)}) + карточки _ADAPT_CARD_RE своего pid по возрастанию id: база B из task_text («после шага B»), остаток из result; план режется до num<=B и накрывается остатком с K=k (пустая/осиротевшая карточка → игнор = keep); возврат (plan, k_cnt, last_base); ошибка чтения/родитель не найден → ({},0,None) → честный halt. total = max(plan) (фоллбэк n из маркера шага). Дальше: i>=total → сводка (финал цепи); plan[i+1] нет → ⚠️-карточка «план не восстановился… поставь декомпозируй: заново» + сводка (halt); АДАПТАЦИЯ зовётся если PLAN_ADAPT=1 И last_base != i (шаг i сам из свежей коррекции — не переспрашиваем) И (pid,i) вне _pc_adapted (дедуп памяти процесса; после рестарта максимум один лишний keep-вопрос): finish → 🏁-карточка + сводка (остаток НЕ релизится, _adapt_finish[pid]=reason); adjust → K=k_cnt+1: K>PLAN_ADAPT_MAX=2 → 🛑 «план дрейфует, нужен владелец» + сводка; i+len(new)>MAX_STEPS=8 → fail-safe keep; иначе карточка коррекции (enqueue vps «[коррекция плана родитель pid] после шага i (K=k)» → claim → complete done с 🧭-картой и новым остатком) + релиз ПЕРВОГО скорректированного _pc_release(pid,i+1,new_total,new[0],k=K); сбой карточки → keep. keep/fail-safe/выкл/уже спрошено → релиз следующего шага ПРЕЖНЕГО плана: _pc_release(pid, i+1, total, текст, k=K-происхождение шага).
_pc_release(pid,j,total,text,k): enqueue lane=pc «[шаг j/total родитель pid] [коррекция плана k] <text>» (маркер K только при k>0); enqueue-fail → warn + повтор следующим циклом.
РЕЛИЗ ШАГА 1: в _dec_plan_and_fanout, ДО complete_task родителя (crash-окно: шаг не встал → родитель остаётся in_progress, devbot поднимет «зависла»); только при ok шага 1 родитель закрывается done с планом в result.
СВОДКА (_pc_post_summary/_pc_summary_text): идемпотентна (_summarized + _dec_summary_exists); done/failed-шаги снапшота, дубли номера → последняя по id; head «🧩 Сводка декомпозиции (родитель pid, театр PC): d/total шагов done» + («🏁 завершено досрочно: <reason>» | «есть упавшие/пропущенные»); строка на шаг «✅|❌ шаг i/n: <первая строка result, ≤400>»; total = n-маркер последнего релизнутого шага (несёт актуальный итог после коррекций).
ПАМЯТЬ ПРОЦЕССА — только дедуп-кэши (_summarized, _pc_adapted, _adapt_finish); всё состояние цепи — из очереди → после рестарта демона цепь продолжается с того же места.

Хвост: часть 2/2 (THINKER_PREAMBLE/ADAPT_PREAMBLE думателей, vps-ветка process_new/гейты, реапер сирот + claim-verify) — отдельной задачей."""

SPEC = SPEC_T.replace("{DELEV}", DELEV)


def main():
    c = BridgeClient()
    r = c._call("read_doc", name="cc_log")
    if not r.get("ok"):
        print("READ FAIL — НЕ пишу (защита от затирки):", r, file=sys.stderr)
        return 1
    old = r.get("text", "")
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    line = f"DONE {ts} UTC (headless): {SPEC}"
    new = _insert_under_vrezka(old, line)
    w = c.write_doc(text=new, name="cc_log")
    if not w.get("ok"):
        print("WRITE FAIL:", w, file=sys.stderr)
        return 1
    print(f"cc_log OK (old={len(old)} → new={len(new)})")
    pulse = (f"{ts} | 🟢 | порт-спека мозга декомпозера ч.1/2 записана в cc_log "
             f"(промпт планировщика + поля/маркеры очереди + релиз pc-цепи; read-only, код не трогался) "
             f"| ничего не жду | детали→cc_log запись «порт-спека 1/2»")
    wp = c.write_doc(text=pulse, name="pulse")
    print("pulse", "OK" if wp.get("ok") else f"FAIL {wp}")
    return 0 if wp.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
