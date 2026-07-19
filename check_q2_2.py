import sys                                          # reads the group number typed on the command line
import subprocess                                    # lets us run shell commands, like sq-poller, from python
import ipaddress                                      # helps us do real subnet math to match up sessions
from suzieq.sqobjects import get_sqobject              # suzieq's official way to pull collected network data

# this script checks q2.2, ebgp sessions with neighboring ases, purely
# using live suzieq data, no config parsing involved
#
# it discovers every as suzieq actually has live bgp data for, instead of
# assuming only a fixed set of groups exist, and cross checks both sides
# of each session, since a session showing down could be either side's
# fault, not just checking our own view of it
#
# fixed from an earlier version that also read router configs directly
# via ssh to check for stray 179./180. subnets in ospf. that check is
# gone now, since it was really just checking saved config text, which
# is exactly the kind of thing already handled elsewhere, this version
# sticks purely to live, real time network state

# the groups we actually control and can force a fresh poll for
KNOWN_GROUP_INVENTORIES = [3, 4, 5, 6]


def repoll_known_groups():
    # we can only force a fresh poll for groups whose inventory files we
    # actually have, thats a real operational limit, not a scope choice.
    # everyone else's data is whatever suzieq last collected on its own
    print("Repolling groups we control before checking, this may take a moment...")
    for g in KNOWN_GROUP_INVENTORIES:
        gs = "{:02d}".format(g)                                    # turns 3 into "03" to match suzieq's naming
        inv = "inventories/" + gs + "/inventory.yml"                 # the file telling suzieq how to reach this group
        try:
            subprocess.run(
                ["sq-poller", "-I", inv, "--run-once=update", "-c", "./suzieq-cfg.yml"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120
            )
        except Exception as e:
            # if one group's repoll fails, dont crash the whole script, just warn and keep going
            print("  Warning: repoll failed for group " + str(g) + ": " + str(e))
    print("Done repolling.\n")


def get_all_known_asns(df):
    # discover every asn suzieq genuinely has data for, instead of
    # assuming only a fixed set of groups exist. namespaces look like
    # "as-07", so we just strip the prefix and convert to a number
    namespaces = df['namespace'].unique()   # every unique namespace suzieq returned across all ases
    asns = []
    for ns in namespaces:
        try:
            asns.append(int(ns.replace('as-', '')))   # "as-07" becomes 7
        except ValueError:
            continue   # skip anything that doesnt match the expected as-XX format
    return sorted(asns)


def check_q2_2(asn):
    ns = "as-{:02d}".format(asn)   # our own namespace name, like "as-03"

    passed = 0
    failed = 0
    results = []     # stores every pass/fail line so we can reprint just the failures later
    skipped = []      # stores sessions we genuinely cant verify

    # small helper so we dont repeat if/else everywhere, just call
    # check("description", true_or_false) and it logs and counts it
    def check(name, condition):
        nonlocal passed, failed
        if condition:
            results.append("  PASS: " + name)
            passed += 1
        else:
            results.append("  FAIL: " + name)
            failed += 1

    cfg = './suzieq-cfg.yml'
    bgp_tbl = get_sqobject('bgp')   # gets a handle to suzieq's bgp data table

    print("=" * 50)
    print("Q2.2 eBGP Sessions - AS " + str(asn))
    print("=" * 50)

    repoll_known_groups()   # always start with fresh data for the groups we control

    # pull bgp data for every as suzieq has, no namespace filter at all,
    # this is the "build a table for all ases together" approach that
    # lets us cross check both sides of any session, not just a fixed set
    df = bgp_tbl(config_file=cfg).get()

    all_known_asns = get_all_known_asns(df)   # every asn suzieq actually has live data for right now
    print("ASNs suzieq currently has live data for: " + str(all_known_asns))

    # our own external sessions, peerAsn different from our own asn means
    # its an ebgp session to someone outside our own network
    ours = df[(df['namespace'] == ns) & (df['peerAsn'] != asn)]

    # split into sessions where we can actually verify the other side
    # (suzieq has live data for that asn too) versus ones we genuinely
    # cant cross check because suzieq has no visibility into them at all
    checkable = ours[ours['peerAsn'].isin(all_known_asns)]
    unverifiable = ours[~ours['peerAsn'].isin(all_known_asns)]

    # just record which sessions we're skipping and why, for visibility
    for _, row in unverifiable.iterrows():
        skipped.append("  SKIPPED (suzieq has no live data for this AS): " +
                        row['hostname'] + " -> AS" + str(row['peerAsn']) +
                        " (" + str(row['peer']) + ")")

    print("\n[Check 1] Our side of each eBGP session:")
    if len(checkable) == 0:
        # if there are genuinely zero verifiable sessions, thats worth flagging as its own failure
        check("AS " + str(asn) + " has at least one verifiable eBGP session", False)
    else:
        for _, row in checkable.iterrows():
            label = row['hostname'] + " -> AS" + str(row['peerAsn']) + " (" + str(row['peer']) + ")"
            # just check what our own router thinks about this session
            check(label + " is Established on our side", row['state'] == 'Established')

    print("\n[Check 2] Neighbor's side of each session (cross-checking both views):")
    for _, row in checkable.iterrows():
        our_ip = row['peer']
        their_asn = row['peerAsn']
        their_ns = "as-{:02d}".format(their_asn)

        # figure out what subnet our side of this link is on, so we can
        # find the matching row on their side later
        try:
            our_net = ipaddress.IPv4Interface(our_ip + '/24').network
        except:
            continue   # skip if the ip doesnt parse cleanly for some reason

        # pull the neighbor's own bgp data, specifically their sessions pointed back at us
        their_side = df[(df['namespace'] == their_ns) & (df['peerAsn'] == asn)]

        # look for the row on their side thats on the same subnet as ours,
        # thats the actual mirror of this specific session
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
            # we couldnt even find their side of this session in live data
            check(label + ": neighbor's side of this session found in live data", False)
        else:
            # we found it, now check if they also think its established
            check(label + ": neighbor's side is also Established",
                  mirror['state'] == 'Established')

    # this section just reports information, doesnt affect pass/fail,
    # since we still dont know if this should be scored
    print("\n[Info] Prefix advertisement per session (not scored, for visibility):")
    for _, row in checkable.iterrows():
        label = row['hostname'] + " -> AS" + str(row['peerAsn'])
        pfx_tx = row.get('pfxTx', None)
        if pfx_tx == 1:
            print("  " + label + ": sent 1 prefix, own /8 only, looks correct")
        else:
            print("  " + label + ": sent " + str(pfx_tx) +
                  " prefixes, may be expected depending on business relationship, unconfirmed")

    if skipped:
        print("\n[Info] Sessions we genuinely cannot verify:")
        for s in skipped:
            print(s)

    # print the final tally, and if anything failed, list exactly which checks failed
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
    # default to group 3 if no group number was typed in
    asn = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    check_q2_2(asn)
