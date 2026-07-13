import sys
import subprocess
import ipaddress
from suzieq.sqobjects import get_sqobject

# this script checks q2.2, ebgp sessions with neighboring ases
#
# check 1: our side of each session is established
# check 2: the neighbor's side agrees, cross-checked directly from their data
#
# check 3 (prefix advertisement) is informational only, not pass/fail.
# spec says only your own /8 should be advertised, but kostas pointed out
# that some leaking is expected depending on business relationship (e.g.
# group3/group4 are peers, so forwarding customer routes to each other is
# expected under gao-rexford). still waiting on a final answer on how this
# should be scored, real grade sheet shows full marks for everyone despite
# every group currently leaking on at least one session
#
# next-hop-self is not implemented, suzieq's nhSelf column is confirmed
# broken (returns False even when next-hop-self is genuinely configured
# per show running-config), would need ssh + config parsing instead

STUDENT_GROUPS = [3, 4, 5, 6]


def repoll_all_groups():
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

    repoll_all_groups()

    df = bgp_tbl(config_file=cfg).get()

    ours = df[(df['namespace'] == ns) & (df['peerAsn'] != asn)]

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

    print("\n[Info] Prefix advertisement per session (not pass/fail, still waiting on kostas):")
    for _, row in student_sessions.iterrows():
        label = row['hostname'] + " -> AS" + str(row['peerAsn'])
        pfx_tx = row.get('pfxTx', None)
        if pfx_tx == 1:
            print("  " + label + ": sent 1 prefix, own /8 only, looks correct")
        else:
            print("  " + label + ": sent " + str(pfx_tx) +
                  " prefixes, may be expected depending on business relationship, unconfirmed")

    print("\n[Info] next-hop-self (not implemented yet):")
    print("  suzieq's nhSelf column is confirmed broken for this deployment.")
    print("  would need ssh + show running-config parsing per router instead.")

    if skipped:
        print("\n[Info] Sessions skipped as non-student infrastructure:")
        for s in skipped:
            print(s)

    print("\n" + "=" * 50)
    print("Results: " + str(passed) + " passed, " + str(failed) + " failed")
    if failed == 0:
        print("Q2.2 PASSED (session-state checks only, see info sections above)")
    else:
        print("Q2.2 FAILED - failed checks:")
        for r in results:
            if 'FAIL' in r:
                print(r)
    print("=" * 50)

if __name__ == "__main__":
    asn = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    check_q2_2(asn)
