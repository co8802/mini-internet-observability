# Mini-Internet Observability

Monitoring and observability stack for the Princeton COS 461 mini-internet networking environment.

## Overview

This repo contains tooling to instrument the mini-internet — a Docker-based simulated network with 10 autonomous systems (AS 1-10) and 178 containers running FRRouting and Open vSwitch.

## Components

### Performance Monitoring
- **cAdvisor** — collects CPU, memory, network, and OOM metrics from all containers
- **Prometheus** — scrapes cAdvisor every 60 seconds and stores metrics as time series
- **Grafana** — visualizes metrics via dashboards
- **monitor.py** — custom Python monitor that tracks container health by AS and role every 60 seconds

### Control Plane Monitoring
- **SuzieQ** — SSHes into every router and switch to collect BGP tables, OSPF state, routing tables, and interface configs

## Setup

### Requirements
- Docker
- Python 3.9
- uv (Python package manager)
- just (task runner)

### Quick Start
cat > justfile << 'EOF'
# Mini-Internet Observability - Task Runner

# Install all dependencies
install:
    curl -LsSf https://astral.sh/uv/install.sh | sh
    source $HOME/.local/bin/env
    uv venv --python 3.9 ~/suzieq-env
    source ~/suzieq-env/bin/activate
    uv pip install suzieq==0.24.0

# Patch SuzieQ to remove sudo requirements
patch:
    SUZIEQ_BASE="$HOME/suzieq-env/lib/python3.9/site-packages/suzieq/config/" && cd $SUZIEQ_BASE && find . -type f -name "*.yml" -exec sed -i 's/sudo //g' {} +
    echo "SuzieQ patched successfully"

# Pull SSH keys from all AS proxy containers and generate inventories
pull-keys:
    cd ~/suzieq && bash pull_keys.sh
    for AS in 01 02 07 08 09 10; do \
        ASN_VAL=$((10#$AS)); \
        mkdir -p inventories/$AS; \
        INV_FILE="inventories/$AS/inventory.yml"; \
        TMP_HOSTS=$(mktemp); \
        while IFS= read -r line || [ -n "$line" ]; do \
            IP=$(echo "$line" | sed "s/{ASN}/${ASN_VAL}/g" | sed 's/,$//'); \
            if [ -n "$IP" ]; then echo "      - url: ssh://root@${IP}" >> "$TMP_HOSTS"; fi; \
        done < templates/ips.csv; \
        sed "s/{ASN}/${AS}/g" templates/inventory.yml | sed "s|keyfile: ./keys/${AS}/id_rsa|keyfile: ./keys/ases/${AS}/id_rsa|g" > "$INV_FILE"; \
        sed -i "/{IP}/r $TMP_HOSTS" "$INV_FILE"; \
        sed -i "/{IP}/d" "$INV_FILE"; \
        rm "$TMP_HOSTS"; \
        echo "Generated inventory for AS $AS"; \
    done

# Start the monitoring stack
start:
    sudo sysctl fs.inotify.max_user_instances=8192
    sudo sysctl fs.inotify.max_user_watches=524288
    sudo docker run -d --name cadvisor \
        --volume /:/rootfs:ro \
        --volume /var/run:/var/run:rw \
        --volume /var/run/docker.sock:/var/run/docker.sock:rw \
        --volume /sys:/sys:ro \
        --volume /var/lib/docker/:/var/lib/docker:ro \
        --publish 8080:8080 \
        gcr.io/cadvisor/cadvisor:latest
    sudo docker run -d --name prometheus \
        --publish 9090:9090 \
        --volume ~/mini-internet-observability/prometheus.yml:/etc/prometheus/prometheus.yml \
        prom/prometheus
    sudo docker run -d --name grafana \
        --publish 3000:3000 \
        grafana/grafana
    sudo screen -dmS monitor python3 ~/mini-internet-observability/monitor.py
    echo "Monitoring stack started"

# Run SuzieQ collection for all ASes
collect:
    cd ~/suzieq && source ~/suzieq-env/bin/activate && \
    for AS in 01 02 03 04 05 06 07 08 09 10; do \
        echo "Collecting AS $AS..."; \
        sq-poller -I inventories/$AS/inventory.yml --run-once=update -c suzieq-cfg.yml 2>/dev/null; \
        echo "Done AS $AS"; \
    done

# Check status of all monitoring components
status:
    sudo docker ps | grep -E "cadvisor|prometheus|grafana"
    sudo screen -list

# Stop the monitoring stack
stop:
    sudo docker stop cadvisor prometheus grafana
    sudo docker rm cadvisor prometheus grafana
    sudo screen -X -S monitor quit
