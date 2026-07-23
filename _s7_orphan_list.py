import glob, os

os.chdir('/root/turbobaby-manager-bot')

groups = {
    'хелперы _*.py': sorted(glob.glob('_*.py')),
    'хелперы прочие (_*.json/_*.jsonl/_*.js)': sorted(glob.glob('_*.json') + glob.glob('_*.jsonl') + glob.glob('_*.js')),
    'бэкапы кода/доков в корне (*.bak*)': sorted(glob.glob('*.bak-*') + glob.glob('*.bak')),
    'бэкапы .claude/*.bak*': sorted(glob.glob('.claude/*.bak*')),
}
# _s7_orphan_list.py сам попадёт в хелперы — это честно, он тоже кандидат
total = 0
for title, files in groups.items():
    size = sum(os.path.getsize(f) for f in files)
    total += size
    print(f'== {title}: {len(files)} файлов, {size/1024:.0f} КБ')
    for f in files:
        print(f'   {f} ({os.path.getsize(f)/1024:.1f} КБ)')

print(f'ИТОГО: {sum(len(v) for v in groups.values())} файлов, {total/1024:.0f} КБ')

print()
print('bridge-gs бэкапы:')
for f in sorted(glob.glob('/root/turbobaby-bridge-gs/*.bak*')):
    print(f'   {f} ({os.path.getsize(f)/1024:.1f} КБ)')
