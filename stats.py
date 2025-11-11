#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
📊 Statistics Manager
مدير الإحصائيات المركزي - ملف منفصل لتجنب Circular Import
"""

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

STATS_FILE = "request_stats.json"


@dataclass
class RequestStats:
    """Track request statistics"""

    total_requests: int = 0
    csrf_refreshes: int = 0
    batch_fetches: int = 0
    cache_hits: int = 0
    errors: int = 0
    fast_detections: int = 0
    burst_activations: int = 0
    adaptive_adjustments: int = 0
    last_reset: str = datetime.now().isoformat()

    def save(self):
        try:
            with open(STATS_FILE, "w") as f:
                json.dump(asdict(self), f, indent=2)
        except Exception as e:
            print(f"❌ Error saving stats: {e}")

    @classmethod
    def load(cls):
        if Path(STATS_FILE).exists():
            try:
                with open(STATS_FILE, "r") as f:
                    data = json.load(f)
                return cls(**data)
            except:
                pass
        return cls()


# Global stats instance
stats = RequestStats.load()
