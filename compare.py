"""
compare.py — 100-Node: Baseline vs Early Prediction Comparison

Runs two identical simulations (same seed, same traffic):
  Run 1 — Traditional reactive routing (no early prediction)
  Run 2 — Early congestion prediction + adaptive rerouting

Produces four comparison charts:
  1. Queue-length timeline for a sample of 12 representative nodes
  2. Average queue length per node (all 100, sorted)
  3. Congestion/prediction event heatmap across all 100 nodes
  4. Summary metrics bar chart
"""

import random
import simpy
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib.colors as mcolors

from network_setup  import create_network, NUM_NODES
from congestion_monitor import NodeMonitor
from adaptive_routing   import AdaptiveRouter

# ── Simulation parameters ──────────────────────────────────────────────────
RANDOM_SEED  = 42
SIM_DURATION = 80        # time units — same as original

# Source and destination for path-finding (first and last node)
SRC_NODE = 1
DST_NODE = NUM_NODES     # 100

# Traffic rates: ~20% of nodes are "hot" (higher load)
# The rest carry light background traffic
random.seed(RANDOM_SEED)
np.random.seed(RANDOM_SEED)
_rng = random.Random(RANDOM_SEED)

def _make_traffic_rates(network):
    nodes = sorted(network.nodes())
    rates = {}
    for n in nodes:
        deg = network.degree(n)
        if deg >= 6:           # high-degree core node → heavy traffic
            rates[n] = _rng.randint(12, 18)
        elif deg >= 4:
            rates[n] = _rng.randint(6, 11)
        else:
            rates[n] = _rng.randint(2, 6)
    return rates

# Base drain: always slightly above arrival so queues don't diverge forever
def _make_drain_rates(traffic_rates):
    drain = {}
    for n, r in traffic_rates.items():
        drain[n] = r + 2 + (2 if r > 10 else 0)
    return drain

QUEUE_SOFT = 6
QUEUE_HARD = 10


# ── Simulation engine ──────────────────────────────────────────────────────

def run_sim(early_prediction: bool, seed: int):
    random.seed(seed)
    np.random.seed(seed)

    env      = simpy.Environment()
    network  = create_network(seed=seed)
    monitors = {n: NodeMonitor(n) for n in network.nodes()}
    router   = AdaptiveRouter(network, monitors)

    traffic_rates = _make_traffic_rates(network)
    drain_rates   = _make_drain_rates(traffic_rates)
    nodes         = sorted(network.nodes())

    results = {
        'queue_history':    {n: [] for n in nodes},
        'delay_history':    {n: [] for n in nodes},
        'time_labels':      [],
        'dropped_total':    0,
        'predicted_events': 0,
        'congested_events': 0,
        'reroutes':         0,
        'reroute_times':    [],
        'rerouted_packets': 0,
    }

    prev_path = [None]

    def packet_generator(node_id, monitor, rate):
        while True:
            yield env.timeout(random.expovariate(rate))

            if early_prediction and (monitor.predicted or monitor.congested):
                results['rerouted_packets'] += 1
                monitor.traffic_rate = int(rate * 10) + random.randint(-3, 3)
                continue

            monitor.queue_length += 1
            monitor.traffic_rate  = int(rate * 10) + random.randint(-3, 3)
            monitor.delay         = monitor.queue_length * 0.005

            # Baseline: drop packets on severely overloaded nodes
            if not early_prediction and monitor.queue_length > QUEUE_HARD + 8:
                results['dropped_total'] += 1
                monitor.queue_length = max(0, monitor.queue_length - 1)

    def drain_and_record():
        while True:
            yield env.timeout(1.0)

            for n, monitor in monitors.items():
                drain = random.randint(drain_rates[n] - 1, drain_rates[n] + 1)
                extra = 0
                if early_prediction and (monitor.predicted or monitor.congested):
                    extra = random.randint(1, 3)

                monitor.queue_length = max(0, monitor.queue_length - drain - extra)
                monitor.traffic_rate = int(traffic_rates[n] * 10) + random.randint(-3, 3)
                monitor.delay        = monitor.queue_length * 0.005
                monitor.predict_congestion()

                results['queue_history'][n].append(monitor.queue_length)
                results['delay_history'][n].append(monitor.delay)

                if monitor.predicted: results['predicted_events'] += 1
                if monitor.congested: results['congested_events'] += 1

            results['time_labels'].append(round(env.now, 1))

            current_path = router.best_path(SRC_NODE, DST_NODE)
            if current_path != prev_path[0]:
                results['reroutes'] += 1
                results['reroute_times'].append(env.now)
                prev_path[0] = current_path

    for n, rate in traffic_rates.items():
        env.process(packet_generator(n, monitors[n], rate))
    env.process(drain_and_record())
    env.run(until=SIM_DURATION)

    results['monitors']   = monitors
    results['final_path'] = router.best_path(SRC_NODE, DST_NODE)
    results['traffic_rates'] = traffic_rates

    for n in nodes:
        qh = results['queue_history'][n]
        dh = results['delay_history'][n]
        results[f'avg_queue_{n}']  = float(np.mean(qh)) if qh else 0.0
        results[f'peak_queue_{n}'] = float(max(qh))     if qh else 0.0
        results[f'avg_delay_{n}']  = float(np.mean(dh)) if dh else 0.0

    return results, network, nodes


def print_summary(label, r, nodes):
    print(f"\n{'─'*55}")
    print(f"  {label}")
    print(f"{'─'*55}")
    print(f"  Packets dropped       : {r['dropped_total']}")
    print(f"  Congestion events     : {r['congested_events']}")
    print(f"  Early prediction hits : {r['predicted_events']}")
    print(f"  Rerouting events      : {r['reroutes']}")
    avg_q = np.mean([r[f'avg_queue_{n}'] for n in nodes])
    print(f"  Overall avg queue     : {avg_q:.2f} pkts")
    if r['reroute_times']:
        print(f"  First reroute at      : t={r['reroute_times'][0]:.1f}s")


# ── Plotting ───────────────────────────────────────────────────────────────

# Colour palette
C_BASE = '#ff4e6a'
C_PRED = '#00d4ff'
C_SOFT = '#ffd93d'
C_HARD = '#ff6b6b'
BG     = '#0f1624'
BG2    = '#0a0e1a'
GRID   = '#1e2d45'
TEXT   = '#c8e0f4'
GREEN  = '#00ff9d'


def _style(ax, title, xlabel='Time (s)', ylabel=''):
    ax.set_facecolor(BG)
    ax.tick_params(colors=TEXT, labelsize=8)
    ax.xaxis.label.set_color(TEXT)
    ax.yaxis.label.set_color(TEXT)
    ax.set_title(title, color=TEXT, fontsize=10, fontweight='bold', pad=5)
    for sp in ax.spines.values():
        sp.set_edgecolor(GRID)
    ax.grid(True, color=GRID, lw=0.4, alpha=0.6)
    if xlabel: ax.set_xlabel(xlabel, color=TEXT, fontsize=8)
    if ylabel: ax.set_ylabel(ylabel, color=TEXT, fontsize=8)


def _pct_improvement(base, pred):
    if base == 0: return 0.0
    return max(min((base - pred) / base * 100, 100.0), -200.0)


# ── Chart 1: Timeline for representative sample nodes ─────────────────────

def plot_queue_timelines(baseline, predicted, nodes, network):
    """Show queue-length timelines for 12 hand-picked representative nodes."""

    # Pick sample: high-degree (core), medium, low-degree (edge)
    degrees  = dict(network.degree())
    sorted_n = sorted(nodes, key=lambda n: degrees[n], reverse=True)
    sample   = sorted_n[:4] + sorted_n[len(nodes)//2-2:len(nodes)//2+2] + sorted_n[-4:]
    sample   = list(dict.fromkeys(sample))[:12]   # deduplicate, keep 12

    fig, axes = plt.subplots(4, 3, figsize=(18, 14))
    fig.patch.set_facecolor(BG2)
    fig.suptitle(
        '100-Node Scale-Up — Queue Length Timelines (Sample of 12 Nodes)\n'
        'Early Prediction vs No Prediction  ·  Same traffic · Same seed',
        color='white', fontsize=13, fontweight='bold', y=1.01
    )

    t = baseline['time_labels']
    for ax, n in zip(axes.flat, sample):
        ax.plot(t, baseline['queue_history'][n],  color=C_BASE, lw=1.4, label='No Prediction')
        ax.plot(t, predicted['queue_history'][n], color=C_PRED, lw=1.4, label='Early Prediction')
        ax.axhline(QUEUE_SOFT, color=C_SOFT, lw=1.0, ls='--', label=f'Predict th. ({QUEUE_SOFT})')
        ax.axhline(QUEUE_HARD, color=C_HARD, lw=1.0, ls=':',  label=f'Congest th. ({QUEUE_HARD})')
        ax.legend(fontsize=6, facecolor=BG, labelcolor=TEXT, loc='upper left')
        deg_label = f'deg={degrees[n]}'
        _style(ax, f'Node {n}  [{deg_label}]', ylabel='Queue (pkts)')

    plt.tight_layout()
    plt.savefig('graph1_queue_timelines.png', dpi=140, bbox_inches='tight',
                facecolor=BG2)
    plt.close()
    print('  Saved: graph1_queue_timelines.png')


# ── Chart 2: Avg queue per node (all 100), sorted ─────────────────────────

def plot_avg_queue_all_nodes(baseline, predicted, nodes):
    """Bar chart of average queue length for all 100 nodes, sorted by baseline."""
    base_avgs = np.array([baseline[f'avg_queue_{n}'] for n in nodes])
    pred_avgs = np.array([predicted[f'avg_queue_{n}'] for n in nodes])

    order      = np.argsort(base_avgs)[::-1]
    base_avgs  = base_avgs[order]
    pred_avgs  = pred_avgs[order]
    x          = np.arange(len(nodes))

    fig, ax = plt.subplots(figsize=(20, 6))
    fig.patch.set_facecolor(BG2)
    ax.bar(x - 0.2, base_avgs, 0.38, color=C_BASE, alpha=0.85,
           label='No Prediction', edgecolor='none')
    ax.bar(x + 0.2, pred_avgs, 0.38, color=C_PRED, alpha=0.85,
           label='Early Prediction', edgecolor='none')
    ax.axhline(QUEUE_SOFT, color=C_SOFT, lw=1, ls='--', label=f'Predict th. ({QUEUE_SOFT})')
    ax.axhline(QUEUE_HARD, color=C_HARD, lw=1, ls=':',  label=f'Congest th. ({QUEUE_HARD})')
    ax.legend(fontsize=10, facecolor=BG, labelcolor=TEXT)
    ax.set_xticks([])
    ax.set_xlabel('All 100 nodes  (sorted by No-Prediction avg queue, highest → lowest)',
                  color=TEXT, fontsize=9)
    _style(ax, '100-Node Avg Queue Length Per Node  (Lower = Better)',
           xlabel='', ylabel='Avg Queue (pkts)')
    plt.tight_layout()
    plt.savefig('graph2_avg_queue_all_nodes.png', dpi=140, bbox_inches='tight',
                facecolor=BG2)
    plt.close()
    print('  Saved: graph2_avg_queue_all_nodes.png')


# ── Chart 3: Congestion heatmap ────────────────────────────────────────────

def plot_congestion_heatmap(baseline, predicted, nodes):
    """
    Heatmap of congestion-event count per node.
    Rows = nodes (sorted by congestion count), Columns = [Baseline, Predicted].
    """
    b_cong = np.array([
        sum(1 for q in baseline['queue_history'][n] if q > QUEUE_HARD)
        for n in nodes
    ], dtype=float)
    p_cong = np.array([
        sum(1 for q in predicted['queue_history'][n] if q > QUEUE_HARD)
        for n in nodes
    ], dtype=float)

    b_pred = np.array([
        sum(1 for q in baseline['queue_history'][n] if QUEUE_SOFT < q <= QUEUE_HARD)
        for n in nodes
    ], dtype=float)
    p_pred = np.array([
        sum(1 for q in predicted['queue_history'][n] if QUEUE_SOFT < q <= QUEUE_HARD)
        for n in nodes
    ], dtype=float)

    order  = np.argsort(b_cong)[::-1]
    matrix = np.stack([b_cong[order], p_cong[order],
                       b_pred[order], p_pred[order]], axis=1)
    cols   = ['Baseline\nCongested', 'Predicted\nCongested',
              'Baseline\nPredicted', 'Predicted\nPredicted']

    fig, ax = plt.subplots(figsize=(10, 18))
    fig.patch.set_facecolor(BG2)
    cmap = plt.cm.YlOrRd
    im   = ax.imshow(matrix, aspect='auto', cmap=cmap,
                     norm=mcolors.PowerNorm(gamma=0.5,
                                            vmin=0, vmax=matrix.max()))
    ax.set_xticks(range(4))
    ax.set_xticklabels(cols, color=TEXT, fontsize=10)
    ax.set_yticks([])
    ax.set_ylabel('All 100 nodes  (sorted by baseline congestion events)',
                  color=TEXT, fontsize=9)
    ax.set_facecolor(BG)
    for sp in ax.spines.values():
        sp.set_edgecolor(GRID)

    cbar = fig.colorbar(im, ax=ax, fraction=0.02, pad=0.02)
    cbar.ax.tick_params(colors=TEXT)
    cbar.set_label('Events above threshold', color=TEXT, fontsize=9)

    ax.set_title(
        '100-Node Congestion & Prediction Event Heatmap\n'
        '(Darker = more events above threshold)',
        color=TEXT, fontsize=11, fontweight='bold', pad=8
    )
    plt.tight_layout()
    plt.savefig('graph3_congestion_heatmap.png', dpi=140, bbox_inches='tight',
                facecolor=BG2)
    plt.close()
    print('  Saved: graph3_congestion_heatmap.png')


# ── Chart 4: Summary metrics ───────────────────────────────────────────────

def plot_summary_metrics(baseline, predicted, nodes):
    """Side-by-side bar chart of key headline metrics."""
    b_avg_q = float(np.mean([baseline[f'avg_queue_{n}'] for n in nodes]))
    p_avg_q = float(np.mean([predicted[f'avg_queue_{n}'] for n in nodes]))

    b_peak  = float(np.max([baseline[f'peak_queue_{n}'] for n in nodes]))
    p_peak  = float(np.max([predicted[f'peak_queue_{n}'] for n in nodes]))

    metrics = {
        'Avg Queue\n(all nodes)':  (b_avg_q,  p_avg_q),
        'Peak Queue\n(worst node)': (b_peak,   p_peak),
        'Congestion\nEvents':      (baseline['congested_events'], predicted['congested_events']),
        'Prediction\nEvents':      (baseline['predicted_events'], predicted['predicted_events']),
        'Packets\nDropped':        (baseline['dropped_total'],    predicted['dropped_total']),
        'Reroutes':                (baseline['reroutes'],         predicted['reroutes']),
    }

    fig, axes = plt.subplots(2, 3, figsize=(16, 8))
    fig.patch.set_facecolor(BG2)
    fig.suptitle(
        '100-Node Scale-Up — Summary Metric Comparison\n'
        'Early Prediction vs Traditional Reactive Routing',
        color='white', fontsize=13, fontweight='bold'
    )

    for ax, (label, (bval, pval)) in zip(axes.flat, metrics.items()):
        bars = ax.bar(['No Prediction', 'Early Prediction'],
                      [bval, pval],
                      color=[C_BASE, C_PRED], alpha=0.88,
                      edgecolor='white', linewidth=0.5)
        for bar, val in zip(bars, [bval, pval]):
            ax.text(bar.get_x() + bar.get_width()/2,
                    bar.get_height() + max(bval, pval) * 0.02,
                    f'{val:.1f}', ha='center', color=TEXT, fontsize=10,
                    fontweight='bold')

        improvement = _pct_improvement(bval, pval)
        col = GREEN if improvement > 0 else (C_HARD if improvement < 0 else TEXT)
        sym = '▼' if improvement > 0 else ('▲' if improvement < 0 else '—')
        ax.set_title(f'{label}\n{sym} {abs(improvement):.1f}% reduction',
                     color=TEXT, fontsize=9, fontweight='bold', pad=4)
        ax.tick_params(colors=TEXT)
        ax.get_xticklabels()[0].set_color(C_BASE)
        ax.get_xticklabels()[1].set_color(C_PRED)
        ax.set_facecolor(BG)
        for sp in ax.spines.values():
            sp.set_edgecolor(GRID)
        ax.grid(True, axis='y', color=GRID, lw=0.4, alpha=0.6)

    plt.tight_layout()
    plt.savefig('graph4_summary_metrics.png', dpi=140, bbox_inches='tight',
                facecolor=BG2)
    plt.close()
    print('  Saved: graph4_summary_metrics.png')


# ── Chart 5: CDF of avg queue length ──────────────────────────────────────

def plot_cdf(baseline, predicted, nodes):
    """CDF of per-node average queue length — good for showing distribution shift."""
    b = np.sort([baseline[f'avg_queue_{n}'] for n in nodes])
    p = np.sort([predicted[f'avg_queue_{n}'] for n in nodes])
    y = np.linspace(0, 1, len(nodes))

    fig, ax = plt.subplots(figsize=(10, 6))
    fig.patch.set_facecolor(BG2)
    ax.plot(b, y, color=C_BASE, lw=2, label='No Prediction')
    ax.plot(p, y, color=C_PRED, lw=2, label='Early Prediction')
    ax.axvline(QUEUE_SOFT, color=C_SOFT, lw=1, ls='--', label=f'Predict threshold ({QUEUE_SOFT})')
    ax.axvline(QUEUE_HARD, color=C_HARD, lw=1, ls=':',  label=f'Congest threshold ({QUEUE_HARD})')
    ax.legend(fontsize=10, facecolor=BG, labelcolor=TEXT)
    _style(ax, 'CDF — Per-Node Avg Queue Length (100 Nodes)\n'
               'Curve shifted left = more nodes with lower queue = better',
           xlabel='Avg Queue Length (pkts)', ylabel='Cumulative Fraction of Nodes')
    plt.tight_layout()
    plt.savefig('graph5_cdf_queue.png', dpi=140, bbox_inches='tight',
                facecolor=BG2)
    plt.close()
    print('  Saved: graph5_cdf_queue.png')


# ── Main ───────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    print('=' * 60)
    print('  100-Node Scale-Up: Baseline vs Early Prediction')
    print('=' * 60)

    print('\n[1/2] Running WITHOUT early prediction (baseline)...')
    baseline, network, nodes = run_sim(early_prediction=False, seed=RANDOM_SEED)

    print('[2/2] Running WITH early prediction...')
    predicted, _,      _     = run_sim(early_prediction=True,  seed=RANDOM_SEED)

    print_summary('WITHOUT Early Prediction (Baseline)', baseline, nodes)
    print_summary('WITH    Early Prediction (This Project)', predicted, nodes)

    print(f'\n{"="*60}')
    print('  KEY IMPROVEMENTS  (100 nodes)')
    print(f'{"="*60}')

    def show(label, bv, pv, unit=''):
        if bv == 0:
            print(f'  ➖  {label}: {bv:.1f}{unit} → {pv:.1f}{unit}')
            return
        diff = bv - pv
        pct  = diff / bv * 100
        icon = '✅' if diff > 0 else ('⚠️ ' if diff < 0 else '➖')
        print(f'  {icon}  {label}: {bv:.1f}{unit} → {pv:.1f}{unit}  ({pct:.1f}% reduction)')

    b_avg_q = float(np.mean([baseline[f'avg_queue_{n}'] for n in nodes]))
    p_avg_q = float(np.mean([predicted[f'avg_queue_{n}'] for n in nodes]))
    show('Overall Avg Queue',  b_avg_q, p_avg_q, ' pkts')
    show('Packets Dropped',    baseline['dropped_total'],    predicted['dropped_total'])
    show('Congestion Events',  baseline['congested_events'], predicted['congested_events'])
    if predicted['reroute_times']:
        print(f'\n  ⚡  First reroute at: t={predicted["reroute_times"][0]:.1f}s')

    print('\n  Generating 5 comparison graphs...')
    plot_queue_timelines  (baseline, predicted, nodes, network)
    plot_avg_queue_all_nodes(baseline, predicted, nodes)
    plot_congestion_heatmap (baseline, predicted, nodes)
    plot_summary_metrics    (baseline, predicted, nodes)
    plot_cdf                (baseline, predicted, nodes)

    print(f'\n{"="*60}')
    print('  All graphs saved!')
    print('    graph1_queue_timelines.png    — timelines for 12 sample nodes')
    print('    graph2_avg_queue_all_nodes.png — avg queue for all 100 nodes')
    print('    graph3_congestion_heatmap.png  — heatmap of congestion events')
    print('    graph4_summary_metrics.png     — headline metric comparison')
    print('    graph5_cdf_queue.png           — CDF of per-node avg queue')
    print(f'{"="*60}\n')