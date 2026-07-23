#!/usr/bin/env python3
"""Аудит 216/шаг5: read-only сканирование ядовитых литералов в промптах/тестах/scratchpad.
Список токенов берётся ПРОГРАММНО из pretool_guard — без литералов в этом файле.
Классифицирует контекст: в тройных кавычках (промпт?), обычная строка, комментарий, код.
"""
import sys, os, re, glob, tokenize, io, ast

PROJECT = '/root/turbobaby-manager-bot'
sys.path.insert(0, PROJECT)
from pretool_guard import RED_TOKEN_HIT

TOKENS = list(RED_TOKEN_HIT.keys())

# ─── Файлы для сканирования ────────────────────────────────────────────────
def scan_targets():
    targets = []
    # Промпты/преамбулы основных модулей обоих театров
    core = [
        'orchestrator_daemon.py',  # APPROVAL_PREAMBLE, decomposer, curator, selfheal, pc
        'prompts.py',
        'claude_client.py',
        'devbot.py',
        'splinter.py',
        'bot.py',
        'bridge_client.py',
        'auditor.py',
    ]
    for name in core:
        p = os.path.join(PROJECT, name)
        if os.path.exists(p):
            targets.append(('core', p))
    # tests/
    for f in sorted(glob.glob(os.path.join(PROJECT, 'tests', '*.py'))):
        targets.append(('test', f))
    # scratchpad _*.py (все)
    for f in sorted(glob.glob(os.path.join(PROJECT, '_*.py'))):
        targets.append(('scratch', f))
    return targets


# ─── Классификация контекста строки ────────────────────────────────────────
_TRIPLE_Q_OPEN = re.compile(r'"""|\'\'\''  )

def classify_lines(text):
    """Для каждой строки → контекст: 'tripleq'(промпт?), 'comment', 'string', 'code'."""
    ctx = []
    in_triple = False
    triple_char = None
    for line in text.splitlines(keepends=True):
        # Отслеживаем тройные кавычки (упрощённо, без экранирования — достаточно для аудита)
        stripped = line.strip()
        if in_triple:
            ctx.append('tripleq')
            if triple_char in line:
                in_triple = False
            continue
        if stripped.startswith('#'):
            ctx.append('comment')
            continue
        m = _TRIPLE_Q_OPEN.search(line)
        if m:
            triple_char = m.group(0)
            # Проверяем, закрывается ли на той же строке
            rest = line[m.start() + 3:]
            if triple_char in rest:
                ctx.append('tripleq_inline')
            else:
                in_triple = True
                ctx.append('tripleq')
            continue
        # Обычная строка с кавычками?
        if '"' in stripped or "'" in stripped:
            ctx.append('string')
        else:
            ctx.append('code')
    return ctx


# ─── Основной скан ─────────────────────────────────────────────────────────
findings = []

for cat, fpath in scan_targets():
    try:
        with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
            text = f.read()
    except Exception as e:
        findings.append({
            'cat': cat, 'file': os.path.relpath(fpath, PROJECT),
            'error': str(e), 'line': 0, 'token': '', 'ctx': 'error', 'text': '',
        })
        continue

    lines = text.splitlines()
    ctx_by_line = classify_lines(text)

    for lineno_0, line in enumerate(lines):
        lineno = lineno_0 + 1
        ctx = ctx_by_line[lineno_0] if lineno_0 < len(ctx_by_line) else 'code'
        for tok in TOKENS:
            if tok in line:
                findings.append({
                    'cat': cat,
                    'file': os.path.relpath(fpath, PROJECT),
                    'line': lineno,
                    'token': tok,
                    'ctx': ctx,
                    'text': line.rstrip()[:200],
                })


# ─── Вывод ─────────────────────────────────────────────────────────────────
by_file = {}
for f in findings:
    by_file.setdefault(f['file'], []).append(f)

total = len(findings)
n_files = len(by_file)

# Категория риска
def risk(h):
    if h.get('error'):
        return 'err'
    if h['ctx'] in ('tripleq', 'string', 'tripleq_inline'):
        return 'HIGH'   # в строке/промпте — может попасть в headless-ввод
    if h['ctx'] == 'code':
        return 'MED'    # в коде — может выполниться
    return 'LOW'        # comment

high = [h for h in findings if risk(h) == 'HIGH']
med  = [h for h in findings if risk(h) == 'MED']
low  = [h for h in findings if risk(h) == 'LOW']

print(f"\n=== АУДИТ 216/шаг5: {total} совпадений в {n_files} файлах ===")
print(f"  🔴 HIGH (в строках/промптах):   {len(high)}")
print(f"  🟠 MED  (в коде):               {len(med)}")
print(f"  🟡 LOW  (в комментариях):        {len(low)}")
print()

# Группировка по категории файла
for section_cat, section_label in [('core', '── CORE (промпты/театры)'), ('test', '── TESTS'), ('scratch', '── SCRATCHPAD (_*.py)')]:
    section_hits = {k: v for k, v in by_file.items() if (v[0]['cat'] == section_cat if v else False)}
    if not section_hits:
        print(f"{section_label}: 0 файлов с совпадениями\n")
        continue
    section_total = sum(len(v) for v in section_hits.values())
    print(f"{section_label}: {section_total} совпадений в {len(section_hits)} файлах")
    for fname in sorted(section_hits.keys()):
        hits = section_hits[fname]
        h_cnt = sum(1 for h in hits if risk(h) == 'HIGH')
        m_cnt = sum(1 for h in hits if risk(h) == 'MED')
        l_cnt = sum(1 for h in hits if risk(h) == 'LOW')
        print(f"\n  📁 {fname}  [HIGH:{h_cnt} MED:{m_cnt} LOW:{l_cnt}]")
        for h in sorted(hits, key=lambda x: x['line']):
            if h.get('error'):
                print(f"    [ERR] {h['error']}")
                continue
            r = risk(h)
            badge = '🔴' if r == 'HIGH' else ('🟠' if r == 'MED' else '🟡')
            print(f"    {badge} L{h['line']:5d}  ctx={h['ctx']:<16s}  [{h['token']}]")
            print(f"           {h['text'][:180]}")
    print()

print("=== конец аудита ===\n")
