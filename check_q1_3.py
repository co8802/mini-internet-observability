import pandas as pd
import glob
import sys

def check_q1_3(asn):
    ns = "as-{:02d}".format(asn)
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

    files = glob.glob('./parquet/ospfIf/**/*.parquet', recursive=True)
    files = [f for f in files if 'namespace=' + ns in f]

    if not files:
        print("No ospfIf data found for " + ns)
        return

    dfs = []
    for f in files:
        df = pd.read_parquet(f)
        hostname = f.split('hostname=')[1].split('/')[0]
        df['hostname'] = hostname
        dfs.append(df)

    ospf = pd.concat(dfs)
    ospf = ospf.sort_values('timestamp')

    print("=" * 50)
    print("Q1.3 OSPF Load Balancing Verification - AS " + str(asn))
    print("=" * 50)
    print("\nChecking OSPF costs for 3 equal-cost paths between ATL and BOS")
    print("Required paths: ATL-BOS, ATL-PHY-BOS, ATL-PHY-NYC-BOS (all cost 5)")

    def get_cost(hostname, ifname):
        rows = ospf[(ospf['hostname'] == hostname) & (ospf['ifname'] == ifname)]
        if len(rows) == 0:
            return None
        return int(rows.iloc[-1]['cost'])

    print("\n[Check 1] ATL interface costs:")
    atl_bos_cost = get_cost('ATL_router', 'port_BOS')
    atl_phy_cost = get_cost('ATL_router', 'port_PHY')
    check("ATL port_BOS cost = 5 (got " + str(atl_bos_cost) + ")", atl_bos_cost == 5)
    check("ATL port_PHY cost = 2 (got " + str(atl_phy_cost) + ")", atl_phy_cost == 2)

    print("\n[Check 2] PHY interface costs:")
    phy_bos_cost = get_cost('PHY_router', 'port_BOS')
    phy_nyc_cost = get_cost('PHY_router', 'port_NYC')
    check("PHY port_BOS cost = 3 (got " + str(phy_bos_cost) + ")", phy_bos_cost == 3)
    check("PHY port_NYC cost = 2 (got " + str(phy_nyc_cost) + ")", phy_nyc_cost == 2)

    print("\n[Check 3] NYC interface costs:")
    nyc_bos_cost = get_cost('NYC_router', 'port_BOS')
    check("NYC port_BOS cost = 1 (got " + str(nyc_bos_cost) + ")", nyc_bos_cost == 1)

    print("\n[Check 4] BOS interface costs:")
    bos_phy_cost = get_cost('BOS_router', 'port_PHY')
    bos_nyc_cost = get_cost('BOS_router', 'port_NYC')
    check("BOS port_PHY cost = 3 (got " + str(bos_phy_cost) + ")", bos_phy_cost == 3)
    check("BOS port_NYC cost = 1 (got " + str(bos_nyc_cost) + ")", bos_nyc_cost == 1)

    print("\n[Check 5] All three paths have equal cost of 5:")
    path1 = atl_bos_cost
    path2 = (atl_phy_cost or 0) + (phy_bos_cost or 0)
    path3 = (atl_phy_cost or 0) + (phy_nyc_cost or 0) + (nyc_bos_cost or 0)
    check("ATL-BOS direct cost = 5 (got " + str(path1) + ")", path1 == 5)
    check("ATL-PHY-BOS cost = 5 (got " + str(path2) + ")", path2 == 5)
    check("ATL-PHY-NYC-BOS cost = 5 (got " + str(path3) + ")", path3 == 5)

    print("\n" + "=" * 50)
    print("Results: " + str(passed) + " passed, " + str(failed) + " failed")
    if failed == 0:
        print("Q1.3 PASSED")
    else:
        print("Q1.3 FAILED - failed checks:")
        for r in results:
            if 'FAIL' in r:
                print(r)
    print("=" * 50)

if __name__ == "__main__":
    asn = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    check_q1_3(asn)
