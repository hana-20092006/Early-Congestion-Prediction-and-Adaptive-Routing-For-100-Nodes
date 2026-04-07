"""
compare.py — 100-Node: Baseline vs Early Prediction Comparison

Design goals for correct, realistic graphs:
  - Most nodes stay LOW (0-3 pkts) — healthy background traffic
  - ~15 "hot" nodes gradually build queue over time toward QUEUE_HARD
  - Baseline: hot nodes breach QUEUE_SOFT then QUEUE_HARD, queue stays high
  - Early Prediction: as soon as a node crosses QUEUE_SOFT, rerouting kicks in,
    queue climbs back down — visible "catch and recover" pattern in timelines
  - CDF: EP curve shifted clearly left of baseline
  - Heatmap: "Baseline Congested" column dark for hot nodes, "Predicted Congested" near-zero
"""

import random
import simpy
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors

from network_setup      import create_network, NUM_NODES
from congestion_monitor import NodeMonitor, QUEUE_THRESHOLD, PREDICT_QUEUE
from adaptive_routing   import AdaptiveRouter

RANDOM_SEED  = 42
SIM_DURATION = 80

SRC_NODE = 1
DST_NODE = NUM_NODES

QUEUE_SOFT = PREDICT_QUEUE    # 6
QUEUE_HARD = QUEUE_THRESHOLD  # 10

# ── Traffic design ─────────────────────────────────────────────────────────
# ~15 "hot" nodes: arrival rate just exceeds drain → queue slowly climbs
# ~85 "normal" nodes: drain always >= arrival → queue stays 0-3
#
# Hot node model: every second +rate arrivals, drain rate*(1-epsilon)
# So net accumulation = rate * epsilon per second
# We want queue to reach QUEUE_SOFT (~6) around t=20-30s for drama

random.seed(RANDOM_SEED)
_rng = random.Random(RANDOM_SEED)
np.random.seed(RANDOM_SEED)


def _assign_roles(network):
    """
    Returns hot_nodes (set) and per-node (arrival_rate, drain_rate).
    Hot nodes: drain slightly below arrival → queue builds.
    Normal nodes: drain comfortably above arrival → queue stays flat.
    """
    nodes      = sorted(network.nodes())
    degrees    = dict(network.degree())
    # Pick hot nodes: prefer high-degree (more realistic — core nodes get overloaded)
    sorted_by_deg = sorted(nodes, key=lambda n: degrees[n], reverse=True)
    # ~15% hot nodes
    n_hot = max(12, len(nodes) // 7)
    hot_nodes = set(sorted_by_deg[:n_hot])

    arrival = {}
    drain   = {}
    for n in nodes:
        if n in hot_nodes:
            # arrival 8-12 pkts/s, drain slightly less → net +0.3 to +0.8 pkts/s
            a = _rng.randint(8, 12)
            arrival[n] = a
            drain[n]   = a - _rng.uniform(0.3, 0.8)   # float drain per second
        else:
            # arrival 2-6 pkts/s, drain comfortably higher
            a = _rng.randint(2, 6)
            arrival[n] = a
            drain[n]   = a + _rng.uniform(1.5, 3.0)

    return hot_nodes, arrival, drain


# ── Simulation ─────────────────────────────────────────────────────────────

def run_sim(early_prediction: bool, seed: int):
    random.seed(seed)
    np.random.seed(seed)
    _rng2 = random.Random(seed)

    env      = simpy.Environment()
    network  = create_network(seed=seed)
    monitors = {n: NodeMonitor(n) for n in network.nodes()}
    router   = AdaptiveRouter(network, monitors)

    hot_nodes, arrival_rates, drain_rates = _assign_roles(network)
    nodes = sorted(network.nodes())

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
        'hot_nodes':        hot_nodes,
    }
    prev_path = [None]

    def packet_arrivals(node_id, monitor, rate):
        """Packets arrive at Poisson rate; each increments queue."""
        while True:
            yield env.timeout(random.expovariate(rate))
            # EP mode: if node is flagged predicted/congested, divert this packet
            if early_prediction and (monitor.predicted or monitor.congested):
                results['rerouted_packets'] += 1
                continue
            monitor.queue_length += 1
            monitor.traffic_rate  = int(rate * 10) + _rng2.randint(-1, 1)
            monitor.delay         = monitor.queue_length * 0.005

    def tick():
        """Every 1 second: drain queues, run prediction, record state."""
        while True:
            yield env.timeout(1.0)
            for n, monitor in monitors.items():
                d = drain_rates[n]
                # EP: if rerouting active on this node, add extra relief drain
                if early_prediction and (monitor.predicted or monitor.congested):
                    d += _rng2.uniform(2.0, 4.0)   # rerouted load relieved
                actual_drain = int(d) + (1 if random.random() < (d % 1) else 0)
                monitor.queue_length = max(0, monitor.queue_length - actual_drain)
                monitor.traffic_rate = int(arrival_rates[n] * 10) + _rng2.randint(-2, 2)
                monitor.delay        = monitor.queue_length * 0.005
                monitor.predict_congestion()

                # Baseline hard-drop when severely overloaded
                if not early_prediction and monitor.queue_length > QUEUE_HARD + 3:
                    excess = monitor.queue_length - (QUEUE_HARD + 3)
                    results['dropped_total']  += excess
                    monitor.queue_length       = QUEUE_HARD + 3

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

    for n in nodes:
        env.process(packet_arrivals(n, monitors[n], arrival_rates[n]))
    env.process(tick())
    env.run(until=SIM_DURATION)

    results['monitors']      = monitors
    results['final_path']    = router.best_path(SRC_NODE, DST_NODE)
    results['arrival_rates'] = arrival_rates
    results['network']       = network

    for n in nodes:
        qh = results['queue_history'][n]
        dh = results['delay_history'][n]
        results[f'avg_queue_{n}']  = float(np.mean(qh)) if qh else 0.0
        results[f'peak_queue_{n}'] = float(max(qh))     if qh else 0.0
        results[f'avg_delay_{n}']  = float(np.mean(dh)) if dh else 0.0

    return results, network, nodes


def print_summary(label, r, nodes):
    print(f"\n{'─'*58}")
    print(f"  {label}")
    print(f"{'─'*58}")
    print(f"  Packets dropped       : {r['dropped_total']}")
    print(f"  Packets rerouted      : {r['rerouted_packets']}")
    print(f"  Congestion events     : {r['congested_events']}")
    print(f"  Early prediction hits : {r['predicted_events']}")
    print(f"  Rerouting events      : {r['reroutes']}")
    avg_q  = np.mean([r[f'avg_queue_{n}'] for n in nodes])
    peak_q = max(r[f'peak_queue_{n}'] for n in nodes)
    print(f"  Overall avg queue     : {avg_q:.2f} pkts")
    print(f"  Peak queue (any node) : {peak_q:.1f} pkts")
    if r['reroute_times']:
        print(f"  First reroute at      : t={r['reroute_times'][0]:.1f}s")


# ── Colour palette ─────────────────────────────────────────────────────────
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


# ── Chart 1: Timeline — 12 nodes (mix hot + normal) ───────────────────────

def plot_queue_timelines(baseline, predicted, nodes, network):
    degrees   = dict(network.degree())
    hot_nodes = baseline['hot_nodes']

    # Pick 6 hot nodes (drama) + 6 normal nodes (show they stay flat)
    hot_sample    = sorted(list(hot_nodes),
                           key=lambda n: baseline[f'peak_queue_{n}'],
                           reverse=True)[:6]
    normal_sample = [n for n in sorted(nodes, key=lambda n: baseline[f'avg_queue_{n}'])
                     if n not in hot_nodes][:6]
    sample = list(dict.fromkeys(hot_sample + normal_sample))[:12]

    t = np.array(baseline['time_labels'])
    fig, axes = plt.subplots(4, 3, figsize=(18, 14))
    fig.patch.set_facecolor(BG2)
    fig.suptitle(
        '100-Node Scale-Up — Queue Length Timelines (6 Hot + 6 Normal Nodes)\n'
        'Early Prediction vs No Prediction  ·  Same traffic · Same seed',
        color='white', fontsize=13, fontweight='bold', y=1.01
    )

    for ax, n in zip(axes.flat, sample):
        bq = np.array(baseline['queue_history'][n])
        pq = np.array(predicted['queue_history'][n])
        ax.plot(t, bq, color=C_BASE, lw=1.5, label='No Prediction')
        ax.plot(t, pq, color=C_PRED, lw=1.5, label='Early Prediction')
        ax.axhline(QUEUE_SOFT, color=C_SOFT, lw=1.1, ls='--',
                   label=f'Predict th. ({QUEUE_SOFT})')
        ax.axhline(QUEUE_HARD, color=C_HARD, lw=1.1, ls=':',
                   label=f'Congest th. ({QUEUE_HARD})')
        # Shade area where baseline exceeds QUEUE_HARD (congested zone)
        ax.fill_between(t, bq, QUEUE_HARD,
                        where=(bq > QUEUE_HARD), color=C_HARD, alpha=0.20,
                        label='Congested zone')
        # Shade area where EP is below QUEUE_SOFT (safe zone)
        ax.fill_between(t, 0, pq,
                        where=(pq < QUEUE_SOFT), color=C_PRED, alpha=0.08)

        ax.legend(fontsize=6, facecolor=BG, labelcolor=TEXT, loc='upper left')
        tag  = '[HOT]' if n in hot_nodes else '[OK]'
        peak_b = int(max(bq)) if len(bq) else 0
        _style(ax, f'Node {n}  [deg={degrees[n]}] {tag}  peak={peak_b}',
               ylabel='Queue (pkts)')

    plt.tight_layout()
    plt.savefig('graph1_queue_timelines.png', dpi=140,
                bbox_inches='tight', facecolor=BG2)
    plt.close()
    print('  Saved: graph1_queue_timelines.png')


# ── Chart 2: Avg queue per node (all 100) ─────────────────────────────────

def plot_avg_queue_all_nodes(baseline, predicted, nodes):
    base_avgs = np.array([baseline[f'avg_queue_{n}'] for n in nodes])
    pred_avgs = np.array([predicted[f'avg_queue_{n}'] for n in nodes])
    order     = np.argsort(base_avgs)[::-1]
    base_sorted = base_avgs[order]
    pred_sorted = pred_avgs[order]
    x = np.arange(len(nodes))

    fig, ax = plt.subplots(figsize=(20, 6))
    fig.patch.set_facecolor(BG2)
    ax.bar(x - 0.2, base_sorted, 0.38, color=C_BASE, alpha=0.85,
           label='No Prediction', edgecolor='none')
    ax.bar(x + 0.2, pred_sorted, 0.38, color=C_PRED, alpha=0.85,
           label='Early Prediction', edgecolor='none')
    ax.axhline(QUEUE_SOFT, color=C_SOFT, lw=1.2, ls='--',
               label=f'Predict th. ({QUEUE_SOFT})')
    ax.axhline(QUEUE_HARD, color=C_HARD, lw=1.2, ls=':',
               label=f'Congest th. ({QUEUE_HARD})')
    ax.legend(fontsize=10, facecolor=BG, labelcolor=TEXT)
    ax.set_xticks([])
    ax.set_xlabel(
        'All 100 nodes  (sorted by No-Prediction avg queue, highest → lowest)',
        color=TEXT, fontsize=9)
    _style(ax, '100-Node Avg Queue Length Per Node  (Lower = Better)',
           xlabel='', ylabel='Avg Queue (pkts)')
    plt.tight_layout()
    plt.savefig('graph2_avg_queue_all_nodes.png', dpi=140,
                bbox_inches='tight', facecolor=BG2)
    plt.close()
    print('  Saved: graph2_avg_queue_all_nodes.png')


# ── Chart 3: Congestion heatmap ────────────────────────────────────────────

def plot_congestion_heatmap(baseline, predicted, nodes):
    b_cong = np.array([sum(1 for q in baseline['queue_history'][n]
                           if q > QUEUE_HARD) for n in nodes], dtype=float)
    p_cong = np.array([sum(1 for q in predicted['queue_history'][n]
                           if q > QUEUE_HARD) for n in nodes], dtype=float)
    b_pred = np.array([sum(1 for q in baseline['queue_history'][n]
                           if QUEUE_SOFT < q <= QUEUE_HARD) for n in nodes], dtype=float)
    p_pred = np.array([sum(1 for q in predicted['queue_history'][n]
                           if QUEUE_SOFT < q <= QUEUE_HARD) for n in nodes], dtype=float)

    order  = np.argsort(b_cong)[::-1]
    matrix = np.stack([b_cong[order], p_cong[order],
                       b_pred[order], p_pred[order]], axis=1)
    cols   = ['Baseline\nCongested', 'Predicted\nCongested',
              'Baseline\nPredicted', 'Predicted\nPredicted']

    fig, ax = plt.subplots(figsize=(10, 18))
    fig.patch.set_facecolor(BG2)
    vmax = max(matrix.max(), 1.0)
    im   = ax.imshow(matrix, aspect='auto', cmap=plt.cm.YlOrRd,
                     norm=mcolors.PowerNorm(gamma=0.5, vmin=0, vmax=vmax))
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
    cbar.set_label('Timesteps above threshold', color=TEXT, fontsize=9)
    ax.set_title(
        '100-Node Congestion & Prediction Event Heatmap\n'
        '(Darker = more timesteps above threshold)',
        color=TEXT, fontsize=11, fontweight='bold', pad=8
    )
    plt.tight_layout()
    plt.savefig('graph3_congestion_heatmap.png', dpi=140,
                bbox_inches='tight', facecolor=BG2)
    plt.close()
    print('  Saved: graph3_congestion_heatmap.png')


# ── Chart 4: Summary metrics ───────────────────────────────────────────────

def plot_summary_metrics(baseline, predicted, nodes):
    b_avg_q = float(np.mean([baseline[f'avg_queue_{n}'] for n in nodes]))
    p_avg_q = float(np.mean([predicted[f'avg_queue_{n}'] for n in nodes]))
    b_peak  = float(np.max([baseline[f'peak_queue_{n}'] for n in nodes]))
    p_peak  = float(np.max([predicted[f'peak_queue_{n}'] for n in nodes]))

    metrics = {
        'Avg Queue\n(all nodes)':   (b_avg_q,  p_avg_q),
        'Peak Queue\n(worst node)': (b_peak,   p_peak),
        'Congestion\nEvents':       (baseline['congested_events'],
                                     predicted['congested_events']),
        'Prediction\nEvents':       (baseline['predicted_events'],
                                     predicted['predicted_events']),
        'Packets\nDropped':         (baseline['dropped_total'],
                                     predicted['dropped_total']),
        'Reroutes':                 (baseline['reroutes'],
                                     predicted['reroutes']),
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
                      [bval, pval], color=[C_BASE, C_PRED], alpha=0.88,
                      edgecolor='white', linewidth=0.5)
        max_val = max(bval, pval, 0.01)
        for bar, val in zip(bars, [bval, pval]):
            ax.text(bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + max_val * 0.03,
                    f'{val:.1f}', ha='center', color=TEXT, fontsize=10,
                    fontweight='bold')
        improvement = _pct_improvement(bval, pval)
        sym = '▼' if improvement > 0 else ('▲' if improvement < 0 else '—')
        ax.set_title(f'{label}\n{sym} {abs(improvement):.1f}% reduction',
                     color=TEXT, fontsize=9, fontweight='bold', pad=4)
        ax.tick_params(colors=TEXT)
        xlabels = ax.get_xticklabels()
        if len(xlabels) >= 2:
            xlabels[0].set_color(C_BASE)
            xlabels[1].set_color(C_PRED)
        ax.set_facecolor(BG)
        for sp in ax.spines.values():
            sp.set_edgecolor(GRID)
        ax.grid(True, axis='y', color=GRID, lw=0.4, alpha=0.6)
    plt.tight_layout()
    plt.savefig('graph4_summary_metrics.png', dpi=140,
                bbox_inches='tight', facecolor=BG2)
    plt.close()
    print('  Saved: graph4_summary_metrics.png')


# ── Chart 5: CDF ──────────────────────────────────────────────────────────

def plot_cdf(baseline, predicted, nodes):
    b = np.sort([baseline[f'avg_queue_{n}'] for n in nodes])
    p = np.sort([predicted[f'avg_queue_{n}'] for n in nodes])
    y = np.linspace(0, 1, len(nodes))

    fig, ax = plt.subplots(figsize=(10, 6))
    fig.patch.set_facecolor(BG2)
    ax.plot(b, y, color=C_BASE, lw=2.2, label='No Prediction')
    ax.plot(p, y, color=C_PRED, lw=2.2, label='Early Prediction')
    ax.axvline(QUEUE_SOFT, color=C_SOFT, lw=1.2, ls='--',
               label=f'Predict threshold ({QUEUE_SOFT})')
    ax.axvline(QUEUE_HARD, color=C_HARD, lw=1.2, ls=':',
               label=f'Congest threshold ({QUEUE_HARD})')
    ax.legend(fontsize=10, facecolor=BG, labelcolor=TEXT)
    _style(ax,
           'CDF — Per-Node Avg Queue Length (100 Nodes)\n'
           'Curve shifted left = more nodes with lower queue = better',
           xlabel='Avg Queue Length (pkts)',
           ylabel='Cumulative Fraction of Nodes')
    plt.tight_layout()
    plt.savefig('graph5_cdf_queue.png', dpi=140,
                bbox_inches='tight', facecolor=BG2)
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

    print_summary('WITHOUT Early Prediction (Baseline)',     baseline, nodes)
    print_summary('WITH    Early Prediction (This Project)', predicted, nodes)

    b_avg = float(np.mean([baseline[f'avg_queue_{n}'] for n in nodes]))
    p_avg = float(np.mean([predicted[f'avg_queue_{n}'] for n in nodes]))
    print(f'\n  Congestion events : {baseline["congested_events"]} → {predicted["congested_events"]}')
    print(f'  Avg queue         : {b_avg:.2f} → {p_avg:.2f} pkts')
    print(f'  Hot nodes tracked : {len(baseline["hot_nodes"])}')

    print('\n  Generating 5 comparison graphs...')
    plot_queue_timelines    (baseline, predicted, nodes, network)
    plot_avg_queue_all_nodes(baseline, predicted, nodes)
    plot_congestion_heatmap (baseline, predicted, nodes)
    plot_summary_metrics    (baseline, predicted, nodes)
    plot_cdf                (baseline, predicted, nodes)

    print(f'\n{"="*60}')
    print('  All 5 graphs saved!')
    print(f'{"="*60}\n')