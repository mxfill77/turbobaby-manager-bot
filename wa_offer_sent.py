"""OFFERSENT2210 (К3 22.10, Codex TB-A2-WIRING-2210-0742 п.1 и TB-AGENT-CRITERIA-2210-OWNER-REVIEW): журнал
ОТПРАВЛЕННЫХ предложений из живого ядра. Ручка WA_AGENT_OFFER_SENT (по умолчанию ВЫКЛ: регистратор не создаётся, ядро
байт-в-байт прежнее).

Два шага, оба вызывает ядро (`wa_agent.Core`), сам модуль сети и модели не трогает:
  on_draft(draft_id, number, last, now) — у только что записанного черновика запоминает ФАКТЫ offer (FACT «свободно» с
      точной ценой) этой сверки: черновик ≠ отправка, в журнал ничего не идёт;
  on_sent(draft_id, wamid, text, now) — черновик реально ушёл (есть WA-id): каждый запомненный OFFER, сумма которого
      названа в УШЕДШЕМ тексте (сотрудник мог править), пишется в wa_consent.SentOfferJournal с этим wamid.
Ключ дела — номер + модель + период: один номер не склеивает две разные аренды.
"""
import json
import os
import tempfile
import threading

import wa_consent
import wa_intake_card

F_OFFER_SENT = "WA_AGENT_OFFER_SENT"
PENDING_MAX = 500


def case_key(number, fact):
    """Ключ дела предложения: номер + модель + период (не один телефон)."""
    return "wa:%s:%s:%s:%s" % (number, fact.get("model"), fact.get("date_start"), fact.get("date_end"))


def offer_facts(last):
    """last модели после хода → [OFFER-факт] «свободно» с точной суммой в THB (то, что можно назвать ценой)."""
    tools = (last or {}).get("tools") if isinstance(last, dict) else None
    out = []
    for r in ((tools or {}).get("offers") or ()) if isinstance(tools, dict) else ():
        if not isinstance(r, dict) or r.get("outcome") != "fact":
            continue
        for f in r.get("facts") or ():
            if (isinstance(f, dict) and f.get("kind") == "offer" and f.get("avail") == "free"
                    and isinstance(f.get("total"), (int, float)) and f.get("currency") == "THB"):
                out.append(f)
    return out


class OfferSentRecorder(object):
    """Ожидание «черновик → отправка» — свой JSON-файл (temp + os.replace), журнал отправленных — SentOfferJournal."""

    def __init__(self, pending_path, journal):
        self.path, self.journal, self._lk = pending_path, journal, threading.Lock()

    def _load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return None                        # файла ещё нет — ожиданий нет; битый JSON — исключение

    def _save(self, d):
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(self.path)), suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)

    def on_draft(self, draft_id, number, last, now):
        keep = [{"case_key": case_key(number, f), "offer_key": wa_intake_card.offer_key(f),
                 "fingerprint": wa_consent.terms_fingerprint(f), "total": f["total"], "currency": f["currency"]}
                for f in offer_facts(last)]
        if keep:                               # без фактов offer ожидание не пишется (файл не трогается)
            with self._lk:
                d = dict(self._load() or {})
                d[str(draft_id)] = {"at": now, "offers": keep}
                for k in sorted(d, key=lambda k: d[k].get("at") or 0)[:-PENDING_MAX]:
                    d.pop(k, None)             # потолок ожиданий: старейшие уходят, журнал отправленных не трогается
                self._save(d)
        return len(keep)

    def on_sent(self, draft_id, wamid, text, now):
        """→ число записанных отправленных предложений. Нет WA-id / нет ожидания — 0, ничего не пишется."""
        if wamid in (None, ""):
            return 0
        with self._lk:
            d = dict(self._load() or {})
            rec = d.pop(str(draft_id), None)
            if rec is not None:
                self._save(d)
        n = 0
        for o in (rec or {}).get("offers") or ():
            if wa_intake_card._digits_have(text, o["total"]) and self.journal.record(
                    o["case_key"], o["offer_key"], o["fingerprint"], o["total"], o["currency"], wamid, now):
                n += 1
        return n
