import socket
import subprocess
import sys

domain = "turbophuket.com"
wa_domain = "wa.turbophuket.com"

results = {}

# Try using Python's socket for A records
try:
    a_records = socket.getaddrinfo(domain, None, socket.AF_INET)
    ips = list(set(r[4][0] for r in a_records))
    results["A_main"] = ips
except Exception as e:
    results["A_main_err"] = str(e)

try:
    a_records_wa = socket.getaddrinfo(wa_domain, None, socket.AF_INET)
    ips_wa = list(set(r[4][0] for r in a_records_wa))
    results["A_wa"] = ips_wa
except Exception as e:
    results["A_wa_err"] = str(e)

# Try dnspython if available
try:
    import dns.resolver
    resolver = dns.resolver.Resolver()

    ns_records = []
    for ns in resolver.resolve(domain, "NS"):
        ns_records.append(str(ns))
    results["NS"] = ns_records

    a_recs = []
    for a in resolver.resolve(domain, "A"):
        a_recs.append(str(a))
    results["A_dns"] = a_recs

    try:
        wa_recs = []
        for a in resolver.resolve(wa_domain, "A"):
            wa_recs.append(str(a))
        results["A_wa_dns"] = wa_recs
    except Exception as e:
        results["A_wa_dns_err"] = str(e)

except ImportError:
    results["dnspython"] = "not installed"
except Exception as e:
    results["dns_err"] = str(e)

for k, v in results.items():
    print(f"{k}: {v}")
