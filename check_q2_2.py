import sys
import subprocess
import ipaddress
from suzieq.sqobjects import get_sqobject

# this script checks q2.2, ebgp sessions with neighboring ases
# unlike q2.1, this cant be checked by looking at one group alone, since
# the session depends on both sides being configured correctly
# so instead of pulling just one namespace, we pull every ases bgp table
# at once and match each session with its mirror on the other side

# known student-managed groups, sessions to anyone outside this list are
# ta-managed infrastructure or ixps, and shouldnt be graded the same way
# since a student cant control the other side of that link
# note: this list should probably come from kostas eventually, since he'd
# know the actual full roster of active student groups this semester
STUDENT_GROUPS = [3, 4, 5, 6]


def repoll_all_groups():
    # bgp state can go stale fast, we already got burned once by a check
    # failing just because the last poll happened before a session came up
    # so we always repoll every known student group right before checking
    # instead of trusting whatever's already sitting in suzieq
    print("Repolling all student groups before checking, this may take a moment...")
    for g in STUDENT_GROUPS:
        gs = "{:02d}".format(g)
        inv = "inventories/" + gs + "/inventory.yml"
        try:
            subprocess.run(
                ["sq-poller", "-I", inv, "--run-once=update", "-c", "./suzieq-cfg.yml"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120
            )
        except Exception as e:
            print("  Warning: repoll failed for group " + str(g) + ": " + str(e))
    print("Done repolling.\n")


def check_q2_2(asn):
    X = asn
    ns = "as-{:02d}".format(asn)

    passed = 0
    failed = 0
    results = []
    skipped = []

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

    print("=" * 50)
    print("Q2.2 eBGP Sessions - AS " + str(asn))
    print("=" * 50)

    # always get fresh data before checking, stale bgp state is exactly
    # what caused a false failure before
    repoll_all_groups()

    # pull every ases bgp data at once, no namespace filter, this is the
    # "build a table for all ases together" approach
    df = bgp_tbl(config_file=cfg).get()

    # our own external sessions, peerAsn different from our own asn means
    # its an ebgp session to someone outside our own network
    ours = df[(df['namespace'] == ns) & (df['peerAsn'] != asn)]

    # split into sessions to other student groups vs everything else
    # (ta-managed ases, ixps, or other infrastructure we cant grade fairly)
    student_sessions = ours[ours['peerAsn'].isin(STUDENT_GROUPS)]
    other_sessions = ours[~ours['peerAsn'].isin(STUDENT_GROUPS)]

    for _, row in other_sessions.iterrows():
        skipped.append("  SKIPPED (infrastructure, not gradable): " +
                        row['hostname'] + " -> AS" + str(row['peerAsn']) +
                        " (" + str(row['peer']) + ")")

    print("[Check 1] Our side of each eBGP session to another student group:")
    if len(student_sessions) == 0:
        check("AS " + str(asn) + " has at least one eBGP session to another student group", False)
    else:
        for _, row in student_sessions.iterrows():
            label = row['hostname'] + " -> AS" + str(row['peerAsn']) + " (" + str(row['peer']) + ")"
            check(label + " is Established on our side", row['state'] == 'Established')

    print("\n[Check 2] Neighbor's side of each session (cross-checking both views):")
    for _, row in student_sessions.iterrows():
        our_ip = row['peer']
        their_asn = row['peerAsn']
        their_ns = "as-{:02d}".format(their_asn)

        # find the mirror row, someone in the neighbor as whose peer ip
        # is on the same subnet as our own interface (same /24, opposite ip)
        try:
            our_net = ipaddress.IPv4Interface(our_ip + '/24').network
        except:
            continue

        their_side = df[(df['namespace'] == their_ns) & (df['peerAsn'] == asn)]
        mirror = None
        for _, trow in their_side.iterrows():
            try:
                their_net = ipaddress.IPv4Interface(trow['peer'] + '/24').network
                if their_net == our_net:
                    mirror = trow
                    break
            except:
                continue

        label = row['hostname'] + " <-> AS" + str(their_asn)
        if mirror is None:
            check(label + ": neighbor's side of this session found in our data", False)
        else:
            check(label + ": neighbor's side is also Established",
                  mirror['state'] == 'Established')

    if skipped:
        print("\n[Info] Sessions skipped as non-student infrastructure:")
        for s in skipped:
            print(s)

    print("\n" + "=" * 50)
    print("Results: " + str(passed) + " passed, " + str(failed) + " failed")
    if failed == 0:
        print("Q2.2 PASSED")
    else:
        print("Q2.2 FAILED - failed checks:")
        for r in results:
            if 'FAIL' in r:
                print(r)
    print("=" * 50)

if __name__ == "__main__":
    asn = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    check_q2_2(asn)
