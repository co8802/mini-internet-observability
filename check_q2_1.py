import sys
from suzieq.sqobjects import get_sqobject

# this script checks q2.1, ibgp full mesh
# it makes sure every router has bgp data, has exactly 7 ibgp sessions,
# every session is established, and every session is using the correct
# neighbor's loopback address, not just any loopback

def check_q2_1(asn):
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

    # bgp table holds every bgp session a router has, both internal (ibgp)
    # and external (ebgp) sessions all live in the same table
    bgp_tbl = get_sqobject('bgp')

    # loopback numbering comes straight from the assignment spec
    # router id y gets loopback x.[150+y].0.1, msp is id 1, nyc is id 2, and so on
    # we need both the name and the loopback here since we check who is
    # peering with who specifically, not just "some loopback somewhere"
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

    # pull every bgp session for this group
    df = bgp_tbl(config_file=cfg).get(namespace=[ns])

    # keep only the internal sessions, peerAsn equal to our own asn means
    # the session is to one of our own routers, not an outside as
    ibgp = df[df['peerAsn'] == asn]

    print("\n[Check 1] All routers have iBGP data:")
    # basic sanity check before digging into specifics, does each router
    # show up in the filtered data at all
    for router in routers:
        check(router + " has BGP data", router in ibgp['hostname'].values)

    print("\n[Check 2] Every router has exactly 7 iBGP sessions:")
    # with 8 routers total, a full mesh means every router should be
    # connected to the other 7, this catches any missing pair
    for router in routers:
        router_sessions = ibgp[ibgp['hostname'] == router]
        num_sessions = len(router_sessions)
        check(router + " has 7 iBGP sessions (got " + str(num_sessions) + ")", num_sessions == 7)

    print("\n[Check 3] All iBGP sessions are Established:")
    # established means the bgp handshake actually completed and the
    # session is live, not stuck connecting or idle
    for router in routers:
        router_sessions = ibgp[ibgp['hostname'] == router]
        for _, row in router_sessions.iterrows():
            # try to label the check with the neighbor's hostname if we know it,
            # otherwise fall back to just showing the peer ip
            peer = row['peerHostname'] if 'peerHostname' in row and row['peerHostname'] else row['peer']
            check(router + " session with " + str(peer) + " is Established",
                  row['state'] == 'Established')

    print("\n[Check 4] Sessions use loopback addresses:")
    # this is the strictest check, for every router we confirm it has a
    # session whose peer ip exactly matches each other router's specific
    # loopback, not just some loopback looking address
    for router, loopback in routers.items():
        router_sessions = ibgp[ibgp['hostname'] == router]
        for peer_router, peer_loopback in routers.items():
            if peer_router != router:
                session = router_sessions[router_sessions['peer'] == peer_loopback]
                check(router + " peers with " + peer_router + " via loopback",
                      len(session) > 0)

    # print the final tally and, if anything failed, list exactly what failed
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
    # default to group 3 if no group number is passed in
    asn = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    check_q2_1(asn)
