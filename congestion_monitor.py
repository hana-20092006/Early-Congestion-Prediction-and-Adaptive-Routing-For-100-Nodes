"""
congestion_monitor.py — Same two-stage detection logic, scales to N nodes.
Thresholds are identical to the 6-node version so results are comparable.
"""

# ── Hard thresholds (actual congestion) ──────────────────────
QUEUE_THRESHOLD = 10    # More than 10 packets waiting = congested
DELAY_THRESHOLD = 0.05  # More than 50ms delay = congested
RATE_THRESHOLD  = 80    # More than 80 packets/sec = congested

# ── Soft thresholds (early prediction) ───────────────────────
PREDICT_QUEUE = 6       # 60% of QUEUE_THRESHOLD
PREDICT_DELAY = 0.03    # 60% of DELAY_THRESHOLD
PREDICT_RATE  = 55      # 70% of RATE_THRESHOLD


class NodeMonitor:
    def __init__(self, node_id):
        self.node_id       = node_id
        self.queue_length  = 0
        self.delay         = 0.0
        self.traffic_rate  = 0
        self.congestion_score = 0
        self.predicted     = False
        self.congested     = False

    def update(self, queue_length=None, delay=None, traffic_rate=None):
        if queue_length is not None:
            self.queue_length = queue_length
        if delay is not None:
            self.delay = delay
        if traffic_rate is not None:
            self.traffic_rate = traffic_rate
        self.predict_congestion()

    def predict_congestion(self):
        hard = 0
        if self.queue_length > QUEUE_THRESHOLD: hard += 1
        if self.delay        > DELAY_THRESHOLD: hard += 1
        if self.traffic_rate > RATE_THRESHOLD:  hard += 1
        self.congestion_score = hard
        self.congested = hard >= 2

        soft = 0
        if self.queue_length > PREDICT_QUEUE: soft += 1
        if self.delay        > PREDICT_DELAY: soft += 1
        if self.traffic_rate > PREDICT_RATE:  soft += 1
        self.predicted = (soft >= 2) and not self.congested
        return self.predicted or self.congested

    def get_routing_score(self):
        if self.congested:
            return 1000   # VERY HIGH → avoid completely
        if self.predicted:
            return 50     # moderate penalty
        return 1          # small base cost

    def report(self):
        if self.congested:
            status = 'CONGESTED'
        elif self.predicted:
            status = 'PREDICTED'
        else:
            status = 'OK'
        print(f'  Node {self.node_id:3d}: Q={self.queue_length:4d}  '
              f'delay={self.delay:.3f}s  rate={self.traffic_rate:4d}  [{status}]')