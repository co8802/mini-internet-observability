import sys
from suzieq.sqobjects import get_sqobject

def check_q1_3(asn):
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
    path_tbl = get_sqobject('path')

    # ATL loopback to BOS loopback
    src = str(X) + '.156.0.1'
    dest = str(X) + '.153.0.1'

    print("=" * 50)
    print("Q1.3 OSPF Load Balancing - AS " + str(asn))
    print("=" * 50)
    print("\nChecking paths from ATL (" + src + ") to BOS (" + dest + ")")

    try:
        df = path_tbl(config_file=cfg).get(namespace=[ns], src=src, dest=dest)

        num_paths = df['pathid'].nunique()
        print("\nPaths found: " + str(num_paths))
        print(df[['pathid', 'hopCount', 'hostname', 'oif']].to_string())

        check("Exactly 3 equal cost paths exist between ATL and BOS", num_paths == 3)

        # Check path 1 is direct ATL-BOS
        path1 = df[df['pathid'] == 1]
        check("Path 1 is ATL-BOS direct", 
              len(path1) == 2 and 'BOS_router' in path1['hostname'].values)

        # Check path 2 goes through PHY
        path2 = df[df['pathid'] == 2]
        check("Path 2 goes through PHY",
              'PHY_router' in path2['hostname'].values)

        # Check path 3 goes through PHY and NYC
        path3 = df[df['pathid'] == 3]
        check("Path 3 goes through PHY and NYC",
              'PHY_router' in path3['hostname'].values and 
              'NYC_router' in path3['hostname'].values)

    except Exception as e:
        print("Error: " + str(e))
        failed += 1
        results.append("  FAIL: Could not compute paths - " + str(e))

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
