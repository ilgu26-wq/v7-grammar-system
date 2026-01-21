# validation/run_validation.py

from core.v7_energy_engine import V7EnergyEngine, check_stb_entry
import numpy as np


def run_backtest(candles, use_g3: bool):
    engine = V7EnergyEngine()

    # 🔒 G3 OFF = baseline
    if not use_g3:
        engine.LWS_BARS = 9999
        engine.LWS_MFE_THRESHOLD = float("inf")

    trade_id = 0
    open_trades = {}
    results = []

    for i in range(len(candles)):
        candle = candles[i]
        history = candles[:i]

        # STB 진입
        direction = check_stb_entry(candle, history)
        if direction:
            tid = f"T{trade_id}"
            engine.open_position(
                trade_id=tid,
                direction=direction,
                entry_price=candle["close"],
                entry_time=candle["time"],
            )
            open_trades[tid] = True
            trade_id += 1

        # 포지션 업데이트
        for tid in list(open_trades.keys()):
            exit_type, pnl = engine.update_position(
                tid,
                high=candle["high"],
                low=candle["low"],
                close=candle["close"],
            )
            if exit_type:
                results.append(pnl)
                del open_trades[tid]

    return summarize(results)


def summarize(pnls):
    if not pnls:
        return {}

    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]

    return {
        "trades": len(pnls),
        "win_rate": len(wins) / len(pnls),
        "ev": float(np.mean(pnls)),
        "avg_loss": float(np.mean(losses)) if losses else 0.0,
        "total_pnl": float(np.sum(pnls)),
    }


def compare(core, g3):
    if not core or not g3:
        return {
            "status": "NO_TRADES",
            "core_trades": core.get("trades", 0),
            "g3_trades": g3.get("trades", 0),
        }

    return {
        "win_rate_diff": g3["win_rate"] - core["win_rate"],
        "ev_diff": g3["ev"] - core["ev"],
        "avg_loss_diff": g3["avg_loss"] - core["avg_loss"],
        "total_pnl_diff": g3["total_pnl"] - core["total_pnl"],
    }
