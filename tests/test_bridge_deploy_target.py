"""test_bridge_deploy_target.py — отказ выкладывать из долгоживущей папки (10.08.2026).

ПОВОД (шаг 2 цели 439). `bridge_deploy.py` был намертво нацелен на долгоживущую папку моста,
а она 10.08.2026 обезврежена как источник выкладки: настройки проекта переименованы, и на
свежем отпечатке прод стоял @79, а папка отставала на 4 файла из 17 — заливка стёрла бы
18 функций и 5 маршрутов живого моста. Отказ при этом был БЕЗМОЛВНЫЙ и ПОЗДНИЙ: скрипт сначала
крутил полный гейт (~3 мин) и Node-харнессы, доходил до clasp и падал уже там — ошибкой
инструмента, из которой не следует, что делать дальше.

ЧТО ЗАКРЕПЛЕНО ЗДЕСЬ:
  - отказ РАННИЙ: цель судится ПЕРВОЙ, до гейта и до единого обращения к clasp
    (доказывается тем, что `subprocess.run` не зван НИ РАЗУ);
  - отказ ЯВНЫЙ: несёт указатель «откуда выкладывать» и «где истина прода»;
  - запрет судит ПУТЬ, а не состояние папки: возврат в неё настроек проекта отказ НЕ снимает;
  - цели по умолчанию нет вовсе — не названа, значит выкладывать неоткуда;
  - у clasp-вызовов нет каталога «по привычке» (структурный страж сигнатур).

Путь запрещённой папки в этом файле НЕ пишется литералом намеренно: замок
`test_bridge_prod_mirror.test_gate_reads_mirror_not_the_folder` флагует такие литералы в
`tests/`, и правило верное — имя берётся из самого модуля, тогда тест и код не разъедутся.
"""
import contextlib
import inspect
import os
import sys
import tempfile
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("PRETOOL_NOPUSH", "1")

import bridge_deploy

GS = bridge_deploy.LEGACY_GS_ROOT          # запрещённая цель, имя берём у модуля
SETTINGS = bridge_deploy.CLASP_SETTINGS


# ──────────────────────────── вспомогательные ────────────────────────────────

@contextlib.contextmanager
def _build(with_settings=True):
    """Настоящий временный каталог сборки (годность судится живыми os-вызовами).

    Каталог живёт контекстом и убирается сам: своего кода удаления здесь нет намеренно —
    цель `shutil.rmtree(<переменная>)` невычислима, и гард честно судит такую уборку красной.
    """
    with tempfile.TemporaryDirectory(prefix="tb_bdt_") as d:
        if with_settings:
            with open(os.path.join(d, SETTINGS), "w") as fh:
                fh.write('{"scriptId":"test"}')
        yield d


def _no_subprocess(*a, **kw):
    raise AssertionError("subprocess вызван при отказе: %r" % (a,))


def _deploy_counting(target_arg, argv=None, env_dir=None):
    """Прогнать deploy() с запретом на любой внешний вызов. Возвращает (code, out)."""
    calls = []

    def rec(*a, **kw):
        calls.append(a)
        return _no_subprocess(*a, **kw)

    argv = ["bridge_deploy.py"] if argv is None else argv
    env = dict(os.environ)
    env.pop(bridge_deploy.BUILD_DIR_ENV, None)
    if env_dir:
        env[bridge_deploy.BUILD_DIR_ENV] = env_dir

    with patch("bridge_deploy.subprocess.run", side_effect=rec), \
         patch.object(sys, "argv", argv), \
         patch.dict(os.environ, env, clear=True):
        if target_arg is _UNSET:
            code = bridge_deploy.deploy()
        else:
            code = bridge_deploy.deploy(target=target_arg)
    return code, calls


_UNSET = object()


# ───────────────────── (1) годная цель проходит проверку ─────────────────────

def test_good_build_dir_is_accepted():
    """Каталог сборки с настройками проекта — годен (иначе правило запрещало бы всё)."""
    with _build() as d:
        assert bridge_deploy.target_refusal(d) is None, "годный каталог сборки отвергнут"


# ─────────────────── (2) долгоживущая папка запрещена по пути ────────────────

def test_legacy_folder_is_refused():
    """Сама долгоживущая папка — отказ, и он называет её вслух."""
    r = bridge_deploy.target_refusal(GS)
    assert r, "выкладка из обезвреженной папки НЕ отказана"
    assert GS in r, "отказ не называет папку, о которой речь: %s" % r


def test_legacy_subdir_is_refused_as_folder_not_as_missing():
    """Подкаталог запрещённой папки отказан ПО ПАПКЕ, а не «не существует».

    Порядок проверок здесь — суть: мягкое «не существует» читалось бы как «создай каталог
    и всё поедет», то есть как починимое препятствие, а не как запрет.
    """
    sub = os.path.join(GS, "нет-такого-каталога", "build")
    r = bridge_deploy.target_refusal(sub)
    assert r, "подкаталог запрещённой папки не отказан"
    assert "обезврежена" in r, "отказ по подкаталогу не про запрет папки: %s" % r
    assert "не существует" not in r, "подкаталог получил мягкий отказ «не существует»: %s" % r


def test_legacy_via_dotdot_is_refused():
    """Путь с «..», ведущий в ту же папку, отказан: судится realpath, а не написание."""
    sneaky = os.path.join(GS, "..", os.path.basename(GS), "sub")
    r = bridge_deploy.target_refusal(sneaky)
    assert r and "обезврежена" in r, "обход через «..» не отказан: %s" % r


def test_ban_is_by_path_not_by_arming():
    """ГЛАВНОЕ СВОЙСТВО: вернули в папку настройки проекта — отказ НЕ снялся.

    Папка запрещена как ИСТОЧНИК ВЫКЛАДКИ, а не как «сейчас неисправная». Если бы запрет
    держался на отсутствии настроек, «зарядка» папки молча вернула бы старый класс: заливка
    целиком из отстающего каталога.
    """
    with _build(with_settings=True) as armed:                        # каталог с настройками…
        with patch.object(bridge_deploy, "LEGACY_GS_ROOT", armed):   # …и он же запрещённый
            r = bridge_deploy.target_refusal(armed)
        assert r, "заряженная долгоживущая папка прошла как годная цель"
        assert "обезврежена" in r, "отказ не по запрету папки: %s" % r


def test_real_folder_today_is_disarmed_and_still_refused():
    """Живой факт: папка на машине разряжена — и всё равно отказана (два независимых основания)."""
    if not os.path.isdir(GS):
        return                                # чужая машина (полоса ПК) — судить не о чем
    assert not os.path.exists(os.path.join(GS, SETTINGS)), \
        "папка снова заряжена — это находка замка bridge_prod, а не этого теста"
    assert bridge_deploy.target_refusal(GS), "живая папка не отказана"


# ──────────────────── (3) прочие негодные цели, fail-closed ──────────────────

def test_unnamed_target_is_refused():
    """Цель не названа → отказ: цели по умолчанию у выкладки нет."""
    for empty in (None, "", "   "):
        r = bridge_deploy.target_refusal(empty)
        assert r, "пустая цель %r принята" % empty
        assert bridge_deploy.BUILD_DIR_ENV in r, "отказ не говорит, чем назвать цель: %s" % r


def test_missing_dir_is_refused():
    """Несуществующая цель → отказ."""
    r = bridge_deploy.target_refusal("/tmp/нет-такого-каталога-сборки-12345")
    assert r and "не существует" in r, "несуществующая цель принята: %s" % r


def test_dir_without_settings_is_refused():
    """Каталог без настроек проекта — не каталог сборки захода."""
    with _build(with_settings=False) as d:
        r = bridge_deploy.target_refusal(d)
        assert r and SETTINGS in r, "каталог без настроек принят: %s" % r


def test_prod_mirror_is_not_a_deploy_source():
    """Зеркало прода `bridge_prod/` целью выкладки НЕ является (оно истина, а не источник)."""
    mirror = os.path.join(ROOT, "bridge_prod")
    if not os.path.isdir(mirror):
        return
    assert bridge_deploy.target_refusal(mirror), "из зеркала прода можно выкладывать — так нельзя"


# ─────────────── (4) отказ РАННИЙ: ни гейта, ни clasp, ни сети ───────────────

def test_deploy_from_legacy_folder_touches_nothing():
    """ГЛАВНЫЙ ТЕСТ: deploy() на запрещённой папке → код 3 и НИ ОДНОГО внешнего вызова.

    Ноль вызовов `subprocess.run` доказывает сразу оба свойства: гейт не крутился (отказ
    ранний) и clasp не звался (ничего не выложено).
    """
    code, calls = _deploy_counting(GS)
    assert code == 3, "ожидали код отказа 3, получили %s" % code
    assert not calls, "при отказе были внешние вызовы: %r" % (calls,)


def test_deploy_without_target_refuses():
    """Голый запуск без аргумента и без переменной окружения → отказ, ноль вызовов."""
    code, calls = _deploy_counting(_UNSET)
    assert code == 3, "голый запуск не отказан: код %s" % code
    assert not calls, "при отказе были внешние вызовы: %r" % (calls,)


def test_deploy_reads_env_target():
    """Цель из переменной окружения читается (иначе отказ был бы неотличим от «не умеет»)."""
    with _build() as d:
        with patch.dict(os.environ, {bridge_deploy.BUILD_DIR_ENV: d}, clear=False), \
             patch.object(sys, "argv", ["bridge_deploy.py"]):
            assert bridge_deploy._cli_target() == d


def test_cli_argument_wins_over_env():
    """Аргумент команды сильнее переменной окружения."""
    with patch.dict(os.environ, {bridge_deploy.BUILD_DIR_ENV: "/tmp/из-окружения"}, clear=False):
        assert bridge_deploy._cli_target(argv=["bridge_deploy.py", "/tmp/из-аргумента"]) \
            == "/tmp/из-аргумента"


def test_cli_target_none_when_nothing_given():
    assert bridge_deploy._cli_target(argv=["bridge_deploy.py"], env={}) is None
    assert bridge_deploy._cli_target(argv=["bridge_deploy.py", "  "], env={}) is None


# ────────────────────── (5) отказ ЯВНЫЙ: указатель на месте ──────────────────

def test_pointer_names_where_to_deploy_from_and_where_truth_is():
    """Указатель называет ОБА адреса: откуда выкладывать и где истина прода."""
    p = bridge_deploy.POINTER
    for must in ("каталог", "сборки захода", "bridge_prod/", "CLAUDE.md"):
        assert must in p, "указатель не называет главного (%s): %s" % (must, p)


def test_refusal_output_carries_pointer():
    """Указатель печатается ВМЕСТЕ с причиной — иначе отказ не говорит, что делать дальше."""
    import io
    from contextlib import redirect_stdout
    buf = io.StringIO()
    with redirect_stdout(buf), patch("bridge_deploy.subprocess.run", side_effect=_no_subprocess):
        code = bridge_deploy.deploy(target=GS)
    out = buf.getvalue()
    assert code == 3
    assert bridge_deploy.POINTER in out, "в выводе отказа нет указателя:\n%s" % out
    assert "ВЫКЛАДКА НЕ НАЧАТА" in out, "отказ не назван вслух:\n%s" % out


# ─────────────── (6) структурные стражи: цели «по привычке» нет ──────────────

def test_clasp_callers_require_explicit_target():
    """У clasp-вызовов нет каталога по умолчанию — иначе запрет обходится прямым зовом."""
    for name in ("_get_current_version", "_do_redeploy", "_do_rollback"):
        fn = getattr(bridge_deploy, name)
        params = inspect.signature(fn).parameters
        assert "target" in params, "%s не принимает цель явно" % name
        assert params["target"].default is inspect.Parameter.empty, \
            "%s имеет цель по умолчанию — так запрет обходится" % name


def test_module_has_no_default_target_constant():
    """В модуле не осталось константы-цели, направленной в долгоживущую папку."""
    src = open(os.path.join(ROOT, "bridge_deploy.py"), encoding="utf-8").read()
    assert "BRIDGE_ROOT" not in src, "вернулась константа-цель BRIDGE_ROOT"
    assert "cwd=LEGACY_GS_ROOT" not in src, "clasp снова работает В долгоживущей папке"
    assert src.count("LEGACY_GS_ROOT") >= 2, "имя запрещённой папки пропало — отказ онемеет"


def test_deploy_accepts_target_argument():
    """deploy() принимает цель параметром (так её задают тесты и вызывающий код)."""
    assert "target" in inspect.signature(bridge_deploy.deploy).parameters


if __name__ == "__main__":
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = []
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS {name}")
        except Exception as e:
            print(f"  FAIL {name}: {e}")
            import traceback; traceback.print_exc()
            failed.append(name)
    print(f"\n{len(tests) - len(failed)}/{len(tests)} — {'ВСЕ PASS' if not failed else 'FAIL: ' + str(failed)}")
    sys.exit(0 if not failed else 1)
