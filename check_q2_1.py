import sys
from suzieq.sqobjects import get_sqobject

def check_q2_1(asn):
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
    bgp_tbl = get_sqobject('bgp')

    routers = {
        'MSP_router': str(X) + '.151.0.1',
        'NYC_router': str(X) + '.152.0.1',
        'BOS_router': str(X) + '.153.0.1',
        'PHY_router': str(X) + '.154.0.1',
        'CHI_router': str(X) + '.155.0.1',
        'ATL_router': str(X) + '.156.0.1',
        'SFO_router': str(X) + '.157.0.1',
        'HOU_router': str(X) + '.158.0.1',
    }

    print("=" * 50)
    print("Q2.1 iBGP Full Mesh - AS " + str(asn))
    print("=" * 50)

    df = bgp_tbl(config_file=cfg).get(namespace=[ns])

    # filter only iBGP sessions (peerAsn == asn)
    ibgp = df[df['peerAsn'] == asn]

    print("\n[Check 1] All routers have iBGP data:")
    for router in routers:
        check(router + " has BGP data", router in ibgp['hostname'].values)

    print("\n[Check 2] Every router has exactly 7 iBGP sessions:")
    for router in routers:
        router_sessions = ibgp[ibgp['hostname'] == router]
        num_sessions = len(router_sessions)
        check(router + " has 7 iBGP sessions (got " + str(num_sessions) + ")", num_sessions == 7)

    print("\n[Check 3] All iBGP sessions are Established:")
    for router in routers:
        router_sessions = ibgp[ibgp['hostname'] == router]
        for _, row in router_sessions.iterrows():
            peer = row['peerHostname'] if 'peerHostname' in row and row['peerHostname'] else row['peer']
            check(router + " session with " + str(peer) + " is Established",
                  row['state'] == 'Established')

    print("\n[Check 4] Sessions use loopback addresses:")
    for router, loopback in routers.items():
        router_sessions = ibgp[ibgp['hostname'] == router]
        for peer_router, peer_loopback in routers.items():
            if peer_router != router:
                session = router_sessions[router_sessions['peer'] == peer_loopback]
                check(router + " peers with " + peer_router + " via loopback",
                      len(session) > 0)

    print("\n" + "=" * 50)
    print("Results: " + str(passed) + " passed, " + str(failed) + " failed")
    if failed == 0:
        print("Q2.1 PASSED")
    else:
        print("Q2.1 FAILED - failed checks:")
        for r in results:
            if 'FAIL' in r:
                print(r)
    print("=" * 50)

if __name__ == "__main__":
    asn = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    check_q2_1(asn)
