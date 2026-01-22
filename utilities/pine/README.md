@"
# Auxiliary Execution Utilities (PineScript)

These PineScript utilities are NOT trading strategies.

They are operational tools used alongside the V7 Grammar System
to provide execution context and risk suppression signals.

## Design Principles

- No entries or exits are generated
- No performance optimization
- No predictive assumptions
- Used only to block or contextualize execution
- Core decision logic remains unaffected

## Included Utilities

- IVWAP / IVPOC  
  Structural reference levels for contextual price positioning.

- Spread Day Detector  
  Identifies abnormal distribution days and regime anomalies.

- Volatility Spike Filter  
  Detects tail-risk conditions to suppress execution during instability.

## Role in the System

The V7 Grammar System defines when execution is allowed.  
These utilities help identify when execution should be avoided.

They do not generate alpha.  
They prevent structural mistakes.
"@ | Set-Content utilities\pine\README.md
