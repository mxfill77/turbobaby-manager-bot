"""A2CONSENT2210 (К3 22.10, Codex TB-A2-WIRING-2210-0742 п.1): producer согласия клиента для wa_intake_card. OFF-код:
вызовов из службы нет, флаг WA_AGENT_INTAKE_CARD прежний.

Смысл решает МОДЕЛЬ (структурный ответ accept/decline/question/ambiguous со ссылками), КОД сверяет привязки:
  - предложение — РЕАЛЬНО отправленное сообщение с WA-id (журнал отправленных OFFER), не черновик;
  - отпечаток условий решения = отпечатку отправленного OFFER (модель, период, точная сумма/валюта, доставка/предоплата);
  - источник — входящее сообщение клиента ЭТОГО дела после отправки предложения;
  - reviewed_upto = последнее входящее клиента; версия дела — текущая.
Любое несовпадение превращает accept в ambiguous с причиной; question/decline/ambiguous никогда не становятся accept.
Только stdlib; сети, окружения и файлов (кроме явно переданного пути журнала) модуль не трогает.
"""
import hashlib
import json
import os
import tempfile
import threading

DECISIONS = ("accept", "decline", "question", "ambiguous")
DECIDED_BY = "model+code"


def terms_fingerprint(fact, delivery=None, prepay=None):
    """Неизменяемый отпечаток условий OFFER: модель, период, точная сумма и валюта, доставка, предоплата.
    fact — OFFER-факт формы wa_offer_tool (`model`, `date_start`, `date_end`, `total`, `currency`)."""
    f = fact or {}
    parts = [f.get("model"), f.get("date_start"), f.get("date_end"), f.get("total"), f.get("currency"),
             (delivery or {}).get("zone") if isinstance(delivery, dict) else delivery,
             (delivery or {}).get("price") if isinstance(delivery, dict) else None, prepay]
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:24]


class SentOfferJournal(object):
    """Журнал ОТПРАВЛЕННЫХ предложений по делу: запись только после достоверной отправки (есть WA-id). Один JSON-файл,
    запись temp + os.replace; процесс один. Хранит id/ключи/суммы — без текста переписки и контактов."""

    def __init__(self, path):
        self.path, self._lk = path, threading.Lock()

    def _load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return None                        # файла ещё нет — записей нет; битый JSON — исключение

    def _save(self, d):
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(self.path)), suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)

    def record(self, case_key, offer_key, fingerprint, total, currency, wa_msg_id, sent_at):
        """→ True записано | None отказ (нет WA-id / ключа дела / отпечатка). Повтор того же wa_msg_id — без второй записи."""
        if not case_key or wa_msg_id in (None, "") or not fingerprint:
            return None
        with self._lk:
            d = dict(self._load() or {})
            rows = list(d.get(case_key) or [])
            if any(r.get("offer_msg_id") == wa_msg_id for r in rows):
                return True
            rows.append({"offer_msg_id": wa_msg_id, "offer_key": offer_key, "fingerprint": fingerprint,
                         "total": total, "currency": currency, "sent_at": sent_at})
            d[case_key] = rows
            self._save(d)
            return True

    def of_case(self, case_key):
        with self._lk:
            return list((self._load() or {}).get(case_key) or [])


def _ambiguous(base, why):
    out = dict(base, decision="ambiguous")
    out["reasons"] = list(base.get("reasons") or []) + [why]
    return out


def consent_from_decision(decision, case, sent_offers, messages):
    """Решение модели + факты → consent для wa_intake_card.prepare (поля case_key, offer_key, decision, source_msg_id,
    offer_msg_id, agreed_total, decided_by, reviewed_upto, case_version, reasons).

    decision      {"decision", "source_msg_id", "offer_msg_id", "terms_fp", "reviewed_upto", "case_key", "case_version"}
    case          {"case_key", "case_version"} — текущее дело
    sent_offers   SentOfferJournal.of_case(case_key)
    messages      [{"id", "who": "клиент"|"мы", "ts"}] — сообщения дела с уже сопоставленными id"""
    dc = decision if isinstance(decision, dict) else {}
    ck, cv = (case or {}).get("case_key"), (case or {}).get("case_version")
    base = {"case_key": ck, "offer_key": None, "decision": dc.get("decision"), "source_msg_id": dc.get("source_msg_id"),
            "offer_msg_id": dc.get("offer_msg_id"), "agreed_total": None, "decided_by": DECIDED_BY,
            "reviewed_upto": dc.get("reviewed_upto"), "case_version": dc.get("case_version"), "reasons": []}
    if dc.get("decision") not in DECISIONS:
        return _ambiguous(base, "решение модели вне словаря")
    if dc.get("decision") != "accept":
        return base
    if not ck or dc.get("case_key") != ck:
        return _ambiguous(base, "решение по другому делу")
    if cv is None or dc.get("case_version") != cv:
        return _ambiguous(base, "решение по другой версии дела")
    offer = next((o for o in (sent_offers or ()) if o.get("offer_msg_id") == dc.get("offer_msg_id")), None)
    if offer is None:
        return _ambiguous(base, "предложение не найдено среди отправленных")
    base.update(offer_key=offer.get("offer_key"), agreed_total=offer.get("total"))
    if dc.get("terms_fp") != offer.get("fingerprint"):
        return _ambiguous(base, "условия решения не совпадают с отправленным предложением")
    latest = max((o for o in sent_offers if isinstance(o.get("sent_at"), (int, float))),
                 key=lambda o: o["sent_at"], default=None)
    if latest is None or latest.get("offer_msg_id") != offer.get("offer_msg_id"):
        return _ambiguous(base, "согласие не на последнее отправленное предложение")
    by_id = {m.get("id"): m for m in (messages or ()) if isinstance(m, dict) and m.get("id") is not None}
    src = by_id.get(dc.get("source_msg_id"))
    if src is None or src.get("who") != "клиент" or not isinstance(src.get("ts"), (int, float)):
        return _ambiguous(base, "источник — не входящее сообщение клиента этого дела")
    if not isinstance(offer.get("sent_at"), (int, float)) or not offer["sent_at"] < src["ts"]:
        return _ambiguous(base, "согласие не после отправки предложения")
    ins = [m for m in by_id.values() if m.get("who") == "клиент"]
    if not all(isinstance(m.get("ts"), (int, float)) for m in ins):
        return _ambiguous(base, "порядок входящих неизвестен")
    if dc.get("reviewed_upto") != max(ins, key=lambda m: m["ts"]).get("id"):
        return _ambiguous(base, "разбор не покрывает последний вход клиента")
    return base
