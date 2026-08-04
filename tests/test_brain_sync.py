# -*- coding: utf-8 -*-
"""Синк базы знаний в Brain (`brain_sync.py`): зеркало не портится молча.

ПОЧЕМУ ЭТО ВООБЩЕ ТЕСТИРУЕТСЯ. Синк — операция «перезаписать док целиком», и её единственная
страховка в том, что истина лежит в git. Значит опасны ровно два молчаливых исхода: записать
ПУСТОТУ (исходник не прочитался) и посчитать успехом расхождение зеркала с истиной. Оба тут
закрыты, плюс отдельная ловушка на FAQ — у него канон живёт в Brain, и синк отсюда затёр бы
канон зеркалом.

Сети нет: BridgeClient подменён на мок целиком."""
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("ORCH_TEST_MODE", "1")
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")

import brain_sync  # noqa: E402


class FakeClient:
    """Мок моста: помнит, что записали, и отдаёт это обратно (как настоящий read_doc)."""
    store = {}
    calls = []
    read_ok = True
    echo = None          # если задано — read_doc вернёт ЭТО вместо записанного

    def __init__(self, *a, **k):
        pass

    def write_doc(self, text, name=None, id=None):
        FakeClient.calls.append(("write", name, len(text)))
        FakeClient.store[name] = text
        return {"ok": True, "name": name}

    def _call(self, action, **kw):
        # живой путь чтения дока: у read_doc своей обёртки нет, зовётся через _call (как в cclog)
        assert action == "read_doc", action
        name = kw.get("name")
        FakeClient.calls.append(("read", name, 0))
        if not FakeClient.read_ok:
            return {"ok": False, "error": "timeout"}
        text = FakeClient.echo if FakeClient.echo is not None else FakeClient.store.get(name, "")
        return {"ok": True, "text": text}


def _install(**kw):
    FakeClient.store, FakeClient.calls = {}, []
    FakeClient.read_ok, FakeClient.echo = True, None
    for k, v in kw.items():
        setattr(FakeClient, k, v)
    mod = types.ModuleType("bridge_client")
    mod.BridgeClient = FakeClient
    sys.modules["bridge_client"] = mod


def test_happy_path_syncs_and_verifies():
    _install()
    rc = brain_sync.sync("knowledge_base")
    assert rc == 0, "совпавшая длина обязана быть успехом"
    assert ("write", "knowledge_base", len(FakeClient.store["knowledge_base"])) in FakeClient.calls
    assert ("read", "knowledge_base", 0) in FakeClient.calls, "без перечитывания синк не доказан"
    src = open(os.path.join(ROOT, "docs", "knowledge_base.md"), encoding="utf-8").read()
    assert FakeClient.store["knowledge_base"] == src, "в Brain ушёл не тот текст"


def test_mismatch_is_a_failure_not_a_shrug():
    """Зеркало вернуло НЕ то, что записали → это расхождение зеркала с истиной, а не мелочь."""
    _install(echo="короче некуда")
    assert brain_sync.sync("knowledge_base") == 1


def test_unreadable_after_write_is_a_failure():
    _install(read_ok=False)
    assert brain_sync.sync("knowledge_base") == 1


def test_faq_is_not_synced_by_default():
    """У FAQ канон в Brain: молчаливый синк отсюда затёр бы канон зеркалом."""
    _install()
    assert brain_sync.sync("faq") == 0, "пропуск — не ошибка"
    assert not FakeClient.calls, f"FAQ трогать не должны были: {FakeClient.calls}"


def test_unknown_key_refused():
    _install()
    assert brain_sync.sync("нет-такого") == 2
    assert not FakeClient.calls


def test_empty_source_never_overwrites_mirror(tmp_path=None):
    """Пустой исходник — не «синк пустого дока», а отказ: зеркало дороже."""
    _install()
    saved = dict(brain_sync.BASE_DOCS)
    probe = os.path.join(ROOT, "docs", "artifacts", ".brain_sync_empty_probe.md")
    try:
        with open(probe, "w", encoding="utf-8") as fh:
            fh.write("   \n")
        brain_sync.BASE_DOCS["park_list"] = os.path.join("artifacts", ".brain_sync_empty_probe.md")
        assert brain_sync.sync("park_list") == 2
        assert not FakeClient.calls, f"на мост звонить было незачем: {FakeClient.calls}"
    finally:
        brain_sync.BASE_DOCS.clear()
        brain_sync.BASE_DOCS.update(saved)
        if os.path.exists(probe):
            os.remove(probe)      # свой черновик, созданный этим же тестом


def test_main_without_keys_does_nothing():
    _install()
    assert brain_sync.main([]) == 2
    assert not FakeClient.calls


def test_check_is_read_only():
    """`--check` — единственный законный ход после `receipt_unknown` (запись могла долететь,
    повтор вслепую положил бы вторую). Значит он обязан ЧИТАТЬ и только читать."""
    _install()
    src = open(os.path.join(ROOT, "docs", "knowledge_base.md"), encoding="utf-8").read()
    FakeClient.echo = src
    assert brain_sync.check("knowledge_base") == 0
    assert [c[0] for c in FakeClient.calls] == ["read"], f"check писал: {FakeClient.calls}"

    _install(echo="разошлось")
    assert brain_sync.check("knowledge_base") == 1
    assert [c[0] for c in FakeClient.calls] == ["read"], f"check писал: {FakeClient.calls}"

    _install(read_ok=False)
    assert brain_sync.check("knowledge_base") == 2


if __name__ == "__main__":
    fails = []
    for _n, _f in sorted(list(globals().items())):
        if _n.startswith("test_") and callable(_f):
            try:
                _f()
                print("OK:", _n)
            except AssertionError as e:
                fails.append((_n, str(e)))
                print("FAIL:", _n, "\n   ", str(e)[:400])
    if fails:
        print("\nКРАСНЫХ:", len(fails))
        sys.exit(1)
    print("\nВСЕ ТЕСТЫ brain_sync ПРОШЛИ")
