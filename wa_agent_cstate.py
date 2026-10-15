# -*- coding: utf-8 -*-
"""Состояние дела договора для МОДЕЛИ — адаптер (CSTATE1510, вариант C; флаг службы WA_AGENT_CONTRACT_STATE).

ЧТО ЭТО. `ContractStateAdapter` — наследник `wa_agent_model.ModelAdapter`. Закреплённые блобы wa_agent*.py не тронуты:
`build()` = родительский `build()`, затем код читает факты договора клиента из базы агента (`read_facts`: sqlite URI
mode=ro, timeout 2 с, выборка только по ТОЧНОМУ номеру) и кладёт блок `wa_contract_state.render` в НАЧАЛО user через
«\n\n». Сверка Т4а (`_draft_tools` → `wa_agent_tools.run`) берёт user целиком в голову КАЖДОГО хода — блок видит
каждый ход модели; черновик без сверки — тоже. Действия — прежними инструментами (`contract`, `contract_pdf`); PDF
прикладывает и проверяет код (`wa_agent_attach`), как прежде. `build_followup` не переопределён: напоминание блока не
видит (остаток выпуска).

ВЫКЛЮЧАТЕЛЬ. `cstate_on = False` (служба: флаг запрошен, а карточка подписи не засчитана) — `build` отдаёт результат
родителя без изменений. Блока нет и тогда, когда по номеру нет ни одной записи и вопрос клиента не о договоре: user
побайтно равен родительскому. Сбой чтения или сборки блока — строка журнала, запрос прежний (черновик строится всегда).

ИСТОЧНИКИ (только чтение, только точный номер): `signed_cards` и `attach` (версия) · `drafts` и `pdf_parts` черновиков,
несущих эту версию (PDF клиенту) · `part_status` по wamid части PDF (ранг read > delivered > sent > failed) · `outbox`
kind='document', via='тема' после подписи или версия, решённая документом человека (`signed_cards` без черновика) —
документ человека · `signed_asks` (просьба) · `contract_expect` (ожидание подписи и проверки реестра). Срок аренды
версии — `attach.date_to` её черновика. Нет таблицы или база не прочитана — «неизвестно (…)», а не «нет». В журнал — только числа и
имена источников: ни текста клиента, ни номера, ни имён."""
import os
import sqlite3

import wa_agent as A
import wa_agent_attach as X
import wa_agent_model
import wa_contract_state as CS

READ_TIMEOUT = 2.0                                            # ожидание блокировки базы агента при чтении, с
SOURCES = ("version", "pdf", "wa", "human_doc", "ask", "expect")
SOURCE_WORDS = {"version": "версия", "pdf": "PDF клиенту", "wa": "статус WhatsApp", "human_doc": "документ человека",
                "ask": "просьба", "expect": "ожидание подписи"}
W_DB = "база агента не прочитана: %s"
W_NO_DB = "база агента не задана"
W_TABLES = "нет таблиц: %s"
_LIVE = (A.PENDING, A.SCHEDULED, A.CLAIMED)                    # текст черновика ещё не решён — PDF ждёт нажатия
_MID = (A.SENDING, A.UNSURE, X.P_CLAIMED)                      # часть PDF посреди двери или исход неизвестен


def _all_unknown(facts, why):
    for k in SOURCES:
        facts[k] = {"unknown": why}
    facts["unread"].append(why)
    return facts


class _Reader:
    """Чтение фактов одной базы по одному номеру: каждый источник — своё «есть / нет / неизвестно (почему)»."""

    def __init__(self, con, tables, number, now, facts):
        self.con, self.tables, self.number, self.now, self.facts = con, tables, number, now, facts

    def q(self, sql, args=()):
        return self.con.execute(sql, args).fetchall()

    def need(self, *names):
        """Каких таблиц нет → слова | None."""
        miss = [t for t in names if t not in self.tables]
        return W_TABLES % ", ".join(miss) if miss else None

    def part(self, key, fn, *args):
        """Источник key → факт; исключение — «неизвестно» с именем ошибки (не «нет»)."""
        try:
            self.facts[key] = fn(*args)
        except Exception as e:                                       # noqa: BLE001
            self.facts[key] = {"unknown": "источник «%s» не прочитан: %s" % (SOURCE_WORDS[key], type(e).__name__)}
        got = self.facts[key]
        if isinstance(got, dict) and "unknown" in got:
            self.facts["unread"].append("%s — %s" % (SOURCE_WORDS[key], got["unknown"]))
        return got

    def run(self):
        ver = self.part("version", self.version)
        if isinstance(ver, dict) and "unknown" in ver:
            # версия не прочитана — PDF, статус и документ человека читаются через неё: тоже «неизвестно», а не «нет»
            for k in ("pdf", "wa", "human_doc"):
                self.facts[k] = {"unknown": "версия не прочитана"}
        elif ver is not None:
            pdf = self.part("pdf", self.pdf, ver)
            if isinstance(pdf, dict) and "unknown" not in pdf and pdf.get("wamids"):
                self.part("wa", self.wa, pdf)
            self.part("human_doc", self.human_doc, ver)
        self.part("ask", self.ask)
        self.part("expect", self.expect)

    # ── источники ────────────────────────────────────────────────────────────────────────────────────────────────

    def version(self):
        """Последняя версия подписанного договора номера: карточки подписи (`signed_cards`) и строки сверки ответов с PDF
        (`attach` черновиков номера). Ключ «последней» — signed_at реестра, затем время записи. Источник: карточка
        подписи · сверка ответа · документ человека (строка `signed_cards` без черновика — версию решил документ, который
        человек отправил сам: из темы или с телефона, `wa_agent_attach._signed_human_doc`). Срок аренды версии (`attach`
        её черновика, конец `date_to`) — блок скажет, если он прошёл: прошлый договор — не договор нынешнего обращения."""
        miss = self.need("signed_cards", "attach", "drafts")
        if miss:
            return {"unknown": miss}
        rows = self.q("SELECT s.signed_at, s.doc_id, s.file_id, s.sha256, s.draft_id, s.ts, d.kind, a.date_to "
                      "FROM signed_cards s LEFT JOIN drafts d ON d.id=s.draft_id LEFT JOIN attach a ON "
                      "a.draft_id=s.draft_id WHERE s.number=?", (self.number,))
        rows += self.q("SELECT a.signed_at, a.doc_id, a.file_id, a.sha256, a.draft_id, a.ts, d.kind, a.date_to "
                       "FROM attach a JOIN drafts d ON d.id=a.draft_id WHERE d.number=? AND a.file_id IS NOT NULL AND "
                       "a.signed_at IS NOT NULL", (self.number,))
        if not rows:
            return None
        best = max(rows, key=lambda r: (str(r[0] or "").strip(), float(r[5] or 0)))
        src = "card" if best[6] == X.KIND_SIGNED else "answer" if best[4] is not None else "human"
        return {"signed_at": best[0], "doc": best[1], "file_id": best[2], "sha": best[3], "draft_id": best[4],
                "src": src, "date_to": best[7], "decided_at": best[5]}

    def pdf(self, ver):
        """PDF этой версии клиенту — по черновикам номера, несущим её файл: ушёл · исход неизвестен · ждёт нажатия · не
        ушёл. Кто отправил — только ролью (`AUTO_WHO` — автоотправка, иное — сотрудник)."""
        miss = self.need("attach", "drafts", "pdf_parts")
        if miss:
            return {"unknown": miss}
        rows = self.q("SELECT d.id, d.state, d.created_at, p.state, p.who, COALESCE(p.sending_at, p.at), p.wamid "
                      "FROM drafts d JOIN attach a ON a.draft_id=d.id LEFT JOIN pdf_parts p ON p.draft_id=d.id "
                      "WHERE d.number=? AND a.file_id=? ORDER BY d.id", (self.number, ver.get("file_id")))
        if not rows:
            return None
        ids = [r[0] for r in rows]
        wamids = sorted({r[6] for r in rows if r[6]})
        if "part_log" in self.tables:
            marks = ",".join("?" * len(ids))
            wamids = sorted(set(wamids) | {r[0] for r in self.q(
                "SELECT wamid FROM part_log WHERE part='pdf' AND wamid IS NOT NULL AND draft_id IN (%s)" % marks, ids)})
        sent = [r for r in rows if r[3] == A.SENT]
        if sent:
            r = max(sent, key=lambda x: float(x[5] or 0))
            return {"state": "sent", "at": r[5], "who": "auto" if r[4] == X.AUTO_WHO else "staff", "wamids": wamids}
        mid = [r for r in rows if r[3] in _MID]
        if mid:
            return {"state": "unknown", "at": mid[-1][5], "wamids": wamids}
        live = [r for r in rows if r[1] in _LIVE]
        if live:
            return {"state": "wait", "at": live[-1][2], "wamids": wamids}
        nots = [r for r in rows if r[3] == A.NOT_SENT]
        return {"state": "not_sent", "at": nots[-1][5] if nots else None, "wamids": wamids}

    def wa(self, pdf):
        """Статус провайдера части PDF по её ТОЧНЫМ wamid: лучший по рангу read > delivered > sent > failed. Статуса нет —
        «статуса нет»; часть старше STATUS_DAYS суток статусы не собирает — так и сказано."""
        miss = self.need("part_status")
        if miss:
            return {"unknown": miss}
        wamids = pdf["wamids"]
        rows = self.q("SELECT status, COALESCE(ts, seen) FROM part_status WHERE part='pdf' AND wamid IN (%s)"
                      % ",".join("?" * len(wamids)), wamids)
        known = [r for r in rows if r[0] in CS.STATUS_RANK]
        if known:
            st, at = max(known, key=lambda r: (CS.STATUS_RANK[r[0]], float(r[1] or 0)))
            return {"status": st, "at": at}
        at = pdf.get("at")
        old = isinstance(at, (int, float)) and self.now - float(at) > X.STATUS_DAYS * 86400
        return {"status": None, "at": at, "old": bool(old)}

    def human_doc(self, ver):
        """Документ, отправленный ЧЕЛОВЕКОМ после подписи: из темы — `outbox` kind='document', via='тема' (время строки);
        строки темы нет, а версию решил документ человека (`signed_cards` без черновика: с телефона — живое эхо, его
        видит только проход подписи) — время, когда код это отметил (`signed_cards.ts`). Иначе — нет."""
        miss = self.need("outbox")
        if miss:
            return {"unknown": miss}
        at = X.signed_epoch(ver.get("signed_at"), self.now)
        if at is None:
            return {"unknown": "время подписи не разобрано"}
        row = self.q("SELECT MAX(ts) FROM outbox WHERE number=? AND kind=? AND via=? AND ts>=?",
                     (self.number, "document", A.VIA_TOPIC, float(at)))
        if row and row[0][0] is not None:
            return {"at": row[0][0], "via": "topic"}
        if ver.get("src") == "human":
            return {"at": ver.get("decided_at"), "via": "noted"}
        return None

    def ask(self):
        """Последняя просьба клиента прислать СВОЙ договор (`signed_asks`): время, вид, исход — без текста клиента."""
        miss = self.need("signed_asks")
        if miss:
            return {"unknown": miss}
        row = self.q("SELECT ts, asked, kind FROM signed_asks WHERE number=? ORDER BY ts DESC, draft_id DESC LIMIT 1",
                     (self.number,))
        return {"at": row[0][0], "asked": row[0][1], "kind": row[0][2]} if row else None

    def expect(self):
        """Последнее ожидание подписи номера (`contract_expect`): открыто · закрыто карточкой / решённой версией ·
        истекло; проверка реестра — время и исход."""
        miss = self.need("contract_expect")
        if miss:
            return {"unknown": miss}
        row = self.q("SELECT opened_at, why, due_at, checked_at, outcome, state, closed_at, closed_by FROM "
                     "contract_expect WHERE number=? ORDER BY opened_at DESC LIMIT 1", (self.number,))
        if not row:
            return None
        opened, why, due, checked, outcome, state, closed, by = row[0]
        out = {"opened_at": opened, "why": why, "due_at": due, "checked_at": checked, "outcome": outcome,
               "state": state, "closed_at": closed, "closed_by": None, "card_wait": False}
        by = str(by or "")
        if by.startswith("card:"):
            out["closed_by"] = "card"
            did = by.split(":", 1)[1]
            got = self.q("SELECT state FROM drafts WHERE id=?", (int(did) if did.isdigit() else -1,))
            out["card_wait"] = bool(got) and got[0][0] in (A.PENDING, A.SCHEDULED)
        elif by:
            out["closed_by"] = by
        return out


def read_facts(path, number, now, timeout=READ_TIMEOUT):
    """База агента → факты договора номера (`wa_contract_state.render`). Только чтение (sqlite URI mode=ro, timeout),
    выборка только по ТОЧНОМУ номеру. База не задана, не открылась или заперта — каждый источник «неизвестно (почему)»."""
    facts = dict({k: None for k in SOURCES}, read_at=float(now), unread=[], records=0)
    if not path:
        return _all_unknown(facts, W_NO_DB)
    try:
        con = sqlite3.connect("file:%s?mode=ro" % os.path.abspath(path).replace("\\", "/"), uri=True, timeout=timeout)
    except Exception as e:                                           # noqa: BLE001
        return _all_unknown(facts, W_DB % type(e).__name__)
    try:
        try:
            tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        except Exception as e:                                       # noqa: BLE001
            return _all_unknown(facts, W_DB % type(e).__name__)
        _Reader(con, tables, str(number), float(now), facts).run()
    finally:
        con.close()
    facts["records"] = sum(1 for k in ("version", "pdf", "human_doc", "ask", "expect")
                           if isinstance(facts[k], dict) and "unknown" not in facts[k])
    return facts


class ContractStateAdapter(wa_agent_model.ModelAdapter):
    """Адаптер модели с блоком фактов договора клиента в начале запроса (CSTATE1510). cstate_on=False — `build`
    родителя без изменений."""

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.cstate_on = True                       # служба гасит, если карточка подписи не засчитана
        self.cstate_timeout = READ_TIMEOUT

    def build(self, number, upto_id, now=None, hint=None):
        system, user, info = super().build(number, upto_id, now=now, hint=hint)
        if not self.cstate_on:
            return system, user, info
        at = self._now(now)
        try:
            facts = read_facts(self.agent_db, number, at, self.cstate_timeout)
            facts["topic"] = CS.topic(info.get("question"))
            block = CS.render(facts, at)
        except Exception as e:                                       # noqa: BLE001
            info["cstate"] = {"lines": 0, "read_at": at, "unread": ["блок не собран: %s" % type(e).__name__]}
            self.log("договор клиента: блок не собран (%s) — запрос модели прежний" % type(e).__name__)
            return system, user, info
        lines = block.count("\n") + 1 if block else 0
        info["cstate"] = {"lines": lines, "read_at": at, "unread": list(facts.get("unread") or [])}
        if block:
            user = block + "\n\n" + user
            info["user_chars"] = len(user)
        self.log("договор клиента: %s%s" % (
            "блок %d строк, %d знаков (записей %d, вопрос о договоре: %s)" % (
                lines, len(block), facts.get("records") or 0, "да" if facts.get("topic") else "нет") if block
            else "блока нет — записей по номеру нет, вопрос не о договоре",
            " · не прочитано: %s" % "; ".join(facts["unread"])[:200] if facts.get("unread") else ""))
        return system, user, info
