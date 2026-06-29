set shell := ["bash", "-c"]

# Install all dependencies
install:
    curl -LsSf https://astral.sh/uv/install.sh | sh
    source $HOME/.local/bin/env
    uv venv --python 3.9 ~/suzieq-env
    source ~/suzieq-env/bin/activate && uv pip install suzieq==0.24.0

# Patch SuzieQ to remove sudo requirements
patch:
    SUZIEQ_BASE="$HOME/suzieq-env/lib/python3.9/site-packages/suzieq/config/" && cd $$SUZIEQ_BASE && find . -type f -name "*.yml" -exec sed -i 's/sudo //g' {} +
    echo "SuzieQ patched successfully"

# Pull SSH keys from all AS proxy containers
pull-keys:
    cd ~/suzieq && bash pull_keys.sh
    echo "Keys pulled"

# Start the full monitoring stack
start:
    sudo sysctl fs.inotify.max_user_instances=8192
    sudo sysctl fs.inotify.max_user_watches=524288
    sudo chmod 666 /var/run/docker.sock
    sudo docker run -d --name otel-collector --volume /var/run/docker.sock:/var/run/docker.sock --volume ~/mini-internet-observability/otel-config.yml:/etc/otel-config.yml --publish 8889:8889 otel/opentelemetry-collector-contrib:latest --config /etc/otel-config.yml
    sudo docker run -d --name prometheus --publish 9090:9090 --volume ~/prometheus.yml:/etc/prometheus/prometheus.yml prom/prometheus
    sudo docker run -d --name grafana --publish 3000:3000 grafana/grafana
    sudo screen -dmS monitor python3 ~/mini-internet-observability/monitor.py
    echo "Monitoring stack started"

# Run SuzieQ collection for a single AS (usage: just collect 03)
collect AS:
    cd ~/suzieq && source ~/suzieq-env/bin/activate && sq-poller -I inventories/{{AS}}/inventory.yml --run-once=update -c suzieq-cfg.yml

# Check status of monitoring stack
status:
    sudo docker ps | grep -E "otel|prometheus|grafana"
    sudo screen -list

# Stop the monitoring stack
stop:
    sudo docker stop otel-collector prometheus grafana
    sudo docker rm otel-collector prometheus grafana
    sudo screen -X -S monitor quit
