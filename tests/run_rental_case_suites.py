#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Раннер наборов К4 (дело аренды, rental_case): tests/run_rental_case_suites.py

Запуск (только stdlib, код разбирается ast.parse(..., feature_version=(3, 8))):

    python tests/run_rental_case_suites.py --label <метка> [--root <каталог>] [--only <набор>]...
                                            [--trace-dir <каталог>] [--runs-base <каталог>] [--timeout <с>]

Наборы по порядку; каждый — отдельный подпроцесс (cwd=<root>, таймаут, своё окружение):

    hygiene      статические проверки (см. HYGIENE_RULES): разбор под 3.8 и синтаксис 3.9+, мимо которого
                 feature_version проходит; только LF; изоляция модулей rental_case*.py; API 3.9+; SQL записи rc_*
                 только в rental_case.py; SQL новее SQLite 3.9; нет удаления файлов; тесты импортируют
                 подделку сети; подделка подменяет socket.socket
    rules        tests/test_rental_case_rules.py
    store        tests/test_rental_case_store.py
    accept       tests/test_rental_case_accept.py
    seam         tests/test_rental_case_seam.py (шапка CONTRACT_K4 и §13: шов S1–S7 на подделке staff_ask)
    demo_A       tests/rental_case_demo.py --variant A --trace <trace-dir>/trace_demo.jsonl
    demo_B       tests/rental_case_demo.py --variant B
    demo_repeat  tests/rental_case_demo.py --repeat-check

--only принимает имя набора или группу (hygiene, rules, store, accept, seam, demo); повторяемый.
tests/test_rental_case_integ_*.py здесь НЕ запускаются (они идут в полном дереве регрессии) — hygiene их
только разбирает; мутанты (tests/rental_case_mutants.py) гоняет независимая проверка (CONTRACT §15 п.4).

Итог: <runs-base>/<label>/results.json (по умолчанию runs-base = D:/turbobaby-bot/tmp/k4_0910/ttmp/runs):
{"suites": [{suite, cmd, exit, status PASS/FAIL/MISSING/TIMEOUT, seconds, ran, failures, errors, tail, ...}],
 "summary": {...}}. Отсутствующий файл набора — MISSING (провал, не пропуск). Код выхода 0 — только если
все выбранные наборы PASS; 1 — иначе; 2 — ошибка вызова/места.

Ничего не удаляет: прежние results.json, logs/ и файл следа той же метки откладываются переименованием
(*.prev-<штамп>), временные каталоги наборов остаются в <runs-base>/<label>/tmp.
"""
import argparse
import ast
import datetime
import glob
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import time
import tokenize
from typing import Any, Dict, List, Optional, Set, Tuple

DEFAULT_RUNS_BASE = "D:/turbobaby-bot/tmp/k4_0910/ttmp/runs"
DEFAULT_TIMEOUT_S = 900
TAIL_LINES = 60
PROXY_SINK = "http://127.0.0.1:9"
HYGIENE_MARK = "K4_HYGIENE_RESULT "
EXIT_MISSING = 3
LABEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
THIS_FILE = os.path.abspath(__file__)

DEMO_FILE = "tests/rental_case_demo.py"
TRACE_NAME = "trace_demo.jsonl"

# Порядок и состав наборов. "args" может содержать "{trace}" — путь следа демо.
SUITES = (
    {"suite": "hygiene", "group": "hygiene", "kind": "hygiene", "file": None, "args": ()},
    {"suite": "rules", "group": "rules", "kind": "unittest", "file": "tests/test_rental_case_rules.py", "args": ()},
    {"suite": "store", "group": "store", "kind": "unittest", "file": "tests/test_rental_case_store.py", "args": ()},
    {"suite": "accept", "group": "accept", "kind": "unittest", "file": "tests/test_rental_case_accept.py", "args": ()},
    {"suite": "seam", "group": "seam", "kind": "unittest", "file": "tests/test_rental_case_seam.py", "args": ()},
    {"suite": "demo_A", "group": "demo", "kind": "demo", "file": DEMO_FILE,
     "args": ("--variant", "A", "--trace", "{trace}")},
    {"suite": "demo_B", "group": "demo", "kind": "demo", "file": DEMO_FILE, "args": ("--variant", "B")},
    {"suite": "demo_repeat", "group": "demo", "kind": "demo", "file": DEMO_FILE, "args": ("--repeat-check",)},
)

NOT_RUN_HERE = (
    "tests/test_rental_case_integ_*.py: full regression tree only (hygiene parses them)",
    "tests/rental_case_mutants.py: independent check, CONTRACT_K4 §15 p.4",
)

# --------------------------------------------------------------------------------------------------
# Общие мелочи
# --------------------------------------------------------------------------------------------------


def _utc_now():
    return datetime.datetime.now(datetime.timezone.utc)


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(1 << 20)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _rel(path, root):
    return os.path.relpath(path, root).replace("\\", "/")


def _norm(path):
    return os.path.normpath(os.path.abspath(path))


# --------------------------------------------------------------------------------------------------
# hygiene: статические проверки (работает в отдельном подпроцессе: --hygiene-worker)
# --------------------------------------------------------------------------------------------------

HYGIENE_RULES = (
    ("missing_required", "нет обязательного файла: rental_case.py, rental_case_rules.py, rental_case_adapters.py, "
                         "tests/rental_case_fakes.py (статус MISSING)"),
    ("crlf", "в файле есть \\r (нужны только LF)"),
    ("not_utf8", "файл не читается как UTF-8"),
    ("py38_syntax", "ast.parse(src, feature_version=(3, 8)) отказал"),
    ("py38_fstring_*", "f-строки PEP 701 (3.12): та же кавычка/обратная косая/комментарий/перенос в выражении"),
    ("py39_paren_with", "скобочный with (a as b, ...): только 3.9+"),
    ("py39_relaxed_decorator", "декоратор не вида имя[.имя][(...)]: только 3.9+"),
    ("py311_star_subscript", "звёздочка в индексе/аннотации *args: только 3.11+"),
    ("py39_api", "API новее 3.8 (removeprefix/removesuffix, functools.cache, datetime.UTC, math.lcm, ...)"),
    ("py39_module", "модуль новее 3.8 (zoneinfo, graphlib, tomllib)"),
    ("banned_utcfromtimestamp", "datetime.utcfromtimestamp запрещён (вместо него datetime.fromtimestamp(t, timezone.utc))"),
    ("py39_generic_subscript", "list[...]/dict[...]/collections.abc.X[...] во время выполнения (без from __future__ "
                               "import annotations)"),
    ("py310_union_annotation", "аннотация X | Y"),
    ("py310_union_runtime", "X | Y из типов во время выполнения"),
    ("py39_dict_union", "dict | dict / |= со словарём"),
    ("py310_keyword", "ключ новее 3.8: zip(strict=), bisect key=, dataclass(slots/kw_only/...), "
                      "sqlite3.connect(autocommit=), logging.basicConfig(encoding=), hashlib usedforsecurity=, "
                      "ArgumentParser(exit_on_error=)"),
    ("py310_traceback_single_arg", "traceback.print_exception/format_exception с одним аргументом"),
    ("py311_int_bytes_default", "int.to_bytes/from_bytes без byteorder"),
    ("no_delete", "удаление: os.remove/unlink/rmdir/removedirs, shutil.rmtree, .unlink(), .rmdir(), "
                  "TemporaryDirectory, NamedTemporaryFile без delete=False"),
    ("module_net_proc_import", "модуль rental_case*.py импортирует сеть/процессы (socket, urllib, http, requests, "
                               "ssl, subprocess, ...)"),
    ("module_config_import", "модуль rental_case*.py импортирует чтение конфигов (configparser, toml, yaml)"),
    ("module_env", "модуль rental_case*.py читает окружение (os.environ/os.getenv/...)"),
    ("module_proc_call", "модуль rental_case*.py запускает/убивает процессы (os.system/popen/spawn*/exec*/kill)"),
    ("module_literal_path", "модуль rental_case*.py открывает файл по пути-литералу (open/io.open/codecs.open/os.open/"
                            "pathlib.Path/sqlite3.connect с константой, кроме ':memory:'): пути только инжектируются"),
    ("sql_write_outside_store", "SQL записи в rc_* (INSERT/UPDATE/DELETE/REPLACE/CREATE/DROP/ALTER) вне rental_case.py "
                                "(текстом, как grep: I23, К4-C14)"),
    ("sqlite_newer_than_3_9", "в SQL модулей и файлов tests/*rental_case*.py (у тестов — константа, f-строка, "
                              "сложение строк): RETURNING, UPSERT ON CONFLICT DO, JSON1, окна, IIF, STRICT, "
                              "RENAME/DROP COLUMN, ... (рамки CONTRACT: SQLite >= 3.9; К4-C19)"),
    ("tech_timeout_name", "в rental_case*.py есть TECH_TIMEOUT_S или tech_due_at (К4-C38)"),
    ("net_guard_import", "tests/test_rental_case_*.py и tests/rental_case_demo.py обязаны импортировать "
                         "rental_case_fakes (подмена socket.socket)"),
    ("fakes_no_socket_patch", "tests/rental_case_fakes.py не подменяет socket.socket"),
)

HYGIENE_REQUIRED = ("rental_case.py", "rental_case_rules.py", "rental_case_adapters.py", "tests/rental_case_fakes.py")
CONTRACT_INVENTORY = HYGIENE_REQUIRED + (
    "tests/test_rental_case_rules.py", "tests/test_rental_case_store.py", "tests/test_rental_case_accept.py",
    "tests/test_rental_case_seam.py", "tests/rental_case_mutants.py", "tests/rental_case_demo.py",
    "tests/run_rental_case_suites.py",
)

API_FULL = {
    "functools.cache": "3.9", "math.lcm": "3.9", "math.nextafter": "3.9", "math.ulp": "3.9",
    "random.randbytes": "3.9", "ast.unparse": "3.9", "asyncio.to_thread": "3.9",
    "os.waitstatus_to_exitcode": "3.9", "argparse.BooleanOptionalAction": "3.9", "types.GenericAlias": "3.9",
    "typing.Annotated": "3.9",
    "itertools.pairwise": "3.10", "contextlib.aclosing": "3.10", "types.NoneType": "3.10",
    "types.UnionType": "3.10", "types.EllipsisType": "3.10", "types.NotImplementedType": "3.10",
    "typing.ParamSpec": "3.10", "typing.TypeAlias": "3.10", "typing.Concatenate": "3.10",
    "typing.TypeGuard": "3.10", "typing.is_typeddict": "3.10",
    "datetime.UTC": "3.11", "contextlib.chdir": "3.11", "enum.StrEnum": "3.11", "enum.verify": "3.11",
    "hashlib.file_digest": "3.11", "operator.call": "3.11", "asyncio.timeout": "3.11", "asyncio.TaskGroup": "3.11",
    "typing.Self": "3.11", "typing.LiteralString": "3.11", "typing.Never": "3.11", "typing.assert_never": "3.11",
    "typing.assert_type": "3.11", "typing.Required": "3.11", "typing.NotRequired": "3.11", "typing.Unpack": "3.11",
    "typing.TypeVarTuple": "3.11", "typing.reveal_type": "3.11", "typing.dataclass_transform": "3.11",
    "typing.override": "3.12", "itertools.batched": "3.12",
}
API_ATTR_ANY = {
    "removeprefix": "3.9", "removesuffix": "3.9", "is_relative_to": "3.9", "with_stem": "3.9",
    "bit_count": "3.10", "hardlink_to": "3.10", "blobopen": "3.11", "setlimit": "3.11", "getlimit": "3.11",
    "is_junction": "3.12", "autocommit": "3.12",
}
API_MODULES = {"zoneinfo": "3.9", "graphlib": "3.9", "tomllib": "3.11"}
BUILTIN_GENERICS = frozenset(("list", "dict", "tuple", "set", "frozenset", "type"))
GENERIC_FULL = frozenset((
    "collections.OrderedDict", "collections.defaultdict", "collections.deque", "collections.Counter",
    "collections.ChainMap", "re.Pattern", "re.Match", "queue.Queue", "os.PathLike",
    "contextlib.AbstractContextManager",
))
TYPEISH_NAMES = frozenset(("int", "str", "float", "bool", "bytes", "bytearray", "complex", "list", "dict",
                           "tuple", "set", "frozenset", "type", "object"))

NET_PROC_MODULES = frozenset((
    "socket", "ssl", "urllib", "urllib2", "urllib3", "http", "httplib", "requests", "httpx", "aiohttp", "ftplib",
    "smtplib", "poplib", "imaplib", "nntplib", "telnetlib", "xmlrpc", "socketserver", "asyncio", "websocket",
    "websockets", "subprocess", "multiprocessing", "pty", "webbrowser",
))
CONFIG_MODULES = frozenset(("configparser", "tomllib", "toml", "yaml"))
ENV_FULL = frozenset(("os.environ", "os.environb", "os.getenv", "os.getenvb", "os.putenv", "os.unsetenv"))
PROC_FULL = frozenset(("os.system", "os.popen", "os.startfile", "os.fork", "os.forkpty", "os.kill", "os.killpg",
                       "os.posix_spawn", "os.posix_spawnp"))
DELETE_FULL = frozenset(("os.remove", "os.unlink", "os.rmdir", "os.removedirs", "shutil.rmtree",
                         "tempfile.TemporaryDirectory"))
DELETE_ATTR_ANY = frozenset(("unlink", "rmdir", "rmtree", "removedirs", "TemporaryDirectory"))

LITERAL_PATH_CALLS = frozenset(("open", "io.open", "codecs.open", "os.open", "builtins.open", "pathlib.Path",
                                "pathlib.PurePath", "sqlite3.connect"))
SQL_WRITE_RE = re.compile(
    r"\b(?:INSERT\s+(?:OR\s+[A-Za-z]+\s+)?INTO|REPLACE\s+INTO|UPDATE(?:\s+OR\s+[A-Za-z]+)?|DELETE\s+FROM"
    r"|CREATE\s+(?:UNIQUE\s+)?(?:TEMP(?:ORARY)?\s+)?(?:TABLE|INDEX|TRIGGER|VIEW)(?:\s+IF\s+NOT\s+EXISTS)?"
    r"|DROP\s+(?:TABLE|INDEX|TRIGGER|VIEW)(?:\s+IF\s+EXISTS)?|ALTER\s+TABLE)"
    r"\s+[\"'`\[]?(?:main\.)?[\"'`\[]?rc_[A-Za-z0-9_]*",
    re.I)
SQL_DDL_ON_RE = re.compile(r"\bCREATE\s+[^;\n]{0,200}?\bON\s+[\"'`\[]?(?:main\.)?rc_[A-Za-z0-9_]*", re.I)
SQL_LOOKS_RE = re.compile(r"^\s*(?:SELECT|INSERT|UPDATE|DELETE|CREATE|DROP|ALTER|WITH|REPLACE|PRAGMA)\b", re.I)
SQL_NEWER = (
    ("RETURNING", re.compile(r"\bRETURNING\b", re.I)),
    ("UPSERT ON CONFLICT ... DO", re.compile(r"\bON\s+CONFLICT\b[^;]*?\bDO\b", re.I)),
    ("JSON1 function", re.compile(r"\bjson(?:_[a-z_]+)?\s*\(", re.I)),
    ("JSON ->> operator", re.compile(r"->>")),
    ("window OVER (", re.compile(r"\bOVER\s*\(", re.I)),
    ("IIF(", re.compile(r"\bIIF\s*\(", re.I)),
    ("NULLS FIRST/LAST", re.compile(r"\bNULLS\s+(?:FIRST|LAST)\b", re.I)),
    ("GENERATED ALWAYS", re.compile(r"\bGENERATED\s+ALWAYS\b", re.I)),
    ("STRICT table", re.compile(r"\)\s*STRICT\b", re.I)),
    ("FILTER (WHERE", re.compile(r"\bFILTER\s*\(\s*WHERE\b", re.I)),
    ("RENAME COLUMN", re.compile(r"\bRENAME\s+COLUMN\b", re.I)),
    ("DROP COLUMN", re.compile(r"\bDROP\s+COLUMN\b", re.I)),
    ("UNIXEPOCH(", re.compile(r"\bUNIXEPOCH\s*\(", re.I)),
    ("IS DISTINCT FROM", re.compile(r"\bIS\s+(?:NOT\s+)?DISTINCT\s+FROM\b", re.I)),
    ("RIGHT/FULL JOIN", re.compile(r"\b(?:RIGHT|FULL)\s+(?:OUTER\s+)?JOIN\b", re.I)),
)
TECH_NAMES = ("TECH_TIMEOUT_S", "tech_due_at")
# Сам раннер SQL не исполняет (sqlite3 не импортирует); его строки вида «DROP COLUMN» — заголовки перечня SQL_NEWER,
# а не SQL. Правило sqlite_newer_than_3_9 для тестов его поэтому не судит (иначе находка на собственном словаре).
RUNNER_REL = "tests/run_rental_case_suites.py"

_FSTART = getattr(tokenize, "FSTRING_START", None)
_FMID = getattr(tokenize, "FSTRING_MIDDLE", None)
_FEND = getattr(tokenize, "FSTRING_END", None)
_AST_INDEX = getattr(ast, "Index", None)


class _Findings(object):
    """Нарушения и предупреждения hygiene без повторов."""

    def __init__(self):
        self.violations = []  # type: List[Dict[str, Any]]
        self.warnings = []  # type: List[Dict[str, Any]]
        self._seen = set()  # type: Set[Tuple[str, str, Any, str]]

    def add(self, rule, rel, line, detail, warning=False):
        key = (rule, rel, line, detail)
        if key in self._seen:
            return
        self._seen.add(key)
        item = {"rule": rule, "file": rel, "line": line, "detail": detail}
        (self.warnings if warning else self.violations).append(item)


def _dotted(node):
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


class _Names(object):
    """Разрешение локальных имён в полные (по импортам файла)."""

    def __init__(self, tree):
        self.mods = {}  # type: Dict[str, str]
        self.froms = {}  # type: Dict[str, Tuple[str, str]]
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    if a.asname:
                        self.mods[a.asname] = a.name
                    else:
                        head = a.name.split(".")[0]
                        self.mods[head] = head
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                for a in node.names:
                    self.froms[a.asname or a.name] = (node.module, a.name)

    def full(self, node):
        name = _dotted(node)
        if not name:
            return None
        head, _, rest = name.partition(".")
        if head in self.froms:
            m, n = self.froms[head]
            base = m + "." + n
        elif head in self.mods:
            base = self.mods[head]
        else:
            base = head
        return base + ("." + rest if rest else "")


def _const_str(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _line(node):
    return getattr(node, "lineno", None)


def _imported_modules(tree, names):
    """(полное имя модуля, строка) для import/from/importlib.import_module/__import__ с константой."""
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                out.append((a.name, node.lineno))
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            out.append((node.module, node.lineno))
        elif isinstance(node, ast.Call) and node.args:
            fn = names.full(node.func)
            if fn in ("importlib.import_module", "__import__"):
                s = _const_str(node.args[0])
                if s:
                    out.append((s, node.lineno))
    return out


def _annotation_ids(tree):
    ids = set()  # type: Set[int]

    def mark(n):
        if n is not None:
            for sub in ast.walk(n):
                ids.add(id(sub))

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            a = node.args
            allargs = list(getattr(a, "posonlyargs", [])) + list(a.args) + list(a.kwonlyargs) + [a.vararg, a.kwarg]
            for arg in allargs:
                if arg is not None:
                    mark(arg.annotation)
            mark(node.returns)
        elif isinstance(node, ast.AnnAssign):
            mark(node.annotation)
    return ids


def _has_future_annotations(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "__future__":
            for a in node.names:
                if a.name == "annotations":
                    return True
    return False


def _is_dotted_name(n):
    while isinstance(n, ast.Attribute):
        n = n.value
    return isinstance(n, ast.Name)


def _typeish(n):
    if isinstance(n, ast.Name):
        return n.id in TYPEISH_NAMES
    if isinstance(n, ast.Constant):
        return n.value is None
    if isinstance(n, ast.BinOp) and isinstance(n.op, ast.BitOr):
        return _typeish(n.left) and _typeish(n.right)
    return False


def _dictish(n):
    if isinstance(n, (ast.Dict, ast.DictComp)):
        return True
    return isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "dict"


def _kw_names(call):
    return set(k.arg for k in call.keywords if k.arg)


def _quote_of(tok_string):
    i = 0
    while i < len(tok_string) and tok_string[i] not in "'\"":
        i += 1
    s = tok_string[i:]
    if s[:3] in ('"""', "'''"):
        return s[:3]
    return s[:1]


def _quote_conflict(inner, stack):
    """До 3.12 строка внутри выражения f-строки не может закрыть объемлющую: одиночная кавычка того же
    знака конфликтует с одиночной объемлющей, тройная того же знака — с любой."""
    for outer in stack:
        if inner[:1] == outer[:1] and (len(outer) == 1 or len(inner) == 3):
            return True
    return False


def _check_tokens(src, rel, out):
    """Синтаксис, который ast.parse(feature_version=(3, 8)) на 3.12 пропускает: PEP 701 и скобочный with."""
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(src).readline))
    except (tokenize.TokenError, SyntaxError) as e:
        out.add("py38_syntax", rel, None, "tokenize: %s" % (e,))
        return
    if _FSTART is not None:
        stack = []  # type: List[str]
        for t in toks:
            if t.type == _FSTART:
                q = _quote_of(t.string)
                if stack and _quote_conflict(q, stack):
                    out.add("py38_fstring_same_quote", rel, t.start[0], "nested f-string reuses enclosing quote")
                stack.append(q)
            elif t.type == _FEND:
                if stack:
                    stack.pop()
            elif not stack:
                continue
            elif t.type == tokenize.STRING:
                if _quote_conflict(_quote_of(t.string), stack):
                    out.add("py38_fstring_same_quote", rel, t.start[0], "string in f-string expression reuses quote")
                if "\\" in t.string:
                    out.add("py38_fstring_backslash", rel, t.start[0], "backslash in f-string expression")
            elif t.type == _FMID:
                if len(stack) >= 2 and "\\" in t.string:
                    out.add("py38_fstring_backslash", rel, t.start[0], "backslash in nested f-string")
            elif t.type == tokenize.COMMENT:
                out.add("py38_fstring_comment", rel, t.start[0], "comment inside f-string expression")
            elif t.type in (tokenize.NL, tokenize.NEWLINE):
                if any(len(s) == 1 for s in stack):
                    out.add("py38_fstring_newline", rel, t.start[0], "newline inside single-quoted f-string")
    skip = (tokenize.NL, tokenize.NEWLINE, tokenize.COMMENT, tokenize.INDENT, tokenize.DEDENT)
    sig = [t for t in toks if t.type not in skip]
    for i, t in enumerate(sig):
        if not (t.type == tokenize.NAME and t.string == "with"):
            continue
        if i + 1 >= len(sig) or not (sig[i + 1].type == tokenize.OP and sig[i + 1].string == "("):
            continue
        depth = 0
        has_as = False
        k = i + 1
        while k < len(sig):
            s = sig[k]
            if s.type == tokenize.OP and s.string in "([{":
                depth += 1
            elif s.type == tokenize.OP and s.string in ")]}":
                depth -= 1
                if depth == 0:
                    break
            elif depth == 1 and s.type == tokenize.NAME and s.string == "as":
                has_as = True
            k += 1
        if has_as and k + 1 < len(sig) and sig[k + 1].type == tokenize.OP and sig[k + 1].string == ":":
            out.add("py39_paren_with", rel, t.start[0], "parenthesized context managers")


def _check_ast_py38(tree, rel, names, out):
    ann = _annotation_ids(tree)
    future_ann = _has_future_annotations(tree)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            for d in node.decorator_list:
                target = d.func if isinstance(d, ast.Call) else d
                if not _is_dotted_name(target):
                    out.add("py39_relaxed_decorator", rel, _line(d), "decorator expression")
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                va = node.args.vararg
                if va is not None and isinstance(va.annotation, ast.Starred):
                    out.add("py311_star_subscript", rel, _line(node), "*args: *Ts")
        if isinstance(node, ast.Subscript):
            sl = node.slice
            if _AST_INDEX is not None and isinstance(sl, _AST_INDEX):
                sl = sl.value  # Python 3.8
            if isinstance(sl, ast.Tuple) and any(isinstance(e, ast.Starred) for e in sl.elts):
                out.add("py311_star_subscript", rel, _line(node), "a[*b]")
            generic = None
            if isinstance(node.value, ast.Name) and node.value.id in BUILTIN_GENERICS \
                    and node.value.id not in names.froms:
                generic = node.value.id
            else:
                fn = names.full(node.value)
                if fn and (fn in GENERIC_FULL or fn.startswith("collections.abc.")):
                    generic = fn
            if generic and not (future_ann and id(node) in ann):
                out.add("py39_generic_subscript", rel, _line(node), "%s[...]" % generic)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            if id(node) in ann:
                out.add("py310_union_annotation", rel, _line(node), "X | Y annotation")
            elif _typeish(node.left) and _typeish(node.right):
                out.add("py310_union_runtime", rel, _line(node), "X | Y of types")
            if _dictish(node.left) or _dictish(node.right):
                out.add("py39_dict_union", rel, _line(node), "dict | dict")
        if isinstance(node, ast.AugAssign) and isinstance(node.op, ast.BitOr) and _dictish(node.value):
            out.add("py39_dict_union", rel, _line(node), "|= dict")
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mods = []  # type: List[str]
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif node.module and not node.level:
                mods = [node.module]
                for a in node.names:
                    full = node.module + "." + a.name
                    if full in API_FULL:
                        out.add("py39_api", rel, node.lineno, "%s (%s+)" % (full, API_FULL[full]))
                    if a.name == "utcfromtimestamp":
                        out.add("banned_utcfromtimestamp", rel, node.lineno, full)
            for m in mods:
                top = m.split(".")[0]
                if top in API_MODULES:
                    out.add("py39_module", rel, node.lineno, "%s (%s+)" % (m, API_MODULES[top]))
        if isinstance(node, ast.Attribute):
            fn = names.full(node)
            if fn in API_FULL:
                out.add("py39_api", rel, _line(node), "%s (%s+)" % (fn, API_FULL[fn]))
            if node.attr in API_ATTR_ANY:
                out.add("py39_api", rel, _line(node), ".%s (%s+)" % (node.attr, API_ATTR_ANY[node.attr]))
            if node.attr == "utcfromtimestamp":
                out.add("banned_utcfromtimestamp", rel, _line(node), ".utcfromtimestamp")
            if node.attr == "fromisoformat":
                out.add("fromisoformat_semantics", rel, _line(node),
                        "fromisoformat accepts less before 3.11 (no 'Z', no short forms)", warning=True)
        if isinstance(node, ast.Call):
            fn = names.full(node.func) or ""
            last = fn.split(".")[-1] if fn else (node.func.attr if isinstance(node.func, ast.Attribute) else "")
            kws = _kw_names(node)
            if fn == "zip" and "strict" in kws:
                out.add("py310_keyword", rel, _line(node), "zip(strict=)")
            if (fn.startswith("bisect.") or last in ("bisect", "bisect_left", "bisect_right", "insort",
                                                       "insort_left", "insort_right")) and "key" in kws:
                out.add("py310_keyword", rel, _line(node), "bisect/insort key=")
            if last == "dataclass" and kws & set(("slots", "kw_only", "match_args", "weakref_slot")):
                out.add("py310_keyword", rel, _line(node), "dataclass(%s)" % ",".join(sorted(
                    kws & set(("slots", "kw_only", "match_args", "weakref_slot")))))
            if last == "connect" and "autocommit" in kws:
                out.add("py310_keyword", rel, _line(node), "connect(autocommit=) (3.12+)")
            if fn == "logging.basicConfig" and kws & set(("encoding", "errors")):
                out.add("py310_keyword", rel, _line(node), "logging.basicConfig(encoding=/errors=) (3.9+)")
            if fn.startswith("hashlib.") and "usedforsecurity" in kws:
                out.add("py310_keyword", rel, _line(node), "hashlib usedforsecurity= (3.9+)")
            if last == "ArgumentParser" and "exit_on_error" in kws:
                out.add("py310_keyword", rel, _line(node), "ArgumentParser(exit_on_error=) (3.9+)")
            if fn in ("traceback.print_exception", "traceback.format_exception") and len(node.args) == 1 \
                    and not (kws & set(("value", "tb"))):
                out.add("py310_traceback_single_arg", rel, _line(node), fn + "(exc)")
            if last in ("to_bytes", "from_bytes") and len(node.args) < 2 and "byteorder" not in kws:
                out.add("py311_int_bytes_default", rel, _line(node), last + " without byteorder")


def _check_no_delete(tree, rel, names, out):
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            fn = names.full(node)
            if fn in DELETE_FULL:
                out.add("no_delete", rel, _line(node), fn)
            elif node.attr in DELETE_ATTR_ANY:
                out.add("no_delete", rel, _line(node), "." + node.attr)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            for a in node.names:
                if (node.module + "." + a.name) in DELETE_FULL:
                    out.add("no_delete", rel, node.lineno, node.module + "." + a.name)
        elif isinstance(node, ast.Name) and node.id == "TemporaryDirectory":
            out.add("no_delete", rel, _line(node), "TemporaryDirectory")
        if isinstance(node, ast.Call):
            fn = names.full(node.func) or ""
            if fn.split(".")[-1] == "NamedTemporaryFile":
                keep = False
                for k in node.keywords:
                    if k.arg == "delete" and isinstance(k.value, ast.Constant) and k.value.value is False:
                        keep = True
                if not keep:
                    out.add("no_delete", rel, _line(node), "NamedTemporaryFile without delete=False")


def _check_module_isolation(tree, rel, names, out):
    """Только для корневых rental_case*.py: сеть/процессы/окружение/конфиги, SQL новее 3.9, К4-C38."""
    for mod, line in _imported_modules(tree, names):
        top = mod.split(".")[0]
        if top in NET_PROC_MODULES:
            out.add("module_net_proc_import", rel, line, mod)
        if top in CONFIG_MODULES:
            out.add("module_config_import", rel, line, mod)
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            fn = names.full(node) or ""
            if fn in ENV_FULL:
                out.add("module_env", rel, _line(node), fn)
            if fn in PROC_FULL or fn.startswith("os.spawn") or fn.startswith("os.exec"):
                out.add("module_proc_call", rel, _line(node), fn)
        elif isinstance(node, ast.ImportFrom) and node.module == "os":
            for a in node.names:
                full = "os." + a.name
                if full in ENV_FULL:
                    out.add("module_env", rel, node.lineno, full)
                if full in PROC_FULL or a.name.startswith("spawn") or a.name.startswith("exec"):
                    out.add("module_proc_call", rel, node.lineno, full)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if SQL_LOOKS_RE.search(node.value):
                for title, rx in SQL_NEWER:
                    if rx.search(node.value):
                        out.add("sqlite_newer_than_3_9", rel, _line(node), title)
            for tn in TECH_NAMES:
                if tn in node.value:
                    out.add("tech_timeout_name", rel, _line(node), tn + " in string")
        if isinstance(node, ast.Call) and node.args and names.full(node.func) in LITERAL_PATH_CALLS:
            lit = _const_str(node.args[0])
            if lit is not None and lit != ":memory:":
                out.add("module_literal_path", rel, _line(node), "%s(%r)" % (names.full(node.func), lit[:60]))
        if isinstance(node, ast.Name) and node.id in TECH_NAMES:
            out.add("tech_timeout_name", rel, _line(node), node.id)
        elif isinstance(node, ast.Attribute) and node.attr in TECH_NAMES:
            out.add("tech_timeout_name", rel, _line(node), node.attr)
        elif isinstance(node, ast.arg) and node.arg in TECH_NAMES:
            out.add("tech_timeout_name", rel, _line(node), node.arg)
        elif isinstance(node, ast.keyword) and node.arg in TECH_NAMES:
            out.add("tech_timeout_name", rel, _line(node.value), node.arg)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name in TECH_NAMES:
            out.add("tech_timeout_name", rel, node.lineno, node.name)


def _str_text(node):
    """Строковая часть выражения, как её увидит исполнение: константа; f-строка и сложение строк «+» — склейка
    частей, подставляемое значение — «?». Не строка — None."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(v.value if isinstance(v, ast.Constant) and isinstance(v.value, str) else "?"
                       for v in node.values)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _str_text(node.left), _str_text(node.right)
        if left is None and right is None:
            return None
        return (left if left is not None else "?") + (right if right is not None else "?")
    return None


def _check_sql_newer_tests(tree, rel, out):
    """Файлы tests/*rental_case*.py (К4-C19): SQL новее SQLite 3.9 — тот же признак строки SQL (SQL_LOOKS_RE) и тот
    же перечень SQL_NEWER, что у модулей. Судятся каждая строковая константа, каждая f-строка и каждая наибольшая
    цепочка сложения строк (подвыражение цепочки отдельно не судится — одна находка на цепочку)."""
    inner = set()  # type: Set[int]
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            for side in (node.left, node.right):
                if isinstance(side, ast.BinOp) and isinstance(side.op, ast.Add):
                    inner.add(id(side))
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and (not isinstance(node.op, ast.Add) or id(node) in inner):
            continue
        if not isinstance(node, (ast.Constant, ast.JoinedStr, ast.BinOp)):
            continue
        text = _str_text(node)
        if text and SQL_LOOKS_RE.search(text):
            for title, rx in SQL_NEWER:
                if rx.search(text):
                    out.add("sqlite_newer_than_3_9", rel, _line(node), title)


def _check_sql_writes_text(src, rel, out):
    """Текстом по всему файлу (как grep, вместе с комментариями): SQL записи rc_* вне rental_case.py."""
    for rx in (SQL_WRITE_RE, SQL_DDL_ON_RE):
        for m in rx.finditer(src):
            line = src.count("\n", 0, m.start()) + 1
            out.add("sql_write_outside_store", rel, line, " ".join(m.group(0).split())[:80])


def _imports_fakes(tree, names):
    for mod, _line_no in _imported_modules(tree, names):
        if mod.split(".")[-1] == "rental_case_fakes":
            return True
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for a in node.names:
                if a.name == "rental_case_fakes":
                    return True
    return False


def _patches_socket(tree, names):
    for node in ast.walk(tree):
        targets = []  # type: List[Any]
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
            targets = [node.target]
        for t in targets:
            if isinstance(t, ast.Attribute) and t.attr == "socket" and names.full(t.value) == "socket":
                return True
        if isinstance(node, ast.Call):
            fn = names.full(node.func) or ""
            last = fn.split(".")[-1]
            if last == "setattr" and len(node.args) >= 2 and names.full(node.args[0]) == "socket" \
                    and _const_str(node.args[1]) == "socket":
                return True
            if last == "patch" and node.args and _const_str(node.args[0]) == "socket.socket":
                return True
            if fn.endswith("patch.object") and len(node.args) >= 2 and names.full(node.args[0]) == "socket" \
                    and _const_str(node.args[1]) == "socket":
                return True
    return False


def hygiene_main(root):
    root = _norm(root)
    out = _Findings()
    files = {}  # type: Dict[str, str]
    read_errors = 0
    missing = [r for r in HYGIENE_REQUIRED if not os.path.isfile(os.path.join(root, r))]
    for r in missing:
        out.add("missing_required", r, None, "required file absent")
    modules = sorted(glob.glob(os.path.join(root, "rental_case*.py")))
    tests = sorted(glob.glob(os.path.join(root, "tests", "*rental_case*.py")))
    print("hygiene root: %s" % root)
    print("checked: %d module(s) rental_case*.py, %d file(s) tests/*rental_case*.py" % (len(modules), len(tests)))
    for path in modules + tests:
        rel = _rel(path, root)
        is_module = "/" not in rel
        try:
            with open(path, "rb") as f:
                data = f.read()
        except OSError as e:
            read_errors += 1
            out.add("not_utf8", rel, None, "cannot read: %s" % (e,))
            continue
        files[rel] = hashlib.sha256(data).hexdigest()
        if b"\r" in data:
            first = data[:data.index(b"\r")].count(b"\n") + 1
            out.add("crlf", rel, first, "%d CR byte(s)" % data.count(b"\r"))
        try:
            src = data.decode("utf-8")
        except UnicodeDecodeError as e:
            out.add("not_utf8", rel, None, str(e))
            continue
        if src.startswith("\ufeff"):
            out.add("utf8_bom", rel, 1, "UTF-8 BOM", warning=True)
            src = src[1:]
        if is_module and os.path.basename(path) != "rental_case.py":
            _check_sql_writes_text(src, rel, out)
        try:
            tree = ast.parse(src, filename=rel, feature_version=(3, 8))
        except SyntaxError as e:
            out.add("py38_syntax", rel, e.lineno, str(e.msg))
            continue
        names = _Names(tree)
        _check_tokens(src, rel, out)
        _check_ast_py38(tree, rel, names, out)
        _check_no_delete(tree, rel, names, out)
        if is_module:
            _check_module_isolation(tree, rel, names, out)
        elif rel != RUNNER_REL:
            _check_sql_newer_tests(tree, rel, out)
        base = os.path.basename(path)
        if is_module is False and (base.startswith("test_rental_case_") or base == "rental_case_demo.py"):
            if not _imports_fakes(tree, names):
                out.add("net_guard_import", rel, None, "does not import rental_case_fakes")
        if rel == "tests/rental_case_fakes.py" and not _patches_socket(tree, names):
            out.add("fakes_no_socket_patch", rel, None, "no assignment/patch of socket.socket found")
    violations = [v for v in out.violations if v["rule"] != "missing_required"]
    for v in out.violations:
        tag = "MISSING  " if v["rule"] == "missing_required" else "VIOLATION"
        print("%s %-26s %s:%s %s" % (tag, v["rule"], v["file"], v["line"] if v["line"] else "-", v["detail"]))
    for w in out.warnings:
        print("warning   %-26s %s:%s %s" % (w["rule"], w["file"], w["line"] if w["line"] else "-", w["detail"]))
    inventory = {}
    for r in CONTRACT_INVENTORY:
        p = os.path.join(root, r)
        inventory[r] = _sha256_file(p) if os.path.isfile(p) else None
    result = {
        "root": root.replace("\\", "/"),
        "python": sys.version.split()[0],
        "files_checked": len(files),
        "files": files,
        "missing_required": missing,
        "violations": violations,
        "warnings": out.warnings,
        "read_errors": read_errors,
        "rules": [r for r, _ in HYGIENE_RULES],
        "inventory": inventory,
    }
    print("hygiene: files=%d violations=%d missing=%d warnings=%d" % (
        len(files), len(violations), len(missing), len(out.warnings)))
    sys.stdout.write(HYGIENE_MARK + json.dumps(result, ensure_ascii=True, sort_keys=True) + "\n")
    sys.stdout.flush()
    if violations or read_errors:
        return 1
    if missing:
        return EXIT_MISSING
    return 0


# --------------------------------------------------------------------------------------------------
# Раннер
# --------------------------------------------------------------------------------------------------

_WIN_KEEP = ("SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "SYSTEMDRIVE", "PATH", "OS", "NUMBER_OF_PROCESSORS",
             "PROCESSOR_ARCHITECTURE", "PROCESSOR_IDENTIFIER", "PROCESSOR_LEVEL", "PROCESSOR_REVISION")
_POSIX_KEEP = ("PATH", "LANG", "LC_ALL", "LC_CTYPE")


def child_env(tmp_dir):
    """Минимальное окружение набора: белый список системных имён + обязательные значения раннера."""
    keep = _WIN_KEEP if os.name == "nt" else _POSIX_KEEP
    env = {}  # type: Dict[str, str]
    for k in keep:
        v = os.environ.get(k)
        if v is not None:
            env[k] = v
    for k in ("K4_TTMP", "TMP", "TEMP", "TMPDIR", "HOME", "USERPROFILE"):
        env[k] = tmp_dir
    proxies = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY")
    for k in proxies:
        env[k] = PROXY_SINK
    env["NO_PROXY"] = ""
    if os.name != "nt":
        for k in proxies:
            env[k.lower()] = PROXY_SINK
        env["no_proxy"] = ""
    env["PYTHON_DOTENV_DISABLED"] = "1"
    env["ORCH_TEST_MODE"] = "1"
    env["PRETOOL_NOPUSH"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


_RAN_RE = re.compile(r"^Ran (\d+) tests? in ", re.M)
_FAILED_RE = re.compile(r"^FAILED \(([^)]*)\)\s*$", re.M)
_OK_RE = re.compile(r"^OK(?: \(([^)]*)\))?\s*$", re.M)


def parse_unittest(text):
    ran = None  # type: Optional[int]
    for m in _RAN_RE.finditer(text):
        ran = (ran or 0) + int(m.group(1))
    counts = {"failures": None, "errors": None, "skipped": None}  # type: Dict[str, Optional[int]]
    seen_summary = False
    for rx in (_FAILED_RE, _OK_RE):
        for m in rx.finditer(text):
            seen_summary = True
            for part in (m.group(1) or "").split(","):
                k, _, v = part.strip().partition("=")
                k = k.strip()
                if k in ("failures", "errors", "skipped") and v.strip().isdigit():
                    counts[k] = (counts[k] or 0) + int(v.strip())
    if seen_summary:
        for k in ("failures", "errors", "skipped"):
            if counts[k] is None:
                counts[k] = 0
    return ran, counts["failures"], counts["errors"], counts["skipped"]


def _parse_hygiene(text):
    for line in reversed(text.splitlines()):
        if line.startswith(HYGIENE_MARK):
            try:
                return json.loads(line[len(HYGIENE_MARK):])
            except ValueError:
                return None
    return None


def _set_aside(path, stamp, preserved):
    """Отложить существующий файл/каталог переименованием (ничего не удаляется)."""
    if not os.path.lexists(path):
        return
    base, ext = os.path.splitext(path)
    if os.path.isdir(path):
        base, ext = path, ""
    n = 0
    while True:
        cand = "%s.prev-%s%s%s" % (base, stamp, ("-%d" % n) if n else "", ext)
        if not os.path.lexists(cand):
            break
        n += 1
    os.rename(path, cand)
    preserved.append({"from": path.replace("\\", "/"), "to": cand.replace("\\", "/")})


def _write_json(path, obj):
    part = path + ".part"
    with open(part, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, sort_keys=False)
        f.write("\n")
    os.replace(part, path)


def _read_text(path):
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return ""
    return data.decode("utf-8", "replace").replace("\r\n", "\n").replace("\r", "\n")


def _run_child(cmd, cwd, env, log_path, timeout):
    t0 = time.monotonic()
    timed_out = False
    start_error = None
    rc = None  # type: Optional[int]
    with open(log_path, "wb") as logf:
        try:
            proc = subprocess.Popen(cmd, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=logf,
                                    stderr=subprocess.STDOUT)
        except OSError as e:
            start_error = "cannot start: %s" % (e,)
            logf.write(("runner: " + start_error + "\n").encode("utf-8"))
        else:
            try:
                rc = proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                proc.kill()  # только свой подпроцесс набора
                try:
                    rc = proc.wait(timeout=60)
                except subprocess.TimeoutExpired:
                    rc = None
    return rc, timed_out, time.monotonic() - t0, start_error


def _select(only):
    if not only:
        return list(SUITES), []
    wanted = set(only)
    known = set(s["suite"] for s in SUITES) | set(s["group"] for s in SUITES)
    unknown = sorted(wanted - known)
    return [s for s in SUITES if s["suite"] in wanted or s["group"] in wanted], unknown


def run(args):
    root = _norm(args.root) if args.root else os.path.dirname(os.path.dirname(THIS_FILE))
    if not os.path.isdir(root):
        sys.stderr.write("run_rental_case_suites: --root is not a directory: %s\n" % root)
        return 2
    if not args.label or not LABEL_RE.match(args.label):
        sys.stderr.write("run_rental_case_suites: --label is required, pattern %s\n" % LABEL_RE.pattern)
        return 2
    selected, unknown = _select(args.only)
    if unknown or not selected:
        valid = []  # type: List[str]
        for s in SUITES:
            for n in (s["suite"], s["group"]):
                if n not in valid:
                    valid.append(n)
        sys.stderr.write("run_rental_case_suites: unknown --only %s; valid: %s\n" % (unknown, ", ".join(valid)))
        return 2
    if args.timeout <= 0:
        sys.stderr.write("run_rental_case_suites: --timeout must be > 0\n")
        return 2
    runs_base = _norm(args.runs_base) if args.runs_base else _norm(DEFAULT_RUNS_BASE)
    if not args.runs_base and not os.path.isdir(os.path.dirname(runs_base)):
        sys.stderr.write("run_rental_case_suites: default runs base parent missing (%s); pass --runs-base\n"
                         % os.path.dirname(runs_base))
        return 2

    run_dir = os.path.join(runs_base, args.label)
    tmp_dir = os.path.join(run_dir, "tmp")
    logs_dir = os.path.join(run_dir, "logs")
    trace_dir = _norm(args.trace_dir) if args.trace_dir else os.path.join(run_dir, "trace")
    trace_path = os.path.join(trace_dir, TRACE_NAME)
    results_path = os.path.join(run_dir, "results.json")
    started = _utc_now()
    stamp = started.strftime("%Y%m%d-%H%M%S")
    preserved = []  # type: List[Dict[str, str]]

    os.makedirs(run_dir, exist_ok=True)
    _set_aside(results_path, stamp, preserved)
    _set_aside(logs_dir, stamp, preserved)
    for d in (tmp_dir, logs_dir, trace_dir):
        os.makedirs(d, exist_ok=True)
    env = child_env(tmp_dir)
    env_set = dict((k, v) for k, v in env.items() if k not in _WIN_KEEP and k not in _POSIX_KEEP)

    doc = {
        "schema": "k4-rental-case-suites/1",
        "label": args.label,
        "root": root.replace("\\", "/"),
        "runner": THIS_FILE.replace("\\", "/"),
        "runner_sha256": _sha256_file(THIS_FILE),
        "python": sys.version.split()[0],
        "executable": sys.executable.replace("\\", "/"),
        "platform": sys.platform,
        "started_at": _iso(started),
        "finished_at": None,
        "complete": False,
        "timeout_s": args.timeout,
        "trace_dir": trace_dir.replace("\\", "/"),
        "only": list(args.only or []),
        "env_set": env_set,
        "env_kept_names": sorted(k for k in env if k not in env_set),
        "preserved": preserved,
        "not_run_here": list(NOT_RUN_HERE),
        "suites": [],
        "summary": None,
    }  # type: Dict[str, Any]
    _write_json(results_path, doc)

    trace_set_aside = False
    for spec in selected:
        name = spec["suite"]
        rel_file = spec["file"]
        entry = {
            "suite": name, "group": spec["group"], "kind": spec["kind"], "file": rel_file, "file_sha256": None,
            "cmd": None, "cwd": root.replace("\\", "/"), "exit": None, "status": None, "seconds": 0.0,
            "ran": None, "failures": None, "errors": None, "skipped": None, "note": None,
            "log": None, "tail": [], "artifacts": [],
        }  # type: Dict[str, Any]
        if spec["kind"] == "hygiene":
            cmd = [sys.executable, THIS_FILE, "--hygiene-worker", "--root", root]
        else:
            script = os.path.join(root, rel_file)
            extra = [trace_path if a == "{trace}" else a for a in spec["args"]]
            cmd = [sys.executable, script] + extra
        entry["cmd"] = [c.replace("\\", "/") for c in cmd]

        if rel_file is not None and not os.path.isfile(os.path.join(root, rel_file)):
            entry["status"] = "MISSING"
            entry["note"] = "suite file not found: %s" % rel_file
            doc["suites"].append(entry)
            _print_entry(entry)
            _write_json(results_path, doc)
            continue
        if rel_file is not None:
            entry["file_sha256"] = _sha256_file(os.path.join(root, rel_file))
        if "{trace}" in spec["args"] and not trace_set_aside:
            _set_aside(trace_path, stamp, preserved)  # старый след не выдаёт себя за свежий
            trace_set_aside = True

        log_path = os.path.join(logs_dir, name + ".log")
        entry["log"] = log_path.replace("\\", "/")
        rc, timed_out, secs, start_error = _run_child(cmd, root, env, log_path, args.timeout)
        text = _read_text(log_path)
        entry["exit"] = rc
        entry["seconds"] = round(secs, 3)
        entry["tail"] = text.splitlines()[-TAIL_LINES:]

        if start_error:
            entry["status"] = "FAIL"
            entry["note"] = start_error
        elif timed_out:
            entry["status"] = "TIMEOUT"
            entry["note"] = "killed after %ss" % args.timeout
        elif spec["kind"] == "hygiene":
            h = _parse_hygiene(text)
            if h is not None:
                entry["ran"] = h.get("files_checked")
                entry["failures"] = len(h.get("violations") or [])
                entry["errors"] = h.get("read_errors")
                entry["hygiene"] = h
            if rc == 0 and h is not None:
                entry["status"] = "PASS"
            elif rc == EXIT_MISSING and h is not None:
                entry["status"] = "MISSING"
                entry["note"] = "required files absent: %s" % ", ".join(h.get("missing_required") or [])
            else:
                entry["status"] = "FAIL"
                if h is None:
                    entry["note"] = "hygiene worker gave no result line"
                elif h.get("missing_required"):
                    entry["note"] = "also missing: %s" % ", ".join(h["missing_required"])
        elif spec["kind"] == "unittest":
            ran, fails, errs, skipped = parse_unittest(text)
            entry["ran"], entry["failures"], entry["errors"], entry["skipped"] = ran, fails, errs, skipped
            if rc != 0:
                entry["status"] = "FAIL"
            elif ran is None:
                entry["status"] = "FAIL"
                entry["note"] = "exit 0 but no unittest 'Ran N tests' line"
            elif ran == 0:
                entry["status"] = "FAIL"
                entry["note"] = "exit 0 but 0 tests ran"
            elif (fails or 0) + (errs or 0) > 0:
                entry["status"] = "FAIL"
                entry["note"] = "exit 0 but failures/errors reported"
            else:
                entry["status"] = "PASS"
        else:
            entry["status"] = "PASS" if rc == 0 else "FAIL"
            if "{trace}" in spec["args"]:
                if os.path.isfile(trace_path):
                    with open(trace_path, "rb") as f:
                        tdata = f.read()
                    entry["artifacts"].append({
                        "path": trace_path.replace("\\", "/"),
                        "sha256": hashlib.sha256(tdata).hexdigest(),
                        "lines": tdata.count(b"\n"),
                        "bytes": len(tdata),
                    })
                elif rc == 0:
                    entry["status"] = "FAIL"
                    entry["note"] = "exit 0 but trace not written: %s" % trace_path.replace("\\", "/")
        doc["suites"].append(entry)
        _print_entry(entry)
        _write_json(results_path, doc)

    counts = {"PASS": 0, "FAIL": 0, "MISSING": 0, "TIMEOUT": 0}
    for e in doc["suites"]:
        counts[e["status"]] = counts.get(e["status"], 0) + 1
    all_pass = bool(doc["suites"]) and counts["PASS"] == len(doc["suites"])
    exit_code = 0 if all_pass else 1
    doc["finished_at"] = _iso(_utc_now())
    doc["complete"] = True
    doc["summary"] = {
        "selected": [e["suite"] for e in doc["suites"]],
        "total": len(doc["suites"]),
        "PASS": counts["PASS"], "FAIL": counts["FAIL"], "MISSING": counts["MISSING"], "TIMEOUT": counts["TIMEOUT"],
        "not_pass": [e["suite"] for e in doc["suites"] if e["status"] != "PASS"],
        "all_pass": all_pass,
        "exit_code": exit_code,
        "results_path": results_path.replace("\\", "/"),
    }
    _write_json(results_path, doc)
    print("results: %s" % results_path.replace("\\", "/"))
    print("K4 suites: total=%d PASS=%d FAIL=%d MISSING=%d TIMEOUT=%d -> exit %d" % (
        len(doc["suites"]), counts["PASS"], counts["FAIL"], counts["MISSING"], counts["TIMEOUT"], exit_code))
    return exit_code


def _print_entry(e):
    def n(v):
        return "-" if v is None else str(v)
    print("%-12s %-8s %8.1fs exit=%s ran=%s fail=%s err=%s%s" % (
        e["suite"], e["status"], e["seconds"], n(e["exit"]), n(e["ran"]), n(e["failures"]), n(e["errors"]),
        ("  [" + e["note"] + "]") if e.get("note") else ""))
    sys.stdout.flush()


def parse_args(argv):
    p = argparse.ArgumentParser(description="K4 rental_case suite runner (see module docstring)")
    p.add_argument("--root", default=None, help="directory with rental_case*.py and tests/ (default: parent of tests/)")
    p.add_argument("--label", default=None, help="run label (required): results go to <runs-base>/<label>/")
    p.add_argument("--only", action="append", default=None, help="suite or group name; repeatable")
    p.add_argument("--trace-dir", default=None, help="where demo_A writes trace_demo.jsonl "
                                                     "(default: <runs-base>/<label>/trace)")
    p.add_argument("--runs-base", default=None, help="default: %s" % DEFAULT_RUNS_BASE)
    p.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_S, help="per-suite timeout, seconds (900)")
    p.add_argument("--hygiene-worker", action="store_true", help=argparse.SUPPRESS)
    return p.parse_args(argv)


def main(argv=None):
    try:
        sys.stdout.reconfigure(errors="backslashreplace")
    except (AttributeError, ValueError):
        pass
    args = parse_args(argv)
    if args.hygiene_worker:
        return hygiene_main(args.root or os.path.dirname(os.path.dirname(THIS_FILE)))
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
