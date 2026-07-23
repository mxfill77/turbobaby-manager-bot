"""Read-only разведка: достать текст задачи 122 (спека куска 3) из очереди Bridge."""
import bridge_client

b = bridge_client.BridgeClient()
r = b.get_pending("done", lane="all")
if not r.get("ok"):
    print("ERR:", r)
else:
    for it in r.get("items", []):
        if str(it.get("id")) == "122":
            print("FROM:", it.get("from"), "| LANE:", it.get("lane"), "| STATUS:", it.get("status"))
            print("=== TASK_TEXT ===")
            print(it.get("task_text") or it.get("task") or "")
            print("=== RESULT ===")
            print((it.get("result") or "")[:2000])
            break
    else:
        ids = [str(it.get("id")) for it in r.get("items", [])]
        print("122 не найдена среди done. ids:", ids[:60])
