#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ПРИЁМКА ВЫПУСКА CASEPDF1510 поверх прода f678739 (SIGNEDCARD1410 уже в проде). Чёрный ящик по СПЕЦИФИКАЦИИ,
написан независимо, БЕЗ реализации. Агент отдаёт клиенту СВОЙ актуальный подписанный договор по ЯВНОЙ просьбе,
переиспользуя готовое: привязку кодом (`T.bind_ctx` / `T.call_tool("contract")`), `AttachCore._code_pdf`, `attach_of`,
`_signed_held` / `_pdf_twin`, `_signed_insert`, нажатие `press` → `_deliver`, раздельные квитанции `part_log` / `pdf_parts`.

ГЛАВНЫЙ ПРИНЦИП (поправка владельца TB-OWNER-AGENT-BEHAVIOR-1510): ЧТО ответить клиенту, решает МОДЕЛЬ своим циклом и
инструментами; КОД проверяет привязку, полномочия, свежесть, дедуп и надёжно исполняет. Поэтому здесь детектор просьбы и
шаблон M4 — только ОГРАНИЧИТЕЛЬ первого узкого ТРАНСПОРТА (когда системе можно нажать «Отправить» самой), а не голова и
не приёмка интеллекта: случаи детектора — короткая проверка СМЫСЛА, не корпус и не перебор фраз; главное в приёмке —
поведение: смешанная просьба сохраняет полезный ответ модели (код лишь прикладывает к нему проверенный PDF), детектор
текст модели не меняет никогда, автоотправка — ровно узкий класс «своя подписанная версия по чистой просьбе».

ИНТЕРФЕЙС, КОТОРОГО В f678739 НЕТ, — УГАДАН ПО СПЕЦИФИКАЦИИ (назван прямо; расхождение имени — правка здесь, не в смысле):
  · модуль `contract_ask`: `verdict(text)` и `verdict_many(texts)` → "pure" | "mixed" | None;
  · `wa_agent_attach.AUTO_WHO` = "агент: автоотправка своего договора по просьбе";
  · `wa_agent_attach.OPORA_ASKED` = " · прочитал КОД: клиент просит договор, модель contract не звала";
  · `wa_agent_attach.AUTOSEND_DAY_MAX` = 10;
  · `AttachCore(..., autosend=True)` и атрибут ядра `autosend` (тем же именем, что параметр);
  · отметка «черновик рождён просьбой»: таблица `signed_asks(draft_id PK, number, asked, ts)` — либо колонка `drafts`
    с «ask» в имени (`asked_mark` ниже понимает обе формы);
  · строка журнала исхода: префикс «подпись: автоотправка черновика N — »;
  · строка старта службы: «автоотправка своего договора по просьбе (WA_AGENT_AUTOSEND_CONTRACT): вкл|выкл — …»;
  · счёт автоотправок — ключ с «авто» в `signed_counts()` ИЛИ слово «автоотправ» в `wa_agent_svc.summary`.
Замок импортов `wa_agent_attach` (tests/test_wa_signed_card.py::test_core_imports_untouched ходит `ast.walk` по ВСЕМУ
модулю — ленивый импорт внутри функции тоже ловится) допускает модуль `contract_ask` двумя формами: свой код на одном
`re` ЛИБО тонкая обёртка над чистыми функциями `wa_agent_attach` — страж ниже принимает обе и проверяет, что новых
импортов у `wa_agent_attach` нет.

СТЕНД — ЖИВЫЕ ФОРМАТЫ tests/test_wa_signed_card.py (импортом, без копии): World, Registry (форма
`bridge_client.contract_find`), Pdfs (`bridge_client.contract_pdf`), Book (снимок броней), настоящая дверь аренды
`ModelAdapter._tool_doors`, номер 79999966963 с неразрывными дефисами в контактах, реестр стр.34/35 ОТОЗВАН, стр.36
ПОДПИСАН 2026-10-14 19:04 с pdf_id, sha PDF36. Сети нет: мост, модель, Telegram, WhatsApp — подделки, базы временные.

ЖИВЫЕ ФАКТЫ: корпус входящих за 60 дней со словами договор/контракт/contract/agreement/pdf/подпис — 7 уникальных фраз,
ЯВНОЙ просьбы прислать договор — 0. Шесть дословных фраз корпуса — НЕГАТИВЫ детектора; все позитивы ниже — парафразы,
живьём НЕ встречались.

WA_AGENT_SRC=<каталог> подменяет модули (прогон мутантов)."""
import ast
import hashlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
if os.environ.get("WA_AGENT_SRC"):
    sys.path.insert(0, os.environ["WA_AGENT_SRC"])

import wa_agent as A  # noqa: E402
import wa_agent_attach as X  # noqa: E402
import wa_agent_model as M  # noqa: E402
import wa_agent_svc as S  # noqa: E402
import wa_agent_tools as T  # noqa: E402
import k3_pdf_fixture  # noqa: E402  (скелет PDF сверяется перед дверью — фикстура живого формата)
import test_wa_signed_card as W  # noqa: E402  (стенд живых форматов SIGNEDCARD1410)

try:
    import contract_ask as Q  # noqa: E402
    Q_ERR = None
except Exception as e:                                               # noqa: BLE001 — назовёт случай M1
    Q, Q_ERR = None, e

NUM, T_SIGN, PDF36, SHA36 = W.NUM, W.T_SIGN, W.PDF36, W.SHA36
RU_TEXT, EN_TEXT = W.RU_TEXT, W.EN_TEXT
KEY36 = {"phone": NUM, "date_from": "2026-10-14", "date_to": "2026-10-17"}   # ключ перечитывания реестра
MEDIA36 = (NUM, "document", "application/pdf", "contract_36.pdf", SHA36)

AUTO_WHO_WANT = "агент: автоотправка своего договора по просьбе"
OPORA_ASKED_WANT = " · прочитал КОД: клиент просит договор, модель contract не звала"
AUTO_LINE = "автоотправка своего договора по просьбе (WA_AGENT_AUTOSEND_CONTRACT): "

ASK_RU = "Пришлите, пожалуйста, мой договор"          # парафраз: живьём не встречался
ASK_EN = "Could you send my contract please?"          # парафраз: живьём не встречался
MIXED_RU = "Пришлите договор и во сколько доставка?"   # пример спецификации
MODEL_TEXT = "Доставим завтра к 10:00 к вашему отелю."
NO_CALL = {"state": "done", "results": []}             # сверка модели завершена, contract модель НЕ звала

# ── детектор: шесть живых фраз корпуса дословно (все — НЕ просьба) ─────────────────────────────────────────
LIVE_NEG = ["Мы же договорились",
            "А если допустим заключим контракт на год? Можно прям очень хорошую цену будет получить?)",
            "Подписал",
            "Какую сумму в рублях и куда перевести и будет ли договор?",
            "За 10 не договоримся?",
            "Тогда договорились"]
# по нескольку примеров на смысл; живьём НЕ встречались — проверка смысла, а не корпус
PURE = ["Пришлите, пожалуйста, мой договор", "Скиньте договор", "Отправьте договор, пожалуйста",
        "Дайте копию договора", "Можно копию договора?", "Где мой договор?",
        "Could you send my contract please?", "Can I get my rental agreement?", "Where is my agreement?",
        "Здравствуйте! Подписал. Пришлите, пожалуйста, договор 🙏",            # приветствие · подписал · эмодзи
        "Hi, signed. Could you send my contract please? Thanks!"]              # то же по-английски
MIXED = ["Пришлите договор и во сколько доставка?", "Скиньте договор. И можно продлить аренду на два дня?",
         "Could you send my contract? And what time is the delivery?"]
DOUBT = ["Пришлите договор и фото байка", "Пришлите договор, завтра уезжаю в аэропорт"]   # при сомнении — НЕ pure
NOT_ASK = ["Будет ли договор?", "Что в договоре про депозит?", "Договор подписан, получил, спасибо",
           "Подписал договор", "Договор получил, всё ок", "Не надо договор", "Отмените договор",
           "I don't need the contract"]


class World(W.World):
    """Стенд SIGNEDCARD1410 + флаг автоотправки ядра: autosend=None — аргумент не передаётся вовсе (умолчание ядра)."""

    def __init__(self, autosend=None, **kw):
        self.autosend = autosend
        W.World.__init__(self, **kw)

    def new_core(self):
        kw = dict(log=self.lines.append, clock=self.clock, attach=True, pdf_fetch=self.pdfs,
                  contract_find=self.registry, signed=self.signed, signed_lookback_h=self.lookback_h)
        if self.autosend is not None:
            kw["autosend"] = self.autosend
        return X.AttachCore(self.dbpath, self.qpath, self.model, self.tg, self.door, **kw)


def _q():
    assert Q is not None, "модуля contract_ask нет: %r" % (Q_ERR,)
    return Q


def _tables(w):
    return {r[0] for r in w.q("SELECT name FROM sqlite_master WHERE type='table'")}


def asked_mark(w, did):
    """Отметка «черновик рождён просьбой» → значение asked | None (интерфейс угадан: signed_asks или колонка drafts)."""
    if "signed_asks" in _tables(w):
        got = w.q("SELECT asked FROM signed_asks WHERE draft_id=?", (did,))
        return got[0][0] if got else None
    cols = [r[1] for r in w.q("PRAGMA table_info(drafts)") if "ask" in r[1].lower()]
    if cols:
        got = w.q("SELECT %s FROM drafts WHERE id=?" % cols[0], (did,))
        return got[0][0] if got else None
    return None


def auto_lines(w, did):
    return [ln for ln in w.lines if ln.startswith("подпись: автоотправка черновика %d — " % did)]


def receipts(w, did):
    return sorted(w.q("SELECT part, who, outcome FROM part_log WHERE draft_id=?", (did,)))


def clean_lines(w, *texts):
    """Журнал без текстов клиента и без его номера целиком (правило SIGNEDCARD1410)."""
    for ln in w.lines:
        assert NUM not in ln and not any(t in ln for t in texts), ln


def after_card(w, act):
    """Сразу после `_card_new` карточки подписи (до автоотправки) мир меняется: act()."""
    real = w.core._card_new

    def wrap(did, ver, now):
        out = real(did, ver, now)
        if w.core.draft_kind(did) == X.KIND_SIGNED:
            act()
        return out
    w.core._card_new = wrap


def one_card(w):
    sd = w.signed_drafts()
    assert len(sd) == 1, (sd, w.sign_lines()[-6:])
    return sd[0][0]


# ═══ M1 · детектор просьбы: проверка СМЫСЛА (транспортный ограничитель, не голова) ════════════════════════════

def test_m1_live_negatives_verbatim():
    """Шесть дословных фраз корпуса за 60 дней — ни одна не просьба прислать договор."""
    q = _q()
    assert len(set(LIVE_NEG)) == 6
    for t in LIVE_NEG:
        assert q.verdict(t) is None, t
        assert q.verdict_many([t]) is None, t
    assert q.verdict_many(LIVE_NEG) is None


def test_m1_pure_paraphrases():
    """Явная просьба СВОЙ договор прислать/дать/где он, вокруг — только нейтральное (живьём не встречались)."""
    q = _q()
    for t in PURE:
        assert q.verdict(t) == "pure", t


def test_m1_mixed_and_doubt_never_pure():
    """Просьба + другой вопрос/просьба → mixed; при сомнении — НЕ pure (pure разрешает автоотправку)."""
    q = _q()
    for t in MIXED:
        assert q.verdict(t) == "mixed", t
    for t in DOUBT:
        assert q.verdict(t) != "pure", t


def test_m1_not_an_ask():
    """«Договорились», вопросы о существовании и условиях, «подписан/получил», отказ и отмена — None."""
    q = _q()
    for t in NOT_ASK + [None, "", "   ", "👍", "ok"]:
        assert q.verdict(t) is None, t


def test_m1_many_unanswered_together():
    q = _q()
    cases = [(["Здравствуйте", "Пришлите, пожалуйста, мой договор", "🙏"], "pure"),
             (["Пришлите договор", "А во сколько доставка?"], "mixed"),
             (["Подписал", "👍", "ok"], None),
             (["Мы же договорились", "Тогда договорились"], None),
             (["Не надо договор"], None),
             ([], None)]
    for texts, want in cases:
        assert q.verdict_many(texts) == want, (texts, want)
    for t in PURE + MIXED + NOT_ASK + LIVE_NEG:
        assert q.verdict(t) in ("pure", "mixed", None), t


def test_m1_module_pure():
    """contract_ask — чистый: импорт `re` (или обёртка над чистыми функциями wa_agent_attach), ни файлов, ни сети."""
    q = _q()
    tree = ast.parse(open(q.__file__, encoding="utf-8").read())
    imps = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            imps |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            imps.add((n.module or "").split(".")[0])
    assert imps in ({"re"}, {"wa_agent_attach"}, {"re", "wa_agent_attach"}), imps
    bad = {"open", "exec", "eval", "__import__", "input", "os", "sys", "socket", "sqlite3", "subprocess", "urllib",
           "requests", "io", "pathlib", "shutil"}
    used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert not (used & bad), used & bad
    assert callable(q.verdict) and callable(q.verdict_many)


# ═══ M2 · просьба открывает СОБСТВЕННУЮ версию ═══════════════════════════════════════════════════════════════

def test_m2_pure_ask_card_marked_nothing_sent():
    """Чистая просьба → ОДНА карточка подписи (шаблон + PDF36); отметка «рождён просьбой» по ключу, без текста
    клиента; без флага автоотправки клиенту НИЧЕГО."""
    w = World()
    w.put(T_SIGN + 60, ASK_RU)
    w.tick(T_SIGN + 600)
    did = one_card(w)
    assert w.signed_drafts()[0][1:3] == (A.PENDING, RU_TEXT), w.signed_drafts()
    a = w.attach(did)
    assert a[:7] == ("PDF36", "contract_36.pdf", len(PDF36), SHA36, 36, "D36", "2026-10-14 19:04"), a
    assert w.versions() == [(NUM, "D36", "2026-10-14 19:04", "PDF36", SHA36, did)], w.versions()
    assert did in w.tg.cards and w.door.sends == [] and w.door.media == []
    assert asked_mark(w, did) == "pure", asked_mark(w, did)
    if "signed_asks" in _tables(w):                               # будущий читатель дела: номер + doc_id + версия
        dump = repr(w.q("SELECT * FROM signed_asks"))
        assert ASK_RU not in dump and "договор" not in dump, dump
        assert w.q("SELECT number FROM signed_asks WHERE draft_id=?", (did,)) == [(NUM,)]
        assert w.q("SELECT s.doc_id, s.signed_at, s.file_id, a.asked FROM signed_cards s JOIN signed_asks a ON "
                   "a.draft_id=s.draft_id") == [("D36", "2026-10-14 19:04", "PDF36", "pure")]
    clean_lines(w, ASK_RU)


def test_m2_watershed_bypassed_only_by_unanswered_ask():
    """Подписан раньше водораздела: событие без просьбы — карточки нет (как было); чистая просьба — карточка (с
    извинением по правилу 30 мин); смешанная — карточки подписи нет; УЖЕ отвеченная просьба водораздел не обходит."""
    start = T_SIGN + 7 * 3600
    w = World(start=start)
    w.put(start + 60, "Подписал договор")
    w.tick(start + 600)
    assert w.signed_drafts() == [] and any("раньше водораздела" in ln for ln in w.sign_lines()), w.sign_lines()
    w = World(start=start)
    w.put(start + 60, ASK_RU)
    w.tick(start + 600)
    did = one_card(w)
    assert w.signed_drafts()[0][2] == X.SIGNED_SORRY["ru"] + RU_TEXT, w.signed_drafts()
    assert w.attach(did)[3] == SHA36 and asked_mark(w, did) == "pure" and w.door.sends == []
    w = World(start=start)
    w.put(start + 60, MIXED_RU)
    w.tick(start + 600)
    assert w.signed_drafts() == [], w.signed_drafts()
    # просьба уже отвечена (ответ модели отправлен), потом «Спасибо» — неотвеченных просьб нет: водораздел в силе
    reg = W.Registry(W.live_rows()[:2])
    w = World(start=start, tools_out=NO_CALL, text="Договор пришлём, как только он будет готов.", registry=reg)
    w.put(start + 60, ASK_RU)
    w.tick(start + 600)
    assert w.q("SELECT id, state FROM drafts") == [(1, A.PENDING)] and w.signed_drafts() == []
    assert w.core.press(1, 1, A.ACT_SEND, "Даня", start + 650)["ok"]
    w.model.text = None
    reg.rows.append(W.live_rows()[2])
    w.put(start + 700, "Спасибо")
    w.tick(start + 700 + w.core.quiet + 60)
    assert w.signed_drafts() == [] and any("раньше водораздела" in ln for ln in w.sign_lines()), w.sign_lines()


def test_m2_memo_pause_bypassed_by_ask():
    """«Договора нет» подряд кладёт номер на паузу SIGNED_IDLE — но не номер с неотвеченной просьбой: подписали через
    несколько проходов — карточка следующим тактом. Тот же сценарий без просьбы ждёт паузу (как было)."""
    def run(text):
        reg = W.Registry(W.live_rows()[:2])
        w = World(registry=reg)
        w.put(T_SIGN + 60, text)
        t = T_SIGN + 600
        for k in range(4):
            w.tick(t + k * (X.SIGNED_EVERY + 1))
        n = len(reg.calls)
        reg.rows.append(W.live_rows()[2])
        w.tick(t + 4 * (X.SIGNED_EVERY + 1))
        return w, n
    w, n = run(ASK_RU)
    assert n >= 4 and asked_mark(w, one_card(w)) == "pure", (n, w.sign_lines())
    c, m = run("Подписал договор")
    assert m == X.SIGNED_EMPTY_FREE + 1 and c.signed_drafts() == [], (m, c.signed_drafts())


def test_m2_human_decided_version_not_reopened():
    """Версия, решённая человеком («Не нужно» или уже отправлена), просьбой не переоткрывается и сама не уходит."""
    w = World(autosend=True)
    did = W._card(w)                                               # событие без просьбы: карточка, автоотправки нет
    assert w.door.sends == [] and asked_mark(w, did) is None
    assert w.core.press(did, 1, A.ACT_DECLINE, "Даня", T_SIGN + 650)["ok"]
    w.put(T_SIGN + 700, ASK_RU)
    w.tick(T_SIGN + 700 + w.core.quiet + 60)
    w.tick(T_SIGN + 700 + w.core.quiet + 60 + X.SIGNED_EVERY + 1)
    assert [r[0] for r in w.signed_drafts()] == [did] and w.door.sends == [] and w.door.media == []
    w = World(autosend=True)
    did = W._card(w)
    assert w.core.press(did, 1, A.ACT_SEND, "Даня", T_SIGN + 650)["ok"]
    w.put(T_SIGN + 700, ASK_RU)
    w.tick(T_SIGN + 700 + w.core.quiet + 60)
    w.tick(T_SIGN + 700 + w.core.quiet + 60 + X.SIGNED_EVERY + 1)
    assert [r[0] for r in w.signed_drafts()] == [did], w.signed_drafts()
    assert w.door.sends == [(NUM, RU_TEXT)] and w.door.media == [MEDIA36], (w.door.sends, w.door.media)


def test_m2_twin_by_ask_no_card_named_in_journal():
    """Этот PDF уже ушёл ответом модели — просьба карточки не даёт (двойник); остаток «повтор по просьбе» назван в
    журнале словами; клиенту второй копии нет."""
    reg = W.Registry(W.live_rows()[:2])
    w = World(autosend=True, tools_out=W.model_pdf36(), text="Договор ниже", registry=reg)
    w.put(T_SIGN + 60)
    w.tick(T_SIGN + 300)
    assert w.q("SELECT id, state FROM drafts") == [(1, A.PENDING)] and w.attach(1)[3] == SHA36
    reg.rows.append(W.live_rows()[2])
    assert w.core.press(1, 1, A.ACT_SEND, "Даня", T_SIGN + 400)["ok"] and len(w.door.media) == 1
    w.model.text, w.model.tools_out = None, None
    w.put(T_SIGN + 450, ASK_RU)
    w.tick(T_SIGN + 450 + w.core.quiet + 60)
    assert w.signed_drafts() == [], w.signed_drafts()
    assert w.versions() == [(NUM, "D36", "2026-10-14 19:04", "PDF36", SHA36, 1)], w.versions()
    assert any("уже уходил черновиком 1" in ln for ln in w.sign_lines()), w.sign_lines()
    assert any("по просьбе" in ln for ln in w.lines), w.lines[-8:]
    assert len(w.door.sends) == 1 and len(w.door.media) == 1, (w.door.sends, w.door.media)
    clean_lines(w, ASK_RU)


# ═══ M3 · смешанная просьба: полезный ответ модели жив и несёт проверенный PDF ═══════════════════════════════

def test_m3_mixed_keeps_model_answer_with_checked_pdf():
    """Модель ответила по делу (доставка), contract не звала; клиент ещё и просит договор → ответ модели НЕ снят, текст
    дословно её, строка attach несёт PDF36, привязанный КОДОМ, с отметкой опоры OPORA_ASKED; карточки подписи нет;
    «Отправить» человека шлёт текст модели, затем PDF — две квитанции."""
    w = World(tools_out=NO_CALL, text=MODEL_TEXT)
    w.put(T_SIGN + 60, MIXED_RU)
    w.tick(T_SIGN + 600)
    assert w.q("SELECT id, state, text, kind FROM drafts ORDER BY id") == [(1, A.PENDING, MODEL_TEXT, None)]
    assert w.signed_drafts() == [] and w.door.sends == [] and w.door.media == []
    a = w.attach(1)
    assert a[:10] == ("PDF36", "contract_36.pdf", len(PDF36), SHA36, 36, "D36", "2026-10-14 19:04", NUM,
                      "2026-10-14", "2026-10-17"), a
    assert a[11] is None, a
    assert X.OPORA_ASKED == OPORA_ASKED_WANT and X.OPORA_ASKED in (a[10] or ""), a[10]
    assert w.core.card_pdf(1, 1).startswith("📄 «Отправить» шлёт ВТОРЫМ сообщением подписанный PDF договора")
    out = w.core.press(1, 1, A.ACT_SEND, "Даня", T_SIGN + 700)
    assert out["ok"] and out["words"] == "текст: ушёл · PDF: ушёл", out
    assert w.door.sends == [(NUM, MODEL_TEXT)] and w.door.media == [MEDIA36], (w.door.sends, w.door.media)
    assert w.registry.calls[-1] == KEY36, "реестр перечитан при нажатии"
    assert receipts(w, 1) == [("pdf", "Даня", A.SENT), ("text", "Даня", A.SENT)], receipts(w, 1)
    clean_lines(w, MIXED_RU)


def test_m3_detector_never_changes_model_text():
    """Один и тот же ответ модели при трёх смыслах входящего: текст черновика модели НЕ меняется ни разу; PDF кодом
    прикладывается ТОЛЬКО к смешанной просьбе; чистая просьба даёт карточку подписи, которая заменяет ждущий ответ."""
    for text, mixed in ((MIXED_RU, True), (ASK_RU, False), ("А во сколько доставка?", False)):
        w = World(tools_out=NO_CALL, text=MODEL_TEXT)
        w.put(T_SIGN + 60, text)
        w.tick(T_SIGN + 600)
        assert w.q("SELECT text, kind FROM drafts WHERE id=1") == [(MODEL_TEXT, None)], text
        a = w.attach(1)
        assert (a[0] == "PDF36") is mixed and (OPORA_ASKED_WANT in (a[10] or "")) is mixed, (text, a)
        if mixed:
            assert w.q("SELECT state FROM drafts WHERE id=1") == [(A.PENDING,)] and w.signed_drafts() == []
        else:
            assert str(a[11] or "").startswith("договор не сверялся"), (text, a)
        if text == ASK_RU:
            did = one_card(w)
            assert asked_mark(w, did) == "pure"
            st = w.q("SELECT state, reason FROM drafts WHERE id=1")[0]
            assert st == (A.SUPERSEDED, X.W_SIGNED_SUPERSEDED % did), st
        assert w.door.sends == [] and w.door.media == []


def test_m3_binding_failure_keeps_answer_text_only():
    """Привязка кодом не удалась (подписанного нет · реестр таймаут) — прежняя строка attach с причиной: ответ модели жив,
    «Отправить» шлёт только его текст, PDF не уходит, ничего не падает."""
    for setup in ("none_signed", "timeout"):
        reg = W.Registry(W.live_rows()[:2] if setup == "none_signed" else None)
        if setup == "timeout":
            reg.fail = T.last9(NUM)
        w = World(tools_out=NO_CALL, text=MODEL_TEXT, registry=reg)
        w.put(T_SIGN + 60, MIXED_RU)
        w.tick(T_SIGN + 600)
        assert w.q("SELECT id, state, text FROM drafts ORDER BY id") == [(1, A.PENDING, MODEL_TEXT)], setup
        a = w.attach(1)
        assert a is not None and a[0] is None and str(a[11] or "").strip(), (setup, a)
        out = w.core.press(1, 1, A.ACT_SEND, "Даня", T_SIGN + 700)
        assert out["ok"] and w.door.sends == [(NUM, MODEL_TEXT)] and w.door.media == [], (setup, out)


# ═══ M4 · узкий класс автоотправки: своя подписанная версия по ЧИСТОЙ просьбе ═══════════════════════════════

def test_m4_flag_off_zero_sends():
    for kw in ({}, {"autosend": False}):
        w = World(**kw)
        w.put(T_SIGN + 60, ASK_RU)
        w.tick(T_SIGN + 600)
        did = one_card(w)
        assert w.signed_drafts()[0][1] == A.PENDING and w.door.sends == [] and w.door.media == [], kw
        assert not auto_lines(w, did), w.lines[-6:]


def test_m4_on_pure_ask_sends_exactly_once():
    """Флаг вкл, чистая просьба → тем же тактом штатным нажатием (who=AUTO_WHO): шаблон, затем PDF36; две квитанции;
    реестр перечитан, PDF прочитан при нажатии ДО текста; исход — строкой журнала и в счёте; повтора нет."""
    w = World(autosend=True)
    w.put(T_SIGN + 60, ASK_RU)
    w.tick(T_SIGN + 600)
    did = one_card(w)
    assert X.AUTO_WHO == AUTO_WHO_WANT
    assert w.door.sends == [(NUM, RU_TEXT)] and w.door.media == [MEDIA36], (w.door.sends, w.door.media)
    assert w.q("SELECT state, decided_by FROM drafts WHERE id=?", (did,)) == [(A.SENT, X.AUTO_WHO)]
    assert receipts(w, did) == [("pdf", X.AUTO_WHO, A.SENT), ("text", X.AUTO_WHO, A.SENT)], receipts(w, did)
    assert w.q("SELECT state, wamid FROM pdf_parts WHERE draft_id=?", (did,)) == [(A.SENT, "wamid.P1")]
    assert len(w.registry.calls) >= 2 and w.registry.calls[-1] == KEY36, w.registry.calls
    assert w.pdfs.calls == ["PDF36", "PDF36"], w.pdfs.calls       # проход + нажатие (до текста), не больше
    assert did in w.tg.cards and asked_mark(w, did) == "pure" and auto_lines(w, did), w.lines[-6:]
    counts = w.core.signed_counts() or {}
    said = any("авто" in str(k) for k in counts)
    if not said:
        class TgStub:
            polls = {"ok": 0, "fail": 0, "conflict": 0}
        w.core.db.execute("CREATE TABLE IF NOT EXISTS tg_cards (x INTEGER)")
        w.core.db.execute("CREATE TABLE IF NOT EXISTS tg_react_out (outcome TEXT)")
        said = "автоотправ" in S.summary(w.core, TgStub(), {k: "выкл" for k in S.FLAGS}, {})
    assert said, counts
    clean_lines(w, ASK_RU)
    w.tick(T_SIGN + 600 + X.SIGNED_EVERY + 1)
    w.tick(T_SIGN + 600 + X.SIGNED_IDLE + 2 * X.SIGNED_EVERY)
    assert len(w.door.sends) == 1 and len(w.door.media) == 1, "второй автоотправки нет"
    w = World(autosend=True)
    w.put(T_SIGN + 60, ASK_EN)
    w.tick(T_SIGN + 600)
    assert w.door.sends == [(NUM, EN_TEXT)] and len(w.door.media) == 1, w.door.sends


def test_m4_never_mixed_event_or_model_answer():
    """Автоотправка НИКОГДА: смешанная просьба (ответ модели с PDF ждёт человека), карточка события без просьбы,
    чистая просьба, на которую уже есть ответ модели с этим PDF."""
    w = World(autosend=True, tools_out=NO_CALL, text=MODEL_TEXT)
    w.put(T_SIGN + 60, MIXED_RU)
    w.tick(T_SIGN + 600)
    assert w.q("SELECT state FROM drafts WHERE id=1") == [(A.PENDING,)] and w.attach(1)[0] == "PDF36"
    assert w.signed_drafts() == [] and w.door.sends == [] and w.door.media == []
    w = World(autosend=True)
    did = W._card(w)
    assert w.signed_drafts()[0][1] == A.PENDING and w.door.sends == [] and asked_mark(w, did) is None
    w = World(autosend=True, tools_out=W.model_pdf36(), text="Договор ниже")
    w.put(T_SIGN + 60, ASK_RU)
    w.tick(T_SIGN + 600)
    w.tick(T_SIGN + 600 + X.SIGNED_EVERY + 1)
    assert w.q("SELECT id, state FROM drafts") == [(1, A.PENDING)] and w.signed_drafts() == []
    assert w.door.sends == [] and w.door.media == []


def test_m4_gate_window_closed():
    """Окно 24 ч перепроверяется перед автоотправкой (`_signed_window`): закрылось после карточки → 0 отправок, карточка
    ждёт человека, исход назван."""
    w = World(autosend=True)
    real = w.core._signed_window

    def win(number, now):
        if w.core.db.execute("SELECT 1 FROM drafts WHERE number=? AND kind=?", (number, X.KIND_SIGNED)).fetchone():
            return False, "окно 24 ч закрыто или кончается"
        return real(number, now)
    w.core._signed_window = win
    w.put(T_SIGN + 60, ASK_RU)
    w.tick(T_SIGN + 600)
    did = one_card(w)
    assert w.signed_drafts()[0][1] == A.PENDING and w.door.sends == [] and w.door.media == []
    assert auto_lines(w, did), w.lines[-6:]


def test_m4_gate_pause_and_echo():
    """После карточки клиента поставили на паузу · человек ответил с телефона (эхо) → 0 отправок."""
    for what in ("pause", "echo"):
        w = World(autosend=True)
        if what == "pause":
            after_card(w, lambda: w.core.db.execute("UPDATE clients SET paused=1 WHERE number=?", (NUM,)))
        else:
            after_card(w, lambda: w.put(T_SIGN + 590, "Сейчас пришлю", kind="echo"))
        w.put(T_SIGN + 60, ASK_RU)
        w.tick(T_SIGN + 600)
        did = one_card(w)
        assert w.door.sends == [] and w.door.media == [], what
        assert auto_lines(w, did), (what, w.lines[-6:])


def test_m4_gate_revoked_before_send():
    """Договор отозван в реестре между карточкой и автоотправкой → штатное перечитывание: 0 отправок."""
    w = World(autosend=True)
    after_card(w, lambda: w.registry.revoke(36))
    w.put(T_SIGN + 60, ASK_RU)
    w.tick(T_SIGN + 600)
    did = one_card(w)
    assert w.door.sends == [] and w.door.media == []
    st = w.q("SELECT state FROM drafts WHERE id=?", (did,))[0][0]
    assert st in (A.STALE, A.PENDING), st
    assert auto_lines(w, did), w.lines[-6:]
    w.tick(T_SIGN + 600 + X.SIGNED_EVERY + 1)
    assert w.door.sends == [] and len(w.signed_drafts()) == 1, w.signed_drafts()


def test_m4_gate_pdf_swapped_no_auto_retry():
    """Файл подменили между карточкой и автоотправкой (другой sha256) → 0 отправок, карточка ждёт; молчаливого автоповтора
    нет и после починки файла — только «Отправить» человека."""
    w = World(autosend=True)
    after_card(w, lambda: w.pdfs.files.__setitem__("PDF36", (36, W.PDF37)))
    w.put(T_SIGN + 60, ASK_RU)
    w.tick(T_SIGN + 600)
    did = one_card(w)
    assert w.door.sends == [] and w.door.media == [] and auto_lines(w, did)
    assert w.q("SELECT state FROM drafts WHERE id=?", (did,)) == [(A.PENDING,)]
    w.tick(T_SIGN + 600 + X.SIGNED_EVERY + 1)
    w.pdfs.files["PDF36"] = (36, PDF36)
    w.tick(T_SIGN + 600 + 2 * (X.SIGNED_EVERY + 1))
    assert w.door.sends == [] and w.door.media == [], "автоповтора нет"
    out = w.core.press(did, 1, A.ACT_SEND, "Даня", T_SIGN + 900)
    assert out["ok"] and w.door.sends == [(NUM, RU_TEXT)] and w.door.media == [MEDIA36], out


def _crowd(n):
    nums, rows, books, files = [], [], [], {}
    for i in range(1, n + 1):
        bike = "PCX 160 PHUKET 71%02d" % i
        rows.append(W.reg_row(100 + i, "ПОДПИСАН", "2026-10-14 19:04", "P%d" % (100 + i), bike=bike,
                              phone="+7 999 000-00-%02d" % i))
        books.append(W.book_row(bike=bike, contacts="Клиент +7 999 000%s00%s%02d" % (W.NBH, W.NBH, i),
                                booking="B71%02d" % i))
        files["P%d" % (100 + i)] = (100 + i, k3_pdf_fixture.classic(b"signed contract row %d" % (100 + i)))
        nums.append("799900000%02d" % i)
    w = World(autosend=True, rows=rows, book=books)
    w.pdfs.files.update(files)
    for num in nums:
        w.put(T_SIGN + 60, ASK_RU, number=num)
    return w, nums


def test_m4_day_ceiling():
    """Суточный потолок службы AUTOSEND_DAY_MAX=10: одиннадцатый клиент получает карточку, но не автоотправку."""
    assert X.AUTOSEND_DAY_MAX == 10
    w, nums = _crowd(11)
    w.tick(T_SIGN + 600)
    w.tick(T_SIGN + 600 + X.SIGNED_EVERY + 1)
    assert len(w.door.sends) == X.AUTOSEND_DAY_MAX, [n for n, _ in w.door.sends]
    assert sorted(n for n, _ in w.door.sends) == nums[:10] and len(w.door.media) == 10
    last = w.q("SELECT id, state FROM drafts WHERE number=? AND kind=?", (nums[10], X.KIND_SIGNED))
    assert len(last) == 1 and last[0][1] == A.PENDING, last
    assert auto_lines(w, last[0][0]), w.lines[-8:]


def test_m4_one_attempt_per_version():
    """Автоотправка на версию — одна: первая попытка не прошла (WhatsApp не принял текст), клиент просит снова —
    вторую версия сама не делает (дальше — человек)."""
    w = World(autosend=True)
    w.door.text_out = "not_sent"
    w.put(T_SIGN + 60, ASK_RU)
    w.tick(T_SIGN + 600)
    did = one_card(w)
    assert len(w.door.sends) == 1 and w.door.media == [] and auto_lines(w, did), (w.door.sends, w.lines[-6:])
    w.door.text_out = "sent"
    w.put(T_SIGN + 900, ASK_RU)
    t = T_SIGN + 900 + w.core.quiet + 60
    w.tick(t)
    w.tick(t + X.SIGNED_EVERY + 1)
    assert len(w.door.sends) == 1 and w.door.media == [], (w.door.sends, w.door.media)


def _svc_world(environ):
    import test_wa_attach_svc as AS

    class Model(AS.Model):
        def _tool_doors(self, number, upto_id):
            return {"rental": lambda: {"ok": True, "rows": []}, "history": lambda: []}
    env = dict(AS.ON, **environ)
    w = AS.World(env)
    w.model = Model()
    w.lines[:] = []
    w.build(env)
    return w


def test_m4_svc_flag_and_start_line():
    """Флаг службы WA_AGENT_AUTOSEND_CONTRACT: правило flag_on, по умолчанию ВЫКЛ, засчитывается только при засчитанном
    WA_AGENT_SIGNED_CARD; строка старта «…: вкл|выкл — …»; ядру — autosend."""
    for raw in ("1", "yes", "on"):
        w = _svc_world({"WA_AGENT_SIGNED_CARD": "1", "WA_AGENT_AUTOSEND_CONTRACT": raw})
        said = [ln for ln in w.lines if ln.startswith(AUTO_LINE)]
        assert said and said[0].startswith(AUTO_LINE + "вкл — "), (raw, w.lines)
        assert w.core.signed and getattr(w.core, "autosend", None) is True, raw
    w = _svc_world({"WA_AGENT_AUTOSEND_CONTRACT": "1"})              # карточка подписи не засчитана
    said = [ln for ln in w.lines if ln.startswith(AUTO_LINE)]
    assert said and said[0].startswith(AUTO_LINE + "выкл — "), w.lines
    assert not getattr(w.core, "autosend", False)
    for env in ({"WA_AGENT_SIGNED_CARD": "1"}, {"WA_AGENT_SIGNED_CARD": "1", "WA_AGENT_AUTOSEND_CONTRACT": "0"}):
        w = _svc_world(env)
        assert not [ln for ln in w.lines if ln.startswith(AUTO_LINE + "вкл")], (env, w.lines)
        assert w.core.signed and not getattr(w.core, "autosend", False), env


# ═══ совместимость: флаги выкл — прежнее байт-в-байт ═════════════════════════════════════════════════════════

def test_compat_signed_off_nothing_new():
    """WA_AGENT_SIGNED_CARD выкл (autosend=True ядру не помогает): просьба и смешанная — прежний путь: ни дверей
    реестра/PDF/аренды, ни таблиц выпуска, ответ модели «договор не сверялся», клиенту ничего."""
    for text in (ASK_RU, MIXED_RU):
        w = World(signed=False, autosend=True, tools_out=NO_CALL, text=MODEL_TEXT)
        w.put(T_SIGN + 60, text)
        w.tick(T_SIGN + 600)
        assert w.q("SELECT id, state, text, kind FROM drafts") == [(1, A.PENDING, MODEL_TEXT, None)], text
        a = w.attach(1)
        assert a[0] is None and str(a[11] or "").startswith("договор не сверялся"), a
        assert OPORA_ASKED_WANT not in (a[10] or "")
        assert w.registry.calls == [] and w.pdfs.calls == [] and w.rental_calls == [], text
        tabs = _tables(w)
        assert "signed_cards" not in tabs and "signed_asks" not in tabs, tabs
        assert w.door.sends == [] and w.door.media == []


def test_compat_event_card_same_with_autosend_flag():
    """Карточка события без просьбы: с флагом автоотправки ядра и без — те же черновики, вложения, версии, двери; нажатие
    человека — тот же исход."""
    def snap(w):
        return (w.q("SELECT id, state, text, upto_id, kind, decided_by, question, q_lang FROM drafts ORDER BY id"),
                w.q("SELECT draft_id, file_id, name, size, sha256, row, doc_id, signed_at, number, date_from, date_to, "
                    "opora, reason FROM attach ORDER BY draft_id"),
                w.versions(), list(w.door.sends), list(w.door.media), list(w.tg.cards), list(w.registry.calls),
                list(w.pdfs.calls))
    a, b = World(), World(autosend=True)
    da, db = W._card(a), W._card(b)
    assert da == db and snap(a) == snap(b), (snap(a), snap(b))
    assert asked_mark(b, db) is None
    for w, did in ((a, da), (b, db)):
        assert w.core.press(did, 1, A.ACT_SEND, "Даня", T_SIGN + 700)["ok"]
    assert snap(a) == snap(b) and a.door.sends == [(NUM, RU_TEXT)], (snap(a), snap(b))


FROZEN = {"wa_agent.py": "70695c7dc669f2b4d14ff7c000763b915e6121e8",          # git-блобы f678739 (`git rev-parse`)
          "wa_agent_tools.py": "2115dfd59818c24fef39bf61a870364357bcd20a",  # DELIVERY2210: было fb70716d
          "wa_agent_model.py": "38ec261976b7e912e25a14129b68c1df05445e45"}  # RCFIX2010: было 868b0c4b (free_bikes с парком снимка) · PROMPT2110: было 7c58cca9 · WAFIX2210: было b95d3a86 · DELIVERY2210: было 29fcf235


def _blob(path):
    data = open(path, "rb").read().replace(b"\r\n", b"\n")
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def test_compat_imports_and_frozen_blobs():
    """Импорты wa_agent_attach прежние (тот же замок, что test_wa_signed_card), wa_agent / wa_agent_tools /
    wa_agent_model не тронуты (блобы f678739): состояние дела модели этим выпуском НЕ передаётся."""
    tree = ast.parse(open(X.__file__, encoding="utf-8").read())
    names = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))
             for a in (n.names if isinstance(n, ast.Import) else [ast.alias(n.module or "")])}
    assert names == {"base64", "hashlib", "re", "zlib", "wa_agent", "wa_agent_tools"}, names
    for mod in (A, T, M):
        name = os.path.basename(mod.__file__)
        assert _blob(mod.__file__) == FROZEN[name], name


def main():
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    bad = 0
    for name, fn in tests:
        try:
            fn()
            print("PASS", name)
        except Exception as e:                                       # noqa: BLE001
            bad += 1
            print("FAIL", name, "—", type(e).__name__, str(e)[:300])
    print("ИТОГ %d/%d" % (len(tests) - bad, len(tests)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
