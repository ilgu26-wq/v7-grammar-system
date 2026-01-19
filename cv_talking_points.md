# CV & Interview Talking Points

## Core Bullet Points (Results-Focused)

### For CV
- Designed and validated a market-structure grammar system for futures trading
- 24 independent validation tests passed without parameter changes
- Achieved 94.1% conditional alpha entry rate across 1,406 samples
- Live execution integrity verified (slippage, ordering, duplication)
- Demonstrated asset-agnostic performance across NQ, ES, and BTC
- Recovery Factor of 115.7x with institutionally-sound risk profile

### For Cover Letter Opening
> "I built a trading system that doesn't predict the market—it classifies when the market has already made its decision. After 24 independent validation tests with zero parameter changes, I'm now validating it in live trading."

---

## Interview One-Liners

### System Philosophy
> "This is not a return-maximizing strategy. It is a conditional alpha system that maximizes decision quality under uncertainty."

### On Prediction
> "We don't predict where the market will go. We identify where participants have already agreed it should be."

### On Alpha
> "Our alpha comes from selection-bias elimination, not forecasting. STB achieves 94.1% TP-first because we only enter when consensus is complete."

### On Losses
> "Most drawdowns occur in EE_Low states, which we intentionally do not optimize for returns. This is designed behavior."

### On Validation
> "We validated across six dimensions: asset, time, regime, roll, portfolio, and execution. Zero modifications across 24 tests."

### On Portfolio
> "We diversify on expansion eligibility, not returns. Our 3-asset grammar states show zero triple-simultaneous occurrences."

### Closing Statement
> "This isn't research. This is a system already in operation."

---

## Handling "No Degree" Questions

### Strategy: Don't Explain, Demonstrate

**Wrong:**
> "I didn't finish university because..."

**Right:**
> "I spent that time building and validating this system across 24 independent tests. Here are the results."

### Redirect Questions
- Q: "What's your educational background?"
- A: "I'm self-taught in quantitative finance. My qualification is the system I built—24 validation tests passed, zero modifications, now live trading."

---

## Technical Deep-Dive Preparation

### If Asked About STB
> "STB is a location confirmation signal. It identifies when price reaches favorable coordinates within an already-stabilized direction. It's not predictive—it confirms market consensus."

### If Asked About V7 Grammar
> "V7 Grammar classifies market states into four categories based on expansion eligibility. The key insight: 70% of losses concentrate in EE_Low states. We use this to localize risk, not eliminate it."

### If Asked About Sharpe
> "Our Sharpe is 0.93—not exceptional, but stable. For conditional alpha systems, stability matters more than magnitude. Our Recovery Factor of 115.7x is the more telling metric."

### If Asked About Overfitting
> "Zero parameter changes across ES, BTC, 4 timeframes, 4 extreme events, and 816 paper trades. If it were overfit to NQ 1-minute, it would have failed at least one of these."

---

## Firm-Specific Angles

### For Citadel/Jane Street
- Emphasize: Market-making philosophy alignment
- Key phrase: "We enter only at consensus-complete zones"
- Highlight: Conditional alpha, not predictive

### For Two Sigma
- Emphasize: Statistical validation rigor
- Key phrase: "24 independent hypothesis tests"
- Highlight: Regime robustness, asset-agnostic

### For Prop Firms
- Emphasize: Operational readiness
- Key phrase: "Human-followable, 7.3-minute average signal spacing"
- Highlight: Case F execution integrity

### For Seed Investment
- Emphasize: Portfolio scalability
- Key phrase: "Zero triple-simultaneous occurrence"
- Highlight: Structural independence for capital allocation
