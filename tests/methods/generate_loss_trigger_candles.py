# validation/generate_loss_trigger_candles.py

def generate_loss_trigger_candles():
    candles = []
    price = 1000.0

    # 1) History 확보 (50봉)
    for i in range(50):
        o = price
        c = price + (1 if i % 2 == 0 else -1)
        h = max(o, c) + 2
        l = min(o, c) - 2
        candles.append({
            "time": f"h{i}",
            "open": o,
            "high": h,
            "low": l,
            "close": c,
        })
        price = c

    # 2) STB 강제 (LONG)
    o = price - 5
    c = price + 30
    h = c + 5
    l = o - 2
    candles.append({
        "time": "stb",
        "open": o,
        "high": h,
        "low": l,
        "close": c,
    })
    price = c

    # 3) LWS 구간 (4봉 정체, MFE < 1.5)
    for i in range(4):
        o = price
        c = price + (0.3 if i % 2 == 0 else -0.3)
        h = max(o, c) + 0.7
        l = min(o, c) - 0.7
        candles.append({
            "time": f"lws{i}",
            "open": o,
            "high": h,
            "low": l,
            "close": c,
        })
        price = c

    # 4) 급락 → SL 히트
    o = price
    c = price - 40
    h = o + 1
    l = c - 5
    candles.append({
        "time": "dump",
        "open": o,
        "high": h,
        "low": l,
        "close": c,
    })

    return candles
