# STB–EE Relationship Analysis

This analysis evaluates the relationship between STB entry strictness
and post-entry Expansion Eligibility (EE).

---

## STB Threshold vs EE_HIGH Ratio

| STB Condition | Decisions | EE_HIGH Ratio | EE_HIGH Win Rate | EE_LOW Win Rate |
|---------------|-----------|---------------|------------------|-----------------|
| 90 / 10       | 108       | 69.4%         | 100.0%           | 12.1%           |
| 85 / 15       | 230       | 61.7%         | 100.0%           | 14.8%           |
| 80 / 20       | 364       | 61.0%         | 100.0%           | 12.7%           |
| 75 / 25       | 522       | 61.7%         | 100.0%           | 11.5%           |

Stricter STB thresholds increase the probability of EE_HIGH outcomes,
while EE itself determines continuation quality.

---

## Directional Breakdown (STB 90 / 10)

| Direction | Trades | EE_HIGH | EE_LOW | Avg MFE | Avg MAE |
|-----------|--------|---------|--------|---------|---------|
| Short     | 60     | 75.0%   | 25.0%  | 20.1pt  | 12.9pt  |
| Long      | 48     | 62.5%   | 37.5%  | 18.9pt  | 17.4pt  |

Short-side setups show higher EE_HIGH frequency.

---

## Sector Extremity vs EE

Sector extremity shows weak correlation with EE outcomes
(correlation coefficient: -0.089),
indicating that EE is not a function of entry extremity,
but a post-entry structural property.

---

## Conclusion

- STB acts as a high-quality entry filter.
- EE acts as a post-entry continuation classifier.
- Entry strictness increases EE_HIGH probability,
  but EE determines continuation success.

STB and EE operate on different decision layers
and are structurally complementary.
