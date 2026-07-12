"""Переключение «пк: декомпозируй» на ЛОКАЛЬНЫЙ дирижёр ПК (финал развязки, 12.07.2026).
Флаг PC_DEC_LOCAL (.env, деф. 0): 1 → родитель pc-декомпозиции ставится from=Filipp-pcloc-dec
+ lane=pc (цепь целиком ведёт pc_orchestrator с PC_LOCAL_DEC=1; живьём доказан родителем 195,
демон ПК 239e4dc), VPS-демон её НЕ трогает (надзор группирует строго Filipp-pc-dec — не менялся);
0 → байт-в-байт старый путь (Filipp-pc-dec БЕЗ lane, план строит VPS). Обе ветки постановки:
тема 829 (lane='pc') и роутер 328 (театр pc). Сети/Telegram/claude НЕТ — слой 2 замокан."""
import os
import sys

sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ["THEATER_ROUTER"] = "1"      # роутер ВКЛ детерминированно (путь 328 с «пк:»)
import devbot as DB


class EnqBridge:
    def __init__(s):
        s.calls = []

    def enqueue_task(s, frm, txt, lane=None):
        s.calls.append((frm, txt, lane))
        return {"ok": True, "id": 77}


class _NoLayer2:
    """Слой 2 ЗАПРЕЩЁН (assert) — все кейсы решает слой 1 (явный «пк:» / keywords)."""
    def __enter__(s):
        s.old = DB._classify_theater

        def fake(text):
            raise AssertionError(f"слой 2 НЕ должен зваться: {text!r}")
        DB._classify_theater = fake
        return s

    def __exit__(s, *a):
        DB._classify_theater = s.old
        return False


class _Flag:
    """Временное значение PC_DEC_LOCAL в env (флаг читается лениво на каждый вызов)."""
    def __init__(s, val):
        s.val = val

    def __enter__(s):
        s.old = os.environ.get("PC_DEC_LOCAL")
        if s.val is None:
            os.environ.pop("PC_DEC_LOCAL", None)
        else:
            os.environ["PC_DEC_LOCAL"] = s.val
        return s

    def __exit__(s, *a):
        if s.old is None:
            os.environ.pop("PC_DEC_LOCAL", None)
        else:
            os.environ["PC_DEC_LOCAL"] = s.old
        return False


# (1) флаг ВКЛ, тема 829 (lane='pc'): родитель Filipp-pcloc-dec + lane=pc, карточка про локальный дирижёр
def test_flag_on_829():
    with _Flag("1"), _NoLayer2():
        b = EnqBridge()
        r = DB._try_enqueue("декомпозируй: большое ТЗ", b, lane="pc")
        assert b.calls[-1] == (DB.QUEUE_FROM_PCLOC_DEC, "большое ТЗ", "pc"), \
            f"PC_DEC_LOCAL=1: родитель pcloc-dec + lane=pc: {b.calls}"
        assert "ЛОКАЛЬНЫЙ" in r and "77" in r, f"карточка про локальный дирижёр: {r}"


# (2) флаг ВКЛ, 328 с явным «пк:»: тот же локальный родитель + бейдж роутера 🎭 pc
def test_flag_on_328_pc_prefix():
    with _Flag("1"), _NoLayer2():
        b = EnqBridge()
        r = DB._try_enqueue("декомпозируй: пк: большое ТЗ", b)
        assert b.calls[-1] == (DB.QUEUE_FROM_PCLOC_DEC, "большое ТЗ", "pc"), \
            f"328+пк: → pcloc-dec + lane=pc, префикс срезан: {b.calls}"
        assert "🎭 pc" in r and "ЛОКАЛЬНЫЙ" in r, f"бейдж роутера + локальный дирижёр: {r}"
        # канонизация лидирующего префикса (инцидент 23:49 11.07) живёт и с флагом
        r = DB._try_enqueue("пк: декомпозируй: другое крупное ТЗ", b)
        assert b.calls[-1] == (DB.QUEUE_FROM_PCLOC_DEC, "другое крупное ТЗ", "pc"), \
            f"«пк: декомпозируй:» канонизируется и идёт локальному дирижёру: {b.calls}"


# (3) флаг ВЫКЛ (0 / не задан): байт-в-байт старый путь — Filipp-pc-dec БЕЗ lane, обе ветки
def test_flag_off_regression():
    for flagval in ("0", None):
        with _Flag(flagval), _NoLayer2():
            b = EnqBridge()
            r = DB._try_enqueue("декомпозируй: большое ТЗ", b, lane="pc")
            assert b.calls[-1] == (DB.QUEUE_FROM_PC_DEC, "большое ТЗ", None), \
                f"флаг {flagval!r}: 829 по-старому (pc-dec без lane): {b.calls}"
            assert "VPS-дирижёр" in r, f"старая карточка (план строит VPS): {r}"
            r = DB._try_enqueue("декомпозируй: пк: большое ТЗ", b)
            assert b.calls[-1] == (DB.QUEUE_FROM_PC_DEC, "большое ТЗ", None), \
                f"флаг {flagval!r}: 328+пк: по-старому: {b.calls}"
            assert "🎭 pc" in r and "VPS-дирижёр" in r


# (4) флаг ВКЛ не трогает остальные ветки роутера: одиночные пк-задачи и vps-декомпозиция как были
def test_flag_on_other_branches_intact():
    with _Flag("1"), _NoLayer2():
        b = EnqBridge()
        DB._try_enqueue("тз: пк: поправь черновики", b)
        assert b.calls[-1] == (DB.QUEUE_FROM_DEV, "поправь черновики", "pc"), \
            f"одиночное «тз: пк:» не изменилось: {b.calls}"
        DB._try_enqueue("задача: пк: пингани агента", b)
        assert b.calls[-1] == (DB.QUEUE_FROM, "пингани агента", "pc"), \
            f"одиночная «задача: пк:» не изменилась: {b.calls}"
        DB._try_enqueue("тз: собери X", b, lane="pc")
        assert b.calls[-1] == (DB.QUEUE_FROM_PC_DEV, "собери X", "pc"), \
            f"829 одиночное ТЗ не изменилось: {b.calls}"
        r = DB._try_enqueue("декомпозируй: прогони гейт", b)
        assert b.calls[-1] == (DB.QUEUE_FROM_DEC, "прогони гейт", None), \
            f"vps-декомпозиция не изменилась (флаг её не касается): {b.calls}"
        assert "🎭 vps" in r


# (5) парсер флага: 1/true/on → ВКЛ; 0/пусто/мусор/не задан → ВЫКЛ (дефолт = старое поведение)
def test_flag_parser():
    for v in ("1", "true", "TRUE", "on"):
        with _Flag(v):
            assert DB._pc_dec_local(), f"PC_DEC_LOCAL={v!r} → включён"
    for v in ("0", "", "false", "off", "мусор", None):
        with _Flag(v):
            assert not DB._pc_dec_local(), f"PC_DEC_LOCAL={v!r} → выключен (старое поведение)"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ✓ {fn.__name__}")
    print(f"OK — {len(fns)} тестов PC_DEC_LOCAL (локальный дирижёр ПК, финал развязки)")
