import urllib.request
import json

def doh_query(name, qtype):
    url = f"https://cloudflare-dns.com/dns-query?name={name}&type={qtype}"
    req = urllib.request.Request(url, headers={"Accept": "application/dns-json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            return data
    except Exception as e:
        return {"error": str(e)}

# NS records
print("=== NS turbophuket.com ===")
ns_data = doh_query("turbophuket.com", "NS")
if "Answer" in ns_data:
    for rec in ns_data["Answer"]:
        print(f"  {rec.get('data','')}")
elif "Authority" in ns_data:
    for rec in ns_data["Authority"]:
        print(f"  AUTH: {rec.get('data','')}")
else:
    print(f"  Status={ns_data.get('Status')}, error={ns_data.get('error','')}")

# A records main
print("=== A turbophuket.com ===")
a_data = doh_query("turbophuket.com", "A")
if "Answer" in a_data:
    for rec in a_data["Answer"]:
        if rec.get("type") == 1:
            print(f"  {rec.get('data','')}")
else:
    print(f"  Status={a_data.get('Status')}, error={a_data.get('error','')}")

# A records wa.
print("=== A wa.turbophuket.com ===")
wa_data = doh_query("wa.turbophuket.com", "A")
status = wa_data.get("Status")
if "Answer" in wa_data:
    for rec in wa_data["Answer"]:
        if rec.get("type") == 1:
            print(f"  {rec.get('data','')}")
        elif rec.get("type") == 5:
            print(f"  CNAME -> {rec.get('data','')}")
elif status == 3:
    print("  NXDOMAIN (субдомен не существует)")
else:
    print(f"  Status={status}, error={wa_data.get('error','')}")
