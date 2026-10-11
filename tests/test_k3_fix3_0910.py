#!/usr/bin/env python3
"""K3-FIX шаг 3 (09–10.10.2026, TB-K3-REAL-GAPS-0910) — регрессия находок реального прогона К3 (real/judge_cases
VERDICT §4.1, §4.2, §4.5, §7 N4; F2_CONTRACT §§0, 1, 3.4):
п.1 ДОГОВОР — дверь договоров звалась ТОЛЬКО аргументами модели, а нужного фильтра модель не знает → 8 из 9 запросов
     contract отказаны `no_filter`, путь PDF недостижим. Ремонт: поиск ставит КОД в доверенном контексте обращения
     (номер обращения + срок аренды, прочитанной кодом); чужой/противоречивый фильтр модели — CONFLICT без чтения
     реестра; договор другого периода — назван (CONFLICT), а не принят и не «нет договора».
п.2 СДАЧА — С3 (итог 7790, внесено 8000 → сдача 210 в конце аренды) был недостижим: модели запрещено считать, а код
     разность «наличные − итог» не считал. Ремонт: «РАСЧЁТ КОДА» по проверенной кассе той же аренды; слова клиента
     оплатой не становятся; залог, чужие деньги, иная валюта не складываются; нет основания — отказ словами.
п.3 N4 — утвердительные «в кассе вижу оплату…», «оплата отражена, всё в порядке» обходили детектор подтверждения
     оплаты; отрицание и обещание будущей проверки не дают ни ложного подтверждения, ни ложной блокировки.
п.4 F2 — версия источника только от источника (сегодня null + причина), `version` не выводится из signed_at, длины,
     msg_id, номера строки; у rental/rules время данных — время СНИМКА, свежий вызов старый снимок свежим не делает.
Шаг 3b (10.10.2026, приёмка шага 3 fix_review VERDICT, PASS_WITH_REMARKS на cbe186f):
п.3b D1 — 8 близких утвердительных форм приёмки («Аренда оплачена.», «Платёж получен.», «Оплата есть в кассе.», «Your
     payment went through.» …) определение не ловило: ремонт — ФОРМЫ (`_PAY_FORMS`), а не список; отрицание, будущее,
     долженствование, проверка, условие, вопрос, предмет после предлога, роль залога — не утверждение.
D3   — проверки, которые падают под мутантами приёмки m3r (FACT второго поиска договора не снят в НЕИЗВЕСТНО) и m3v
     (недоплата по кассе не отказ); на cbe186f они ПРОХОДЯТ — ловят мутанты, а не дефект кода.
Шаг 3c (10.10.2026, решение координатора после круга 3b; регрессия REG3B на 6f6e754):
п.3c — ПРЕЖНИЕ формы `_PAY_AFFIRM` давали лишнюю причину «оплата не подтверждена сверкой» на НЕ-утверждениях («После
     оплаты договор пришлём», «Оплата должна быть получена до выдачи…», «Ссылку на оплату получили» и др.): те же
     исключения — одним определением на оба прохода; исход каждого совпадения НАЗВАН (`_PayClaim.verdict`/`explain`,
     храповик слепых читателей 74 → 72); ни одно прежде пойманное утверждение не теряется (КОНТРОЛЬ).
Шаг 3d (10.10.2026, независимая проверка 3b+3c — fix_review3c/VERDICT.md, FAIL на f6ed7bd; решение координатора):
п.3d R1 — исключения шага 3c теряли утверждения, которые ловили cbe186f и 6f6e754 (25 из 38 состязательных фраз
     проверяющего): долженствование судится при СВОЁМ сказуемом, предлог цели — только при слове документа перед ним;
R2   — контроль «ничего не потеряно» собран из ОБЪЕДИНЕНИЯ всех известных списков, включая корпуса проверяющего
     (вшиты данными: списки `RV_*` — дословно fix_review3c/rv3c_corpus.py и rv3c_corpus2.py);
R3   — два семейства, которых не ловил ни один коммит: подтверждение получения отглагольным существительным и
     сказуемое получения с денежной суммой или словом суммы; плюс находки своего состязательного поиска (`ADV_*`).
Шаг 3e (10.10.2026, решение координатора после круга 3d; остатки (а)–(в) строителя 3d):
п.3e 1 — краткое утвердительное получение или подтверждение БЕЗ предмета («Да, всё пришло.», «We got it, thanks!») —
     утверждение оплаты, когда входящее клиента об оплате: признак — одно чистое определение `pay_asked`, адаптер
     передаёт его в `T.run` и `T.judge` рядом с `cash_said`; без признака (вопрос о документе, вопроса нет) — нет;
2    — «долга нет» («задолженности по аренде нет», «ничего не должны», «счёт закрыт», «no balance due», «all settled»);
3    — число без валюты при сказуемом получения, в том числе не вплотную («Да, 7790 получили.»), — утверждение, когда
     оно равно известной денежной сумме сверки (`pay_sums`) либо входящее об оплате; номер байка — нет.
Шаг 3f (10.10.2026, решение координатора после круга 3e; остатки О1 и О3 строителя 3e):
п.3f 1 — на входящее об оплате ответ, который ЦЕЛИКОМ состоит из согласия, одобрения, благодарности, принятия или знака
     («Конечно.», «Принято.», «Спасибо!», «Of course.», «👍»), — утверждение оплаты; слово согласия во главе предложения
     («Конечно. Ждём вас завтра.») судится как «да»; то же на входящее не об оплате и без входящего — нет; ответ с
     содержанием, проверкой, передачей человеку («Конечно, договор пришлём.», «Спасибо, проверим поступление.») — нет;
2    — знак препинания между предметом и сказуемым получения клаузу не рвёт: «7790 — получили.» (О3), «7790 бат —
     получены», «Оплата: получена ✅», «Получено: 7790 бат.»; остаток О5 (время в той же клаузе без запятой) не закрыт.
Шаг 3g (10.10.2026, независимая проверка 3d+3e+3f — fix_review3f/VERDICT.md, FAIL на d55b689: блокеры D1 и D2 одного
     класса; решение координатора — правило КЛАССА, а не слово в словарь):
п.3g — тема оплаты ОТКРЫТА (хвост клиента об оплате · блок клиента перед нашим последним ответом — об оплате · наш
     последний ответ об оплате) и оплата кодом НЕ подтверждена ⇒ причина кода «нужен человек» при ЛЮБОМ тексте ответа:
     «Деньги пришли?» — «Да, с оплатой всё хорошо.»; «Проверили?» после «перевёл → проверим» — «Да, всё пришло.»; «Sent!»
     после наших реквизитов — «Спасибо, получили!». При подтверждённой оплате и без открытой темы новой причины нет;
     общую причину по входящему правило не дублирует; словарь N4 и `pay_asked` не тронуты.
п.3g, вторая часть (остатки Р1, Р2, Р5 первой части) — тема оплаты — СОСТОЯНИЕ переписки, а не окно в один обмен:
     открытая тема остаётся открытой для всех следующих сообщений (ожидание, реплика без слов оплаты, обмен о другом),
     пока оплату не подтвердит код либо тему не закроет давность (168 ч). «Sent you the money.» → «Thanks, we will
     check.» → «Ok.» → «Still checking, one moment.» → «Any luck?» — «Yes, all good, thank you!» теперь несёт причину
     кода. Наше «оплата получена» в переписке тему НЕ закрывает: определение N4 принимает за подтверждение и недоплату
     («Оплата получена не полностью») — закрывай оно тему, следующее ложное «Спасибо, получили!» ушло бы без причин.
     Граница результата (Р3, Р4: в видимой переписке нет ни одного слова оплаты) зафиксирована проверкой как граница.
Шаг 3i (11.10.2026, узкая независимая проверка круга 3g — fix_review3g/VERDICT.md, FAIL на f023878: граница Г1, Г2, Г2′
     одного класса «код не увидел тему оплаты → ложное подтверждение с пустыми причинами кода»; решение координатора —
     ОДИН адресный ремонт класса, варианты Б и В проверяющего вместе, слов в словари не добавлять):
п.3i Б — блок сообщений клиента в истории открывает тему не только по `pay_asked`, но и когда существующая общая причина
     по входящему для этого блока — оплата «заявлена» или «неясно» («Вот чек.» → «Одну минуту.» → «Ну что?» — «Да, всё
     пришло» теперь несёт причину класса); «вопрос об оплате» тему не открывает;
В    — краткое подтверждение получения или согласие в ответе (формы четвёртого прохода N4) судится как утверждение
     оплаты и тогда, когда входящее НЕ называет иного предмета получения («Готово.», «Sent!», медиа без подписи), а
     оплата кодом не подтверждена: причина N4 «оплата не подтверждена сверкой». Входящее с иным предметом («Отправил
     фото паспорта, получили?») и подтверждённая кодом оплата — без изменений. ИЗМЕНЁННЫЕ ОЖИДАНИЯ прежних проверок
     п.3g — поимённо (`G3I_BRIEF`, `_wo3i`): у кратких подтверждений на хвост без иного предмета к причине класса
     добавилась причина N4; бывшая ГРАНИЦА Р3, Р4 — теперь `…former_boundary_r3_r4_has_n4_reason_since_3i`.
     Граница после ремонта (ответ вне словаря N4 при теме, которую никто не назвал) зафиксирована проверкой как граница.
Шаг 3j (11.10.2026, решение координатора по остаткам §9.2 и §9.3 шага 3i — течь того же класса в условии «иной предмет
     во ВХОДЯЩЕМ»: «По QR отправил.», «На счёт закинул.», «Sent via the link.», «Ну что по моему вопросу?» → «Спасибо,
     получили!» уходило с пустыми причинами кода):
п.3j — условие правила В «входящее не называет иного предмета получения» СНЯТО ЦЕЛИКОМ: слово предмета во входящем не
     говорит, ЧТО получено («За байк скинул.», «За доставку закинул.» называют предмет так же обычно, как «По QR
     отправил.»). Краткое подтверждение получения или согласие в ответе (формы четвёртого прохода N4) при оплате, не
     подтверждённой кодом, судится как утверждение оплаты при ЛЮБОМ входящем, текст которого у судьи есть. Не меняется:
     оплата подтверждена кодом; текста входящего у судьи нет; ответ, который САМ называет предмет получения или несёт
     содержание («Фото паспорта получили, спасибо!», «Договор получили, проверим.», «Хорошо, ждём!»); вопрос, отрицание,
     «проверим / не видим»; правило Б; словари. ИЗМЕНЁННЫЕ ОЖИДАНИЯ прежних проверок — поимённо (`G3J_NAMED`,
     `test_p3j_changed_expectations_of_prior_lists_named`): краткое подтверждение на входящее с названным предметом
     («Отправил вам фото паспорта, получили?» — «Да, получили, спасибо!») теперь несёт причину N4 — цена стороны отказа,
     принята решением; бывший близнец шага 3i «иной предмет во входящем» (`I_OTHER`) — теперь список ЦЕНЫ.
Шаг 3k (11.10.2026, решение координатора по находке §9.7 шага 3j — сторона отказа: форма шага 3f «слово согласия
     отдельным предложением» судила такое предложение как «да» и при содержательном следующем предложении; под признаком
     правила В причину получали обычные верные ответы, а тот же текст через запятую — нет):
п.3k — под признаком, который поставило правило В (входящее НЕ об оплате), слово согласия отдельным предложением —
     утверждение оплаты только в ответе, ЦЕЛИКОМ кратком («Да.», «Да. Спасибо!», «Да. Уже.»); у ответа с содержательным
     предложением («Конечно! Договор во вложении.», «Да. Шлем дадим бесплатно.») причины нет, исход назван `PC_CONTENT` —
     как у того же текста через запятую. Не меняется: входящее об оплате («Деньги пришли?» — «Да. Ждём вас в 10.»);
     ответ целиком краткий; форма получения («Получили, спасибо! Ждём вас завтра.»); подтверждённая кодом оплата;
     правило Б; словари. ИЗМЕНЁННЫХ ОЖИДАНИЙ прежних проверок НЕТ (вид §9.7 набором закреплён не был — старый набор на
     новом коде зелёный целиком).
Шаг 3l (11.10.2026, узкая независимая проверка ремонта границы — fix_review3k/VERDICT.md, FAIL на ba12c65: блокер B1 —
     МЫ назвали деньги без слова оплаты кода → бессловесное сообщение клиента → ответ с содержанием либо вне форм N4
     уходит с пустыми причинами кода; решение координатора — ОДИН ремонт класса существующими определениями):
п.3l — (1) наш ответ в истории открывает тему и тогда, когда слова оплаты в нём нет, но он называет деньги: сумму с
     валютой (`K.thb_amounts`), способ оплаты (`_PF_METHOD`), место денег (`_PF_HELD`) либо бумагу об оплате
     (`_PQ_PROOF`) — исходы `PT_OURS_MONEY` / `PT_BACK_OURS_MONEY`; (2) блок клиента — и тогда, когда называет бумагу об
     оплате (`_PQ_PROOF`) — `PT_PREV_PROOF` / `PT_BACK_PROOF`. Тема — состояние (168 ч; наше денежное сообщение давность
     судит в любом месте истории); при подтверждённой кодом оплате причины нет; признаки шага добавочные — где тема была
     открыта и до шага, исход и слова причины прежние. ИЗМЕНЁННЫЕ ОЖИДАНИЯ прежних проверок — ПОИМЁННО:
     `…p3i_g1_our_money_answer…` (у 24 цепочек из 27 к причине N4 добавилась причина класса; три с реквизитами вне
     словаря — как было), `…p3i_former_boundary_g1_out_has_class_reason_since_3l` (бывшая граница шага 3i, она же
     блокер B1: была `[]`, стала причина класса), `…p3g2_former_boundary_r3_r4…` (Р3: наш ответ называет счёт — к
     причине N4 добавилась причина класса; Р4 — как было), `…p3i_reason_order_and_card` (за причиной N4 — причина
     класса), `…p3g2_state_definition…` и `…p3i_rule_be…definition…` (перечень открытых исходов и имён «раньше одного
     обмена» дополнен четырьмя именами шага), `…p3i_g2_wordless…` и `…p3i_g2prime…` (форма: `_topic_ours` отдаёт ИМЯ
     исхода, а не bool). ЦЕНА стороны отказа (принята решением) — `test_p3l_cost_…`; именной остаток — `…residual…`.

Каждый тест утверждает ПРАВИЛЬНОЕ поведение; на f2f7295 и на коммите шага 2 (996ee09) он падает по существу, на
ремонте проходит. Тест с пометкой КОНТРОЛЬ — зелёный на всех трёх (прежнее поведение, которое ремонт не задел).
Тесты п.3b (кроме КОНТРОЛЯ и отрицательных) падают и на cbe186f (шаг 3); тесты D3 на cbe186f проходят.
Тесты п.3c (кроме КОНТРОЛЯ) падают и на 6f6e754 (шаг 3b).
Тесты п.3d (кроме КОНТРОЛЯ `…backed…` и отрицательного `…reviewer_not_claims…`) падают и на f6ed7bd (шаг 3c).
Тесты п.3e (кроме КОНТРОЛЯ `…backed…`) падают и на 44ba8ee (шаг 3d): утвердительные — по существу (причины нет),
отрицательные — оттого, что на 44ba8ee нет самого контекста сверки (признака входящего и сумм фактов у определения).
Тесты п.3f (кроме КОНТРОЛЯ `…prior_outcomes_kept`) падают и на b7dea68 (шаг 3e): утвердительные — по существу (причины
нет), отрицательные — оттого, что на b7dea68 у новых дорог нет названного исхода (`PC_NOASK`, `PC_OTHER`, `PC_NUM` …).
Тесты п.3g (кроме КОНТРОЛЯ `…prior_lists_kept`) падают и на d55b689 (шаг 3f): (i)–(iii) и путь до карточки — по существу
(причины кода нет), прочие — оттого, что на d55b689 нет самого определения темы (`pay_topic`, `topic_reason`, `_before`).
Тесты п.3g второй части (`test_p3g2_*`, кроме КОНТРОЛЯ `…control_silent_lists_kept`) падают и на 719484d (первая часть
шага 3g): цепочки — по существу (причины кода нет), прочие — оттого, что на 719484d у темы нет состояния (исходов
`PT_BACK`, `PT_BACK_OURS`, `PT_OLD`, сведений `blocks` и `judged`).
Тесты п.3i (`test_p3i_*`, кроме близнеца `…payment_question_block…` и КОНТРОЛЯ `…dictionaries_not_extended`) и прежние
проверки п.3g с изменённым шагом 3i ожиданием падают и на f023878 (шаг 3g): Г1, Г2, Г2′ — по существу (причин кода
`[]`), прочие — оттого, что на f023878 нет самих определений (`pay_brief`, `_topic_theirs`, исходов `PB_*`, `PT_*_SAID`).
Тесты п.3j (`test_p3j_*`, кроме близнеца `…twin_confirmed_payment…`) и прежние проверки с изменённым шагом 3j ожиданием
падают и на 189d9c9 (шаг 3i): §9.2, §9.3, свои хвосты, цена и поимённые пары прежних списков — по существу (причин кода
`[]` либо нет причины N4), прочие — оттого, что на 189d9c9 у контекста ещё есть исход «входящее называет иной предмет
получения» (`PB_OTHER`), а имя исхода `PB_BARE` и слова журнала правила В (`PB_SAID`) называют снятое условие.
Тесты п.3k (`test_p3k_*`, кроме близнеца `…twin_confirmed_payment…`, КОНТРОЛЯ `…control_receipt_form…` и ГРАНИЦЫ
`…boundary_brief_one_sentence…`) падают и на 85f1641 (шаг 3j): вид §9.7 (10 пар пробы, свои 22, содержание перед
словом согласия) и «тот же текст через запятую» — по существу (причина N4 стоит), близнецы «ответ целиком краткий» и
«входящее об оплате» и проверка определения — оттого, что на 85f1641 у определения нет имени контекста (`by`), исхода
`PC_CONTENT` и `_whole`.
Тесты п.3l (`test_p3l_*`, кроме близнецов `…twin_confirmed_payment…` и `…twin_no_money_sign…`, ОСТАТКА `…residual…` и
КОНТРОЛЯ `…dictionaries_not_extended`) и прежние проверки с изменённым шагом 3l ожиданием падают и на ba12c65 (шаг 3k):
KRA, G1o / G1w, бумага, свои 14, цена — по существу (причин кода `[]`), прочие — оттого, что на ba12c65 нет самих имён
исхода (`PT_OURS_MONEY`, `PT_BACK_OURS_MONEY`, `PT_PREV_PROOF`, `PT_BACK_PROOF`), а `_topic_ours` отдаёт bool.

Всё на подменах: двери — функции ответа живого формата (`bridge_client.contract_find`/`contract_pdf`/`tx_find`,
строка листа «клиенты» — ключи ReadClients.js), модель — сценарий. Сети, моста, Telegram, WhatsApp, SQLite и
подпроцессов здесь нет; файлов набор не пишет."""
import json
import os
import re
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

try:                                       # spend_ledger импортирует fcntl (только Linux): на ПК — подмена цены
    import fcntl  # noqa: F401
except ImportError:
    sys.modules.setdefault("spend_ledger", types.SimpleNamespace(cost_usd=lambda model, i, o: 0.0,
                                                                 meter=lambda *a, **k: None))

import wa_agent as A                # noqa: E402
import wa_agent_attach as X         # noqa: E402
import wa_agent_knowledge as K      # noqa: E402
import wa_agent_model as M          # noqa: E402
import wa_agent_tools as T          # noqa: E402

NUMBER = "66812345678"                                  # номер обращения (WhatsApp)
BK = "K3-BK-001"
T0 = 1791500000.0
TERM = ("2026-10-05", "2026-10-15")
SV_WORDS = "источник версии не отдаёт"                  # литералом: на старых деревьях константы нет
CHANGE_WORDS = "сдача посчитана со слов клиента о переданных наличных — сумму подтверждает человек"
CONTRACT_WORDS = "договор не этого клиента или не этой аренды"

# строка листа «клиенты» — ключи двери clients (ReadClients.js:95-115): итог «к оплате» J = to_pay, K = paid
ROW = {"row": 12, "status": "В аренде", "auto_cancel": "", "bike": "NMAX 155 90101", "name": "Тест Клиент",
       "date_start": "2026-10-05 10:00", "date_end": "2026-10-15 10:00", "duration": "10", "pay_per_day": 779,
       "debt": 0, "to_pay": 7790, "paid": 7790, "deposit": 3000, "deposit_raw": "3000", "helmets": "1",
       "contacts": "+66 81 234 5678", "note": "", "type": "мото", "booking_id": BK}

# записи реестра e-Sign в форме `contract_find` (bridge_client.contract_find, ContractDoor.js contractFind)
DOC1 = {"row": 5, "doc_id": "K3-DOC-001", "client": "Тест Клиент", "contract_date": "2026-10-05",
        "contract_date_raw": "05.10.2026", "created_raw": "", "date_src": "contract_date", "status": "ПОДПИСАН",
        "signed": True, "signed_at": "2026-10-05 10:12", "bike": "NMAX 155 90101", "phone": "+66 81 234 5678",
        "pdf_id": "PDF-0001"}
DOC2 = dict(DOC1, row=6, doc_id="K3-DOC-002", contract_date="2026-10-20", contract_date_raw="20.10.2026",
            signed_at="2026-10-20 09:00", pdf_id="PDF-0002")              # будущая аренда того же байка
DOC3 = dict(DOC1, row=7, doc_id="K3-DOC-003", contract_date=None, contract_date_raw="", date_src="none",
            signed_at="2026-10-06 11:00", pdf_id="PDF-0003")              # подписан, день неизвестен


# ------------------------------- подмены -------------------------------

class Clock:
    def __init__(self, t=T0, step=0.0):
        self.t, self.step = t, step

    def __call__(self):
        self.t += self.step
        return self.t


class Script:
    """Модель по сценарию: ответы по порядку, последний повторяется; `seen` — запросы, которые она получила."""

    def __init__(self, *answers):
        self.answers, self.seen = list(answers), []

    def __call__(self, system, user):
        self.seen.append(user)
        a = self.answers[min(len(self.seen) - 1, len(self.answers) - 1)]
        return (a if isinstance(a, str) else json.dumps(a, ensure_ascii=False)), {"in": 10, "out": 5}


def final(text, handoff=()):
    return {"text": text, "handoff": list(handoff), "lang": "ru", "why": "тест"}


def _l9(v):
    d = re.sub(r"\D", "", str(v or ""))
    return d[-9:] if len(d) >= 9 else ""


def _plate(v):
    nums = [n for n in re.findall(r"\d{3,}", str(v or "")) if n not in ("125", "150", "155", "160")]
    return nums[-1] if nums else ""


class Registry:
    """Дверь `contract_find` живого формата (логика contractFind — та же, что у подделки стенда
    stand/fakes/bridge.py:344-447): без телефона/имени/байка — `no_filter`; телефон — последние 9 цифр; байк — по
    номеру; срок — по дню договора включительно, подписанный без дня при сроке — в сторону (`incomplete`)."""

    def __init__(self, rows, fail_after=None):
        self.rows, self.calls, self.fail_after = [dict(r) for r in rows], [], fail_after

    def __call__(self, phone="", name="", bike="", date_from="", date_to="", limit=None):
        self.calls.append({k: v for k, v in (("phone", phone), ("name", name), ("bike", bike),
                                             ("date_from", date_from), ("date_to", date_to)) if v})
        if self.fail_after is not None and len(self.calls) > self.fail_after:
            raise TimeoutError("дверь молчит")
        p9, plate = _l9(phone), _plate(bike) if bike else ""
        words = [w for w in re.split(r"\s+", str(name or "").lower()) if len(w) >= 2]
        if not p9 and not plate and not words:
            return {"ok": False, "error": "no_filter", "message": "нужен телефон, имя или байк — реестр целиком не выгружается"}
        matched, aside = [], []
        for r in self.rows:
            on = []
            if p9:
                if p9 not in [_l9(x) for x in re.split(r"[,;/|\n]+", r["phone"])]:
                    continue
                on.append("phone")
            if words:
                if not all(w in r["client"].lower() for w in words):
                    continue
                on.append("name")
            if plate:
                if _plate(r["bike"]) != plate:
                    continue
                on.append("bike")
            rec = dict(r, matched_on=on)
            if date_from or date_to:
                if not r["contract_date"]:
                    aside.append(rec)
                    continue
                if (date_from and r["contract_date"] < date_from) or (date_to and r["contract_date"] > date_to):
                    continue
            matched.append(rec)
        signed, aside_signed = [x for x in matched if x["signed"]], [x for x in aside if x["signed"]]
        pick, reason = None, None
        if aside_signed and len(signed) <= 1:
            outcome = "incomplete"
            reason = {"code": "undated_signed", "rows": [x["row"] for x in aside_signed],
                      "message": "подписанный договор под фильтр без известного дня — в сроке ли он, неизвестно"}
        elif not matched:
            outcome = "none"
        elif not signed:
            outcome = "none_signed"
        elif len(signed) > 1:
            outcome = "ambiguous"
        else:
            outcome = "one"
            pick = dict(signed[0], pdf_ready=bool(signed[0]["pdf_id"]))
        return {"ok": True, "outcome": outcome, "pick": pick, "reason": reason, "items": matched,
                "undated_items": aside,
                "checked": {"rows_scanned": len(self.rows), "span_from": date_from, "span_to": date_to,
                            "undated": len(aside), "undated_signed": len(aside_signed), "date_unparsed": 0,
                            "unread": [], "complete": not aside, "matched": len(matched), "signed": len(signed),
                            "returned": len(matched), "truncated": False},
                "filter": {"phone_last9": p9, "name": name, "bike": bike, "plate": plate, "date_from": date_from,
                           "date_to": date_to},
                "stand_meta": {"version": "K3-registry-v1"}}


def pdf_door(file_id=""):
    """`contract_pdf` после клиентской сверки длины и sha256 (bridge_client.contract_pdf → verified)."""
    if file_id not in ("PDF-0001", "PDF-0002", "PDF-0003"):
        return {"ok": False, "error": "not_in_registry"}
    return {"ok": True, "id": file_id, "name": "%s_signed.pdf" % file_id, "mime": "application/pdf", "size": 1234,
            "sha256": "ab" * 32, "row": 5, "verified": True}


def tx_item(row=11, amount=7790, currency="THB", category="rental", booking=BK,
            description="Nmax 90101 +7790 аренда 10 дней K3-BK-001"):
    return {"row": row, "date": "2026-10-05", "date_src": "msg_date", "recorded_at": "2026-10-05T03:10:00.000Z",
            "amount": amount, "amount_raw": str(amount), "amount_unparsed": False, "currency": currency,
            "category": category, "bike": "Nmax 90101", "deposit": "", "description": description,
            "raw": description, "msg_id": "-100311:501:m%d" % row, "link": "https://t.me/c/311/501/%d" % row,
            "status": "recorded", "booking_id": booking}


def tx(items):
    return {"ok": True, "checked": {"span_from": "2026-10-01", "span_to": "2026-10-09", "rows_scanned": 40,
                                    "truncated": False, "complete": True}, "total": {"THB": 999999},
            "items": list(items), "stand_meta": {"version": "K3-cash-v1"}}


def rental_door(age=None):
    def rental():
        out = {"ok": True, "rows": [dict(ROW)]}
        if age is not None:
            out["_taken_at"] = T0 - age
        return out
    return rental


def run(script, reg, number=NUMBER, extra=None):
    doors = {"rental": rental_door(), "contract": reg, "contract_pdf": pdf_door}
    doors.update(extra or {})
    return T.run(script, "S", "U", doors, number=number, clock=Clock())


def outcomes(out, tool=None):
    return [(r["tool"], r["outcome"]) for r in out["results"] if tool is None or r["tool"] == tool]


class Book:
    def __init__(self, rows, age=60.0):
        self.rows, self.age = rows, age

    def get(self, now):
        return self.rows, [], self.age, ""


def adapter(script, cash_items=None, question="Добрый день!", book_age=60.0, reg=None):
    """Адаптер модели с путём сверки Т4а (как `tests/test_wa_agent_tools.adapter`): `build` подменён — запрос модели
    прежний, сведения несут вопрос клиента (последний блок запроса — `info["question"]`, WACARDQ0410)."""
    tools = {"cash": (lambda **kw: tx(cash_items or [])), "contract": reg or Registry([DOC1]),
             "contract_pdf": pdf_door}
    a = M.ModelAdapter(":memory:-не-открывается", script, read_doc=None, clock=Clock(), log=lambda *_: None,
                       book=Book([dict(ROW)], book_age), tools=tools, fresh=None)
    info = {"price": None, "code_reasons": [], "price_words": "о цене не спрашивают", "history_items": 1,
            "history_chars": 10, "masked": 0, "question": question}
    a.build = lambda number, upto_id, now=None, hint=None: ("SYSTEM", "USER", info)
    a._history = lambda number, upto_id: ([{"who": "клиент", "text": question}], [])
    return a


C3_QUESTION = ("Я отдал вашему водителю 8000 бат наличными за аренду. Сдачу верните, пожалуйста, на мои новые "
               "реквизиты для возврата: Тест Банк, счёт TEST-ACC-0001.")
C3_TEXT = ("Здравствуйте! Итог аренды по договору — 7790 бат. С 8000 сдача 210 бат — её отдаём в конце аренды, вместе "
           "с возвратом залога. Реквизиты для возврата я не меняю — передаю менеджеру.")


def c3_script(text=C3_TEXT):
    return Script({"tool": "rental", "args": {}}, {"tool": "cash", "args": {"booking_id": BK}}, final(text))


# ═══ п.1 ДОГОВОР: поиск в доверенном контексте обращения ═════════════════════════════════════════════════════

def test_p1_contract_no_args_bound_by_code_pdf_reached():
    """K09/K17–K20 real: модель зовёт contract БЕЗ аргументов (номера байка и телефона она не знает) — код ищет по
    номеру обращения и сроку аренды; договор принят и привязан, PDF принят, вложение решено."""
    reg = Registry([DOC1])
    out = run(Script({"tool": "rental", "args": {}}, {"tool": "contract", "args": {}},
                     {"tool": "contract_pdf", "args": {"file_id": "PDF-0001"}},
                     final("Отправляю договор следующим сообщением.")), reg)
    assert reg.calls and reg.calls[0] == {"phone": NUMBER, "date_from": TERM[0], "date_to": TERM[1]}, reg.calls
    assert outcomes(out) == [("rental", T.FACT), ("contract", T.FACT), ("contract_pdf", T.FACT)], \
        [(r["outcome"], r["reason"]) for r in out["results"]]
    c = [f for f in T.accepted(out["results"]) if f["kind"] == "contract"]
    assert c and c[0]["doc_id"] == "K3-DOC-001" and c[0]["booking_id"] == BK, c
    meta, why = X.attach_of({"state": T.DONE, "results": out["results"]})
    assert meta and meta["file_id"] == "PDF-0001", why


def test_p1_period_choice_two_contracts():
    """K06: два подписанных договора того же номера и байка (текущий и будущий) — выбран договор СРОКА аренды
    обращения; без срока дверь сказала бы «несколько, выбрать нельзя»."""
    reg = Registry([DOC1, DOC2])
    out = run(Script({"tool": "contract", "args": {}}, final("Договор следующим сообщением.")), reg)
    assert outcomes(out, "contract") == [("contract", T.FACT)], [(r["outcome"], r["reason"]) for r in out["results"]]
    docs = [f["doc_id"] for f in T.accepted(out["results"]) if f["kind"] == "contract"]
    assert docs == ["K3-DOC-001"], docs


def test_p1_other_period_named_conflict_not_fact():
    """K07: у номера есть только договор ДРУГОГО периода — не принят, не «договора нет», а назван конфликтом
    (причина «нужен человек»), PDF не прикладывается."""
    reg = Registry([DOC2])
    out = run(Script({"tool": "contract", "args": {}}, {"tool": "contract_pdf", "args": {"file_id": "PDF-0002"}},
                     final("Уточню у коллег.")), reg)
    res = [r for r in out["results"] if r["tool"] == "contract"][0]
    assert res["outcome"] == T.CONFLICT and "вне срока аренды" in res["reason"] and "2026-10-20" in res["reason"], res
    assert not [f for f in T.accepted(out["results"]) if f["kind"] in ("contract", "pdf")]
    words, _ = T.judge("Уточню у коллег.", None, out["results"], out["journal"])
    assert CONTRACT_WORDS in words, words
    meta, why = X.attach_of({"state": T.DONE, "results": out["results"]})
    assert meta is None, meta


def test_p1_incomplete_registry_stays_incomplete():
    """K08: в сроке аренды есть подписанный БЕЗ известного дня — «неполно», не факт, вложения нет."""
    reg = Registry([DOC1, DOC3])
    out = run(Script({"tool": "contract", "args": {}}, final("Договор пришлёт коллега.")), reg)
    res = [r for r in out["results"] if r["tool"] == "contract"][0]
    assert res["outcome"] == T.INCOMPLETE and "без известного дня" in res["reason"], res
    assert reg.calls[0].get("date_from") == TERM[0], reg.calls
    assert not [f for f in T.accepted(out["results"]) if f["kind"] == "contract"]
    assert X.attach_of({"state": T.DONE, "results": out["results"]})[0] is None


def test_p1_foreign_or_conflicting_filter_conflict_no_read():
    """Отрицательный: явный чужой номер (в т.ч. тот же хвост 9 цифр с другим кодом страны), чужой байк, другой срок —
    CONFLICT с причиной; реестр НЕ читается, привязка к обращению не подменяется, чужого документа нет."""
    for args, word in (({"phone": "+66 89 765 4321"}, "договор другого номера"),
                       ({"phone": "+7 981 234 5678"}, "договор другого номера"),
                       ({"bike": "NMAX 155 90202"}, "договор другой аренды"),
                       ({"date_from": "2026-10-20", "date_to": "2026-10-25"}, "договор другой аренды")):
        reg = Registry([DOC1, DOC2])
        out = run(Script({"tool": "contract", "args": args}, final("Ок")), reg)
        res = out["results"][0]
        assert reg.calls == [], (args, reg.calls)
        assert res["outcome"] == T.CONFLICT and res["reason"].startswith(word), (args, res)
        assert not [f for f in T.accepted(out["results"]) if f["kind"] == "contract"], args
        words, _ = T.judge("Ок", None, out["results"], out["journal"])
        assert CONTRACT_WORDS in words, (args, words)


def test_p1_model_name_or_matching_filter_not_used_as_search():
    """Имя модели кодом не проверить — в поиск не идёт; фильтр, совпавший с привязкой (тот же срок), конфликтом не
    становится: в дверь идёт ровно запрос кода."""
    reg = Registry([DOC1, DOC2])
    out = run(Script({"tool": "contract", "args": {"name": "Иван Петров"}},
                     {"tool": "contract", "args": {"date_from": TERM[0], "date_to": TERM[1]}}, final("Ок")), reg)
    assert reg.calls == [{"phone": NUMBER, "date_from": TERM[0], "date_to": TERM[1]}] * 2, reg.calls
    assert outcomes(out) == [("contract", T.FACT), ("contract", T.FACT)], out["results"]


def test_p1_no_number_no_registry_read():
    """Отрицательный: номера обращения нет — без связи с клиентом реестр не читается."""
    reg = Registry([DOC1])
    out = run(Script({"tool": "contract", "args": {}}, final("Ок")), reg, number="")
    assert reg.calls == [] and out["results"][0]["outcome"] != T.FACT, (reg.calls, out["results"])


def test_p1_request_identity_is_code_query():
    """Тождество запроса договора — запрос, посланный КОДОМ: два вызова с разными словами модели и одним запросом двери
    — один запрос; позднее «не факт» того же запроса (таймаут) снимает прежний FACT (AGENTDEDUP0410)."""
    reg = Registry([DOC1], fail_after=1)
    out = run(Script({"tool": "contract", "args": {}},
                     {"tool": "contract", "args": {"date_from": TERM[0], "date_to": TERM[1]}}, final("Ок")), reg)
    a, b = out["results"]
    assert (a["outcome"], b["outcome"]) == (T.FACT, T.TIMEOUT), (a["outcome"], b["outcome"])
    assert a["req"] == b["req"], (a["req"], b["req"])
    assert NUMBER not in a["req"], a["req"]                    # номер обращения в тождество не пишется
    assert not [f for f in T.accepted(out["results"]) if f["kind"] == "contract"]


def test_p1_other_term_search_respects_deadline():
    """K07-поиск без срока — тоже вызов двери: модель думала до T+55, поиск в сроке шёл 40 с (до T+95, за пределом
    сверки AGENTDEDUP0410) — второго обращения к реестру нет; в сроке договора нет — «не найдено» со словами, а не
    поиск после дедлайна. Первый (и единственный) запрос — запрос КОДА."""
    clk = Clock()
    reg = Registry([DOC2])
    stamps = []

    def slow_reg(**kw):
        stamps.append(clk.t)
        out = reg(**kw)
        clk.t += 40.0
        return out

    script = Script({"tool": "contract", "args": {}}, final("Ок"))

    def model(system, user):
        clk.t += 55.0 if not script.seen else 0.0
        return script(system, user)

    out = T.run(model, "S", "U", {"rental": rental_door(), "contract": slow_reg, "contract_pdf": pdf_door},
                number=NUMBER, clock=clk)
    stop = T0 + T.MAX_SEC - T.FALLBACK_SEC
    assert reg.calls == [{"phone": NUMBER, "date_from": TERM[0], "date_to": TERM[1]}], reg.calls
    assert all(t < stop for t in stamps), (stamps, stop)
    res = [r for r in out["results"] if r["tool"] == "contract"][0]
    assert res["outcome"] == T.EMPTY and "предел сверки" in res["reason"], res
    assert out["state"] == T.OVER, out["state"]


# ═══ п.2 СДАЧА кодом ═════════════════════════════════════════════════════════════════════════════════════════

HEAD = "РАСЧЁТ КОДА — сдача"        # голова блока расчёта (в инструкции инструментов слово «РАСЧЁТ КОДА» есть всегда)


def _block(script):
    return [u for u in script.seen if HEAD in u]


def test_p2_c3_change_210_by_code_at_end():
    """С3 (K05): итог 7790 (касса этой аренды и лист), внесено 8000 со слов клиента → в запрос модели код кладёт
    «сдача 210 THB … в конце аренды»; числа черновика имеют опору, «8000» названо словами клиента — причина
    «сумму подтверждает человек», а не «денежное утверждение без опоры»."""
    s = c3_script()
    a = adapter(s, [tx_item()], question=C3_QUESTION)
    out = a.draft(NUMBER, 5)
    blk = _block(s)
    assert blk and "сдача 210 THB" in blk[-1] and "в конце аренды" in blk[-1] and "итог 7790 THB" in blk[-1], s.seen[-1][-600:]
    assert HEAD not in s.seen[0] and HEAD not in s.seen[1], "расчёт до чтения кассы"
    assert K.MONEY_CLAIM_WORDS not in out["handoff"], out["handoff"]
    assert CHANGE_WORDS in out["handoff"], out["handoff"]
    assert out["claims"] == [], out["claims"]


def test_p2_cash_exceeds_total_confirmed_by_cash():
    """Касса записала 8000 при итоге 7790, клиент называет те же 8000 → сдача 210 по КАССЕ: эскалации «со слов
    клиента» нет."""
    s = c3_script()
    a = adapter(s, [tx_item(amount=8000, description="Nmax 90101 +8000 аренда K3-BK-001")], question=C3_QUESTION)
    out = a.draft(NUMBER, 5)
    blk = _block(s)
    assert blk and "сдача 210 THB" in blk[-1] and "касса: оплачено 8000 при итоге 7790" in blk[-1], s.seen[-1][-600:]
    assert CHANGE_WORDS not in out["handoff"] and K.MONEY_CLAIM_WORDS not in out["handoff"], out["handoff"]


def test_p2_deposit_not_added_to_payment():
    """Залог той же аренды в кассе с оплату не складывается: сдача 210, а не «оплачено 12790»."""
    s = c3_script()
    a = adapter(s, [tx_item(), tx_item(row=12, amount=3000, category="deposit",
                                       description="Nmax 90101 залог 3000 K3-BK-001")], question=C3_QUESTION)
    a.draft(NUMBER, 5)
    blk = _block(s)
    assert blk and "сдача 210 THB" in blk[-1] and "12790" not in blk[-1], s.seen[-1][-600:]


def _refused(cash_items, text, why):
    s = c3_script(text)
    a = adapter(s, cash_items, question=C3_QUESTION)
    out = a.draft(NUMBER, 5)
    blk = _block(s)
    assert blk and "сдача НЕ посчитана" in blk[-1] and why in blk[-1], s.seen[-1][-700:]
    assert "сдача 210" not in blk[-1], blk[-1]
    assert K.MONEY_CLAIM_WORDS in out["handoff"], out["handoff"]        # 210 названа без опоры
    assert not T.pay_confirmed(a.last["tools"]["journal"].facts)
    return out


def test_p2_neg_unconfirmed_cash_no_change_no_payment():
    """Отрицательный: в кассе оплаты аренды нет — «отдал 8000 наличными» остаётся словами клиента: ни подтверждения
    оплаты, ни сдачи; текст «оплата 8000 получена» — причина «оплата не подтверждена сверкой»."""
    out = _refused([], "Оплата 8000 бат получена. Сдача 210 бат — в конце аренды, вместе с возвратом залога.",
                   "в кассе нет")
    assert T.PAY_WORDS in out["handoff"], out["handoff"]


def test_p2_neg_foreign_rental_no_change():
    """Отрицательный: в кассе 7790 ЧУЖОЙ аренды (K3-BK-002) — деньгами этой аренды не считаются, сдачи нет."""
    _refused([tx_item(booking="K3-BK-002", description="Nmax 90101 +7790 аренда K3-BK-002")], C3_TEXT, "в кассе нет")


def test_p2_neg_other_currency_no_change():
    """Отрицательный: оплата этой аренды записана в USD — разные валюты не складываются и не пересчитываются."""
    _refused([tx_item(amount=220, currency="USD", description="Nmax 90101 +220 USD аренда K3-BK-001")], C3_TEXT,
             "в другой валюте")


def test_p2_control_no_handed_no_block():
    """КОНТРОЛЬ: клиент не называл переданных наличных — блока «РАСЧЁТ КОДА» нет, запрос прежний."""
    s = Script({"tool": "rental", "args": {}}, {"tool": "cash", "args": {"booking_id": BK}},
               final("Здравствуйте! Подскажу по аренде."))
    adapter(s, [tx_item()], question="Подскажите, до какого числа у меня аренда?").draft(NUMBER, 5)
    assert not _block(s), s.seen


# ═══ п.3 N4: одно определение «текст утверждает, что оплата получена» ═══════════════════════════════════════════

def _facts_no_second_source():
    """Касса этой аренды + её строка листа, второго источника нет (ни договора, ни суммы в переписке)."""
    return T.accepted([T.rental_result({"ok": True, "rows": [dict(ROW)]}, at=T0), T.cash_result(tx([tx_item()]), at=T0)])


AFFIRM = ["Здравствуйте! В кассе вижу оплату аренды по вашей брони от 05.10 на 7790 бат.",          # K15 real
          "Добрый день! Да, оплата аренды NMAX 90101 на 7790 бат у нас отражена, всё в порядке.",  # K02 real
          "Вижу вашу оплату 7790 бат, всё в порядке.",
          "С оплатой всё в порядке, спасибо!",
          "We can see your payment of 7790 baht, all good.",
          "Payment is reflected in our records."]
NOT_CLAIM = ["Оплату пока не вижу — коллега проверит поступление и вам ответит.",
             "Передал коллеге: он сверит поступления по кассе и подтвердит оплату аренды.",           # K04 real
             "Как только оплата отразится в кассе, подтвердим.",
             "Оплата будет подтверждена после сверки.",
             "Оплата подтверждена?",
             "Если оплата прошла, договор пришлём.",
             "Оплата пока не отражена.",
             "We will confirm the payment once it is received."]


def test_p3_affirmative_forms_flagged_without_second_source():
    """N4: утвердительные формы (дословные фразы K15 и K02 реального прогона и близкие) без второго источника —
    причина «оплата не подтверждена сверкой» тем же определением, что у F3 шага 1."""
    facts = _facts_no_second_source()
    for text in AFFIRM:
        assert [w for w, _why in T.money_roles(text, facts)] == [T.PAY_WORDS], text


def test_p3_negation_future_question_not_confirmation_not_blocked():
    """Отрицательный N4: отрицание, обещание будущей проверки, условие и вопрос — не подтверждение: ни ложной
    блокировки причиной, ни сумм «полученной оплаты»."""
    facts = _facts_no_second_source()
    for text in NOT_CLAIM:
        assert T.money_roles(text, facts) == [], (text, T.money_roles(text, facts))
        assert T.pay_claimed(text) == set(), (text, T.pay_claimed(text))


def test_p3_claimed_sums_same_definition():
    """«Сумма, названная полученной оплатой» — тем же определением: у фразы K15 это 7790, у фразы K02 номер байка
    90101 суммой не стал."""
    assert T.pay_claimed(AFFIRM[0]) == {7790}, T.pay_claimed(AFFIRM[0])
    assert T.pay_claimed(AFFIRM[1]) == {7790}, T.pay_claimed(AFFIRM[1])


def test_p3_k15_draft_flagged_end_to_end():
    """K15 real дословно: rental + cash, договора нет — черновик «В кассе вижу оплату…» получает причину кода."""
    text = ("Здравствуйте! В кассе вижу оплату аренды по вашей брони от 05.10 на 7790 бат. Если вы сегодня оплачивали "
            "что-то ещё, коллега проверит поступление и вам ответит. Договор тоже передам коллеге, он пришлёт его "
            "отдельным сообщением.")
    s = Script({"tool": "rental", "args": {}}, {"tool": "cash", "args": {"booking_id": BK}}, final(text))
    out = adapter(s, [tx_item()], question="Я оплатил аренду, подтвердите").draft(NUMBER, 5)
    assert T.PAY_WORDS in out["handoff"], out["handoff"]


def test_p3_control_backed_confirmation_not_blocked():
    """КОНТРОЛЬ: подтверждение с опорой (касса + договор той же аренды) причины не получает — ни на ремонте, ни до."""
    con = T.contract_result(Registry([DOC1])(phone=NUMBER), at=T0, number=NUMBER,
                            rental=T.rental_result({"ok": True, "rows": [dict(ROW)]}, at=T0))
    facts = T.accepted([T.rental_result({"ok": True, "rows": [dict(ROW)]}, at=T0), T.cash_result(tx([tx_item()]), at=T0),
                        con])
    assert T.money_roles(AFFIRM[1], facts) == [], T.money_roles(AFFIRM[1], facts)


# ═══ п.3b N4 (D1 приёмки шага 3, fix_review VERDICT §9): ФОРМЫ, а не список фраз ═══════════════════════════════

CLOSE_ACCEPT = ["В кассе есть ваша оплата аренды на 7790 бат.", "Оплата есть в кассе.",            # приёмка ДОСЛОВНО:
                "Оплата зафиксирована в кассе.", "Аренда оплачена.", "Оплачено, спасибо!",           # fix_review VERDICT §9,
                "Платёж получен.", "Деньги получили, спасибо.", "Your payment went through."]       # out_rv_newx_a :49-56
CLOSE_OWN = ["Оплата за аренду учтена в кассе.", "Ваш перевод пришёл, спасибо.", "Средства зачислены на счёт.",
             "Платёж прошёл успешно.", "Получена ваша оплата за аренду 7790 бат.", "Зафиксировали ваш платёж.",
             "Бронь полностью оплачена.", "Предоплата внесена, спасибо.", "Деньги дошли.",
             "На счёте имеется ваш платёж.",
             "The rental is paid.", "Your rent has been paid.", "We got your transfer, thanks.",
             "The money arrived this morning.", "All paid, thank you!", "Funds have been credited to our account."]
NOT_CLOSE = ["Оплата пока не поступила.", "Аренда ещё не оплачена.", "Деньги ещё не получили.",          # отрицание
             "Платёж поступит завтра.", "Оплата будет зафиксирована после сверки.", "Оплачено будет при выдаче байка.",
             "Платёж должен быть проведён до выдачи байка.",                                          # будущее, долг
             "Проверю, получена ли оплата.", "Если аренда оплачена, договор пришлём.",                 # проверка, условие
             "If the money arrived, please let us know.",
             "Оплачено?", "Деньги получили?", "Has your payment gone through?",                        # вопрос
             "Your payment hasn't gone through yet.",
             "Оплата наличными тоже есть.", "Получили ваш запрос на оплату.", "Payment link received, thank you.",
             "Перевод договора на английский получен.", "Срок оплаты прошёл.", "The rent is paid at pickup."]


def _facts_backed():
    """Касса этой аренды + её строка листа + договор, привязанный к ней кодом: оплата подтверждена, опора 7790."""
    rent = T.rental_result({"ok": True, "rows": [dict(ROW)]}, at=T0)
    con = T.contract_result(Registry([DOC1])(phone=NUMBER), at=T0, number=NUMBER, rental=rent)
    return T.accepted([rent, T.cash_result(tx([tx_item()]), at=T0), con])


def test_p3b_acceptance_close_forms_flagged():
    """D1: 8 близких утвердительных форм приёмки шага 3 (дословно) без второго источника — причина «оплата не
    подтверждена сверкой» тем же определением (`_PayClaim`)."""
    facts = _facts_no_second_source()
    miss = [t for t in CLOSE_ACCEPT if [w for w, _why in T.money_roles(t, facts)] != [T.PAY_WORDS]]
    assert not miss, miss


def test_p3b_own_close_forms_flagged():
    """D1: свои близкие формы RU/EN (причастие оплаты, предмет + сказуемое получения/учёта, сказуемое + предмет) —
    ловятся формами, а не списком."""
    facts = _facts_no_second_source()
    miss = [t for t in CLOSE_OWN if [w for w, _why in T.money_roles(t, facts)] != [T.PAY_WORDS]]
    assert not miss, miss


def test_p3b_not_claims_not_blocked():
    """D1, отрицательный: отрицание, будущее/долженствование, проверка, условие, вопрос; «есть» без кассы/учёта;
    предмет после предлога; «payment link»; «перевод договора»; «срок оплаты»; правило «is paid at pickup» — не
    утверждение: ни причины, ни сумм «полученной оплаты»."""
    facts = _facts_no_second_source()
    bad = [(t, T.money_roles(t, facts), sorted(T.pay_claimed(t))) for t in NOT_CLOSE
           if T.money_roles(t, facts) or T.pay_claimed(t)]
    assert not bad, bad


def test_p3b_claimed_sums_close_forms():
    """D1: сумма, названная полученной оплатой близкой формой, — тем же определением (7790), без чисел — пусто."""
    assert T.pay_claimed(CLOSE_ACCEPT[0]) == {7790}, T.pay_claimed(CLOSE_ACCEPT[0])
    assert T.pay_claimed("Получена ваша оплата за аренду 7790 бат.") == {7790}
    assert T.pay_claimed("Платёж получен.") == set()


def test_p3b_deposit_subject_existing_role():
    """D1 + роли money_roles: подлежащее — залог («Залог оплачен», «деньги за залог получили») — роль залога
    (`_DEP_CLAIM`), а не оплата аренды; аренда названа раньше залога — утверждение оплаты аренды."""
    facts = _facts_no_second_source()
    assert [w for w, _why in T.money_roles("Залог оплачен.", facts)] == [T.ROLE_WORDS]
    assert T.pay_claimed("Залог оплачен.") == set()
    assert T.PAY_WORDS not in [w for w, _why in T.money_roles("Деньги за залог получили.", facts)]
    assert T.PAY_WORDS in [w for w, _why in T.money_roles("Аренда и залог оплачены.", facts)]


def test_p3b_control_backed_close_forms_not_blocked():
    """КОНТРОЛЬ D1: близкие формы С опорой (касса + договор той же аренды, сумма 7790) — причины нет."""
    facts = _facts_backed()
    assert T.pay_confirmed(facts) is True
    bad = [(t, T.money_roles(t, facts)) for t in CLOSE_ACCEPT + CLOSE_OWN if T.money_roles(t, facts)]
    assert not bad, bad


# ═══ п.3c: те же исключения не-утверждений у ПРЕЖНИХ форм `_PAY_AFFIRM`; исход каждого совпадения НАЗВАН ═══════

# имена исходов — литералами: на 6f6e754 и старше таких констант нет (как SV_WORDS выше)
V_CLAIM, V_WORD = "утверждение", "основа сказуемого — начало другого слова"
V_MUST, V_PREP, V_NEXT = "долженствование или ожидание", "предмет после предлога", "предмет — документ, а не оплата"
V_EXIST, V_DEP = "«есть» без кассы, учёта, счёта или «ваша оплата»", "подлежащее — залог"

# не-утверждения, которые ловили ПРЕЖНИЕ формы: на 6f6e754 каждое получало причину «оплата не подтверждена сверкой»
OLD_NOT = [("После оплаты договор пришлём.", V_WORD),                              # три названные решением — дословно
           ("Оплата должна быть получена до выдачи байка.", V_MUST),
           ("Оплата должна быть получена до выдачи…", V_MUST),
           ("Ссылку на оплату получили.", V_PREP),
           ("Оплата требует подтверждения коллегой.", V_MUST),                     # FIX.md «Шаг 3b» п.7.4
           ("Оплата за прошлую неделю.", V_WORD),
           ("Оплата обязательно должна быть подтверждена коллегой.", V_MUST),      # долженствование и ожидание
           ("Оплата ожидает подтверждения.", V_MUST),
           ("Оплата ждёт подтверждения коллегой.", V_MUST),
           ("Payment must be recorded before pickup.", V_MUST),
           ("Счёт на оплату получили, спасибо.", V_PREP),                           # предмет после предлога цели/времени
           ("Реквизиты для оплаты получили.", V_PREP),
           ("Вижу запрос на оплату.", V_PREP),
           ("После оплаты бронь подтверждается автоматически.", V_PREP),
           ("Без оплаты бронь подтверждена только на сутки.", V_PREP),
           ("До оплаты бронь подтверждена только на сутки.", V_PREP),
           ("Перед оплатой получите подтверждение брони.", V_PREP),
           ("Link for payment received, thank you.", V_PREP),
           ("We keep the bike for you without payment received until tomorrow.", V_PREP),
           ("Оплата при получении байка, наличными или переводом.", V_WORD),        # основа внутри другого слова
           ("Оплату пришлите, пожалуйста, на карту.", V_WORD),
           ("Оплату пришлось вернуть клиенту.", V_WORD),
           ("Оплата видимо ещё в пути.", V_WORD),
           ("Получили перевод договора, спасибо.", V_NEXT),                         # документ, а не оплата
           ("Payment details recorded in the booking.", V_NEXT)]
# те же исключения у форм шага 3b — тем же именем (одно определение на оба прохода)
SAME_3B = [("Платёж должен быть проведён до выдачи байка.", V_MUST), ("Оплачено будет при выдаче байка.", V_MUST),
           ("Получили ваш запрос на оплату.", V_PREP), ("Payment link received, thank you.", V_NEXT),
           ("Оплата наличными тоже есть.", V_EXIST), ("Залог оплачен.", V_DEP), ("Деньги за залог получили.", V_DEP)]
# прежде пойманные утверждения прежних форм и положительные близнецы каждого исключения — по-прежнему ловятся
OLD_AFFIRM = ["Оплата получена.", "Мы получили вашу оплату.", "Оплата прошла, всё хорошо.", "Оплата пришла, спасибо.",
              "Оплату видим в кассе, спасибо.", "Оплата подтверждена коллегой.", "Предоплата получена, спасибо.",
              "Доплата 500 бат получена.", "Payment received, thank you.", "We received your payment.",
              "Your payment is reflected in the cash book.",
              "С оплатой всё в порядке, спасибо!", "По оплате всё в порядке.",       # предлог темы — утверждение
              "Подтверждение об оплате получено.", "По оплате есть подтверждение.",
              "Получили вашу оплату на карту.", "Оплата до выдачи байка получена.",   # предлог НЕ перед предметом
              "Оплата без комиссии получена.", "После проверки кассы оплата 7790 бат получена.",
              "После того как оплата поступила, мы отправили договор.",
              "Оплата за прошлую неделю получена.",                                 # «прошлую» — не сказуемое, оно дальше
              "Оплаты за прошлую и эту недели получены.",
              "Оплата должным образом отражена в кассе.",                           # «должным образом» — не долженствование
              "Оплата получена, договор будет у вас завтра.",                       # будущее в ДРУГОЙ клаузе
              "Оплата подтверждена, больше ничего не требуется.",
              "Получили перевод, спасибо."]                                         # перевод денег, не документа


def _verdicts(text):
    return {v for _match, v in T._PAY_CLAIM.explain(text)}


def test_p3c_old_forms_not_claims_not_blocked():
    """п.3c: не-утверждения прежних форм (в т.ч. три названные решением дословно) — ни причины «оплата не подтверждена
    сверкой», ни сумм «полученной оплаты». На 6f6e754 каждая из них причину получала."""
    facts = _facts_no_second_source()
    bad = [(t, T.money_roles(t, facts), sorted(T.pay_claimed(t))) for t, _name in OLD_NOT
           if T.money_roles(t, facts) or T.pay_claimed(t)]
    assert not bad, bad


def test_p3c_not_claim_names_its_exclusion():
    """п.3c: исход совпадения НАЗВАН — у каждой фразы имя того исключения, которое к ней относится (а не «какое-то
    сработало»), и одно и то же у прежних форм и у форм 3b (одно определение на оба прохода)."""
    wrong = [(t, name, T._PAY_CLAIM.explain(t)) for t, name in OLD_NOT + SAME_3B if _verdicts(t) != {name}]
    assert not wrong, wrong


def test_p3c_verdict_never_empty_two_former_blind_branches():
    """п.3c, храповик слепых читателей: исход — всегда НЕПУСТОЕ имя; `search` говорит «утверждение» ровно тогда, когда
    так назван хотя бы один исход. Две ветки, которые до 3c отдавали голое False оттого, что шаблон НЕ нашёл слова
    кассы или аренды, называют себя; с найденным словом — утверждение (положительные близнецы)."""
    every = (AFFIRM + NOT_CLAIM + CLOSE_ACCEPT + CLOSE_OWN + NOT_CLOSE + OLD_AFFIRM
             + [t for t, _name in OLD_NOT + SAME_3B])
    for text in every:
        got = T._PAY_CLAIM.explain(text)
        assert all(isinstance(v, str) and v.strip() for _match, v in got), (text, got)
        assert (V_CLAIM in [v for _match, v in got]) == bool(T._PAY_CLAIM.search(text)), (text, got)
    assert _verdicts("Оплата наличными тоже есть.") == {V_EXIST}
    assert _verdicts("Для вашего удобства есть оплата картой.") == {V_EXIST}
    assert _verdicts("Залог оплачен.") == {V_DEP} and _verdicts("Деньги за залог получили.") == {V_DEP}
    assert V_CLAIM in _verdicts("Оплата есть в кассе.") and V_CLAIM in _verdicts("На счёте имеется ваш платёж.")
    assert V_CLAIM in _verdicts("Аренда и залог оплачены.")


def test_p3c_must_governs_predicate_not_whole_clause():
    """п.3c: долженствование и будущее снимают утверждение, только когда управляют сказуемым — стоят в клаузе до конца
    сказуемого или сразу за ним. Слово дальше — уже другое сказуемое: «Аренда оплачена и договор будет отправлен
    завтра.» — утверждение (на 6f6e754 у форм 3b «будет» где угодно в клаузе снимало его)."""
    facts = _facts_no_second_source()
    for text in ("Аренда оплачена и договор будет отправлен завтра.", "Оплата получена и договор будет отправлен завтра.",
                 "Деньги получили и байк будет ждать вас утром."):
        assert [w for w, _why in T.money_roles(text, facts)] == [T.PAY_WORDS], (text, T._PAY_CLAIM.explain(text))
    for text in ("Оплачено будет при выдаче байка.", "Аренда оплачена должна быть до выдачи байка.",
                 "Платёж должен быть проведён до выдачи байка.", "Оплата должна быть получена до выдачи байка."):
        assert T.money_roles(text, facts) == [], (text, T._PAY_CLAIM.explain(text))


def test_p3c_control_nothing_caught_is_lost():
    """КОНТРОЛЬ п.3c: ни одно прежде пойманное утверждение не теряется — K15 и формы K02 реального прогона (AFFIRM),
    8 форм приёмки шага 3 дословно (CLOSE_ACCEPT), свои формы 3b (CLOSE_OWN) и прежние формы с положительными
    близнецами исключений (OLD_AFFIRM): причина «оплата не подтверждена сверкой» — как на 6f6e754."""
    facts = _facts_no_second_source()
    miss = [(t, T.money_roles(t, facts)) for t in AFFIRM + CLOSE_ACCEPT + CLOSE_OWN + OLD_AFFIRM
            if [w for w, _why in T.money_roles(t, facts)] != [T.PAY_WORDS]]
    assert not miss, miss
    assert T.pay_claimed("После проверки кассы оплата 7790 бат получена.") == {7790}
    # роль залога на прежние формы НЕ распространена: «залог» раньше «аренды» в клаузе оплату аренды не снимает
    assert T.PAY_WORDS in [w for w, _why in T.money_roles("Залог и оплата аренды получены.", facts)]


# ═══ п.3d: R1 — потерянные утверждения, R2 — контроль из объединения списков, R3 — два семейства ═══════════════

V_NOT, V_LATER, V_ASKED = "отрицание", "будущее, проверка или условие", "вопрос"
V_THEIR = "получатель — клиент, а не мы"

# КОРПУСА ПРОВЕРЯЮЩЕГО кругов 3b+3c — ДОСЛОВНО, данными (источник: tmp/k3_0910/fix_review3c/rv3c_corpus.py, sha256
# f5ac0c13…8211, и rv3c_corpus2.py, 04294a3d…70df; имена списков — те же с приставкой RV_). ACCEPT8 = CLOSE_ACCEPT выше.
RV_K15 = ("Здравствуйте! В кассе вижу оплату аренды по вашей брони от 05.10 на 7790 бат. Если вы сегодня оплачивали "
          "что-то ещё, коллега проверит поступление и вам ответит. Договор тоже передам коллеге, он пришлёт его "
          "отдельным сообщением.")
RV_K02 = "Добрый день! Да, оплата аренды NMAX 90101 на 7790 бат у нас отражена, всё в порядке."
RV_OWN_AFFIRM = [
    "Ваш платёж зачислен, спасибо.", "Оплату за аренду приняли, спасибо.", "Перевод на 7790 бат дошёл.",
    "Деньги за аренду пришли, всё отлично.", "Аренда за 10 дней оплачена полностью.", "Всё оплачено, ждём вас завтра.",
    "Мы зафиксировали вашу оплату в журнале.", "Платёж по вашей брони проведён.", "Вашу оплату подтверждаю.",
    "Средства поступили на наш счёт сегодня утром.", "Оплата аренды внесена в полном объёме.",
    "Предоплата за байк учтена.", "Видим ваш перевод, спасибо.", "Подтверждаем: оплата принята.",
    "Your payment has cleared.", "The transfer has been credited, thank you.",
    "We have received the funds for your rental.", "Your booking is fully paid.", "The rental was paid yesterday.",
    "Payment for your booking has been processed.", "Your money came through this morning.",
    "The rent is paid, thank you.", "We confirmed your payment.", "Your transfer arrived safely."]
RV_OWN_NOT = [
    "Ваш платёж пока не зачислен.", "Перевод ещё не дошёл до нас.", "К сожалению, средства на счёт не поступили.",
    "The transfer has not arrived yet.", "Your booking isn't paid yet.", "Как только перевод дойдёт, сразу сообщим.",
    "Платёж будет проведён завтра утром.", "Мы проверим, зачислены ли средства.",
    "We will let you know once the funds are credited.", "Your payment will be processed tomorrow.",
    "Если перевод уже дошёл, пришлём договор.", "When the money arrives, we'll confirm.",
    "Once your payment has cleared, the booking is confirmed.", "Платёж уже проведён?", "Вы уже оплатили аренду?",
    "Has the transfer been credited?", "Аренда оплачена?", "Аренда должна быть оплачена до выдачи байка.",
    "The rent must be paid before pickup.", "Оплату нужно внести до 12:00.", "Перевод ожидается сегодня.",
    "Оплата ожидается сегодня, пока не поступила."]
RV_NAMED3 = ["После оплаты договор пришлём.", "Оплата должна быть получена до выдачи байка.",
             "Ссылку на оплату получили."]
RV_OWN_PLAIN = [
    "Ваш запрос получен, скоро ответим.", "После оплаты пришлём договор.", "Оплата должна поступить до выдачи байка.",
    "Ссылку на оплату отправили вам в этот чат.", "Ваше сообщение получили, спасибо.", "Документы получены, спасибо.",
    "Оплата возможна наличными или переводом.", "Оплата производится при получении байка.",
    "Способ оплаты подтвердим позже.", "Для оплаты пришлите, пожалуйста, фото паспорта.",
    "Когда поступит оплата, мы сообщим.", "Оплата картой проходит через терминал.",
    "Бронь подтверждена, оплата при встрече.", "Заявку на возврат залога получили.",
    "Чек об оплате пришлите сюда, пожалуйста.", "Оплата за следующий месяц должна прийти до пятницы.",
    "Информацию об оплате вы получите в договоре.", "Подтверждение оплаты придёт вам на почту.",
    "Оплата прошлого месяца не учитывается.", "Мы приняли вашу заявку на оплату картой.",
    "Получили ваш вопрос про перевод.", "Вижу ваше сообщение про деньги.", "Есть оплата картой и наличными.",
    "Оплаченные дни не возвращаются.", "Сумма к оплате указана в договоре.", "Оплата принимается наличными.",
    "Your request has been received, we will reply soon.", "We sent you the payment link.",
    "Payment is due at pickup.", "The payment details are in the contract."]
RV_ADVERSARIAL = [
    "You should know that your payment has been received.",
    "I need to let you know that your payment has been received.",
    "I should mention that we received your payment.", "We have to tell you that the payment is confirmed.",
    "Thank you for the payment received today.", "Thanks for your payment received.",
    "7790 бат на оплату аренды получены.", "Сумма на оплату аренды получена.", "Деньги на оплату аренды получены.",
    "Ваша оплата должна была поступить вчера и поступила.", "Надо сказать что оплата получена.",
    "Оплата получена нужно только подписать договор.", "Без оплаты залога оплата аренды получена.",
    "После оплаты получили ваш чек, всё в порядке.", "Вашу оплату для брони получили.",
    "После вашего перевода оплата получена.", "На карту оплата получена.", "Оплата на карту получена.",
    "Оплата получена, нужно только подписать договор.", "Оплата получена и байк ждёт вас.",
    "Payment received and you should get the contract soon.",
    "Your payment has been received and we will send the contract.", "Как и должно быть, оплата получена.",
    "Оплата необходимой суммы получена.", "Оплата ожидаемой суммы получена.", "Байк ждёт вас, оплата получена."]
# RESIDUAL_INFO проверяющего (16 наблюдений): 14 — с причиной; две фразы БЕЗ слова оплаты, денег или суммы
# («Да, всё пришло.», «We got it, thanks!») определение по ТЕКСТУ не судит — их смысл задаёт вопрос клиента, которого
# `money_roles` не видит (остаток круга 3d, назван в FIX.md); набор о них ничего не утверждает
RV_RESIDUAL = [
    "Подтвердили поступление оплаты, спасибо.", "Подтверждаю получение оплаты.",
    "Подтверждаем поступление оплаты за аренду.", "Поступление оплаты подтверждаем.", "Получили 7790 бат, спасибо.",
    "Да, 7790 бат получили.", "Деньги у нас, спасибо.", "Сумма получена.",
    "Платёж 4100 бат в кассе записан на другую бронь, а 150 долларов — в иностранной валюте; подтверждать сам не "
    "буду — передаю коллеге.",
    "Подтверждаю оплату при получении байка: наличными.", "Оплата получена не полностью.",
    "Платёж принят банком в обработку.", "Бронь подтверждена оплата при встрече", "Payment confirmed."]
RV_RESIDUAL_OPEN = ["Да, всё пришло.", "We got it, thanks!"]
RV_OLD_CONTROL = [
    "Оплата получена.", "Мы получили вашу оплату.", "Оплата 7790 бат получена, спасибо.", "Оплата 8000 бат получена.",
    "Оплата прошла успешно.", "Оплата поступила, спасибо.", "Оплату вижу, всё в порядке.", "С оплатой всё в порядке.",
    "Оплата подтверждена.", "Получили деньги, спасибо.", "Получили перевод, спасибо.", "Payment received, thank you.",
    "We received your payment.", "Payment is confirmed.", "Paid in full, thank you.", "We can see your payment.",
    "Payment has been received.", "Ваша оплата за аренду у нас отражена.", "В кассе видна ваша оплата.",
    "Оплата аренды за 10 дней пришла."]
RV_MORE_ADV = [
    "We must confirm that we received your payment in full.", "Thank you for your payment received on 5 October.",
    "We need to mention the payment is confirmed.", "Ваши 7790 бат на оплату аренды поступили.",
    "Сумма для оплаты брони поступила.", "8000 бат для оплаты аренды получили, спасибо.",
    "Оплата за аренду должна была прийти вчера и пришла.", "На оплату аренды получили от вас 7790 бат.",
    "После оплаты всё прошло успешно.", "Вам нужно знать что оплата получена.",
    "You need to know your payment is confirmed.", "Должен сообщить что ваша оплата поступила."]
RV_TWINS_OK = [
    "Just to let you know that your payment has been received.",
    "I'm happy to confirm that your payment has been received.", "Thank you, payment received for the rental.",
    "Перевод для оплаты аренды получили.", "В счёт оплаты аренды получили 7790 бат.", "Оплату на 7790 бат получили.",
    "Вам нужно знать: оплата получена.", "Должен сообщить, что ваша оплата поступила.",
    "Нужно отметить: оплата получена.", "Оплата до 12:00 получена."]
RV_TWINS_NOT = [
    "You should pay before pickup so that the payment is confirmed.", "The payment must be received before pickup.",
    "Ссылку для оплаты получили?", "Счёт на оплату аренды получен, спасибо.",
    "После оплаты подтверждение придёт автоматически.", "Оплата должна была поступить вчера.",
    "Thank you for your payment request, received.", "We need to confirm your payment first."]

# СВОИ фразы шага 3d (нет ни в одном прежнем корпусе)
R1_OWN = [                                              # R1: слово долженствования и предлог — НЕ при этом сказуемом
    "You should know we received your payment.", "I should add that your payment has cleared.",
    "Надо отметить что платёж получен.", "Должны сообщить что деньги поступили.",
    "Оплата должна была поступить сегодня и поступила.", "Thanks a lot for the payment received yesterday.",
    "Перевод на оплату аренды получили.", "3000 бат на оплату продления получены.",
    "Оплата получена можно забирать байк.", "Можем сообщить что оплата поступила.",
    "We will send the contract now that your payment has been received.",    # причинный союз без запятой
    "Договор отправим сегодня потому что оплата получена.",
    "Без оплаты доставки оплата аренды получена.", "После оплаты получили от вас чек, спасибо.",
    "It should be noted that your payment has been received.",
    "For the payment received yesterday, thank you.", "Отправленное вами на оплату аренды получили."]
R1_OWN_NOT = [                                          # те же исключения там, где они на своём месте
    ("Нужно проверить что оплата прошла.", V_MUST),                        # обязанность ПРОВЕРИТЬ — не утверждение
    ("We need to check that your payment has been received.", V_MUST),
    ("Нужно чтобы оплата поступила до выдачи байка.", V_MUST),             # цель
    ("Оплата должна быть получена и подтверждена до выдачи байка.", V_MUST),
    ("We need to wait until the payment is confirmed.", V_MUST),
    ("Оплата может быть произведена наличными или картой.", V_MUST),       # возможность — правило, а не факт
    ("The payment should have been received by Friday.", V_MUST),
    ("Оплата должна до выдачи байка быть получена.", V_MUST),
    ("Payment can be made in cash or by transfer.", None),
    ("Payment can be received in cash or by transfer.", V_MUST),
    ("Ссылку на оплату 7790 бат получили.", V_PREP),
    ("После оплаты 7790 бат бронь подтверждается автоматически.", V_PREP),
    ("Квитанцию для оплаты получили.", V_PREP),
    ("Invoice for payment received, thanks.", V_PREP),
    ("Thank you for your payment request received yesterday.", V_NEXT)]
R3_NOUN_AFFIRM = [                                      # R3 (i): подтверждение получения существительным
    "Подтверждаю получение платежа.", "Подтверждаем поступление предоплаты.",
    "Подтвердили зачисление средств, спасибо.", "Получение денег подтверждаем.", "Поступление платежа подтверждено.",
    "Подтверждаю приход оплаты за аренду.", "Могу подтвердить получение оплаты.", "Вижу поступление 7790 бат от вас.",
    "We confirm receipt of your payment.", "I can confirm receipt of your transfer.",
    "We acknowledge receipt of the funds.", "Confirmed receipt of your payment, thank you.",
    "Receipt of your transfer acknowledged.", "Payment receipt confirmed."]
R3_NOUN_NOT = [
    ("Поступление оплаты подтвердить не могу.", None), ("Подтвердим получение оплаты после сверки.", None),
    ("Подтвердите получение договора, пожалуйста.", None), ("Подтверждение получения оплаты придёт на почту.", None),
    ("Подтверждаю получение паспорта и прав.", None), ("Подтверждаем поступление заявки.", None),
    ("Вы подтвердили получение оплаты?", V_ASKED), ("Поступление оплаты должно быть подтверждено коллегой.", V_MUST),
    ("Подтверждаю получение залога.", None), ("We will confirm receipt of your payment tomorrow.", None),
    ("Can you confirm receipt of the payment?", None), ("Please confirm receipt of the payment link.", None),
    ("We confirm receipt of your documents.", None), ("We cannot confirm receipt of your payment yet.", None)]
R3_SUM_AFFIRM = [                                       # R3 (ii): сказуемое получения с суммой или словом суммы
    "Получили от вас 7790 бат, спасибо.", "7790 бат поступили на счёт.", "Ваши 7790 бат получены.",
    "Сумму получили полностью.", "Вся сумма поступила, спасибо.", "Деньги уже у нас.", "Ваши 7790 бат у нас.",
    "Приняли 7790 бат наличными.", "Поступило 7 790 бат, спасибо.", "Получили 7790, спасибо.",
    "We received 7790 baht, thank you.", "Got your 7790 THB, thanks.", "7790 baht has been received.",
    "The full amount has been received.", "We have received the full amount.", "We have your payment.",
    "Your 7790 baht arrived this morning."]
R3_SUM_NOT = [
    ("7790 бат пока не получили.", V_NOT), ("Сумма ещё не поступила.", V_NOT),
    ("Как только 7790 бат поступят, сообщим.", None), ("Сумма будет получена завтра.", V_LATER),
    ("Если сумма получена, пришлём договор.", V_LATER), ("Вы получили 7790 бат?", V_ASKED),
    ("Сумма должна быть получена до выдачи байка.", V_MUST),
    ("Получили ваш запрос на 7790 бат.", V_PREP), ("Счёт на сумму 7790 бат получили.", V_PREP),       # документ
    ("За 7790 бат получили бы NMAX на 10 дней.", V_PREP),
    ("Получили ваш паспорт и фото прав, спасибо.", None), ("Получили 3 фото, спасибо.", None),
    ("2 батареи получили, спасибо.", None),
    ("Итог аренды 7790 бат.", None), ("Итого к оплате 7790 бат.", None), ("С 8000 сдача 210 бат.", None),   # цена, итог, сдача
    ("Вы написали, что перевели 7790 бат.", None),                                                  # слова клиента
    ("Вы получили 500 бат обратно.", V_THEIR), ("You received 210 baht change.", V_THEIR),
    ("Получили 3000 бат залога.", V_DEP),                                                           # роль залога
    ("Оплата у нас проходит через терминал.", None), ("We have not received 7790 baht yet.", V_NOT),
    ("The total is 7790 baht.", None), ("We received your request for 7790 baht.", V_PREP),
    ("Once we have your payment, we will confirm.", V_LATER)]
ADV_AFFIRM = [                                          # свой состязательный поиск шага 3d: чинено тем же определением
    "Оплата произведена, спасибо.", "Оплата успешно завершена.", "Платёж успешно обработан.",
    "Оплата засчитана, бронь за вами.", "Оплата зачтена в счёт аренды.", "Мы увидели вашу оплату, спасибо.",
    "Ваша оплата отображается в кассе.", "Оплата выполнена успешно.", "Оплата в системе есть.",
    "Спасибо за оплату!", "Благодарим за оплату аренды.", "Your payment was successful.",
    "Payment successful, thank you.", "Your payment came in this morning.", "Your payment has landed, thanks.",
    "Your payment has been made, thank you.", "Thank you for your payment!", "Thanks for the transfer.",
    "Paid, thank you!"]
ADV_NOT = [
    ("Оплата ещё не произведена.", V_NOT), ("Your payment was not successful.", V_NOT),
    ("Оплата обрабатывается банком до трёх дней.", None), ("Заранее спасибо за оплату.", None),
    ("Thank you in advance for your payment.", None), ("Спасибо за вопрос про оплату.", None),
    ("Спасибо за перевод договора.", None), ("Thank you for the payment details.", None),
    ("Thanks for the payment confirmation, our colleague will check it.", None),
    ("Спасибо за оплату залога.", V_DEP), ("Договор не отправили потому что оплата не получена.", V_NOT),
    ("The rent can be paid at pickup.", None), ("Оплата в системе появится завтра.", None)]


def _pay(text, facts):
    return T.PAY_WORDS in [w for w, _why in T.money_roles(text, facts)]


def _blocked(pairs, facts):
    """Не-утверждения, получившие причину оплаты, сумму «полученной оплаты» или НЕ то имя исхода."""
    return [(t, name, T.money_roles(t, facts), sorted(T.pay_claimed(t)), T._PAY_CLAIM.explain(t)) for t, name in pairs
            if _pay(t, facts) or T.pay_claimed(t) or (name is not None and _verdicts(t) != {name})]


def test_p3d_r1_lost_claims_caught_again():
    """R1: 38 состязательных утверждений проверяющего (ADVERSARIAL 26 + MORE_ADV 12) и свои того же строя — причина
    «оплата не подтверждена сверкой», как на cbe186f и 6f6e754. На f6ed7bd 25 из 38 терялись: модальное слово главной
    части («You should know that…», «Надо сказать что…») и предлог перед словом оплаты («7790 бат на оплату аренды
    получены», «Thank you for the payment received») снимали утверждение. Сумма возвращается в `pay_claimed`."""
    facts = _facts_no_second_source()
    miss = [(t, T._PAY_CLAIM.explain(t)) for t in RV_ADVERSARIAL + RV_MORE_ADV + R1_OWN if not _pay(t, facts)]
    assert not miss, miss
    assert T.pay_claimed("7790 бат на оплату аренды получены.") == {7790}
    assert T.pay_claimed("На оплату аренды получили от вас 7790 бат.") == {7790}


def test_p3d_r1_exclusions_stay_where_they_belong():
    """R1, отрицательный: долженствование ПРИ сказуемом, обязанность проверить или дождаться, цель («чтобы», «so
    that»), возможность, документ перед предлогом цели, правило «после оплаты …» — по-прежнему не утверждение, и исход
    назван своим именем. Ложные блокировки, снятые шагом 3c, не вернулись (OLD_NOT, три названные решением)."""
    facts = _facts_no_second_source()
    bad = _blocked(R1_OWN_NOT + OLD_NOT, facts)
    assert not bad, bad


def test_p3d_r2_union_of_all_known_lists_nothing_lost_nothing_blocked():
    """R2: контроль «ничего не потеряно» — из ОБЪЕДИНЕНИЯ всех известных списков, а не из списков строителя: реальный
    прогон (K15, K02), приёмка шага 3, списки шагов 3–3c, корпуса проверяющего 3b+3c (вшиты выше дословно), свои
    списки шага 3d. Каждое утверждение — с причиной; каждое не-утверждение — без причины и без сумм (мутант «у форм
    прочие предлоги не судятся» краснит именно здесь: «Получили ваш вопрос про перевод.»). На f6ed7bd — красный."""
    facts = _facts_no_second_source()
    claims = (AFFIRM + CLOSE_ACCEPT + CLOSE_OWN + OLD_AFFIRM + [RV_K15, RV_K02] + RV_OWN_AFFIRM + RV_ADVERSARIAL
              + RV_MORE_ADV + RV_OLD_CONTROL + RV_TWINS_OK + RV_RESIDUAL + R1_OWN + R3_NOUN_AFFIRM + R3_SUM_AFFIRM
              + ADV_AFFIRM)
    nots = (NOT_CLAIM + NOT_CLOSE + RV_OWN_NOT + RV_NAMED3 + RV_OWN_PLAIN + RV_TWINS_NOT
            + [t for t, _name in OLD_NOT + SAME_3B + R1_OWN_NOT + R3_NOUN_NOT + R3_SUM_NOT + ADV_NOT])
    assert len(set(claims)) >= 200 and len(set(nots)) >= 160, (len(set(claims)), len(set(nots)))
    lost = [t for t in claims if not _pay(t, facts)]
    assert not lost, lost
    blocked = [(t, sorted(T.pay_claimed(t))) for t in nots if _pay(t, facts) or T.pay_claimed(t)]
    assert not blocked, blocked


def test_p3d_reviewer_not_claims_no_reason():
    """Отрицательный (зелёный и на f6ed7bd): не-утверждения корпусов проверяющего — NAMED3, OWN_PLAIN, TWINS_NOT,
    OWN_NOT — ни одной причины оплаты и ни одной суммы «полученной оплаты»."""
    facts = _facts_no_second_source()
    bad = [(t, T.money_roles(t, facts), sorted(T.pay_claimed(t)))
           for t in RV_NAMED3 + RV_OWN_PLAIN + RV_TWINS_NOT + RV_OWN_NOT if _pay(t, facts) or T.pay_claimed(t)]
    assert not bad, bad


def test_p3d_r3_noun_family_confirm_receipt():
    """R3 (i): подтверждение получения, поступления, зачисления оплаты / платежа / денег / средств отглагольным
    существительным (RU и EN) — утверждение; отрицание, будущее, вопрос, долженствование, просьба подтвердить,
    «подтверждение … придёт», получение документа, роль залога — нет."""
    facts = _facts_no_second_source()
    miss = [(t, T._PAY_CLAIM.explain(t)) for t in R3_NOUN_AFFIRM + RV_RESIDUAL[:4] if not _pay(t, facts)]
    assert not miss, miss
    bad = _blocked(R3_NOUN_NOT, facts)
    assert not bad, bad


def test_p3d_r3_sum_family_receipt_with_amount():
    """R3 (ii): сказуемое получения с денежной суммой или словом суммы без слова «оплата» (RU и EN), «деньги у нас» —
    утверждение, сумма идёт в `pay_claimed` и сверяется с деньгами аренды; сумма как цена, итог, сдача; документ
    («запрос на 7790 бат»); слова клиента; получатель — клиент; роль залога; число без валюты не у сказуемого — нет."""
    facts = _facts_no_second_source()
    miss = [(t, T._PAY_CLAIM.explain(t)) for t in R3_SUM_AFFIRM + RV_RESIDUAL[4:8] if not _pay(t, facts)]
    assert not miss, miss
    assert T.pay_claimed("Получили 7790 бат, спасибо.") == {7790}
    assert T.pay_claimed("Да, 7790 бат получили.") == {7790}
    assert T.pay_claimed("Получили 7790, спасибо.") == {7790}
    assert T.pay_claimed("Сумма получена.") == set()
    bad = _blocked(R3_SUM_NOT, facts)
    assert not bad, bad
    backed = _facts_backed()                             # с опорой: своя сумма — без причины, чужая — причина
    assert T.money_roles("Получили 7790 бат, спасибо.", backed) == []
    assert [w for w, _why in T.money_roles("Получили 8000 бат, спасибо.", backed)] == [T.PAY_WORDS]


def test_p3d_reviewer_residual_caught():
    """RESIDUAL_INFO проверяющего: 14 из 16 наблюдений — с причиной (8 фраз двух семейств R3 и 6, пойманных прежде).
    Две фразы без слова оплаты, денег или суммы (`RV_RESIDUAL_OPEN`) набор НЕ утверждает ни в одну сторону."""
    facts = _facts_no_second_source()
    miss = [(t, T._PAY_CLAIM.explain(t)) for t in RV_RESIDUAL if not _pay(t, facts)]
    assert not miss, miss
    assert len(RV_RESIDUAL) + len(RV_RESIDUAL_OPEN) == 16


def test_p3d_own_adversarial_search():
    """Свой состязательный поиск шага 3d (существенные находки чинены тем же определением): сказуемые-синонимы
    («произведена», «завершена», «обработан», «засчитана», «увидели», «отображается»; successful, came in, landed,
    has been made), благодарность за оплату, «в системе есть», краткое «Paid, …» — утверждение; их отрицания, «заранее
    спасибо», «спасибо за вопрос про оплату», «payment details», «обрабатывается», залог — нет."""
    facts = _facts_no_second_source()
    miss = [(t, T._PAY_CLAIM.explain(t)) for t in ADV_AFFIRM if not _pay(t, facts)]
    assert not miss, miss
    bad = _blocked(ADV_NOT, facts)
    assert not bad, bad


def test_p3d_verdict_named_on_every_road():
    """Храповик слепых читателей: у новых веток шага 3d исход — тоже всегда НЕПУСТОЕ имя, и `search` говорит
    «утверждение» ровно тогда, когда так назван хотя бы один исход; новое имя «получатель — клиент» названо."""
    every = (RV_OWN_AFFIRM + RV_OWN_NOT + RV_NAMED3 + RV_OWN_PLAIN + RV_ADVERSARIAL + RV_RESIDUAL + RV_RESIDUAL_OPEN
             + RV_OLD_CONTROL + RV_MORE_ADV + RV_TWINS_OK + RV_TWINS_NOT + R1_OWN + R3_NOUN_AFFIRM + R3_SUM_AFFIRM
             + ADV_AFFIRM + [t for t, _name in R1_OWN_NOT + R3_NOUN_NOT + R3_SUM_NOT + ADV_NOT])
    for text in every:
        got = T._PAY_CLAIM.explain(text)
        assert all(isinstance(v, str) and v.strip() for _match, v in got), (text, got)
        assert (V_CLAIM in [v for _match, v in got]) == bool(T._PAY_CLAIM.search(text)), (text, got)
    assert _verdicts("Вы получили 500 бат обратно.") == {V_THEIR}
    assert _verdicts("Получили 3000 бат залога.") == {V_DEP}


def test_p3d_control_backed_new_families_not_blocked():
    """КОНТРОЛЬ п.3d: новые семейства С опорой (касса + договор той же аренды, сумма 7790) причины не получают — ни на
    ремонте, ни до него."""
    facts = _facts_backed()
    assert T.pay_confirmed(facts) is True
    bad = [(t, T.money_roles(t, facts)) for t in R3_NOUN_AFFIRM + R3_SUM_AFFIRM + ADV_AFFIRM + RV_RESIDUAL[:8]
           if T.money_roles(t, facts)]
    assert not bad, bad


# ═══ п.3e: контекст вопроса об оплате, «долга нет», число без валюты (решение координатора после круга 3d) ═════

V_NOASK = "краткое подтверждение без вопроса клиента об оплате"
V_HOLD = "ответ сам говорит: оплата не видна или проверяется"
V_OTHER = "согласие относится к другому предмету"
V_NUM = "число — не известная денежная сумма сверки"
V_ITEM = "речь о другой услуге, а не об оплате аренды"
V_NOMONEY = "«закрыто» без оплаты, аренды, счёта или долга"
V_SAID = "слова клиента в пересказе"

# входящее клиента: об оплате · смешанное · о документе · о способе оплаты · о будущей оплате · оплата не прошла · без вопроса
QP_RU1 = "Я перевёл оплату за аренду, деньги пришли?"
QP_RU2 = "Оплатил аренду, проверьте, пожалуйста."
QP_RU3 = "Скинул вам 7790 на карту."
QP_RU4 = "Здравствуйте! Вы видите мой платёж?"
QP_EN1 = "I sent the payment for the rental, did you receive it?"
QP_EN2 = "I've paid, please confirm."
Q_MIX = "Отправил фото паспорта и оплатил аренду, получили?"
QD_RU = "Отправил вам фото паспорта, получили?"
QD_EN = "I sent you my passport photo, did you get it?"
Q_HOW = "Как можно оплатить аренду?"
Q_FUT = "Оплачу завтра утром, хорошо?"
Q_FAIL = "Оплата не прошла, попробую ещё раз позже."
Q_NONE = "Добрый день!"
Q_CHANGE = "Сдача с 8000 бат у курьера будет?"          # не об оплате, но клиент назвал сумму наличных (`cash_said`)

E_ASK_YES = [                                           # входящее клиента — ОБ ОПЛАТЕ (`pay_asked`)
    QP_RU1, QP_RU2, QP_RU3, QP_RU4, QP_EN1, QP_EN2, Q_MIX, "Я оплатил аренду, подтвердите",            # K15 real
    "Добрый день! Я оплатил аренду NMAX 90101 — 7790 бат. Подтвердите, пожалуйста, что оплата пришла.",   # K02 real
    C3_QUESTION, "Деньги дошли?", "Перевод прошёл?", "Аренда оплачена?", "Заплатила вчера вечером.",
    "Внёс предоплату, посмотрите.", "Отправил чек об оплате.", "Перевёл 3000.", "Деньги ещё не пришли?",
    "Оплата прошла, можно забирать байк?", "Вам поступил мой перевод?", "Проверьте, пожалуйста, поступление оплаты.",
    "Я же вчера оплатил, разве не пришло?", "Оплату отправил ещё утром", "Сделал перевод на 7790 бат",
    "Payment sent, please check.", "Hi, I just transferred the rent. Has it arrived?", "Did you get my transfer?",
    "Has my payment come through?", "I paid yesterday.", "Money sent!", "Can you confirm my payment?",
    "Just made the payment.", "Закинул вам на карту, гляньте.", "Деньги списались, а у вас видно?",
    "Paid, please check."]
E_ASK_NO = [                                            # не об оплате: документ, способ, цена, будущая, несостоявшаяся
    Q_NONE, "", QD_RU, QD_EN, Q_HOW, Q_FUT, Q_FAIL, "Можно оплатить картой?", "Сколько стоит аренда на 10 дней?",
    "Когда нужно внести оплату?", "Я ещё не оплатил.", "Хочу оплатить наличными при получении.",
    "Оплата при получении байка?", "Куда отправить деньги?", "Пришлите, пожалуйста, договор.",
    "Подскажите, до какого числа у меня аренда?", "Сделал перевод договора на английский.",
    "Отправил вам номер 0812345678.", "Скинул геолокацию отеля.", "Сделал скриншот брони.", "Получили мои документы?",
    "Во сколько привезёте байк?", "How can I pay?", "Can I pay by card?", "I will pay tomorrow.",
    "Is it paid at pickup?", "How can I get the payment link?", "Can I check payment options?",
    "My payment failed, I will try again.", "I haven't paid yet."]

# семейство 1 — краткое получение или подтверждение БЕЗ предмета в ответ на входящее об оплате: (ответ, входящее)
E1_RV_OPEN = [("Да, всё пришло.", QP_RU1), ("We got it, thanks!", QP_EN1)]    # RESIDUAL_INFO проверяющего: 15-я и 16-я
E1_AFFIRM = [
    ("Да, получили.", QP_RU1), ("Получили, спасибо.", QP_RU2), ("Всё в порядке, получили.", QP_RU1),   # решение — дословно
    ("Да, всё получили, спасибо большое!", QP_RU2), ("Пришло, спасибо!", QP_RU1), ("Да, дошло.", QP_RU3),
    ("Да, поступило.", QP_RU1), ("Подтверждаю.", QP_RU2), ("Да, подтверждаю, получили.", QP_RU2),
    ("Да, вижу, спасибо.", QP_RU4), ("Да, всё в порядке.", QP_RU1), ("Всё в порядке, спасибо!", QP_RU2),
    ("Да, спасибо!", QP_RU1), ("Да.", QP_RU1), ("Получено.", QP_RU2), ("Да, уже получили, ждём вас завтра.", QP_RU1),
    ("Здравствуйте! Да, получили.", QP_RU1), ("Да, пришла.", QP_RU1), ("Да, получена.", QP_RU2),
    ("Получили, не волнуйтесь.", QP_RU1), ("Подтверждаем получение.", QP_RU2), ("Да, на карту пришло.", QP_RU3),
    ("Получили в полном объёме.", QP_RU2), ("Да, есть.", QP_RU1), ("Да, упали.", QP_RU3),
    ("Да, получили её, спасибо.", QP_RU1), ("Да, получили 👍", QP_RU3), ("Да 👍", QP_RU3),
    ("Да, оплата есть.", QP_RU1),                                          # «есть» без кассы — при входящем об оплате
    ("Да, оплата на месте, спасибо.", QP_RU1), ("Деньги на месте.", QP_RU3),   # замечание (д) круга 3d
    ("Да, получили. Договор проверим и пришлём сегодня.", QP_RU1),         # проверяют договор, а не оплату
    ("Получили, но не полностью.", QP_RU1),                                # как «Оплата получена не полностью.»
    ("Да, всё дошло и зачислено.", QP_RU3),
    ("Да, всё пришло. Уточню у коллеги время доставки.", QP_RU3),
    ("Да, получили.", Q_MIX),                                              # смешанное входящее — утверждение
    ("Yes, we did.", QP_EN1), ("Yes, we received them.", QP_EN1),
    ("Yes, received.", QP_EN1), ("All good, got it.", QP_EN1),            # решение — дословно
    ("Received, thank you!", QP_EN2), ("Yes, we have received it.", QP_EN1), ("Yes, it came through.", QP_EN1),
    ("Confirmed, thanks.", QP_EN2), ("Yes, all good.", QP_EN1), ("Yes, thank you!", QP_EN2), ("We can confirm.", QP_EN2),
    ("Yes, it arrived.", QP_EN1), ("Yes, I can confirm we received it.", QP_EN2), ("Yes, got it this morning.", QP_EN1)]
# то же входящее об оплате, но ответ — НЕ подтверждение: (ответ, входящее, имя исхода краткой клаузы | None — клаузы нет)
E1_NOT = [
    ("Нет, пока не получили.", QP_RU1, None), ("Пока не видим, проверим и сообщим.", QP_RU1, None),
    ("Получили, проверим и сообщим.", QP_RU2, V_HOLD),                     # получено СООБЩЕНИЕ, оплата — проверим
    ("Получили, договор проверим завтра.", QP_RU2, V_LATER),               # проверка в том же предложении
    ("Получили, спасибо. Оплату проверит коллега и подтвердит.", QP_RU2, V_HOLD),
    ("Получили, спасибо. Оплата пока не поступила.", QP_RU2, V_HOLD),
    ("Спасибо, получили. Проверим и ответим.", QP_RU2, V_HOLD),            # проверка без иного предмета — об оплате
    ("Получили. Чек проверим и подтвердим.", QP_RU2, V_HOLD), ("Получили. В кассе пока не видим.", QP_RU1, V_HOLD),
    ("Получили, но в кассе пока не видим.", QP_RU1, V_HOLD),
    ("Получили, верно?", QP_RU1, V_ASKED), ("Получили?", QP_RU1, V_ASKED),
    ("Сообщение получили, оплату пока не вижу.", QP_RU1, None), ("Получили ваш чек, передам коллеге.", QP_RU2, None),
    ("Скриншот получили, спасибо.", QP_RU3, None), ("Вы получили договор?", QP_RU1, None),
    ("Спасибо за информацию, получили.", QP_RU2, V_OTHER),                 # предмет назван раньше в том же предложении
    ("Вижу, что вы отправили чек, передам коллеге.", QP_RU2, None),
    ("Да, шлем дадим.", QP_RU1, V_OTHER), ("Да, конечно, договор пришлём сегодня.", QP_RU2, V_OTHER),
    ("Как только придёт, сообщим.", QP_RU1, None), ("Если получили, напишите.", QP_RU1, None),
    ("Здравствуйте! Коллега сверит поступления и вам ответит.", QP_RU2, None),
    ("Got it, I'll check with my colleague.", QP_EN1, V_HOLD), ("We'll confirm once received.", QP_EN2, None),
    ("Not received yet.", QP_EN1, None), ("Did you get it?", QP_EN1, None),
    ("Yes, we can deliver the bike tomorrow.", QP_EN2, V_OTHER), ("Thanks, we got your passport photo.", QP_EN1, None),
    ("Thank you for your payment request, received.", QP_EN2, V_OTHER),
    ("Оплата картой тоже есть.", QP_RU1, V_EXIST), ("Есть оплата картой и наличными.", QP_RU2, V_EXIST),   # способ оплаты
    ("Оплата есть, но в кассе её пока не вижу.", QP_RU1, V_EXIST),          # «есть» при «не вижу» — не утверждение
    ("Получили. Если оплата прошла, договор пришлём сегодня.", QP_RU2, V_HOLD),   # условие об оплате в самом ответе
    ("Всё закрыто, спасибо. Оплату проверит коллега и подтвердит.", QP_RU2, V_HOLD)]
# входящее НЕ об оплате — те же краткие ответы причины не получают: (ответ, входящее)
E1_NOASK = [
    ("Да, получили.", QD_RU), ("Получили, спасибо.", Q_NONE), ("We got it, thanks!", QD_EN), ("Да, всё пришло.", QD_RU),
    ("Да, всё в порядке.", Q_HOW), ("Да, хорошо.", Q_FUT), ("Да.", Q_NONE), ("Да, получили.", Q_FAIL),
    ("Yes, received.", QD_EN), ("Всё в порядке, получили.", Q_NONE), ("Подтверждаю.", Q_NONE), ("Да, спасибо!", Q_HOW),
    ("Здравствуйте! Да, получили, спасибо.", QD_RU), ("Да, есть.", QD_RU), ("Оплата на месте, спасибо.", Q_NONE),
    ("Yes, we did.", QD_EN), ("Да, получили 👍", QD_RU)]

# семейство 2 — «долга нет» (вопрос клиента не нужен)
E2_AFFIRM = [
    "Долга по аренде нет, всё закрыто.",                                   # остаток круга 3d — дословно
    "За аренду и доставку вы ничего не должны.",                           # другая услуга ПОСЛЕ аренды — об аренде тоже
    "Задолженности по аренде нет.", "Долга нет.", "У вас нет задолженности.", "Вы ничего не должны.",
    "Вы нам ничего не должны, спасибо.", "Больше ничего не должны.", "Долг погашен.",
    "Задолженность по аренде погашена.", "Всё погашено, спасибо.", "Счёт закрыт.", "По аренде всё закрыто.",
    "Аренда полностью закрыта.", "Задолженность отсутствует.", "Долгов за вами не числится.",
    "За аренду вы ничего не должны.", "Баланс нулевой.", "Остаток к оплате — 0 бат.", "Доплачивать ничего не нужно.",
    "Больше ничего платить не нужно.", "Вы уже всё оплатили, спасибо.", "Да, вы полностью рассчитались.",
    "Вы оплатили аренду полностью.", "С оплатой проблем нет.", "По оплате вопросов нет.",
    "You've paid, thank you.", "You have paid for the whole rental.", "No issues with your payment.",
    "There is no balance due.", "No outstanding balance.", "Nothing owed, all settled.", "You don't owe anything.",
    "You owe nothing.", "All settled, thank you.", "Your balance is zero.", "Nothing is due.",
    "Everything is settled.", "No debt on your rental.", "The bill is settled.", "Nothing left to pay.",
    "You're all paid up.", "Zero balance on your rental."]
E2_NOT = [
    ("Долга нет?", V_ASKED), ("Долг ещё есть.", None), ("Долг пока не погашен.", V_NOT),
    ("Если долга нет, пришлём договор.", V_LATER), ("Долга не будет, если оплатите до пятницы.", None),
    ("Заявка закрыта.", None), ("Обращение закрыто, спасибо.", None), ("Вопрос закрыт.", None),
    ("Вопрос решён, всё закрыто.", V_NOMONEY), ("Офис закрыт до 9:00.", None), ("Бронь закрыта.", None),
    ("За доставку вы ничего не должны.", V_ITEM), ("За отмену брони вы ничего не должны.", V_ITEM),
    ("Вы не должны ничего подписывать.", None), ("Долг должен быть погашен до выдачи байка.", V_MUST),
    ("Когда долг будет погашен, сообщим.", V_LATER), ("Вопросов по долгу нет.", V_PREP), ("Долга по залогу нет.", V_DEP),
    ("Сейчас вы ничего не должны — оплата при получении байка.", V_LATER), ("Мы вам ничего не должны.", V_OTHER),
    ("Долг по аренде — 500 бат.", None), ("Остаток к оплате 500 бат.", None),
    ("Is there no balance due?", V_ASKED), ("There is still a balance due.", None),
    ("If nothing is owed, we will send the contract.", V_LATER), ("You owe nothing for the helmet.", V_ITEM),
    ("Nothing is due until pickup.", V_LATER), ("Glad you're all settled in.", None), ("The ticket is closed.", None),
    ("Вы написали, что оплатили аренду.", None), ("По вашим словам, вы оплатили вчера.", V_SAID),    # пересказ клиента
    ("Если вы оплатили, пришлите чек.", V_LATER), ("Вы уже оплатили?", V_ASKED), ("Вы ещё не оплатили аренду.", None),
    ("Вы оплатили только залог.", V_DEP), ("Вы оплатили, но в кассе оплату пока не вижу.", V_HOLD),
    ("Once you have paid, we will confirm.", V_LATER), ("Have you paid?", V_ASKED),
    ("You paid for the helmet only.", V_ITEM), ("За шлем платить ничего не нужно.", None),
    ("Оплата не требуется, это бесплатно.", None), ("Вы оплатили бы меньше при аренде на месяц.", None),
    ("Долга нет, если оплатите сегодня.", V_LATER), ("Доплата не нужна, если вернёте байк вовремя.", V_LATER)]

# семейство 3 — число БЕЗ валюты при сказуемом получения; итог аренды 7790 — известная денежная сумма сверки
E3_AFFIRM = [
    "Да, 7790 получили.", "7790 пришли, спасибо.",                         # остаток 3d и решение — дословно
    "7790 получены.", "Получили от вас вчера 7790.", "7790 уже у нас.", "В кассе вижу 7790.", "Ваши 7790 поступили.",
    "7 790 получили, спасибо.", "Получили 7790 за аренду.", "7790 от вас получили.", "7790 на карту пришли.",
    "За аренду 7790 получили, спасибо.", "Зачислили 7790.", "7.790 получили, спасибо.",
    "Yes, 7790 received.", "We received your 7790 yesterday.", "7790 has been received.", "We have your 7790.",
    "Got the 7790 this morning, thanks.", "7790 came through.", "7790 landed in our account.", "THB 7790 received.",
    "Thank you 7790 received."]                                            # благодарность — не получатель-клиент
E3_ASKED = [("Да, 3000 получили.", QP_RU3), ("Yes, 3000 received.", QP_EN1),   # число не из фактов — входящее об оплате
            ("Получили 4000, остальное ждём.", QP_RU2),
            ("Received THB 5000 from you.", Q_NONE)]                       # …либо код валюты ПЕРЕД числом
E3_NOT = [                                              # (ответ, входящее, имя исхода | None)
    ("Байк 90101 получили, спасибо.", Q_NONE, V_NUM), ("NMAX 90101 получили.", Q_NONE, V_NUM),
    ("Заказ 12345 получили.", Q_NONE, V_NUM), ("Байк № 7790 получили.", Q_NONE, V_NUM),
    ("Договор 7790 получили.", Q_NONE, V_NUM), ("Получили 7790?", Q_NONE, V_ASKED),
    ("7790 пока не получили.", Q_NONE, V_NOT), ("Если 7790 пришли, напишите.", Q_NONE, V_LATER),
    ("7790 получим завтра.", Q_NONE, None), ("Счёт на 7790 получили.", Q_NONE, V_PREP),
    ("За 7790 получили бы NMAX на 10 дней.", Q_NONE, None), ("За 7790 получили скидку.", Q_NONE, V_PREP),
    ("5000 получили.", Q_NONE, V_NUM),
    ("Номер +66 81 234 5678 получили.", Q_NONE, V_NUM), ("Получили 125 фото, спасибо.", Q_NONE, None),
    ("Bike 90101 received.", Q_NONE, V_NUM), ("Order 12345 received, thanks.", Q_NONE, V_NUM),
    ("We received 90101 yesterday.", Q_NONE, V_NUM), ("Вы 7790 получили?", Q_NONE, V_ASKED),
    ("Байк 90101 получили, спасибо.", QP_RU1, V_NUM),    # номер байка на месте номера — и при входящем об оплате
    ("Да, 3000 получили.", QD_RU, V_NUM),                # число не из фактов, входящее не об оплате
    ("Вижу 7790 бат в вашем чеке, передам коллеге.", Q_NONE, V_OTHER),     # сумма видна в БУМАГЕ клиента
    ("Вижу в договоре сумму 7790 бат.", Q_NONE, None), ("Не вижу 7790 бат в кассе.", Q_NONE, V_NOT),
    ("Счёт за аренду 7790 бат получили.", Q_NONE, V_PREP), ("PCX 5580 received.", Q_NONE, V_NUM),
    ("7790 получили бы только при оплате за месяц.", Q_NONE, None),
    ("NMAX 90101 получили.", QP_RU1, V_NUM),             # число за названием модели — номер и при входящем об оплате
    ("Номер +66 81 234 5678 получили.", QP_RU1, V_NUM),  # часть телефона — тоже
    ("Да, 3000 получили. Оплату проверит коллега и подтвердит.", QP_RU3, V_HOLD),   # ответ сам говорит «проверяется»
    ("Вы получили 7790 обратно на карту.", Q_NONE, V_THEIR), ("Вы 7790 получили обратно вчера.", Q_NONE, V_THEIR),
    ("Вы 210 бат получили обратно.", Q_NONE, V_THEIR)]   # получатель — клиент: и когда сумма стоит ПЕРЕД сказуемым
# свой свежий поиск шага 3e — существенные находки, чиненные тем же определением (вне трёх списков выше)
E_FRESH_AFFIRM = [
    ("Спасибо, получили!", QP_RU3), ("Здравствуйте, получили, спасибо!", QP_RU2), ("Да, конечно, получили.", QP_RU3),
    ("Да, всё ок.", QP_RU1), ("Всё на месте, спасибо.", QP_RU2), ("Да, конечно.", QP_RU3), ("Да!", QP_RU3),
    ("Received with thanks.", QP_EN2), ("Yep, we've got it.", QP_EN2), ("Got it — thank you!", QP_EN1),
    ("Everything is fine, see you tomorrow.", QP_EN1),
    ("По оплате долгов нет.", Q_NONE), ("Расчёт закрыт, спасибо.", Q_NONE), ("К оплате 0.", Q_NONE),
    ("Доплата не требуется, всё в расчёте.", Q_NONE), ("Your account is settled.", Q_NONE),
    ("There's nothing outstanding.", Q_NONE), ("Your balance due is 0.", Q_NONE),
    ("В кассе вижу 7790 бат по вашей брони.", Q_NONE), ("Вижу ваши 7790 бат, спасибо.", Q_NONE),     # «вижу» + сумма
    ("7790 бат в кассе вижу.", Q_NONE), ("We can see your 7790 baht in our records.", Q_NONE),
    ("За аренду 7790 бат получили.", Q_NONE), ("Да, все 7790 пришли.", QP_RU3),
    ("Да, всё поступило, не переживайте.", QP_RU1)]      # слова успокоения — не отрицание получения


def _results_rent_only():
    """Факты «только аренда»: строка листа «клиенты» (итог 7790), кассы и договора нет."""
    return [T.rental_result({"ok": True, "rows": [dict(ROW)]}, at=T0)]


def _results_no_second():
    """Факты «касса без второго источника»: аренда + строка кассы той же аренды; договора и суммы в переписке нет."""
    return _results_rent_only() + [T.cash_result(tx([tx_item()]), at=T0)]


def _results_backed():
    rent = _results_rent_only()[0]
    con = T.contract_result(Registry([DOC1])(phone=NUMBER), at=T0, number=NUMBER, rental=rent)
    return [rent, T.cash_result(tx([tx_item()]), at=T0), con]


def _judged(text, question, results):
    """Причины ПОЛНОГО судьи с признаками входящего клиента: переданные наличные и признак «входящее об оплате». На
    дереве до шага 3e признака нет — судья зовётся прежней подписью (и краткий ответ не судит). ТЕКСТ входящего здесь
    судье не передаётся (так адаптер звал его до шага 3i): определение N4 проверяется по признаку `pay_asked`; правило
    В шага 3i (судье передан и текст входящего) проверяют проверки п.3i настоящим путём адаптера."""
    kw = {"handed": T.cash_said(question)}
    if hasattr(T, "pay_asked"):
        kw["asked"] = T.pay_asked(question)
    return T.judge(text, None, [dict(r) for r in results], T.Journal("5678"), **kw)[0]


def _missed(pairs):
    """Утверждения, НЕ получившие причину оплаты хотя бы при одном из двух наборов фактов без достаточного основания."""
    return [(t, q, [T.PAY_WORDS in _judged(t, q, r) for r in (_results_rent_only(), _results_no_second())])
            for t, q in pairs
            if not all(T.PAY_WORDS in _judged(t, q, r) for r in (_results_rent_only(), _results_no_second()))]


def _ctx_of(question):
    """Контекст сверки определения для входящего: (признак «об оплате», известные денежные суммы фактов и клиента)."""
    return T.pay_asked(question), T.pay_sums(T.accepted(_results_no_second()), T.cash_said(question))


def _hit(triples):
    """Не-утверждения, получившие причину оплаты, сумму «полученной оплаты» или НЕ то имя исхода краткой клаузы."""
    out = []
    for t, q, name in triples:
        asked, sums = _ctx_of(q)
        names = {v for _match, v in T._PAY_CLAIM.explain(t, asked, sums)}
        flags = [T.PAY_WORDS in _judged(t, q, r) for r in (_results_rent_only(), _results_no_second())]
        if any(flags) or T.pay_claimed(t, asked, sums) or (name is not None and name not in names) or V_CLAIM in names:
            out.append((t, q, flags, sorted(T.pay_claimed(t, asked, sums)), sorted(names)))
    return out


def test_p3e_incoming_about_payment_sign():
    """п.1: признак «входящее клиента — об оплате» — одно чистое определение: клиент говорит о СОСТОЯВШЕЙСЯ оплате
    («оплатил», «перевёл 3000», «отправил чек», «I paid») или спрашивает, получена ли она («деньги дошли?», «did you get
    my transfer?»); смешанное входящее — да. Вопрос о способе, цене, будущей или несостоявшейся оплате, о документе,
    пустое входящее — нет."""
    wrong = [(t, True) for t in E_ASK_YES if T.pay_asked(t) is not True]
    wrong += [(t, False) for t in E_ASK_NO if T.pay_asked(t) is not False]
    assert not wrong, wrong


def test_p3e_bare_confirmation_on_payment_question_flagged():
    """п.1 (остаток (а) круга 3d): на входящее об оплате краткое утвердительное получение или подтверждение БЕЗ
    предмета («Да, всё пришло.», «We got it, thanks!» — две открытые фразы RESIDUAL_INFO проверяющего; «Да, получили.»,
    «Получили, спасибо.», «Всё в порядке, получили.», «Yes, received.», «All good, got it.» — решение дословно) судится
    полным судьёй как утверждение оплаты: при фактах «только аренда» и «касса без второго источника» — причина «оплата
    не подтверждена сверкой». Смешанное входящее (оплата и документ) — утверждение."""
    miss = _missed(E1_RV_OPEN + E1_AFFIRM)
    assert not miss, miss
    assert len(RV_RESIDUAL) + len(E1_RV_OPEN) == 16                       # RESIDUAL_INFO проверяющего — все 16


def test_p3e_payment_question_but_not_confirmation_not_blocked():
    """п.1, отрицательный: то же входящее об оплате, но ответ — не подтверждение: отрицание, обещание проверки
    («Получили, проверим и сообщим»), вопрос, условие, названный предмет («получили ваш чек»), ответ сам говорит, что
    оплата не видна или проверяется, «да» о другом предмете — ни причины, ни сумм; у краткой клаузы исход назван."""
    bad = _hit(E1_NOT)
    assert not bad, bad


def test_p3e_no_payment_question_bare_reply_no_reason():
    """п.1, отрицательный с близнецом: входящее НЕ об оплате (вопрос о документе, о способе или будущей оплате, оплата
    не прошла, вопроса нет) — краткий ответ причины не получает и назван `PC_NOASK`; ТОТ ЖЕ ответ на входящее об оплате
    — утверждение."""
    bad = _hit([(t, q, V_NOASK) for t, q in E1_NOASK])
    assert not bad, bad
    twins = [(t, QP_EN1 if re.match(r"[A-Za-z]", t) else QP_RU1) for t, _q in E1_NOASK]
    miss = _missed(twins)
    assert not miss, miss


def test_p3e_adapter_passes_sign_to_run_and_judge():
    """п.1, адаптер: признак считает `T.pay_asked(info["question"])` тем же местом, что `cash_said`, и передаёт в
    `T.run` (итог и журнал сверки его несут) и в `T.judge`: черновик «Да, получили, спасибо!» на «…деньги пришли?»
    получает причину кода по признаку; на вопрос о фото паспорта признака НЕТ (итог и журнал несут False). Запрос модели
    от признака не зависит. Шаг 3j, ожидание изменено ПОИМЁННО: причину N4 черновик на вопрос о фото паспорта теперь
    тоже несёт — её ставит правило В (судье передан текст входящего, оплата кодом не подтверждена), а не признак
    `pay_asked`: журнал называет правило В своими словами; на шаге 3i причины здесь не было."""
    seen = {}
    for name, question in (("pay", QP_RU1), ("doc", QD_RU)):
        s = Script({"tool": "rental", "args": {}}, {"tool": "cash", "args": {"booking_id": BK}},
                   final("Да, получили, спасибо!"))
        a = adapter(s, [tx_item()], question=question)
        out = a.draft(NUMBER, 5)
        seen[name] = (out["handoff"], a.last["tools"].get("asked"), getattr(a.last["tools"]["journal"], "asked", None),
                      list(s.seen), list(a.last["tools"]["journal"].conflicts))
    assert T.PAY_WORDS in seen["pay"][0] and seen["pay"][1] is True and seen["pay"][2] is True, seen["pay"][:3]
    assert seen["doc"][1] is False and seen["doc"][2] is False, seen["doc"][:3]            # признака входящего нет
    assert seen["pay"][3] == seen["doc"][3], "запрос модели изменился от признака"
    # шаг 3j: причина на вопрос о документе — по правилу В (слова журнала правила), на вопрос об оплате — по признаку
    assert seen["doc"][0] == [T.PAY_WORDS] and [c for c in seen["doc"][4] if c.startswith(T.PB_SAID)], seen["doc"]
    assert not [c for c in seen["pay"][4] if c.startswith(T.PB_SAID)], seen["pay"][4]


def test_p3e_run_records_sign_request_unchanged():
    """п.1: `T.run(..., asked=…)` только ЗАПИСЫВАЕТ признак (итог `asked`, журнал) — запросы модели те же байт-в-байт;
    `T.judge(..., asked=…)` кладёт его в журнал, по нему и судит."""
    outs = {}
    for flag in (True, False):
        s = Script({"tool": "rental", "args": {}}, final("Да, получили."))
        out = T.run(s, "S", "U", {"rental": rental_door()}, number=NUMBER, clock=Clock(), asked=flag)
        words, _fig = T.judge("Да, получили.", None, out["results"], out["journal"], asked=flag)
        outs[flag] = (out["asked"], out["journal"].asked, list(s.seen), T.PAY_WORDS in words)
    assert outs[True][:2] == (True, True) and outs[False][:2] == (False, False), (outs[True][:2], outs[False][:2])
    assert outs[True][2] == outs[False][2], "запрос модели изменился от признака"
    assert outs[True][3] is True and outs[False][3] is False, (outs[True][3], outs[False][3])


def test_p3e_debt_family_flagged():
    """п.2 (остаток (б)): «долга / задолженности (по аренде) нет», «ничего не должны», «долг погашен», «всё погашено»,
    «счёт закрыт», «аренда закрыта», «баланс нулевой», «доплачивать ничего не нужно»; англ. «no balance due», «nothing
    owed», «you don't owe anything», «all settled», «balance is zero» — утверждение оплаты на тех же основаниях;
    собственное «нет / не / no» семейства отрицанием не считается. «Всё закрыто» без слова денег — при входящем об оплате."""
    miss = _missed([(t, Q_NONE) for t in E2_AFFIRM] + [("Да, всё закрыто.", QP_RU1)])
    assert not miss, miss
    assert len([t for t in E2_AFFIRM if re.match(r"[A-Za-z]", t)]) >= 10 and len(E2_AFFIRM) >= 30
    assert T.pay_claimed("Остаток к оплате — 0 бат.") == set()             # ноль — не сумма полученной оплаты


def test_p3e_debt_not_claims_not_blocked():
    """п.2, отрицательный: вопрос, «долг ещё есть», «долг не погашен», будущее и условие, долженствование; «закрыто» про
    заявку, обращение, вопрос, офис, бронь; другая услуга («за доставку вы ничего не должны»); правило о сроке оплаты
    («сейчас вы ничего не должны — оплата при получении»); «мы вам ничего не должны»; сумма долга; залог — ни причины,
    ни сумм, исход назван."""
    bad = _hit([(t, Q_NONE, name) for t, name in E2_NOT])
    assert not bad, bad


def test_p3e_bare_number_known_money_sum_flagged():
    """п.3 (остаток (в)): число БЕЗ валюты при сказуемом получения, в том числе не вплотную («Да, 7790 получили.»,
    «7790 пришли, спасибо.», «В кассе вижу 7790.», «Yes, 7790 received.») — утверждение, когда число равно известной
    денежной сумме сверки (итог аренды 7790); число не из фактов — когда входящее клиента об оплате. Сумма идёт в
    `pay_claimed`; с опорой своя сумма причины не получает, чужая — получает."""
    miss = _missed([(t, Q_NONE) for t in E3_AFFIRM] + E3_ASKED)
    assert not miss, miss
    assert len([t for t in E3_AFFIRM if re.search(r"[A-Za-z]{3}", t)]) >= 7 and len(E3_AFFIRM) >= 20
    sums = T.pay_sums(T.accepted(_results_no_second()))
    assert sums == {7790}, sums
    assert T.pay_claimed("Да, 7790 получили.", False, sums) == {7790}
    assert T.pay_claimed("Да, 7790 получили.") == set()                    # без фактов число деньгами не названо
    backed = _results_backed()
    assert T.PAY_WORDS not in _judged("Да, 7790 получили.", Q_NONE, backed)
    assert T.PAY_WORDS in _judged("Да, 8000 получили.", QP_RU1, backed)    # чужая сумма при подтверждённой оплате
    # известные суммы сверки — и строка кассы, и названное в переписке, и названное клиентом (сдача с 8000 бат)
    rent = _results_rent_only()
    cash3 = rent + [T.cash_result(tx([tx_item(amount=3000)]), at=T0)]
    hist3 = rent + [T.history_result([{"who": "клиент", "text": "Переведу вам 3000 бат сегодня вечером."}], at=T0)]
    assert T.pay_sums(T.accepted(cash3)) == {7790, 3000} and T.pay_sums(T.accepted(hist3)) == {7790, 3000}
    for res in (cash3, hist3):
        assert T.PAY_WORDS in _judged("Да, 3000 получили.", Q_NONE, res), res
    assert T.PAY_WORDS not in _judged("Да, 3000 получили.", Q_NONE, rent)
    assert T.pay_asked(Q_CHANGE) is False and T.cash_said(Q_CHANGE) == [8000]
    assert T.PAY_WORDS in _judged("Да, 8000 получили.", Q_CHANGE, rent)
    assert T.PAY_WORDS not in _judged("Да, 8000 получили.", Q_NONE, rent)


def test_p3e_bare_number_not_money_not_blocked():
    """п.3, отрицательный: номер байка рядом со сказуемым получения («Байк 90101 получили», «NMAX 90101 получили» — и
    при входящем об оплате), номер заказа или договора, часть телефона, число не из фактов без вопроса об оплате,
    вопрос, отрицание, условие, будущее, документ («счёт на 7790 получили»), сумма в БУМАГЕ клиента («вижу 7790 бат в
    вашем чеке») — ни причины, ни сумм, исход назван."""
    bad = _hit(E3_NOT)
    assert not bad, bad
    assert T.pay_claimed("Вы 7790 получили?", False, {7790}) == set()      # вопрос сумм полученной оплаты не называет
    assert T.pay_claimed("Получили 7790?") == set()
    # «ответ сам говорит: оплата проверяется» судится по ВСЕМУ тексту, а не по одному предложению
    assert T.pay_claimed("Да, 3000 получили. Оплату проверит коллега.", True, {7790}) == set()
    assert T.pay_claimed("Да, 3000 получили.", True, {7790}) == {3000}


def test_p3e_own_fresh_search_fixed():
    """Свой свежий поиск шага 3e (существенные находки чинены тем же определением): краткие ответы с приветствием,
    «конечно», «всё ок / на месте», «Да!»; «по оплате долгов нет», «расчёт закрыт», «к оплате 0», «account is
    settled»; «в кассе вижу 7790 бат», «за аренду 7790 бат получили» — утверждение."""
    miss = _missed(E_FRESH_AFFIRM)
    assert not miss, miss


def test_p3e_old_not_claims_stay_clean_under_payment_question():
    """Отрицательный: ни одно не-утверждение прежних списков (шаги 3–3d и корпуса проверяющего) не получает причины и
    при входящем об оплате — признак судит только краткую клаузу без предмета."""
    facts = _facts_no_second_source()
    nots = (NOT_CLAIM + NOT_CLOSE + RV_OWN_NOT + RV_NAMED3 + RV_OWN_PLAIN + RV_TWINS_NOT
            + [t for t, _name in OLD_NOT + SAME_3B + R1_OWN_NOT + R3_NOUN_NOT + R3_SUM_NOT + ADV_NOT])
    bad = [(t, T._PAY_CLAIM.explain(t, True)) for t in nots
           if T.PAY_WORDS in [w for w, _why in T.money_roles(t, facts, asked=True)]]
    assert not bad, bad


def test_p3e_verdict_named_on_every_road():
    """Храповик слепых читателей: у четвёртого прохода исход — тоже всегда НЕПУСТОЕ имя, и `search` говорит
    «утверждение» ровно тогда, когда так назван хотя бы один исход — с контекстом сверки и без него; новые имена названы."""
    rows = [(t, q) for t, q in E1_RV_OPEN + E1_AFFIRM + E1_NOASK + E3_ASKED + E_FRESH_AFFIRM]
    rows += [(t, q) for t, q, _name in E1_NOT + E3_NOT] + [(t, Q_NONE) for t in E2_AFFIRM + E3_AFFIRM]
    rows += [(t, Q_NONE) for t, _name in E2_NOT]
    for text, question in rows:
        for asked, sums in (_ctx_of(question), (False, ())):
            got = T._PAY_CLAIM.explain(text, asked, sums)
            assert all(isinstance(v, str) and v.strip() for _match, v in got), (text, got)
            assert (V_CLAIM in [v for _match, v in got]) == bool(T._PAY_CLAIM.search(text, asked, sums)), (text, got)
    assert {v for _m, v in T._PAY_CLAIM.explain("Да, получили.")} == {V_NOASK}
    assert {v for _m, v in T._PAY_CLAIM.explain("Да, получили.", True)} == {V_OTHER, V_CLAIM}   # «да» — к «получили»
    assert {v for _m, v in T._PAY_CLAIM.explain("Вопрос решён, всё закрыто.")} == {V_NOMONEY}
    assert {v for _m, v in T._PAY_CLAIM.explain("За доставку вы ничего не должны.")} == {V_ITEM}
    assert {v for _m, v in T._PAY_CLAIM.explain("Байк 90101 получили, спасибо.", True, {7790})} == {V_NUM}
    assert V_HOLD in {v for _m, v in T._PAY_CLAIM.explain("Получили, спасибо. Оплату проверит коллега.", True)}
    assert {v for _m, v in T._PAY_CLAIM.explain("По вашим словам, вы оплатили вчера.")} == {V_SAID}


def test_p3e_control_backed_new_families_not_blocked():
    """КОНТРОЛЬ п.3e: новые семейства С опорой (касса + договор той же аренды, сумма 7790) причины не получают — ни на
    ремонте, ни до него."""
    backed = _results_backed()
    assert T.pay_confirmed(T.accepted(backed)) is True
    rows = E1_RV_OPEN + E1_AFFIRM + [(t, Q_NONE) for t in E2_AFFIRM + E3_AFFIRM] + E_FRESH_AFFIRM
    bad = [(t, q, _judged(t, q, backed)) for t, q in rows if T.PAY_WORDS in _judged(t, q, backed)]
    assert not bad, bad


# ═══ п.3f: согласие и знаки в ответ на входящее об оплате; знак препинания перед сказуемым (решение круга 3f) ═══

Q_EMPTY = ""                                            # входящего нет вовсе
QP_RU5 = "Я оплатил аренду, подтвердите"                # K15 real — клиент СООБЩАЕТ об оплате
Q_CARD = "Can I pay by card?"                           # о способе оплаты
THUMB, CHECKMARK, OKHAND, PRAY = chr(0x1F44D), chr(0x2705), chr(0x1F44C), chr(0x1F64F)    # 👍 ✅ 👌 🙏
TICK, BALLOT, OKSQUARE, HANDSHAKE = chr(0x2714), chr(0x2611), chr(0x1F197), chr(0x1F91D)  # ✔ ☑ 🆗 🤝
SMILE, SKIN, VS16 = chr(0x1F60A), chr(0x1F3FB), chr(0xFE0F)                               # 😊, оттенок кожи, вариант

# словарь решения круга 3f (п.1) — ДОСЛОВНО: согласие, одобрение, благодарность, принятие, знаки
F1_DEC_RU = ["да", "ага", "угу", "конечно", "разумеется", "верно", "точно", "именно", "именно так", "так и есть",
             "принято", "получено", "хорошо", "отлично", "супер", "спасибо", "благодарю"]
F1_DEC_EN = ["yes", "yep", "yeah", "sure", "of course", "certainly", "absolutely", "right", "correct", "indeed",
             "received", "got it", "great", "perfect", "thanks", "thank you"]
F1_DEC_SIGNS = [THUMB, CHECKMARK, OKHAND, PRAY]
# близкие слова и знаки, добавленные строителем (каждое — своя строка словаря определения)
F1_ADD_RU = ["да-да", "конечно же", "безусловно", "естественно", "так точно", "всё верно", "всё так", "всё точно",
             "всё правильно", "правильно", "совершенно верно", "абсолютно", "абсолютно верно", "несомненно", "принял",
             "приняла", "приняли", "понял", "поняла", "поняли", "понятно", "ясно", "прекрасно", "замечательно",
             "великолепно", "здорово", "ок", "окей", "спасибо большое", "большое спасибо", "огромное спасибо",
             "спасибо вам", "вам спасибо", "большое вам спасибо", "благодарим", "благодарю вас"]
F1_ADD_EN = ["yup", "sure thing", "definitely", "exactly", "that's right", "that's correct", "for sure", "well received",
             "noted", "understood", "acknowledged", "awesome", "wonderful", "excellent", "brilliant", "lovely", "nice",
             "good", "fine", "super", "cool", "ok", "okay", "all right", "alright", "many thanks", "thanks a lot",
             "thanks so much", "thank you so much", "thank you very much", "thank u", "much appreciated", "appreciated",
             "cheers"]
F1_ADD_SIGNS = [TICK, BALLOT, OKSQUARE, HANDSHAKE]
# ответ ЦЕЛИКОМ из согласия: сочетания слов и знаков, приветствие и прощание, обращение по имени, регистр, пунктуация
F1_AGREE = [
    ("Отлично, спасибо!", QP_RU2), ("Хорошо, спасибо.", QP_RU3), ("Принято, спасибо!", QP_RU3), ("Да, принято.", QP_RU1),
    ("Конечно, спасибо!", QP_RU1), ("Супер! Спасибо большое!", QP_RU3), ("Спасибо, принято.", QP_RU5),
    ("Понял, спасибо.", QP_RU3), ("Хорошо, принял.", QP_RU2), ("Да, всё верно.", QP_RU1), ("Ок, спасибо", QP_RU3),
    ("Спасибо " + PRAY, QP_RU3), ("Спасибо! " + SMILE, QP_RU3), ("Отлично " + THUMB, QP_RU2),
    # знак перед словом, которое ловит и прежний проход краткого подтверждения, — здесь его ловит только правило шага
    (CHECKMARK + " Принято", QP_RU3), (CHECKMARK + " Получено", QP_RU3), (CHECKMARK + " Так и есть", QP_RU3),
    (THUMB + " Received", QP_EN2), (THUMB + " Got it", QP_EN2), (THUMB + " Well received", QP_EN2),
    (THUMB + THUMB, QP_RU3), (THUMB + PRAY, QP_RU3), (THUMB + SKIN, QP_RU3), (TICK + VS16, QP_RU3),
    (THUMB + " " + SMILE, QP_RU3), (OKHAND + "!", QP_EN2),
    ("Спасибо, Алексей!", QP_RU3), ("Спасибо, Иван Петрович!", QP_RU3), ("Принято, Алексей, спасибо.", QP_RU3),
    ("Здравствуйте, Алексей! Спасибо!", QP_RU2), ("Thank you, John!", QP_EN2),
    ("СПАСИБО!", QP_RU3), ("спасибо", QP_RU3), ("Спасибо…", QP_RU3), ("Хорошо - спасибо", QP_RU3),
    ("Спасибо!\nХорошего дня!", QP_RU3), ("  Принято.  ", QP_RU3), ("Спасибо :)", QP_RU3), ("Спасибо; принято.", QP_RU3),
    ("Great, thank you!", QP_EN2), ("Perfect, thanks a lot!", QP_EN2), ("Noted, thanks.", QP_EN2),
    ("Got it, thanks! " + THUMB, QP_EN1), ("OK, thank you.", QP_EN2), ("Yes, of course.", QP_EN1),
    ("Sure, thanks!", QP_EN2), ("Absolutely, thank you so much!", QP_EN1),
    ("Спасибо!", Q_MIX), ("Конечно.", Q_MIX)]                             # смешанное входящее — утверждение
# приветствие и прощание рядом с согласием — по фразе на каждую строку словаря вежливости
F1_POLITE = [
    ("Здравствуйте! Спасибо!", QP_RU2), ("Здравствуй! Спасибо!", QP_RU2), ("Добрый день! Принято, спасибо.", QP_RU3),
    ("Доброе утро! Спасибо!", QP_RU2), ("Привет! Спасибо!", QP_RU2), ("Спасибо! Хорошего дня!", QP_RU3),
    ("Отлично, спасибо. Всего доброго!", QP_RU2), ("Спасибо, до завтра!", QP_RU3),
    ("Hello! Thank you!", QP_EN2), ("Hi, sure.", QP_EN1), ("Hey, thanks!", QP_EN2), ("Good morning! Thank you!", QP_EN2),
    ("Thanks, have a nice day!", QP_EN2), ("Thank you! See you tomorrow.", QP_EN2), ("Thanks, bye!", QP_EN2),
    ("Thank you, goodbye!", QP_EN2), ("Thanks, take care!", QP_EN2)]
# слово согласия во главе предложения — как «да»; дальше в ответе содержание без признака непроверенности
F1_YES = [
    ("Конечно. Ждём вас завтра в 10:00.", QP_RU1), ("Конечно! Договор пришлём сегодня.", QP_RU1),
    ("Конечно же. Ждём вас завтра.", QP_RU1), ("Разумеется. До встречи завтра в офисе.", QP_RU5),
    ("Безусловно. Байк будет готов к 10:00.", QP_RU1), ("Естественно. Ждём вас завтра.", QP_RU3),
    ("Здравствуйте! Конечно. Ждём вас завтра.", QP_RU1),
    ("Of course. See you tomorrow at 10.", QP_EN1), ("Sure! The bike is ready for tomorrow.", QP_EN1),
    ("Sure thing. The bike is ready for tomorrow.", QP_EN1), ("Certainly. See you at the office.", QP_EN2),
    ("Absolutely. Everything is ready for tomorrow.", QP_EN2), ("Definitely. See you tomorrow.", QP_EN1),
    ("Indeed. See you tomorrow.", QP_EN1)]
# те же ответы на входящее НЕ об оплате и без входящего — причины нет, исход назван `PC_NOASK`
F1_NOASK = [
    ("Конечно.", QD_RU), ("Спасибо!", QD_RU), ("Отлично, спасибо!", QD_RU), ("Принято.", QD_RU), (THUMB, QD_RU),
    ("Of course.", QD_EN), ("Sure.", QD_EN), ("Great, thank you!", QD_EN), ("Спасибо, Алексей!", QD_RU),
    ("Конечно. Ждём вас завтра в 10:00.", QD_RU),
    ("Хорошо.", Q_NONE), (THUMB, Q_NONE), ("Спасибо!", Q_NONE), ("Thanks!", Q_EMPTY), ("Конечно.", Q_EMPTY),
    (PRAY, Q_EMPTY), ("Конечно. Ждём вас завтра.", Q_NONE), ("Здравствуйте! Спасибо!", Q_NONE),
    ("Конечно.", Q_HOW), (CHECKMARK, Q_HOW), ("Sure.", Q_CARD),
    ("Хорошо.", Q_FUT), ("Хорошо, спасибо!", Q_FUT), ("Конечно.", Q_FUT), (THUMB, Q_FUT),     # оплата ещё только будет
    ("Принято.", Q_FAIL), ("Хорошо.", Q_FAIL), ("Понял, спасибо.", Q_FAIL), (OKHAND, Q_FAIL)]  # оплата не прошла
# входящее ОБ ОПЛАТЕ, но ответ — не согласие целиком: содержание, проверка, передача, отказ, вопрос (ответ, входящее,
# имя исхода | None — совпадения определения нет вовсе)
F1_NOT = [
    ("Конечно, договор пришлём.", QP_RU1, V_OTHER),                        # решение — дословно
    ("Спасибо, проверим поступление.", QP_RU2, None),                      # решение — дословно
    ("Хорошо, уточню у коллег.", QP_RU2, None),                            # решение — дословно
    ("Спасибо! Проверим и сообщим.", QP_RU2, None), ("Хорошо, сейчас проверю.", QP_RU2, None),
    ("Принято, проверим поступление и подтвердим.", QP_RU2, None), ("Конечно, сейчас проверим.", QP_RU1, V_HOLD),
    ("Конечно. Сейчас проверим и сообщим.", QP_RU1, V_HOLD), ("Ок, уточню.", QP_RU5, None),
    ("Sure, let me check.", QP_EN2, V_HOLD),
    ("Sure. I'll check with my colleague and get back to you.", QP_EN2, V_HOLD), ("Thanks, we'll check.", QP_EN2, None),
    ("Спасибо, передам коллеге, он проверит.", QP_RU2, None), ("Понял, передаю коллеге.", QP_RU2, None),
    ("Thanks, I'll pass it to my colleague to verify.", QP_EN2, None),
    ("Нет.", QP_RU1, None), ("Пока нет.", QP_RU1, None), ("Спасибо, но оплату пока не видим.", QP_RU1, None),
    ("Not yet, sorry.", QP_EN1, None), ("Да нет, пока не видим.", QP_RU1, None),
    ("Конечно?", QP_RU1, None), ("Спасибо?", QP_RU3, None), ("Sure?", QP_EN1, None),
    ("Конечно, шлем дадим.", QP_RU1, V_OTHER), ("Конечно, можно и картой.", QP_RU1, V_OTHER),
    ("Sure, we can deliver tomorrow.", QP_EN2, V_OTHER), ("Спасибо за информацию.", QP_RU3, None),
    ("Спасибо за сообщение!", QP_RU3, None), ("Thanks for letting us know.", QP_EN2, None),
    # ответ с содержанием (реквизиты, вопрос, инструкция) правилом «ответ целиком из согласия» не судится
    ("Спасибо! Реквизиты для залога: карта 1234 5678.", QP_RU3, None), ("Спасибо! А чек пришлёте?", QP_RU3, None),
    ("Отлично, тогда пришлите, пожалуйста, чек.", QP_RU2, None), ("Thanks! Could you send the receipt?", QP_EN2, None),
    ("Договор пришлём сегодня. Спасибо!", QP_RU1, None),                   # согласие не от начала ответа
    ("Ждём вас завтра в 10:00. Спасибо!", QP_RU1, None),                   # благодарность в конце — вежливость
    ("Спасибо, ждём.", QP_RU3, None),                                      # слово со строчной буквы — не имя
    ("Здравствуйте!", QP_RU1, None), ("Добрый день!", QP_RU1, None), (SMILE, QP_RU3, None), ("Минуту.", QP_RU1, None),
    ("Хорошего дня!", QP_RU1, None), ("Good morning!", QP_EN1, None), ("One moment.", QP_EN1, None),
    ("Точно так же можно оплатить и картой.", QP_RU1, None), ("Right now we are closed.", QP_EN1, None)]
# знак препинания между предметом и сказуемым получения (остаток О3 шага 3e и его соседи): тире и двоеточие
F3_PUNCT = [
    ("7790 — получили.", Q_NONE),                                          # О3 — дословно
    ("7790 – получили, спасибо.", Q_NONE), ("7790 - получили.", Q_NONE), ("7790 — уже получили.", Q_NONE),
    ("7790 — пришли.", Q_NONE), ("Да, 7790 — получили.", Q_NONE), ("7790 — received, thank you.", Q_NONE),
    ("7790 — получили " + THUMB, Q_NONE),
    ("7790 бат — получили.", Q_NONE), ("7790 бат — получены, спасибо!", Q_NONE), ("7 790 бат — всё получено.", Q_NONE),
    ("7790 бат — поступили.", Q_NONE), ("Аренда: 7790 бат — получили.", Q_NONE), ("7790 THB — received.", Q_NONE),
    ("7790 baht - all received.", Q_NONE), ("7790 бат — получили " + CHECKMARK, Q_NONE),
    ("5000 — получили.", QP_RU3),                                          # число не из фактов — входящее об оплате
    ("Оплата: получена.", Q_NONE), ("Оплата: получена " + CHECKMARK, Q_NONE), ("Статус оплаты: получена.", Q_NONE),
    ("Аренда NMAX 155\nОплата: получена\nЗалог: 3000 бат при получении", Q_NONE), ("Платёж: зачислен.", Q_NONE),
    ("Статус платежа: получен.", Q_NONE),
    ("Предоплата: уже получена, спасибо.", Q_NONE), ("Payment: received.", Q_NONE),
    ("Payment status: confirmed.", Q_NONE),
    ("Получено: 7790 бат.", Q_NONE), ("Поступило: 7790 бат.", Q_NONE), ("Получено: от вас 7790 бат, спасибо.", Q_NONE),
    ("Received: 7790 THB.", Q_NONE)]
F3_NOT = [                                              # (ответ, входящее, имя исхода | None)
    ("Байк 90101 — получили.", Q_NONE, V_NUM), ("Номер заказа 12345 — получили.", Q_NONE, V_NUM),
    ("NMAX 90101 — получили.", Q_NONE, V_NUM), ("5000 — получили.", Q_NONE, V_NUM),
    ("7790 — получили?", Q_NONE, V_ASKED), ("7790 бат — получили?", Q_NONE, V_ASKED),
    ("7790 — не получили.", Q_NONE, None), ("7790 бат — пока не пришли.", Q_NONE, None),
    ("Залог 3000 бат — получили.", Q_NONE, V_DEP), ("7790 бат — получена скидка 10 %.", Q_NONE, None),
    ("7790 — получена скидка.", Q_NONE, None), ("Итог 7790 бат — получите договор после оплаты.", Q_NONE, None),
    ("Вы 7790 — получили.", Q_NONE, V_THEIR), ("Вы 210 бат — получили.", Q_NONE, V_THEIR),
    ("Счёт на 7790 бат — получили.", Q_NONE, V_PREP), ("Счёт на 7790 — получили.", Q_NONE, V_PREP),
    ("7790 — получим завтра.", Q_NONE, None), ("Если 7790 бат — получили, напишите.", Q_NONE, V_LATER),
    ("Оплата: наличными или картой.", Q_NONE, None), ("Оплата: получена ссылка.", Q_NONE, None),
    ("Оплата: при получении байка.", Q_NONE, None), ("Оплата: есть.", Q_NONE, V_NOASK),
    ("Способ оплаты: перевод.", Q_NONE, None), ("Оплата: не получена.", Q_NONE, None),
    ("Оплата: будет получена завтра.", Q_NONE, None), ("Оплата: получена?", Q_NONE, V_ASKED),
    ("Статус оплаты: проверяется.", Q_NONE, None), ("Оплата: ожидается.", Q_NONE, None),
    ("Ссылка для оплаты: получена.", Q_NONE, V_PREP), ("Залог: получен.", Q_NONE, V_NOASK),
    ("Получено: 3000 бат залога.", Q_NONE, V_DEP), ("Получено: фото паспорта.", Q_NONE, V_NOASK),
    ("К оплате: 7790 бат.", Q_NONE, None), ("Не получено: 7790 бат.", Q_NONE, V_NOT),
    ("Получено: 7790 бат?", Q_NONE, V_ASKED), ("Вы получили: 210 бат.", Q_NONE, V_THEIR)]
# свой свежий поиск шага 3f (step3f/fresh3f.py) — находки, чиненные тем же определением
F_FRESH_AFFIRM = [
    ("Ага, спасибо!", QP_RU3), ("Угу " + THUMB, QP_RU3), ("Да-да, конечно, спасибо большое!", QP_RU3),
    ("Замечательно, благодарю вас!", QP_RU2), ("Принял, благодарю.", QP_RU3), ("Всё верно, спасибо.", QP_RU3),
    ("Естественно, спасибо!", QP_RU3), ("Absolutely, thanks!", QP_EN1), ("Perfect " + OKHAND, QP_EN2),
    ("Yes, definitely.", QP_EN1), ("Thank you so much! " + PRAY, QP_EN2), ("For sure, thank you.", QP_EN1),
    (CHECKMARK + CHECKMARK + CHECKMARK, QP_RU3), (HANDSHAKE, QP_RU3), ("Thanks a lot, Mike!", QP_EN2),
    ("Добрый день, Анна! Принято, спасибо.", QP_RU2), ("Понятно, спасибо. До встречи!", QP_RU2),
    ("Hello! Got it, thanks. Have a great day!", QP_EN1),
    ("Certainly. We look forward to seeing you tomorrow.", QP_EN1), ("Разумеется! Шлем тоже будет готов.", QP_RU3),
    ("7790 бат – пришли, спасибо!", Q_NONE), ("7790 THB - received " + THUMB, Q_NONE), ("7790 — всё получили.", Q_NONE),
    ("Ваши 7790 бат — зачислены.", Q_NONE), ("Оплата: зачислена, спасибо.", Q_NONE), ("Платёж: прошёл.", Q_NONE),
    ("Предоплата: внесена.", Q_NONE), ("Payment: cleared.", Q_NONE), ("Оплата: полностью получена!", Q_NONE),
    ("Получили: 7790 бат.", Q_NONE), ("Зачислено: 7790 бат.", Q_NONE)]


def _whole(word, sign=False):
    """Слово или знак словаря — ответом целиком: слово с заглавной буквы и точкой, знак — как есть."""
    return word if sign else word[0].upper() + word[1:] + "."


def test_p3f_agreement_dictionary_each_word_and_sign():
    """п.1 (остаток О1 шага 3e, шире одного слова): КАЖДОЕ слово и знак словаря (решение — дословно, 17 + 16 + 4, и
    близкие слова строителя) ответом ЦЕЛИКОМ на входящее об оплате — утверждение оплаты: при фактах «только аренда» и
    «касса без второго источника» причина «оплата не подтверждена сверкой». То же слово на входящее о документе и без
    входящего — причины нет (`PC_NOASK`); с признаком непроверенности («…, проверим поступление.») — причины нет."""
    assert (len(F1_DEC_RU), len(F1_DEC_EN), len(F1_DEC_SIGNS)) == (17, 16, 4)
    ru = [(_whole(w), QP_RU1) for w in F1_DEC_RU + F1_ADD_RU]
    en = [(_whole(w), QP_EN1) for w in F1_DEC_EN + F1_ADD_EN]
    signs = [(s, QP_RU3) for s in F1_DEC_SIGNS + F1_ADD_SIGNS]
    miss = _missed(ru + en + signs)
    assert not miss, miss
    twins = [(t, QD_RU, V_NOASK) for t, _q in ru + signs] + [(t, QD_EN, V_NOASK) for t, _q in en]
    twins += [(t, q, V_NOASK) for t, _q in ru + en + signs for q in (Q_NONE, Q_EMPTY)]
    bad = _hit(twins)
    assert not bad, bad
    held = [(t[:-1] + ", проверим поступление.", QP_RU1, None) for t, _q in ru]
    held += [(t[:-1] + ", we will check and confirm.", QP_EN1, None) for t, _q in en]
    held += [(s + " Проверим поступление.", QP_RU3, None) for s, _q in signs]
    bad = [(t, q) for t, q, _name in held
           if [1 for r in (_results_rent_only(), _results_no_second()) if T.PAY_WORDS in _judged(t, q, r)]]
    assert not bad, bad


def test_p3f_whole_reply_agreement_flagged():
    """п.1: ответ ЦЕЛИКОМ из согласия, одобрения, благодарности, принятия или знака — сочетания слов, знак при слове и
    одни знаки, приветствие и прощание рядом (по фразе на каждую строку словаря вежливости), обращение по имени после
    запятой, регистр и пунктуация; смешанное входящее (оплата и документ) — тоже утверждение."""
    miss = _missed(F1_AGREE + F1_POLITE)
    assert not miss, miss


def test_p3f_yes_word_heads_sentence_flagged():
    """п.1: слово согласия во главе предложения («Конечно.», «Разумеется.», «Of course.», «Sure.», «Certainly.») судится
    как «да»: дальше в ответе содержание без признака непроверенности — утверждение (как «Да. Ждём вас завтра.»)."""
    miss = _missed(F1_YES)
    assert not miss, miss
    assert T.PAY_WORDS in _judged("Да. Ждём вас завтра в 10:00.", QP_RU1, _results_rent_only())    # прежнее — так же


def test_p3f_agreement_without_payment_question_no_reason():
    """п.1, отрицательный с близнецом: входящее о документе, о способе или БУДУЩЕЙ оплате («Оплачу завтра утром,
    хорошо?» — «Хорошо.»), оплата не прошла, входящего нет — ответ-согласие причины не получает и назван `PC_NOASK`;
    ТОТ ЖЕ ответ на входящее об оплате — утверждение."""
    bad = _hit([(t, q, V_NOASK) for t, q in F1_NOASK])
    assert not bad, bad
    twins = [(t, QP_EN1 if re.match(r"[A-Za-z]", t) else QP_RU1) for t, _q in F1_NOASK]
    miss = _missed(twins)
    assert not miss, miss


def test_p3f_reply_with_content_or_check_not_blocked():
    """п.1, отрицательный (не менее 15 не-утверждений рядом): на входящее об оплате ответ с содержанием (реквизиты,
    вопрос, инструкция — правилом «целиком согласие» не судится), с обещанием проверки или передачей человеку, отказ,
    вопрос, согласие о другом предмете, согласие не от начала ответа, слово со строчной буквы после запятой (не имя),
    одно приветствие или значок — ни причины, ни сумм; у совпадения исход назван."""
    assert len(F1_NOT) >= 15
    bad = _hit(F1_NOT)
    assert not bad, bad


def test_p3f_punctuation_before_predicate_flagged():
    """п.2 (остаток О3 шага 3e и соседи): тире между суммой или числом и сказуемым получения клаузу не рвёт («7790 —
    получили.», «7790 бат — получены, спасибо!»), двоеточие между словом оплаты и сказуемым и между сказуемым и суммой
    — тоже («Оплата: получена ✅», «Получено: 7790 бат.») — утверждение на тех же основаниях; число без валюты — когда
    равно известной сумме сверки либо входящее об оплате. С опорой своя сумма причины не получает."""
    miss = _missed(F3_PUNCT)
    assert not miss, miss
    sums = T.pay_sums(T.accepted(_results_no_second()))
    assert T.pay_claimed("7790 — получили.", False, sums) == {7790}
    assert T.pay_claimed("7790 бат — получили.") == {7790} and T.pay_claimed("Получено: 7790 бат.") == {7790}
    backed = _results_backed()
    for text in ("7790 — получили.", "7790 бат — получили.", "Оплата: получена.", "Получено: 7790 бат."):
        assert T.PAY_WORDS not in _judged(text, Q_NONE, backed), text
    assert T.PAY_WORDS in _judged("8000 бат — получили.", Q_NONE, backed)   # чужая сумма при подтверждённой оплате


def test_p3f_punctuation_not_claims_not_blocked():
    """п.2, отрицательный: номер байка или заказа перед тире, число не из фактов без входящего об оплате, вопрос,
    отрицание, будущее, условие, залог, получатель — клиент, счёт на сумму, не сказуемое получения за тире или
    двоеточием («получена скидка», «получена ссылка», «есть», «ожидается»), способ оплаты, «К оплате: 7790 бат.» — ни
    причины, ни сумм, исход назван."""
    bad = _hit(F3_NOT)
    assert not bad, bad


def test_p3f_own_fresh_search_fixed():
    """Свой свежий поиск шага 3f (существенные находки чинены тем же определением): сочетания согласия со знаками,
    обращением и вежливостью, согласие во главе предложения, тире и двоеточие перед сказуемым получения."""
    miss = _missed(F_FRESH_AFFIRM)
    assert not miss, miss


def test_p3f_verdict_named_on_every_road():
    """Храповик слепых читателей: у правил шага 3f исход — тоже всегда НЕПУСТОЕ имя, и `search` говорит «утверждение»
    ровно тогда, когда так назван хотя бы один исход — с контекстом сверки и без него."""
    rows = [(t, q) for t, q in F1_AGREE + F1_POLITE + F1_YES + F1_NOASK + F3_PUNCT + F_FRESH_AFFIRM]
    rows += [(t, q) for t, q, _name in F1_NOT + F3_NOT]
    rows += [(_whole(w), QP_RU1) for w in F1_DEC_RU + F1_ADD_RU + F1_DEC_EN + F1_ADD_EN]
    rows += [(s, QP_RU3) for s in F1_DEC_SIGNS + F1_ADD_SIGNS]
    for text, question in rows:
        for asked, sums in (_ctx_of(question), (False, ())):
            got = T._PAY_CLAIM.explain(text, asked, sums)
            assert all(isinstance(v, str) and v.strip() for _match, v in got), (text, got)
            assert (V_CLAIM in [v for _match, v in got]) == bool(T._PAY_CLAIM.search(text, asked, sums)), (text, got)
    assert {v for _m, v in T._PAY_CLAIM.explain("Конечно.")} == {V_NOASK}
    assert {v for _m, v in T._PAY_CLAIM.explain("Конечно.", True)} == {V_CLAIM}
    assert {v for _m, v in T._PAY_CLAIM.explain("Спасибо, Алексей!")} == {V_NOASK}
    assert {v for _m, v in T._PAY_CLAIM.explain(THUMB, True)} == {V_CLAIM}
    assert {v for _m, v in T._PAY_CLAIM.explain("Конечно, договор пришлём.", True)} == {V_OTHER}
    assert {v for _m, v in T._PAY_CLAIM.explain("Спасибо, проверим поступление.", True)} == set()   # совпадения нет
    assert {v for _m, v in T._PAY_CLAIM.explain("NMAX 90101 — получили.", False, {7790})} == {V_NUM}
    assert {v for _m, v in T._PAY_CLAIM.explain("7790 — получили.", False, {7790})} == {V_CLAIM}
    assert {v for _m, v in T._PAY_CLAIM.explain("7790 — получили.")} == {V_NUM}                # без сумм фактов
    assert {v for _m, v in T._PAY_CLAIM.explain("Ссылка для оплаты: получена.")} == {V_PREP, V_NOASK}


def test_p3f_agreement_parse_is_unambiguous():
    """п.1, устройство: разбор «ответа целиком из согласия» на слова ОДНОЗНАЧЕН — на длинном ответе, который согласием
    не кончается, перебор вариантов не растёт взрывом (первый вариант правки на таком тексте не кончался вовсе): слово
    словаря не бывает именем, «спасибо большое», «абсолютно верно», «да-да» разбираются одним способом."""
    import time
    for unit in (", спасибо", ", Спасибо", " спасибо большое", " абсолютно верно", " именно так точно", "-да",
                 ", Алексей, спасибо", " thanks so much", ", Привет", " " + THUMB):
        text = "Спасибо" + unit * 28 + ", ждём вас завтра"                 # 28 повторов: неоднозначный разбор — секунды
        t0 = time.perf_counter()
        got = T._PAY_CLAIM.explain(text, True)
        took = time.perf_counter() - t0
        assert took < 1.0, (unit, took)
        assert V_CLAIM not in [v for _m, v in got], (unit, got)
        whole = "Спасибо" + unit * 28                                       # тот же текст без содержания — согласие
        assert V_CLAIM in [v for _m, v in T._PAY_CLAIM.explain(whole, True)], unit


def test_p3f_control_prior_outcomes_kept():
    """КОНТРОЛЬ п.3f (зелёный и на b7dea68): прежние исходы не задеты — «Да.», «Да, получили.» и их имена; сказуемое за
    тире при входящем об оплате — прежнее краткое подтверждение и тогда, когда число перед тире стоит на месте номера
    («NMAX 90101 — получили.»); остаток О5 с запятой — утверждение; с опорой (касса + договор) согласие причины не
    получает."""
    assert not _missed([("Да.", QP_RU1), ("Да, получили.", QP_RU1), ("Да, конечно.", QP_RU3), ("7790 — получили.", QP_RU1),
                        ("NMAX 90101 — получили.", QP_RU1), ("Байк 90101 — получили.", QP_RU1),
                        ("Когда приедете за байком, оплата уже получена.", Q_NONE), ("Оплата уже получена.", Q_NONE)])
    assert {v for _m, v in T._PAY_CLAIM.explain("Да, получили.", True)} == {V_OTHER, V_CLAIM}
    assert {v for _m, v in T._PAY_CLAIM.explain("Да, получили.")} == {V_NOASK}
    backed = _results_backed()
    rows = F1_AGREE + F1_POLITE + F1_YES + [(_whole(w), QP_RU1) for w in F1_DEC_RU] + [(s, QP_RU3) for s in F1_DEC_SIGNS]
    bad = [(t, q) for t, q in rows if T.PAY_WORDS in _judged(t, q, backed)]
    assert not bad, bad
    assert not _hit([("Да, получили.", QD_RU, V_NOASK), ("Оплату пока не вижу, коллега проверит.", QP_RU1, None)])


# ═══ п.3g: открытая тема оплаты без подтверждения кодом — причина класса (блокеры D1, D2 проверки 3d+3e+3f) ═════
# Словарь утверждений N4 класс не закрывает (15 из 32 свежих утвердительных обычного строя): на входящем без слов общей
# причины кода (`K.handoff`) черновик уходил вовсе без причины. Правило класса: тема оплаты ОТКРЫТА и оплата кодом НЕ
# подтверждена ⇒ причина кода есть при ЛЮБОМ тексте ответа. Всё — настоящим путём адаптера: `build` НЕ подменён,
# подменён только `_history` (история сценария в форме `wa_history`); причин модели нет — всё, что вернулось, поставил код.
G_FAMILY = ("оплата со слов клиента — поступление не проверено", "вопрос об оплате", "оплата")   # K.MONEY_WORDS оплаты
G_SAID, G_ASK, G_PLAIN = G_FAMILY
V_TAIL = "тема оплаты открыта: клиент сейчас сообщает об оплате или спрашивает о поступлении"
V_PREV = "тема оплаты открыта: клиент сообщал об оплате или спрашивал о поступлении перед нашим последним ответом"
V_OURS = "тема оплаты открыта: наш последний ответ — об оплате"
V_NONE = "тема оплаты не открыта"
V_PAID = "тема оплаты открыта, оплата подтверждена кодом — причины класса нет"

# (i) D2 — входящее об оплате БЕЗ слов общей причины кода, истории нет. PATH_B — дословно fix_review3f/my_corpus2.py
GB1, GB2, GB3 = "Деньги пришли?", "Скинул 7790 на карту, гляньте.", "Has the money arrived?"
GB4, GB5 = "Закинул вам на карту, посмотрите.", "Money sent, please confirm."
G_PATH_B = [
    (GB1, "Да, всё пришло, спасибо!"), (GB1, "Да, оплата получена."), (GB1, "Да, с оплатой всё хорошо."),
    (GB1, "Да, деньги на счёте."), (GB1, "Да, деньги на счёте, спасибо! Договор пришлю сегодня."),
    (GB2, "Да, видим, спасибо!"), (GB2, "Спасибо! Ждём вас завтра в 10:00."),
    (GB2, "Отлично! Договор пришлю сегодня вечером."), (GB3, "Yes, your payment is complete."),
    (GB3, "Yes, everything is fine with your payment."), (GB3, "Yes, it's in, thank you!"),
    (GB5, "Confirmed, thank you!"), (GB5, "Happy to confirm receipt of your payment."), (GB4, "Да, всё на месте.")]
G_HEDGED = ([(q, t) for q in (GB1, GB2, GB4)                                      # оговорки: «не видим», «проверим»
             for t in ("Пока не видим, проверим.", "Пока оплату в кассе не вижу, коллега проверит и ответит.",
                       "Спасибо! Сейчас проверим кассу и вернёмся с ответом.")]
            + [(q, t) for q in (GB3, GB5) for t in ("We don't see it yet, we will check and reply.",
                                                    "Thank you! We will check our records and confirm shortly.")])
G_PATH_B_OWN = [                                # СВОИ пары: на d55b689 признак входящего True, причин кода [] при обоих наборах
    ("Видите мои деньги?", "Да, с оплатой порядок, ждём вас завтра."), ("Деньги дошли?", "Всё зачтено, спасибо!"),
    ("Отправил вам 7790 бат, посмотрите.", "Да, видим вашу сумму, всё верно."),
    ("Кинул 7790 на карту, глянь.", "Спасибо, всё у нас! Ждём вас завтра в 10:00."),
    ("Средства поступили?", "Супер, спасибо! Байк будет готов к 10:00."),
    ("Вы получили деньги?", "С деньгами всё ок, ждём вас."), ("Закинул 7790, гляньте.", "Отлично, тогда оформляю договор."),
    ("Деньги отправил, гляньте.", "Благодарю! Договор пришлю сегодня вечером."),
    ("Передал деньги водителю.", "Замечательно! Шлем тоже подготовим."),
    ("Did the money come through?", "Yes, you're all set. See you tomorrow!"),
    ("Sent 7790 baht, can you see it?", "Great! See you tomorrow at 10."),
    ("Have you got the money?", "Perfect — you're good to go."), ("Has the money landed?", "Yes, sorted, thanks!"),
    ("Funds sent, please confirm.", "Thanks! Everything's set for tomorrow.")]

# (ii) D1 — хвост без слов оплаты после обмена «клиент сообщил об оплате → мы: проверим». PATH_C, FOLLOWUP — дословно
G_PAID = "Перевёл вам 7790 бат за аренду, проверьте, пожалуйста."
G_H_CHECK = [("клиент", G_PAID), ("мы", "Спасибо! Проверим поступление и вернёмся с ответом.")]
G_PATH_C = [
    ("Проверили?", "Да, проверили — всё пришло, спасибо!"), ("Проверили?", "Да, оплата получена."),
    ("Проверили?", "Да, деньги пришли."), ("Проверили?", "Да, 7790 получили."), ("Проверили?", "Да, всё в порядке."),
    ("Ну что там?", "Всё в порядке, получили."), ("Ну как, пришло?", "Да, пришло, спасибо!"),
    ("Есть новости по моему вопросу?", "Да, всё получили, спасибо. Ждём вас завтра."),
    ("Any news?", "Yes, all received, thank you!"), ("Did it arrive?", "Yes, it arrived this morning."),
    ("Ну что?", "Да, всё на месте."), ("Получили?", "Получили, спасибо!")]
G_FOLLOWUP = [
    ("Проверили?", "Да, всё пришло, спасибо!"), ("Ну что, получили?", "Да, получили, спасибо!"), ("Пришло?", "Да, пришло."),
    ("Есть новости?", "Да, всё получили, спасибо."), ("Did you get it?", "Yes, we got it, thanks!"),
    ("Any update?", "Yes, received, thank you."), ("Transferred 7790 baht, please check.", "Yes, received, thank you!"),
    ("Отправил, проверьте, пожалуйста.", "Да, получили, спасибо!"), ("[фото]", "Получили, спасибо!"),
    ("Sent!", "Got it, thanks!"), ("Готово, скинул.", "Да, всё дошло."), ("Дошло?", "Да, дошло.")]
G_D1_OWN = [                                    # СВОИ: иные обмены «клиент сообщил об оплате → мы ответили»
    ([("клиент", "Деньги отправил, гляньте."), ("мы", "Спасибо, сейчас посмотрим.")], "Ну как?", "Да, всё пришло, спасибо!"),
    ([("клиент", "I've just sent the money, please confirm."), ("мы", "Thank you! We will check and get back to you.")],
     "So?", "Yes, all good, thank you!"),
    ([("клиент", "Закинул вам 7790 на карту."), ("мы", "Принято, уточню у коллег и вернусь.")], "Алло?", "Да, получили."),
    ([("клиент", "Оплатила аренду, проверьте."), ("мы", "Пока не видим поступления, проверяем.")],
     "Есть что-нибудь?", "Да, всё в порядке."),
    ([("клиент", "Отправил вам 7790 бат."), ("клиент", "Посмотрите, пожалуйста."), ("мы", "Здравствуйте!"),
      ("мы", "Минуту, смотрим.")], "Жду ответа.", "Спасибо за ожидание! Всё хорошо, ждём вас завтра."),
    ([("клиент", "Передал деньги вашему водителю."), ("мы", "Хорошо, спасибо.")],     # наш ответ без слов оплаты: часть (2)
     "И что дальше?", "Всё отлично, байк ваш до 15 октября.")]
G_D1_CHAIN = [                                  # тема тянется через наше «проверяем»: клиент об оплате — два обмена назад
    ([("клиент", "Перевёл 7790 бат."), ("мы", "Спасибо, проверим."), ("клиент", "Ок, жду."), ("мы", "Ещё проверяем.")],
     "Ну как?", "Да, всё пришло!"),
    ([("клиент", "Sent you the money."), ("мы", "Thanks, we will check."), ("клиент", "Ok."),
      ("мы", "We will check again, one moment.")], "Any luck?", "Yes, all good, thank you!")]

# (iii) — первое сообщение без слов словаря после НАШЕГО ответа об оплате (способ, реквизиты, сумма к оплате)
G_H_HOW = [("клиент", "Как можно оплатить аренду?"),
           ("мы", "Оплатить можно переводом на карту — реквизиты пришлю следующим сообщением — или наличными при "
                  "получении байка.")]
G_H_HOW_EN = [("клиент", "How can I pay for the rental?"),
              ("мы", "You can pay by bank transfer — I will send the details — or in cash at pickup.")]
G_PHOTO = ("медиа", "фото")
G_CHAIN3 = [(G_H_HOW, q, t)                                                          # дословно решение: 5 × 3
            for q in ("Sent!", "Готово, скинул.", G_PHOTO, "Wired the money.", "Отправил, проверьте, пожалуйста.")
            for t in ("Спасибо, получили!", "Да, всё пришло.", THUMB)]
G_CHAIN3_EN = [(G_H_HOW_EN, q, t) for q in ("Sent!", "Wired the money.", G_PHOTO)
               for t in ("Thank you, received!", "Yes, all received.", THUMB)]
G_CHAIN3_OWN = [                                # СВОИ: иные наши ответы об оплате; у каждого — какая подчасть (3) её узнаёт
    ([("клиент", "Куда платить?"), ("мы", "Реквизиты для перевода: Тест Банк, счёт TEST-ACC-0001, получатель Test Co.")],
     "Готово.", "Спасибо, получили!"),
    ([("клиент", "How do I pay?"), ("мы", "You can pay by bank transfer or in cash at pickup. The total is 7790 THB.")],
     "Done!", "Great, thank you!"),
    ([("клиент", "Сколько с меня?"), ("мы", "К оплате 7790 бат за 10 дней, залог 3000 бат.")],
     "Всё, сделал.", "Да, всё пришло, спасибо."),
    ([("клиент", "Можно картой?"), ("мы", "Да, картой можно. Переведите 7790 бат на карту — номер пришлю.")],
     "Отправил.", THUMB),                                                          # только группа оплаты R_MONEY
    ([("клиент", "Хочу продлить на неделю."), ("мы", "Продление на 7 дней — 5453 бат, оплатить можно до конца аренды.")],
     "Вот.", "Спасибо! Ждём вас завтра в 10:00."),
    ([("клиент", "Ок, беру."), ("мы", "Отлично! Деньги можно передать курьеру при встрече либо отправить заранее.")],
     "Ок, держите.", "Получили, спасибо!"),                                         # только слово оплаты `_PQ_PAYWORD`
    ([("клиент", "Здравствуйте."), ("мы", "Здравствуйте! Счёт на 7790 бат отправили вам на почту, чек пришлём после.")],
     "Готово, спасибо.", "Отлично, спасибо!"),
    ([("клиент", "Is everything ok with my booking?"), ("мы", "Yes. Payment for the rental is by transfer or cash.")],
     "Lovely, done.", "Perfect, thanks!"),
    ([("клиент", "Когда платить?"), ("мы", "Проверим и ответим.")], "Скинул только что.", "Отлично, спасибо!"),   # обещание
    ([("клиент", "Что по расчётам?"), ("мы", "Задолженности по аренде нет.")], "Тогда ещё докинул.", "Спасибо, получили!")]

# без открытой темы: новой причины нет (общая причина по входящему, если была, — как была)
G_DOC = "Здравствуйте! Пришлите, пожалуйста, договор аренды."
G_CLOSED = [
    ([], "Как можно оплатить аренду?", "Оплатить можно наличными при получении байка или переводом на тайский счёт."),
    ([], "Можно оплатить картой?", "Да, картой можно — через терминал при получении байка."),
    ([], "Оплачу завтра утром, хорошо?", "Хорошо, ждём вас завтра."),
    ([], G_DOC, "Договор во вложении. Если будут вопросы по условиям — пишите."),
    ([], QD_RU, "Да, получили, спасибо!"),
    ([], "Здравствуйте! Есть шлемы?", "Да, шлем входит в стоимость аренды."),
    ([("клиент", "Во сколько вы открываетесь?"), ("мы", "Мы работаем с 9:00 до 20:00 каждый день.")],
     "Спасибо!", "Пожалуйста! Ждём вас."),
    ([("клиент", "Пришлите договор."), ("мы", "Договор проверим и пришлём сегодня.")], "Ок, жду.", "Спасибо за ожидание!"),
    ([("клиент", "Можно шлем побольше?"), ("мы", "Да, подберём размер L.")], "Супер", "Отлично, до встречи!"),
    ([("клиент", "Do you deliver to Kata?"), ("мы", "Yes, delivery to Kata is available.")], "Great, thanks!",
     "You're welcome!"),
    # (строка первой части «клиент говорил об оплате ДВА обмена назад, наш последний ответ — не об оплате» отсюда снята
    # второй частью шага: тема — состояние переписки, она открыта и там — см. `G2_FORMER_CLOSED`)
    # автоприветствие нашим ответом не считается (его слово «оплата» тему не открывает)
    ([("клиент", "Здравствуйте."), ("авто", "Здравствуйте! Это TurboBaby, оплата и вопросы — здесь.")],
     "Есть NMAX на завтра?", "Уточню наличие и вернусь.")]
# общая причина по входящему уже стоит (слова R_MONEY во входящем): правило её не дублирует — список причин прежний
G_MERGED = [
    ([], QP_RU1, "Да, с оплатой всё хорошо.", [G_SAID]),
    ([], G_PAID, "Да, деньги на счёте, спасибо!", [G_SAID]),
    ([], QP_EN1, "Yes, everything is fine with your payment.", [G_SAID]),
    # общая по хвосту + тема по части (2); шаг 3i (В): краткое «Да, всё пришло.» на хвост без иного предмета — и причина N4
    (G_H_CHECK, "Ну что с оплатой?", "Да, всё пришло.", ["оплата не подтверждена сверкой", G_ASK]),
    (G_H_HOW, "Оплатил, проверьте.", "Спасибо, получили!", ["оплата не подтверждена сверкой", G_SAID]),
    ([], "Как можно оплатить аренду?", "Оплата принимается наличными в батах при выдаче байка.", [G_ASK])]

# ── шаг 3i (вариант В) в ПРЕЖНИХ списках п.3g: изменённые ожидания ПОИМЁННО ───────────────────────────────────────
# Правило В (шаг 3i; шаг 3j — без условия «иной предмет во входящем»): краткое подтверждение получения или согласие в
# ответе при оплате, не подтверждённой кодом, судится как утверждение оплаты при ЛЮБОМ входящем — к причине класса (если
# тема открыта) добавляется причина N4 «оплата не подтверждена сверкой», и стоит она раньше причин семьи оплаты. Ниже —
# ВСЕ ответы прежних списков п.3g, которые получают её на хвостах без признака `pay_asked` (на хвостах с признаком она
# стояла и до шага). `G3J_NAMED` — три хвоста этих списков, которые называют предмет («шлем», «вопрос», «фото
# паспорта»): на шаге 3i ответ на них судился как раньше (условие «иной предмет»), шаг 3j ожидание ИЗМЕНИЛ — поимённые
# пары проверяет `test_p3j_changed_expectations_of_prior_lists_named`. Решают эти списки, а не код под проверкой.
G3I_BRIEF = (
    "Спасибо, получили!", "Да, всё пришло.", "Да, всё пришло!", "Да, всё пришло, спасибо!", "Да, всё пришло, спасибо.",
    "Да, проверили — всё пришло, спасибо!", "Да, оплата получена.", "Да, деньги пришли.", "Да, 7790 получили.",
    "Да, всё в порядке.", "Всё в порядке, получили.", "Да, пришло, спасибо!", "Да, пришло.", "Да, всё на месте.",
    "Получили, спасибо!", "Да, получили, спасибо!", "Да, получили.", "Да, всё получили, спасибо.", "Да, всё дошло.",
    "Да, дошло.", "Да, видим, спасибо!", "Отлично, спасибо!", "Отлично, до встречи!",
    "Спасибо за ожидание! Всё хорошо, ждём вас завтра.", "Всё отлично, байк ваш до 15 октября.", chr(0x1F44D),
    "Yes, all good, thank you!", "Yes, all received, thank you!", "Yes, all received.", "Yes, it arrived this morning.",
    "Yes, we got it, thanks!", "Yes, received, thank you.", "Yes, received, thank you!", "Thank you, received!",
    "Got it, thanks!", "Great, thank you!", "Perfect, thank you!", "Perfect, thanks!")
G3J_NAMED = ("Any luck with the helmet?", "Есть новости по моему вопросу?", "Отправил вам фото паспорта, получили?")


def _b3i(tail, text, facts="cash"):
    """Ждёт ли пара «хвост → ответ» ПРЕЖНИХ списков п.3g причину N4 по правилу В: ответ — поимённое краткое
    подтверждение или согласие (`G3I_BRIEF`), оплата кодом не подтверждена (набор фактов не «backed»). Хвост — любой
    (шаг 3j: и тот, что называет предмет, — `G3J_NAMED`; на шаге 3i такие хвосты ответ не судили). Только для хвостов БЕЗ
    признака `pay_asked`."""
    return facts != "backed" and text in G3I_BRIEF


def _wo3i(out, tail, text, facts="cash"):
    """Причины черновика БЕЗ причины N4 правила В (шаг 3i) — для прежних сравнений п.3g «список причин равен …». У
    поимённой пары (`_b3i`) причина `PAY_WORDS` обязана стоять ровно один раз и раньше причин семьи оплаты; у прочих пар
    её быть не должно — иначе в список попадает строка-маркер, и прежнее сравнение падает (на дереве до шага — тоже)."""
    hand = list(out["handoff"])
    if not _b3i(tail, text, facts):
        return hand
    fam = [i for i, w in enumerate(hand) if w in G_FAMILY]
    if hand.count(T.PAY_WORDS) != 1 or (fam and hand.index(T.PAY_WORDS) > fam[0]):
        return ["НЕТ причины N4 правила В (шаг 3i)"] + hand
    return [w for w in hand if w != T.PAY_WORDS]


def _items3g(history, tail):
    """История сценария → элементы формы `wa_history` (key, ts, who, text, word, file; «авто» — автоприветствие)."""
    rows, out = list(history) + [("клиент", tail)], []
    for i, (who, said) in enumerate(rows):
        media = isinstance(said, tuple)
        it = {"key": "g%d" % i, "ts": int(T0) - 60 * (len(rows) - i), "who": "мы" if who == "авто" else who,
              "text": "" if media else said, "word": said[1] if media else None, "file": None}
        if who == "авто":
            it["auto"] = True
        out.append(it)
    return out


def _draft3g(history, tail, text, facts="cash", handoff=(), hint=None, items=None):
    """Черновик настоящим путём адаптера (`draft` → `build` → `_draft_tools`) на истории сценария → (итог, адаптер,
    сценарий модели, журнал). facts: «none» — строки кассы нет; «cash» — касса без второго источника; «backed» — касса и
    договор той же аренды (оплата подтверждена кодом); «over» — предел вызовов, запасной вызов без фактов. `items` —
    готовые элементы истории (вторая часть шага: реплики со своим временем), иначе — `_items3g(history, tail)`."""
    steps = [{"tool": "rental", "args": {}}] * T.MAX_CALLS if facts == "over" else \
        [{"tool": "rental", "args": {}}, {"tool": "cash", "args": {"booking_id": BK}}] + \
        ([{"tool": "contract", "args": {}}] if facts == "backed" else [])
    s, logs = Script(*(steps + [final(text, handoff)])), []
    tools = {"cash": (lambda **kw: tx([] if facts == "none" else [tx_item()])), "contract": Registry([DOC1]),
             "contract_pdf": pdf_door}
    a = M.ModelAdapter(":memory:-не-открывается", s, read_doc=None, clock=Clock(), log=logs.append,
                       book=Book([dict(ROW)], 60.0), tools=tools, fresh=None)
    items = _items3g(history, tail) if items is None else items
    a._history = lambda number, upto_id: (items, [])
    out = a.draft(NUMBER, 5) if hint is None else a.redraft_checked(NUMBER, 5, *hint)
    return out, a, s, logs


def _family(out):
    """Причины кода семьи оплаты в итоговом списке черновика (слова `K.MONEY_WORDS`: заявил · спросил · нейтральное)."""
    return [w for w in out["handoff"] if w in G_FAMILY]


def _topic3g(a):
    """Исход определения «тема оплаты открыта» на том, что собрал настоящий `build` этого черновика."""
    info = a.last["info"]
    return T.pay_topic(info["question"], *info["before"])


def _no_reason3g(rows, want, need_words):
    """Сценарии без причины семьи оплаты при «строки кассы нет» / «касса без второго источника» либо с иным исходом
    определения, чем `want`, либо с иными словами, чем `need_words(адаптер)`."""
    bad = []
    for history, tail, text in rows:
        for facts in ("none", "cash"):
            out, a, _s, _logs = _draft3g(history, tail, text, facts)
            name, _words = _topic3g(a)
            if out["text"] != text or name != want or _family(out) != [need_words(a)] \
                    or T.pay_confirmed(a.last["tools"]["journal"].facts):
                bad.append((tail, text, facts, name, out["handoff"]))
    return bad


def test_p3g_topic_definition_named_parts():
    """Определение «тема оплаты открыта» — ОДНО, исход назван всегда: (1) хвост клиента об оплате; (2) блок клиента перед
    нашим последним ответом — об оплате; (3) наш последний ответ об оплате — обещал проверку или «не видим», подтвердил
    оплату, назвал её предметом (слово оплаты — `_PQ_PAYWORD` либо группа оплаты выражения R_MONEY); иначе — не открыта.
    Слова причины — существующие `K.MONEY_WORDS`: части (1)–(2) — смысл слов клиента (`K.payment_mode`), часть (3) —
    нейтральное «оплата». Первая сработавшая часть называет исход: хвост, затем предыдущий обмен, затем наш ответ."""
    assert (T.PT_TAIL, T.PT_PREV, T.PT_OURS, T.PT_NONE, T.PT_PAID) == (V_TAIL, V_PREV, V_OURS, V_NONE, V_PAID)
    assert G_FAMILY == (K.MONEY_WORDS[K.MONEY_PAYMENT], K.MONEY_WORDS[K.MONEY_PAYMENT_ASK],
                        K.MONEY_WORDS[K.MONEY_PAYMENT_UNCLEAR])
    assert T.pay_topic("Деньги пришли?") == (V_TAIL, G_ASK)                       # спросил о поступлении
    assert T.pay_topic("Скинул 7790 на карту, гляньте.") == (V_TAIL, G_SAID)       # заявил оплату
    assert T.pay_topic("Проверили?", G_PAID, "Проверим.") == (V_PREV, G_SAID)
    assert T.pay_topic("Ну что?", "Деньги пришли?", "Минуту.") == (V_PREV, G_ASK)
    assert T.pay_topic("Деньги пришли?", G_PAID, "Проверим оплату.") == (V_TAIL, G_ASK)   # хвост сильнее предыдущего
    assert T.pay_topic("Sent!", G_PAID, "Проверим оплату.") == (V_PREV, G_SAID)            # предыдущий сильнее нашего
    ours = [("Проверим и вернёмся с ответом.", "обещание проверки без иного предмета"),       # только `unsettled`
            ("В кассе пока не видим.", "«не видим»"),
            ("Задолженности по аренде нет.", "подтвердил оплату: «долга нет»"),                  # только утверждение N4
            ("All settled.", "подтвердил оплату"),
            ("Деньги можно передать курьеру при встрече.", "слово оплаты `_PQ_PAYWORD`"),        # только `_PQ_PAYWORD`
            ("Переведите 7790 бат на карту — номер пришлю.", "группа оплаты R_MONEY"),           # только R_MONEY
            ("You can pay in cash or by card at pickup.", "группа оплаты R_MONEY"),
            ("Оплатить можно наличными при получении байка.", "слово оплаты"),
            ("Реквизиты для оплаты отправил выше.", "реквизиты"), ("К оплате 7790 бат.", "сумма к оплате"),
            ("Оплата получена, спасибо!", "подтвердил оплату"), ("Чек пришлём после.", "чек")]
    for text, why in ours:
        assert T.pay_topic("Sent!", "Как оплатить?", text) == (V_OURS, G_PLAIN), (text, why)
    for text in ("Да, шлем дадим.", "Мы работаем с 9:00 до 20:00.", "Договор проверим и пришлём сегодня.",
                 "Уточню наличие байка и вернусь.", "Ждём вас завтра в 10:00.", "", None, "👍"):
        name, words = T.pay_topic("Sent!", "А шлем дадите?", text)
        assert name == V_NONE and words, (text, name)
        # шаг 3m, ожидание изменено ПОИМЁННО: блок клиента «Как оплатить?» («вопрос об оплате») перед таким нашим ответом
        # тему теперь ОТКРЫВАЕТ — `PT_PREV_NAMED`, слова «оплата» (было: `PT_NONE`)
        assert T.pay_topic("Sent!", "Как оплатить?", text) == (V_PREV_NAMED, G_PLAIN), text
    assert T.pay_topic() == (V_NONE, G_PLAIN) and T.pay_topic(None, None, None)[0] == V_NONE
    for q in ("Как оплатить?", "Можно картой?", "Оплачу завтра.", "Пришлите договор.", "Спасибо!", "[пусто]"):
        assert T.pay_topic(q)[0] == V_NONE, q                                       # вопрос о способе, будущая оплата


def test_p3g_rule_open_topic_and_unconfirmed_payment():
    """Правило класса: тема открыта И `pay_verdict` оплату не подтверждает (фактов нет, только аренда, касса без второго
    источника, чужая валюта) — причина есть, её слова — слова темы; оплата подтверждена (касса + договор той же аренды) —
    `PT_PAID`, причины нет; тема не открыта — причины нет при любых фактах. Исход назван на каждой ветке."""
    usd = _results_rent_only() + [T.cash_result(tx([tx_item(currency="USD")]), at=T0)]
    unpaid = {"фактов нет": [], "только аренда": T.accepted(_results_rent_only()),
              "касса без второго источника": T.accepted(_results_no_second()), "чужая валюта": T.accepted(usd)}
    backed = T.accepted(_results_backed())
    assert T.pay_confirmed(backed) is True and not [k for k, f in unpaid.items() if T.pay_confirmed(f)]
    for name, words in ((V_TAIL, G_ASK), (V_TAIL, G_SAID), (V_PREV, G_SAID), (V_OURS, G_PLAIN)):
        for label, facts in unpaid.items():
            assert T.topic_reason((name, words), facts) == (name, [words]), (name, label)
        assert T.topic_reason((name, words), backed) == (V_PAID, []), name
    for facts in list(unpaid.values()) + [backed]:
        assert T.topic_reason((V_NONE, G_PLAIN), facts) == (V_NONE, [])
        assert T.topic_reason(None, facts) == (V_NONE, []) and T.topic_reason((), facts) == (V_NONE, [])
        assert T.topic_reason(("иное имя", G_PLAIN), facts) == (V_NONE, [])


def test_p3g_d2_incoming_about_payment_any_reply_has_code_reason():
    """(i) D2: входящее об оплате БЕЗ слов общей причины кода («Деньги пришли?», «Скинул 7790 на карту, гляньте.», «Has
    the money arrived?», «Money sent, please confirm.» и 14 своих) × ЛЮБОЙ ответ — утверждение вне словаря N4 («Да, с
    оплатой всё хорошо.», «Yes, your payment is complete.»), ответ с содержанием («Спасибо! Ждём вас завтра в 10:00.»),
    оговорка («Пока не видим, проверим.») — при «строки кассы нет» и при «касса без второго источника» черновик несёт
    причину кода семьи оплаты, ровно одну, словами смысла входящего."""
    rows = [([], q, t) for q, t in G_PATH_B + G_HEDGED + G_PATH_B_OWN]
    assert (len(G_PATH_B), len(G_HEDGED), len(G_PATH_B_OWN)) == (14, 13, 14)
    for _h, q, _t in rows:
        assert T.pay_asked(q) is True and K.handoff(q, None) == [], q            # общей причины по входящему нет
    bad = _no_reason3g(rows, V_TAIL, lambda a: K.MONEY_WORDS[K.payment_mode(a.last["info"]["question"])])
    assert not bad, bad
    out, _a, _s, _logs = _draft3g([], GB1, "Да, с оплатой всё хорошо.", "cash")
    assert out["handoff"] == [G_ASK], out["handoff"]                              # была []: N4 фразу не ловит
    out, _a, _s, _logs = _draft3g([], GB2, "Спасибо! Ждём вас завтра в 10:00.", "none")
    assert out["handoff"] == [G_SAID], out["handoff"]


def test_p3g_d1_followup_after_payment_exchange_has_code_reason():
    """(ii) D1: хвост без слов оплаты («Проверили?», «Ну как, пришло?», «Any news?», «Sent!», «[фото]») после обмена, где
    клиент сообщал об оплате, а мы ответили («проверим», «сейчас посмотрим», «хорошо, спасибо»), — причина кода семьи
    оплаты при обоих наборах фактов; слова — смысл слов клиента ПРЕДЫДУЩЕГО блока. Тема тянется и через наше
    «проверяем» (клиент об оплате — два обмена назад): тогда слова — нейтральное «оплата»."""
    rows = [(G_H_CHECK, q, t) for q, t in G_PATH_C + G_FOLLOWUP] + G_D1_OWN
    assert (len(G_PATH_C), len(G_FOLLOWUP), len(G_D1_OWN)) == (12, 12, 6)
    # у одного хвоста («Transferred 7790 baht…») общая причина по входящему уже стоит — её слова и остаются
    plain = [r for r in rows if not K.handoff(r[1], None)]
    assert len(rows) - len(plain) == 1 and not [1 for _h, q, _t in rows if T.pay_asked(q)]
    bad = _no_reason3g(plain, V_PREV, lambda a: K.MONEY_WORDS[K.payment_mode(a.last["info"]["before"][0])])
    assert not bad, bad
    for facts in ("none", "cash"):
        out, a, _s, _logs = _draft3g(G_H_CHECK, "Transferred 7790 baht, please check.", "Yes, received, thank you!", facts)
        assert _topic3g(a)[0] == V_PREV and _family(out) == [G_ASK], out["handoff"]
    out, a, _s, _logs = _draft3g(G_H_CHECK, "Проверили?", "Да, проверили — всё пришло, спасибо!", "cash")
    # шаг 3i (В): краткое «всё пришло» на «Проверили?» (иного предмета нет) — ещё и причина N4, впереди причины класса
    assert out["handoff"] == [T.PAY_WORDS, G_SAID] and a.last["info"]["before"] == (G_PAID, G_H_CHECK[1][1]), out["handoff"]
    bad = _no_reason3g(G_D1_CHAIN, V_OURS, lambda a: G_PLAIN)
    assert not bad, bad


def test_p3g_first_message_after_our_payment_answer_has_code_reason():
    """(iii): мы назвали способ, реквизиты или сумму к оплате → клиент: «Sent!», «Готово, скинул.», «[фото]», «Wired the
    money.», «Отправил, проверьте, пожалуйста.» (признак хвоста False, предыдущий блок клиента — не об оплате) → краткое
    подтверждение («Спасибо, получили!», «Да, всё пришло.», «👍») — причина кода «оплата» при обоих наборах фактов.
    Свои — по ответу на каждую подчасть (3): обещание проверки, утверждение оплаты, слово оплаты, группа оплаты R_MONEY."""
    rows = G_CHAIN3 + G_CHAIN3_EN + G_CHAIN3_OWN
    assert (len(G_CHAIN3), len(G_CHAIN3_EN), len(G_CHAIN3_OWN)) == (15, 9, 10)
    for history, tail, _text in rows:
        said = tail if isinstance(tail, str) else "[%s]" % tail[1]
        assert T.pay_asked(said) is False and T.pay_asked(history[-2][1]) is False, (said, history)
        assert K.handoff(said, None) == [], said
    bad = _no_reason3g(rows, V_OURS, lambda a: G_PLAIN)
    assert not bad, bad
    out, a, _s, _logs = _draft3g(G_H_HOW, G_PHOTO, THUMB, "none")
    # шаг 3i (В): знак согласия на медиа без подписи (предмета не называет) — ещё и причина N4
    assert out["handoff"] == [T.PAY_WORDS, G_PLAIN] and a.last["info"]["question"] == "[фото]", (out["handoff"], a.last["info"])


def test_p3g_confirmed_payment_adds_nothing():
    """Близнецы: ТЕ ЖЕ пары (i)–(iii) при ПОДТВЕРЖДЁННОЙ оплате (касса аренды обращения + договор той же аренды) — новой
    причины нет ни в одной: в списке нет причины семьи оплаты сверх общей причины по входящему, исход правила —
    `PT_PAID`. Полезный сценарий (оплата подтверждена, ответ с PDF) правилом не задет."""
    rows = [([], q, t) for q, t in G_PATH_B + G_HEDGED + G_PATH_B_OWN]
    rows += [(G_H_CHECK, q, t) for q, t in G_PATH_C + G_FOLLOWUP] + G_D1_OWN + G_D1_CHAIN
    rows += G_CHAIN3 + G_CHAIN3_EN + G_CHAIN3_OWN
    assert len(rows) == 107
    bad = []
    for history, tail, text in rows:
        out, a, _s, logs = _draft3g(history, tail, text, "backed")
        facts = a.last["tools"]["journal"].facts
        by_tail = [r["words"] for r in a.last["info"]["code_reasons"]]
        if not T.pay_confirmed(facts) or T.topic_reason(_topic3g(a), facts) != (V_PAID, []) \
                or _family(out) != [w for w in by_tail if w in G_FAMILY] or "оплата не подтверждена сверкой" in out["handoff"] \
                or not [ln for ln in logs if ln.startswith("правило класса: " + V_PAID)]:
            bad.append((tail, text, out["handoff"]))
    assert not bad, bad
    out, _a, _s, _logs = _draft3g([], GB1, "Да, оплата получена. Договор отправляю следующим сообщением.", "backed")
    assert out["handoff"] == [], out["handoff"]


def test_p3g_closed_topic_adds_nothing():
    """Без открытой темы новой причины нет: первое обращение «как оплатить?» (общая причина «вопрос об оплате» — как была,
    одна), вопрос о документе, о шлеме, благодарность после ответа не об оплате; автоприветствие нашим ответом не
    считается — при «строки кассы нет» и «касса без второго источника» список причин равен причинам кода по входящему.
    (Строка «клиент говорил об оплате два обмена назад» — уже не «без темы»: вторая часть шага, `G2_FORMER_CLOSED`.)
    Шаг 3i (В), ЦЕНА правила поимённо: «Супер» → «Отлично, до встречи!» (ответ целиком из согласия, оплата кодом не
    подтверждена) получает причину N4; шаг 3j (условие «иной предмет во входящем» снято), поимённо: её получает и
    «Отправил вам фото паспорта, получили?» → «Да, получили, спасибо!». Обе сняты из сравнения `_wo3i`; причины КЛАССА
    по-прежнему нет ни у одной строки."""
    bad = []
    for history, tail, text in G_CLOSED:
        for facts in ("none", "cash"):
            out, a, _s, logs = _draft3g(history, tail, text, facts)
            by_tail = [r["words"] for r in a.last["info"]["code_reasons"]]
            if _topic3g(a)[0] != V_NONE or _wo3i(out, tail, text, facts) != by_tail \
                    or [ln for ln in logs if ln.startswith("правило класса")]:
                bad.append((tail, facts, _topic3g(a)[0], out["handoff"], by_tail))
    assert not bad, bad
    assert [(tail, text) for _h, tail, text in G_CLOSED if _b3i(tail, text)] == [
        (QD_RU, "Да, получили, спасибо!"), ("Супер", "Отлично, до встречи!")]
    out, a, _s, _logs = _draft3g(*G_CLOSED[-1], facts="cash")
    assert a.last["info"]["before"] == ("", ""), a.last["info"]["before"]         # автоприветствие — не наш ответ


def test_p3g_merge_with_general_reason_no_duplicate():
    """Слияние: общая причина по входящему (слова R_MONEY во входящем) уже стоит — правило второй причины оплаты не
    добавляет и порядка не меняет: список причин дословно прежний (K02: одна «оплата со слов клиента — поступление не
    проверено»), в журнале — «не добавлена (оплату уже назвал код по входящему)»."""
    bad = []
    for history, tail, text, want in G_MERGED:
        closed = _topic3g(_draft3g(history, tail, text, "cash")[1])[0] == V_NONE
        for facts in ("none", "cash"):
            out, a, _s, logs = _draft3g(history, tail, text, facts)
            said = [ln for ln in logs if ln.startswith("правило класса")]
            if out["handoff"] != want or len(_family(out)) != 1 or (not closed and not [1 for ln in said if "не добавлена" in ln]) \
                    or (closed and said):
                bad.append((tail, facts, out["handoff"], said))
    assert not bad, bad
    # причина МОДЕЛИ об оплате — пересказ: отпадает как повтор причины кода, а не вытесняет её
    out, _a, _s, _logs = _draft3g([], GB1, "Да, с оплатой всё хорошо.", "cash",
                                  handoff=["клиент спрашивает об оплате — проверьте поступление"])
    assert out["handoff"] == [G_ASK], out["handoff"]


def test_p3g_adapter_path_history_to_card():
    """Путь адаптера целиком: история → `build` (хвост, блок клиента перед нашим ответом, наш ответ — в сведениях
    `before`, в ЗАПРОС модели признаки не идут) → исход определения → причина ПЕРВОЙ среди причин не о деньгах текста →
    поля карточки сотрудника: слова → категория → ярлык действия (`wa_agent_tg.card_actions`), строка «НУЖЕН ЧЕЛОВЕК»."""
    import wa_agent_tg as TG
    labels = {G_SAID: TG.CARD_ACTIONS[K.MONEY_PAYMENT], G_ASK: TG.CARD_ACTIONS[K.MONEY_PAYMENT_ASK],
              G_PLAIN: TG.CARD_ACTIONS[K.MONEY_PAYMENT_UNCLEAR]}
    # шаг 3i (В): у краткого подтверждения на хвост без иного предмета («Проверили?», «Готово, скинул.») первой стоит ещё
    # и причина N4 — её слова на карточке дают действие «вопрос об оплате» (категория слов причины, как у N4 всегда)
    n4_act = TG.CARD_ACTIONS[K.MONEY_PAYMENT_ASK]
    cases = [([], GB1, "Да, с оплатой всё хорошо.", G_ASK, False),
             (G_H_CHECK, "Проверили?", "Да, всё в порядке.", G_SAID, True),
             (G_H_HOW, "Готово, скинул.", "Спасибо, получили!", G_PLAIN, True)]
    for history, tail, text, want, n4 in cases:
        out, a, s, logs = _draft3g(history, tail, text, "cash")
        hand = A.draft_out(out)[1]
        assert hand == ([T.PAY_WORDS] if n4 else []) + [want] and K.word_categories(want), (tail, hand)
        assert TG.card_actions(hand) == ([n4_act] if n4 else []) + [labels[want]], (tail, TG.card_actions(hand))
        notes = TG.card_notes(hand, 1, True)
        assert TG.W_HAND in notes and "• " + labels[want] in notes and TG.W_SEND_HAND in notes, notes
        assert out["question"] == tail and not [u for u in s.seen if "НУЖЕН ЧЕЛОВЕК" in u], out["question"]
        assert [ln for ln in logs if ln.startswith("правило класса") and "причина кода добавлена" in ln], logs
    # порядок: причина класса — впереди причин не о деньгах, сразу за причинами судьи по тексту
    q = "Деньги пришли? И есть ли свободный NMAX со скидкой?"
    assert [r["words"] for r in K.handoff(q, None)] == [K.REASON_WORDS[K.R_AVAILABILITY], K.REASON_WORDS[K.R_DISCOUNT]]
    out, _a, _s, _logs = _draft3g([], q, "Уточню у коллег и вернусь.", "cash")
    assert out["handoff"] == [G_ASK, K.REASON_WORDS[K.R_AVAILABILITY], K.REASON_WORDS[K.R_DISCOUNT]], out["handoff"]
    out, _a, _s, _logs = _draft3g([], q, "Да, оплата получена.", "cash")
    assert out["handoff"][:2] == ["оплата не подтверждена сверкой", G_ASK], out["handoff"]


def test_p3g_unfinished_check_and_hint_paths():
    """Тот же признак — в каждом пути черновика со сверкой: сверка НЕ завершена (предел вызовов → запасной вызов без
    фактов: оплата кодом не подтверждена) — причина класса стоит за «сверка не завершена»; версия по пояснению со
    сверкой (`redraft_checked`) — тот же путь. Без открытой темы у незавершённой сверки причины класса нет."""
    rows = [([], GB1, "Да, с оплатой всё хорошо.", G_ASK), (G_H_CHECK, "Проверили?", "Да, всё в порядке.", G_SAID),
            (G_H_HOW, "Sent!", THUMB, G_PLAIN)]
    for history, tail, text, want in rows:
        out, a, s, _logs = _draft3g(history, tail, text, "over")
        assert a.last["tools"]["state"] == T.OVER and len(s.seen) == T.MAX_CALLS + 1, a.last["tools"]["state"]
        # шаг 3i (В): у «Проверили?» → «Да, всё в порядке.» и «Sent!» → «👍» между ними стоит ещё и причина N4 (`_wo3i`)
        hand = out["handoff"] if T.pay_asked(tail) else _wo3i(out, tail, text, "over")
        assert hand[:2] == [T.INCOMPLETE_WORDS, want] and _family(out) == [want], out["handoff"]
        out, a, _s, _logs = _draft3g(history, tail, text, "cash", hint=("прежний черновик", "скажи короче"))
        assert a.last["info"].get("hint") is True and _family(out) == [want], out["handoff"]
    assert [T.pay_asked(r[1]) or _b3i(r[1], r[2], "over") for r in rows] == [True, True, True]
    out, _a, _s, _logs = _draft3g([], G_DOC, "Договор пришлём.", "over")
    assert out["handoff"] == [T.INCOMPLETE_WORDS], out["handoff"]


def test_p3g_cash_said_opens_topic_until_confirmed():
    """K05 и соседи: клиент заявил ПЕРЕДАННЫЕ наличные («отдал вашему водителю 8000 бат наличными…») — это сообщение об
    оплате (`pay_asked`), а общая причина по входящему называет только сдачу («возврат денег»). Пока касса и второй
    источник оплату не подтвердили, правило добавляет причину семьи оплаты к прежним причинам кода (за причинами судьи
    по тексту, впереди прочих); подтвердили (K05 стенда: касса + договор той же аренды) — список причин прежний."""
    assert T.pay_asked(C3_QUESTION) is True and T.pay_topic(C3_QUESTION)[0] == V_TAIL
    want = K.MONEY_WORDS[K.payment_mode(C3_QUESTION)]
    out, a, _s, _logs = _draft3g([], C3_QUESTION, C3_TEXT, "backed")
    by_tail = [r["words"] for r in a.last["info"]["code_reasons"]]
    assert by_tail and not [w for w in by_tail if w in G_FAMILY], by_tail          # общая причина — не об оплате
    assert T.pay_confirmed(a.last["tools"]["journal"].facts) and out["handoff"] == [CHANGE_WORDS] + by_tail, out["handoff"]
    out, _a, _s, _logs = _draft3g([], C3_QUESTION, C3_TEXT, "cash")
    assert out["handoff"] == [CHANGE_WORDS, want] + by_tail, out["handoff"]
    out, _a, _s, _logs = _draft3g([], C3_QUESTION, C3_TEXT, "none")
    assert out["handoff"][1:] == [want] + by_tail and _family(out) == [want], out["handoff"]


def test_p3g_before_collects_previous_exchange():
    """Сбор признаков из истории (`ModelAdapter._before`): блок сообщений клиента перед нашим последним ответом и сам
    ответ — реплики подряд, склеенные по порядку; хвост в них не входит; автоприветствие и неизвестный отправитель
    пропускаются; медиа без подписи — словом; тексты под маской и не длиннее предела; ответа не было — пустые."""
    def items(*rows):
        return _items3g(rows[:-1], rows[-1][1])
    its = items(("клиент", "раньше"), ("мы", "старое"), ("клиент", "раз"), ("клиент", ("медиа", "фото")), ("мы", "ответ 1"),
                ("авто", "приветствие"), ("?", "шум"), ("мы", "ответ 2"), ("клиент", "хвост 1"), ("клиент", "хвост 2"))
    assert [it["text"] for it in M.ModelAdapter._tail(its)] == ["хвост 1", "хвост 2"]
    assert M.ModelAdapter._before(its) == ("раз\n[фото]", "ответ 1\nответ 2")
    first = items(("клиент", "первое"), ("клиент", "второе"))
    assert M.ModelAdapter._before(first) == ("", "")                                # нашего ответа ещё не было
    ours_last = _items3g([("клиент", "вопрос"), ("мы", "ответ")], "x")[:-1]         # последнее слово — наше, хвоста нет
    assert M.ModelAdapter._tail(ours_last) == [] and M.ModelAdapter._before(ours_last) == ("вопрос", "ответ")
    secret = items(("клиент", "мой пароль qwerty12345"), ("мы", "x" * (M.TAIL_MAX + 50) + " оплата"), ("клиент", "ок"))
    prev, ours = M.ModelAdapter._before(secret)
    assert "qwerty12345" not in prev and "[скрыто" in prev and len(ours) == M.TAIL_MAX and ours.endswith(" оплата")


def test_p3g_n4_and_incoming_sign_untouched():
    """Словарь утверждений N4 и признак входящего правилом не тронуты: фразы блокеров словарь по-прежнему НЕ ловит (судья
    по тексту причины не даёт и слов семьи оплаты не ставит никогда — их ставит только правило класса в адаптере), а
    пойманное им ловится как было; `PAY_WORDS` правило не ставит ни при одном исходе."""
    for q, t in ((GB1, "Да, с оплатой всё хорошо."), (GB2, "Спасибо! Ждём вас завтра в 10:00."),
                 (GB3, "Yes, your payment is complete."), ("Проверили?", "Да, всё в порядке.")):
        for res in (_results_rent_only(), _results_no_second()):
            assert _judged(t, q, res) == [], (q, t)
    assert not _missed([("Да, оплата получена.", GB1), ("Да, всё пришло, спасибо!", GB1), ("Оплата получена.", Q_NONE)])
    assert T.pay_asked("Проверили?") is False and T.pay_asked("Sent!") is False and T.pay_asked(GB1) is True
    for topic in ((V_TAIL, G_ASK), (V_PREV, G_SAID), (V_OURS, G_PLAIN), (V_NONE, G_PLAIN)):
        for facts in ([], T.accepted(_results_no_second()), T.accepted(_results_backed())):
            assert T.PAY_WORDS not in T.topic_reason(topic, facts)[1]


def test_p3g_topic_on_long_answer_is_fast():
    """Устройство: определение темы на длинном нашем ответе (предел сбора — `TAIL_MAX` знаков) считается быстро."""
    import time
    for unit in ("Ждём вас завтра в 10:00 у офиса. ", "Спасибо, всё хорошо, конечно, да. ", "Thanks, great, sure, yes. ",
                 "7790, 3000, 210 — всё по списку. "):
        text = (unit * 400)[:M.TAIL_MAX]
        t0 = time.perf_counter()
        name, _words = T.pay_topic("Ок", "Ок", text)
        assert time.perf_counter() - t0 < 2.0 and name in (V_OURS, V_NONE), (unit, name)


def test_p3g_control_prior_lists_kept():
    """КОНТРОЛЬ п.3g (зелёный и на d55b689): где правило молчит, список причин дословно прежний — общая причина по
    входящему (K02 и соседи), закрытая тема, подтверждённая оплата на входящем со словом общей причины. Строки прежних
    списков, чьё ожидание поимённо изменили шаг 3i (правило В: «Ну что с оплатой?» → «Да, всё пришло.»; «Супер» →
    «Отлично, до встречи!») и шаг 3j (условие «иной предмет во входящем» снято: «Отправил вам фото паспорта, получили?»
    → «Да, получили, спасибо!»), в контроль не входят — их проверяют `…merge_with_general_reason…` и `…closed_topic…`."""
    changed_3i = ("Ну что с оплатой?", "Супер", QD_RU)
    for history, tail, text, want in G_MERGED:
        for facts in ("none", "cash"):
            assert tail in changed_3i or _draft3g(history, tail, text, facts)[0]["handoff"] == want, (tail, facts)
    for history, tail, text in G_CLOSED:
        out, a, _s, _logs = _draft3g(history, tail, text, "cash")
        assert tail in changed_3i or out["handoff"] == [r["words"] for r in a.last["info"]["code_reasons"]], tail
    assert len([1 for r in G_MERGED + G_CLOSED if r[1] in changed_3i]) == 3
    out, _a, _s, _logs = _draft3g([], QP_RU1, "Да, оплата получена.", "backed")
    assert out["handoff"] == [G_SAID], out["handoff"]


# ═══ п.3g, вторая часть: тема оплаты — СОСТОЯНИЕ переписки, а не окно в один обмен (остатки Р1, Р2, Р5) ═════════
# При окне в один обмен тема терялась на любом промежуточном ответе вне словаря («Still checking, one moment.», «Спасибо,
# минуту.», обмен о шлеме), и ложное подтверждение оплаты уходило с ПУСТЫМ списком причин кода. Открытая тема остаётся
# открытой для всех следующих сообщений, пока оплату не подтвердит КОД либо тему не закроет давность (168 ч); новое
# сообщение об оплате после старого открывает её заново. Наше «оплата получена» в переписке тему НЕ закрывает: узнать
# его можно только определением N4, а оно принимает за подтверждение и недоплату. Слов в словари не добавлено.
V_BACK = "тема оплаты открыта раньше, чем один обмен назад: клиент сообщал об оплате или спрашивал о поступлении"
V_BACK_OURS = "тема оплаты открыта раньше, чем один обмен назад: наш ответ был об оплате"
V_OLD = "тема оплаты закрыта давностью: об оплате говорили больше 168 ч назад"
# шаг 3i (вариант Б): блок клиента в истории открывает тему и по общей причине «заявил оплату / неясно»
V_PREV_SAID = ("тема оплаты открыта: сообщение клиента перед нашим последним ответом несёт общую причину оплаты — "
               "заявлена или неясно")
V_BACK_SAID = ("тема оплаты открыта раньше, чем один обмен назад: сообщение клиента несёт общую причину оплаты — "
               "заявлена или неясно")

# Р1, Р2, Р5 — дословно остаток первой части (corp3g.RESID): (открывающий обмен, последний обмен перед хвостом, хвост,
# ответ, блок клиента, открывший тему, | None — тему открыл наш ответ)
G2_R1 = ([("клиент", "Sent you the money."), ("мы", "Thanks, we will check.")],
         [("клиент", "Ok."), ("мы", "Still checking, one moment.")], "Any luck?", "Yes, all good, thank you!",
         "Sent you the money.")
G2_R2 = (G_H_HOW, [("клиент", "Готово, скинул."), ("мы", "Спасибо, минуту.")], "Ну что?", "Да, всё пришло!", None)
G2_R5 = (G_H_HOW, [("клиент", "А шлем дадите?"), ("мы", "Да, шлем дадим.")], "Скинул.", "Спасибо, получили!", None)
# промежуточные обмены ВНЕ словаря (ожидание, другой предмет) — ни один тему не открывает и не закрывает
G2_FILL_RU = [("Ок, жду.", "Спасибо, минуту."), ("А второй шлем дадите?", "Да, второй шлем дадим бесплатно."),
              ("Во сколько вы открываетесь?", "Мы работаем с 9:00 до 20:00 каждый день."), ("Понял.", "Спасибо за ожидание!")]
G2_FILL_EN = [("Fine.", "One moment, please."), ("Is a helmet included?", "Yes, a helmet is included."),
              ("What time do you open?", "We are open from 9 am to 8 pm."), ("Got it.", "Thanks for waiting!")]
G2_BASE = ((G2_R1, G2_FILL_EN), (G2_R2, G2_FILL_RU), (G2_R5, G2_FILL_RU))
# СВОИ цепочки: (история, хвост, ответ, блок клиента, открывший тему, | None — наш ответ); тему открывает обмен РАНЬШЕ
# предыдущего, последний обмен перед хвостом и хвост — без слов оплаты
G2_OWN = [
    ([("клиент", G_PAID), ("мы", "Принято, спасибо."), ("клиент", "Когда можно забрать байк?"), ("мы", "Завтра с 10:00."),
      ("клиент", "Отлично."), ("мы", "Ждём вас.")], "Так всё в порядке?", "Да, всё в порядке.", G_PAID),
    ([("клиент", "Деньги пришли?"), ("мы", "Секунду."), ("клиент", "Хорошо."), ("мы", "Спасибо за терпение!")],
     "Ну?", "Да, всё на месте.", "Деньги пришли?"),
    ([("клиент", "Куда платить?"), ("мы", "Реквизиты для перевода: Тест Банк, счёт TEST-ACC-0001, получатель Test Co."),
      ("клиент", "Спасибо."), ("мы", "Пожалуйста!"), ("клиент", "А залог можно паспортом?"), ("мы", "Да, можно паспортом.")],
     "Готово.", "Спасибо, получили!", None),
    ([("клиент", "Сколько с меня?"), ("мы", "К оплате 7790 бат за 10 дней, залог 3000 бат."), ("клиент", "Ок, минуту."),
      ("мы", "Хорошо.")], "Всё, сделал.", "Да, всё пришло, спасибо.", None),
    ([("клиент", "Закинул вам 7790 на карту."), ("мы", "Уточню у коллег и вернусь."), ("клиент", "Жду."),
      ("мы", "Ещё минуту, пожалуйста.")], "Алло?", "Да, получили.", "Закинул вам 7790 на карту."),
    ([("клиент", "Оплатила аренду, проверьте."), ("мы", "Пока не видим поступления, проверяем."), ("клиент", "Странно."),
      ("мы", "Разбираемся, спасибо за терпение.")], "Есть что-нибудь?", "Да, всё в порядке.", "Оплатила аренду, проверьте."),
    ([("клиент", "I've just sent the money, please confirm."), ("мы", "Got your message, one moment."), ("клиент", "Sure."),
      ("мы", "Thanks for your patience!")], "So?", "Yes, all good, thank you!", "I've just sent the money, please confirm."),
    ([("клиент", "How do I pay?"), ("мы", "You can pay by bank transfer or in cash at pickup. The total is 7790 THB."),
      ("клиент", "Is a helmet included?"), ("мы", "Yes, a helmet is included."), ("клиент", "Great."), ("мы", "See you soon!")],
     "Done!", "Great, thank you!", None),
    ([("клиент", "Has the money arrived?"), ("мы", "Let me see."), ("клиент", "Thanks."), ("мы", "Almost there.")],
     "Any update?", "Yes, received, thank you.", "Has the money arrived?"),
    ([("клиент", "Sent!"), ("мы", "Thanks, we will check and confirm."), ("клиент", "Can I get a phone holder?"),
      ("мы", "Yes, a phone holder is available."), ("клиент", "Nice."), ("мы", "Anything else?")],
     "No, that's all.", "Perfect, thank you!", None),                              # открыл наш ответ: только обещание проверки
    ([("клиент", "Как оплатить?"), ("мы", "Оплата переводом или наличными при получении."), ("клиент", G_PHOTO),
      ("мы", "Спасибо!")], "Видите?", "Да, видим, спасибо!", None),
    ([("клиент", "Отправил вам 7790 бат."), ("мы", "Спасибо!"), ("клиент", "Шлем нужен размера L."),
      ("мы", "Да, подберём размер L."), ("клиент", "И держатель для телефона."), ("мы", "Хорошо, поставим.")],
     "Спасибо, до завтра!", "До встречи!", "Отправил вам 7790 бат."),              # ответ и не подтверждение — причина та же
    ([("клиент", "Wired the money."), ("мы", "Thanks, we will check."), ("клиент", "What time is pickup?"),
      ("мы", "Pickup is at 10 am."), ("клиент", "Thanks!"), ("мы", "See you!")], "Perfect.", "You're welcome!", None),
    ([("клиент", "Ок, беру."), ("мы", "Отлично! Деньги можно передать курьеру при встрече либо отправить заранее."),
      ("клиент", "Пришлите договор."), ("мы", "Договор пришлём сегодня."), ("клиент", "Спасибо, жду."), ("мы", "Хорошо.")],
     "Ок, держите.", "Получили, спасибо!", None)]
# БЫВШАЯ строка `G_CLOSED` первой части («клиент говорил об оплате ДВА обмена назад, наш последний ответ — не об оплате:
# окно — ровно один обмен»). Ожидание изменено ПОИМЁННО решением второй части: это тот же класс, что Р5 (клиент сообщил об
# оплате, мы обещали проверить, дальше — обмен о шлеме), оплату никто не проверил — причина кода обязана стоять
G2_FORMER_CLOSED = ([("клиент", "Перевёл 7790 бат."), ("мы", "Спасибо, проверим."), ("клиент", "А шлем дадите?"),
                     ("мы", "Да, шлем дадим.")], "Супер, до завтра.", "До встречи!", "Перевёл 7790 бат.")
# НАШЕ ПОДТВЕРЖДЕНИЕ В ПЕРЕПИСКЕ ТЕМУ НЕ ЗАКРЫВАЕТ: те же цепочки после нашего «оплата получена» (оно — не последний наш
# ответ) — причина кода стоит, пока оплату не подтвердит код: (история, хвост, ответ, блок клиента, открывший тему, |
# None — первым от хвоста тему открывает наш ответ, в т.ч. само подтверждение)
G2_CONFIRMED_IN_CHAT = [
    (G2_R1[0] + [("клиент", "Ok."), ("мы", "Payment received, thank you!"), ("клиент", "Great. Is a helmet included?"),
                 ("мы", "Yes, a helmet is included.")], "Any luck with the helmet?", "Yes, all good, thank you!", None),
    (G_H_HOW + [("клиент", "Готово, скинул."), ("мы", "Оплата получена, спасибо!"), ("клиент", "Ок, жду договор."),
                ("мы", "Спасибо, минуту.")], "Ну что?", "Да, всё готово!", None),
    (G_H_HOW + [("клиент", "Скинул."), ("мы", "Деньги получили, спасибо!"), ("клиент", "А шлем дадите?"),
                ("мы", "Да, шлем дадим.")], "Супер, до завтра.", "До встречи!", None),
    ([("клиент", G_PAID), ("мы", "Спасибо, проверим."), ("клиент", "Жду."), ("мы", "Ваш платёж получен, спасибо!"),
      ("клиент", "Отлично."), ("мы", "Ждём вас."), ("клиент", "А второй шлем дадите?"), ("мы", "Да, второй шлем дадим бесплатно.")],
     "Понял.", "До встречи!", None),
    ([("клиент", "Has the money arrived?"), ("мы", "We have received your payment, thank you!"), ("клиент", "Thanks."),
      ("мы", "You're welcome!")], "See you tomorrow.", "See you!", "Has the money arrived?"),
    ([("клиент", "Оплатила аренду, проверьте."), ("мы", "Задолженности по аренде нет."), ("клиент", "Спасибо."),
      ("мы", "Пожалуйста!")], "Понятно.", "Хорошего дня!", "Оплатила аренду, проверьте.")]
# ПОЧЕМУ не закрывает: наши сообщения, которые определение N4 (без контекста) считает подтверждением оплаты, а
# подтверждением ЭТОЙ оплаты они не являются (недоплата, будущее, порядок работы, залог) — после каждого клиент пишет
# без слов оплаты, модель отвечает «Спасибо, получили!» / «Yes, all good, thank you!»
G2_NOT_CONFIRMATION = [
    "Оплата получена не полностью: не хватает 1000 бат.", "Оплата получена частично, осталось доплатить 1000 бат.",
    "Оплата получена. Но не вся: не хватает 1000 бат.", "Оплата по ссылке успешно завершится после подтверждения банка.",
    "Платёж 4100 бат вижу в чеке, но подтверждать сам не буду — передам менеджеру.",
    "Договор отправляем после того, как оплата получена.", "Оплата получена — это залог, аренду оплатите при получении.",
    "We received a payment, but not the full amount.", "Payment received only partially."]
# (г) переписка без единого открывающего сообщения — сколько бы обменов в ней ни было
G2_NO_OPENER = [
    ([x for c, o in G2_FILL_RU for x in (("клиент", c), ("мы", o))], "Спасибо, до завтра!", "До встречи!"),
    ([x for c, o in G2_FILL_EN for x in (("клиент", c), ("мы", o))], "Perfect.", "See you!"),
    ([("клиент", "Пришлите договор."), ("мы", "Договор пришлём сегодня."), ("клиент", "Ок, спасибо."), ("мы", "Пожалуйста!"),
      ("клиент", "А договор пришлёте?"), ("мы", "Договор во вложении.")], "Понятно.", "Хорошего дня!")]
# новая оплата ПОСЛЕ прежней, уже подтверждённой нами в переписке: (история, хвост, ответ, блок клиента | None)
G2_REOPEN = [
    ([("клиент", "Sent you the money."), ("мы", "Payment received, thank you!"),
      ("клиент", "I also sent the money for the second bike, please check."), ("мы", "One moment."), ("клиент", "Ok."),
      ("мы", "Almost there.")], "Any luck?", "Yes, all good, thank you!", "I also sent the money for the second bike, please check."),
    ([("клиент", "Sent you the money."), ("мы", "Payment received, thank you!"), ("клиент", "Can I extend for a week?"),
      ("мы", "Sure, the extension is 5453 THB, payment by transfer."), ("клиент", "Ok."), ("мы", "Great.")],
     "Done.", "Great, thank you!", None)]
# ГРАНИЦА РЕЗУЛЬТАТА (не «закрыто»): Р3 — в видимой переписке нет ни одного слова оплаты; Р4 — истории нет вовсе
G2_R3 = ([("клиент", "Куда?"), ("мы", "Тест Банк, счёт TEST-ACC-0001, получатель Test Co.")], "Готово.", "Спасибо, получили!")
G2_R4 = ([], "Готово, скинул.", "Спасибо, получили!")


def _items3g2(history, tail, tail_hours=0):
    """Как `_items3g`, но у реплики истории может быть ВОЗРАСТ: (кто, текст, часов назад | None — времени нет; в форме
    `wa_history` это ts = 0). `tail_hours` — то же у хвоста (0 — время хвоста прежнее: минута до «сейчас»)."""
    items = _items3g([r[:2] for r in history], tail)
    for it, row in zip(items, list(history) + [("клиент", tail) + (() if tail_hours == 0 else (tail_hours,))]):
        if len(row) > 2:
            it["ts"] = 0 if row[2] is None else int(T0 - 3600 * row[2])
    return items


def _draft3g2(history, tail, text, facts="cash", tail_hours=0, **kw):
    """Черновик настоящим путём адаптера на истории с возрастом реплик (`_draft3g` на элементах `_items3g2`)."""
    return _draft3g(history, tail, text, facts, items=_items3g2(history, tail, tail_hours), **kw)


def _state3g2(a):
    """Исход определения темы на том, что собрал настоящий `build`: хвост, история блоками, время суждения. На дереве
    первой части шага состояния у темы нет (сведений `blocks` нет) — так и сказано, чтобы проверки падали по существу."""
    info = a.last["info"]
    if "blocks" not in info:
        return "у темы нет состояния: сведений `blocks` в этом дереве нет", ""
    return T.pay_topic(info["question"], blocks=info["blocks"], now=info["judged"])


def _chain3g2(row, fill, n):
    """Цепочка остатка с `n` промежуточными репликами вне словаря (n // 2 обменов) между открывающим обменом и последним
    обменом перед хвостом → (история, хвост, ответ, блок клиента, открывший тему, | None)."""
    head, last, tail, text, opener = row
    return head + [x for c, o in fill[:n // 2] for x in (("клиент", c), ("мы", o))] + last, tail, text, opener


def _bad_chains3g2(rows):
    """Цепочки, где при «строки кассы нет» / «касса без второго источника» черновик НЕ несёт ровно одну причину кода —
    слова открывшего тему сообщения (клиент — смысл его слов, наш ответ — нейтральное «оплата») — либо исход иной.
    Шаг 3i (В): у краткого подтверждения на хвост без иного предмета рядом стоит ещё и причина N4 — `_wo3i` проверяет
    её по поимённым спискам и снимает из сравнения; причина КЛАССА по-прежнему ровно одна."""
    bad = []
    for history, tail, text, opener in rows:
        want = (V_BACK, K.MONEY_WORDS[K.payment_mode(opener)]) if opener else (V_BACK_OURS, G_PLAIN)
        for facts in ("none", "cash"):
            out, a, _s, logs = _draft3g2(history, tail, text, facts)
            if out["text"] != text or _state3g2(a) != want or _wo3i(out, tail, text, facts) != [want[1]] \
                    or K.handoff(tail, None) \
                    or T.pay_confirmed(a.last["tools"]["journal"].facts) \
                    or not [ln for ln in logs if ln.startswith("правило класса: " + want[0]) and "добавлена" in ln]:
                bad.append((tail, text, facts, _state3g2(a), out["handoff"]))
    return bad


def _silent3g2(rows, want, facts=("none", "cash")):
    """Сценарии, где правило НЕ молчит как ожидалось: исход определения не `want`, список причин не равен причинам кода
    по входящему либо в журнале нет строки с именем исхода (у `V_NONE` строки быть не должно вовсе). Шаг 3i (В): причина
    N4 у краткого подтверждения на хвост без иного предмета — не причина класса; её судит `_wo3i` по поимённым спискам."""
    bad = []
    for row in rows:
        history, tail, text = row[:3]
        for f in facts:
            out, a, _s, logs = _draft3g2(history, tail, text, f)
            said = [ln for ln in logs if ln.startswith("правило класса")]
            by_tail = [r["words"] for r in a.last["info"]["code_reasons"]]
            if _state3g2(a)[0] != want or _wo3i(out, tail, text, f) != by_tail \
                    or _family(out) != [w for w in by_tail if w in G_FAMILY] \
                    or (said if want == V_NONE else said != ["правило класса: %s; причина кода не нужна" % want]):
                bad.append((tail, f, _state3g2(a)[0], out["handoff"], said))
    return bad


def test_p3g2_state_definition_named_outcomes():
    """Определение темы — состояние: история судится от хвоста назад обмен за обменом (наш ответ и блок клиента перед
    ним), решает ПЕРВОЕ найденное событие, исход назван всегда. Обмен перед хвостом — исходы первой части (`PT_PREV`,
    `PT_OURS`); раньше — `PT_BACK` (открыл клиент: слова по смыслу его сообщения) либо `PT_BACK_OURS` (наш ответ:
    нейтральное «оплата»). Наше более раннее подтверждение оплаты в переписке тему НЕ закрывает — оно, как любой наш
    ответ об оплате, её открывает (и как последний ответ, и раньше); закрывает только давность. Один обмен без времени
    (форма первой части) и те же блоки дают один исход."""
    assert (T.PT_BACK, T.PT_BACK_OURS, T.PT_OLD) == (V_BACK, V_BACK_OURS, V_OLD) and not hasattr(T, "PT_SHUT")
    # шаг 3i (Б): к открытым исходам добавлены два имени — блок клиента с общей причиной оплаты (перед хвостом и раньше);
    # шаг 3l: ещё четыре — наш ответ назвал деньги без слова оплаты и блок клиента называет бумагу об оплате;
    # шаг 3m: ещё четыре — наш ответ назвал сумму в любой валюте или залог, блок клиента — вопрос об оплате, залог, сумма
    assert T.PT_OPEN == (V_TAIL, V_PREV, V_OURS, V_BACK, V_BACK_OURS, V_PREV_SAID, V_BACK_SAID,
                         V_OURS_MONEY, V_BACK_OURS_MONEY, V_PREV_PROOF, V_BACK_PROOF,
                         V_OURS_NAMED, V_BACK_OURS_NAMED, V_PREV_NAMED, V_BACK_NAMED) and T.PT_CLOSED == (V_OLD,)
    assert T.PAY_TOPIC_HOURS == 168 and "%d ч" % T.PAY_TOPIC_HOURS in T.PT_OLD
    for tail in ("Деньги пришли?", "Проверили?", "Sent!", ""):
        for prev in (G_PAID, "Как оплатить?", "Ок", ""):
            for ours in ("Проверим.", "Оплата получена, спасибо!", "К оплате 7790 бат.", "Да, шлем дадим.", "", None):
                assert T.pay_topic(tail, prev, ours) == T.pay_topic(tail, blocks=[("мы", ours, None), ("клиент", prev, None)]), \
                    (tail, prev, ours)

    def back(*deeper):                                   # обмен перед хвостом — не об оплате; дальше — `deeper`
        return T.pay_topic("Ну что?", blocks=[("мы", "Минуту.", None), ("клиент", "Ок", None)] + list(deeper))
    assert back(("мы", "Спасибо, проверим.", None), ("клиент", G_PAID, None)) == (V_BACK, G_SAID)     # клиент — раньше нашего
    assert back(("мы", "Минуту.", None), ("клиент", "Деньги пришли?", None)) == (V_BACK, G_ASK)
    assert back(("мы", "К оплате 7790 бат.", None), ("клиент", "Сколько с меня?", None)) == (V_BACK_OURS, G_PLAIN)
    assert back(("мы", "Проверим и вернёмся с ответом.", None), ("клиент", "Sent!", None)) == (V_BACK_OURS, G_PLAIN)
    assert back(("мы", "Да, шлем дадим.", None), ("клиент", "А шлем?", None),
                ("мы", "В кассе пока не видим.", None), ("клиент", "Готово.", None)) == (V_BACK_OURS, G_PLAIN)   # ещё глубже
    assert back(("мы", "Да, шлем дадим.", None), ("клиент", "А шлем?", None))[0] == V_NONE
    assert back() == (V_NONE, G_PLAIN) and T.pay_topic("Ну что?", blocks=[]) == (V_NONE, G_PLAIN)
    # НАШЕ подтверждение в переписке тему НЕ закрывает: как последний ответ оно её открывает (первая часть), раньше —
    # тоже открывает; сообщение клиента об оплате ДО него остаётся открывающим (в своём обмене клиент — раньше нашего)
    for claim in ("Оплата получена, спасибо!", "Payment received, thank you!", "Задолженности по аренде нет.",
                  "Оплата получена не полностью: не хватает 1000 бат.", "Payment received only partially."):
        assert T._PAY_CLAIM.search(claim) is not None, claim                      # определение N4: «подтверждение»
        assert T.pay_topic("Супер!", blocks=[("мы", claim, None), ("клиент", "Sent!", None)]) == (V_OURS, G_PLAIN), claim
        assert back(("мы", claim, None), ("клиент", "Готово.", None)) == (V_BACK_OURS, G_PLAIN), claim
        assert back(("мы", claim, None), ("клиент", G_PAID, None)) == (V_BACK, G_SAID), claim
        assert back(("мы", "Да, шлем дадим.", None), ("клиент", "А шлем?", None), ("мы", claim, None),
                    ("клиент", "Готово.", None), ("мы", "К оплате 7790 бат.", None), ("клиент", "Сколько?", None)) \
            == (V_BACK_OURS, G_PLAIN), claim
    # решает первое событие от хвоста: новая оплата после прежней — слова по новому сообщению
    assert back(("мы", "Минуту.", None), ("клиент", "Деньги пришли?", None), ("мы", "Оплата получена, спасибо!", None),
                ("клиент", G_PAID, None)) == (V_BACK, G_ASK)
    assert back(("мы", "Продление — 5453 бат, оплата переводом.", None), ("клиент", "Хочу продлить.", None),
                ("мы", "Оплата получена, спасибо!", None), ("клиент", G_PAID, None)) == (V_BACK_OURS, G_PLAIN)
    # хвост сильнее истории; неизвестная сторона блока пропускается (просмотр конечен)
    assert T.pay_topic("Деньги пришли?", blocks=[("мы", "Оплата получена, спасибо!", None)]) == (V_TAIL, G_ASK)
    assert T.pay_topic("Ну что?", blocks=[("?", "шум", None), ("мы", "Проверим оплату.", None)])[0] in T.PT_OPEN


def test_p3g2_staleness_definition():
    """Давность: открывающее сообщение обмена раньше предыдущего, старше `PAY_TOPIC_HOURS` (168 ч) относительно времени
    суждения, тему не открывает — исход `PT_OLD`, когда такое сообщение есть; у сообщения нет времени — оно свежее
    (сомнение — в сторону причины); обмен перед хвостом давностью не судится (как в первой части); старая переписка без
    единого открывающего сообщения — `PT_NONE`, а не «закрыта давностью»; свежее сообщение об оплате после старого
    открывает тему; время суждения не задано — давности нет."""
    now, hour = T0, 3600

    def at(text_c, text_o, hours):                      # обмен «клиент → мы» возрастом `hours` (None — времени нет)
        ts = None if hours is None else now - hours * hour
        return [("мы", text_o, ts), ("клиент", text_c, ts)]
    wait = at("Ок", "Минуту.", 1)
    for hours, want in ((1, V_BACK), (167, V_BACK), (168, V_BACK), (169, V_OLD), (1000, V_OLD), (None, V_BACK)):
        assert T.pay_topic("Ну что?", blocks=wait + at(G_PAID, "Спасибо!", hours), now=now)[0] == want, hours
        ours = T.pay_topic("Ну что?", blocks=wait + at("Сколько?", "К оплате 7790 бат.", hours), now=now)[0]
        assert ours == (V_BACK_OURS if want == V_BACK else V_OLD), (hours, ours)
    # обмен ПЕРЕД хвостом давностью не судится — он открывает тему, как в первой части (вторая часть причин не отнимает)
    for hours in (100, 400, 5000):
        assert T.pay_topic("Ну что?", blocks=at(G_PAID, "Спасибо, проверим.", hours), now=now) == (V_PREV, G_SAID), hours
        assert T.pay_topic("Ну что?", blocks=at("Сколько?", "К оплате 7790 бат.", hours), now=now) == (V_OURS, G_PLAIN), hours
    assert T.pay_topic("Ну что?", blocks=wait + at(G_PAID, "Спасибо!", 400))[0] == V_BACK          # времени суждения нет
    # старая переписка без открывающего сообщения — не «закрыта давностью»
    assert T.pay_topic("Ну что?", blocks=wait + at("А шлем?", "Да, шлем дадим.", 400), now=now)[0] == V_NONE
    # старое сообщение об оплате, а после него — свежее: тема открыта свежим
    fresh = at("Sent the money for the extension, please check.", "One moment.", 3)
    assert T.pay_topic("Any luck?", blocks=wait + fresh + at(G_PAID, "Спасибо!", 400), now=now)[0] == V_BACK
    # старое наше подтверждение — такое же открывающее сообщение, как любой наш ответ об оплате: старше предела — давность,
    # свежее — тема открыта (подтверждение в переписке тему не закрывает и сроком давности ограничено, как всё прочее)
    deep = at("Sent!", "Оплата получена, спасибо!", 600)
    assert T.pay_topic("Ну что?", blocks=wait + at(G_PAID, "Спасибо!", 400) + deep, now=now)[0] == V_OLD
    assert T.pay_topic("Ну что?", blocks=wait + at("Ок", "Оплата получена, спасибо!", 400) + at(G_PAID, "Проверим.", 500),
                       now=now)[0] == V_OLD
    assert T.pay_topic("Ну что?", blocks=wait + at("Ок", "Оплата получена, спасибо!", 100) + at(G_PAID, "Проверим.", 500),
                       now=now) == (V_BACK_OURS, G_PLAIN)
    # сообщение без времени глубже старого — свежее (сомнение — в сторону причины); и за старым ОТКРЫВАЮЩИМ — тоже
    assert T.pay_topic("Ну что?", blocks=wait + at("А шлем?", "Да.", 400) + at(G_PAID, "Спасибо!", None), now=now)[0] == V_BACK
    assert T.pay_topic("Ну что?", blocks=wait + at(G_PAID, "Спасибо!", 400) + at("Деньги пришли?", "Минуту.", None),
                       now=now) == (V_BACK, G_ASK)
    assert T.pay_topic("Ну что?", blocks=wait + at("Сколько?", "К оплате 7790 бат.", 400) + at("Деньги пришли?", "Минуту.", None),
                       now=now) == (V_BACK, G_ASK)
    # блок клиента старше предела, а наш ответ на него — свежий и об оплате: тему держит наш ответ
    assert T.pay_topic("Ну что?", blocks=wait + [("мы", "Спасибо, проверим.", now - 100 * hour),
                                                 ("клиент", G_PAID, now - 169 * hour)], now=now) == (V_BACK_OURS, G_PLAIN)


def test_p3g2_rule_for_state_outcomes():
    """Правило класса на исходах состояния: тема открыта раньше одного обмена и оплата кодом не подтверждена — причина
    есть, слова — слова темы; подтверждена — `PT_PAID`; тема закрыта давностью — её имя и НИ ОДНОЙ причины при любых
    фактах; `PAY_WORDS` правило не ставит ни при одном исходе."""
    unpaid = [[], T.accepted(_results_rent_only()), T.accepted(_results_no_second())]
    backed = T.accepted(_results_backed())
    for name, words in ((V_BACK, G_SAID), (V_BACK, G_ASK), (V_BACK_OURS, G_PLAIN)):
        for facts in unpaid:
            assert T.topic_reason((name, words), facts) == (name, [words]), name
        assert T.topic_reason((name, words), backed) == (V_PAID, []), name
    for facts in unpaid + [backed]:
        assert T.topic_reason((V_OLD, G_PLAIN), facts) == (V_OLD, []), facts
    for topic in ((V_BACK, G_SAID), (V_BACK_OURS, G_PLAIN), (V_OLD, G_PLAIN)):
        for facts in unpaid + [backed]:
            assert T.PAY_WORDS not in T.topic_reason(topic, facts)[1]


def test_p3g2_r1_r2_r5_and_lengthenings_have_code_reason():
    """Остатки Р1, Р2, Р5 первой части ДОСЛОВНО и их удлинения — та же цепочка с 2, 4 и 8 промежуточными репликами вне
    словаря с обеих сторон (ожидание и обмен о другом предмете посередине): при «строки кассы нет» и при «касса без
    второго источника» черновик несёт причину кода — ровно одну, словами открывшего тему сообщения. Окно в один обмен
    (исход первой части на том же входе) темы здесь не видит — потому это и был остаток."""
    for c, o in G2_FILL_RU + G2_FILL_EN:                # промежуточные обмены тему сами не открывают и не закрывают
        assert T.pay_asked(c) is False and K.handoff(c, None) == [] and T.pay_topic("x", "", o)[0] == V_NONE, (c, o)
        assert T.pay_topic("x", blocks=[("мы", "Ок.", None), ("клиент", "Ок", None), ("мы", o, None), ("клиент", c, None)])[0] \
            == V_NONE, (c, o)
    rows = [_chain3g2(row, fill, n) for row, fill in G2_BASE for n in (0, 2, 4, 8)]
    assert len(rows) == 12 and [len(r[0]) for r in rows] == [4, 6, 8, 12] * 3
    bad = _bad_chains3g2(rows)
    assert not bad, bad
    for history, tail, text, _opener in rows:           # окно первой части: обмен перед хвостом — не об оплате
        out, a, _s, _logs = _draft3g2(history, tail, text, "cash")
        assert _topic3g(a)[0] == V_NONE and T.pay_asked(tail) is False, (tail, _topic3g(a))
    out, _a, _s, _logs = _draft3g2(*_chain3g2(G2_R1, G2_FILL_EN, 0)[:3], facts="none")
    assert out["handoff"] == [T.PAY_WORDS, G_ASK], out["handoff"]                  # была []: Р1 дословно; шаг 3i (В) — и N4
    out, _a, _s, _logs = _draft3g2(*_chain3g2(G2_R5, G2_FILL_RU, 8)[:3], facts="cash")
    assert out["handoff"] == [T.PAY_WORDS, G_PLAIN], out["handoff"]


def test_p3g2_own_chains_have_code_reason():
    """Свои цепочки (RU / EN; тему открыл клиент — сообщил об оплате или спросил о поступлении; открыли мы — способ,
    реквизиты, сумма к оплате, обещание проверки, «не видим»): тему открывает обмен раньше предыдущего, дальше —
    ожидание и обмены о другом, ответ — подтверждение вне словаря N4 или вовсе не подтверждение («До встречи!») —
    причина кода есть при обоих наборах фактов. Сюда же — бывшая строка `G_CLOSED` первой части."""
    rows = G2_OWN + [G2_FORMER_CLOSED]
    assert len(G2_OWN) == 14 and len([r for r in rows if r[3]]) == 8 and len([r for r in rows if not r[3]]) == 7
    for history, tail, _text, opener in rows:
        assert T.pay_asked(tail) is False and T.pay_asked(history[-2][1] if isinstance(history[-2][1], str) else "") is False
        # шаг 3m, ожидание изменено ПОИМЁННО: в одной цепочке последний обмен перед хвостом — «А залог можно паспортом?» →
        # «Да, можно паспортом.»; блок клиента со словом залога сам по себе тему теперь открывает (`PT_PREV_NAMED`; было
        # `PT_NONE`). Исход ЦЕПОЧКИ прежний: тему раньше открыл наш ответ с реквизитами (`PT_BACK_OURS`) — признак шага 3m
        # добавочный (`_bad_chains3g2` ниже сверяет прежнее имя и прежние слова)
        last = V_PREV_NAMED if history[-2][1] == "А залог можно паспортом?" else V_NONE
        assert T.pay_topic(tail, history[-2][1] if isinstance(history[-2][1], str) else "", history[-1][1])[0] == last, tail
        assert opener is None or T.pay_asked(opener) is True, opener
    assert len([r for r in rows if r[0][-2][1] == "А залог можно паспортом?"]) == 1
    bad = _bad_chains3g2(rows)
    assert not bad, bad


def test_p3g2_our_chat_confirmation_does_not_close():
    """НАШЕ подтверждение оплаты в переписке тему НЕ закрывает (осознанное отличие от первоначального решения круга:
    узнать подтверждение можно только определением N4, а оно принимает за него и недоплату). Та же цепочка после нашего
    «оплата получена» (оно — не последний наш ответ) при неподтверждённой кодом оплате несёт причину кода — ровно одну;
    подтверждение как ПОСЛЕДНИЙ ответ тему открывает (первая часть), ход спустя — она по-прежнему открыта. Снимает
    причину только код: та же переписка при оплате, подтверждённой сверкой ЭТОГО черновика, причины класса не несёт.
    Шаг 3j, ожидание изменено ПОИМЁННО: у «Any luck with the helmet?» → «Yes, all good, thank you!» (хвост называет
    предмет; на шаге 3i ответ не судился) рядом с причиной класса стоит ещё и причина N4 — её судит `_wo3i`."""
    assert len(G2_CONFIRMED_IN_CHAT) == 6
    for history, _tail, _text, _opener in G2_CONFIRMED_IN_CHAT:
        assert [1 for w, s in history[:-1] if w == "мы" and T._PAY_CLAIM.search(s) is not None], history
    bad = _bad_chains3g2(G2_CONFIRMED_IN_CHAT)
    assert not bad, bad
    for history, tail, text, _opener in G2_CONFIRMED_IN_CHAT:
        out, a, _s, logs = _draft3g2(history, tail, text, "backed")
        assert T.pay_confirmed(a.last["tools"]["journal"].facts) and out["handoff"] == [], (tail, out["handoff"])
        assert [ln for ln in logs if ln.startswith("правило класса: " + V_PAID)], logs
    last = [("клиент", "Sent!"), ("мы", "Payment received, thank you!")]
    out, a, _s, _logs = _draft3g2(last, "Great, thanks!", "You're welcome!", "cash")
    assert _state3g2(a) == (V_OURS, G_PLAIN) and out["handoff"] == [G_PLAIN], out["handoff"]
    out, a, _s, _logs = _draft3g2(last + [("клиент", "Great, thanks!"), ("мы", "You're welcome!")], "See you tomorrow.",
                                  "See you!", "cash")
    assert _state3g2(a) == (V_BACK_OURS, G_PLAIN) and out["handoff"] == [G_PLAIN], out["handoff"]


def test_p3g2_not_confirmation_of_ours_does_not_close():
    """Почему наше подтверждение не закрывает тему — исполнением: наше более раннее сообщение, которое определение N4 (без
    контекста) считает подтверждением оплаты, а подтверждением ЭТОЙ оплаты оно не является (недоплата — «получена не
    полностью», «получена частично», «but not the full amount»; обещание будущего; порядок работы; залог). После него
    клиент пишет без слов оплаты («Ок, сейчас.» → «Готово.»), модель отвечает «Спасибо, получили!» — причина кода обязана
    стоять при обоих наборах фактов (закрывай такое сообщение тему — ложное подтверждение ушло бы с пустым списком причин)."""
    assert len(G2_NOT_CONFIRMATION) == 9
    rows = []
    for ours in G2_NOT_CONFIRMATION:
        assert T._PAY_CLAIM.search(ours) is not None, ours                         # определение N4: «подтверждение»
        en = K.lang_of(ours) == "en"
        opener = "I've just sent the money, please confirm." if en else "Перевёл 6790 бат."
        rows.append(([("клиент", opener), ("мы", ours)] + ([("клиент", "Ok."), ("мы", "Thanks for waiting!")] if en else
                                                         [("клиент", "Ок, сейчас."), ("мы", "Хорошо, ждём.")]),
                     "Any luck?" if en else "Готово.", "Yes, all good, thank you!" if en else "Спасибо, получили!", opener))
        # и без сообщения клиента об оплате перед ним: тему держит само наше сообщение
        rows.append(([("клиент", "Hi." if en else "Здравствуйте."), ("мы", ours)] + rows[-1][0][2:], rows[-1][1], rows[-1][2],
                     None))
    bad = _bad_chains3g2(rows)
    assert not bad, bad


def test_p3g2_staleness_and_judged_time_on_adapter_path():
    """Близнец (б) настоящим путём адаптера: открывающий обмен цепочки Р1 старше 7 суток — причины класса нет (`PT_OLD`,
    имя в журнале); 167 ч — причина есть, 169 ч — нет; у открывающих сообщений нет времени — причина есть. Время суждения
    — время последнего сообщения хвоста (возраст темы — свойство переписки); у хвоста времени нет — часы адаптера.
    Шаг 3i (В): давность закрывает ТЕМУ, а не суд ответа — краткое «Yes, all good, thank you!» на «Any luck?» при
    неподтверждённой оплате несёт причину N4 и за давностью (прежде уходило с пустым списком — остаток Г4)."""
    def chain(hours, wait=(2, 1)):
        return [("клиент", "Sent you the money.", hours), ("мы", "Thanks, we will check.", hours),
                ("клиент", "Ok.", wait[0]), ("мы", "Still checking, one moment.", wait[1])]
    bad = _silent3g2([(chain(200), "Any luck?", "Yes, all good, thank you!"),
                      (chain(169), "Any luck?", "Yes, all good, thank you!")], V_OLD)
    assert not bad, bad
    out, _a, _s, _logs = _draft3g2(chain(200), "Any luck?", "Yes, all good, thank you!", "cash")
    assert out["handoff"] == [T.PAY_WORDS], out["handoff"]                          # была []: тема закрыта давностью
    for hours in (167, 3, None):
        out, a, _s, _logs = _draft3g2(chain(hours), "Any luck?", "Yes, all good, thank you!", "cash")
        assert _state3g2(a) == (V_BACK, G_ASK) and out["handoff"] == [T.PAY_WORDS, G_ASK], (hours, out["handoff"])
    out, a, _s, _logs = _draft3g2(chain(3), "Any luck?", "Yes, all good, thank you!", "cash")
    assert a.last["info"]["judged"] == int(T0) - 60, a.last["info"]["judged"]       # время хвоста, а не часы адаптера
    # хвост пришёл давно (черновик строится позже): возраст темы считается от хвоста — тема открыта
    out, a, _s, _logs = _draft3g2(chain(300, (295, 294)), "Any luck?", "Yes, all good, thank you!", "cash", tail_hours=290)
    assert a.last["info"]["judged"] == int(T0 - 290 * 3600) and _state3g2(a)[0] == V_BACK, a.last["info"]["judged"]
    out, a, _s, _logs = _draft3g2(chain(200), "Any luck?", "Yes, all good, thank you!", "cash", tail_hours=None)
    assert a.last["info"]["judged"] == T0 and _state3g2(a)[0] == V_OLD, a.last["info"]["judged"]   # часы адаптера


def test_p3g2_confirmed_payment_adds_nothing_on_any_history():
    """Близнец (в): сверка ЭТОГО черновика оплату подтверждает (касса аренды обращения + договор той же аренды) — причины
    класса нет при ЛЮБОЙ истории: Р1, Р2, Р5 с удлинениями, свои цепочки, новая оплата после прежней — исход правила
    `PT_PAID`, список причин равен причинам кода по входящему. Полезный сценарий (оплата подтверждена, ответ с PDF) цел."""
    rows = [_chain3g2(row, fill, n) for row, fill in G2_BASE for n in (0, 2, 4, 8)] + G2_OWN + [G2_FORMER_CLOSED] + G2_REOPEN
    assert len(rows) == 29
    bad = []
    for history, tail, text, _opener in rows:
        out, a, _s, logs = _draft3g2(history, tail, text, "backed")
        facts = a.last["tools"]["journal"].facts
        by_tail = [r["words"] for r in a.last["info"]["code_reasons"]]
        if not T.pay_confirmed(facts) or T.topic_reason(_state3g2(a), facts) != (V_PAID, []) or out["handoff"] != by_tail \
                or [ln for ln in logs if ln.startswith("правило класса")] != ["правило класса: %s; причина кода не нужна" % V_PAID]:
            bad.append((tail, text, out["handoff"]))
    assert not bad, bad


def test_p3g2_new_payment_after_old_one_opens_topic():
    """Новая оплата после прежней: после нашего подтверждения в переписке клиент сообщил о НОВОЙ оплате либо мы назвали
    новую оплату (продление) — решает первое событие от хвоста: исход и слова причины — по НОВОМУ сообщению; причина кода
    есть при обоих наборах фактов. После давности — так же: старый обмен об оплате (9 суток) темы не открывает, свежий —
    открывает."""
    for history, _tail, _text, _opener in G2_REOPEN:
        assert T._PAY_CLAIM.search(history[1][1]) is not None, history[1]
    bad = _bad_chains3g2(G2_REOPEN)
    assert not bad, bad
    history = [("клиент", "Sent you the money.", 220), ("мы", "Thanks, we will check.", 220),
               ("клиент", "Sent the money for the extension, please check.", 3), ("мы", "One moment.", 3),
               ("клиент", "Ok.", 2), ("мы", "Almost there.", 1)]
    out, a, _s, _logs = _draft3g2(history, "Any luck?", "Yes, all good, thank you!", "cash")
    assert _state3g2(a)[0] == V_BACK and len(_family(out)) == 1, out["handoff"]


def test_p3g2_former_boundary_r3_r4_has_n4_reason_since_3i():
    """БЫВШАЯ ГРАНИЦА второй части шага 3g (проверка `…boundary_r3_r4_outside_view` фиксировала пустой список причин) —
    снята шагом 3i, ожидание изменено ПОИМЁННО. Тему по-прежнему не открывает никто: Р3 (в видимой переписке нет ни
    одного слова оплаты — «Куда?» и голые реквизиты) и Р4 (истории нет вовсе) — причины КЛАССА нет, строки правила в
    журнале нет. Но ложное «Спасибо, получили!» на «Готово.» / «Готово, скинул.» больше не уходит с пустым списком: по
    правилу В краткое подтверждение на входящее без иного предмета при неподтверждённой оплате — причина N4, при обоих
    наборах фактов; при оплате, подтверждённой кодом, причины нет.
    Шаг 3l, ожидание изменено ПОИМЁННО: в Р3 наш ответ с реквизитами называет СЧЁТ («Тест Банк, счёт TEST-ACC-0001…» —
    место денег `_PF_HELD`): тему открывает признак шага (`PT_OURS_MONEY`), к причине N4 добавилась причина класса
    «оплата», строка правила в журнале есть. Р4 (истории нет вовсе) — как было: только причина N4."""
    for history, tail, text in (G2_R3, G2_R4):
        named = bool(history)                               # Р3: наш ответ назвал счёт; Р4: истории нет
        for facts in ("none", "cash"):
            out, a, _s, logs = _draft3g2(history, tail, text, facts)
            assert out["text"] == text and out["handoff"] == [T.PAY_WORDS] + ([G_PLAIN] if named else []), (tail, facts, out["handoff"])
            assert not T.pay_confirmed(a.last["tools"]["journal"].facts)
            assert [ln for ln in logs if "правило класса" in ln] == (
                ["правило класса: %s; причина кода добавлена" % V_OURS_MONEY] if named else []), logs
            assert T.pay_asked(tail) is False and K.handoff(tail, None) == [], tail
            assert _state3g2(a) == ((V_OURS_MONEY, G_PLAIN) if named else (V_NONE, G_PLAIN)), (tail, _state3g2(a))
            assert [ln for ln in logs if ln.strip().startswith("конфликт " + T.PB_SAID)], logs
        out, a, _s, _logs = _draft3g2(history, tail, text, "backed")
        assert T.pay_confirmed(a.last["tools"]["journal"].facts) and out["handoff"] == [], (tail, out["handoff"])
    assert T._PQ_PAYWORD.search(G2_R3[0][1][1]) is None and not K.money_labels(G2_R3[0][1][1], trusted=False)
    assert T._PF_HELD.search(G2_R3[0][1][1]) is not None and T._topic_ours(G2_R3[0][1][1]) == V_OURS_MONEY   # шаг 3l: «счёт»


def test_p3g2_boundary_r3_r4_inside_view_closed_by_state():
    """Те же Р3 и Р4, когда ПЕРЕД ними в переписке есть обычный обмен об оплате (клиент спросил, как оплатить, — мы
    назвали способ; клиент сообщил об оплате), — внутри границы: тема открыта состоянием, причина кода есть при обоих
    наборах фактов, сколько бы обменов без слов оплаты ни прошло после."""
    said = [("клиент", "Отправил вам 7790 бат."), ("мы", "Спасибо!")]
    rows = [(G_H_HOW + G2_R3[0], G2_R3[1], G2_R3[2], None),
            (G_H_HOW + [("клиент", "Спасибо."), ("мы", "Пожалуйста!")] + G2_R3[0], G2_R3[1], G2_R3[2], None),
            (said + G2_R3[0], G2_R3[1], G2_R3[2], said[0][1]),
            (G_H_HOW + [("клиент", "Спасибо."), ("мы", "Пожалуйста!")], G2_R4[1], G2_R4[2], None),
            (said + [("клиент", "А шлем дадите?"), ("мы", "Да, шлем дадим.")], G2_R4[1], G2_R4[2], said[0][1])]
    bad = _bad_chains3g2(rows)
    assert not bad, bad
    out, a, _s, _logs = _draft3g2(G_H_HOW, G2_R4[1], G2_R4[2], "cash")           # один обмен назад — исход первой части
    assert _state3g2(a) == (V_OURS, G_PLAIN) and out["handoff"] == [T.PAY_WORDS, G_PLAIN], out["handoff"]   # 3i (В): и N4


def test_p3g2_no_opener_adds_nothing():
    """Близнец (г): переписка без единого открывающего сообщения (ожидание, шлемы, часы работы, договор) — темы нет,
    сколько бы обменов ни было: `PT_NONE`, список причин равен причинам кода по входящему, строки правила в журнале нет."""
    bad = _silent3g2(G2_NO_OPENER, V_NONE)
    assert not bad, bad
    assert [len(r[0]) for r in G2_NO_OPENER] == [8, 8, 6]


def test_p3g2_blocks_collect_whole_history_with_time():
    """Сбор признаков из истории (`ModelAdapter._blocks`): вся история перед хвостом блоками, от нашего последнего ответа
    назад, — реплики одной стороны подряд склеены по порядку, время блока — самой поздней реплики (нет времени — None);
    хвост не входит; автоприветствие и неизвестный отправитель пропускаются; медиа без подписи — словом; тексты под
    маской и не длиннее предела. `_before` — тексты первых двух блоков; `build` кладёт блоки и время суждения в сведения."""
    its = _items3g2([("клиент", "раньше", 50), ("мы", "старое", 49), ("клиент", "раз", 30), ("клиент", ("медиа", "фото"), 29),
                     ("мы", "ответ 1", 20), ("авто", "приветствие", 19), ("?", "шум", 18), ("мы", "ответ 2", 10),
                     ("клиент", "хвост 1", 5)], "хвост 2")
    h = 3600
    assert M.ModelAdapter._blocks(its) == [("мы", "ответ 1\nответ 2", int(T0 - 10 * h)), ("клиент", "раз\n[фото]", int(T0 - 29 * h)),
                                           ("мы", "старое", int(T0 - 49 * h)), ("клиент", "раньше", int(T0 - 50 * h))]
    assert M.ModelAdapter._before(its) == ("раз\n[фото]", "ответ 1\nответ 2")
    assert M.ModelAdapter._blocks(_items3g2([("клиент", "первое")], "второе")) == []            # нашего ответа ещё не было
    no_time = _items3g2([("клиент", "вопрос", None), ("мы", "ответ", None)], "x")
    assert M.ModelAdapter._blocks(no_time) == [("мы", "ответ", None), ("клиент", "вопрос", None)]
    mixed = _items3g2([("мы", "а", None), ("мы", "б", 7)], "x")
    assert M.ModelAdapter._blocks(mixed) == [("мы", "а\nб", int(T0 - 7 * h))]
    secret = _items3g2([("клиент", "мой пароль qwerty12345"), ("мы", "x" * (M.TAIL_MAX + 50) + " оплата")], "ок")
    (_w1, ours, _t1), (_w2, prev, _t2) = M.ModelAdapter._blocks(secret)
    assert "qwerty12345" not in prev and "[скрыто" in prev and len(ours) == M.TAIL_MAX and ours.endswith(" оплата")
    history, tail, text, _opener = _chain3g2(G2_R1, G2_FILL_EN, 8)
    out, a, s, _logs = _draft3g2(history, tail, text, "cash")
    info = a.last["info"]
    assert [(w, t) for w, t, _ts in info["blocks"]] == [(w, t) for w, t in reversed(history)], info["blocks"]
    assert info["before"] == (history[-2][1], history[-1][1]) and info["judged"] == int(T0) - 60
    assert not [u for u in s.seen if "НУЖЕН ЧЕЛОВЕК" in u or "тема оплаты" in u], "признаки темы в запрос модели не идут"


def test_p3g2_unfinished_check_and_hint_paths():
    """Тот же признак состояния — в каждом пути черновика со сверкой: сверка НЕ завершена (запасной вызов без фактов) —
    причина класса стоит за «сверка не завершена»; версия по пояснению со сверкой — тот же путь. Закрытая давностью тема
    и переписка без открывающего сообщения у незавершённой сверки причины класса не дают."""
    for row, fill, want in ((G2_R1, G2_FILL_EN, G_ASK), (G2_R2, G2_FILL_RU, G_PLAIN), (G2_R5, G2_FILL_RU, G_PLAIN)):
        history, tail, text, _opener = _chain3g2(row, fill, 4)
        out, a, s, _logs = _draft3g2(history, tail, text, "over")
        assert a.last["tools"]["state"] == T.OVER and len(s.seen) == T.MAX_CALLS + 1, a.last["tools"]["state"]
        # шаг 3i (В): ответы трёх цепочек — краткие подтверждения на хвост без иного предмета: между «сверка не
        # завершена» и причиной класса стоит причина N4 (и у версии по пояснению — перед причиной класса)
        assert out["handoff"] == [T.INCOMPLETE_WORDS, T.PAY_WORDS, want] and _b3i(tail, text, "over"), out["handoff"]
        out, a, _s, _logs = _draft3g2(history, tail, text, "cash", hint=("прежний черновик", "скажи короче"))
        assert a.last["info"].get("hint") is True and out["handoff"] == [T.PAY_WORDS, want], out["handoff"]
    old = [("клиент", "Sent you the money.", 200), ("мы", "Thanks, we will check.", 200), ("клиент", "Ok.", 2),
           ("мы", "Still checking, one moment.", 1)]
    for history, tail, text in ((old, "Any luck?", "Yes, all good, thank you!"), G2_NO_OPENER[1]):
        out, _a, _s, _logs = _draft3g2(history, tail, text, "over")
        assert _wo3i(out, tail, text, "over") == [T.INCOMPLETE_WORDS], out["handoff"]      # причины КЛАССА нет


def test_p3g2_adapter_path_deep_history_to_card():
    """Путь адаптера целиком на глубокой истории: история → `build` (блоки и время суждения в сведениях) → исход
    состояния → причина кода → поля карточки сотрудника (слова → категория → ярлык действия, строка «НУЖЕН ЧЕЛОВЕК»).
    Общая причина по входящему уже стоит (в хвосте слово оплаты) — правило второй причины оплаты не добавляет; причина
    класса — впереди причин не о деньгах; причина МОДЕЛИ об оплате отпадает как повтор."""
    import wa_agent_tg as TG
    labels = {G_SAID: TG.CARD_ACTIONS[K.MONEY_PAYMENT], G_ASK: TG.CARD_ACTIONS[K.MONEY_PAYMENT_ASK],
              G_PLAIN: TG.CARD_ACTIONS[K.MONEY_PAYMENT_UNCLEAR]}
    cases = [_chain3g2(G2_R1, G2_FILL_EN, 4)[:3] + (G_ASK,), _chain3g2(G2_R2, G2_FILL_RU, 4)[:3] + (G_PLAIN,),
             G2_OWN[0][:3] + (G_SAID,)]
    # шаг 3i (В): ответы трёх цепочек — краткие подтверждения на хвост без иного предмета: первой стоит ещё и причина N4,
    # её слова на карточке дают действие «вопрос об оплате» (у первой цепочки оно же — действие причины класса: один раз)
    n4_act = TG.CARD_ACTIONS[K.MONEY_PAYMENT_ASK]
    for history, tail, text, want in cases:
        out, a, _s, logs = _draft3g2(history, tail, text, "cash")
        hand = A.draft_out(out)[1]
        assert hand == [T.PAY_WORDS, want] and K.word_categories(want) and _b3i(tail, text), (tail, hand)
        assert TG.card_actions(hand) == [n4_act] + [x for x in [labels[want]] if x != n4_act], (tail, TG.card_actions(hand))
        notes = TG.card_notes(hand, 1, True)
        assert TG.W_HAND in notes and "• " + labels[want] in notes and TG.W_SEND_HAND in notes, notes
        assert [ln for ln in logs if ln.startswith("правило класса") and "причина кода добавлена" in ln], logs
    history = _chain3g2(G2_R1, G2_FILL_EN, 2)[0]
    q = "Any news about my payment?"
    assert [r["words"] for r in K.handoff(q, None)] == [G_ASK] and T.pay_asked(q) is False
    out, a, _s, logs = _draft3g2(history, q, "Yes, all good, thank you!", "cash")
    assert _state3g2(a)[0] == V_BACK and out["handoff"] == [T.PAY_WORDS, G_ASK], out["handoff"]   # 3i (В): и причина N4
    assert [ln for ln in logs if ln.startswith("правило класса") and "не добавлена" in ln], logs
    out, _a, _s, _logs = _draft3g2(history, "Any luck?", "Yes, all good, thank you!", "cash",
                                  handoff=["the client asks about the payment — please check the transfer"])
    assert out["handoff"] == [T.PAY_WORDS, G_ASK], out["handoff"]
    history = _chain3g2(G2_R2, G2_FILL_RU, 2)[0]
    q = "Ну что? И есть ли свободный NMAX со скидкой?"
    assert [r["words"] for r in K.handoff(q, None)] == [K.REASON_WORDS[K.R_AVAILABILITY], K.REASON_WORDS[K.R_DISCOUNT]]
    out, _a, _s, _logs = _draft3g2(history, q, "Уточню у коллег и вернусь.", "cash")
    assert out["handoff"] == [G_PLAIN, K.REASON_WORDS[K.R_AVAILABILITY], K.REASON_WORDS[K.R_DISCOUNT]], out["handoff"]


def test_p3g2_n4_untouched_on_deep_history():
    """Словарь утверждений N4 и признак входящего второй частью не тронуты: ответы остатков («Yes, all good, thank you!»,
    «Да, всё пришло!», «Спасибо, получили!») судья БЕЗ текста входящего по-прежнему НЕ ловит (признака входящего нет —
    причина «оплата не подтверждена сверкой» не ставится), а пойманное им на той же глубокой истории ловится как было и
    стоит ПЕРЕД причиной класса. Шаг 3i (В), ожидание изменено ПОИМЁННО: настоящим путём адаптера (судье передан текст
    входящего) те же три ответа — краткие подтверждения на хвост без иного предмета при неподтверждённой оплате —
    причину N4 получают, и стоит она перед причиной класса (до шага — `PAY_WORDS not in`)."""
    for row, fill in G2_BASE:
        history, tail, text, _opener = _chain3g2(row, fill, 2)
        for res in (_results_rent_only(), _results_no_second()):
            assert _judged(text, tail, res) == [], (tail, text)
        out, _a, _s, _logs = _draft3g2(history, tail, text, "cash")
        assert out["handoff"][:1] == [T.PAY_WORDS] and _b3i(tail, text) and len(_family(out)) == 1, out["handoff"]
    history, tail, _text, _opener = _chain3g2(G2_R2, G2_FILL_RU, 2)
    out, _a, _s, _logs = _draft3g2(history, tail, "Оплата получена, спасибо!", "cash")
    assert out["handoff"] == [T.PAY_WORDS, G_PLAIN], out["handoff"]
    assert T.pay_asked("Any luck?") is False and T.pay_asked("Ну что?") is False and T.pay_asked("Скинул.") is False


def test_p3g2_long_history_is_fast():
    """Устройство: состояние темы на длинной переписке (200 обменов без слов оплаты, открывающее сообщение — в самом
    начале) считается быстро — и определение, и сбор блоков из истории."""
    import time
    rows = [("клиент", G_PAID), ("мы", "Спасибо!")]
    for i in range(200):
        c, o = (G2_FILL_RU + G2_FILL_EN)[i % 8]
        rows += [("клиент", c), ("мы", o)]
    its = _items3g2(rows, "Ну что?")
    t0 = time.perf_counter()
    blocks = M.ModelAdapter._blocks(its)
    name, words = T.pay_topic("Ну что?", blocks=blocks, now=T0)
    assert time.perf_counter() - t0 < 5.0 and (name, words) == (V_BACK, G_SAID) and len(blocks) == 402, (name, len(blocks))


def test_p3g2_control_silent_lists_kept():
    """КОНТРОЛЬ второй части (зелёный и на 719484d): где правило состояния молчит — открывающего сообщения нет, оплата
    подтверждена кодом, — список причин дословно прежний (равен причинам кода по входящему); проверяется только то, что
    есть и у первой части (без сведений `blocks`)."""
    for history, tail, text in G2_NO_OPENER:
        for facts in ("none", "cash"):
            out, a, _s, _logs = _draft3g2(history, tail, text, facts)
            assert out["handoff"] == [r["words"] for r in a.last["info"]["code_reasons"]], (tail, facts, out["handoff"])
    for row, fill in G2_BASE:
        history, tail, text, _opener = _chain3g2(row, fill, 4)
        out, a, _s, _logs = _draft3g2(history, tail, text, "backed")
        assert out["handoff"] == [r["words"] for r in a.last["info"]["code_reasons"]], (tail, out["handoff"])


# ═══ п.3i: адресный ремонт границы круга 3g — варианты Б и В (решение координатора 11.10 после fix_review3g) ═══
# Один класс «код не увидел тему оплаты → ложное подтверждение с пустыми причинами кода»: Г1 — наш ответ о деньгах без
# существующего слова оплаты → бессловесное сообщение клиента → «Спасибо, получили!»; Г2 — бессловесное сообщение
# клиента, оплату признаком не называл никто (в том числе без истории); Г2′ — сообщение клиента со словом оплаты кода, но
# без признака `pay_asked` («Вот чек.») → наш нейтральный ответ → «Ну что?» → «Да, всё пришло». Правило Б: блок клиента
# в истории открывает тему и по общей причине «заявил оплату / неясно». Правило В: краткое подтверждение или согласие в
# ответе при оплате, не подтверждённой кодом, — утверждение оплаты (`PAY_WORDS`); на шаге 3i — только на входящее БЕЗ
# иного предмета получения, с шага 3j — на ЛЮБОЕ входящее, текст которого у судьи есть (условие снято решением: имена
# исходов и слова журнала ниже — редакции шага 3j; исхода «входящее называет иной предмет получения» больше нет).
# Слов в словари не добавлено. Всё — настоящим путём адаптера (`_draft3g2`), причин модели нет.
V_B_ASKED = "входящее клиента — об оплате"
V_B_BARE = "текст входящего у судьи есть, оплата кодом не подтверждена"
V_B_PAID = "оплата подтверждена кодом"
V_B_UNSEEN = "текста входящего у судьи нет"
V_B_SAID = ("краткое подтверждение при оплате, не подтверждённой кодом, судится как подтверждение оплаты без кассы и "
            "второго источника")
I_OLD_SAID = "текст подтверждает оплату без кассы и второго источника"
I_PHOTO, I_DOC, I_VIDEO = ("медиа", "фото"), ("медиа", "документ"), ("медиа", "видео")

# Г1 — ДОСЛОВНО fix_review3g/my_chains.py, семейство G1: (вопрос клиента, наш ответ о деньгах без слова оплаты, хвост,
# ответ). 14 из 16 формулировок проверяющего; две с ответом ВНЕ словаря N4 — `I_G1_OUT` (граница после ремонта)
I_G1 = [
    ("Сколько с меня и куда?", "С вас 7790 бат за 10 суток.", "Готово.", "Спасибо, получили!"),
    ("Сколько выходит?", "Итого 7790 бат, залог 3000 бат.", "Сделал.", "Да, всё пришло, спасибо!"),
    ("Куда кидать?", "Карта Kasikorn 123-4-56789-0, получатель Test Rent Co.", "Скинул.", "Получили, благодарим!"),
    ("Как можно оплатить?", "Можно наличными при получении или на карту — как вам удобнее.", "Отправил.",
     "Спасибо, получили!"),
    ("Как можно оплатить?", "Наличными курьеру либо по QR, QR пришлю следующим сообщением.", I_PHOTO, "Получили, спасибо!"),
    ("Куда?", "Номер счёта: TEST-ACC-0042, банк Test Bank.", "Всё, ушло.", "Да, видим, спасибо!"),
    ("А за неделю сколько?", "Аренда выходит 5390 бат за неделю.", "Готово.", "Спасибо, всё получили!"),
    ("Можно оплатить картой?", "Да, можно картой при получении.", "Готово.", "Спасибо, получили!"),
    ("How much is it?", "That's 7790 THB for ten days.", "Sent!", "Thank you, received!"),
    ("What's the total?", "The total comes to 7790 THB plus a 3000 THB deposit.", "Done.", "Got it, thanks!"),
    ("How can I pay?", "Cash on delivery or card, whichever you prefer.", "Done, sent.", "Thank you, received!"),
    ("Where to?", "Our account: Test Bank, TEST-ACC-0042, Test Rent Co.", I_DOC, "Got it, thanks!"),
    ("How can I pay?", "You can use PromptPay — I'll send the QR code now.", "Sent!", "Received, thank you!"),
    ("Can I pay by card?", "Yes, card is fine at pickup.", "Done.", "Thank you, received!")]
I_G1_OUT = [                                    # ответ — не краткое подтверждение и вне словаря N4: ГРАНИЦА после ремонта
    ("Забронируете за мной?", "Бронь держим до вечера, ждём 1000 бат.", "Сделано.", "Отлично, бронь за вами!"),
    ("Can you hold it for me?", "We hold the booking once we get 1000 THB.", "Done.", "Great, it's yours!")]
I_G1_OWN = [                                    # СВОИ 13: иные ответы о сумме, реквизитах и способе, иные хвосты и ответы
    ("Сколько за неделю?", "Выходит 5453 бата за неделю, плюс залог 3000.", "Кинул.", "Да, получили."),
    ("Как вам удобнее принять?", "Наличными курьеру либо по QR — как удобнее.", "Всё, отослал.", "Всё получили, спасибо."),
    ("Куда слать?", "Kasikorn, счёт TEST-ACC-0042, получатель Test Rent Co.", "Улетело.", "Принято, спасибо!"),
    ("А на две недели?", "За две недели выйдет 10900 бат.", "Готово, проверяйте.", "Да, всё на месте."),
    ("По QR можно?", "Да, по QR тоже можно.", I_PHOTO, chr(0x1F44D)),
    ("Сколько с залогом?", "С залогом получится 10790 бат.", "Сделал, гляньте.", "Отлично, спасибо!"),
    ("Можно картой курьеру?", "Можно картой курьеру при встрече.", "Вот.", "Получили, спасибо!"),
    ("How much for a week?", "It comes to 5453 THB for the week.", "It's sent.", "Yes, received."),
    ("Do you take PromptPay?", "PromptPay works: 081 000 0000.", "Just did it.", "We got it, thank you!"),
    ("Card or cash?", "Card or cash at pickup, both are fine.", "There you go.", "All received, thanks!"),
    ("Where do I send it?", "Our Kasikorn account: TEST-ACC-0042.", I_VIDEO, "Got it, thanks!"),
    ("And with the deposit?", "With the deposit it's 10790 THB in total.", "All done, have a look.", "Thanks, received!"),
    ("Is QR ok?", "Sure, QR is fine.", "Sorted on my side.", "Received, thank you!")]

# Г2 — ДОСЛОВНО fix_review3g/my_chains.py, семейство G2: обмен о брони без слов оплаты (либо истории нет вовсе) →
# бессловесное сообщение клиента → краткое подтверждение
I_NEUTRAL = {"ru": [("клиент", "Здравствуйте, хочу NMAX на 10 дней с завтра."), ("мы", "Здравствуйте! NMAX свободен, оформляем."),
                    ("клиент", "Отлично, беру."), ("мы", "Записали, ждём вас.")],
             "en": [("клиент", "Hi, I'd like an NMAX for 10 days from tomorrow."), ("мы", "Hello! The NMAX is free, booking it for you."),
                    ("клиент", "Great, I'll take it."), ("мы", "Noted, see you then.")]}
I_G2 = [("Скинул.", "Спасибо, получили!"), ("Отправил.", "Да, всё пришло, спасибо!"), ("Всё отправил.", "Получили!"),
        ("Закинул.", "Спасибо, видим!"), ("Ушло.", "Да, дошло, спасибо!"), ("Вот скрин.", "Спасибо, получили!"),
        (I_PHOTO, "Получили, спасибо!"), (I_DOC, "Спасибо, всё получили!"),
        ("Sent!", "Thank you, received!"), ("Just sent it.", "Got it, thanks!"), ("Wired it.", "Received, thank you!"),
        ("Here you go.", "Thanks, received!")]
I_G2_NOHIST = I_G2[:4] + I_G2[8:10]             # те же шесть без истории (как у проверяющего)
I_NEUTRAL_OWN = {"ru": [("клиент", "Добрый день! Нужен скутер на неделю."), ("мы", "Добрый день! Есть PCX, привезём к отелю."),
                        ("клиент", "Хорошо, давайте."), ("мы", "Договорились, ждём вас.")],
                 "en": [("клиент", "Hello! I need a scooter for a week."), ("мы", "Hello! A PCX is available, we can bring it over."),
                        ("клиент", "Sounds good."), ("мы", "Great, see you then.")]}
I_G2_OWN = [                                    # СВОИ 14: иные бессловесные сообщения и иные краткие подтверждения
    ("Кинул.", "Спасибо, получили!"), ("Всё, отослал.", "Да, получили."), ("Улетело.", "Да, всё пришло, спасибо!"),
    ("Готово, проверяйте.", "Всё получили, спасибо."), ("Сделал, гляньте.", "Да, видим, спасибо!"),
    ("Отослал только что.", "Принято, спасибо!"), (I_VIDEO, "Получили, спасибо!"), ("Вот.", "Спасибо, всё получили!"),
    ("It's sent.", "Thank you, received!"), ("Just did it.", "Got it, thanks!"), ("There you go.", "Yes, received."),
    ("All done, have a look.", "We got it, thank you!"), ("Sorted on my side.", "All received, thanks!"),
    ("Shot it over.", "Received, thank you!")]

# Г2′ — ДОСЛОВНО fix_review3g/my_chains_b.py, семейство G3: сообщение клиента со СЛОВОМ оплаты кода, но без признака
# `pay_asked` → наш нейтральный ответ → хвост без слов оплаты → утвердительный ответ
I_G3 = ["Вот чек.", "Чек во вложении.", "Доплатил 300 бат за шлем.", "Скрин перевода во вложении.",
        "Оплата с моей стороны готова.", "Here is the receipt.", "Receipt attached.", "Proof of payment attached."]
I_G3_ASK_ONLY = "Оплата с моей стороны готова."      # общая причина по нему — «вопрос об оплате»: тему не открывает (Б), закрывает В
I_G3_OWN = [                                    # СВОИ 12: общая причина «заявил оплату», признака `pay_asked` нет
    "Чек прикрепил.", "Чек у меня на руках.", "Квитанция об оплате во вложении.", "Вот квитанция по оплате.",
    "Скрин оплаты выше.", "Вам чек из банка — выше.", "Чек из банкомата — на фото выше.", "The receipt is above.",
    "Receipt from my bank is attached.", "Screenshot of the transfer is above.", "I attached the payment receipt.",
    "Payment screenshot is in the previous message."]
I_ASK_ONLY = ["Как оплатить?", "Оплачу завтра.", "Можно оплатить картой?", "Когда нужно оплатить?",       # «вопрос об оплате»
              "Оплата при получении, верно?", "Нужна предоплата?", "Оплата не прошла.", "How can I pay?",
              "I will pay tomorrow."]
# БЫВШИЙ близнец шага 3i «иной предмет во входящем» (на 189d9c9 — причины нет). Шаг 3j условие снял: слово предмета во
# входящем не говорит, ЧТО получено, — краткое подтверждение на такое входящее при неподтверждённой кодом оплате теперь
# несёт причину N4. Это ЦЕНА стороны отказа (принята решением), а не успех: `test_p3j_cost_incoming_names_subject_named`
I_OTHER = [("Отправил вам фото паспорта, получили?", "Да, получили, спасибо!"), ("Договор подписал, отправил.", "Спасибо, получили!"),
           ("Отправил вам документы.", "Получили, спасибо!"), ("Фото прав отправил, дошло?", "Да, дошло, спасибо!"),
           ("Вот паспорт.", "Спасибо, получили!"), ("Подписанный договор выслал.", "Принято, спасибо!"),
           ("Скинул фото байка.", chr(0x1F44D)), ("Sent the passport photo.", "Got it, thanks!"),
           ("I sent you my passport photo, did you get it?", "Yes, received."),
           ("Sent you the signed contract.", "Thank you, received!"), ("Here is my licence.", "Received, thank you!"),
           ("Did you get my documents?", "We got it, thank you!")]
# ЦЕНА правила В — ДОСЛОВНО fix_review3g/my_probe3g.py (RC_COST): 24 обычные пары НЕ об оплате с хвостом без названного
# предмета; `I_COST_HIT` — те из них, что при неподтверждённой оплате получают пометку N4 (сторона отказа, принята решением)
I_COST = [
    ("Готово.", "Отлично, спасибо!"), ("Отправил.", "Спасибо, получили!"), ("Ок.", "Хорошо, ждём вас завтра."),
    ("Спасибо!", "Пожалуйста!"), (chr(0x1F44D), "Хорошего дня!"), ("Договорились.", "До встречи!"),
    ("Да.", "Отлично, тогда оформляем."), ("Понял.", "Если будут вопросы — пишите."), ("Подъезжаю.", "Ждём!"),
    ("Я на месте.", "Выходим, минуту."), ("Вернул ключ.", "Спасибо, получили!"), ("Заполнил.", "Спасибо, всё получили!"),
    ("Подписал.", "Спасибо, получили!"), ("Sent.", "Thanks, received!"), ("Done.", "Great, thanks!"),
    ("Ok.", "See you tomorrow."), ("Thanks!", "You're welcome!"), ("Signed.", "Thank you, received!"),
    ("I'm here.", "Coming out now."), ("Got it.", "Great!"), (I_PHOTO, "Спасибо, получили!"),
    (I_PHOTO, "Thanks, got it!"), ("Хорошо.", "Да, всё в порядке."), ("Ясно.", "Да, получили, спасибо.")]
I_COST_HIT = [
    ("Готово.", "Отлично, спасибо!"), ("Отправил.", "Спасибо, получили!"), ("Вернул ключ.", "Спасибо, получили!"),
    ("Заполнил.", "Спасибо, всё получили!"), ("Подписал.", "Спасибо, получили!"), ("Sent.", "Thanks, received!"),
    ("Done.", "Great, thanks!"), ("Signed.", "Thank you, received!"), ("Got it.", "Great!"),
    (I_PHOTO, "Спасибо, получили!"), (I_PHOTO, "Thanks, got it!"), ("Хорошо.", "Да, всё в порядке."),
    ("Ясно.", "Да, получили, спасибо.")]
# отпечатки выражений словарей (sha256 шаблона, 16 знаков) — сняты с f023878: слов в словари шагом не добавлено
I_PRINTS_T = {"_PAY_AFFIRM": "9bd33f386562e774", "_PAY_FORMS": "412d1e9a0f9f38b4", "_PAY_SUMS": "90d4629ea837d9dc",
              "_PAY_CTX": "c591cad2a8c76b81", "_ASK_DID": "ba5ea75d13ab7c95", "_ASK_SUBJ": "a8939e4f4cb17e8d",
              "_ASK_GOT": "8b3f601b0898ea03", "_PQ_TOPIC": "e7f5ae796bbfb331", "_PQ_THING": "339f674f75bbb118",
              "_PQ_PAYWORD": "8203aa7c34d97133", "_PQ_PROOF": "19cb9d2738e3c1c1", "_PQ_CHECK": "acfa3efebbc28394",
              "_PQ_SEEN": "c1f1201d7991533d", "_PC_DOC": "64145061f60d3102", "_PD_ITEM": "27a486fab46f9984"}
I_PRINTS_K = {"_PAY_DONE": "bcdf5352e762620d", "_PAY_PROOF": "6d31de87dabadcef", "_PAY_QUESTION": "a82e69b740fe4b73"}


def _said3i(tail):
    return tail if isinstance(tail, str) else "[%s]" % tail[1]


def _run3i(history, tail, text, facts):
    """Черновик настоящим путём адаптера → (причины, исход темы, строки журнала «конфликт», строки «правило класса»,
    причины кода по входящему, оплата подтверждена кодом?)."""
    out, a, _s, logs = _draft3g2(history, tail, text, facts)
    assert out is not None and out["text"] == text, (tail, text)
    return (list(out["handoff"]), _state3g2(a), [ln for ln in logs if ln.strip().startswith("конфликт ")],
            [ln for ln in logs if ln.startswith("правило класса")], [r["words"] for r in a.last["info"]["code_reasons"]],
            T.pay_confirmed(a.last["tools"]["journal"].facts))


def _bad_b3i(rows, want_state=V_NONE):
    """Цепочки (история, хвост, ответ), где при «строки кассы нет» / «касса без второго источника» черновик НЕ несёт
    ровно причину N4 правила В (тему никто не открыл — причины класса и строки правила нет, журнал называет правило В)."""
    bad = []
    for history, tail, text in rows:
        said = _said3i(tail)
        for facts in ("none", "cash"):
            hand, state, conf, rule, by_tail, paid = _run3i(history, tail, text, facts)
            if hand != [T.PAY_WORDS] or state[0] != want_state or rule or by_tail or paid or T.pay_asked(said) \
                    or not [ln for ln in conf if V_B_SAID in ln] or T.pay_brief(said, False, False) != (V_B_BARE, True):
                bad.append((said, text, facts, state[0], hand, conf))
    return bad


def test_p3i_incoming_context_named_outcomes():
    """Определение контекста краткого подтверждения (`pay_brief`, правило В) — ОДНО, исход назван на каждой ветке:
    входящее об оплате — признак есть (как до шага 3i); текста входящего у судьи нет — признака нет (как до шага 3i);
    оплата подтверждена кодом — признака нет (правило не применяется); иначе — признак есть при ЛЮБОМ тексте входящего.
    Шаг 3j: исхода «входящее называет иной предмет получения» больше нет (имени `PB_OTHER` и выражения-заглушки
    `_PB_STUB` в модуле нет) — входящее с названным предметом («Отправил вам фото паспорта, получили?», «По QR отправил.»,
    «За байк скинул.») даёт тот же исход, что бессловесное «Готово.» и медиа без подписи."""
    assert (T.PB_ASKED, T.PB_BARE, T.PB_PAID, T.PB_UNSEEN, T.PB_SAID) == (V_B_ASKED, V_B_BARE, V_B_PAID, V_B_UNSEEN, V_B_SAID)
    assert not hasattr(T, "PB_OTHER") and not hasattr(T, "_PB_STUB")
    assert {T.pay_brief(i, a, p)[0] for i in ("Готово.", "Вот паспорт.", "", None) for a in (False, True) for p in (False, True)} \
        == {V_B_ASKED, V_B_BARE, V_B_PAID, V_B_UNSEEN}                                   # иных исходов у определения нет
    for incoming in ("Готово.", "Отправил фото паспорта.", None, ""):
        for paid in (False, True):
            assert T.pay_brief(incoming, True, paid) == (V_B_ASKED, True), incoming       # признак входящего — как был
    for paid in (False, True):
        assert T.pay_brief(None, False, paid) == (V_B_UNSEEN, False)
    bare = ["Готово.", "Скинул.", "Отправил.", "Ушло.", "Sent!", "Done.", "Just sent it.", "[фото]", "[документ]",
            "[видео]", "[пусто]", "", "Ну что?", "Спасибо!", "Готово.\n[фото]", "[фото]\nГотово.", " [фото] ",
            "Вот скрин.", "Вот чек.", "Скинул скрин договора.", "Receipt attached.",              # бумага об оплате
            "Деньги за шлем и байк — всё у вас?", "Is the money for the helmet all good?",        # слово оплаты + предмет
            "Как оплатить?", "Можно оплатить картой?"]
    # входящее НАЗЫВАЕТ предмет (слово предмета `_PQ_TOPIC` без слова оплаты и без бумаги об оплате): на шаге 3i исход
    # был «входящее называет иной предмет получения», признака не было; шаг 3j — тот же исход, что у прочих входящих
    named = ["Отправил вам фото паспорта, получили?", "Договор подписал, отправил.", "Пришлите договор.", "А шлем дадите?",
             "Отправил вам документы.", "Вот адрес отеля.", "Sent the passport photo.", "Here is my licence.",
             "Готово.\nОтправил фото паспорта.", "[фото]\nЭто мой паспорт.", "Фото [фото] отправил.",
             "По QR отправил.", "На счёт закинул.", "Sent via the link.", "Ну что по моему вопросу?",       # §9.2, §9.3
             "За байк скинул.", "За доставку закинул.", "Sent it for the bike."]
    for incoming in bare + named:
        assert T.pay_asked(incoming) is False, incoming
        assert T.pay_brief(incoming, False, False) == (V_B_BARE, True), incoming
        assert T.pay_brief(incoming, False, True) == (V_B_PAID, False), incoming          # оплата подтверждена кодом
    for incoming in named:                              # предмет назван существующим словом — и всё же признак есть
        assert T._PQ_TOPIC.search(incoming) and not T._PQ_PAYWORD.search(incoming) and not T._PQ_PROOF.search(incoming), incoming


def test_p3i_money_roles_and_judge_take_incoming():
    """Судья денежных ролей с текстом входящего (`money_roles` / `judge`, параметр `incoming`): при неподтверждённой
    оплате краткое подтверждение на ЛЮБОЕ входящее с текстом — причина N4, словами журнала правила В (шаг 3j: и на
    входящее с названным предметом — «Отправил вам фото паспорта, получили?», «По QR отправил.»; на шаге 3i причины на
    них не было); без текста входящего — причины нет (как до шага 3i); утверждение, найденное и без правила, называет
    журнал прежними словами. Подтверждённая кодом оплата: причины нет при любом входящем — в том числе у числа без валюты
    («Да, 9990 получили.»), которое при признаке стало бы «суммы у аренды нет»."""
    unpaid = [[], T.accepted(_results_rent_only()), T.accepted(_results_no_second())]
    backed = T.accepted(_results_backed())
    for facts in unpaid:
        for incoming in ("Готово.", "Отправил вам фото паспорта, получили?", "По QR отправил.", "За байк скинул.", "[фото]", ""):
            got = T.money_roles("Спасибо, получили!", facts, asked=False, incoming=incoming)
            assert [w for w, _why in got] == [T.PAY_WORDS] and got[0][1].startswith(V_B_SAID + ": "), (incoming, got)
        assert T.money_roles("Спасибо, получили!", facts, asked=False) == []              # текста входящего нет — как было
        assert T.money_roles("Спасибо, получили!", facts, asked=False, incoming=None) == []
        assert T.money_roles("Спасибо, получили!", facts) == []
        got = T.money_roles("Оплата получена, спасибо!", facts, asked=False, incoming="Готово.")
        assert [w for w, _why in got] == [T.PAY_WORDS] and got[0][1].startswith(I_OLD_SAID + ": "), got
        got = T.money_roles("Да, всё пришло.", facts, asked=True, incoming="Деньги пришли?")
        assert [w for w, _why in got] == [T.PAY_WORDS] and got[0][1].startswith(I_OLD_SAID + ": "), got
        assert [w for w, _why in T.money_roles("Да, 9990 получили.", facts, asked=False, incoming="Готово.")] == [T.PAY_WORDS]
        assert [w for w, _why in T.money_roles("Да, 9990 получили.", facts, asked=False,
                                               incoming="Отправил вам документы.")] == [T.PAY_WORDS]          # шаг 3j
        assert T.money_roles("Да, 9990 получили.", facts, asked=False) == []              # без текста входящего — как было
        # ответ сам говорит «проверим» / предмет назван раньше / вопрос — прежние исключения N4 действуют и при правиле В
        for text in ("Получили, проверим и ответим.", "Спасибо за информацию, получили.", "Получили?", "Пока не получили."):
            for incoming in ("Готово.", "Отправил вам документы.", "По QR отправил."):
                assert T.money_roles(text, facts, asked=False, incoming=incoming) == [], (text, incoming)
    for incoming in ("Готово.", "[фото]", "Отправил вам документы.", None):
        for text in ("Спасибо, получили!", "Да, всё пришло.", "Да, 9990 получили.", chr(0x1F44D)):
            assert T.money_roles(text, backed, asked=False, incoming=incoming) == [], (text, incoming)
    assert T.money_roles("Да, 7790 получили.", backed, asked=False, incoming="Готово.") == []     # сумма аренды — с опорой
    for res in (_results_rent_only(), _results_no_second()):
        jr = T.Journal("5678")
        words, _fig = T.judge("Спасибо, получили!", None, [dict(r) for r in res], jr, asked=False, incoming="Готово.")
        assert words == [T.PAY_WORDS] and [c for c in jr.conflicts if c.startswith(V_B_SAID)], (words, jr.conflicts)
        assert T.judge("Спасибо, получили!", None, [dict(r) for r in res], T.Journal("5678"), asked=False)[0] == []
        assert T.judge("Спасибо, получили!", None, [dict(r) for r in res], T.Journal("5678"), asked=False,
                       incoming="Отправил вам фото паспорта, получили?")[0] == [T.PAY_WORDS]                  # шаг 3j
    assert T.judge("Да, 9990 получили.", None, [dict(r) for r in _results_backed()], T.Journal("5678"), asked=False,
                   incoming="Готово.")[0] == []


def test_p3i_g1_our_money_answer_without_pay_word_then_wordless_message():
    """Г1: наш ответ о деньгах БЕЗ существующего слова оплаты (сумма, реквизиты, способ) → бессловесное сообщение
    клиента («Готово.», «Скинул.», «Sent!», фото без подписи) → краткое подтверждение («Спасибо, получили!», «Got it,
    thanks!»). 14 цепочек проверяющего дословно и 13 своих: черновик при «строки кассы нет» и при «касса без второго
    источника» несёт причину N4 (была `[]`).
    Шаг 3l, ожидание изменено ПОИМЁННО: наш ответ с суммой, способом или счётом тему теперь ОТКРЫВАЕТ (`PT_OURS_MONEY`) —
    у 24 цепочек из 27 рядом с причиной N4 стоит причина класса «оплата» (было: тему не открывает никто, ровно причина
    N4). Три цепочки `L_G1_NO_SIGN` (реквизиты вне словаря кода: «Our account: …», «PromptPay works: …», «Our Kasikorn
    account: …») — как было: `PT_NONE`, ровно причина N4."""
    assert (len(I_G1), len(I_G1_OUT), len(I_G1_OWN)) == (14, 2, 13)
    rows = [([("клиент", q), ("мы", ours)], tail, text) for q, ours, tail, text in I_G1 + I_G1_OWN]
    plain = [r for r in rows if r[0][1][1] in L_G1_NO_SIGN]
    assert len(plain) == len(L_G1_NO_SIGN) == 3
    for history, _tail, _text in rows:
        want = V_NONE if history[1][1] in L_G1_NO_SIGN else V_OURS_MONEY
        # шаг 3m, ожидание изменено ПОИМЁННО: вопрос клиента с общей причиной «вопрос об оплате» либо «депозит»
        # (`M_G1_ASKS`) блоком истории тему теперь открывает сам (`PT_PREV_NAMED`; было `PT_NONE`). Исход ЦЕПОЧЕК прежний:
        # тему открывает наш ответ (`PT_OURS_MONEY`) — признак шага 3m добавочный и к признакам шага 3l
        asks = V_PREV_NAMED if history[0][1] in M_G1_ASKS else V_NONE
        assert T._topic_ours(K.mask(history[1][1])[0]) == want and T._topic_theirs(history[0][1]) == asks, history
    assert len([r for r in rows if r[0][0][1] in M_G1_ASKS]) == 8 and not [r for r in plain if r[0][0][1] in M_G1_ASKS]
    bad = _bad_b3i(plain)
    assert not bad, bad
    for history, tail, text in [r for r in rows if r not in plain]:
        for facts in ("none", "cash"):
            hand, state, conf, rule, by_tail, paid = _run3i(history, tail, text, facts)
            assert hand == [T.PAY_WORDS, G_PLAIN] and state == (V_OURS_MONEY, G_PLAIN), (history[1][1], facts, hand, state)
            assert rule == ["правило класса: %s; причина кода добавлена" % V_OURS_MONEY] and not by_tail and not paid, rule
            assert [ln for ln in conf if V_B_SAID in ln], conf
    # сверка не завершена и версия по пояснению — тот же путь
    history, tail, text = rows[0]
    out, a, s, _logs = _draft3g2(history, tail, text, "over")
    assert a.last["tools"]["state"] == T.OVER and out["handoff"] == [T.INCOMPLETE_WORDS, T.PAY_WORDS, G_PLAIN], out["handoff"]
    out, a, _s, _logs = _draft3g2(history, tail, text, "cash", hint=("прежний черновик", "скажи короче"))
    assert a.last["info"].get("hint") is True and out["handoff"] == [T.PAY_WORDS, G_PLAIN], out["handoff"]


def test_p3i_g2_wordless_message_nobody_named_payment():
    """Г2: бессловесное сообщение клиента («Скинул.», «Отправил.», «Ушло.», «Вот скрин.», фото или документ без подписи,
    «Sent!», «Just sent it.»), оплату признаком не называл никто, — после обмена о брони без слов оплаты и без истории
    вовсе: краткое подтверждение несёт причину N4 при обоих наборах фактов (была `[]`). 12 хвостов проверяющего дословно
    (с историей и шесть без неё) и 14 своих."""
    assert (len(I_G2), len(I_G2_NOHIST), len(I_G2_OWN)) == (12, 6, 14)
    def lang(tail, text):
        return "en" if K.lang_of(text) == "en" else "ru"
    rows = [(I_NEUTRAL[lang(t, a)], t, a) for t, a in I_G2] + [([], t, a) for t, a in I_G2_NOHIST]
    rows += [(I_NEUTRAL_OWN[lang(t, a)], t, a) for t, a in I_G2_OWN] + [([], t, a) for t, a in I_G2_OWN[:4] + I_G2_OWN[8:10]]
    assert len(rows) == 12 + 6 + 14 + 6
    for hist in list(I_NEUTRAL.values()) + list(I_NEUTRAL_OWN.values()):
        for who, said in hist:                          # шаг 3l: `_topic_ours` отдаёт ИМЯ исхода (было — bool)
            assert (T._topic_ours(said) if who == "мы" else T._topic_theirs(said)) == V_NONE, said
    bad = _bad_b3i(rows)
    assert not bad, bad
    assert T.pay_brief("Вот скрин.", False, False) == (V_B_BARE, True) and T._PQ_TOPIC.search("Вот скрин.") is not None


def test_p3i_g2prime_client_block_with_general_reason_opens_topic():
    """Г2′ (правило Б): сообщение клиента со словом оплаты кода, но без признака `pay_asked` («Вот чек.», «Доплатил 300
    бат за шлем.», «Here is the receipt.» — в хвосте общая причина по входящему на них стоит) → наш нейтральный ответ →
    «Ну что?» → «Да, всё пришло, спасибо!»: блок клиента открывает тему общей причиной «заявил оплату» (исход
    `PT_PREV_SAID`, слова — смысл блока), черновик несёт причину класса и причину N4 (была `[]`). 8 сообщений
    проверяющего дословно (семь открывает Б; «Оплата с моей стороны готова.» — «вопрос об оплате», его закрывает В) и
    12 своих. Б работает и БЕЗ правила В: на ответ вне словаря N4 причина класса стоит одна."""
    assert (len(I_G3), len(I_G3_OWN)) == (8, 12)
    for x in I_G3 + I_G3_OWN:
        assert T.pay_asked(x) is False and K.handoff(x, None), x                    # признака нет, общая причина в хвосте есть
        en = K.lang_of(x) == "en"
        history = [("клиент", x), ("мы", "Hello! One moment, please." if en else "Добрый день! Одну минуту.")]
        tail, text = ("So?", "Yes, all received, thank you!") if en else ("Ну что?", "Да, всё пришло, спасибо!")
        plain = "Let me ask my colleague and get back to you." if en else "Уточняю у коллеги, вернусь с ответом."
        # шаг 3l: `_topic_ours` отдаёт ИМЯ исхода (было — bool)
        assert T._topic_ours(history[1][1]) == V_NONE and T._PayClaim(True).search(plain) is None, (history[1][1], plain)
        words = K.MONEY_WORDS[K.payment_mode(x)]
        for facts in ("none", "cash"):
            hand, state, conf, rule, by_tail, paid = _run3i(history, tail, text, facts)
            assert not by_tail and not paid, (x, by_tail)
            if x == I_G3_ASK_ONLY:
                # шаг 3m, ожидание изменено ПОИМЁННО: «Оплата с моей стороны готова.» — общая причина «вопрос об оплате»;
                # блок клиента тему теперь открывает (`PT_PREV_NAMED`), за причиной N4 стоит причина класса «оплата»
                # (было: `PT_NONE`, ровно причина N4, строки правила нет)
                assert T._topic_theirs(x) == V_PREV_NAMED and state == (V_PREV_NAMED, G_PLAIN), (x, state)
                assert hand == [T.PAY_WORDS, G_PLAIN], (x, facts, hand)
                assert rule == ["правило класса: %s; причина кода добавлена" % V_PREV_NAMED], rule
                continue
            assert T._topic_theirs(x) == V_PREV_SAID and state == (V_PREV_SAID, words) and words == G_SAID, (x, state)
            assert hand == [T.PAY_WORDS, words], (x, facts, hand)
            assert rule == ["правило класса: %s; причина кода добавлена" % V_PREV_SAID], rule
            hand, state, _conf, rule, _by, _paid = _run3i(history, tail, plain, facts)          # Б без В
            assert hand == [words] and state[0] == V_PREV_SAID, (x, facts, hand)
            deep = history + [("клиент", "Is a helmet included?" if en else "А шлем дадите?"),
                              ("мы", "Yes, a helmet is included." if en else "Да, шлем дадим.")]
            hand, state, _conf, rule, _by, _paid = _run3i(deep, tail, plain, facts)             # глубже одного обмена
            assert hand == [words] and state == (V_BACK_SAID, words), (x, facts, hand, state)
            assert rule == ["правило класса: %s; причина кода добавлена" % V_BACK_SAID], rule


def test_p3i_rule_be_client_block_definition_named_outcomes():
    """Определение блока клиента в истории (`_topic_theirs`, правило Б) — исход назван: признак `pay_asked` — `PT_PREV`
    (как до шага); признака нет, общая причина по входящему «заявил оплату» либо «неясно» — `PT_PREV_SAID`; «вопрос об
    оплате» и блок без слов общей причины — `PT_NONE`. Раньше одного обмена — `PT_BACK_SAID`; давность судит его как
    любое открывающее сообщение; хвост судится по-прежнему (на нём общая причина по входящему стоит сама); слова причины
    — смысл блока; блок с признаком сильнее нашего ответа в том же обмене."""
    assert (T.PT_PREV_SAID, T.PT_BACK_SAID) == (V_PREV_SAID, V_BACK_SAID)
    # шаг 3l: у обмена раньше предыдущего своё имя есть и у бумаги клиента, и у обоих исходов нашего ответа;
    # шаг 3m: и у обоих его исходов (блок клиента — вопрос об оплате, залог, сумма; наш ответ — сумма в любой валюте, залог)
    assert T._PT_DEEPER == {V_PREV: V_BACK, V_PREV_SAID: V_BACK_SAID, V_PREV_PROOF: V_BACK_PROOF, V_OURS: V_BACK_OURS,
                            V_OURS_MONEY: V_BACK_OURS_MONEY, V_PREV_NAMED: V_BACK_NAMED, V_OURS_NAMED: V_BACK_OURS_NAMED}
    for x in I_G3 + I_G3_OWN:
        # шаг 3m, ожидание изменено ПОИМЁННО: «Оплата с моей стороны готова.» («вопрос об оплате») — `PT_PREV_NAMED`
        want = V_PREV_NAMED if x == I_G3_ASK_ONLY else V_PREV_SAID
        assert T._topic_theirs(x) == want, x
        assert T.pay_topic(x)[0] == V_NONE, x                                       # хвост — определение прежнее
        if want == V_PREV_NAMED:
            assert T.pay_topic("Ну что?", x, "Одну минуту.") == (V_PREV_NAMED, G_PLAIN), x
            continue
        assert T.pay_topic("Ну что?", x, "Одну минуту.") == (V_PREV_SAID, G_SAID), x
        assert T.pay_topic("Ну что?", blocks=[("мы", "Ок.", None), ("клиент", "Ок", None), ("мы", "Минуту.", None),
                                              ("клиент", x, None)]) == (V_BACK_SAID, G_SAID), x
    assert T._topic_theirs("Чек дадите?") == V_PREV_SAID and K.payment_mode("Чек дадите?") == K.MONEY_PAYMENT_UNCLEAR
    assert T.pay_topic("Ну что?", "Чек дадите?", "Минуту.") == (V_PREV_SAID, G_PLAIN)             # «неясно» — слова «оплата»
    for x in ["Сколько стоит аренда?", "Спасибо!", "А шлем дадите?", "", None, "[фото]"]:
        assert T._topic_theirs(x) == V_NONE, x
        assert T.pay_topic("Ну что?", x, "Минуту.")[0] == V_NONE, x
    for x in I_ASK_ONLY:                                # шаг 3m, ожидание изменено ПОИМЁННО: «вопрос об оплате» — открывает
        assert T._topic_theirs(x) == V_PREV_NAMED, x
        assert T.pay_topic("Ну что?", x, "Минуту.") == (V_PREV_NAMED, G_PLAIN), x
    for x in (G_PAID, "Деньги пришли?", "Sent you the money."):                     # признак `pay_asked` — имена прежние
        assert T._topic_theirs(x) == V_PREV and T.pay_topic("Ну что?", x, "Минуту.")[0] == V_PREV, x
    # давность: блок с общей причиной раньше одного обмена и старше 168 ч тему не открывает; свежий и без времени — открывает
    now, hour = T0, 3600
    wait = [("мы", "Минуту.", now - hour), ("клиент", "Ок", now - hour)]
    for hours, want in ((1, V_BACK_SAID), (168, V_BACK_SAID), (169, V_OLD), (None, V_BACK_SAID)):
        ts = None if hours is None else now - hours * hour
        got = T.pay_topic("Ну что?", blocks=wait + [("мы", "Одну минуту.", ts), ("клиент", "Вот чек.", ts)], now=now)
        assert got[0] == want, (hours, got)
    assert T.pay_topic("Ну что?", blocks=[("мы", "Одну минуту.", now - 500 * hour), ("клиент", "Вот чек.", now - 500 * hour)],
                       now=now)[0] == V_PREV_SAID                                   # обмен перед хвостом давностью не судится
    for topic in ((V_PREV_SAID, G_SAID), (V_BACK_SAID, G_PLAIN)):
        assert T.topic_reason(topic, []) == (topic[0], [topic[1]])
        assert T.topic_reason(topic, T.accepted(_results_no_second())) == (topic[0], [topic[1]])
        assert T.topic_reason(topic, T.accepted(_results_backed())) == (V_PAID, [])


def test_p3j_cost_incoming_names_subject_named():
    """ЦЕНА снятия условия «иной предмет во входящем» (сторона отказа, принята решением; НЕ успех) — БЫВШИЙ близнец шага
    3i поимённо (`I_OTHER`, 12 пар): входящее называет предмет получения («Отправил вам фото паспорта, получили?»,
    «Договор подписал, отправил.», «Sent the passport photo.»), ответ — краткое подтверждение без названного предмета. На
    189d9c9 причины не было (ожидание изменено шагом 3j); теперь при неподтверждённой кодом оплате пометку «оплата не
    подтверждена сверкой» несут 12 из 12 — слово предмета во входящем не говорит, ЧТО получено. Без признака контекста
    исход N4 прежний («краткое подтверждение без вопроса клиента об оплате»); при подтверждённой кодом оплате пометки
    нет ни у одной; автоотправки нет — пометка есть предупреждение на карточке сотрудника."""
    assert len(I_OTHER) == 12
    for tail, text in I_OTHER:
        assert T.pay_asked(tail) is False and K.handoff(tail, None) == [], tail
        assert T._PQ_TOPIC.search(tail) and not T._PQ_PAYWORD.search(tail) and not T._PQ_PROOF.search(tail), tail
        assert T.pay_brief(tail, False, False) == (V_B_BARE, True), tail
        assert V_NOASK in {v for _m, v in T._PAY_CLAIM.explain(text, False)}, (text, T._PAY_CLAIM.explain(text, False))
        for history in ([], I_NEUTRAL["en" if K.lang_of(text) == "en" else "ru"]):
            for facts in ("none", "cash"):
                hand, state, conf, rule, _by, _paid = _run3i(history, tail, text, facts)
                assert hand == [T.PAY_WORDS] and state[0] == V_NONE and not rule, (tail, text, facts, hand)
                assert [ln for ln in conf if V_B_SAID in ln], (tail, conf)
            hand, _state, conf, _rule, by_tail, paid = _run3i(history, tail, text, "backed")
            assert paid and hand == by_tail == [] and not conf, (tail, text, hand, conf)


def test_p3i_twin_confirmed_payment_adds_nothing():
    """Близнец «оплата подтверждена кодом» (касса аренды обращения + договор той же аренды): ни одной новой причины — те
    же цепочки Г1, Г2, Г2′ дают список причин, равный причинам кода по входящему; число без валюты («Да, 9990 получили.»
    на «Готово.») причины не получает (при признаке оно стало бы «такой суммы у аренды нет»); полезный сценарий с PDF цел."""
    rows = [([("клиент", q), ("мы", ours)], tail, text) for q, ours, tail, text in I_G1 + I_G1_OUT + I_G1_OWN]
    rows += [(I_NEUTRAL["en" if K.lang_of(a) == "en" else "ru"], t, a) for t, a in I_G2] + [([], t, a) for t, a in I_G2_OWN]
    for x in I_G3 + I_G3_OWN:
        en = K.lang_of(x) == "en"
        rows.append(([("клиент", x), ("мы", "Hello! One moment, please." if en else "Добрый день! Одну минуту.")],
                     "So?" if en else "Ну что?", "Yes, all received, thank you!" if en else "Да, всё пришло, спасибо!"))
    rows += [([], "Готово.", "Да, 9990 получили."), ([], "Done.", "Yes, 9990 received."), ([], I_PHOTO, "Да, 9990 получили."),
             ([], "Готово.", "Да, оплата получена, договор отправляю файлом.")]
    assert len(rows) == 29 + 12 + 14 + 20 + 4
    bad = []
    for history, tail, text in rows:
        hand, state, conf, rule, by_tail, paid = _run3i(history, tail, text, "backed")
        if not paid or hand != by_tail or T.PAY_WORDS in hand or conf \
                or [ln for ln in rule if "причина кода не нужна" not in ln]:
            bad.append((_said3i(tail), text, hand, conf, rule))
    assert not bad, bad
    # без условия «оплата не подтверждена» у числа появилась бы причина: то же число при неподтверждённой оплате её несёт
    # (шаг 3j: и на входящее с названным предметом — на 189d9c9 у «Отправил вам документы.» причины не было)
    assert _run3i([], "Готово.", "Да, 9990 получили.", "cash")[0] == [T.PAY_WORDS]
    assert _run3i([], "Отправил вам документы.", "Да, 9990 получили.", "cash")[0] == [T.PAY_WORDS]
    assert _run3i([], "Отправил вам документы.", "Да, 9990 получили.", "backed")[0] == []


def test_p3i_former_twin_payment_question_block_opens_topic_since_3m():
    """БЫВШИЙ близнец шага 3i «вопрос об оплате тему не открывает» (проверка `…twin_payment_question_block_does_not_open_
    topic` фиксировала пустой список причин) — сторона ОТМЕНЕНА решением координатора 11.10 (блокер B2, лекарство Л2),
    ожидание изменено ПОИМЁННО. Блок клиента, чья общая причина — «вопрос об оплате» («Как оплатить?», «Оплачу завтра.»,
    «Оплата не прошла.»), тему теперь ОТКРЫВАЕТ (`PT_PREV_NAMED`): после нашего нейтрального ответа и хвоста без слов
    оплаты ответ вне словаря N4 несёт причину класса «оплата» при обоих наборах фактов — 18 из 18 (было `[]`, исход
    `PT_NONE`, строки правила нет). Это ЦЕНА шага (сторона отказа), а не успех. При подтверждённой кодом оплате причины
    нет."""
    assert len(I_ASK_ONLY) == 9
    got = 0
    for x in I_ASK_ONLY:
        en = K.lang_of(x) == "en"
        assert [r["words"] for r in K.handoff(x, None)] == [G_ASK] and T.pay_asked(x) is False, x
        history = [("клиент", x), ("мы", "Hello! One moment, please." if en else "Добрый день! Одну минуту.")]
        plain = "Let me ask my colleague and get back to you." if en else "Уточняю у коллеги, вернусь с ответом."
        for facts in ("none", "cash"):
            hand, state, conf, rule, _by, _paid = _run3i(history, "So?" if en else "Ну что?", plain, facts)
            assert hand == [G_PLAIN] and state == (V_PREV_NAMED, G_PLAIN) and not conf, (x, facts, hand, state)   # была []
            assert rule == ["правило класса: %s; причина кода добавлена" % V_PREV_NAMED], rule
            got += 1
        hand, _state, _conf, rule, by_tail, paid = _run3i(history, "So?" if en else "Ну что?", plain, "backed")
        assert paid and hand == by_tail == [] and rule == ["правило класса: %s; причина кода не нужна" % V_PAID], (x, hand, rule)
    assert got == 18


def test_p3i_reason_order_and_card():
    """Порядок и карточка: причина N4 правила В — первой, перед причиной класса и причинами не о деньгах; на карточке
    сотрудника её слова дают действие (категория слов причины), «Отправить» открыто с пометкой; в ЗАПРОС модели признаки
    не идут. Причина модели об оплате отпадает как повтор, а не вытесняет причину кода.
    Шаг 3l, ожидание изменено ПОИМЁННО: наш ответ «С вас 7790 бат за 10 суток.» называет сумму — тема открыта признаком
    шага, и за причиной N4 стоит причина класса «оплата» (было: ровно причина N4); на карточке — два действия."""
    import wa_agent_tg as TG
    history = [("клиент", "Сколько с меня и куда?"), ("мы", "С вас 7790 бат за 10 суток.")]
    out, a, s, logs = _draft3g2(history, "Готово.", "Спасибо, получили!", "cash")
    hand = A.draft_out(out)[1]
    assert hand == [T.PAY_WORDS, G_PLAIN], hand
    assert TG.card_actions(hand) == [TG.CARD_ACTIONS[K.MONEY_PAYMENT_ASK], TG.CARD_ACTIONS[K.MONEY_PAYMENT_UNCLEAR]], TG.card_actions(hand)
    notes = TG.card_notes(hand, 1, True)
    assert TG.W_HAND in notes and TG.W_SEND_HAND in notes, notes
    assert out["question"] == "Готово." and not [u for u in s.seen if "НУЖЕН ЧЕЛОВЕК" in u or V_B_BARE in u], out["question"]
    assert not [u for u in s.seen if V_OURS_MONEY in u or "назвал деньги" in u], "признаки темы в запрос модели не идут"
    q = "Готово. И есть ли свободный NMAX со скидкой?"
    assert [r["words"] for r in K.handoff(q, None)] == [K.REASON_WORDS[K.R_AVAILABILITY], K.REASON_WORDS[K.R_DISCOUNT]]
    out, _a, _s, _logs = _draft3g2(history, q, "Спасибо, получили!", "cash")
    assert out["handoff"] == [T.PAY_WORDS, G_PLAIN, K.REASON_WORDS[K.R_AVAILABILITY], K.REASON_WORDS[K.R_DISCOUNT]], out["handoff"]
    out, _a, _s, _logs = _draft3g2(history, "Готово.", "Спасибо, получили!", "cash",
                                  handoff=["клиент сообщает об оплате — проверьте поступление"])
    assert out["handoff"][0] == T.PAY_WORDS and out["handoff"].count(T.PAY_WORDS) == 1, out["handoff"]


def test_p3i_cost_of_rule_ve_named():
    """ЦЕНА правила В (сторона отказа, принята решением; НЕ успех): 24 обычные пары НЕ об оплате проверяющего дословно —
    при неподтверждённой кодом оплате пометку «оплата не подтверждена сверкой» получают 13 из них поимённо (`I_COST_HIT`:
    краткое подтверждение или согласие на «Подписал.», «Заполнил.», «Вернул ключ.», фото без подписи); прочие 11 — нет.
    При подтверждённой кодом оплате пометку не получает ни одна."""
    assert (len(I_COST), len(I_COST_HIT)) == (24, 13) and not [p for p in I_COST_HIT if p not in I_COST]
    hit = []
    for tail, text in I_COST:
        for facts in ("none", "cash"):
            hand = _run3i([], tail, text, facts)[0]
            if T.PAY_WORDS in hand and (tail, text) not in hit:
                hit.append((tail, text))
            assert (T.PAY_WORDS in hand) == ((tail, text) in I_COST_HIT), (tail, text, facts, hand)
        assert T.PAY_WORDS not in _run3i([], tail, text, "backed")[0], (tail, text)
    assert hit == I_COST_HIT, hit


def test_p3i_former_boundary_g1_out_has_class_reason_since_3l():
    """БЫВШАЯ ГРАНИЦА шага 3i (проверка `…boundary_after_repair_answer_outside_n4_dictionary` фиксировала пустой список
    причин; блокер B1 узкой проверки 3k — цепочки G107 и G114) — снята шагом 3l, ожидание изменено ПОИМЁННО. Наш ответ
    назвал сумму без слова оплаты кода («Бронь держим до вечера, ждём 1000 бат.», «We hold the booking once we get 1000
    THB.»), клиент ответил бессловесно, ответ — не краткое подтверждение и вне словаря N4 («Отлично, бронь за вами!»,
    «Great, it's yours!»): тему открывает признак шага (`PT_OURS_MONEY`), причина кода «оплата» стоит при обоих наборах
    фактов (была `[]`); при подтверждённой кодом оплате причины нет. Слов в словари не добавлено."""
    for q, ours, tail, text in I_G1_OUT:
        assert T.pay_brief(tail, False, False) == (V_B_BARE, True) and T._PayClaim(True).search(text) is None, text
        assert T._PQ_PAYWORD.search(ours) is None and K.thb_amounts(ours) == [1000], ours
        for facts in ("none", "cash"):
            hand, state, conf, rule, _by, _paid = _run3i([("клиент", q), ("мы", ours)], tail, text, facts)
            assert hand == [G_PLAIN] and state == (V_OURS_MONEY, G_PLAIN) and not conf, (tail, text, hand, state)   # была []
            assert rule == ["правило класса: %s; причина кода добавлена" % V_OURS_MONEY], rule
        hand, _state, _conf, rule, by_tail, paid = _run3i([("клиент", q), ("мы", ours)], tail, text, "backed")
        assert paid and hand == by_tail == [] and rule == ["правило класса: %s; причина кода не нужна" % V_PAID], (hand, rule)


def test_p3i_dictionaries_not_extended():
    """Слов в словари не добавлено: шаблоны выражений N4 (четыре прохода), признака входящего (`pay_asked`), предмета,
    слова оплаты, бумаги об оплате и общей причины оплаты побайтно те же, что на f023878 (отпечатки сняты с него)."""
    import hashlib

    def mark(rx):
        return hashlib.sha256(rx.pattern.encode("utf-8")).hexdigest()[:16]
    assert {n: mark(getattr(T, n)) for n in I_PRINTS_T} == I_PRINTS_T
    assert {n: mark(getattr(K, n)) for n in I_PRINTS_K} == I_PRINTS_K
    assert T._PAY_PASSES == (T._PAY_AFFIRM, T._PAY_FORMS, T._PAY_SUMS, T._PAY_CTX)


# ═══ п.3j: условие правила В «иной предмет во входящем» снято (решение координатора 11.10 по §9.2 и §9.3 шага 3i) ═══
# На 189d9c9 краткое подтверждение («Спасибо, получили!») не судилось, когда входящее без признака `pay_asked` называло
# предмет существующим словом `_PQ_TOPIC` без слова оплаты и без бумаги об оплате. Но слово предмета во входящем не
# говорит, ЧТО получено: платёжную бумагу («По QR отправил.», «На счёт закинул.») и предмет оплаты («За байк скинул.»,
# «За доставку закинул.») клиент называет так же обычно, как документ, — и ложное подтверждение уходило с ПУСТЫМИ
# причинами кода. Условие снято целиком; слов в словари не добавлено. Всё — настоящим путём адаптера (`_draft3g2`).
# §9.2 шага 3i ДОСЛОВНО (step3i/probe_bound3i.py, B_TAILS): входящее называет ПЛАТЁЖНЫЙ ИНСТРУМЕНТ словом предмета
J_9_2 = ["По QR отправил.", "По реквизитам отправил.", "По ссылке всё сделал.", "На счёт закинул.", "Инвойс закрыл.",
         "Реквизиты получил, отправил.", "По вашему QR всё ушло.", "Счёт закрыл.", "Done via QR.", "Sent via the link.",
         "Used the details you sent.", "Invoice settled."]
# §9.3 шага 3i ДОСЛОВНО (C_TAILS): входящее с общим словом предмета
J_9_3 = ["Ну что по моему вопросу?", "Есть новости по моему вопросу?", "Информацию получили?", "Сообщение дошло?",
         "Any news on my request?", "Did you get my message?"]
# СВОИ 26: входящее называет предмет (байк, доставка, шлем, бронь, паспорт, договор, страховка) и сообщает об оплате без
# слова оплаты кода — признака `pay_asked` нет, слова оплаты `_PQ_PAYWORD` и бумаги об оплате нет
J_OWN = ["За байк скинул.", "За доставку закинул.", "Отправил паспорт и закинул залог.", "За шлем тоже скинул.",
         "За скутер отправил.", "За бронь закинул.", "За страховку докинул.", "Всё за байк отправил, гляньте.",
         "За мотоцикл кинул, проверяйте.", "За доставку и шлем отправил.", "За байк всё ушло.", "Залог за байк закинул.",
         "За бронь байка скинул, гляньте.", "По договору всё закинул.", "За доставку байка кинул вам.",
         "Закинул за байк и за шлем.", "Sent it for the bike.", "Sent for the delivery.", "Done for the scooter.",
         "Covered the helmet too.", "Sorted the booking.", "Wired it for the delivery.", "All sent for the bike and helmet.",
         "Just did it for the insurance.", "Sent for the booking, have a look.", "It's sent for the bike, check please."]
# те из своих, у которых стоит общая причина кода по входящему НЕ об оплате («депозит», «наличие и брони…»): на 189d9c9
# черновик нёс только её — причины оплаты не было ни у одного из 26
J_OWN_OTHER_REASON = ["Отправил паспорт и закинул залог.", "За бронь закинул.", "Залог за байк закинул.",
                      "За бронь байка скинул, гляньте.", "Sorted the booking.", "Sent for the booking, have a look."]
# БЛИЗНЕЦЫ: ответ САМ называет предмет получения или несёт содержание — существующие исключения N4, причины нет
J_TWIN = [("Отправил вам фото паспорта, получили?", "Фото паспорта получили, спасибо!"),
          ("Отправил вам документы.", "Документы получили."),
          ("Договор подписал, отправил.", "Договор получили, проверим."),
          ("Буду в 10.", "Хорошо, ждём!"),
          ("Вот паспорт.", "Паспорт получили, спасибо!"),
          ("Фото прав отправил, дошло?", "Фото прав дошло, спасибо!"),
          ("Скинул фото байка.", "Фото получили, спасибо!"),
          ("Отправил вам фото паспорта, получили?", "Да, фото паспорта получили."),
          ("По QR отправил.", "Проверим и ответим."),
          ("За байк скинул.", "Спасибо! Проверим поступление и вернёмся с ответом."),
          ("За доставку закинул.", "Пока не видим, проверим и напишем."),
          ("Подписал.", "Отлично, тогда оформляем."),
          ("Готово.", "Хорошо, ждём вас завтра в 10:00."),
          ("Подписанный договор выслал.", "Договор получили, спасибо!"),
          ("Sent the passport photo.", "Passport photo received, thank you!"),
          ("Here is my licence.", "Licence received, thanks!"),
          ("Sent you the signed contract.", "Contract received, we will check it."),
          ("Did you get my documents?", "Yes, the documents are here, thank you!"),
          ("Sent it for the bike.", "Thanks! We will check and get back to you."),
          ("Sent you the documents.", "Documents received, thank you!")]
# ГРАНИЦА 9.1 на тех же входящих: ответ — не краткое подтверждение и вне форм N4 (тему никто не назвал)
J_BOUNDARY = [("За байк скинул.", "Отлично, тогда оформляю договор."), ("По QR отправил.", "Супер, ждём вас завтра!"),
              ("На счёт закинул.", "Замечательно, байк ваш!"), ("Sent it for the bike.", "Great, it's yours!"),
              ("Sent via the link.", "Perfect — you're good to go.")]


def _brief3j(tail):
    """Краткое подтверждение на языке хвоста (как в пробе шага 3i: кириллицы нет — английское)."""
    en = not re.search("[а-яёА-ЯЁ]", tail)
    return "Thank you, received!" if en else "Спасибо, получили!"


def _bad_j(tails):
    """Хвосты, где при «строки кассы нет» / «касса без второго источника» черновик краткого подтверждения НЕ несёт
    причину N4 правила В первой и ровно один раз (за ней — причины кода по входящему, если есть), либо журнал правило не
    называет, либо тему кто-то открыл; и хвосты, где при подтверждённой кодом оплате причина N4 появилась."""
    bad = []
    for tail in tails:
        text = _brief3j(tail)
        for facts in ("none", "cash"):
            hand, state, conf, rule, by_tail, paid = _run3i([], tail, text, facts)
            if hand != [T.PAY_WORDS] + by_tail or state[0] != V_NONE or rule or paid or T.pay_asked(tail) \
                    or not [ln for ln in conf if V_B_SAID in ln] or [w for w in by_tail if w in G_FAMILY[:1]]:
                bad.append((tail, text, facts, state[0], hand, by_tail, conf))
        hand, _state, conf, _rule, by_tail, paid = _run3i([], tail, text, "backed")
        if not paid or hand != by_tail or conf:
            bad.append((tail, text, "backed", hand, by_tail, conf))
    return bad


def test_p3j_9_2_payment_instrument_named_by_subject_word_has_n4_reason():
    """§9.2 шага 3i ДОСЛОВНО, 12 хвостов: входящее без признака `pay_asked` называет ПЛАТЁЖНЫЙ ИНСТРУМЕНТ словом предмета
    («По QR отправил.», «По реквизитам отправил.», «На счёт закинул.», «Инвойс закрыл.», «Sent via the link.») → краткое
    подтверждение («Спасибо, получили!»). На 189d9c9 контекст — «входящее называет иной предмет получения», причины кода
    `[]` у 10 из 12 (у двух — только общая причина по входящему: язык, «вопрос об оплате»), причины N4 нет ни у одного.
    Теперь при «строки кассы нет» и «касса без второго источника» причину N4 несут 12 из 12; при подтверждённой кодом
    оплате — ни один."""
    assert len(J_9_2) == 12
    for tail in J_9_2:
        assert T.pay_asked(tail) is False and T._PQ_TOPIC.search(tail), tail
        assert not T._PQ_PAYWORD.search(tail) and not T._PQ_PROOF.search(tail), tail
    bad = _bad_j(J_9_2)
    assert not bad, bad
    assert [t for t in J_9_2 if K.handoff(t, None)] == ["Done via QR.", "Invoice settled."]


def test_p3j_9_3_general_subject_word_has_n4_reason():
    """§9.3 шага 3i ДОСЛОВНО, 6 хвостов: входящее с общим словом предмета («Ну что по моему вопросу?», «Информацию
    получили?», «Any news on my request?», «Did you get my message?») → краткое подтверждение. На 189d9c9 причины кода
    `[]` у 6 из 6; теперь причину N4 при неподтверждённой кодом оплате несут 6 из 6, при подтверждённой — ни один."""
    assert len(J_9_3) == 6
    for tail in J_9_3:
        assert T.pay_asked(tail) is False and T._PQ_TOPIC.search(tail) and K.handoff(tail, None) == [], tail
    bad = _bad_j(J_9_3)
    assert not bad, bad


def test_p3j_own_subject_named_and_payment_reported_without_pay_word_has_n4_reason():
    """СВОИ 26 хвостов: входящее называет предмет и сообщает об оплате без слова оплаты кода («За байк скинул.», «За
    доставку закинул.», «Отправил паспорт и закинул залог.», «Sent it for the bike.», «Covered the helmet too.») →
    краткое подтверждение. На 189d9c9 причины N4 нет ни у одного из 26: у 20 причины кода `[]`, у 6 — только общая
    причина по входящему НЕ об оплате («депозит», «наличие и брони…»). Теперь причину N4 несут 26 из 26 — первой, перед
    причинами по входящему; при подтверждённой кодом оплате — ни один."""
    assert (len(J_OWN), len(J_OWN_OTHER_REASON)) == (26, 6) and not [t for t in J_OWN_OTHER_REASON if t not in J_OWN]
    for tail in J_OWN:
        assert T.pay_asked(tail) is False and T._PQ_TOPIC.search(tail), tail
        assert not T._PQ_PAYWORD.search(tail) and not T._PQ_PROOF.search(tail), tail
        assert not [r for r in K.handoff(tail, None) if r["words"] in G_FAMILY], tail      # общей причины ОПЛАТЫ по хвосту нет
    assert [t for t in J_OWN if K.handoff(t, None)] == J_OWN_OTHER_REASON
    bad = _bad_j(J_OWN)
    assert not bad, bad
    # после обмена о брони без слов оплаты — тот же исход: тему не открыл никто, причина N4 стоит
    for tail in J_OWN[:4] + J_OWN[16:20]:
        hist = I_NEUTRAL["ru" if re.search("[а-яё]", tail) else "en"]
        for facts in ("none", "cash"):
            hand, state, _conf, rule, by_tail, _paid = _run3i(hist, tail, _brief3j(tail), facts)
            assert hand == [T.PAY_WORDS] + by_tail and state[0] == V_NONE and not rule, (tail, facts, hand)


def test_p3j_twin_reply_names_subject_or_carries_content_no_reason():
    """Близнец (20 пар): ответ САМ называет предмет получения («Фото паспорта получили, спасибо!», «Документы
    получили.», «Passport photo received, thank you!») либо несёт содержание («Договор получили, проверим.», «Хорошо,
    ждём!», «Спасибо! Проверим поступление и вернёмся с ответом.», «Пока не видим, проверим и напишем.») — существующие
    исключения N4: причины нет при обоих наборах фактов, какое бы входящее ни было (с названным предметом, с сообщением
    об оплате без слова оплаты, бессловесное), журнал правило В не называет. Полезный правильный ответ не помечен."""
    assert len(J_TWIN) == 20
    for tail, text in J_TWIN:
        assert T.pay_asked(tail) is False and K.handoff(tail, None) == [], tail
        assert T.pay_brief(tail, False, False) == (V_B_BARE, True), tail                  # контекст тот же — решает ответ
        assert T._PayClaim(True).search(text) is None, (text, T._PAY_CLAIM.explain(text, True))
        for facts in ("none", "cash"):
            hand, state, conf, rule, _by, _paid = _run3i([], tail, text, facts)
            assert hand == [] and state[0] == V_NONE and not conf and not rule, (tail, text, facts, hand, conf)
    # тот же вход, но ответ — краткое подтверждение без названного предмета: причина есть (иначе близнец ничего не значит)
    assert _run3i([], "Отправил вам фото паспорта, получили?", "Да, получили, спасибо!", "cash")[0] == [T.PAY_WORDS]
    assert _run3i([], "За байк скинул.", "Спасибо, получили!", "cash")[0] == [T.PAY_WORDS]


def test_p3j_twin_confirmed_payment_adds_nothing():
    """Близнец «оплата подтверждена кодом» (касса аренды обращения + договор той же аренды): правило В не применяется —
    на всех хвостах §9.2, §9.3, своих 26 и на 12 парах `I_OTHER` список причин равен причинам кода по входящему, причины
    N4 нет, журнал правило не называет. Без условия «оплата не подтверждена» пометку получил бы полезный сценарий с PDF."""
    rows = [(t, _brief3j(t)) for t in J_9_2 + J_9_3 + J_OWN] + list(I_OTHER)
    assert len(rows) == 12 + 6 + 26 + 12
    bad = []
    for tail, text in rows:
        hand, _state, conf, rule, by_tail, paid = _run3i([], tail, text, "backed")
        if not paid or hand != by_tail or T.PAY_WORDS in hand or conf or [ln for ln in rule if "причина кода не нужна" not in ln]:
            bad.append((tail, text, hand, by_tail, conf))
    assert not bad, bad
    backed = T.accepted(_results_backed())
    for incoming in ("По QR отправил.", "За байк скинул.", "Отправил вам фото паспорта, получили?", "Ну что по моему вопросу?"):
        assert T.pay_brief(incoming, False, True) == (V_B_PAID, False), incoming
        for text in ("Спасибо, получили!", "Да, всё пришло.", chr(0x1F44D), "Да, 9990 получили."):
            assert T.money_roles(text, backed, asked=False, incoming=incoming) == [], (incoming, text)


def test_p3j_twin_no_incoming_text_as_before():
    """Близнец «текста входящего у судьи нет»: судью зовут без `incoming` (так его звали до шага 3i) — краткое
    подтверждение без признака `pay_asked` причины не получает ни при каких фактах; исход контекста — «текста входящего
    у судьи нет». Правило В судит только по входящему, текст которого передан."""
    for paid in (False, True):
        assert T.pay_brief(None, False, paid) == (V_B_UNSEEN, False)
    for text in ("Спасибо, получили!", "Да, всё пришло.", "Да, получили, спасибо!", "Thank you, received!", chr(0x1F44D),
                 "Да, 9990 получили."):
        for res in (_results_rent_only(), _results_no_second()):
            assert T.judge(text, None, [dict(r) for r in res], T.Journal("5678"), asked=False)[0] == [], text
            assert T.judge(text, None, [dict(r) for r in res], T.Journal("5678"), asked=False, incoming=None)[0] == [], text
            facts = T.accepted([dict(r) for r in res])
            assert T.money_roles(text, facts, asked=False) == [] and T.money_roles(text, facts) == [], text
            # тот же вызов С текстом входящего — причина есть (иначе близнец ничего не значит)
            assert T.judge(text, None, [dict(r) for r in res], T.Journal("5678"), asked=False,
                           incoming="За байк скинул.")[0] == [T.PAY_WORDS], text


def test_p3j_adapter_passes_tail_text_to_judge():
    """Устройство: адаптер передаёт судье текст ХВОСТА клиента (`info["question"]`, как его собрал `build`), а не
    предыдущий блок клиента и не пустоту — правило В судит по входящему, текст которого у судьи ЕСТЬ. После снятия
    условия «иной предмет» содержимое текста исход правила не меняет (важен сам факт текста), поэтому передачу
    проверяет прямой перехват вызова `T.judge`, а не причины черновика."""
    seen, orig = [], T.judge

    def spy(*args, **kw):
        seen.append(kw.get("incoming", "ключа incoming нет"))
        return orig(*args, **kw)
    history = [("клиент", "Отправил вам фото паспорта."), ("мы", "Спасибо, паспорт получили.")]
    T.judge = spy
    try:
        out, a, _s, _logs = _draft3g2(history, "За байк скинул.", "Спасибо, получили!", "cash")
    finally:
        T.judge = orig
    assert seen == ["За байк скинул."] and a.last["info"]["question"] == "За байк скинул.", seen
    assert a.last["info"]["before"][0] == "Отправил вам фото паспорта." and out["handoff"] == [T.PAY_WORDS], out["handoff"]


def test_p3j_changed_expectations_of_prior_lists_named():
    """ИЗМЕНЁННЫЕ шагом 3j ожидания прежних списков — ПОИМЁННО (три хвоста `G3J_NAMED`, которые называют предмет; на
    189d9c9 краткое подтверждение на них не судилось): «Отправил вам фото паспорта, получили?» → «Да, получили,
    спасибо!» (строка `G_CLOSED` и случай «doc» проверки `…p3e_adapter_passes_sign…`) — было `[]`, стало `[N4]`; «Any
    luck with the helmet?» → «Yes, all good, thank you!» (первая цепочка `G2_CONFIRMED_IN_CHAT`) — к причине класса
    добавилась причина N4; «Есть новости по моему вопросу?» → «Да, всё получили, спасибо. Ждём вас завтра.» (строка
    `G_PATH_C`) — то же. Причина N4 — первой; причина класса — прежняя; иных изменений в прежних списках нет."""
    for tail in G3J_NAMED:
        assert T.pay_asked(tail) is False and T._PQ_TOPIC.search(tail) and not T._PQ_PAYWORD.search(tail), tail
    assert ([], QD_RU, "Да, получили, спасибо!") in G_CLOSED and QD_RU == G3J_NAMED[2]
    assert G2_CONFIRMED_IN_CHAT[0][1:3] == (G3J_NAMED[0], "Yes, all good, thank you!")
    assert (G3J_NAMED[1], "Да, всё получили, спасибо. Ждём вас завтра.") in G_PATH_C
    for facts in ("none", "cash"):
        out, a, _s, _logs = _draft3g([], QD_RU, "Да, получили, спасибо!", facts)
        assert out["handoff"] == [T.PAY_WORDS] and _topic3g(a)[0] == V_NONE, (facts, out["handoff"])
        history, tail, text, _opener = G2_CONFIRMED_IN_CHAT[0]
        out, a, _s, _logs = _draft3g2(history, tail, text, facts)
        assert out["handoff"] == [T.PAY_WORDS, G_PLAIN] and _state3g2(a) == (V_BACK_OURS, G_PLAIN), (facts, out["handoff"])
        out, a, _s, _logs = _draft3g(G_H_CHECK, G3J_NAMED[1], "Да, всё получили, спасибо. Ждём вас завтра.", facts)
        assert out["handoff"] == [T.PAY_WORDS, G_SAID] and _topic3g(a)[0] == V_PREV, (facts, out["handoff"])
    for history, tail, text in (([], QD_RU, "Да, получили, спасибо!"), G2_CONFIRMED_IN_CHAT[0][:3],
                                (G_H_CHECK, G3J_NAMED[1], "Да, всё получили, спасибо. Ждём вас завтра.")):
        out, a, _s, _logs = _draft3g2(history, tail, text, "backed")
        assert T.pay_confirmed(a.last["tools"]["journal"].facts) and T.PAY_WORDS not in out["handoff"], (tail, out["handoff"])


def test_p3j_boundary_answer_outside_n4_forms_still_no_reason():
    """ГРАНИЦА ПОСЛЕ ШАГА — проверка ФИКСИРУЕТ нынешний исход и НЕ означает «закрыто» (граница 9.1 шага 3i на тех же
    входящих): тему никто не назвал, а ответ — не краткое подтверждение и вне форм N4 («Отлично, тогда оформляю
    договор.», «Замечательно, байк ваш!», «Great, it's yours!») — причины кода НЕТ при обоих наборах фактов и на
    входящее «За байк скинул.», «По QR отправил.». Снятие условия судит только существующие формы N4; слово в словарь
    по решению не добавляется. (Шаг 3l: сумма, способ, счёт или бумага в НАШЕМ ответе тему теперь открывают — здесь
    истории нет вовсе, деньги не называл никто: остаток (б) шага 3l, исход прежний.)"""
    assert len(J_BOUNDARY) == 5
    for tail, text in J_BOUNDARY:
        assert T.pay_brief(tail, False, False) == (V_B_BARE, True) and T._PayClaim(True).search(text) is None, text
        for facts in ("none", "cash"):
            hand, state, conf, rule, _by, _paid = _run3i([], tail, text, facts)
            assert hand == [] and state[0] == V_NONE and not conf and not rule, (tail, text, hand)      # ← остаток, не успех


# ═══ п.3k: правило В судит слово согласия отдельным предложением только в ответе, ЦЕЛИКОМ кратком (решение 11.10) ═══
# Находка §9.7 шага 3j: форма шага 3f «слово согласия во главе предложения» (`q3`) судила ОТДЕЛЬНОЕ предложение-согласие
# как «да» и тогда, когда следующим предложением ответ нёс содержание. Под признаком правила В (входящее не об оплате,
# оплата кодом не подтверждена) причину «оплата не подтверждена сверкой» получали обычные верные ответы («Пришлите,
# пожалуйста, договор.» — «Конечно! Договор во вложении.»), а тот же текст через запятую («Конечно, договор во
# вложении.») — нет: исход зависел от точки вместо запятой. Решение: под признаком, который поставило правило В, слово
# согласия отдельным предложением — утверждение оплаты только в ответе, ЦЕЛИКОМ кратком; у ответа с содержательным
# предложением исход назван `PC_CONTENT`. Входящее об оплате — форма судится, как до шага. Слов в словари не добавлено.
# Всё — настоящим путём адаптера (`_draft3g2`), причин модели нет.
V_CONTENT = "слово согласия — отдельным предложением ответа с содержанием, входящее не об оплате"
# вид (а) — ДОСЛОВНО step3j/probe_cost3j.py: согласие отдельным предложением + содержание (на 85f1641 причина N4 у 10 из 10)
K_97 = [("А шлем дадите?", "Разумеется! Шлем тоже будет готов."), ("А шлем дадите?", "Да. Шлем дадим бесплатно."),
        ("Доставка к отелю есть?", "Конечно! Привезём к 10:00."), ("Можно забрать байк завтра?", "Да, конечно. Ждём вас в 10."),
        ("Пришлите, пожалуйста, договор.", "Конечно! Договор во вложении."),
        ("Вы работаете в воскресенье?", "Да. Работаем с 9 до 20."),
        ("Можно продлить на два дня?", "Да, конечно! Продление — 779 бат в сутки."),
        ("Is a helmet included?", "Sure! A helmet is included."),
        ("Can you send me the contract?", "Of course! The contract is attached."),
        ("Do you deliver to Kata?", "Yes. Delivery to Kata is available.")]
# у этих ответов пробы есть причина кода НЕ об оплате (время приезда; сумма без опоры) — она стоит при любых фактах
K_97_ELSE = ["Конечно! Привезём к 10:00.", "Да, конечно! Продление — 779 бат в сутки.", "Конечно, привезём к 10:00."]
# вид (б) — ДОСЛОВНО: согласие и содержание в ОДНОМ предложении; вид (в) — ДОСЛОВНО: содержание без слова согласия
K_97_SAME = [("А шлем дадите?", "Да, шлем дадим бесплатно."), ("Доставка к отелю есть?", "Конечно, привезём к 10:00."),
             ("Пришлите, пожалуйста, договор.", "Конечно, договор во вложении."),
             ("Вы работаете в воскресенье?", "Да, работаем с 9 до 20."), ("Is a helmet included?", "Sure, a helmet is included."),
             ("Can you send me the contract?", "Of course, the contract is attached.")]
K_97_PLAIN = [("А шлем дадите?", "Шлем дадим бесплатно."), ("Пришлите, пожалуйста, договор.", "Договор во вложении."),
              ("Вы работаете в воскресенье?", "Работаем с 9 до 20 каждый день."),
              ("Can you send me the contract?", "The contract is attached.")]
# СВОИ 22 пары вида (а): русские 14 и английские 8; входящее называет предмет (`_PQ_TOPIC`) у 13, не называет у 9
K_OWN = [
    ("Можно шлем побольше?", "Конечно. Подберём шлем по размеру."),
    ("Договор можно на английском?", "Да. Договор будет на английском и на русском."),
    ("Байк привезёте к отелю?", "Да! Привезём байк к отелю."),
    ("Пришлёте фото байка?", "Конечно! Фото пришлю следующим сообщением."),
    ("Адрес офиса подскажете?", "Да, конечно. Мы на Раваи, рядом с пирсом."),
    ("Страховка входит?", "Разумеется. Страховка входит в аренду."),
    ("Пришлите, пожалуйста, договор.", "Да. Договор отправляю файлом."),
    ("Можно договор на почту?", "Безусловно. Договор пришлём на почту сегодня."),
    ("Вы открыты завтра?", "Да. Работаем каждый день."),
    ("Можно приехать после шести?", "Конечно. Ждём вас до восьми вечера."),
    ("А детское кресло дадите?", "Да. Детское кресло дадим бесплатно."),
    ("Второй ключ дадите?", "Разумеется! Второй ключ положим в бардачок."),
    ("Можно приехать пораньше?", "Да, конечно. Приезжайте к девяти."),
    ("С собакой можно?", "Естественно. Собаку берите с собой."),
    ("Is delivery to the hotel possible?", "Yes. We deliver to your hotel."),
    ("Could you send the contract in English?", "Sure. The contract will be in English."),
    ("Is insurance included?", "Of course! Basic insurance is included."),
    ("Can I see the bike first?", "Certainly. You can see the bike at our office."),
    ("Do you have a bigger helmet?", "Absolutely. Helmets come in every size."),
    ("Are you open on Sunday?", "Yes. We are open every day."),
    ("Do you have a child seat?", "Absolutely. A child seat is free of charge."),
    ("Can I come after six?", "Sure! We are here until eight.")]
# содержательное предложение стоит ПЕРЕД словом согласия — ответ тоже не «целиком краткий»
K_BEFORE = [("А шлем дадите?", "Шлем дадим бесплатно. Разумеется!"),
            ("Пришлите, пожалуйста, договор.", "Договор во вложении. Да, конечно."),
            ("Can you send me the contract?", "The contract is attached. Sure!"),
            ("Вы работаете в воскресенье?", "Здравствуйте! Да. Работаем с 9 до 20.")]
# БЛИЗНЕЦ «ответ ЦЕЛИКОМ краткий»: (входящее не об оплате, ответ, сколько кратких предложений) — причина N4 остаётся
K_BRIEF = [
    ("Готово.", "Да.", 1), ("Отправил вам фото паспорта.", "Конечно!", 1), ("Подписал.", "Спасибо, получили!", 1),
    ("А шлем дадите?", "Да. Спасибо!", 2), ("Sent.", "Sure! " + THUMB, 2), ("Отправил.", "Да. Получили.", 2),
    ("Всё отправил.", "Конечно. Хорошего дня!", 2), ("Signed.", "Of course. Thank you!", 2),
    ("Отправил.", "Да. Уже.", 2), ("Всё отправил.", "Да, конечно. Всё у нас.", 2), ("Sent.", "Yes. Already.", 2),
    ("Отправил.", "Да. Сегодня утром.", 2), ("Sent.", "Yes. Just now.", 2),
    ("Отправил вам документы.", "Да, уже. Хорошего дня!", 2), ("Done.", "Yes, already. Cheers!", 2),
    ("Вот.", "Да, уже. Принято, спасибо!", 2),
    ("Готово.", "Да. Конечно. Спасибо!", 3), ("Done.", "Yes. Sure. Thanks!", 3),
    ("Скинул фото байка.", "Да! Получили. Спасибо!", 3), ("Sent you the documents.", "Yes. Got it. Thanks!", 3),
    ("Готово.", "Да. Уже. Спасибо!", 3), ("Done.", "Yes. Already. Thank you!", 3),
    ("Здравствуйте! Отправил.", "Здравствуйте! Да. Уже.", 3)]
# те из них, где утверждение даёт ТОЛЬКО форма «слово согласия во главе предложения» (`q3`): решает определение шага
K_BRIEF_Q3 = ["Да. Уже.", "Да, конечно. Всё у нас.", "Yes. Already.", "Да. Сегодня утром.", "Yes. Just now.",
              "Да, уже. Хорошего дня!", "Yes, already. Cheers!", "Да, уже. Принято, спасибо!", "Да. Уже. Спасибо!",
              "Yes. Already. Thank you!", "Здравствуйте! Да. Уже."]
# БЛИЗНЕЦ «входящее ОБ ОПЛАТЕ» (`pay_asked`) + «Да. <содержание>» — форма судится, как до шага
K_ASKED = [("Деньги пришли?", "Да. Ждём вас в 10."),
           ("Я перевёл оплату за аренду, деньги пришли?", "Конечно. Ждём вас завтра в 10:00."),
           ("Оплатил аренду, проверьте, пожалуйста.", "Да. Договор во вложении."),
           ("Скинул вам 7790 на карту.", "Разумеется! Шлем тоже будет готов."),
           ("Оплату получили?", "Да. Работаем с 9 до 20."),
           ("I sent the payment for the rental, did you receive it?", "Sure! The bike is ready for tomorrow."),
           ("I've paid, please confirm.", "Yes. Delivery to Kata is available."),
           ("Did you get my payment?", "Of course! The contract is attached.")]
# КОНТРОЛЬ: форма получения (`q1`, `q2` — сказуемое получения без предмета) шагом НЕ сужается — цена стороны отказа
K_RCV = [("Отправил вам фото паспорта.", "Получили, спасибо! Ждём вас завтра в 10."),
         ("Отправил.", "Да, получили. Ждём вас завтра."),
         ("Есть новости по моему вопросу?", "Да, всё получили, спасибо. Ждём вас завтра."),
         ("Sent.", "Got it, thanks! See you tomorrow at 10."), ("Готово.", "Всё в порядке. Ждём вас завтра.")]
# ГРАНИЦА (была и до шага): краткий ответ ОДНИМ предложением, где рядом со словом согласия стоят и слово вне словаря
# согласия («уже»), и вежливость либо одобрение, — вне форм N4; тот же ответ двумя предложениями причину несёт
K_GAP = [("Отправил вам документы.", "Да, уже, хорошего дня!", "Да, уже. Хорошего дня!"),
         ("Done.", "Yes, already, cheers!", "Yes, already. Cheers!"),
         ("Вот.", "Да, уже, принято, спасибо!", "Да, уже. Принято, спасибо!")]


def _comma3k(text):
    """Тот же ответ ОДНИМ предложением через запятую: первый знак конца предложения → запятая, следующая буква — строчная."""
    m = re.search(r"[.!]\s+(\S)", text)
    return text[:m.start()] + ", " + m.group(1).lower() + text[m.end():]


def _names3k(text, by, asked=True):
    """Имена исходов совпадений определения N4 при признаке `asked`, который поставил названный контекст `by`."""
    return [v for _m, v in T._PayClaim(asked, (), by).explain(text)]


def _forms3k(text):
    """Формы краткого подтверждения (группы четвёртого прохода), совпавшие в ответе."""
    return [k for rx, m in T._PayClaim._matches(text) if rx is T._PAY_CTX for k in ("q1", "q2", "q3", "q4", "q5") if m.group(k)]


def test_p3k_9_7_agreement_sentence_with_content_no_reason():
    """Находка §9.7 шага 3j — 10 пар пробы ДОСЛОВНО (вид (а)): входящее не об оплате, ответ — слово согласия отдельным
    предложением и содержание следующим («Конечно! Договор во вложении.», «Да. Шлем дадим бесплатно.», «Sure! A helmet
    is included.»). На 85f1641 причину «оплата не подтверждена сверкой» несли 10 из 10; теперь при «строки кассы нет» и
    «касса без второго источника» её нет ни у одной: список причин равен причинам того же черновика при подтверждённой
    кодом оплате (у двух пар — причина НЕ об оплате: время приезда, сумма без опоры), журнал правило В не называет, исход
    формы назван `PC_CONTENT`. Виды (б) и (в) пробы — как были: причины нет."""
    assert (len(K_97), len(K_97_SAME), len(K_97_PLAIN)) == (10, 6, 4)
    for tail, text in K_97 + K_97_SAME + K_97_PLAIN:
        assert T.pay_asked(tail) is False and T.pay_brief(tail, False, False) == (V_B_BARE, True), tail
        base = _run3i([], tail, text, "backed")[0]
        assert T.PAY_WORDS not in base and bool(base) == (text in K_97_ELSE), (text, base)
        for facts in ("none", "cash"):
            hand, state, conf, rule, by_tail, paid = _run3i([], tail, text, facts)
            assert hand == base and state[0] == V_NONE and not conf and not rule and not by_tail and not paid, \
                (tail, text, facts, hand, conf)
    for _tail, text in K_97:
        assert _names3k(text, T.PB_BARE) == [V_CONTENT], (text, _names3k(text, T.PB_BARE))
        assert _forms3k(text) == ["q3"], (text, _forms3k(text))
    for _tail, text in K_97_SAME:
        assert _names3k(text, T.PB_BARE) == [V_OTHER] and _names3k(text, T.PB_ASKED) == [V_OTHER], text
    for _tail, text in K_97_PLAIN:
        assert _names3k(text, T.PB_BARE) == [], text


def test_p3k_own_agreement_sentence_with_content_no_reason():
    """СВОИ 22 пары того же вида (на 85f1641 причина N4 у 22 из 22): русские 14 и английские 8; входящее называет
    предмет существующим словом (`_PQ_TOPIC`: шлем, договор, байк, фото, адрес, страховка, delivery, contract) у 13 и не
    называет у 9 — причины нет ни у одной при обоих наборах фактов, с историей и без неё; исход формы — `PC_CONTENT`."""
    assert len(K_OWN) == 22
    ru = [p for p in K_OWN if re.search("[а-яё]", p[1])]
    assert (len(ru), len(K_OWN) - len(ru), len([p for p in K_OWN if T._PQ_TOPIC.search(p[0])])) == (14, 8, 13)
    for tail, text in K_OWN:
        assert T.pay_asked(tail) is False and T.pay_brief(tail, False, False) == (V_B_BARE, True), tail
        assert _forms3k(text) == ["q3"], (text, _forms3k(text))
        for facts in ("none", "cash"):
            hand, state, conf, rule, by_tail, paid = _run3i([], tail, text, facts)
            assert hand == [] and state[0] == V_NONE and not conf and not rule and not by_tail and not paid, \
                (tail, text, facts, hand, conf)
    for tail, text in K_OWN[:3] + K_OWN[14:17]:                 # после обмена о брони без слов оплаты — тот же исход
        hist = I_NEUTRAL["ru" if re.search("[а-яё]", text) else "en"]
        for facts in ("none", "cash"):
            hand, state, conf, rule, _by, _paid = _run3i(hist, tail, text, facts)
            assert hand == [] and state[0] == V_NONE and not conf and not rule, (tail, text, facts, hand)
    for _tail, text in K_OWN:
        assert _names3k(text, T.PB_BARE) == [V_CONTENT], (text, _names3k(text, T.PB_BARE))


def test_p3k_content_before_agreement_sentence_no_reason():
    """Содержательное предложение стоит ПЕРЕД словом согласия («Договор во вложении. Да, конечно.», «The contract is
    attached. Sure!») либо между приветствием и содержанием («Здравствуйте! Да. Работаем с 9 до 20.»): ответ не «целиком
    краткий» — причины нет (на 85f1641 была у 4 из 4), исход формы — `PC_CONTENT`."""
    assert len(K_BEFORE) == 4
    for tail, text in K_BEFORE:
        assert T.pay_asked(tail) is False, tail
        for facts in ("none", "cash"):
            hand, state, conf, rule, _by, _paid = _run3i([], tail, text, facts)
            assert hand == [] and state[0] == V_NONE and not conf and not rule, (tail, text, facts, hand)
    for _tail, text in K_BEFORE:
        assert _names3k(text, T.PB_BARE) == [V_CONTENT], (text, _names3k(text, T.PB_BARE))


def test_p3k_same_text_through_comma_same_outcome():
    """Исход не зависит от точки вместо запятой: у 10 пар пробы и 22 своих ответ двумя предложениями («Конечно! Договор
    во вложении.») и тот же текст ОДНИМ предложением через запятую («Конечно, договор во вложении.») дают один список
    причин при обоих наборах фактов (на 85f1641 — разные: через точку стояла причина N4). Имена исходов формы: через
    точку — `PC_CONTENT`, через запятую — `PC_OTHER`. Ответ целиком краткий — причина есть и через точку, и через
    запятую («Да. Спасибо!» / «Да, спасибо!», «Да. Уже.» / «Да, уже.»)."""
    for tail, text in K_97 + K_OWN:
        one = _comma3k(text)
        assert one != text and not K._SENTENCE.search(one.rstrip(".!")), (text, one)
        for facts in ("none", "cash"):
            a, b = _run3i([], tail, text, facts)[0], _run3i([], tail, one, facts)[0]
            assert a == b and T.PAY_WORDS not in a, (tail, text, one, facts, a, b)
    gap = [dot for _tail, _one, dot in K_GAP]
    both = [(tail, text) for tail, text, n in K_BRIEF if n == 2 and text not in gap]
    assert len(both) == 10
    for tail, text in both:
        for facts in ("none", "cash"):
            assert _run3i([], tail, text, facts)[0] == _run3i([], tail, _comma3k(text), facts)[0] == [T.PAY_WORDS], (tail, text)
    for _tail, text in K_97 + K_OWN:
        assert _names3k(_comma3k(text), T.PB_BARE) == [V_OTHER] and _names3k(text, T.PB_BARE) == [V_CONTENT], text


def test_p3k_twin_whole_brief_reply_keeps_reason():
    """Близнец «ответ ЦЕЛИКОМ краткий» (23 пары; одно, два и три кратких предложения подряд): входящее не об оплате, в
    ответе нет ни одного содержательного предложения («Да.», «Конечно!», «Да. Спасибо!», «Sure! 👍», «Спасибо,
    получили!», «Да. Уже.», «Да. Конечно. Спасибо!», «Yes. Already. Thank you!», «Здравствуйте! Да. Уже.») — причина N4
    стоит при обоих наборах фактов, журнал называет правило В; при подтверждённой кодом оплате её нет. У 11 из них
    утверждение даёт ТОЛЬКО форма «слово согласия во главе предложения» — их держит определение шага (`_whole`): другое
    предложение ответа само состоит из слов согласия («Уже.», «Сегодня утром.») либо вместе со словом согласия
    составляет ответ-согласие («Хорошего дня!», «Принято, спасибо!», «Cheers!»)."""
    assert len(K_BRIEF) == 23 and [len([1 for _t, _x, n in K_BRIEF if n == k]) for k in (1, 2, 3)] == [3, 13, 7]
    assert [x for _t, x, _n in K_BRIEF if _forms3k(x) == ["q3"]] == K_BRIEF_Q3 and len(K_BRIEF_Q3) == 11
    for tail, text, _n in K_BRIEF:
        assert T.pay_asked(tail) is False and T.pay_brief(tail, False, False) == (V_B_BARE, True), tail
        names = _names3k(text, T.PB_BARE)
        assert V_CLAIM in names and (V_CONTENT not in names or text in ("Да. Получили.", "Да! Получили. Спасибо!",
                                                                         "Yes. Got it. Thanks!")), (text, names)
        for facts in ("none", "cash"):
            hand, state, conf, rule, by_tail, paid = _run3i([], tail, text, facts)
            assert hand == [T.PAY_WORDS] and state[0] == V_NONE and not rule and not by_tail and not paid, (tail, text, hand)
            assert [ln for ln in conf if V_B_SAID in ln], (tail, text, conf)
        assert _run3i([], tail, text, "backed")[0] == [], (tail, text)
    for text in K_BRIEF_Q3:
        assert _names3k(text, T.PB_BARE) == [V_CLAIM] == _names3k(text, T.PB_ASKED), text


def test_p3k_twin_incoming_about_payment_agreement_sentence_as_before():
    """Близнец «входящее ОБ ОПЛАТЕ» (`pay_asked`; 8 пар): «Деньги пришли?» — «Да. Ждём вас в 10.», «Оплатил аренду,
    проверьте, пожалуйста.» — «Да. Договор во вложении.» — слово согласия отдельным предложением судится, как до шага:
    причина N4 стоит первой при обоих наборах фактов, журнал называет её прежними словами (не правилом В), тема оплаты
    открыта хвостом. ТОТ ЖЕ ответ под признаком правила В — `PC_CONTENT`. Прежний список шага 3f (`F1_YES`, 14 ответов):
    при входящем об оплате — утверждение; под признаком правила В — нет у 12, а два ответа из согласия и прощания
    («Definitely. See you tomorrow.») — ответ-согласие шага 3f ЦЕЛИКОМ (`q5`), их причина остаётся (цена стороны отказа)."""
    assert len(K_ASKED) == 8
    for tail, text in K_ASKED:
        assert T.pay_asked(tail) is True and T.pay_brief(tail, True, False) == (V_B_ASKED, True), tail
        assert _names3k(text, T.PB_ASKED) == [V_CLAIM] == _names3k(text, None), (text, _names3k(text, T.PB_ASKED))
        assert _names3k(text, T.PB_BARE) == [V_CONTENT], text
        for facts in ("none", "cash"):
            hand, state, conf, rule, _by, paid = _run3i([], tail, text, facts)
            assert hand[0] == T.PAY_WORDS and hand.count(T.PAY_WORDS) == 1 and state[0] == V_TAIL and not paid, (tail, hand)
            assert [ln for ln in conf if I_OLD_SAID in ln] and not [ln for ln in conf if V_B_SAID in ln], (tail, conf)
        assert T.PAY_WORDS not in _run3i([], tail, text, "backed")[0], (tail, text)
    assert len(F1_YES) == 14
    whole = [text for text, _q in F1_YES if _forms3k(text) == ["q5"]]   # согласие и прощание — ответ-согласие шага 3f целиком
    assert whole == ["Definitely. See you tomorrow.", "Indeed. See you tomorrow."], whole
    for text, question in F1_YES:
        assert T.pay_asked(question) is True, question
        assert T._PayClaim(True, (), T.PB_ASKED).search(text) is not None and T._PayClaim(True).search(text) is not None, text
        if text in whole:                                   # ответ целиком краткий — причина и под правилом В (цена 9.6)
            assert _names3k(text, T.PB_BARE) == [V_CLAIM], text
            continue
        assert T._PayClaim(True, (), T.PB_BARE).search(text) is None and V_CONTENT in _names3k(text, T.PB_BARE), text


def test_p3k_twin_confirmed_payment_adds_nothing():
    """Близнец «оплата подтверждена кодом» (касса аренды обращения + договор той же аренды): правило В не применяется —
    ни у вида §9.7 (10 + 22 + 4), ни у ответа, целиком краткого (23), ни при входящем об оплате (8), ни у формы
    получения (5) причины N4 нет, журнал правило не называет."""
    rows = K_97 + K_OWN + K_BEFORE + [(t, x) for t, x, _n in K_BRIEF] + K_ASKED + K_RCV
    assert len(rows) == 10 + 22 + 4 + 23 + 8 + 5
    bad = []
    for tail, text in rows:
        hand, _state, conf, rule, by_tail, paid = _run3i([], tail, text, "backed")
        if not paid or T.PAY_WORDS in hand or conf or [ln for ln in rule if "причина кода не нужна" not in ln]:
            bad.append((tail, text, hand, by_tail, conf, rule))
    assert not bad, bad


def test_p3k_control_receipt_form_not_narrowed():
    """КОНТРОЛЬ п.3k (зелёный и на 85f1641) — ЦЕНА стороны отказа, НЕ успех: форма получения (`q1`, `q2` — сказуемое
    получения или «всё в порядке» без предмета) шагом не сужается. «Отправил вам фото паспорта.» — «Получили, спасибо!
    Ждём вас завтра в 10.» несёт причину N4 и с содержательным вторым предложением: тот же текст через запятую несёт её
    так же (исход от точки не зависит), а краткое получение без названного предмета — то, что правило В и судит."""
    assert len(K_RCV) == 5
    for tail, text in K_RCV:
        assert T.pay_asked(tail) is False, tail
        for facts in ("none", "cash"):
            assert _run3i([], tail, text, facts)[0] == [T.PAY_WORDS], (tail, text, facts)
            assert _run3i([], tail, _comma3k(text), facts)[0] == [T.PAY_WORDS], (tail, _comma3k(text), facts)


def test_p3k_definition_named_outcome_and_context_name():
    """Определение шага: исход НАЗВАН (`PC_CONTENT`), имя контекста доходит до формы (`_PayClaim.by` — исход
    `pay_brief`), а без имени и при иных именах всё судится, как до шага. `_whole` — ответ целиком краткий? — на
    существующих формах: другое предложение из одних слов согласия (`_PQ_ONLY`) либо вместе со словом согласия —
    ответ-согласие (`q5`); предложение-получение судит своя форма. Исход — непустое имя на каждой дороге (храповик);
    `search` говорит «утверждение» ровно тогда, когда так назван хотя бы один исход. Судья денежных ролей и судья:
    под правилом В содержательный ответ причины не получает, при входящем об оплате — получает."""
    assert T.PC_CONTENT == V_CONTENT and T._PAY_CLAIM.by is None and T._PayClaim(True).by is None
    assert T._PayClaim(True, (), T.PB_BARE).by == V_B_BARE
    for text, want in (("Да. Шлем дадим бесплатно.", V_CONTENT), ("Да.", V_CLAIM), ("Да. Спасибо!", V_CLAIM),
                       ("Да. Уже.", V_CLAIM), ("Да, уже. Хорошего дня!", V_CLAIM), ("Здравствуйте! Да. Уже.", V_CLAIM),
                       ("Да. Уже. Спасибо большое, Алексей!", V_CLAIM), ("Да!!! Уже…", V_CLAIM), ("Да\nУже", V_CLAIM),
                       ("Шлем дадим бесплатно. Да.", V_CONTENT), ("Да. Получили.", V_CONTENT), ("Да. Хорошо, ждём!", V_CONTENT),
                       ("Да. Спасибо за информацию.", V_CONTENT), ("Да… Шлем дадим.", V_CONTENT), ("Да\nШлем дадим", V_CONTENT),
                       ("Sure! " + THUMB, V_CLAIM), ("Yes. Already. Cheers!", V_CLAIM), ("Yes. See you at ten.", V_CONTENT)):
        m = [m for rx, m in T._PayClaim._matches(text) if rx is T._PAY_CTX and m.group("q3")]
        got = "формы q3 в ответе нет"
        if m:
            fin = T._PAY_END.search(text, m[0].end())
            got = T._PayClaim._whole(text, m[0].start(), len(text) if fin is None else fin.start(), m[0].group("q3"))
        elif want == V_CLAIM:                             # ответ целиком из согласия ловит форма q5 — до `_whole` не доходит
            got = V_CLAIM if _forms3k(text) == ["q5"] else got
        assert got == want, (text, got)
    assert _names3k("Да. Получили.", T.PB_BARE) == [V_CONTENT, V_CLAIM]         # получение судит своя форма — утверждение
    texts = [x for _t, x in K_97 + K_97_SAME + K_97_PLAIN + K_OWN + K_BEFORE + K_ASKED + K_RCV] + [x for _t, x, _n in K_BRIEF]
    for by in (None, T.PB_ASKED, T.PB_BARE, T.PB_PAID, T.PB_UNSEEN):
        for text in texts:
            for asked in (True, False):
                got = T._PayClaim(asked, (), by).explain(text)
                assert all(isinstance(v, str) and v.strip() for _m, v in got), (text, by, got)
                assert (V_CLAIM in [v for _m, v in got]) == bool(T._PayClaim(asked, (), by).search(text)), (text, by, got)
            if by != T.PB_BARE:                             # иное имя контекста — как без имени (до шага)
                assert _names3k(text, by) == _names3k(text, None), (text, by)
            assert V_CLAIM not in _names3k(text, by, asked=False), (text, by)       # без признака — не утверждение
    unpaid = [[], T.accepted(_results_rent_only()), T.accepted(_results_no_second())]
    for facts in unpaid:
        for incoming, text in K_97[:2] + K_97[4:5] + K_OWN[:2]:
            assert T.money_roles(text, facts, asked=False, incoming=incoming) == [], (incoming, text)
            assert T.money_roles(text, facts, asked=False) == [] and T.money_roles(text, facts) == [], text
            got = T.money_roles(text, facts, asked=True, incoming="Деньги пришли?")
            assert [w for w, _why in got] == [T.PAY_WORDS] and got[0][1].startswith(I_OLD_SAID + ": "), (text, got)
            assert [w for w, _why in T.money_roles(text, facts, asked=True)] == [T.PAY_WORDS], text    # признак без текста
        for text in ("Да.", "Да. Уже.", "Конечно! Спасибо!", "Yes. Already. Thank you!"):
            got = T.money_roles(text, facts, asked=False, incoming="Готово.")
            assert [w for w, _why in got] == [T.PAY_WORDS] and got[0][1].startswith(V_B_SAID + ": "), (text, got)
    for res in (_results_rent_only(), _results_no_second()):
        assert T.judge("Да. Шлем дадим бесплатно.", None, [dict(r) for r in res], T.Journal("5678"), asked=False,
                       incoming="А шлем дадите?")[0] == []
        assert T.judge("Да. Шлем дадим бесплатно.", None, [dict(r) for r in res], T.Journal("5678"), asked=True,
                       incoming="Деньги пришли?")[0] == [T.PAY_WORDS]
        assert T.judge("Да.", None, [dict(r) for r in res], T.Journal("5678"), asked=False,
                       incoming="А шлем дадите?")[0] == [T.PAY_WORDS]
    backed = T.accepted(_results_backed())
    for text in ("Да. Шлем дадим бесплатно.", "Да.", "Да. Уже."):
        assert T.money_roles(text, backed, asked=False, incoming="Готово.") == [], text


def test_p3k_boundary_brief_one_sentence_reply_outside_n4_forms_still_no_reason():
    """ГРАНИЦА (была до шага и шагом не меняется) — проверка ФИКСИРУЕТ нынешний исход и НЕ означает «закрыто». Краткий
    ответ ОДНИМ предложением, где рядом со словом согласия стоят и слово вне словаря согласия («уже», «already»), и
    вежливость либо одобрение («Да, уже, хорошего дня!», «Yes, already, cheers!»), — вне форм N4: причины кода нет при
    обоих наборах фактов (так на всех деревьях). Тот же ответ двумя предложениями («Да, уже. Хорошего дня!») причину N4
    несёт, как нёс. Слово в словарь по решению не добавляется; редкая фраза нового круга не запускает."""
    assert len(K_GAP) == 3
    for tail, one, dot in K_GAP:
        assert (tail, dot, 2) in K_BRIEF and _comma3k(dot) == one and T._PayClaim(True).search(one) is None, (one, dot)
        for facts in ("none", "cash"):
            hand, state, conf, rule, _by, _paid = _run3i([], tail, one, facts)
            assert hand == [] and state[0] == V_NONE and not conf and not rule, (tail, one, hand)      # ← остаток, не успех
            assert _run3i([], tail, dot, facts)[0] == [T.PAY_WORDS], (tail, dot)


# ═══ п.3l: денежное сообщение без слова оплаты кода открывает тему (решение координатора 11.10 по блокеру B1) ═══
# Узкая независимая проверка ремонта границы (fix_review3k/VERDICT.md, FAIL на ba12c65): МЫ назвали деньги без слова
# оплаты кода («Бронь держим до вечера, ждём 1000 бат.», «С вас 7790 бат за 10 суток.») → бессловесное сообщение клиента
# («Скинул.», «Сделано.», «Sent!») → ответ с содержанием либо вне форм N4 («Да, ждём вас завтра в 10.», «Отлично, бронь
# за вами!») — причины кода `[]`: клиент читает ответ как подтверждение оплаты, предупреждения на карточке нет. Находка
# по дороге: сообщение клиента с БУМАГОЙ об оплате без общей причины («Квитанция во вложении.», «Slip attached.») →
# нейтральный ответ → «Ну что?» → «Отлично, тогда оформляю договор.» — тоже `[]`. Решение — ОДИН ремонт класса
# существующими определениями: (1) наш ответ открывает тему и тогда, когда называет деньги — сумму с валютой
# (`K.thb_amounts`), способ (`_PF_METHOD`), место денег (`_PF_HELD`), бумагу об оплате (`_PQ_PROOF`); (2) блок клиента — и
# тогда, когда называет бумагу об оплате (`_PQ_PROOF`). Тема — состояние (168 ч); при подтверждённой кодом оплате причины
# нет; признаки шага ДОБАВОЧНЫЕ (где тема была открыта и до шага — исход и слова прежние). Слов и выражений не добавлено.
# Всё — настоящим путём адаптера (`_draft3g2`), причин модели нет.
V_OURS_MONEY = "тема оплаты открыта: наш последний ответ назвал деньги — сумму, способ, место или бумагу"
V_BACK_OURS_MONEY = ("тема оплаты открыта раньше, чем один обмен назад: наш ответ назвал деньги — сумму, способ, место "
                     "или бумагу")
V_PREV_PROOF = "тема оплаты открыта: сообщение клиента перед нашим последним ответом называет бумагу об оплате"
V_BACK_PROOF = "тема оплаты открыта раньше, чем один обмен назад: сообщение клиента называет бумагу об оплате"
# KRA — ДОСЛОВНО fix_review3k/gen_my3k.py (семейство KRA): 5 наших сообщений с суммой × 2 хвоста × 3 ответа
L_KRA_SUMS = ["Бронь держим до вечера, ждём 1000 бат.", "За 10 суток выйдет 7790 бат.", "С вас 7790 бат за 10 суток.",
              "Итого 7790 бат, залог 3000 бат отдельно.", "That's 7790 THB for ten days."]
L_KRA_Q = {"ru": "Забронируете за мной?", "en": "Can you hold it for me?"}
L_KRA_TAILS = {"ru": ["Скинул.", "Сделано."], "en": ["Sent!", "Done."]}
L_KRA_ANS = {"ru": ["Да. Ждём вас завтра в 10.", "Да, ждём вас завтра в 10.", "Отлично, бронь за вами!"],
             "en": ["Yes. See you tomorrow at 10.", "Yes, see you tomorrow at 10.", "Great, it's yours!"]}
# G1o / G1w — ДОСЛОВНО fix_review3k/gen_g1out.py: 16 цепочек Г1 проверки 3g (`I_G1` + `I_G1_OUT`) × два ответа
L_G1_ANS = {"ru": ["Отлично, бронь за вами!", "Да, ждём вас завтра в 10."],
            "en": ["Great, it's yours!", "Yes, see you tomorrow at 10."]}
# наши ответы списков Г1 с реквизитами ВНЕ словаря кода: ни суммы с валютой, ни способа, ни места, ни бумаги (ОСТАТОК)
L_G1_NO_SIGN = ["Our account: Test Bank, TEST-ACC-0042, Test Rent Co.", "PromptPay works: 081 000 0000.",
                "Our Kasikorn account: TEST-ACC-0042."]
# находка «бумага об оплате» — ДОСЛОВНО fix_review3k/gen_my3k.py (семейство KBXout): 8 сообщений клиента без признака
# `pay_asked` и без общей причины «заявил оплату / неясно»; `L_PAPER_LEFT` — два, где бумага названа вне `_PQ_PROOF`
L_PAPER = ["Квитанция во вложении.", "Вот квитанция.", "Платёжка во вложении.", "Вот подтверждение перевода.",
           "Here's the payment slip.", "Transfer slip is above.", "Slip attached.", "Payment slip attached."]
L_PAPER_LEFT = ["Платёжка во вложении.", "Вот подтверждение перевода."]
L_NEU = {"ru": "Добрый день! Одну минуту.", "en": "Hello! One moment, please."}
L_UPD = {"ru": "Ну что?", "en": "Any update?"}
L_OUT = {"ru": "Отлично, тогда оформляю договор.", "en": "Great, I'll prepare the contract then."}
# промежуточные обмены не об оплате (ни один тему не открывает)
L_FILL = {"ru": [("А шлем дадите?", "Да, шлем дадим бесплатно."),
                 ("Во сколько вы открываетесь?", "Мы работаем с 9:00 до 20:00 каждый день.")],
          "en": [("Is a helmet included?", "Yes, a helmet is included."), ("What time do you open?", "We are open from 9 am to 8 pm.")]}
# СВОИ 14: (признак, вопрос клиента, НАШ ответ с деньгами без слова оплаты кода, число промежуточных обменов, хвост,
# ответ с содержанием либо вне форм N4) — в нашем ответе РОВНО один признак шага и ни одного прежнего
L_OWN = [
    ("sum", "Сколько с меня?", "С вас 7790 бат за 10 суток.", 1, "Скинул.", "Да, ждём вас завтра в 10."),
    ("sum", "Забронируете за мной?", "Бронь держим до вечера, ждём 1000 бат.", 2, "Сделано.", "Отлично, бронь за вами!"),
    ("sum", "How much is it?", "That's 7790 THB for ten days.", 1, "Sent!", "Great, it's yours!"),
    ("sum", "А на две недели?", "За две недели выйдет 10900 бат.", 2, "Готово, проверяйте.", "Отлично, тогда оформляю договор."),
    ("method", "Можно картой курьеру?", "Можно картой курьеру при встрече.", 1, "Готово.", "Отлично, тогда оформляю договор."),
    ("method", "Как вам удобнее принять?", "Наличными курьеру либо по QR — как удобнее.", 2, "Всё, отослал.", "Супер, ждём вас завтра!"),
    ("method", "Card or cash?", "Card or cash at pickup, both are fine.", 1, "Done.", "Yes, see you tomorrow at 10."),
    ("held", "Куда?", "Номер счёта: TEST-ACC-0042, банк Test Bank.", 1, "Всё, ушло.", "Да, ждём вас завтра в 10."),
    ("held", "Куда слать?", "Kasikorn, счёт TEST-ACC-0042, получатель Test Rent Co.", 2, "Улетело.", "Отлично, бронь за вами!"),
    ("held", "Куда подойти?", "Можно в кассу в офисе, мы на месте до 20:00.", 1, "Сделал.", "Отлично, тогда оформляю договор."),
    ("proof", "Что дальше?", "Квитанцию выдадим при встрече.", 1, "Готово.", "Да, ждём вас завтра в 10."),
    ("proof", "Что от меня нужно?", "Скрин пришлите сюда же.", 2, "Вот.", "Отлично, бронь за вами!"),
    ("proof", "What do you need from me?", "Just send the slip here.", 1, "There you go.", "Great, it's yours!"),
    ("proof", "Is a photo ok?", "A screenshot is enough.", 2, "Done.", "Yes, see you tomorrow at 10.")]
# близнец: наши ответы БЕЗ денежного признака
L_PLAIN_OURS = ["Здравствуйте! NMAX свободен, оформляем.", "Записали, ждём вас.", "Да, шлем дадим бесплатно.",
                "Мы работаем с 9:00 до 20:00 каждый день.", "Договор пришлём сегодня.",
                "Hello! The NMAX is free, booking it for you.", "Noted, see you then.", "Yes, a helmet is included."]
# ИМЕННОЙ ОСТАТОК: реквизиты вне словаря кода (слова «account», «PromptPay», «реквизиты» ни в одном определении нет)
L_RESIDUAL = [("Where to?", "Our account: Test Bank, TEST-ACC-0042, Test Rent Co.", I_DOC, "Great, it's yours!"),
              ("Do you take PromptPay?", "PromptPay works: 081 000 0000.", "Just did it.", "Great, it's yours!"),
              ("Where do I send it?", "Our Kasikorn account: TEST-ACC-0042.", "Done.", "Yes, see you tomorrow at 10."),
              ("Куда?", "Реквизиты пришлю следующим сообщением.", "Готово.", "Отлично, бронь за вами!")]
# ЦЕНА — ДОСЛОВНО fix_review3k/gen_my3k.py (семейства KP и KPD): обычные обмены НЕ об оплате после нашего сообщения с ценой
L_PRICE = ["NMAX на 10 суток — 7790 бат.", "PCX на 10 суток — 9990 бат.", "Залог — 3000 бат или паспорт.",
           "Продление — 779 бат в сутки."]
L_EXCH = [("А шлем дадите?", "Да, шлем дадим бесплатно."), ("Хорошо, спасибо.", "Пожалуйста!"),
          ("Буду завтра в 10.", "Отлично, тогда до завтра!")]
# отпечатки выражений четырёх определений шага (sha256 шаблона, 16 знаков) — сняты с ba12c65: выражения не тронуты
L_PRINTS_T = {"_PF_METHOD": "85fbdb4b7dbe24ec", "_PF_HELD": "f48e6ed3e373ad32", "_PQ_PROOF": "19cb9d2738e3c1c1",
              "_PQ_PAYWORD": "8203aa7c34d97133"}
L_PRINTS_K = {"_CLAIM_THB": "b73d1cea7bf29323"}
L_PRINTS_ALL = {"T": (71, "a1716e9f7a0d5beb"), "K": (22, "34eff516dd9e1e3b")}     # ВСЕ скомпилированные выражения модулей


def _en3l(text):
    return not re.search("[а-яёА-ЯЁ]", text if isinstance(text, str) else "")


def _lang3l(*texts):
    return "en" if all(_en3l(t) for t in texts) else "ru"


def _old_sign3l(text):
    """Прежние признаки «наш ответ об оплате» (шаг 3g) — пересчитаны здесь из существующих определений, не из
    `_topic_ours` под проверкой: слово оплаты, группа оплаты R_MONEY, обещание проверки или «не видим», утверждение N4."""
    named = T._PQ_PAYWORD.search(text) is not None or bool(
        [k for k, _w in K.money_labels(text, trusted=False) if K._FAMILY.get(k, k) == K.MONEY_PAYMENT])
    return bool(named or T._PayClaim.unsettled(text) or T._PAY_CLAIM.search(text) is not None)


def _signs3l(text):
    """Какие из ЧЕТЫРЁХ определений шага называют деньги в тексте: сумма с валютой, способ, место денег, бумага."""
    hit = (("sum", bool(K.thb_amounts(text))), ("method", T._PF_METHOD.search(text) is not None),
           ("held", T._PF_HELD.search(text) is not None), ("proof", T._PQ_PROOF.search(text) is not None))
    return [name for name, on in hit if on]


def _own3l(row, n=None):
    """Своя цепочка шага → (история, хвост, ответ): открывающий обмен + `n` промежуточных обменов не об оплате."""
    _sign, q, ours, k, tail, text = row
    fill = L_FILL[_lang3l(text)][:k if n is None else n]
    return [("клиент", q), ("мы", ours)] + [x for c, o in fill for x in (("клиент", c), ("мы", o))], tail, text


def _class3l(rows, want_state):
    """Цепочки (история, хвост, ответ), где при «строки кассы нет» / «касса без второго источника» черновик НЕ несёт
    ровно одну причину класса — нейтральное «оплата» (признак шага), — либо исход темы иной, либо в журнале нет строки
    правила с этим именем, либо текст ответа изменён, либо стоит причина N4 (ответы шага — не краткие подтверждения)."""
    bad = []
    for history, tail, text in rows:
        for facts in ("none", "cash"):
            hand, state, conf, rule, by_tail, paid = _run3i(history, tail, text, facts)
            if hand != [G_PLAIN] or state != (want_state, G_PLAIN) or conf or by_tail or paid \
                    or rule != ["правило класса: %s; причина кода добавлена" % want_state]:
                bad.append((_said3i(tail), text, facts, state, hand, rule))
    return bad


def test_p3l_definition_named_outcomes_our_money_and_client_paper():
    """Определение темы после шага — исход назван на каждой дороге. `_topic_ours` отдаёт ИМЯ: прежние признаки (слово
    оплаты, группа оплаты R_MONEY, обещание проверки, утверждение) — `PT_OURS`; ни одного из них, но КАЖДЫЙ из четырёх
    признаков шага в одиночку — сумма с валютой, способ, место денег, бумага — `PT_OURS_MONEY`; иначе `PT_NONE`.
    `_topic_theirs`: бумага об оплате без признака `pay_asked` и без общей причины — `PT_PREV_PROOF`. Раньше одного обмена
    — свои имена. Слова причины у обоих признаков шага — нейтральное «оплата». Признаки шага ДОБАВОЧНЫЕ: прежний признак
    где угодно в истории решает сам — исход и слова прежние; из признаков шага берётся ближайший к хвосту, в одном обмене
    блок клиента раньше нашего ответа. Хвост судится по-прежнему (`pay_asked`)."""
    assert (T.PT_OURS_MONEY, T.PT_BACK_OURS_MONEY, T.PT_PREV_PROOF, T.PT_BACK_PROOF) \
        == (V_OURS_MONEY, V_BACK_OURS_MONEY, V_PREV_PROOF, V_BACK_PROOF)
    assert len({V_OURS, V_OURS_MONEY, V_BACK_OURS, V_BACK_OURS_MONEY, V_PREV_PROOF, V_BACK_PROOF, V_PREV_SAID}) == 7
    for text in ("К оплате 7790 бат.", "Проверим и вернёмся с ответом.", "Оплата получена, спасибо!", "Чек пришлём после.",
                 "Переведите 7790 бат на карту — номер пришлю.", "You can pay in cash or by card at pickup."):
        assert _old_sign3l(text) and T._topic_ours(text) == V_OURS, text           # прежний признак — имя прежнее
    alone = {"sum": "С вас 7790 бат за 10 суток.", "method": "Можно картой курьеру при встрече.",
             "held": "Номер счёта: TEST-ACC-0042, банк Test Bank.", "proof": "Квитанцию выдадим при встрече."}
    for sign, text in alone.items():
        assert _signs3l(text) == [sign] and not _old_sign3l(text), (sign, text, _signs3l(text))
        assert T._topic_ours(text) == V_OURS_MONEY, (sign, text)
        assert T.pay_topic("Сделано.", "Сколько?", text) == (V_OURS_MONEY, G_PLAIN), (sign, text)
        assert T.pay_topic("Сделано.", blocks=[("мы", "Да, шлем дадим.", None), ("клиент", "А шлем?", None),
                                               ("мы", text, None), ("клиент", "Сколько?", None)]) \
            == (V_BACK_OURS_MONEY, G_PLAIN), (sign, text)
    for row in L_OWN:
        assert _signs3l(row[2]) == [row[0]] and not _old_sign3l(row[2]) and T._topic_ours(row[2]) == V_OURS_MONEY, row
    for text in L_PLAIN_OURS + L_G1_NO_SIGN + ["Реквизиты пришлю следующим сообщением.", "", None, chr(0x1F44D)]:
        assert T._topic_ours(text) == V_NONE and not _signs3l(str(text or "")), text
    # блок клиента: бумага об оплате
    for x in L_PAPER:
        assert T.pay_asked(x) is False, x
        assert not [k for k, _w in K.money_labels(x) if k in (K.MONEY_PAYMENT, K.MONEY_PAYMENT_UNCLEAR)], x
        proof = x not in L_PAPER_LEFT
        # шаг 3m, ожидание изменено ПОИМЁННО: «Вот подтверждение перевода.» (`M_PAPER_ASK`) — бумаги `_PQ_PROOF` в нём
        # нет, но общая причина кода по нему — «вопрос об оплате»: `PT_PREV_NAMED` (было `PT_NONE`)
        want = V_PREV_PROOF if proof else (V_PREV_NAMED if x == M_PAPER_ASK else V_NONE)
        assert T._topic_theirs(x) == want and (T._PQ_PROOF.search(x) is not None) == proof, x
        assert T.pay_topic(x)[0] == V_NONE, x                                       # хвост — определение прежнее
        if not proof:
            continue
        assert T.pay_topic("Ну что?", x, "Одну минуту.") == (V_PREV_PROOF, G_PLAIN), x
        assert T.pay_topic("Ну что?", blocks=[("мы", "Ок.", None), ("клиент", "Ок", None), ("мы", "Минуту.", None),
                                              ("клиент", x, None)]) == (V_BACK_PROOF, G_PLAIN), x
    assert [K.MONEY_WORDS[K.payment_mode(x)] for x in ("Slip attached.", "Квитанция во вложении.")] == [G_ASK, G_SAID]
    assert T._topic_theirs("Вот чек.") == V_PREV_SAID and T._topic_theirs(G_PAID) == V_PREV      # прежние признаки сильнее
    assert T.pay_topic("С вас 7790 бат за 10 суток.")[0] == V_NONE and T.pay_asked("С вас 7790 бат за 10 суток.") is False
    # ДОБАВОЧНЫЕ: прежний признак где угодно в истории решает сам — исход и слова причины прежние
    money, wait = ("мы", "Итого 7790 бат.", None), ("клиент", "Ок", None)
    assert T.pay_topic("Ну что?", blocks=[money, wait, ("мы", "Спасибо!", None), ("клиент", G_PAID, None)]) == (V_BACK, G_SAID)
    assert T.pay_topic("Ну что?", blocks=[money, wait, ("мы", "К оплате 7790 бат.", None), ("клиент", "Сколько?", None)]) \
        == (V_BACK_OURS, G_PLAIN)
    assert T.pay_topic("Ну что?", blocks=[money, ("клиент", "Вот чек.", None)]) == (V_PREV_SAID, G_SAID)
    assert T.pay_topic("Ну что?", blocks=[("мы", "Минуту.", None), ("клиент", "Квитанция во вложении.", None),
                                          ("мы", "Спасибо!", None), ("клиент", "Деньги пришли?", None)]) == (V_BACK, G_ASK)
    # из признаков шага — ближайший к хвосту; в одном обмене блок клиента раньше нашего ответа
    assert T.pay_topic("Ну что?", blocks=[money, ("клиент", "Квитанция во вложении.", None)]) == (V_PREV_PROOF, G_PLAIN)
    assert T.pay_topic("Ну что?", blocks=[("мы", "Можно картой.", None), wait, ("мы", "Минуту.", None),
                                          ("клиент", "Вот квитанция.", None)]) == (V_OURS_MONEY, G_PLAIN)
    assert T.pay_topic("Ну что?", blocks=[("мы", "Минуту.", None), wait, ("мы", "Можно картой.", None),
                                          ("клиент", "Вот квитанция.", None)]) == (V_BACK_PROOF, G_PLAIN)
    # правило класса на новых именах: не подтверждена — причина, подтверждена — нет; `PAY_WORDS` правило не ставит
    for name in (V_OURS_MONEY, V_BACK_OURS_MONEY, V_PREV_PROOF, V_BACK_PROOF):
        assert name in T.PT_OPEN and T.topic_reason((name, G_PLAIN), []) == (name, [G_PLAIN])
        assert T.topic_reason((name, G_PLAIN), T.accepted(_results_no_second())) == (name, [G_PLAIN])
        assert T.topic_reason((name, G_PLAIN), T.accepted(_results_backed())) == (V_PAID, [])


def test_p3l_kra_our_sum_then_wordless_message_reply_with_content_has_class_reason():
    """KRA — блокер B1 ДОСЛОВНО (60 записей проверяющего): 5 наших сообщений с суммой без слова оплаты кода × 2
    бессловесных хвоста («Скинул.», «Сделано.», «Sent!», «Done.») × 3 ответа с содержанием либо вне форм N4 («Да. Ждём
    вас завтра в 10.», «Да, ждём вас завтра в 10.», «Отлично, бронь за вами!») × «строки кассы нет» и «касса без второго
    источника»: причина кода «оплата» у 60 из 60 (на ba12c65 — `[]` у 60 из 60), исход `PT_OURS_MONEY`. Близнец того же
    обмена — ответ целиком краткий («Да.», «Yes.») — причина N4 как была, рядом причина класса."""
    rows = []
    for ours in L_KRA_SUMS:
        lang = _lang3l(ours)
        assert not _old_sign3l(ours) and _signs3l(ours) == ["sum"], ours
        for tail in L_KRA_TAILS[lang]:
            assert T.pay_asked(tail) is False and K.handoff(tail, None) == [], tail
            rows += [([("клиент", L_KRA_Q[lang]), ("мы", ours)], tail, text) for text in L_KRA_ANS[lang]]
    assert len(rows) * 2 == 60
    bad = _class3l(rows, V_OURS_MONEY)
    assert not bad, bad
    for history, tail, _text in rows[::3]:
        brief = "Yes." if _en3l(tail) else "Да."
        for facts in ("none", "cash"):
            assert _run3i(history, tail, brief, facts)[0] == [T.PAY_WORDS, G_PLAIN], (tail, facts)


def test_p3l_g1_chains_reply_outside_forms_have_class_reason():
    """G1o / G1w — 16 цепочек Г1 проверки 3g (`I_G1` + `I_G1_OUT`) с ответом вне форм N4 и с ответом с содержанием
    («Отлично, бронь за вами!» / «Great, it's yours!»; «Да, ждём вас завтра в 10.» / «Yes, see you tomorrow at 10.») ×
    два набора фактов — 64 записи проверяющего: на ba12c65 причины `[]` у 64 из 64; теперь причина класса «оплата» у 60
    из 64 — наш ответ назвал сумму, способ («картой», «наличными», «QR», «cash», «card») либо счёт. Остаётся ОДНА
    цепочка (4 записи) — именной остаток: «Where to?» → «Our account: Test Bank, TEST-ACC-0042, Test Rent Co.» (слова
    «account» нет ни в одном определении; словарь не расширяется). G107 / G114 в своей формулировке — 4 из 4."""
    chains = I_G1 + I_G1_OUT
    assert len(chains) == 16
    got, left = 0, []
    for q, ours, tail, _text in chains:
        lang = "ru" if re.search("[а-яёА-ЯЁ]", q + ours) else "en"
        history = [("клиент", q), ("мы", ours)]
        want = [] if ours in L_G1_NO_SIGN else [G_PLAIN]
        for text in L_G1_ANS[lang]:
            for facts in ("none", "cash"):
                hand, state, conf, rule, by_tail, paid = _run3i(history, tail, text, facts)
                assert hand == want and not conf and not by_tail and not paid, (ours, _said3i(tail), text, facts, hand)
                assert state[0] == (V_OURS_MONEY if want else V_NONE) and bool(rule) == bool(want), (ours, state, rule)
                got += bool(hand)
                left += [ours] if not hand else []
    assert got == 60 and sorted(set(left)) == [L_G1_NO_SIGN[0]] and len(left) == 4, (got, left)
    for q, ours, tail, text in I_G1_OUT:                                            # G107, G114 — своей формулировкой
        for facts in ("none", "cash"):
            assert _run3i([("клиент", q), ("мы", ours)], tail, text, facts)[0] == [G_PLAIN], (ours, facts)


def test_p3l_client_paper_block_opens_topic():
    """Находка «бумага об оплате» ДОСЛОВНО (8 сообщений проверяющего, семейство KBXout): сообщение клиента называет
    бумагу об оплате, но признака `pay_asked` и общей причины «заявил оплату / неясно» у него нет → наш нейтральный ответ
    → «Ну что?» → «Отлично, тогда оформляю договор.». На ba12c65 — `[]` у 8 из 8; теперь блок с бумагой из `_PQ_PROOF`
    («квитанция», «slip») открывает тему (`PT_PREV_PROOF`; раньше одного обмена — `PT_BACK_PROOF`), причина «оплата» у
    6 из 8. Остаются поимённо два: «Платёжка во вложении.» и «Вот подтверждение перевода.» — бумага названа вне
    `_PQ_PROOF` (словарь не расширяется). На краткое «Да, всё пришло.» причина N4 — как была, рядом причина класса."""
    assert len(L_PAPER) == 8 and len(L_PAPER_LEFT) == 2 and M_PAPER_ASK in L_PAPER_LEFT
    opened = 0
    for x in L_PAPER:
        lang = _lang3l(x)
        history = [("клиент", x), ("мы", L_NEU[lang])]
        # шаг 3m, ожидание изменено ПОИМЁННО: «Вот подтверждение перевода.» (`M_PAPER_ASK`; бумага вне `_PQ_PROOF`, общая
        # причина кода — «вопрос об оплате») тему теперь открывает признаком шага 3m — `PT_PREV_NAMED`, причина «оплата»
        # (было `PT_NONE`, `[]`): причина у 7 из 8 (было 6 из 8). Остаётся одно: «Платёжка во вложении.»
        want = V_PREV_NAMED if x == M_PAPER_ASK else (V_NONE if x in L_PAPER_LEFT else V_PREV_PROOF)
        assert not _old_sign3l(L_NEU[lang]) and not _signs3l(L_NEU[lang]) and T._PayClaim(True).search(L_OUT[lang]) is None, lang
        for facts in ("none", "cash"):
            hand, state, conf, rule, by_tail, paid = _run3i(history, L_UPD[lang], L_OUT[lang], facts)
            assert not conf and not by_tail and not paid and state[0] == want, (x, facts, state)
            assert hand == ([] if want == V_NONE else [G_PLAIN]), (x, facts, hand)
            assert rule == ([] if want == V_NONE else ["правило класса: %s; причина кода добавлена" % want]), rule
            opened += bool(hand)
            brief = "Yes, all received." if lang == "en" else "Да, всё пришло."
            assert _run3i(history, L_UPD[lang], brief, facts)[0] == [T.PAY_WORDS] + hand, (x, facts)
        if want == V_NONE:
            continue
        deep = history + [("клиент", L_FILL[lang][0][0]), ("мы", L_FILL[lang][0][1])]
        hand, state, _conf, rule, _by, _paid = _run3i(deep, L_UPD[lang], L_OUT[lang], "cash")
        back = {V_PREV_PROOF: V_BACK_PROOF, V_PREV_NAMED: V_BACK_NAMED}[want]
        assert hand == [G_PLAIN] and state == (back, G_PLAIN), (x, hand, state)
        assert rule == ["правило класса: %s; причина кода добавлена" % back], rule
    assert opened == 7 * 2


def test_p3l_own_chains_money_named_then_other_exchanges_then_wordless_message():
    """СВОИ 14 цепочек: наш ответ называет деньги РОВНО одним признаком шага — суммой (4), способом (3), местом денег
    «счёт» / «в кассу» (3), бумагой (4) — и ни одним прежним → один или два обмена не об оплате (шлем, часы работы) →
    бессловесное сообщение клиента → ответ с содержанием либо вне форм N4. На ba12c65 причины `[]` у 28 из 28; теперь при
    обоих наборах фактов — ровно причина класса «оплата», исход `PT_BACK_OURS_MONEY` (тема — состояние: её держит
    сообщение раньше одного обмена). Без промежуточных обменов — `PT_OURS_MONEY`."""
    assert len(L_OWN) == 14 and [r[0] for r in L_OWN].count("sum") == 4 and {r[3] for r in L_OWN} == {1, 2}
    for lang in ("ru", "en"):
        for c, o in L_FILL[lang]:                       # промежуточные обмены тему не открывают ни одним признаком
            assert T.pay_asked(c) is False and K.handoff(c, None) == [] and T._topic_theirs(c) == V_NONE, c
            assert not _signs3l(o) and not _old_sign3l(o), o
    rows = [_own3l(r) for r in L_OWN]
    for (sign, _q, ours, n, tail, text), (history, _t, _x) in zip(L_OWN, rows):
        assert len(history) == 2 + 2 * n and _signs3l(K.mask(ours)[0]) == [sign] and not _old_sign3l(ours), (sign, ours)
        assert T.pay_asked(tail) is False and K.handoff(tail, None) == [] and T._PQ_PROOF.search(tail) is None, tail
        assert T._PayClaim(True, (), T.PB_BARE).search(text) is None, (text, T._PAY_CLAIM.explain(text, True))
    bad = _class3l(rows, V_BACK_OURS_MONEY)
    assert not bad, bad
    bad = _class3l([_own3l(r, 0) for r in L_OWN], V_OURS_MONEY)
    assert not bad, bad


def test_p3l_staleness_of_our_money_message_and_client_paper():
    """Давность (168 ч) у признаков шага. НАШЕ денежное сообщение старше предела тему не открывает В ЛЮБОМ месте истории —
    и раньше одного обмена, и последним перед хвостом (у прежних признаков обмен перед хвостом давностью не судится: то
    же место со словом оплаты тему открывает и через 400 ч); 168 ч и свежее — открывает; времени у сообщения нет — оно
    свежее; время суждения не задано — давности нет. Бумага клиента — как прочие признаки клиента: обмен перед хвостом
    давностью не судится, раньше — судится. Исход закрытой темы — `PT_OLD`, причины нет. То же — путём адаптера."""
    now, hour = T0, 3600

    def at(text_c, text_o, hours):
        ts = None if hours is None else now - hours * hour
        return [("мы", text_o, ts), ("клиент", text_c, ts)]
    wait = at("Ок", "Минуту.", 1)
    for text in ("С вас 7790 бат за 10 суток.", "Можно картой курьеру при встрече.", "Номер счёта: TEST-ACC-0042.",
                 "Квитанцию выдадим при встрече."):
        for hours, want in ((1, True), (167, True), (168, True), (169, False), (1000, False), (None, True)):
            got = T.pay_topic("Сделано.", blocks=wait + at("Сколько?", text, hours), now=now)
            assert got == ((V_BACK_OURS_MONEY if want else V_OLD), G_PLAIN), (text, hours, got)
            got = T.pay_topic("Сделано.", blocks=at("Сколько?", text, hours), now=now)       # последним перед хвостом
            assert got == ((V_OURS_MONEY if want else V_OLD), G_PLAIN), (text, hours, got)
        assert T.pay_topic("Сделано.", blocks=wait + at("Сколько?", text, 400))[0] == V_BACK_OURS_MONEY, text   # без «сейчас»
    # прежний признак в том же месте: обмен перед хвостом давностью не судится — как был
    assert T.pay_topic("Сделано.", blocks=at("Сколько?", "К оплате 7790 бат.", 400), now=now) == (V_OURS, G_PLAIN)
    # старое денежное сообщение, а после него свежее — тему открывает свежее; старое и свежий прежний признак — прежний
    assert T.pay_topic("Сделано.", blocks=wait + at("А на неделю?", "За неделю 5453 бат.", 3) + at("Сколько?", "С вас 7790 бат.", 400),
                       now=now) == (V_BACK_OURS_MONEY, G_PLAIN)
    assert T.pay_topic("Сделано.", blocks=wait + at(G_PAID, "Спасибо!", 3) + at("Сколько?", "С вас 7790 бат.", 400), now=now) \
        == (V_BACK, G_SAID)
    assert T.pay_topic("Сделано.", blocks=wait + at("Сколько?", "С вас 7790 бат.", 400), now=now) == (V_OLD, G_PLAIN)
    # бумага клиента
    for hours, want in ((1, V_BACK_PROOF), (168, V_BACK_PROOF), (169, V_OLD), (None, V_BACK_PROOF)):
        got = T.pay_topic("Ну что?", blocks=wait + at("Квитанция во вложении.", "Одну минуту.", hours), now=now)
        assert got[0] == want, (hours, got)
    assert T.pay_topic("Ну что?", blocks=at("Квитанция во вложении.", "Одну минуту.", 500), now=now)[0] == V_PREV_PROOF
    # путь адаптера: (возраст открывающего обмена, есть ли промежуточный обмен) → причина класса и исход
    for hours, deep, opened in ((200, True, False), (169, True, False), (167, True, True), (3, True, True),
                                (200, False, False), (3, False, True), (None, True, True)):
        history = [("клиент", "Сколько с меня?", hours), ("мы", "С вас 7790 бат за 10 суток.", hours)]
        history += [("клиент", "А шлем дадите?", 2), ("мы", "Да, шлем дадим бесплатно.", 1)] if deep else []
        for facts in ("none", "cash"):
            out, a, _s, logs = _draft3g2(history, "Скинул.", "Да, ждём вас завтра в 10.", facts)
            want = (V_BACK_OURS_MONEY if deep else V_OURS_MONEY) if opened else V_OLD
            assert _state3g2(a) == (want, G_PLAIN) and out["handoff"] == ([G_PLAIN] if opened else []), (hours, deep, out["handoff"])
            assert [ln for ln in logs if ln.startswith("правило класса")] == [
                "правило класса: %s; причина кода %s" % (want, "добавлена" if opened else "не нужна")], logs


def test_p3l_twin_confirmed_payment_adds_nothing():
    """Близнец «оплата подтверждена кодом» (касса аренды обращения + договор той же аренды): ни одной новой причины на
    всех цепочках шага — KRA (30), Г1 с двумя ответами (32), бумага (8), свои (14), цена (12): список причин равен
    причинам кода по входящему, причины N4 нет, исход правила у открытой темы — `PT_PAID`. Полезный сценарий (оплата
    подтверждена, ответ с PDF) правилом не задет."""
    rows = []
    for ours in L_KRA_SUMS:
        lang = _lang3l(ours)
        rows += [([("клиент", L_KRA_Q[lang]), ("мы", ours)], tail, text) for tail in L_KRA_TAILS[lang] for text in L_KRA_ANS[lang]]
    for q, ours, tail, _text in I_G1 + I_G1_OUT:
        lang = "ru" if re.search("[а-яёА-ЯЁ]", q + ours) else "en"
        rows += [([("клиент", q), ("мы", ours)], tail, text) for text in L_G1_ANS[lang]]
    rows += [([("клиент", x), ("мы", L_NEU[_lang3l(x)])], L_UPD[_lang3l(x)], L_OUT[_lang3l(x)]) for x in L_PAPER]
    rows += [_own3l(r) for r in L_OWN]
    rows += [([("клиент", "Сколько стоит?"), ("мы", m)], q, a) for m in L_PRICE for q, a in L_EXCH]
    assert len(rows) == 30 + 32 + 8 + 14 + 12
    bad = []
    for history, tail, text in rows:
        hand, state, conf, rule, by_tail, paid = _run3i(history, tail, text, "backed")
        if not paid or hand != by_tail or hand or conf or [ln for ln in rule if "причина кода не нужна" not in ln] \
                or (state[0] in T.PT_OPEN and rule != ["правило класса: %s; причина кода не нужна" % V_PAID]):
            bad.append((_said3i(tail), text, hand, state[0], rule))
    assert not bad, bad
    out, _a, _s, _logs = _draft3g2([("клиент", "Сколько с меня?"), ("мы", "С вас 7790 бат за 10 суток.")], "Скинул.",
                                  "Да, оплата получена. Договор отправляю следующим сообщением.", "backed")
    assert out["handoff"] == [], out["handoff"]


def test_p3l_twin_no_money_sign_does_not_open_and_payment_question_opens_since_3m():
    """Близнец «тему не открывает»: (а) наш ответ БЕЗ денежного признака («Здравствуйте! NMAX свободен, оформляем.»,
    «Записали, ждём вас.», «Да, шлем дадим бесплатно.») — после него бессловесное сообщение и ответ с содержанием уходят
    без причины кода, как до шага (исход `PT_NONE`, строки правила в журнале нет). (б) БЫВШАЯ вторая половина близнеца
    шага 3l (имя проверки было `…no_money_sign_and_payment_question_do_not_open`) — «вопрос об оплате» клиента сам по
    себе («Как оплатить?», «Оплачу завтра.», «How can I pay?»): сторона ОТМЕНЕНА решением координатора 11.10 (блокер B2),
    ожидание изменено ПОИМЁННО — блок клиента с общей причиной «вопрос об оплате» тему теперь открывает (`PT_PREV_NAMED`),
    ответ вне форм N4 несёт причину класса «оплата» (было `[]`, `PT_NONE`)."""
    for ours in L_PLAIN_OURS:
        lang = _lang3l(ours)
        history = [("клиент", "Hi, I'd like an NMAX for 10 days." if lang == "en" else "Здравствуйте, хочу NMAX на 10 дней."),
                   ("мы", ours)]
        tail, text = ("Sent!", "Yes, see you tomorrow at 10.") if lang == "en" else ("Скинул.", "Да, ждём вас завтра в 10.")
        for facts in ("none", "cash"):
            hand, state, conf, rule, _by, _paid = _run3i(history, tail, text, facts)
            assert hand == [] and state[0] == V_NONE and not conf and not rule, (ours, facts, hand, state)
    for hist in list(I_NEUTRAL.values()) + list(I_NEUTRAL_OWN.values()):
        tail, text = ("Sent!", "Great, it's yours!") if _en3l(hist[1][1]) else ("Сделано.", "Отлично, бронь за вами!")
        hand, state, _conf, rule, _by, _paid = _run3i(hist, tail, text, "cash")
        assert hand == [] and state[0] == V_NONE and not rule, (hist[1][1], hand)
    for x in I_ASK_ONLY:
        assert T._topic_theirs(x) == V_PREV_NAMED and T._PQ_PROOF.search(x) is None, x
        assert [r["words"] for r in K.handoff(x, None)] == [G_ASK], x
        lang = _lang3l(x)
        for facts in ("none", "cash"):
            hand, state, _conf, rule, _by, _paid = _run3i([("клиент", x), ("мы", L_NEU[lang])], L_UPD[lang], L_OUT[lang], facts)
            assert hand == [G_PLAIN] and state == (V_PREV_NAMED, G_PLAIN), (x, facts, hand, state)             # была []
            assert rule == ["правило класса: %s; причина кода добавлена" % V_PREV_NAMED], rule


def test_p3l_cost_ordinary_exchanges_after_our_price_named():
    """ЦЕНА шага (сторона отказа, принята решением; НЕ успех) — числом. После нашего сообщения с ценой, способом, счётом
    или бумагой причина «оплата» стоит на КАЖДОМ черновике, пока оплату не подтвердит код либо не пройдёт 168 ч. KP / KPD
    проверяющего ДОСЛОВНО: 4 наших сообщения с ценой × 3 обычных обмена не об оплате («А шлем дадите?» — «Да, шлем дадим
    бесплатно.», «Хорошо, спасибо.» — «Пожалуйста!», «Буду завтра в 10.» — «Отлично, тогда до завтра!») — причина «оплата»
    у 24 из 24 сразу после цены и у 12 из 12, когда цена названа раньше одного обмена (на ba12c65 — 0 и 0); свои 14 — на
    первом же промежуточном обмене не об оплате — 28 из 28. При подтверждённой кодом оплате — ни у одной. Причина —
    предупреждение на карточке сотрудника: текст черновика, язык, пояснение, проверка чисел и поля карточки от неё не
    зависят (тот же черновик с заглушённым правилом класса отличается ТОЛЬКО списком причин)."""
    assert (len(L_PRICE), len(L_EXCH)) == (4, 3)
    hit = {"KP": 0, "KPD": 0, "свои": 0}
    for m in L_PRICE:
        assert not _old_sign3l(m) and _signs3l(m) == ["sum"], m
        for q, a in L_EXCH:
            assert T.pay_asked(q) is False and K.handoff(q, None) == [], q
            history = [("клиент", "Сколько стоит?"), ("мы", m)]
            for facts in ("none", "cash"):
                hand, state, _conf, _rule, _by, _paid = _run3i(history, q, a, facts)
                hit["KP"] += G_PLAIN in hand
                assert state[0] == V_OURS_MONEY and [w for w in hand if w != T.PAY_WORDS] == [G_PLAIN], (m, q, hand)
            deep = history + [("клиент", "А доставка есть?"), ("мы", "Да, привезём к отелю.")]
            hand, state, _conf, _rule, _by, _paid = _run3i(deep, q, a, "none")
            hit["KPD"] += G_PLAIN in hand
            assert state[0] == V_BACK_OURS_MONEY, (m, q, state)
            assert G_PLAIN not in _run3i(history, q, a, "backed")[0], (m, q)
    for row in L_OWN:
        history, _tail, _text = _own3l(row, 0)
        q, a = L_FILL[_lang3l(row[5])][0]
        for facts in ("none", "cash"):
            hand = _run3i(history, q, a, facts)[0]
            hit["свои"] += hand == [G_PLAIN]
    assert hit == {"KP": 24, "KPD": 12, "свои": 28}, hit
    # причина класса — только список причин: всё прочее в черновике то же, что без неё
    history, tail, text = _own3l(L_OWN[0])
    out, _a, _s, _logs = _draft3g2(history, tail, text, "cash")
    orig = T.topic_reason
    T.topic_reason = lambda topic, facts: (T.PT_NONE, [])
    try:
        mute, _a2, _s2, _logs2 = _draft3g2(history, tail, text, "cash")
    finally:
        T.topic_reason = orig
    assert out["handoff"] == [G_PLAIN] and mute["handoff"] == [] and out["text"] == mute["text"] == text
    assert {k: v for k, v in out.items() if k != "handoff"} == {k: v for k, v in mute.items() if k != "handoff"}, sorted(out)


def test_p3l_adapter_path_to_card_and_request_unchanged():
    """Путь адаптера до карточки: история → `build` (блоки и время суждения в сведениях; в ЗАПРОС модели признаки не идут)
    → исход темы признаком шага → причина кода «оплата» ПЕРВОЙ среди причин не о деньгах текста → поля карточки
    сотрудника (слова → категория → ярлык действия, строка «НУЖЕН ЧЕЛОВЕК», «Отправить» открыто с пометкой). Сверка не
    завершена и версия по пояснению — тот же путь. Причина модели об оплате отпадает как повтор."""
    import wa_agent_tg as TG
    label = TG.CARD_ACTIONS[K.MONEY_PAYMENT_UNCLEAR]
    for row in (L_OWN[0], L_OWN[4], L_OWN[7], L_OWN[10]):                         # сумма, способ, место, бумага
        history, tail, text = _own3l(row)
        out, a, s, logs = _draft3g2(history, tail, text, "cash")
        hand = A.draft_out(out)[1]
        assert hand == [G_PLAIN] and K.word_categories(G_PLAIN) and TG.card_actions(hand) == [label], (row[0], hand)
        notes = TG.card_notes(hand, 1, True)
        assert TG.W_HAND in notes and "• " + label in notes and TG.W_SEND_HAND in notes, notes
        assert out["question"] == tail and not [u for u in s.seen if "НУЖЕН ЧЕЛОВЕК" in u or "тема оплаты" in u], row[0]
        assert [ln for ln in logs if ln == "правило класса: %s; причина кода добавлена" % V_BACK_OURS_MONEY], logs
        out, a, s, _logs = _draft3g2(history, tail, text, "over")
        assert a.last["tools"]["state"] == T.OVER and out["handoff"] == [T.INCOMPLETE_WORDS, G_PLAIN], out["handoff"]
        out, a, _s, _logs = _draft3g2(history, tail, text, "cash", hint=("прежний черновик", "скажи короче"))
        assert a.last["info"].get("hint") is True and out["handoff"] == [G_PLAIN], out["handoff"]
    history, tail, text = _own3l(L_OWN[0])
    q = tail + " И есть ли свободный NMAX со скидкой?"
    out, _a, _s, _logs = _draft3g2(history, q, "Уточню у коллег и вернусь.", "cash")
    assert out["handoff"] == [G_PLAIN, K.REASON_WORDS[K.R_AVAILABILITY], K.REASON_WORDS[K.R_DISCOUNT]], out["handoff"]
    out, _a, _s, _logs = _draft3g2(history, tail, text, "cash", handoff=["клиент сообщает об оплате — проверьте поступление"])
    assert out["handoff"] == [G_PLAIN], out["handoff"]


def test_p3l_named_residual_requisites_outside_dictionary_still_no_reason():
    """ИМЕННОЙ ОСТАТОК ПОСЛЕ ШАГА — проверка ФИКСИРУЕТ нынешний исход и НЕ означает «закрыто». (1) Реквизиты вне словаря
    кода: «Where to?» → «Our account: Test Bank, TEST-ACC-0042, Test Rent Co.» (цепочка Г1 проверяющего), «PromptPay
    works: 081 000 0000.», «Our Kasikorn account: TEST-ACC-0042.», «Реквизиты пришлю следующим сообщением.» — ни суммы с
    валютой, ни способа, ни места денег, ни бумаги, ни слова оплаты: тему не открывает никто, ответ вне форм N4 уходит
    без причины кода при обоих наборах фактов. (2) Деньги не называл никто, истории нет: «Скинул.» → «Да, ждём вас завтра
    в 10.» — без причины. Слово в словарь по решению не добавляется; краткое подтверждение на тех же цепочках причину N4
    несёт (правило В)."""
    assert len(L_RESIDUAL) == 4 and L_RESIDUAL[0][1] == L_G1_NO_SIGN[0]
    for q, ours, tail, text in L_RESIDUAL:
        assert not _old_sign3l(K.mask(ours)[0]) and not _signs3l(K.mask(ours)[0]) and not _signs3l(ours), ours
        for facts in ("none", "cash"):
            hand, state, conf, rule, _by, _paid = _run3i([("клиент", q), ("мы", ours)], tail, text, facts)
            assert hand == [] and state[0] == V_NONE and not conf and not rule, (ours, facts, hand)     # ← остаток, не успех
        brief = "Thank you, received!" if _en3l(text) else "Спасибо, получили!"
        assert _run3i([("клиент", q), ("мы", ours)], tail, brief, "cash")[0] == [T.PAY_WORDS], ours
    for tail, text in (("Скинул.", "Да, ждём вас завтра в 10."), ("Сделано.", "Отлично, бронь за вами!"), ("Sent!", "Great, it's yours!")):
        for facts in ("none", "cash"):
            hand, state, _conf, rule, _by, _paid = _run3i([], tail, text, facts)
            assert hand == [] and state[0] == V_NONE and not rule, (tail, text, hand)                   # ← остаток (б), не успех


def test_p3l_dictionaries_not_extended():
    """Слов и выражений не добавлено: шаблоны четырёх определений шага и слова оплаты побайтно те же, что на ba12c65
    (отпечатки сняты с него), и ВСЕ скомпилированные выражения модулей `wa_agent_tools` (71) и `wa_agent_knowledge`
    (22) — тоже (один отпечаток на модуль). Определения шага — существующие имена модуля, новых выражений нет."""
    import hashlib

    def mark(rx):
        return hashlib.sha256(rx.pattern.encode("utf-8")).hexdigest()[:16]

    def whole(mod):
        rows = sorted("%s=%s" % (n, v.pattern) for n, v in vars(mod).items() if hasattr(v, "pattern"))
        return len(rows), hashlib.sha256("|".join(rows).encode("utf-8")).hexdigest()[:16]
    assert {n: mark(getattr(T, n)) for n in L_PRINTS_T} == L_PRINTS_T
    assert {n: mark(getattr(K, n)) for n in L_PRINTS_K} == L_PRINTS_K
    assert {"T": whole(T), "K": whole(K)} == L_PRINTS_ALL, (whole(T), whole(K))


# ═══ п.3m: деньги, названные стороной существующим определением ВНЕ открывателей, открывают тему (блокер B2) ════════
# Узкая независимая приёмка шага 3l (fix_review3l/VERDICT.md, FAIL на d07b895): деньги НАЗВАНЫ стороной существующим
# определением либо ярлыком кода, которого нет среди открывателей темы, → бессловесное сообщение клиента (в т.ч. фото без
# подписи) → ответ с содержанием либо вне форм N4 («Да, ждём вас завтра в 10.», «Отлично, бронь за вами!») — причины кода
# `[]`. Три формы, сообщения — из FAQ дерева: (а) НАША сумма в иной валюте (её видит `_PM_AMT`, а `K.thb_amounts` нет);
# (б) НАШЕ слово залога (`_PF_DEP`, ярлык «депозит»); (в) деньги назвал КЛИЕНТ в истории — сумма либо слова оплаты с
# общей причиной кода «вопрос об оплате» / «депозит», без `pay_asked` и без бумаги. Решение координатора 11.10 —
# лекарство Л2 проверяющего целиком: наш ответ открывает тему ещё суммой в любой валюте и словом залога; блок клиента —
# общей причиной «вопрос об оплате» / «депозит» либо суммой в любой валюте. Сторона шага 3l «вопрос об оплате клиента
# сам по себе не открывает» ОТМЕНЕНА. Тема — состояние (168 ч); при подтверждённой кодом оплате причины нет; признаки
# шага ДОБАВОЧНЫЕ и к признакам шага 3l (где тема была открыта и до шага — имя исхода и слова прежние). Слов, списков и
# выражений не добавлено. Всё — настоящим путём адаптера (`_draft3g2`), причин модели нет.
V_OURS_NAMED = "тема оплаты открыта: наш последний ответ назвал сумму в любой валюте или залог"
V_BACK_OURS_NAMED = "тема оплаты открыта раньше, чем один обмен назад: наш ответ назвал сумму в любой валюте или залог"
V_PREV_NAMED = "тема оплаты открыта: сообщение клиента перед нашим последним ответом — вопрос об оплате, залог или сумма"
V_BACK_NAMED = "тема оплаты открыта раньше, чем один обмен назад: сообщение клиента — вопрос об оплате, залог или сумма"
# форма (а) — ДОСЛОВНО fix_review3l/gen_own3l.py, семейства D2 и D2q (5 наших сообщений; у D2q — первые два после вопроса
# клиента о рублях). `M_D2_LEFT` — ИМЕННОЙ ОСТАТОК: «USDT» не знает ни одно определение кода
M_D2 = ["С вас 21 500 руб за 10 суток.", "Можно в рублях на Т-Банк: 21 500 руб.", "Бронь держим до вечера, ждём 3000 руб.",
        "That's $230 for ten days.", "Итого 230 USDT за 10 суток."]
M_D2_LEFT = "Итого 230 USDT за 10 суток."
M_D2Q = "Можно оплатить в рублях?"
# форма (б) — ДОСЛОВНО семейство D1 (третье — типовой ответ FAQ дерева)
M_D1 = ["Бронь держим до вечера, ждём депозит.", "Внесите залог, и байк ваш.",
        "Можно зафиксировать залог в долларах (200 USDT) и вернуть так же.", "We hold the bike for you once the deposit is in."]
# форма (в) — ДОСЛОВНО семейство CL: (сообщение клиента о деньгах, наш нейтральный ответ)
M_CL = [("С меня 7790 бат, верно?", "Да, верно."), ("Могу закинуть 1000 бат сегодня, остальное при встрече.", "Да, так можно."),
        ("Доставку и аренду оплачу наличными, депозит переводом.", "Хорошо, договорились."),
        ("I can send 1000 baht today and the rest on pickup.", "Yes, that works.")]
# «поздняя оплата» — ДОСЛОВНО fix_review3l/gen_probeb3l.py (семейства LATED2, LATED1, LATECL): цена в батах в формате FAQ
# названа 9 суток назад (тема закрыта давностью), сегодня — обмен о деньгах, хвост — фото без подписи либо «Скинул.»
M_QUOTE = "NMAX 155CC | 10 дней: 7 790 ฿ (779 ฿/день), депозит 3 000 ฿"
M_LATE = [("Можно оплатить в рублях?", "Можно в рублях на Т-Банк: 21 500 руб."),
          ("Залог можно в долларах?", "Можно зафиксировать залог в долларах (200 USDT) и вернуть так же."),
          ("Доставку и аренду оплачу наличными, депозит переводом.", "Хорошо, договорились.")]
M_LATE_ANS = ["Отлично, бронь за вами!", "Да, ждём вас завтра в 10."]
# СВОИ 13: (чья сторона назвала деньги, признак шага — РОВНО один, сообщение клиента, наш ответ, число промежуточных
# обменов не об оплате, бессловесный хвост, ответ с содержанием либо вне форм N4). «ours» — деньги назвал НАШ ответ
# (сумма в иной валюте `amt` / слово залога `dep`), вопрос клиента нейтрален; «theirs» — деньги назвал КЛИЕНТ (общая
# причина «вопрос об оплате» `ask` / «депозит» `dep`, сумма `amt` — её видит только `_PM_AMT`, `thb` — только
# `K.thb_amounts`), наш ответ нейтрален
M_OWN = [
    ("ours", "amt", "Сколько с меня?", "С вас 21 500 рублей за 10 суток.", 1, "Скинул.", "Да, ждём вас завтра в 10."),
    ("ours", "amt", "А в долларах сколько?", "В долларах это $230 за десять суток.", 2, "Сделано.", "Отлично, бронь за вами!"),
    ("ours", "amt", "How much in euros?", "That would be 210 EUR for ten days.", 1, "Sent!", "Great, it's yours!"),
    ("ours", "amt", "А в евро?", "В евро выходит 210 евро за 10 суток.", 2, "Готово, проверяйте.", "Отлично, тогда оформляю договор."),
    ("ours", "dep", "Что нужно для брони?", "Внесите залог, и байк ваш.", 1, "Сделал.", "Да, ждём вас завтра в 10."),
    ("ours", "dep", "Байк точно будет?", "Бронь держим до вечера, ждём депозит.", 2, "Готово.", "Отлично, бронь за вами!"),
    ("ours", "dep", "What do I need to do?", "We hold the bike for you once the deposit is in.", 1, "Done.", "Yes, see you tomorrow at 10."),
    ("ours", "dep", "Что по условиям?", "Депозит возвращаем при сдаче байка.", 2, "Улетело.", "Отлично, тогда оформляю договор."),
    ("theirs", "ask", "Оплата при получении, верно?", "Да, всё так.", 1, "Скинул.", "Да, ждём вас завтра в 10."),
    ("theirs", "dep", "Залог внесу при встрече.", "Хорошо, договорились.", 2, "Сделано.", "Отлично, бронь за вами!"),
    ("theirs", "amt", "У меня с собой только 200 долларов.", "Ничего страшного, разберёмся.", 1, "Готово.", "Отлично, тогда оформляю договор."),
    ("theirs", "amt", "I have 230 dollars with me.", "No problem at all.", 2, "Sent!", "Great, it's yours!"),
    ("theirs", "thb", "THB 7,790 for ten days, right?", "Yes, that's right.", 1, "Done.", "Yes, see you tomorrow at 10.")]
# изменённые ожидания прежних проверок — поимённые данные: вопросы клиента списков Г1 (`I_G1` + `I_G1_OWN`) с общей причиной
# «вопрос об оплате» либо «депозит»; сообщение списка «бумага об оплате» с общей причиной «вопрос об оплате»
M_G1_ASKS = ("Как можно оплатить?", "Можно оплатить картой?", "How can I pay?", "Can I pay by card?", "Сколько с залогом?",
             "And with the deposit?")
M_PAPER_ASK = "Вот подтверждение перевода."
# ЦЕНА — ДОСЛОВНО: KBQ (fix_review3k/gen_my3k.py, ASKMSG — 9) и ASKQ (fix_review3l/gen_own3l.py, ASK — 6): «вопрос об
# оплате» клиента сам по себе → нейтральный ответ → «Ну что?» → ответ вне форм N4
M_KBQ = ["Как оплатить?", "Оплачу завтра.", "Можно оплатить картой?", "Когда нужно оплатить?", "Нужна предоплата?",
         "How can I pay?", "I will pay tomorrow.", "Where do I pay?", "Can I pay by card?"]
M_ASKQ = ["Сколько нужно оплатить?", "Оплата при получении?", "Можно оплатить на месте?", "Предоплата обязательна?",
          "Is payment on pickup?", "Do I need to pay in advance?"]
# цена слова залога: обычные НАШИ фразы со словом «залог / депозит» без суммы — и та, что говорит «депозит не нужен»
M_DEP_COST = ["Залог можно паспортом.", "Депозит не нужен, достаточно паспорта.", "No deposit is needed with a passport."]
# ТАБЛИЦА ИСЧЕРПАНИЯ — закреплена исполнением: (определение / ярлык кода, фраза, исход). `M_T_OURS` — наш ответ,
# `M_T_THEIRS` — блок клиента. Исход `V_NONE` — ИМЕННОЙ ОСТАТОК (определение фразу видит, тему не открывает)
M_T_OURS = [
    ("группа оплаты R_MONEY", "Оплатить можно при встрече.", V_OURS),
    ("_PQ_PAYWORD", "Деньги можно передать курьеру при встрече.", V_OURS),
    ("_PayClaim", "Оплата получена, спасибо!", V_OURS), ("_PayClaim.unsettled", "Проверим и вернёмся с ответом.", V_OURS),
    ("K.thb_amounts", "С вас 7790 бат.", V_OURS_MONEY), ("_PF_METHOD", "Можно картой курьеру при встрече.", V_OURS_MONEY),
    ("_PF_HELD", "Номер счёта: TEST-ACC-0042.", V_OURS_MONEY), ("_PQ_PROOF", "Квитанцию выдадим при встрече.", V_OURS_MONEY),
    ("_PM_AMT", "С вас 21 500 руб за 10 суток.", V_OURS_NAMED), ("_PF_DEP", "Внесите залог, и байк ваш.", V_OURS_NAMED),
    ("_DEP_CLAIM", "Залог получен.", V_OURS_NAMED),
    ("_PM_BARE", "С вас 7790 за 10 суток.", V_NONE), ("_PN_CODE", "That's USD 230 for ten days.", V_NONE),
    ("USDT", M_D2_LEFT, V_NONE), ("_OTHER_MONEY", "Бронь держим до вечера, ждём аванс.", V_NONE),
    ("_PC_DOC", "Реквизиты отправили вам отдельным сообщением.", V_NONE), ("_PD_DEBT", "За вами остался долг за шлем.", V_NONE),
    ("_PD_MONEY", "Баланс по вашей брони нулевой.", V_NONE), ("_ASK_NOUN", "Взнос можно сделать завтра.", V_NONE),
    ("_PAY_PROOF", "Send the proof here.", V_NONE), ("ярлык «возврат денег»", "A refund takes two days.", V_NONE),
    ("ярлык «спор»", "Жалобу передали руководителю.", V_NONE),
    ("ярлык «повреждения и штрафы»", "Штраф за царапину — по прайсу.", V_NONE),
    ("_REFUND_PROMISE", "Вернём всё в конце аренды.", V_NONE), ("_CHANGE", "Сдачу отдадим в конце.", V_NONE)]
M_T_THEIRS = [
    ("pay_asked", "Деньги пришли?", V_PREV), ("общая причина «заявил»", "Чек во вложении.", V_PREV_SAID),
    ("общая причина «неясно»", "Чек дадите?", V_PREV_SAID), ("_PQ_PROOF", "Квитанция во вложении.", V_PREV_PROOF),
    ("общая причина «вопрос об оплате»", "Как оплатить?", V_PREV_NAMED),
    ("общая причина «депозит»", "А залог обязателен?", V_PREV_NAMED),
    ("K.thb_amounts", "С меня THB 7,790, верно?", V_PREV_NAMED), ("_PM_AMT", "У меня с собой только 200 долларов.", V_PREV_NAMED),
    ("cash_said", "Дал курьеру 8000 бат наличными.", V_PREV_NAMED),
    ("_PQ_PAYWORD", "Деньги отдам курьеру.", V_NONE), ("_PQ_PAYWORD", "Средства передам курьеру.", V_NONE),
    ("_PF_METHOD", "Можно картой?", V_NONE), ("_PF_HELD", "На какой счёт?", V_NONE), ("_PD_DEBT", "Долг за мной есть?", V_NONE),
    ("_PM_BARE", "С меня 7790, верно?", V_NONE), ("_PN_CODE", "Is USD 230 ok?", V_NONE), ("_PAY_DONE", "Скинул.", V_NONE),
    ("_PAY_PROOF", "Proof attached.", V_NONE), ("_OTHER_MONEY", "Аванс нужен?", V_NONE),
    ("_PC_DOC", "Пришлите реквизиты.", V_NONE), ("_ASK_NOUN", "Взнос сделаю завтра.", V_NONE),
    ("_PD_MONEY", "Какой у меня баланс?", V_NONE), ("ярлык «возврат денег»", "Верните, пожалуйста, за шлем.", V_NONE),
    ("ярлык «спор»", "У меня претензия по байку.", V_NONE),
    ("ярлык «повреждения и штрафы»", "Я поцарапал байк, что теперь?", V_NONE), ("_CHANGE", "Сдача будет?", V_NONE)]
# отпечатки определений шага (sha256 шаблона, 16 знаков) — сняты с d07b895: выражения, строки-шаблоны и слова причин те же
M_PRINTS_RX = {"_PF_DEP": "db2ddac8172c7e1e", "_PF_METHOD": "85fbdb4b7dbe24ec", "_PF_HELD": "f48e6ed3e373ad32"}
M_PRINTS_STR = {"_PM_AMT": "1aeb409af6d8a644", "_PM_BARE": "ffa1c90f5fb84285", "_ASK_AMT": "00e6f83de4eb679d"}
M_PRINTS_LABELS = {"damage_fines": "a4af662f2c29d1d8", "deposit": "862e8fd57b2a48e2", "refund": "2a15a7e95ea59527",
                   "dispute": "093cb7b0f235f46a", "payment": "e980d8fc35d09e4b"}
M_PRINTS_ALL = {"T": (71, "a1716e9f7a0d5beb"), "K": (22, "34eff516dd9e1e3b"), "T_str": (33, "6c6d6ceca5ddf0bf"),
                "K_words": "fa3f9028dd677f56"}


def _amt3m(text):
    return re.search(T._PM_AMT, text, re.I) is not None


def _new3m(text):
    """Какие из ДВУХ определений шага 3m видят НАШ текст: сумма в любой валюте (`_PM_AMT`), залог (`_PF_DEP`)."""
    return [n for n, on in (("amt", _amt3m(text)), ("dep", T._PF_DEP.search(text) is not None)) if on]


def _their3m(text):
    """Какие признаки шага 3m видят блок КЛИЕНТА: общая причина «вопрос об оплате» / «депозит» (`K.money_labels`), сумма
    в батах (`K.thb_amounts`), сумма в любой валюте (`_PM_AMT`)."""
    labels = [k for k, _w in K.money_labels(text)]
    return [n for n, on in (("ask", K.MONEY_PAYMENT_ASK in labels), ("dep", K.MONEY_DEPOSIT in labels),
                            ("thb", bool(K.thb_amounts(text))), ("amt", _amt3m(text))) if on]


def _kra3m(ours, q=None):
    """Форма цепочки приёмки (`kra_like`): вопрос клиента → НАШЕ сообщение → бессловесное сообщение → три ответа."""
    lang = _lang3l(ours)
    return [([("клиент", q or L_KRA_Q[lang]), ("мы", ours)], L_KRA_TAILS[lang][0], text) for text in L_KRA_ANS[lang]]


def _late3m(q, a):
    """Форма цепочки «поздняя оплата»: цена в батах 9 суток назад → сегодняшний обмен → (фото | «Скинул.») × два ответа."""
    history = [("клиент", "Сколько стоит NMAX на 10 суток?", 216.2), ("мы", M_QUOTE, 216), ("клиент", q, 1), ("мы", a, 0.8)]
    return [(history, tail, text) for tail in (I_PHOTO, "Скинул.") for text in M_LATE_ANS]


def _own3m(row, n=None):
    """Своя цепочка шага 3m → (история, хвост, ответ): открывающий обмен + `n` промежуточных обменов не об оплате."""
    _side, _sign, client, ours, k, tail, text = row
    fill = L_FILL[_lang3l(text)][:k if n is None else n]
    return [("клиент", client), ("мы", ours)] + [x for c, o in fill for x in (("клиент", c), ("мы", o))], tail, text


def test_p3m_definition_named_outcomes_any_currency_deposit_and_client_block():
    """Определение темы после шага 3m — исход назван на каждой дороге. `_topic_ours`: прежние признаки — `PT_OURS`,
    признаки шага 3l — `PT_OURS_MONEY` (как были); ни одного из них, но сумма в ЛЮБОЙ валюте (`_PM_AMT`) либо залог
    (`_PF_DEP`) — `PT_OURS_NAMED`; иначе `PT_NONE`. `_topic_theirs`: `pay_asked`, общая причина «заявил / неясно», бумага
    — как были; ни одного из них, но общая причина «вопрос об оплате» / «депозит» либо сумма в любой валюте
    (`K.thb_amounts`, `_PM_AMT`) — `PT_PREV_NAMED`; иначе `PT_NONE`. Раньше одного обмена — свои имена. Слова причины —
    нейтральное «оплата». Признаки шага ДОБАВОЧНЫЕ и к признакам шага 3l: прежний признак либо признак 3l где угодно в
    истории решает сам — имя и слова прежние; из признаков шага 3m берётся ближайший к хвосту, в одном обмене блок
    клиента раньше нашего ответа. Хвост судится по-прежнему (`pay_asked`)."""
    assert (T.PT_OURS_NAMED, T.PT_BACK_OURS_NAMED, T.PT_PREV_NAMED, T.PT_BACK_NAMED) \
        == (V_OURS_NAMED, V_BACK_OURS_NAMED, V_PREV_NAMED, V_BACK_NAMED)
    assert len(set(T.PT_OPEN)) == len(T.PT_OPEN) == 15 and len({V_OLD, V_NONE, V_PAID} | set(T.PT_OPEN)) == 18
    # НАШ ответ: каждый из двух признаков шага в одиночку
    alone = {"amt": "С вас 21 500 руб за 10 суток.", "dep": "Внесите залог, и байк ваш."}
    for sign, text in alone.items():
        assert _new3m(text) == [sign] and not _old_sign3l(text) and not _signs3l(text), (sign, text)
        assert T._topic_ours(text) == V_OURS_NAMED, (sign, text)
        assert T.pay_topic("Сделано.", "Сколько?", text) == (V_OURS_NAMED, G_PLAIN), (sign, text)
        assert T.pay_topic("Сделано.", blocks=[("мы", "Да, шлем дадим.", None), ("клиент", "А шлем?", None),
                                               ("мы", text, None), ("клиент", "Сколько?", None)]) \
            == (V_BACK_OURS_NAMED, G_PLAIN), (sign, text)
    for text in M_D2 + M_D1:
        want = V_NONE if text == M_D2_LEFT else V_OURS_NAMED
        assert T._topic_ours(text) == want and not _old_sign3l(text) and not _signs3l(text), text
        assert bool(_new3m(text)) == (want != V_NONE), (text, _new3m(text))
    assert [_new3m(t) for t in M_D2] == [["amt"]] * 4 + [[]] and [_new3m(t) for t in M_D1] == [["dep"]] * 4
    # прежние имена — прежние: признак 3g либо 3l рядом с признаком шага 3m решает сам
    assert T._topic_ours("К оплате 21 500 руб.") == V_OURS and T._topic_ours("Залог — 3000 бат или паспорт.") == V_OURS_MONEY
    assert T._topic_ours("Можно картой, это 230 USD.") == V_OURS_MONEY and T._topic_ours("Депозит на счёт, оплата потом.") == V_OURS
    # БЛОК КЛИЕНТА: каждый признак шага в одиночку
    single = {"ask": "Как оплатить?", "dep": "А залог обязателен?", "amt": "У меня с собой только 200 долларов.",
              "thb": "THB 7,790 for ten days, right?"}
    for sign, x in single.items():
        assert _their3m(x) == [sign] and T.pay_asked(x) is False and T._PQ_PROOF.search(x) is None, (sign, x, _their3m(x))
        assert not [k for k, _w in K.money_labels(x) if k in (K.MONEY_PAYMENT, K.MONEY_PAYMENT_UNCLEAR)], x
        assert T._topic_theirs(x) == V_PREV_NAMED, (sign, x)
        assert T.pay_topic(x)[0] == V_NONE, x                                       # хвост — определение прежнее
        assert T.pay_topic("Ну что?", x, "Одну минуту.") == (V_PREV_NAMED, G_PLAIN), x
        assert T.pay_topic("Ну что?", blocks=[("мы", "Ок.", None), ("клиент", "Ок", None), ("мы", "Минуту.", None),
                                              ("клиент", x, None)]) == (V_BACK_NAMED, G_PLAIN), x
    for q, a in M_CL:
        assert T._topic_theirs(q) == V_PREV_NAMED and T._topic_ours(a) == V_NONE and T.pay_asked(q) is False, (q, a)
    assert [_their3m(q) for q, _a in M_CL] == [["thb", "amt"], ["thb", "amt"], ["ask", "dep"], ["thb", "amt"]]
    for x in ("Вот чек.", G_PAID, "Квитанция во вложении.", "Скрин перевода на 7790 бат во вложении."):   # прежние сильнее
        assert T._topic_theirs(x) in (V_PREV, V_PREV_SAID, V_PREV_PROOF), x
    for x in ("Спасибо!", "А шлем дадите?", "Скинул.", "Sent!", "", None, "[фото]", "Забронируете за мной?"):
        assert T._topic_theirs(x) == V_NONE, x
    # ДОБАВОЧНЫЕ и к шагу 3l: признак 3g либо 3l где угодно в истории решает сам — имя и слова прежние
    wait, m3l, m3m = ("клиент", "Ок", None), ("мы", "Итого 7790 бат.", None), ("мы", "С вас 21 500 руб.", None)
    ask = ("клиент", "Как оплатить?", None)
    assert T.pay_topic("Ну что?", blocks=[m3m, wait, m3l, ("клиент", "Сколько?", None)]) == (V_BACK_OURS_MONEY, G_PLAIN)
    assert T.pay_topic("Ну что?", blocks=[("мы", "Минуту.", None), ask, ("мы", "Спасибо!", None),
                                          ("клиент", "Квитанция во вложении.", None)]) == (V_BACK_PROOF, G_PLAIN)
    assert T.pay_topic("Ну что?", blocks=[m3m, wait, ("мы", "К оплате 7790 бат.", None), ("клиент", "Сколько?", None)]) \
        == (V_BACK_OURS, G_PLAIN)
    assert T.pay_topic("Ну что?", blocks=[("мы", "Минуту.", None), ask, ("мы", "Спасибо!", None), ("клиент", G_PAID, None)]) \
        == (V_BACK, G_SAID)
    assert T.pay_topic("Ну что?", blocks=[m3l, ask]) == (V_OURS_MONEY, G_PLAIN)       # в одном обмене: 3l сильнее 3m
    # из признаков шага 3m — ближайший к хвосту; в одном обмене блок клиента раньше нашего ответа
    assert T.pay_topic("Ну что?", blocks=[m3m, ask]) == (V_PREV_NAMED, G_PLAIN)
    assert T.pay_topic("Ну что?", blocks=[m3m, wait, ("мы", "Минуту.", None), ask]) == (V_OURS_NAMED, G_PLAIN)
    assert T.pay_topic("Ну что?", blocks=[("мы", "Минуту.", None), wait, m3m, ask]) == (V_BACK_NAMED, G_PLAIN)
    # правило класса на новых именах: не подтверждена — причина, подтверждена — нет; `PAY_WORDS` правило не ставит
    for name in (V_OURS_NAMED, V_BACK_OURS_NAMED, V_PREV_NAMED, V_BACK_NAMED):
        assert name in T.PT_OPEN and T.topic_reason((name, G_PLAIN), []) == (name, [G_PLAIN])
        assert T.topic_reason((name, G_PLAIN), T.accepted(_results_no_second())) == (name, [G_PLAIN])
        assert T.topic_reason((name, G_PLAIN), T.accepted(_results_backed())) == (V_PAID, [])


def test_p3m_form_a_our_sum_in_other_currency_has_class_reason():
    """Форма (а) блокера B2 ДОСЛОВНО (семейства D2 и D2q приёмки): НАША сумма в иной валюте — рубли, доллары — без слова
    оплаты кода → бессловесное сообщение («Скинул.», «Sent!») → три ответа с содержанием либо вне форм N4 × «строки кассы
    нет» и «касса без второго источника». На d07b895 причины `[]` у 30 из 30 (D2) и 12 из 12 (D2q). Теперь: D2 — причина
    класса «оплата» у 24 из 30 (исход `PT_OURS_NAMED`); остаются 6 записей ИМЕННОГО ОСТАТКА «Итого 230 USDT за 10
    суток.» — «USDT» не знает ни одно определение кода, слово не добавляется; D2q (после вопроса клиента «Можно оплатить
    в рублях?») — 12 из 12 (тему открывает блок клиента — `PT_PREV_NAMED`). Краткий ответ на те же цепочки — причина N4
    как была, рядом причина класса."""
    rows = [r for ours in M_D2 for r in _kra3m(ours)]
    assert len(rows) * 2 == 30
    for ours in M_D2:
        assert T.pay_asked(L_KRA_TAILS[_lang3l(ours)][0]) is False and T._topic_theirs(L_KRA_Q[_lang3l(ours)]) == V_NONE
    bad = _class3l([r for r in rows if r[0][1][1] != M_D2_LEFT], V_OURS_NAMED)
    assert not bad, bad
    left = [r for r in rows if r[0][1][1] == M_D2_LEFT]
    assert len(left) * 2 == 6
    for history, tail, text in left:                                                # ← именной остаток, не успех
        assert not _amt3m(M_D2_LEFT) and K.thb_amounts(M_D2_LEFT) == [] and T._topic_ours(M_D2_LEFT) == V_NONE
        for facts in ("none", "cash"):
            hand, state, conf, rule, _by, _paid = _run3i(history, tail, text, facts)
            assert hand == [] and state[0] == V_NONE and not conf and not rule, (text, facts, hand, state)
    rows_q = [r for ours in M_D2[:2] for r in _kra3m(ours, M_D2Q)]
    assert len(rows_q) * 2 == 12 and _their3m(M_D2Q) == ["ask"]
    bad = _class3l(rows_q, V_PREV_NAMED)
    assert not bad, bad
    for history, tail, _text in (rows[0], rows[9], rows_q[0]):
        brief = "Yes." if _en3l(tail) else "Да."
        for facts in ("none", "cash"):
            assert _run3i(history, tail, brief, facts)[0] == [T.PAY_WORDS, G_PLAIN], (tail, facts)


def test_p3m_form_b_our_deposit_word_has_class_reason():
    """Форма (б) блокера B2 ДОСЛОВНО (семейство D1 приёмки): НАШЕ слово залога — «Бронь держим до вечера, ждём депозит.»,
    «Внесите залог, и байк ваш.», типовой ответ FAQ «Можно зафиксировать залог в долларах (200 USDT) и вернуть так же.»,
    «We hold the bike for you once the deposit is in.» — без суммы в батах и без слова оплаты кода → бессловесное
    сообщение → три ответа × два набора фактов. На d07b895 причины `[]` у 24 из 24; теперь причина класса «оплата» у 24 из
    24, исход `PT_OURS_NAMED` (определение — существующее `_PF_DEP`)."""
    rows = [r for ours in M_D1 for r in _kra3m(ours)]
    assert len(rows) * 2 == 24
    bad = _class3l(rows, V_OURS_NAMED)
    assert not bad, bad


def test_p3m_form_c_client_named_money_in_history_has_class_reason():
    """Форма (в) блокера B2 ДОСЛОВНО (семейство CL приёмки): деньги назвал КЛИЕНТ — сумма в батах («С меня 7790 бат,
    верно?», «Могу закинуть 1000 бат сегодня, остальное при встрече.», «I can send 1000 baht today…») либо слова оплаты и
    залога с общей причиной кода «вопрос об оплате» / «депозит» («Доставку и аренду оплачу наличными, депозит переводом.»
    — частый сценарий FAQ) → наш нейтральный ответ («Да, верно.», «Хорошо, договорились.») → бессловесное сообщение → два
    ответа × два набора фактов. На d07b895 причины `[]` у 16 из 16; теперь причина класса «оплата» у 16 из 16, исход
    `PT_PREV_NAMED`."""
    rows = []
    for q, a in M_CL:
        lang = _lang3l(q)
        rows += [([("клиент", q), ("мы", a)], L_KRA_TAILS[lang][0], text) for text in L_KRA_ANS[lang][1:]]
    assert len(rows) * 2 == 16
    bad = _class3l(rows, V_PREV_NAMED)
    assert not bad, bad


def test_p3m_late_payment_after_stale_price_has_class_reason():
    """«Поздняя оплата» ДОСЛОВНО (семейства LATED2, LATED1, LATECL приёмки): цена в батах (формат FAQ) названа 9 суток
    назад — тема закрыта давностью; сегодня — обмен «Можно оплатить в рублях?» → «Можно в рублях на Т-Банк: 21 500 руб.»
    / «Залог можно в долларах?» → типовой ответ FAQ / «Доставку и аренду оплачу наличными, депозит переводом.» →
    «Хорошо, договорились.» → фото без подписи либо «Скинул.» → два ответа × два набора фактов. На d07b895 причины `[]` у
    8 из 8 в каждом семействе (исход `PT_OLD`); теперь причина класса «оплата» у 24 из 24 — тему открывает сегодняшний
    блок клиента (`PT_PREV_NAMED`). Близнец: краткий ответ «Спасибо, получили!» — причина N4 как была, рядом причина
    класса."""
    assert T._topic_ours(M_QUOTE) == V_OURS_MONEY and len(M_LATE) == 3
    for q, a in M_LATE:
        rows = _late3m(q, a)
        assert len(rows) * 2 == 8 and T._topic_theirs(q) == V_PREV_NAMED, q
        bad = _class3l(rows, V_PREV_NAMED)
        assert not bad, bad
        for facts in ("none", "cash"):
            assert _run3i(rows[0][0], I_PHOTO, "Спасибо, получили!", facts)[0] == [T.PAY_WORDS, G_PLAIN], (q, facts)
    # без сегодняшнего денежного обмена та же старая цена тему не открывает — исход «закрыта давностью», причины нет
    old = [("клиент", "Сколько стоит NMAX на 10 суток?", 216.2), ("мы", M_QUOTE, 216), ("клиент", "Беру.", 1),
           ("мы", "Записали, ждём вас.", 0.8)]
    for facts in ("none", "cash"):
        hand, state, _conf, rule, _by, _paid = _run3i(old, "Скинул.", "Отлично, бронь за вами!", facts)
        assert hand == [] and state[0] == V_OLD and rule == ["правило класса: %s; причина кода не нужна" % V_OLD], (hand, state)


def test_p3m_own_chains_money_named_then_other_exchanges_then_wordless_message():
    """СВОИ 13 цепочек: деньги названы РОВНО одним признаком шага 3m и ни одним прежним — НАШИМ ответом (сумма в рублях,
    долларах, евро — 4; слово залога — 4) либо КЛИЕНТОМ при нашем нейтральном ответе (общая причина «вопрос об оплате» —
    1, «депозит» — 1, сумма в долларах — 2, сумма в батах с кодом валюты впереди — 1) → один или два обмена не об оплате
    (шлем, часы работы) → бессловесное сообщение клиента → ответ с содержанием либо вне форм N4. На d07b895 причины `[]`
    у 26 из 26; теперь при обоих наборах фактов — ровно причина класса «оплата», исход `PT_BACK_OURS_NAMED` /
    `PT_BACK_NAMED` (тема — состояние); без промежуточных обменов — `PT_OURS_NAMED` / `PT_PREV_NAMED`."""
    assert len(M_OWN) == 13 and {r[4] for r in M_OWN} == {1, 2}
    assert [(r[0], r[1]) for r in M_OWN].count(("ours", "amt")) == 4 and [(r[0], r[1]) for r in M_OWN].count(("ours", "dep")) == 4
    for side, sign, client, ours, n, tail, text in M_OWN:
        assert T.pay_asked(tail) is False and K.handoff(tail, None) == [] and T._PQ_PROOF.search(tail) is None, tail
        assert T._PayClaim(True, (), T.PB_BARE).search(text) is None, (text, T._PAY_CLAIM.explain(text, True))
        if side == "ours":
            assert T._topic_theirs(client) == V_NONE and not _their3m(client), client
            assert _new3m(ours) == [sign] and not _old_sign3l(ours) and not _signs3l(ours), (sign, ours, _new3m(ours))
        else:
            assert _their3m(client) == [sign] and T.pay_asked(client) is False, (sign, client, _their3m(client))
            assert T._topic_ours(ours) == V_NONE and not _new3m(ours), ours
    for side, deep, flat in (("ours", V_BACK_OURS_NAMED, V_OURS_NAMED), ("theirs", V_BACK_NAMED, V_PREV_NAMED)):
        rows = [r for r in M_OWN if r[0] == side]
        bad = _class3l([_own3m(r) for r in rows], deep)
        assert not bad, bad
        bad = _class3l([_own3m(r, 0) for r in rows], flat)
        assert not bad, bad


def test_p3m_staleness_of_new_openers():
    """Давность (168 ч) у признаков шага 3m. НАШ ответ с суммой в иной валюте либо словом залога старше предела тему не
    открывает В ЛЮБОМ месте истории — и раньше одного обмена, и последним перед хвостом (как признаки шага 3l); 168 ч и
    свежее — открывает; времени нет — свежий; время суждения не задано — давности нет. Блок КЛИЕНТА — как прочие признаки
    клиента: обмен перед хвостом давностью не судится, раньше — судится. Исход закрытой темы — `PT_OLD`, причины нет.
    Старый признак шага 3l и свежий признак шага 3m — тему открывает свежий. То же — путём адаптера."""
    now, hour = T0, 3600

    def at(text_c, text_o, hours):
        ts = None if hours is None else now - hours * hour
        return [("мы", text_o, ts), ("клиент", text_c, ts)]
    wait = at("Ок", "Минуту.", 1)
    for text in ("С вас 21 500 руб за 10 суток.", "Внесите залог, и байк ваш."):
        for hours, want in ((1, True), (167, True), (168, True), (169, False), (1000, False), (None, True)):
            got = T.pay_topic("Сделано.", blocks=wait + at("Сколько?", text, hours), now=now)
            assert got == ((V_BACK_OURS_NAMED if want else V_OLD), G_PLAIN), (text, hours, got)
            got = T.pay_topic("Сделано.", blocks=at("Сколько?", text, hours), now=now)       # последним перед хвостом
            assert got == ((V_OURS_NAMED if want else V_OLD), G_PLAIN), (text, hours, got)
        assert T.pay_topic("Сделано.", blocks=wait + at("Сколько?", text, 400))[0] == V_BACK_OURS_NAMED, text   # без «сейчас»
    for x in ("Как оплатить?", "А залог обязателен?", "У меня с собой только 200 долларов."):
        for hours, want in ((1, V_BACK_NAMED), (168, V_BACK_NAMED), (169, V_OLD), (None, V_BACK_NAMED)):
            got = T.pay_topic("Ну что?", blocks=wait + at(x, "Одну минуту.", hours), now=now)
            assert got[0] == want, (x, hours, got)
        assert T.pay_topic("Ну что?", blocks=at(x, "Одну минуту.", 500), now=now)[0] == V_PREV_NAMED, x   # перед хвостом
    # старый признак 3l и свежий признак 3m — свежий; свежий признак 3l и свежий 3m — 3l (добавочность)
    assert T.pay_topic("Сделано.", blocks=wait + at("А в рублях?", "В рублях 21 500 руб.", 3) + at("Сколько?", "С вас 7790 бат.", 400),
                       now=now) == (V_BACK_OURS_NAMED, G_PLAIN)
    assert T.pay_topic("Сделано.", blocks=wait + at("А в рублях?", "В рублях 21 500 руб.", 3) + at("Сколько?", "С вас 7790 бат.", 100),
                       now=now) == (V_BACK_OURS_MONEY, G_PLAIN)
    # путь адаптера: (возраст открывающего обмена, есть ли промежуточный обмен) → причина класса и исход
    for hours, deep, opened in ((200, True, False), (169, True, False), (167, True, True), (3, True, True),
                                (200, False, False), (3, False, True), (None, True, True)):
        history = [("клиент", "Сколько с меня?", hours), ("мы", "С вас 21 500 руб за 10 суток.", hours)]
        history += [("клиент", "А шлем дадите?", 2), ("мы", "Да, шлем дадим бесплатно.", 1)] if deep else []
        for facts in ("none", "cash"):
            out, a, _s, logs = _draft3g2(history, "Скинул.", "Да, ждём вас завтра в 10.", facts)
            want = (V_BACK_OURS_NAMED if deep else V_OURS_NAMED) if opened else V_OLD
            assert _state3g2(a) == (want, G_PLAIN) and out["handoff"] == ([G_PLAIN] if opened else []), (hours, deep, out["handoff"])
            assert [ln for ln in logs if ln.startswith("правило класса")] == [
                "правило класса: %s; причина кода %s" % (want, "добавлена" if opened else "не нужна")], logs
    for hours, opened in ((200, False), (3, True)):                                  # блок клиента раньше одного обмена
        history = [("клиент", "Залог внесу при встрече.", hours), ("мы", "Хорошо, договорились.", hours),
                   ("клиент", "А шлем дадите?", 2), ("мы", "Да, шлем дадим бесплатно.", 1)]
        out, a, _s, _logs = _draft3g2(history, "Скинул.", "Да, ждём вас завтра в 10.", "cash")
        assert _state3g2(a)[0] == (V_BACK_NAMED if opened else V_OLD) and out["handoff"] == ([G_PLAIN] if opened else []), hours


def test_p3m_twin_confirmed_payment_adds_nothing():
    """Близнец «оплата подтверждена кодом» (касса аренды обращения + договор той же аренды): ни одной новой причины на
    всех цепочках шага — форма (а) D2 (15) и D2q (6), форма (б) D1 (12), форма (в) CL (8), поздняя оплата (12), свои
    (13), цена «вопрос об оплате» (15): список причин равен причинам кода по входящему, причины N4 нет, исход правила у
    открытой темы — `PT_PAID`. Полезный сценарий (оплата подтверждена, ответ с PDF) правилом не задет."""
    rows = [r for ours in M_D2 for r in _kra3m(ours)] + [r for ours in M_D2[:2] for r in _kra3m(ours, M_D2Q)]
    rows += [r for ours in M_D1 for r in _kra3m(ours)]
    for q, a in M_CL:
        rows += [([("клиент", q), ("мы", a)], L_KRA_TAILS[_lang3l(q)][0], text) for text in L_KRA_ANS[_lang3l(q)][1:]]
    rows += [r for q, a in M_LATE for r in _late3m(q, a)]
    rows += [_own3m(r) for r in M_OWN]
    rows += [([("клиент", x), ("мы", L_NEU[_lang3l(x)])], L_UPD[_lang3l(x)], L_OUT[_lang3l(x)]) for x in M_KBQ + M_ASKQ]
    assert len(rows) == 15 + 6 + 12 + 8 + 12 + 13 + 15
    bad = []
    for history, tail, text in rows:
        hand, state, conf, rule, by_tail, paid = _run3i(history, tail, text, "backed")
        if not paid or hand != by_tail or hand or conf or [ln for ln in rule if "причина кода не нужна" not in ln] \
                or (state[0] in T.PT_OPEN and rule != ["правило класса: %s; причина кода не нужна" % V_PAID]):
            bad.append((_said3i(tail), text, hand, state[0], rule))
    assert not bad, bad
    out, _a, _s, _logs = _draft3g2([("клиент", "Сколько с меня?"), ("мы", "С вас 21 500 руб за 10 суток.")], "Скинул.",
                                  "Да, оплата получена. Договор отправляю следующим сообщением.", "backed")
    assert out["handoff"] == [], out["handoff"]


def test_p3m_twin_message_without_money_sign_does_not_open():
    """Близнец «сообщение стороны без единого денежного признака тему не открывает» — как до шага: обмены о брони, шлеме,
    доставке, договоре, часах работы с обеих сторон (ни один признак 3g, 3i, 3l и 3m их не видит) → бессловесное сообщение
    → ответ с содержанием либо вне форм N4 уходит без причины кода, исход `PT_NONE`, строки правила в журнале нет."""
    plain = [("Здравствуйте, хочу NMAX на 10 дней.", "Здравствуйте! NMAX свободен, оформляем."),
             ("Забронируете за мной?", "Да, бронь за вами на завтра."), ("А шлем дадите?", "Да, шлем дадим бесплатно."),
             ("К отелю привезёте?", "Да, привезём к отелю утром."), ("Пришлите договор.", "Договор пришлём сегодня."),
             ("Hi, I'd like an NMAX for 10 days.", "Hello! The NMAX is free, booking it for you."),
             ("Can you hold it for me?", "It is reserved for you."), ("Is a helmet included?", "Yes, a helmet is included.")]
    for c, o in plain:
        assert T._topic_theirs(c) == V_NONE and not _their3m(c) and T.pay_asked(c) is False and K.money_labels(c) == [], c
        assert T._topic_ours(o) == V_NONE and not _new3m(o) and not _signs3l(o) and not _old_sign3l(o), o
        tail, text = ("Sent!", "Great, it's yours!") if _en3l(c) else ("Скинул.", "Отлично, бронь за вами!")
        for history in ([("клиент", c), ("мы", o)], [("клиент", c), ("мы", o)] + [x for p in plain[:2] for x in (("клиент", p[0]), ("мы", p[1]))]):
            for facts in ("none", "cash"):
                hand, state, conf, rule, _by, _paid = _run3i(history, tail, text, facts)
                assert hand == [] and state[0] == V_NONE and not conf and not rule, (c, o, facts, hand, state)


def test_p3m_cost_payment_question_and_deposit_word_named():
    """ЦЕНА шага (сторона отказа, принята решением координатора; НЕ успех) — числом. (1) «Вопрос об оплате» клиента сам
    по себе ДОСЛОВНО по корпусам приёмки (KBQ — 9, ASKQ — 6): нейтральный ответ → «Ну что?» → ответ вне форм N4 — причина
    «оплата» у 30 из 30 при обоих наборах фактов (на d07b895 — `[]`: сторона «вопрос об оплате не открывает» отменена).
    (2) Обычные обмены НЕ об оплате после «вопроса об оплате» клиента и нашего нейтрального ответа («А шлем дадите?» —
    «Да, шлем дадим бесплатно.», «Хорошо, спасибо.» — «Пожалуйста!», «Буду завтра в 10.» — «Отлично, тогда до завтра!»):
    причина «оплата» у 27 из 27 (было 0). (3) Обычная НАША фраза со словом «залог / депозит» без суммы — и та, что
    говорит «депозит не нужен», — тему открывает: тот же обычный обмен после неё несёт причину «оплата» — 9 из 9 (было 0).
    При подтверждённой кодом оплате — ни у одной. Причина — предупреждение на карточке сотрудника: текст черновика и прочие
    поля итога от неё не зависят (тот же черновик с заглушённым правилом отличается ТОЛЬКО списком причин)."""
    assert (len(M_KBQ), len(M_ASKQ), len(M_DEP_COST)) == (9, 6, 3)
    hit = {"вопрос": 0, "обмен после вопроса": 0, "обмен после залога": 0}
    for x in M_KBQ + M_ASKQ:
        lang = _lang3l(x)
        assert _their3m(x) == ["ask"] and T.pay_asked(x) is False, (x, _their3m(x))
        for facts in ("none", "cash"):
            hand, state, _conf, _rule, _by, _paid = _run3i([("клиент", x), ("мы", L_NEU[lang])], L_UPD[lang], L_OUT[lang], facts)
            hit["вопрос"] += hand == [G_PLAIN] and state == (V_PREV_NAMED, G_PLAIN)
    for x in M_KBQ:
        lang = _lang3l(x)
        for q, a in (L_EXCH if lang == "ru" else [("Is a helmet included?", "Yes, a helmet is included."), ("Ok, thanks.", "You're welcome!"),
                                                    ("I'll come at 10 tomorrow.", "Great, see you tomorrow then!")]):
            assert T.pay_asked(q) is False and K.handoff(q, None) == [] and T._topic_ours(a) == V_NONE, (q, a)
            hand, state, _conf, _rule, _by, _paid = _run3i([("клиент", x), ("мы", L_NEU[lang])], q, a, "none")
            hit["обмен после вопроса"] += G_PLAIN in hand and state[0] == V_PREV_NAMED
            assert G_PLAIN not in _run3i([("клиент", x), ("мы", L_NEU[lang])], q, a, "backed")[0], (x, q)
    for m in M_DEP_COST:
        lang = _lang3l(m)
        assert _new3m(m) == ["dep"] and not _old_sign3l(m) and not _signs3l(m), m
        for q, a in (L_EXCH if lang == "ru" else [("Is a helmet included?", "Yes, a helmet is included."), ("Ok, thanks.", "You're welcome!"),
                                                    ("I'll come at 10 tomorrow.", "Great, see you tomorrow then!")]):
            history = [("клиент", "What are the terms?" if lang == "en" else "Что по условиям?"), ("мы", m)]
            assert T._topic_theirs(history[0][1]) == V_NONE, history[0][1]
            hand, state, _conf, _rule, _by, _paid = _run3i(history, q, a, "none")
            hit["обмен после залога"] += G_PLAIN in hand and state[0] == V_OURS_NAMED
            assert G_PLAIN not in _run3i(history, q, a, "backed")[0], (m, q)
    assert hit == {"вопрос": 30, "обмен после вопроса": 27, "обмен после залога": 9}, hit
    # причина класса — только список причин: всё прочее в черновике то же, что без неё
    for row in (M_OWN[0], M_OWN[9]):
        history, tail, text = _own3m(row)
        out, _a, _s, _logs = _draft3g2(history, tail, text, "cash")
        orig = T.topic_reason
        T.topic_reason = lambda topic, facts: (T.PT_NONE, [])
        try:
            mute, _a2, _s2, _logs2 = _draft3g2(history, tail, text, "cash")
        finally:
            T.topic_reason = orig
        assert out["handoff"] == [G_PLAIN] and mute["handoff"] == [] and out["text"] == mute["text"] == text
        assert {k: v for k, v in out.items() if k != "handoff"} == {k: v for k, v in mute.items() if k != "handoff"}, sorted(out)


def test_p3m_adapter_path_to_card_and_request_unchanged():
    """Путь адаптера до карточки на признаках шага 3m: история → `build` (в ЗАПРОС модели признаки темы не идут) → исход
    темы признаком шага → причина кода «оплата» → поля карточки сотрудника (слова → категория → ярлык действия, строка
    «НУЖЕН ЧЕЛОВЕК», «Отправить» открыто с пометкой). Сверка не завершена и версия по пояснению — тот же путь. Причина
    модели об оплате отпадает как повтор; причины не о деньгах стоят за причиной класса."""
    import wa_agent_tg as TG
    label = TG.CARD_ACTIONS[K.MONEY_PAYMENT_UNCLEAR]
    for row, want in ((M_OWN[0], V_BACK_OURS_NAMED), (M_OWN[4], V_BACK_OURS_NAMED), (M_OWN[8], V_BACK_NAMED),
                      (M_OWN[9], V_BACK_NAMED), (M_OWN[10], V_BACK_NAMED)):       # сумма, залог; вопрос, залог, сумма клиента
        history, tail, text = _own3m(row)
        out, a, s, logs = _draft3g2(history, tail, text, "cash")
        hand = A.draft_out(out)[1]
        assert hand == [G_PLAIN] and K.word_categories(G_PLAIN) and TG.card_actions(hand) == [label], (row[1], hand)
        notes = TG.card_notes(hand, 1, True)
        assert TG.W_HAND in notes and "• " + label in notes and TG.W_SEND_HAND in notes, notes
        assert out["question"] == tail and not [u for u in s.seen if "НУЖЕН ЧЕЛОВЕК" in u or "тема оплаты" in u], row[1]
        assert [ln for ln in logs if ln == "правило класса: %s; причина кода добавлена" % want], logs
        out, a, s, _logs = _draft3g2(history, tail, text, "over")
        assert a.last["tools"]["state"] == T.OVER and out["handoff"] == [T.INCOMPLETE_WORDS, G_PLAIN], out["handoff"]
        out, a, _s, _logs = _draft3g2(history, tail, text, "cash", hint=("прежний черновик", "скажи короче"))
        assert a.last["info"].get("hint") is True and out["handoff"] == [G_PLAIN], out["handoff"]
    history, tail, text = _own3m(M_OWN[0])
    q = tail + " И есть ли свободный NMAX со скидкой?"
    out, _a, _s, _logs = _draft3g2(history, q, "Уточню у коллег и вернусь.", "cash")
    assert out["handoff"] == [G_PLAIN, K.REASON_WORDS[K.R_AVAILABILITY], K.REASON_WORDS[K.R_DISCOUNT]], out["handoff"]
    out, _a, _s, _logs = _draft3g2(history, tail, text, "cash", handoff=["клиент сообщает об оплате — проверьте поступление"])
    assert out["handoff"] == [G_PLAIN], out["handoff"]


def test_p3m_exhaustion_table_pinned_and_named_residual():
    """ТАБЛИЦА ИСЧЕРПАНИЯ, закреплённая исполнением, и ИМЕННОЙ ОСТАТОК — проверка ФИКСИРУЕТ нынешний исход и НЕ означает
    «закрыто». Для каждого определения / ярлыка денег в коде — одна фраза нашей стороны (`M_T_OURS`) и одна фраза клиента
    (`M_T_THEIRS`) с исходом `_topic_ours` / `_topic_theirs`. Открывают тему: у нас — слово оплаты, группа оплаты,
    утверждение, обещание проверки (`PT_OURS`); сумма в батах, способ, место, бумага (`PT_OURS_MONEY`); сумма в любой
    валюте, залог (`PT_OURS_NAMED`); у клиента — `pay_asked` (`PT_PREV`), «заявил / неясно» (`PT_PREV_SAID`), бумага
    (`PT_PREV_PROOF`), «вопрос об оплате», «депозит», сумма (`PT_PREV_NAMED`). НЕ открывают (остаток поимённо): число без
    валюты и код валюты перед числом; «USDT»; «аванс», «реквизиты», «взнос», «баланс», «proof», «долг»; ярлыки «возврат
    денег», «спор», «повреждения и штрафы»; обещание возврата, сдача; у БЛОКА КЛИЕНТА — ещё слово денег вне группы
    оплаты (`_PQ_PAYWORD`: «Деньги отдам курьеру.»), способ (`_PF_METHOD`: «Можно картой?») и место денег (`_PF_HELD`:
    «На какой счёт?») — у нашего ответа те же определения тему открывают. Остаток формы (а) на пути адаптера — «Итого
    230 USDT за 10 суток.»; остаток клиентской стороны — «Можно картой?» → «Да, можно.» → «Скинул.» → ответ вне форм:
    причины `[]` при обоих наборах фактов; краткий ответ на те же цепочки причину N4 несёт (правило В)."""
    for name, text, want in M_T_OURS:
        assert T._topic_ours(text) == want, (name, text, T._topic_ours(text))
    for name, text, want in M_T_THEIRS:
        assert T._topic_theirs(text) == want, (name, text, T._topic_theirs(text))
    assert len([r for r in M_T_OURS if r[2] == V_NONE]) == 14 and len([r for r in M_T_THEIRS if r[2] == V_NONE]) == 17
    seen = {"_PQ_PAYWORD": T._PQ_PAYWORD.search, "_PF_METHOD": T._PF_METHOD.search, "_PF_HELD": T._PF_HELD.search,
            "_PD_DEBT": re.compile(T._PD_DEBT, re.I).search, "_PM_BARE": re.compile(T._PM_BARE).search,
            "_PF_DEP": T._PF_DEP.search, "_PM_AMT": _amt3m, "_PQ_PROOF": T._PQ_PROOF.search,
            "_OTHER_MONEY": K._OTHER_MONEY.search, "_PAY_PROOF": K._PAY_PROOF.search, "_PAY_DONE": K._PAY_DONE.search}
    for name, text, _want in M_T_OURS + M_T_THEIRS:                 # определение, названное в строке, фразу ВИДИТ
        assert name not in seen or seen[name](text), (name, text)
    left = [("Where to?" if _en3l(m) else "Сколько с меня?", m, "Sent!" if _en3l(m) else "Скинул.",
             "Great, it's yours!" if _en3l(m) else "Отлично, бронь за вами!") for m in (M_D2_LEFT, "С вас 7790 за 10 суток.",
                                                                                         "That's USD 230 for ten days.")]
    left += [("Можно картой?", "Да, можно.", "Скинул.", "Отлично, бронь за вами!"),
             ("Деньги отдам курьеру.", "Хорошо, договорились.", "Скинул.", "Да, ждём вас завтра в 10."),
             ("На какой счёт?", "Сейчас пришлём.", "Скинул.", "Отлично, бронь за вами!")]
    for q, ours, tail, text in left:
        for facts in ("none", "cash"):
            hand, state, conf, rule, _by, _paid = _run3i([("клиент", q), ("мы", ours)], tail, text, facts)
            assert hand == [] and state[0] == V_NONE and not conf and not rule, (q, ours, facts, hand)     # ← остаток, не успех
        brief = "Thank you, received!" if _en3l(text) else "Спасибо, получили!"
        assert _run3i([("клиент", q), ("мы", ours)], tail, brief, "cash")[0] == [T.PAY_WORDS], (q, ours)


def test_p3m_dictionaries_not_extended():
    """Слов, списков и выражений не добавлено: выражения и строки-шаблоны определений шага (`_PF_DEP`, `_PM_AMT`), ярлыки
    общей причины (`K.MONEY_LABELS`) и слова причин (`K.MONEY_WORDS`) побайтно те же, что на d07b895 (отпечатки сняты с
    него); ВСЕ скомпилированные выражения модулей `wa_agent_tools` (71) и `wa_agent_knowledge` (22) и ВСЕ строки-шаблоны
    `_P*` / `_ASK*` модуля `wa_agent_tools` (33) — тоже (один отпечаток на модуль). `_PM_AMT` ищется как есть —
    нового скомпилированного выражения в модуле нет."""
    import hashlib

    def h(s):
        return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]

    def whole(mod):
        rows = sorted("%s=%s" % (n, v.pattern) for n, v in vars(mod).items() if hasattr(v, "pattern"))
        return len(rows), h("|".join(rows))
    strs = sorted("%s=%s" % (n, v) for n, v in vars(T).items() if isinstance(v, str) and (n.startswith("_P") or n.startswith("_ASK")))
    assert {n: h(getattr(T, n).pattern) for n in M_PRINTS_RX} == M_PRINTS_RX
    assert {n: h(getattr(T, n)) for n in M_PRINTS_STR} == M_PRINTS_STR
    assert {str(k): h(rx.pattern) for k, _w, rx in K.MONEY_LABELS} == M_PRINTS_LABELS
    assert {"T": whole(T), "K": whole(K), "T_str": (len(strs), h("|".join(strs))),
            "K_words": h("|".join("%s=%s" % (k, v) for k, v in sorted(K.MONEY_WORDS.items())))} == M_PRINTS_ALL


# ═══ D3 приёмки шага 3: проверки, которые убивают мутанты m3r и m3v ═══════════════════════════════════════════

class SelfContradicting(Registry):
    """Дверь противоречит сама себе: со сроком аренды — «не найден», без срока — тот же договор В сроке."""

    def __call__(self, **kw):
        out = super().__call__(**kw)
        if kw.get("date_from"):
            out = dict(out, outcome="none", pick=None, items=[])
        return out


def test_d3_m3r_door_contradicts_itself_unknown():
    """D3 (мутант m3r_contradiction_is_fact): в сроке «нет», без срока — договор В сроке → НЕИЗВЕСТНО (не FACT), договор
    и PDF не приняты, вложения нет."""
    reg = SelfContradicting([DOC1])
    out = run(Script({"tool": "contract", "args": {}}, {"tool": "contract_pdf", "args": {"file_id": "PDF-0001"}},
                     final("Ок")), reg)
    assert len(reg.calls) == 2 and reg.calls[0].get("date_from") == TERM[0] and "date_from" not in reg.calls[1], \
        reg.calls
    res = [r for r in out["results"] if r["tool"] == "contract"][0]
    assert res["outcome"] == T.UNKNOWN and "противоречат" in res["reason"], (res["outcome"], res["reason"])
    assert not [f for f in T.accepted(out["results"]) if f["kind"] in ("contract", "pdf")], T.accepted(out["results"])
    assert X.attach_of({"state": T.DONE, "results": out["results"]})[0] is None


def test_d3_m3v_underpaid_cash_no_change():
    """D3 (мутант m3v_underpaid_off): касса этой аренды записала МЕНЬШЕ итога (7000 из 7790), клиент назвал 8000 —
    сдачи кодом нет («оплачена на 7000 из 7790»), ни в расчёте, ни в блоке запроса модели."""
    res = [T.rental_result({"ok": True, "rows": [dict(ROW)]}, at=T0),
           T.cash_result(tx([tx_item(amount=7000, description="Nmax 90101 +7000 аренда K3-BK-001")]), at=T0)]
    ch = T.change_of(T.accepted(res), [8000])
    assert ch["state"] == T.CHANGE_NO and "оплачена на 7000 из 7790" in ch["why"], ch
    blk = T.change_block(res, [8000])
    assert "сдача НЕ посчитана" in blk and "→ сдача" not in blk, blk
    _refused([tx_item(amount=7000, description="Nmax 90101 +7000 аренда K3-BK-001")], C3_TEXT,
             "оплачена на 7000 из 7790")


# ═══ п.4 F2-честность ═════════════════════════════════════════════════════════════════════════════════════════

def test_p4_all_tools_carry_f2_fields():
    """F2_CONTRACT §1.1/§1.2: у КАЖДОГО ответа всех 7 инструментов — `source_version` = null с причиной «источник
    версии не отдаёт» и ключ `read_at`; мёртвое поле `version` пусто."""
    clk = Clock()
    node = {"name": "business_rules", "read": True, "text": "… 03.10.2026-1 …", "len": 18, "taken_at": T0 - 600,
            "why": ""}
    doors = {"history": lambda: [{"who": "клиент", "text": "привет", "ts": T0 - 5}], "rental": rental_door(age=1500),
             "cash": lambda **kw: tx([tx_item()]), "contract": Registry([DOC1]), "contract_pdf": pdf_door,
             "rules": lambda: node}
    results = []
    ctx = T.bind_ctx(NUMBER, doors, results, clk)
    for tool, args in (("history", {}), ("rental", {}), ("cash", {"booking_id": BK}), ("contract", {}),
                       ("contract_pdf", {"file_id": "PDF-0001"}), ("delivery", {}), ("rules", {})):
        results.append(T.call_tool(tool, args, doors, clk, ctx))
    for r in results:
        assert "source_version" in r and r["source_version"] is None, (r["tool"], r.get("source_version", "нет ключа"))
        assert r.get("source_version_basis") == SV_WORDS, (r["tool"], r.get("source_version_basis"))
        assert "read_at" in r and not r.get("version"), (r["tool"], r.get("version"))


def test_p4_version_never_from_signed_at_len_msgid_row():
    """Версия не выводится из `signed_at` договора, длины правил, msg_id или номера строки кассы, служебного
    `stand_meta` подделки: ни в `version`, ни в `source_version`, ни на карточке («версия: неизвестна»)."""
    rent = T.rental_result({"ok": True, "rows": [dict(ROW)]}, at=T0)
    con = T.contract_result(Registry([DOC1])(phone=NUMBER), at=T0, number=NUMBER, rental=rent)
    cash = T.cash_result(tx([tx_item()]), at=T0)
    rules = T.rules_result({"name": "business_rules", "read": True, "text": "x" * 856, "len": 856, "taken_at": T0},
                           at=T0)
    assert con["outcome"] == T.FACT and cash["outcome"] == T.FACT and rules["outcome"] == T.FACT
    bad = ["2026-10-05 10:12", "856 симв.", "-100311:501:m11", "11", "K3-cash-v1", "K3-registry-v1"]
    for r in (con, rules, cash, rent):                         # договор первым: на 996ee09 у него version = signed_at
        assert not r.get("version") and r.get("source_version", "нет ключа") is None, (r["tool"], r.get("version"))
        assert not [b for b in bad if b == str(r.get("version")) or b == str(r.get("source_version"))], r["tool"]
    card = X.opora_of({"state": T.DONE, "results": [dict(r, req="%s #%d" % (r["tool"], i))
                                                    for i, r in enumerate((rent, con, cash, rules))]})
    assert card.count("версия: неизвестна") == 4 and "версия: 2026" not in card and "K3-" not in card, card


def test_p4_rental_rules_time_is_snapshot_time():
    """У rental/rules время данных — время СНИМКА (25 и 10 мин назад), а не вызова: `read_at`, карточка
    «прочитано ЧЧ:ММ» снимка; `at` (начало нашего запроса) — отдельно."""
    a = adapter(Script(final("Ок")), book_age=1500.0)
    rent_raw = a._tool_doors(NUMBER, 5)["rental"]()
    assert rent_raw.get("_taken_at") == T0 - 1500.0, rent_raw.get("_taken_at")
    rent = T.rental_result(rent_raw, at=T0)
    rules = T.rules_result({"name": "business_rules", "read": True, "text": "правила", "len": 7,
                            "taken_at": T0 - 600}, at=T0)
    assert rent.get("read_at") == T0 - 1500.0 and rent["at"] == T0, (rent.get("read_at"), rent["at"])
    assert rules.get("read_at") == T0 - 600 and rules["at"] == T0, (rules.get("read_at"), rules["at"])
    card = X.opora_of({"state": T.DONE, "results": [dict(rent, req="r"), dict(rules, req="b")]})
    assert "прочитано %s" % A.hm_phuket(T0 - 1500) in card and "прочитано %s" % A.hm_phuket(T0 - 600) in card, card
    assert "прочитано %s" % A.hm_phuket(T0) not in card, card


def test_p4_snapshot_time_unknown_is_unknown():
    """Снимочная дверь не передала время снимка — «время чтения неизвестно», а не время вызова."""
    rent = T.rental_result({"ok": True, "rows": [dict(ROW)]}, at=T0)
    assert "read_at" in rent and rent["read_at"] is None, rent.get("read_at", "нет ключа")
    card = X.opora_of({"state": T.DONE, "results": [dict(rent, req="r")]})
    assert "время чтения неизвестно" in card and "прочитано %s" % A.hm_phuket(T0) not in card, card


def main():
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    bad = 0
    for name, fn in tests:
        try:
            fn()
            print("PASS", name)
        except Exception as e:                                       # noqa: BLE001
            bad += 1
            print("FAIL", name, "—", type(e).__name__, str(e)[:400])
    print("ИТОГ %d/%d" % (len(tests) - bad, len(tests)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
