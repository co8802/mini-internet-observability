import sys
from suzieq.sqobjects import get_sqobject

def check_q1_2(asn):
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
    device_tbl = get_sqobject('device')
    route_tbl = get_sqobject('route')

    routers = ['MSP_router', 'NYC_router', 'BOS_router', 'PHY_router',
               'CHI_router', 'ATL_router', 'SFO_router', 'HOU_router']

    print("=" * 50)
    print("Q1.2 OSPF Verification - AS " + str(asn))
    print("=" * 50)

    print("\n[Check 1] All routers have data:")
    devices = device_tbl(config_file=cfg).get(namespace=[ns])
    for router in routers:
        check(router + " has data", router in devices['hostname'].values)

    print("\n[Check 2] Key subnets reachable on all routers:")
    routes_df = route_tbl(config_file=cfg).get(namespace=[ns])

    for router in routers:
        router_routes = routes_df[routes_df['hostname'] == router]['prefix'].tolist()

        check(router + " sees DNS server (198." + str(X) + ".0.0/24)",
              '198.' + str(X) + '.0.0/24' in router_routes)

        check(router + " sees Measurement service (" + str(X) + ".0.199.0/24)",
              str(X) + '.0.199.0/24' in router_routes)

        # Accept either /23 summary or two /24s for DCS
        has_dcs = (str(X) + '.200.0.0/23' in router_routes or
                   (str(X) + '.200.0.0/24' in router_routes and
                    str(X) + '.200.1.0/24' in router_routes))
        check(router + " sees DCS subnets (" + str(X) + ".200.0.0/23 or /24s)", has_dcs)

    print("\n[Check 3] All loopback addresses reachable:")
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

    for router, loopback in loopbacks.items():
        for other_router in routers:
            if other_router != router:
                other_routes = routes_df[routes_df['hostname'] == other_router]['prefix'].tolist()
                check(router + " loopback visible from " + other_router, loopback in other_routes)

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
