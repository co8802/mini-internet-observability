import sys
import ipaddress
from suzieq.sqobjects import get_sqobject

def check_q1_1(asn):
    ns = "as-{:02d}".format(asn)
    X = asn
    passed = 0
    failed = 0
    results = []

    def check(name, condition):
        nonlocal passed, failed
        if condition:
            results.append("  PASS: " + name)
            passed += 1
        else:
            results.append("  FAIL: " + name)
            failed += 1

    cfg = './suzieq-cfg.yml'
    iface_tbl = get_sqobject('interface')

    admin_net = ipaddress.IPv4Network(str(X) + '.200.0.0/24')
    patient_net = ipaddress.IPv4Network(str(X) + '.200.1.0/24')

    print("=" * 50)
    print("Q1.1 L2 DCS Verification - AS " + str(asn))
    print("=" * 50)

    df = iface_tbl(config_file=cfg).get(namespace=[ns], hostname=['ATL_router'])

    print("\n[Check 1] ATL VLAN interfaces exist and are up:")
    atl_l2_10 = df[df['ifname'] == 'ATL-L2.10']
    atl_l2_20 = df[df['ifname'] == 'ATL-L2.20']

    check("ATL-L2.10 exists", len(atl_l2_10) > 0)
    check("ATL-L2.20 exists", len(atl_l2_20) > 0)

    if len(atl_l2_10) > 0:
        check("ATL-L2.10 is up", 'up' in atl_l2_10['state'].values)
    if len(atl_l2_20) > 0:
        check("ATL-L2.20 is up", 'up' in atl_l2_20['state'].values)

    print("\n[Check 2] ATL VLAN interfaces have correct IPs:")

    def has_ip_in_network(rows, network):
        for _, row in rows.iterrows():
            for ip in row['ipAddressList']:
                try:
                    addr = ipaddress.IPv4Interface(ip).ip
                    if addr in network:
                        return True
                except:
                    pass
        return False

    if len(atl_l2_10) > 0:
        check("ATL-L2.10 has IP in admin subnet (" + str(X) + ".200.0.0/24)",
              has_ip_in_network(atl_l2_10, admin_net))
    if len(atl_l2_20) > 0:
        check("ATL-L2.20 has IP in patient subnet (" + str(X) + ".200.1.0/24)",
              has_ip_in_network(atl_l2_20, patient_net))

    print("\n" + "=" * 50)
    print("Results: " + str(passed) + " passed, " + str(failed) + " failed")
    if failed == 0:
        print("Q1.1 PASSED")
    else:
        print("Q1.1 FAILED - failed checks:")
        for r in results:
            if 'FAIL' in r:
                print(r)
    print("=" * 50)

if __name__ == "__main__":
    asn = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    check_q1_1(asn)
