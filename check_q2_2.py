import sys
import subprocess
import ipaddress
import re
from suzieq.sqobjects import get_sqobject

STUDENT_GROUPS = [3, 4, 5, 6]

ROUTERS = {
    'MSP_router': 1,
    'NYC_router': 2,
    'BOS_router': 3,
    'PHY_router': 4,
    'CHI_router': 5,
    'ATL_router': 6,
    'SFO_router': 7,
    'HOU_router': 8,
}


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


def get_router_config(group, router_id):
    router_ip = "158." + str(group) + "." + str(9 + router_id) + ".1"
    proxy_port = str(2000 + group)
    cmd = (
        "ssh -p " + proxy_port +
        " -i ~/suzieq/keys/master/id_rsa -o StrictHostKeyChecking=no root@localhost "
        "\"echo 'show running-config' | ssh -o StrictHostKeyChecking=no root@" +
        router_ip + " vtysh\""
    )
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        return result.stdout
    except Exception:
        return None


def find_stray_ospf_networks(config_text):
    ospf_block_match = re.search(r'router ospf.*?(?=\nrouter |\n!\nip |\Z)', config_text, re.DOTALL)
    if not ospf_block_match:
        return []
    ospf_block = ospf_block_match.group(0)
    stray = re.findall(r'network (179\.\S+|180\.\S+)', ospf_block)
    return stray


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

    print("\n[Check 3] No 179./180. subnets leaking into OSPF:")
    for router_name, router_id in ROUTERS.items():
        config = get_router_config(asn, router_id)
        if config is None:
            check(router_name + " OSPF config could be checked", False)
            continue
        stray = find_stray_ospf_networks(config)
        label = router_name + " has no 179./180. subnets in OSPF"
        if stray:
            label += " (found: " + str(stray) + ")"
        check(label, len(stray) == 0)

    print("\n[Info] Prefix advertisement per session (not pass/fail, still waiting on kostas):")
    for _, row in student_sessions.iterrows():
        label = row['hostname'] + " -> AS" + str(row['peerAsn'])
        pfx_tx = row.get('pfxTx', None)
        if pfx_tx == 1:
            print("  " + label + ": sent 1 prefix, own /8 only, looks correct")
        else:
            print("  " + label + ": sent " + str(pfx_tx) +
                  " prefixes, may be expected depending on business relationship, unconfirmed")

    print("\n[Info] next-hop-self on eBGP sessions is checked separately:")
    print("  see check_q2_2_nexthop.py for that, kept in its own file since")
    print("  its explicitly called out as a tip rather than a hard rule.")

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
