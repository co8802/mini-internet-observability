import pandas as pd
import glob
import sys

def check_q1_2(asn):
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

    files = glob.glob('./parquet/routes/**/*.parquet', recursive=True)
    files = [f for f in files if 'namespace=' + ns in f]

    if not files:
        print("No routes data found for " + ns)
        return

    dfs = []
    for f in files:
        df = pd.read_parquet(f)
        hostname = f.split('hostname=')[1].split('/')[0]
        df['hostname'] = hostname
        dfs.append(df)

    routes = pd.concat(dfs)
    routes = routes[routes['active'] == True]

    routers = {
        'MSP_router': 1,
        'NYC_router': 2,
        'BOS_router': 3,
        'PHY_router': 4,
        'CHI_router': 5,
        'ATL_router': 6,
        'SFO_router': 7,
        'HOU_router': 8,
    }

    print("=" * 50)
    print("Q1.2 OSPF Verification - AS " + str(asn))
    print("=" * 50)

    print("\n[Check 1] All routers have routing data:")
    for router in routers:
        check(router + " has routing data", router in routes['hostname'].values)

    print("\n[Check 2] Key subnets reachable on all routers:")
    key_subnets = {
        '198.' + str(X) + '.0.0/24': 'DNS server',
        str(X) + '.0.199.0/24': 'Measurement service',
        str(X) + '.200.0.0/24': 'DCS admin subnet',
        str(X) + '.200.1.0/24': 'DCS patient subnet',
    }

    for router in routers:
        router_routes = routes[routes['hostname'] == router]
        all_prefixes = router_routes['prefix'].tolist()
        ospf_prefixes = router_routes[router_routes['protocol'] == 'ospf']['prefix'].tolist()
        for subnet, name in key_subnets.items():
            check(router + " sees " + name + " (" + subnet + ")", subnet in all_prefixes)

    print("\n[Check 3] All loopback addresses visible via OSPF:")
    for router, rid in routers.items():
        loopback = str(X) + '.' + str(150 + rid) + '.0.1/32'
        for other_router in routers:
            if other_router != router:
                other_ospf = routes[(routes['hostname'] == other_router) & (routes['protocol'] == 'ospf')]['prefix'].tolist()
                check(router + " loopback visible from " + other_router, loopback in other_ospf)

    print("\n" + "=" * 50)
    print("Results: " + str(passed) + " passed, " + str(failed) + " failed")
    if failed == 0:
        print("Q1.2 PASSED")
    else:
        print("Q1.2 FAILED - failed checks:")
        for r in results:
            if 'FAIL' in r:
                print(r)
    print("=" * 50)

if __name__ == "__main__":
    asn = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    check_q1_2(asn)
