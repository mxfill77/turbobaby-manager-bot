import os, datetime

db_path = "/root/turbobaby-manager-bot/wa_queue.db"
mtime = os.path.getmtime(db_path)
print("Last modified:", datetime.datetime.utcfromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S UTC"))
print("Size:", os.path.getsize(db_path), "bytes")
