# Monitoring Stack Performance Profile

## Test Environment
- VM: 16 cores, 121GB RAM
- Mini-internet: 178 containers (10 AS downscaled topology)

## Results

### Scrape Duration
- cAdvisor scrape time: 0.39 seconds
- Prometheus polling interval: 60 seconds
- Ratio: 0.65% — well within limits

### CPU and Memory Overhead
| Component  | CPU % | Memory  |
|------------|-------|---------|
| cAdvisor   | 8.53% | 220 MB  |
| Prometheus | 0.19% | 226 MB  |
| Grafana    | 0.38% | 131 MB  |
| **Total**  | **9.1%** | **577 MB** |

### Observations
- cAdvisor dominates CPU usage at 8.53% for 178 containers
- Extrapolating to full 1192 container topology: ~57% CPU for cAdvisor alone
- This confirms scaling concern raised by Kostas beyond 200-300 containers
- Recommendation: switch to OpenTelemetry for better scaling efficiency

### Scrape Interval History
- Original: 15 seconds — caused periodic memory spikes up to 1.2GB
- Current: 60 seconds — stable, no spikes observed
