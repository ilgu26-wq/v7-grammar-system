from validation.run_validation import run_backtest, compare
from validation.generate_loss_trigger_candles import generate_loss_trigger_candles

candles = generate_loss_trigger_candles()

core = run_backtest(candles, use_g3=False)
g3   = run_backtest(candles, use_g3=True)

print("CORE:", core)
print("G3:", g3)
print("DIFF:", compare(core, g3))
