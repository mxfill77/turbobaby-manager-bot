"""Read-only: построить перечень удаляемого по правилу владельца (заявка 40).
Правило: удалить из списка орфанов (DONE шаг 7/7 родитель 33) всё СТАРШЕ 7 дней;
ОСТАВИТЬ свежие (mtime за последние 7 дней, вкл. бэкапы 02-03.07) и
.claude/settings*.bak-approve* / *.bak-reclass* (прописанный откат авто-approve)."""
import glob, os, time, datetime, json

ROOT = '/root/turbobaby-manager-bot'
BGS = '/root/turbobaby-bridge-gs'
os.chdir(ROOT)

NOW = time.time()
CUTOFF = NOW - 7 * 86400  # старше 7 дней = mtime до этой отметки
print('cutoff (UTC):', datetime.datetime.utcfromtimestamp(CUTOFF).isoformat())

groups = {
    'хелперы _*.py корня': sorted(glob.glob('_*.py')),
    'хелперы _*.json/_*.jsonl/_*.js': sorted(glob.glob('_*.json') + glob.glob('_*.jsonl') + glob.glob('_*.js')),
    'бэкапы кода/доков в корне (*.bak*)': sorted(glob.glob('*.bak-*') + glob.glob('*.bak')),
    'бэкапы .claude/*.bak*': sorted(glob.glob('.claude/*.bak*')),
    'бэкапы bridge-gs (*.bak*)': sorted(glob.glob(BGS + '/*.bak*')),
}

def keep_reason(path):
    base = os.path.basename(path)
    if path.startswith('.claude/') and ('bak-approve' in base or 'bak-reclass' in base):
        return 'откат авто-approve (CLAUDE.md)'
    if os.path.getmtime(path) >= CUTOFF:
        return 'свежий <7 дней'
    return None

delete, keep = {}, {}
for title, files in groups.items():
    d, k = [], []
    for f in files:
        r = keep_reason(f)
        (k if r else d).append((f, os.path.getsize(f),
                                datetime.datetime.utcfromtimestamp(os.path.getmtime(f)).strftime('%m-%d'),
                                r or ''))
    delete[title], keep[title] = d, k

total_n = total_sz = 0
print('===== УДАЛИТЬ =====')
for title, files in delete.items():
    sz = sum(s for _, s, _, _ in files)
    total_n += len(files); total_sz += sz
    print(f'-- {title}: {len(files)} шт, {sz/1024:.0f} КБ')
    for f, s, d, _ in files:
        print(f'   DEL {f} ({s/1024:.1f} КБ, mtime {d})')
print(f'ИТОГО УДАЛИТЬ: {total_n} файлов, {total_sz/1024:.0f} КБ')
print()
print('===== ОСТАВИТЬ =====')
kn = ksz = 0
for title, files in keep.items():
    if not files:
        continue
    kn += len(files); ksz += sum(s for _, s, _, _ in files)
    print(f'-- {title}: {len(files)} шт')
    for f, s, d, r in files:
        print(f'   KEEP {f} (mtime {d}, {r})')
print(f'ИТОГО ОСТАВИТЬ: {kn} файлов, {ksz/1024:.0f} КБ')

with open('/tmp/orph40_delete_list.json', 'w') as fh:
    json.dump({t: [f for f, _, _, _ in fs] for t, fs in delete.items()}, fh, ensure_ascii=False, indent=1)
print('список сохранён: /tmp/orph40_delete_list.json')
