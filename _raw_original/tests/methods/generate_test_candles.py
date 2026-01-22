# validation/generate_test_candles.py
"""
Deterministic candle generator for STB triggering.

Purpose:
- Force STB entries for validation
- Ensure reproducible CORE vs G3 comparison
"""

import random

def generate_stb_test_candles(n=80):
    candles = []
    price = 1000.0

    # 1️⃣ 초기 안정 구간 (history 확보용)
    for i in range(50):
        open_p = price
        close_p = price + random.uniform(-2, 2)
        high_p = max(open_p, close_p) + random.uniform(1, 3)
        low_p = min(open_p, close_p) - random.uniform(1, 3)

        candles.append({
            "time": f"t{i}",
            "open": open_p,
            "high": high_p,
            "low": low_p,
            "close": close_p,
        })
        price = close_p

    # 2️⃣ STB 강제 캔들 (LONG 유도)
    for i in range(50, n):
        open_p = price - 5
        close_p = price + 25      # 큰 바디 (body_z ↑)
        low_p = open_p - 2
        high_p = close_p + 5      # channel 확장

        candles.append({
            "time": f"t{i}",
            "open": open_p,
            "high": high_p,
            "low": low_p,
            "close": close_p,
        })
        price = close_p

    return candles
