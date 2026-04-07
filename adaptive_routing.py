"""
adaptive_routing.py — Improved congestion-aware routing for large networks.

Enhancements:
- Uses Dijkstra (O(E log V)) for scalability
- HARD avoids congested nodes (infinite cost)
- Softly penalizes predicted nodes
- Includes queue length in cost (dynamic load awareness)
"""

import networkx as nx


class AdaptiveRouter:
    def __init__(self, network, monitors):
        self.network = network
        self.monitors = monitors

    def _edge_weight(self, u, v, data):
        """
        Dynamic edge weight based on node state.

        Strategy:
        - Congested nodes → completely avoided (∞ cost)
        - Predicted nodes → moderate penalty
        - Queue length → proportional cost
        """

        # If node has monitoring data
        if v in self.monitors:
            node = self.monitors[v]

            # 🚨 HARD BLOCK: avoid congested nodes completely
            if node.congested:
                return float('inf')

            # Base cost
            cost = 1

            # ⚠️ Soft penalty for predicted congestion
            if node.predicted:
                cost += 20

            # 📦 Queue-based dynamic cost
            cost += node.queue_length * 2

            return cost

        # Default cost if no monitor exists
        return 1

    def find_best_path(self, source, destination, verbose=False):

        # Step 1: remove red nodes
        filtered_graph = self.network.copy()

        removed_nodes = []
        for node_id, monitor in self.monitors.items():
            if monitor.congested:
                if node_id in filtered_graph:
                    filtered_graph.remove_node(node_id)
                    removed_nodes.append(node_id)

        try:
            # Try strict path
            path = nx.dijkstra_path(filtered_graph, source, destination, weight=self._edge_weight)

        except:
            if verbose:
                print("⚠️ No safe path — allowing congested nodes")

            # Fallback: use full graph
            path = nx.dijkstra_path(self.network, source, destination, weight=self._edge_weight)

        return path

    # Alias used by simulation / compare modules
    def best_path(self, src, dst):
        return self.find_best_path(src, dst)