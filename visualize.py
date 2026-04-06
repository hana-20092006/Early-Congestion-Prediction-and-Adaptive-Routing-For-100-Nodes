import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import networkx as nx
from network_setup import create_network
from simulation import run_simulation
from adaptive_routing import AdaptiveRouter


def visualize(duration=100):
    print(f"\nVisualizing simulation for {duration} time units...")

    # Run simulation
    results, monitors = run_simulation(duration=duration)

    # Create network dynamically
    network = create_network(num_nodes=len(monitors))

    # Routing
    router = AdaptiveRouter(network, monitors)
    best_path = router.find_best_path(1, 6)

    # Setup plots
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle('Early Congestion Prediction & Adaptive Routing', fontsize=16, fontweight='bold')

    # ── Plot 1: Network Topology ──────────────────────────────
    ax1 = axes[0, 0]

    # 🔥 Dynamic layout (FIXES your crash)
    pos = nx.spring_layout(network, seed=42)

    node_colors = []
    for node in network.nodes():
        m = monitors[node]
        if m.congested:
            node_colors.append('tomato')
        elif m.predicted:
            node_colors.append('gold')
        else:
            node_colors.append('lightgreen')

    best_path_edges = [(best_path[i], best_path[i+1]) for i in range(len(best_path)-1)] if best_path else []

    edge_colors = [
        'blue' if (u, v) in best_path_edges or (v, u) in best_path_edges else 'gray'
        for u, v in network.edges()
    ]

    edge_widths = [
        3 if (u, v) in best_path_edges or (v, u) in best_path_edges else 1
        for u, v in network.edges()
    ]

    nx.draw(
        network,
        pos,
        ax=ax1,
        with_labels=False,   # 🔥 important for large graphs
        node_color=node_colors,
        node_size=120,
        edge_color=edge_colors,
        width=edge_widths
    )

    red_patch    = mpatches.Patch(color='tomato',     label='Congested Node')
    yellow_patch = mpatches.Patch(color='gold',       label='Predicted (early warning)')
    green_patch  = mpatches.Patch(color='lightgreen', label='OK Node')
    blue_patch   = mpatches.Patch(color='blue',       label='Best Path')

    ax1.legend(handles=[green_patch, yellow_patch, red_patch, blue_patch], loc='lower right', fontsize=8)
    ax1.set_title('Network Topology (Scalable View)', fontsize=11)

    # ── Plot 2: Queue Length — Top Nodes ──────────────────────
    ax2 = axes[0, 1]

    node_ids = sorted(monitors.keys())

    avg_queue_per_node = {}
    for n in node_ids:
        qs = [r['queue'] for r in results if r['node'] == n]
        avg_queue_per_node[n] = sum(qs)/len(qs) if qs else 0

    # 🔥 Top 3 busiest nodes
    top_nodes = sorted(avg_queue_per_node, key=avg_queue_per_node.get, reverse=True)[:3]

    for node_id in top_nodes:
        times  = [r['time']  for r in results if r['node'] == node_id]
        queues = [r['queue'] for r in results if r['node'] == node_id]
        ax2.plot(times, queues, label=f'Node {node_id}')

    ax2.axhline(y=6,  linestyle='--', linewidth=1.5, label='Prediction Threshold')
    ax2.axhline(y=10, linestyle='--', linewidth=1.5, label='Congestion Threshold')

    ax2.set_xlabel('Simulation Time')
    ax2.set_ylabel('Queue Length')
    ax2.set_title(f'Queue Length — Top {len(top_nodes)} Nodes', fontsize=11)
    ax2.legend(fontsize=8)
    ax2.grid(True, alpha=0.3)

    # ── Plot 3: Prediction vs Congestion Events ───────────────
    ax3 = axes[1, 0]

    predicted_counts = [
        sum(1 for r in results if r['node'] == n and r['predicted'])
        for n in node_ids
    ]

    congested_counts = [
        sum(1 for r in results if r['node'] == n and r['congested'])
        for n in node_ids
    ]

    x = range(len(node_ids))
    w = 0.35

    ax3.bar([i - w/2 for i in x], predicted_counts, w, label='Early Prediction')
    ax3.bar([i + w/2 for i in x], congested_counts, w, label='Actual Congestion')

    ax3.set_xticks(list(x))
    ax3.set_xticklabels(node_ids, rotation=90, fontsize=6)

    ax3.set_ylabel('Number of Events')
    ax3.set_title(f'Prediction vs Congestion (All {len(node_ids)} Nodes)', fontsize=11)
    ax3.legend(fontsize=8)

    # ── Plot 4: Avg Queue per Node ────────────────────────────
    ax4 = axes[1, 1]

    avg_queues = []
    for n in node_ids:
        qs = [r['queue'] for r in results if r['node'] == n]
        avg_queues.append(sum(qs)/len(qs) if qs else 0)

    colors = []
    for n in node_ids:
        m = monitors[n]
        if m.congested:
            colors.append('tomato')
        elif m.predicted:
            colors.append('gold')
        else:
            colors.append('lightgreen')

    ax4.bar(node_ids, avg_queues, color=colors)

    ax4.set_xticks(node_ids)
    ax4.set_xticklabels(node_ids, rotation=90, fontsize=6)

    ax4.axhline(y=6, linestyle='--', linewidth=1.5, label='Prediction Threshold')
    ax4.axhline(y=10, linestyle='--', linewidth=1.5, label='Congestion Threshold')

    ax4.set_ylabel('Average Queue Length')
    ax4.set_title(f'Average Queue per Node ({len(node_ids)} Nodes)', fontsize=11)
    ax4.legend(fontsize=8)

    # ── Final Layout ──────────────────────────────────────────
    plt.tight_layout()
    plt.savefig('results.png', dpi=150, bbox_inches='tight')

    print("\n✅ Chart saved as results.png")

    plt.show()


if __name__ == '__main__':
    visualize(duration=100)