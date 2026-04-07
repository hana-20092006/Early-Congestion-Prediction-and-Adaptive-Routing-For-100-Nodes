# Early Congestion Prediction & Adaptive Routing — 100-Node Scale

> A Computer Networks simulation that **predicts congestion before it happens** and reroutes traffic proactively to prevent packet loss and delay — scaled to a realistic 100-node topology.

This is the scaled-up version of the project. The core congestion prediction logic is identical to the 6-node version, but the network, routing algorithm, and simulation are redesigned for large-scale performance.

[Live Demo](https://srijani-das07.github.io/Early-Congestion-Prediction-and-Adaptive-Routing/)

---

## Overview

In a computer network, data packets compete for limited bandwidth. When queues fill up, congestion occurs, leading to delay and packet drops.

This project implements:

- A **two-stage congestion detection model** (identical thresholds to the 6-node version)
- A **Dijkstra-based adaptive routing algorithm** (upgraded from all-simple-paths for scalability)
- A **SimPy discrete-event network simulation** over a 100-node random geometric graph
- Visualization of congestion trends, heatmaps, and CDF comparisons across all nodes

The system reroutes traffic at the *prediction stage*, not the failure stage.

---

## Problem Statement

Most congestion control mechanisms (e.g., TCP AIMD) use packet loss as the signal for congestion. This is reactive and the performance degradation has already occurred.

This project improves upon that by:

| Traditional Approach | This Project |
|----------------------|-------------|
| Detects after packet loss | Predicts before packet loss |
| Acts when queue is full | Acts at 60–70% capacity |
| Single detection threshold | Two-stage threshold system |
| Reroutes after degradation | Reroutes while performance is stable |

Core insight: **If congestion can be predicted, it can be avoided.**

---

## Architecture

### 1. Two-Stage Congestion Detection

Implemented in `congestion_monitor.py`. **Thresholds are identical to the 6-node version** so results remain directly comparable.

#### Stage 1 — Early Prediction (Soft Thresholds)

A node is marked **PREDICTED** if any 2 of the following occur:

- Queue length > 6 packets
- Delay > 30 ms
- Traffic rate > 55 packets/sec

These represent ~60–70% of danger capacity.

#### Stage 2 — Hard Congestion (Hard Thresholds)

A node is marked **CONGESTED** if any 2 of the following occur:

- Queue length > 10 packets
- Delay > 50 ms
- Traffic rate > 80 packets/sec

This two-metric requirement prevents false positives from single metric spikes.

#### Routing Scores (updated for large-scale avoidance)

| Status | Routing Cost |
|--------|-------------|
| OK | 1 (base) |
| PREDICTED | +20 penalty |
| CONGESTED | ∞ (hard block — node removed from graph) |

The congested node cost is raised to ∞ (compared to cost 3 in the 6-node version) to **completely avoid** congested nodes in a large graph where alternate paths always exist.

---

### 2. Adaptive Routing Logic

Implemented in `adaptive_routing.py`.

**Upgraded from `all_simple_paths` to Dijkstra's algorithm** for O(E log V) scalability across 100 nodes.

Strategy:
1. Build a filtered graph with all **CONGESTED** nodes removed
2. Run Dijkstra with dynamic edge weights based on node state and live queue length
3. If no safe path exists (rare), fall back to the full graph

Dynamic edge weight formula:
```
weight(u → v) = 1 + (20 if predicted) + (queue_length × 2)
```

This makes routing **load-aware** — even among non-congested nodes, paths through heavily queued nodes are penalised.

---

## Network Topology

- **100 nodes** (routers), labelled 1–100
- **Random geometric graph** with radius 0.15 — nodes connect if within spatial proximity, mimicking real ISP mesh topology
- **Full connectivity guaranteed** — isolated components are bridged automatically
- **Variable edge capacities** (40–150): core nodes with higher degree receive higher capacity, reflecting real backbone links
- ~5–8 average degree per node (sparse, realistic)
- **~15 "hot" nodes** receive elevated traffic during simulation (high-degree nodes preferred, as in real networks)

---

## Project Structure

```
nodes_100/
│
├── network_setup.py       # 100-node random geometric graph with capacity scaling
├── congestion_monitor.py  # Two-stage prediction logic (same thresholds, ∞ cost for congested)
├── adaptive_routing.py    # Dijkstra-based routing with hard block + dynamic queue cost
├── simulation.py          # SimPy simulation (traffic rates tuned for 100-node scale)
├── compare.py             # Baseline vs Early Prediction: heatmap, CDF, timeline graphs
├── visualize.py           # Per-node visualisation helpers
├── run.py                 # Single command to run everything in order
├── index.html             # Live interactive browser demo (no install needed)
├── package-lock.json      # Frontend dependency lock file
├── requirements.txt       # Python dependencies
└── README.md              # This file
```

---

## How to Run

### Prerequisites

Make sure you have Python 3.8 or higher installed. You can check by running:

```bash
python --version
```

### Step 1 — Fork & Clone the Repository

First, fork the repository on GitHub, then clone it locally:

```bash
git clone https://github.com/YOUR-USERNAME/Early-Congestion-Prediction-and-Adaptive-Routing.git
cd Early-Congestion-Prediction-and-Adaptive-Routing/nodes_100
```

### Step 2 — Install Dependencies

```bash
pip install -r requirements.txt
```

This installs: `networkx`, `simpy`, `matplotlib`, `numpy`.

### Step 3 — Run Everything

```bash
python run.py
```

### Running the Live Demo (Optional)

Open `index.html` in any browser or use the demo link provided in the description. No installation required. Use the sliders to control traffic rates per node in real time and watch the routing adapt live.

---

## CN Concepts Used

| Concept | Where It's Applied |
|---|---|
| **Congestion Control** | Two-stage threshold system in `congestion_monitor.py` |
| **Routing Algorithms** | Dijkstra's shortest path with dynamic weights in `adaptive_routing.py` |
| **Quality of Service (QoS)** | Prioritising low-congestion paths to maintain throughput and reduce delay |
| **Network Monitoring** | Continuous per-node tracking of queue length, delay, and traffic rate across all 100 nodes |
| **Discrete Event Simulation** | SimPy environment simulating packet arrivals using exponential distribution |
| **Graph Theory** | NetworkX random geometric graph with degree-scaled edge capacities |

---

## Tools & Technologies

| Tool | Purpose |
|---|---|
| **Python 3.8+** | Core programming language |
| **NetworkX** | 100-node graph creation, Dijkstra path finding |
| **NumPy** | Random geometric graph generation and degree calculations |
| **SimPy** | Discrete-event simulation engine for modelling time and packet arrivals |
| **Matplotlib** | Chart generation — heatmaps, CDFs, timeline graphs |
| **HTML/CSS/JavaScript** | Live interactive browser demo (`index.html`) |
| **Chart.js** | Real-time charts inside the browser demo |

---

## Key Results

With early prediction enabled across 100 nodes:

- **~15 hot nodes** identified and monitored for early congestion buildup
- **Baseline**: hot nodes breach soft threshold then hard threshold — queues remain elevated
- **Early Prediction**: rerouting triggered as soon as soft threshold crossed — queue climbs then recovers (visible "catch and recover" pattern)
- **CDF curve** for Early Prediction shifted clearly left of baseline — lower queue lengths across the network
- **Heatmap**: "Baseline Congested" column dark for hot nodes; "Predicted Congested" near-zero

---

## Difference from the 6-Node Version

| Aspect | 6-Node Version | 100-Node Version |
|--------|---------------|-----------------|
| **Nodes / Edges** | 6 nodes, 7 edges | 100 nodes, ~300+ edges |
| **Topology** | Hand-crafted fixed graph | Random geometric graph (ISP-like) |
| **Routing algorithm** | `all_simple_paths` (exhaustive) | Dijkstra (O(E log V)) |
| **Congested node cost** | 3 | ∞ (hard block) |
| **Hot nodes** | Node 2, Node 4 (fixed) | ~15 high-degree nodes (dynamic) |
| **Edge capacity** | Fixed values | Degree-scaled (40–150) |
| **Congestion thresholds** | Same | Same (identical, for comparability) |

---

## Conclusion

Compared to no early prediction:

- Reduced packet loss (queues avoided before overflow)
- Lower end-to-end delay across a realistic large-scale network
- Improved throughput
- Better traffic distribution — hot nodes offloaded before saturation
- Fewer nodes reaching hard congestion state

---

## Advantages

- Predictive rather than reactive
- Lightweight (no ML, no DPI)
- Dijkstra ensures scalability — runs efficiently on 100+ node graphs
- Two-metric validation reduces false positives
- Queue-length-aware routing provides dynamic load balancing
- Hard block on congested nodes ensures they are never used as relay points

---

## Limitations

- Simulated environment (SimPy model)
- Static threshold values
- No feedback loop for rerouted traffic load
- Simplified queue drain model
- Assumes global state visibility (SDN-like control)
- No packet prioritization
- Random geometric graph may produce varying topologies across seeds

---

## Authors

- [Hana Maria Philip](https://github.com/hana-20092006)
- [Leela Chandana Apilagunta](https://github.com/leelachandana45-a11y)
- [Poojitha Sudalagunta](https://github.com/poojithasudalagunta-source)
- [Srijani Das](https://github.com/Srijani-Das07)

---

*This project was built as part of a Computer Networks course to demonstrate early congestion prediction using traffic trend analysis, without relying on packet loss as the primary congestion signal.*
