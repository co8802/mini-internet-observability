import sys
from suzieq.sqobjects import get_sqobject

# this script checks q1.2, ospf network-wide
# it makes sure every router has data, can see the important shared subnets,
# and can see every other router's loopback address

def check_q1_2(asn):
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

    # device table tells us which routers suzieq actually has data for
    # route table tells us what prefixes each router knows how to reach
    device_tbl = get_sqobject('device')
    route_tbl = get_sqobject('route')

    # all 8 routers we expect to exist in every group's network
    routers = ['MSP_router', 'NYC_router', 'BOS_router', 'PHY_router',
               'CHI_router', 'ATL_router', 'SFO_router', 'HOU_router']

    print("=" * 50)
    print("Q1.2 OSPF Verification - AS " + str(asn))
    print("=" * 50)

    print("\n[Check 1] All routers have data:")

    # pull the device table and just confirm each of our 8 routers shows up at all
    # if a router is missing here, something is badly wrong before we even check routes
    devices = device_tbl(config_file=cfg).get(namespace=[ns])
    for router in routers:
        check(router + " has data", router in devices['hostname'].values)

    print("\n[Check 2] Key subnets reachable on all routers:")

    # pull the whole routing table once, then filter per router as we go
    routes_df = route_tbl(config_file=cfg).get(namespace=[ns])

    for router in routers:
        # grab just this router's list of known prefixes as plain strings
        router_routes = routes_df[routes_df['hostname'] == router]['prefix'].tolist()

        # dns server lives at msp, every router should be able to route to it
        check(router + " sees DNS server (198." + str(X) + ".0.0/24)",
              '198.' + str(X) + '.0.0/24' in router_routes)

        # measurement service lives at hou, same idea
        check(router + " sees Measurement service (" + str(X) + ".0.199.0/24)",
              str(X) + '.0.199.0/24' in router_routes)

        # dcs subnets can be advertised two ways depending on how the group split it
        # either as one combined /23 block, or as two separate /24 halves
        # the assignment only guarantees the combined /23, so we accept both forms
        has_dcs = (str(X) + '.200.0.0/23' in router_routes or
                   (str(X) + '.200.0.0/24' in router_routes and
                    str(X) + '.200.1.0/24' in router_routes))
        check(router + " sees DCS subnets (" + str(X) + ".200.0.0/23 or /24s)", has_dcs)

    print("\n[Check 3] All loopback addresses reachable:")

    # loopback numbering comes straight from the assignment spec
    # router id y gets loopback x.[150+y].0.1, msp is id 1, nyc is id 2, and so on
    loopbacks = {
        'MSP_router': str(X) + '.151.0.1/32',
        'NYC_router': str(X) + '.152.0.1/32',
        'BOS_router': str(X) + '.153.0.1/32',
        'PHY_router': str(X) + '.154.0.1/32',
        'CHI_router': str(X) + '.155.0.1/32',
        'ATL_router': str(X) + '.156.0.1/32',
        'SFO_router': str(X) + '.157.0.1/32',
        'HOU_router': str(X) + '.158.0.1/32',
    }

    # for every router's loopback, check that every other router can see it
    # this is the real proof that ospf is fully converged network-wide
    # 8 loopbacks times 7 other routers each means 56 checks just from this loop
    for router, loopback in loopbacks.items():
        for other_router in routers:
            if other_router != router:
                other_routes = routes_df[routes_df['hostname'] == other_router]['prefix'].tolist()
                check(router + " loopback visible from " + other_router, loopback in other_routes)

    # print the final tally and, if anything failed, list exactly what failed
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
    # default to group 3 if no group number is passed in
    asn = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    check_q1_2(asn)
