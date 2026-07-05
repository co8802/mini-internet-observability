import pandas as pd
import glob
import sys
import ipaddress

def check_q1_1(asn):
    ns = "as-{:02d}".format(asn)
    X = asn
    results = []
    passed = 0
    failed = 0

    def check(name, condition):
        nonlocal passed, failed
        if condition:
            results.append("  PASS: " + name)
            passed += 1
        else:
            results.append("  FAIL: " + name)
            failed += 1

    files = glob.glob('./parquet/interfaces/**/*.parquet', recursive=True)
    files = [f for f in files if 'namespace=' + ns in f and 'ATL_router' in f]

    if not files:
        print("No interface data found for " + ns)
        return

    dfs = [pd.read_parquet(f) for f in files]
    ifaces = pd.concat(dfs)

    admin_net = ipaddress.IPv4Network(str(X) + '.200.0.0/24')
    patient_net = ipaddress.IPv4Network(str(X) + '.200.1.0/24')

    print("=" * 50)
    print("Q1.1 L2 DCS Verification - AS " + str(asn))
    print("=" * 50)

    print("\n[Check 1] ATL VLAN interfaces exist and are up:")
    atl_l2_10 = ifaces[ifaces['ifname'] == 'ATL-L2.10']
    atl_l2_20 = ifaces[ifaces['ifname'] == 'ATL-L2.20']

    check("ATL-L2.10 exists", len(atl_l2_10) > 0)
    check("ATL-L2.20 exists", len(atl_l2_20) > 0)

    if len(atl_l2_10) > 0:
        check("ATL-L2.10 is up", 'up' in atl_l2_10['state'].values)
    if len(atl_l2_20) > 0:
        check("ATL-L2.20 is up", 'up' in atl_l2_20['state'].values)

    print("\n[Check 2] ATL VLAN interfaces have correct IPs:")

    def has_ip_in_network(df_rows, network):
        for _, row in df_rows.iterrows():
            for ip in row['ipAddressList']:
                try:
                    addr = ipaddress.IPv4Interface(ip).ip
                    if addr in network:
                        return True
                except:
                    pass
        return False

    if len(atl_l2_10) > 0:
        check("ATL-L2.10 has IP in admin subnet (" + str(X) + ".200.0.0/24)", has_ip_in_network(atl_l2_10, admin_net))

    if len(atl_l2_20) > 0:
        check("ATL-L2.20 has IP in patient subnet (" + str(X) + ".200.1.0/24)", has_ip_in_network(atl_l2_20, patient_net))

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
