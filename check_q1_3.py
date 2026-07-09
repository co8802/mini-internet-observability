import sys
from suzieq.sqobjects import get_sqobject

# this script checks q1.3, ospf load balancing between atl and bos
# it traces every equal cost path between them and confirms there are
# exactly 3, and that each one matches the specific path the assignment asks for

def check_q1_3(asn):
    # turn the group number into suzieq's namespace format, like 3 becomes as-03
    ns = "as-{:02d}".format(asn)
    X = asn

    passed = 0
    failed = 0
    results = []

    # small helper so we dont repeat if/else everywhere
    # just call check("description", true or false) and it logs and counts it
    def check(name, condition):
        nonlocal passed, failed
        if condition:
            results.append("  PASS: " + name)
            passed += 1
        else:
            results.append("  FAIL: " + name)
            failed += 1

    cfg = './suzieq-cfg.yml'

    # path table lets us trace the actual hop by hop route between two addresses
    # this is different from the route table, it walks the real path instead of
    # just listing what a router knows about
    path_tbl = get_sqobject('path')

    # atl loopback to bos loopback, numbering comes from the assignment spec
    # router id y gets loopback x.[150+y].0.1, atl is id 6, bos is id 3
    src = str(X) + '.156.0.1'
    dest = str(X) + '.153.0.1'

    print("=" * 50)
    print("Q1.3 OSPF Load Balancing - AS " + str(asn))
    print("=" * 50)

    print("\nChecking paths from ATL (" + src + ") to BOS (" + dest + ")")

    try:
        # ask suzieq to trace every equal cost path between the two loopbacks
        # each row is one hop, and pathid groups the hops that belong to the same path
        df = path_tbl(config_file=cfg).get(namespace=[ns], src=src, dest=dest)

        # count how many distinct paths came back
        num_paths = df['pathid'].nunique()
        print("\nPaths found: " + str(num_paths))
        print(df[['pathid', 'hopCount', 'hostname', 'oif']].to_string())

        # the main check, the assignment wants exactly 3 equal cost paths, no more no less
        check("Exactly 3 equal cost paths exist between ATL and BOS", num_paths == 3)

        # path 1 should be the direct atl-bos link, just 2 hops with bos as the end
        path1 = df[df['pathid'] == 1]
        check("Path 1 is ATL-BOS direct", 
              len(path1) == 2 and 'BOS_router' in path1['hostname'].values)

        # path 2 should route through phy on the way to bos
        path2 = df[df['pathid'] == 2]
        check("Path 2 goes through PHY",
              'PHY_router' in path2['hostname'].values)

        # path 3 should route through both phy and nyc on the way to bos
        path3 = df[df['pathid'] == 3]
        check("Path 3 goes through PHY and NYC",
              'PHY_router' in path3['hostname'].values and 
              'NYC_router' in path3['hostname'].values)

    except Exception as e:
        # this catches cases where the path query fails entirely, usually because
        # ospf hasnt converged yet and theres no route to the destination at all
        print("Error: " + str(e))
        failed += 1
        results.append("  FAIL: Could not compute paths - " + str(e))

    # print the final tally and, if anything failed, list exactly what failed
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
    # default to group 3 if no group number is passed in
    asn = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    check_q1_3(asn)
