import docker
import json
import time
import os
from datetime import datetime, timezone

client = docker.DockerClient(base_url="unix:///var/run/docker.sock")
LOG_FILE = "/home/miniint/container_health.json"
EVENTS_FILE = "/home/miniint/container_events.log"

def parse_container_name(name):
    parts = name.split("_")
    if len(parts) >= 2:
        as_num = parts[0]
        rest = "_".join(parts[1:])
        if rest.endswith("router"):
            router = rest.replace("router", "")
            return {"as": as_num, "role": "router", "display": f"AS{as_num} {router} router"}
        elif rest.endswith("host"):
            host = rest.replace("host", "")
            return {"as": as_num, "role": "host", "display": f"AS{as_num} {host} host"}
        elif rest == "ssh":
            return {"as": as_num, "role": "proxy", "display": f"AS{as_num} proxy"}
        elif rest.startswith("L2"):
            return {"as": as_num, "role": "switch", "display": f"AS{as_num} {rest} switch"}
    return {"as": "unknown", "role": "service", "display": name}

def get_container_status():
    snapshot = {"timestamp": datetime.now(timezone.utc).isoformat(), "containers": {}}
    for container in client.containers.list(all=True):
        name = container.name
        parsed = parse_container_name(name)
        snapshot["containers"][name] = {
            "status": container.status,
            "restart_count": container.attrs["RestartCount"],
            "started_at": container.attrs["State"]["StartedAt"],
            "exit_code": container.attrs["State"]["ExitCode"],
            "healthy": container.status == "running",
            "as": parsed["as"],
            "role": parsed["role"],
            "display": parsed["display"]
        }
    return snapshot

def load_previous():
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r") as f:
            lines = f.readlines()
            if lines:
                return json.loads(lines[-1])
    return None

def log_event(msg):
    with open(EVENTS_FILE, "a") as f:
        f.write(msg + "\n")
    print(msg, flush=True)

def detect_changes(previous, current):
    if previous is None:
        return
    for name, curr in current["containers"].items():
        if name in previous["containers"]:
            prev = previous["containers"][name]
            if prev["status"] != curr["status"]:
                log_event(f"[{current['timestamp']}] STATUS CHANGE: {curr['display']} | {prev['status']} -> {curr['status']}")
            if prev["restart_count"] != curr["restart_count"]:
                log_event(f"[{current['timestamp']}] RESTART: {curr['display']} | total restarts: {curr['restart_count']}")
        else:
            log_event(f"[{current['timestamp']}] NEW CONTAINER: {curr['display']}")

def print_summary(current):
    total = len(current["containers"])
    running = sum(1 for c in current["containers"].values() if c["healthy"])
    down = total - running
    by_role = {}
    for c in current["containers"].values():
        role = c["role"]
        if role not in by_role:
            by_role[role] = {"total": 0, "running": 0}
        by_role[role]["total"] += 1
        if c["healthy"]:
            by_role[role]["running"] += 1
    summary = f"[{current['timestamp']}] {running}/{total} running | "
    summary += " | ".join([f"{role}: {v['running']}/{v['total']}" for role, v in by_role.items()])
    if down > 0:
        down_list = [c["display"] for c in current["containers"].values() if not c["healthy"]]
        summary += f" | DOWN: {', '.join(down_list)}"
    print(summary, flush=True)

def main():
    print("Starting container health monitor - polling every 60s", flush=True)
    while True:
        previous = load_previous()
        current = get_container_status()
        detect_changes(previous, current)
        with open(LOG_FILE, "a") as f:
            f.write(json.dumps(current) + "\n")
        print_summary(current)
        time.sleep(60)

if __name__ == "__main__":
    main()
