# 🚗 Live Trading Directory

This directory contains production execution code.

**Principle:** Ferrari judgment (core/) + Hyundai execution (live/)

---

## Components

| File | Purpose |
|------|---------|
| `main.py` | Main execution loop |
| `broker_adapter.py` | Broker API integration |
| `telegram_logger.py` | Trade notifications |
| `config.yaml` | Runtime configuration |

---

## Responsibilities

### What `live/` handles:
- Slippage management
- Broker API calls
- Order failures and retries
- Reconnection logic
- Telegram alerts
- Position tracking
- Risk checks

### What `live/` does NOT handle:
- Entry logic (→ core/stb_entry.py)
- MFE trailing (→ core/v7_energy_engine.py)
- SL defense (→ core/v7_energy_engine.py)

---

## Safety Rule

> Even if `live/` crashes, `core/` remains untouched.
> This is institutional-grade separation.
