"""
adaptive_routing.py — Scalable path-finding for 100 nodes.

Key change vs 6-node version:
  nx.all_simple_paths() is exponential in the number of nodes — it would
  hang on a 100-node mesh.  We use Dijkstra with a congestion-aware weight
  function: each node's routing score (0/1/3) is added to the edge weight
  of all edges incident to that node, steering paths away from hot nodes.
  This is O(E log V) per call — fast at any scale.
"""

import networkx as nx


class AdaptiveRouter:
    def __init__(self, network, monitors):
        self.network  = network
        self.monitors = monitors

    def _edge_weight(self, u, v, data):
        """Edge weight = base 1 + routing score of both endpoints."""
        score_u = self.monitors[u].get_routing_score() if u in self.monitors else 0
        score_v = self.monitors[v].get_routing_score() if v in self.monitors else 0
        return 1 + score_u + score_v

    def find_best_path(self, source, destination, verbose=False):
        try:
            path = nx.dijkstra_path(
                self.network, source, destination,
                weight=self._edge_weight
            )
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            if verbose:
                print(f'No path between {source} and {destination}')
            return None
        return path

    # Alias used by compare.py / simulation.py
    def best_path(self, src, dst):
        return self.find_best_path(src, dst)