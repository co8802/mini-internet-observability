# Monitoring Stack Performance Profile

## Test Environment
- VM: 16 cores, 121GB RAM
- Mini-internet: 178 containers (10 AS downscaled topology)
- Test duration: 90 minutes, 87 data points, sampled every 60 seconds

## Results

### Scrape Duration
- Average: 0.389s
- Min: 0.360s
- Max: 0.424s
- Prometheus polling interval: 60 seconds
- Scrape duration is consistent and well within the polling interval

### CPU Overhead (% of one core)
| Component  | Average | Min   | Max    |
|------------|---------|-------|--------|
| cAdvisor   | 19.30%  | 6.97% | 96.52% |
| Prometheus | 0.42%   | 0.14% | 6.74%  |
| Grafana    | 0.55%   | 0.29% | 7.34%  |

### Memory Overhead
| Component  | Memory  |
|------------|---------|
| cAdvisor   | ~225 MB |
| Prometheus | ~245 MB |
| Grafana    | ~130 MB |
| **Total**  | ~600 MB |

### Prometheus Query Download Time
- Time to download query results: 7ms
- Well under the 60 second scrape interval

## Key Findings

**Single snapshot is misleading.** An initial snapshot showed cAdvisor at 8.53% CPU. The 90 minute average is 19.30% — more than double. cAdvisor regularly bursts to 50-96% during its internal housekeeping cycles.

**cAdvisor dominates overhead.** Prometheus and Grafana are negligible at under 1% average CPU. cAdvisor is doing all the heavy lifting — it polls every container every second internally regardless of Prometheus scrape interval.

**Scaling concern is real.** At 178 containers cAdvisor averages 19.30% of one core with bursts to 96%. Since cAdvisor is a single process it cannot parallelize across cores. Extrapolating to the full 1192 container topology, average CPU would be around 129% of one core — exceeding what a single core can handle, causing missed scrapes and data gaps.

**Scrape duration is not the bottleneck.** It stays between 0.360s and 0.424s consistently regardless of cAdvisor CPU spikes. The bottleneck at scale would be cAdvisor's internal polling, not Prometheus scraping.

## Recommendation
Switch from cAdvisor to OpenTelemetry. OpenTelemetry uses a push model where each container sends its own metrics rather than one process polling everything. Overhead stays flat as containers scale. This is the right architecture for a 1192 container topology.

A quick win before that switch: adjust cAdvisor's housekeeping interval from the default 1 second to 30 seconds using the --housekeeping_interval flag. This would reduce cAdvisor CPU by roughly 30x with no impact on data quality since Prometheus only scrapes every 60 seconds anyway.

## OpenTelemetry vs cAdvisor Comparison

Both profiled over 90 minutes at 178 containers.

| Metric | cAdvisor | OpenTelemetry | Improvement |
|--------|----------|---------------|-------------|
| CPU Average | 19.30% | 0.11% | 175x less |
| CPU Max | 96.52% | 3.55% | 27x less |
| Memory Average | 225MB | 61MB | 4x less |
| Memory Max | 285MB | 64MB | 4x less |

## Decision
Switched from cAdvisor to OpenTelemetry. cAdvisor removed.

### Limitations
OpenTelemetry cannot collect network stats from mini-internet containers that use Open vSwitch — "Link not found" errors for OVS network namespaces. CPU and memory collection works perfectly for all 178 containers.
