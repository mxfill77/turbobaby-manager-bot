"""КОНТРАКТ ЧИТАТЕЛЯ ЖИВОГО ТЕКСТА — одно место на весь репозиторий (08.08.2026).

КЛАСС, который он закрывает — «нуль по неразбору» (перепись
`docs/artifacts/2026-08-08-zero-on-parse-miss-census.md`, 469 веток, слепых ≈368):
у читателя живого текста тип возврата НЕ ИМЕЕТ ТРЕТЬЕГО СОСТОЯНИЯ, поэтому «не смог разобрать» и
«нечего разбирать» приходят наверх ОДИНАКОВЫМ нулём. Снаружи молчание источника и слепота читателя
выглядят одинаково. Чинится не разбор (шаблон всегда вправе разойтись с живым текстом) — чинится
КОНТРАКТ: наверх идёт ПАРА «сколько осмотрено — сколько разобрано» и ИСХОД.

ПРАВИЛО ОДНОЙ СТРОКОЙ (§6 переписи):
    Нуль без знаменателя не отдаётся.

ИСХОДЫ — четыре, и каждый произносится ВСЛУХ:
    ok          осмотрено > 0, разобрано > 0        числу можно верить
    empty       осмотрено 0                          нуль честный, но знаменатель тоже 0
    mismatch    осмотрено > 0, разобрано 0           ТРЕТИЙ ИСХОД, ради которого всё:
                                                     «шаблон разошёлся с источником»
    unreadable  осмотрено НЕИЗВЕСТНО                 источник не прочитан

ПОЧЕМУ «осмотрено» БЫВАЕТ None, А НЕ 0. Ноль — это ИЗМЕРЕНИЕ («посмотрели, там пусто»), а
недоступный источник — ОТСУТСТВИЕ измерения. Записать второе нулём значит повторить ровно ту
ошибку, ради которой заведён модуль. Поэтому `scanned=None` — отдельное состояние, а не число.

ПОЧЕМУ ИСХОДОВ ЧЕТЫРЕ, А ТРЕТЬИМ НАЗВАН ОДИН. `unreadable` в этом репозитории кое-где уже отличают
честно (образцы §5 переписи: `_queue_items`, `_git_tracked_top_level`, `check_fleet_oil_gear`), а
`mismatch` не отличает НИКТО — он и есть новая клетка. Оба живут в одном перечислении, потому что
у вызывающего вопрос ОДИН: «этому числу можно верить?».

ГРАНИЦА УСТРОЙСТВОМ: у модуля НОЛЬ импортов. Ему нечем ни читать, ни писать, ни ходить в сеть, ни
звать подпроцесс — он только считает исход по двум числам и выдаёт фразу. Проверяется разбором
(ast) в `tests/test_scan_contract.py`, а не докстрингом.

FAIL-CLOSED В СТОРОНУ ГРОМКОГО: любая противоречивая пара («разобрано больше осмотренного»,
«источник не прочитан, но что-то разобрано», нецелые/отрицательные числа) даёт НЕ `ok`, а громкий
исход — сомнение в самих счётчиках есть повод сказать вслух, а не промолчать.

КАК ПОЛЬЗОВАТЬСЯ (переведённый образец — `splinter._o3_overdue_scan`):
    источник не прочитан      → ScanResult.unreadable("байков", detail="fleet() упал: …")
    прочитан                  → ScanResult(scanned=len(rows), parsed=n, subject="байков",
                                           payload=overdue)
    у вызывающего             → `if not res.ok: сказать res.say()` и ТОЛЬКО потом `res.payload`.
    payload читать до проверки исхода нельзя: у `unreadable`/`mismatch` он пуст не потому, что
    находок нет, а потому, что их НЕ ИСКАЛИ.
"""

# Ключи исхода (машинные). Человеческая фраза — в `_PHRASE` и `say()`.
OUTCOME_OK = "ok"
OUTCOME_EMPTY = "empty"
OUTCOME_MISMATCH = "mismatch"
OUTCOME_UNREADABLE = "unreadable"

# Порядок = порядок громкости: сначала то, что требует голоса.
OUTCOMES = (OUTCOME_UNREADABLE, OUTCOME_MISMATCH, OUTCOME_EMPTY, OUTCOME_OK)

_PHRASE = {
    OUTCOME_UNREADABLE: "источник не прочитан",
    OUTCOME_MISMATCH: "шаблон разошёлся с источником",
    OUTCOME_EMPTY: "источник пуст",
    OUTCOME_OK: "разобрано",
}


class ScanResult:
    """Результат ОДНОГО прохода читателя по живому источнику.

    scanned  int | None  сколько единиц ОСМОТРЕЛИ (None = источник не прочитан, измерения нет)
    parsed   int         сколько из них РАЗОБРАЛИ (по ним решение принято по существу)
    subject  str         что считали, в родительном падеже: «байков», «строк», «записей»
    payload  любое       находки прохода; читать ТОЛЬКО при `.ok`
    detail   str         почему не прочитали / что именно разошлось — одной строкой
    """

    __slots__ = ("scanned", "parsed", "subject", "payload", "detail", "outcome", "contradiction")

    def __init__(self, scanned, parsed=0, subject="", payload=None, detail=""):
        s, p = scanned, parsed
        bad = ""
        if isinstance(p, bool) or not isinstance(p, int) or p < 0:
            bad = f"«разобрано» не целое неотрицательное ({p!r})"
            p = 0
        if s is not None:
            if isinstance(s, bool) or not isinstance(s, int) or s < 0:
                bad = bad or f"«осмотрено» не целое неотрицательное ({s!r})"
                s, p = None, 0
            elif p > s:
                bad = bad or f"разобрано {p} больше осмотренного {s} — счётчики разошлись"
        elif p > 0:
            bad = bad or f"источник не прочитан, но разобрано {p} — счётчики разошлись"
            p = 0
        self.scanned = s
        self.parsed = p
        self.subject = str(subject or "")
        self.payload = payload
        self.detail = str(detail or "")
        self.contradiction = bad
        self.outcome = self._decide()

    def _decide(self):
        if self.scanned is None:
            return OUTCOME_UNREADABLE
        if self.contradiction:          # счётчикам не верим → громкий исход, а не ok
            return OUTCOME_MISMATCH
        if self.scanned == 0:
            return OUTCOME_EMPTY
        if self.parsed == 0:
            return OUTCOME_MISMATCH
        return OUTCOME_OK

    # --- Конструкторы отдельных исходов (чтобы вызывающий не собирал их из чисел) ---

    @classmethod
    def unreadable(cls, subject="", detail=""):
        """Источник не прочитан: осмотра НЕ БЫЛО. Не «осмотрено 0» — измерения нет вовсе."""
        return cls(None, 0, subject=subject, detail=detail)

    # --- Чтение исхода ---

    @property
    def ok(self):
        """Разбор состоялся: осмотрели больше нуля и хоть что-то разобрали.

        ТОЛЬКО при True нулевое число находок означает «находок правда нет». При любом другом
        исходе нуль означает «не искали» либо «искали не тем шаблоном»."""
        return self.outcome == OUTCOME_OK

    @property
    def missed(self):
        """Сколько осмотренного НЕ разобрано (осмотр был). Источник не прочитан → None."""
        if self.scanned is None:
            return None
        return self.scanned - self.parsed

    def say(self):
        """Одна строка для человека — ВСЕГДА со знаменателем. Это и есть «произносится вслух»."""
        subj = (" " + self.subject) if self.subject else ""
        tail = f" ({self.detail})" if self.detail else ""
        if self.outcome == OUTCOME_UNREADABLE:
            return f"осмотреть не удалось: {_PHRASE[OUTCOME_UNREADABLE]}{tail}"
        if self.outcome == OUTCOME_MISMATCH:
            why = self.contradiction or _PHRASE[OUTCOME_MISMATCH]
            return f"осмотрено {self.scanned}{subj}, разобрано {self.parsed} — {why}{tail}"
        if self.outcome == OUTCOME_EMPTY:
            return f"осмотрено 0{subj} — {_PHRASE[OUTCOME_EMPTY]}{tail}"
        if self.parsed == self.scanned:
            return f"осмотрено {self.scanned}{subj}{tail}"
        return (f"осмотрено {self.scanned}{subj}, разобрано {self.parsed} "
                f"(не разобрано {self.missed}){tail}")

    def __repr__(self):
        return (f"ScanResult({self.outcome}: scanned={self.scanned}, parsed={self.parsed}, "
                f"subject={self.subject!r})")
