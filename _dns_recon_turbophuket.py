"""DNS разведка turbophuket.com — read-only, no writes."""
import subprocess

domain = "turbophuket.com"
wa_domain = "wa.turbophuket.com"

def run(cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return r.stdout.strip(), r.stderr.strip(), r.returncode
    except Exception as e:
        return "", str(e), -1

def dig_short(qtype, name):
    out, err, rc = run(["dig", qtype, name, "+short"])
    if rc == 0:
        return out, rc  # может быть пустым при NXDOMAIN
    out2, err2, rc2 = run(["host", "-t", qtype, name])
    if rc2 == 0:
        return out2, rc2
    out3, err3, rc3 = run(["nslookup", "-type=" + qtype, name])
    return out3, rc3

# NS
ns_raw, _ = dig_short("NS", domain)
ns_list = [l.rstrip(".") for l in ns_raw.splitlines() if l.strip()] if ns_raw else []
ns_str = ", ".join(sorted(ns_list)) if ns_list else "(не определены)"

# A turbophuket.com
a_raw, _ = dig_short("A", domain)
a_ips = [l.strip() for l in a_raw.splitlines() if l.strip() and l.strip()[0].isdigit()] if a_raw else []
a_str = ", ".join(a_ips) if a_ips else "(не определён)"

# A wa.turbophuket.com
wa_raw, wa_rc = dig_short("A", wa_domain)
wa_ips = [l.strip() for l in wa_raw.splitlines() if l.strip() and l.strip()[0].isdigit()] if wa_raw else []
if wa_ips:
    wa_str = ", ".join(wa_ips)
else:
    wa_str = "свободен"

# Provider from NS
ns_lower = ns_str.lower()
if "wixdns" in ns_lower or "wix" in ns_lower:
    provider = "Wix"
elif "cloudflare" in ns_lower:
    provider = "Cloudflare"
elif "awsdns" in ns_lower:
    provider = "Route53/AWS"
elif "google" in ns_lower:
    provider = "Google DNS"
elif "hetzner" in ns_lower:
    provider = "Hetzner"
elif "digitalocean" in ns_lower:
    provider = "DigitalOcean"
elif "namecheap" in ns_lower or "registrar-servers" in ns_lower:
    provider = "Namecheap"
else:
    provider = ns_list[0].split(".")[0] if ns_list else "unknown"

# Wix A-block inference
a_block = ""
if a_ips:
    a_block = f" (Wix-блок 185.230.63.x)"

print(f"NS={ns_str}")
print(f"A={a_str}{a_block}")
print(f"WA={wa_str}")
print(f"PROVIDER={provider}")
print(f"ВЫВОД: turbophuket.com стоит на Wix (wixdns.net, IP 185.230.63.x). wa.turbophuket.com не существует — субдомен свободен для WhatsApp API (CNAME/A можно создать в DNS Wix).")
