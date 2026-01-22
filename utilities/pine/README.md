# Auxiliary Execution Utilities (PineScript)

These PineScript utilities are **not trading strategies**.

They are execution-context tools designed to operate **alongside the V7 Grammar System**,  
providing **risk suppression, regime awareness, and structural context** only.

No decision authority resides in these scripts.

---

## Design Principles

- **No trade entries or exits**
- **No performance optimization or backtesting**
- **No predictive or directional assumptions**
- Used strictly for **execution filtering and contextual awareness**
- Core decision grammar remains **fully isolated and unaffected**

These utilities are intentionally non-actionable.

---

## Included Utilities

### IVWAP / IVPOC Context
Structural reference levels derived from clustered price–volume behavior.  
Used to evaluate **relative price positioning**, not to trigger execution.

### Spread Day Detector (FLAG)
Identifies abnormal distribution days and regime instability  
based on structural stress, volatility dispersion, and execution risk markers.

Used to **block execution on structurally hostile days**.

### Volatility Spike Filter
Detects tail-risk conditions such as volatility expansion and liquidity stress,  
preventing execution during unstable or non-stationary market phases.

---

## Role in the System

The **V7 Grammar System** determines *when execution is allowed*.  
These utilities help identify *when execution should be avoided*.

They do **not** generate alpha.  
They **prevent structural mistakes**.

Execution authority always remains external to PineScript.
