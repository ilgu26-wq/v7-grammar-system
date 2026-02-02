"""
V7 Shadow Mode Adapter
======================

Shadow Mode Purpose:
- NOT for making profit
- FOR collecting state distributions

Shadow Mode Design:
- WAIT: Log only
- OBSERVE: Virtual entry tracking (hypothetical PnL)
- ENTER: Official entry candidate (still no real orders)

Key Insight:
- "Small profit" = Statistical byproduct of OBSERVE region
- "Entry" = Authenticated profit region (τ≥5, dir≥3, DC extreme)
"""

import json
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from v7_engine_d import V7EngineD, EngineOutputD
from state_profit_analyzer import StateProfitAnalyzer, BarData


@dataclass
class OPAOverlay:
    """
    OPA Overlay - Decision권 없음, 기록만!
    
    OPA는 V7 action을 바꾸지 않는다.
    단지 "OPA가 붙었다면 어땠을지" 기록한다.
    """
    verdict: str           # "ALLOW" or "DENY"
    size: str              # "SMALL", "MED", "LARGE"
    cooldown: bool         # cooldown 적용 여부
    reason: str            # 판단 근거
    force_score: float     # Force 기반 스코어
    risk_score: float      # 위험 스코어
    
    def to_dict(self) -> Dict:
        return {
            "verdict": self.verdict,
            "size": self.size,
            "cooldown": self.cooldown,
            "reason": self.reason,
            "force_score": self.force_score,
            "risk_score": self.risk_score
        }


class OPAOverlayEvaluator:
    """
    OPA Overlay Evaluator
    
    중요: V7 action을 바꾸지 않음!
    오직 "OPA가 붙었다면" 어떤 판단을 했을지 기록만 함.
    
    H-OPA-OVERLAY 가설 검증용:
    - V7 ENTER 후보 중 OPA가 DENY하는 비율
    - OPA size가 Force/DC/τ와 어떤 상관인지
    - OPA cooldown이 실제로 과잉 엔트리를 줄이는지
    """
    
    COOLDOWN_BARS = 5
    
    def __init__(self):
        self.last_entry_bar = -100
        self.current_bar = 0
    
    def evaluate(self, v7_action: str, dc: float, tau: int, 
                 force: float, delta: float) -> OPAOverlay:
        """
        Evaluate OPA overlay for current state
        
        Args:
            v7_action: V7 engine action (WAIT/OBSERVE/ENTER)
            dc: DC value (0-1)
            tau: tau value
            force: Force value
            delta: Delta value
        
        Returns:
            OPAOverlay with verdict/size/cooldown (로그용)
        """
        self.current_bar += 1
        
        in_cooldown = (self.current_bar - self.last_entry_bar) < self.COOLDOWN_BARS
        
        force_score = min(1.0, force / 100.0) if force > 0 else 0.0
        
        risk_score = 0.0
        if dc > 0.8 or dc < 0.2:
            risk_score += 0.3
        if tau < 3:
            risk_score += 0.4
        if abs(delta) > 50:
            risk_score += 0.3
        
        if v7_action == "ENTER":
            if in_cooldown:
                verdict = "DENY"
                reason = f"Cooldown active ({self.COOLDOWN_BARS - (self.current_bar - self.last_entry_bar)} bars left)"
            elif risk_score > 0.7:
                verdict = "DENY"
                reason = f"Risk too high: {risk_score:.2f}"
            else:
                verdict = "ALLOW"
                reason = "Entry conditions met"
                self.last_entry_bar = self.current_bar
        else:
            verdict = "N/A"
            reason = f"V7 action is {v7_action}, OPA not applicable"
        
        if force_score < 0.3:
            size = "SMALL"
        elif force_score < 0.7:
            size = "MED"
        else:
            size = "LARGE"
        
        return OPAOverlay(
            verdict=verdict,
            size=size,
            cooldown=in_cooldown,
            reason=reason,
            force_score=force_score,
            risk_score=risk_score
        )
    
    def reset(self):
        self.last_entry_bar = -100
        self.current_bar = 0


@dataclass
class VirtualPosition:
    """Virtual position for OBSERVE region tracking"""
    entry_price: float
    entry_time: str
    direction: str  # "LONG" or "SHORT"
    entry_type: str  # "OBSERVE" or "ENTER"
    tau_at_entry: int
    dc_at_entry: float
    
    tp_small: float = 0.0  # TP for small profit (5pt)
    tp_full: float = 0.0   # TP for full profit (20pt)
    sl: float = 0.0        # Stop loss
    
    exit_price: Optional[float] = None
    exit_time: Optional[str] = None
    exit_reason: Optional[str] = None
    pnl: float = 0.0
    bars_held: int = 0


@dataclass
class ShadowModeStats:
    """Shadow mode statistics"""
    total_candles: int = 0
    wait_count: int = 0
    observe_count: int = 0
    enter_count: int = 0
    
    virtual_observe_trades: int = 0
    virtual_enter_trades: int = 0
    
    observe_tp_small_hits: int = 0
    observe_tp_full_hits: int = 0
    observe_sl_hits: int = 0
    
    enter_tp_small_hits: int = 0
    enter_tp_full_hits: int = 0
    enter_sl_hits: int = 0
    
    def to_dict(self) -> Dict:
        return asdict(self)


class ShadowModeAdapter:
    """
    Shadow Mode Adapter for V7 Engine
    
    This adapter wraps V7EngineD and adds:
    1. Virtual position tracking for OBSERVE signals
    2. Hypothetical PnL calculation
    3. Distribution collection
    
    NO REAL ORDERS - this is observation only.
    """
    
    TP_SMALL = 5.0   # Small profit target (points)
    TP_FULL = 20.0   # Full profit target (points)
    SL = 15.0        # Stop loss (points)
    
    def __init__(self, encoder_name: str = None):
        self.engine = V7EngineD(encoder_name=encoder_name)
        self.opa_evaluator = OPAOverlayEvaluator()
        self.profit_analyzer = StateProfitAnalyzer()
        self.stats = ShadowModeStats()
        
        self.active_observe_position: Optional[VirtualPosition] = None
        self.active_enter_position: Optional[VirtualPosition] = None
        
        self.closed_positions: List[VirtualPosition] = []
        self.state_distribution: List[Dict] = []
        self.opa_log: List[Dict] = []
        
        self.last_price = 0.0
    
    def process(self, candle: Dict) -> Dict:
        """
        Process candle through V7 engine + shadow tracking
        
        Returns:
            Combined output with engine result + shadow info
        """
        self.stats.total_candles += 1
        
        current_price = candle.get('close', 0.0)
        self.last_price = current_price
        current_time = candle.get('close_time_utc', 
                                   candle.get('time', 
                                              datetime.now(timezone.utc).isoformat()))
        
        output = self.engine.process(candle)
        action = output.action.get('action', 'WAIT')
        direction = output.direction
        tau = output.state.get('tau_hat', 0)
        dc = output.state.get('dc_hat', 0.5)
        
        self._collect_distribution(output)
        
        bar_data = BarData(
            timestamp=current_time,
            open=float(candle.get('open', current_price)),
            high=float(candle.get('high', current_price)),
            low=float(candle.get('low', current_price)),
            close=current_price,
            state=action,
            dc=dc,
            tau=tau,
            force=output.state.get('force_hat', 0),
            delta=output.state.get('delta_hat', 0),
            direction=direction
        )
        self.profit_analyzer.add_bar(bar_data)
        
        opa_overlay = self.opa_evaluator.evaluate(
            v7_action=action,
            dc=dc,
            tau=tau,
            force=output.state.get('force_hat', 0),
            delta=output.state.get('delta_hat', 0)
        )
        
        self.opa_log.append({
            "bar": self.stats.total_candles,
            "v7_action": action,
            "opa_overlay": opa_overlay.to_dict()
        })
        if len(self.opa_log) > 500:
            self.opa_log = self.opa_log[-500:]
        
        if action == 'WAIT':
            self.stats.wait_count += 1
        elif action == 'OBSERVE':
            self.stats.observe_count += 1
            self._handle_observe_signal(current_price, current_time, direction, tau, dc)
        elif action == 'ENTER':
            self.stats.enter_count += 1
            self._handle_enter_signal(current_price, current_time, direction, tau, dc)
        
        self._update_virtual_positions(current_price, current_time)
        
        shadow_info = {
            "shadow_mode": True,
            "virtual_observe_active": self.active_observe_position is not None,
            "virtual_enter_active": self.active_enter_position is not None,
            "stats": self.stats.to_dict(),
            "closed_count": len(self.closed_positions),
            "opa_overlay": opa_overlay.to_dict()
        }
        
        return {
            "engine": output.to_dict(),
            "shadow": shadow_info
        }
    
    def _handle_observe_signal(self, price: float, time: str, 
                                direction: str, tau: int, dc: float):
        """
        Handle OBSERVE signal - create virtual position for tracking
        
        OBSERVE = Pre-authenticated region
        We track "what if" we entered here
        """
        if self.active_observe_position is not None:
            return
        
        inferred_dir = "LONG" if dc <= 0.1 else "SHORT" if dc >= 0.9 else None
        if inferred_dir is None:
            return
        
        if inferred_dir == "LONG":
            tp_small = price + self.TP_SMALL
            tp_full = price + self.TP_FULL
            sl = price - self.SL
        else:
            tp_small = price - self.TP_SMALL
            tp_full = price - self.TP_FULL
            sl = price + self.SL
        
        self.active_observe_position = VirtualPosition(
            entry_price=price,
            entry_time=str(time),
            direction=inferred_dir,
            entry_type="OBSERVE",
            tau_at_entry=tau,
            dc_at_entry=dc,
            tp_small=tp_small,
            tp_full=tp_full,
            sl=sl
        )
        self.stats.virtual_observe_trades += 1
    
    def _handle_enter_signal(self, price: float, time: str,
                              direction: str, tau: int, dc: float):
        """
        Handle ENTER signal - create virtual position for official entry
        
        ENTER = Authenticated region (τ≥5, dir≥3, DC extreme)
        This is the "real" signal but still virtual in shadow mode
        """
        if self.active_enter_position is not None:
            return
        
        inferred_dir = "LONG" if dc <= 0.1 else "SHORT" if dc >= 0.9 else "LONG"
        
        if inferred_dir == "LONG":
            tp_small = price + self.TP_SMALL
            tp_full = price + self.TP_FULL
            sl = price - self.SL
        else:
            tp_small = price - self.TP_SMALL
            tp_full = price - self.TP_FULL
            sl = price + self.SL
        
        self.active_enter_position = VirtualPosition(
            entry_price=price,
            entry_time=str(time),
            direction=inferred_dir,
            entry_type="ENTER",
            tau_at_entry=tau,
            dc_at_entry=dc,
            tp_small=tp_small,
            tp_full=tp_full,
            sl=sl
        )
        self.stats.virtual_enter_trades += 1
    
    def _update_virtual_positions(self, price: float, time: str):
        """Update and check virtual positions for TP/SL hits"""
        
        if self.active_observe_position:
            pos = self.active_observe_position
            pos.bars_held += 1
            
            result = self._check_exit(pos, price)
            if result:
                pos.exit_price = price
                pos.exit_time = str(time)
                pos.exit_reason = result
                
                if pos.direction == "LONG":
                    pos.pnl = price - pos.entry_price
                else:
                    pos.pnl = pos.entry_price - price
                
                if result == "TP_SMALL":
                    self.stats.observe_tp_small_hits += 1
                elif result == "TP_FULL":
                    self.stats.observe_tp_full_hits += 1
                elif result == "SL":
                    self.stats.observe_sl_hits += 1
                
                self.closed_positions.append(pos)
                self.active_observe_position = None
        
        if self.active_enter_position:
            pos = self.active_enter_position
            pos.bars_held += 1
            
            result = self._check_exit(pos, price)
            if result:
                pos.exit_price = price
                pos.exit_time = str(time)
                pos.exit_reason = result
                
                if pos.direction == "LONG":
                    pos.pnl = price - pos.entry_price
                else:
                    pos.pnl = pos.entry_price - price
                
                if result == "TP_SMALL":
                    self.stats.enter_tp_small_hits += 1
                elif result == "TP_FULL":
                    self.stats.enter_tp_full_hits += 1
                elif result == "SL":
                    self.stats.enter_sl_hits += 1
                
                self.closed_positions.append(pos)
                self.active_enter_position = None
    
    def _check_exit(self, pos: VirtualPosition, price: float) -> Optional[str]:
        """Check if position should exit"""
        if pos.direction == "LONG":
            if price >= pos.tp_full:
                return "TP_FULL"
            elif price >= pos.tp_small:
                return "TP_SMALL"
            elif price <= pos.sl:
                return "SL"
        else:
            if price <= pos.tp_full:
                return "TP_FULL"
            elif price <= pos.tp_small:
                return "TP_SMALL"
            elif price >= pos.sl:
                return "SL"
        return None
    
    def _collect_distribution(self, output: EngineOutputD):
        """Collect state distribution for analysis"""
        self.state_distribution.append({
            "action": output.action.get('action'),
            "dc": output.state.get('dc_hat'),
            "tau": output.state.get('tau_hat'),
            "delta": output.state.get('delta_hat'),
            "force": output.state.get('force_hat'),
            "direction": output.direction
        })
        
        if len(self.state_distribution) > 1000:
            self.state_distribution = self.state_distribution[-1000:]
    
    def get_summary(self) -> Dict:
        """Get shadow mode summary"""
        observe_win_rate = 0.0
        enter_win_rate = 0.0
        
        observe_trades = [p for p in self.closed_positions if p.entry_type == "OBSERVE"]
        enter_trades = [p for p in self.closed_positions if p.entry_type == "ENTER"]
        
        if observe_trades:
            wins = sum(1 for p in observe_trades if p.pnl > 0)
            observe_win_rate = wins / len(observe_trades) * 100
        
        if enter_trades:
            wins = sum(1 for p in enter_trades if p.pnl > 0)
            enter_win_rate = wins / len(enter_trades) * 100
        
        return {
            "total_candles": self.stats.total_candles,
            "action_distribution": {
                "WAIT": f"{self.stats.wait_count / max(1, self.stats.total_candles) * 100:.1f}%",
                "OBSERVE": f"{self.stats.observe_count / max(1, self.stats.total_candles) * 100:.1f}%",
                "ENTER": f"{self.stats.enter_count / max(1, self.stats.total_candles) * 100:.1f}%"
            },
            "observe_virtual_trades": {
                "total": len(observe_trades),
                "tp_small": self.stats.observe_tp_small_hits,
                "tp_full": self.stats.observe_tp_full_hits,
                "sl": self.stats.observe_sl_hits,
                "win_rate": f"{observe_win_rate:.1f}%"
            },
            "enter_virtual_trades": {
                "total": len(enter_trades),
                "tp_small": self.stats.enter_tp_small_hits,
                "tp_full": self.stats.enter_tp_full_hits,
                "sl": self.stats.enter_sl_hits,
                "win_rate": f"{enter_win_rate:.1f}%"
            },
            "hypothesis": {
                "OBSERVE_vs_ENTER": "OBSERVE = pre-authenticated, ENTER = authenticated",
                "small_profit": "Statistical byproduct of OBSERVE region",
                "expectation": "ENTER win_rate > OBSERVE win_rate (if theory is correct)"
            }
        }
    
    def save_results(self, filepath: str = "shadow_results.json"):
        """Save shadow mode results to file"""
        results = {
            "summary": self.get_summary(),
            "stats": self.stats.to_dict(),
            "closed_positions": [asdict(p) for p in self.closed_positions[-100:]],
            "engine_stats": self.engine.get_stats()
        }
        with open(filepath, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        return filepath
    
    def get_profit_report(self) -> Dict:
        """Get state→profit analysis report"""
        return self.profit_analyzer.get_report()
    
    def print_profit_report(self):
        """Print state→profit analysis"""
        self.profit_analyzer.print_report()
    
    def get_opa_summary(self) -> Dict:
        """Get OPA overlay summary for H-OPA-OVERLAY verification"""
        enter_logs = [l for l in self.opa_log if l["v7_action"] == "ENTER"]
        
        if not enter_logs:
            return {
                "total_entries": 0,
                "opa_allow": 0,
                "opa_deny": 0,
                "deny_rate": "N/A",
                "size_distribution": {}
            }
        
        allow_count = sum(1 for l in enter_logs if l["opa_overlay"]["verdict"] == "ALLOW")
        deny_count = sum(1 for l in enter_logs if l["opa_overlay"]["verdict"] == "DENY")
        
        sizes = {"SMALL": 0, "MED": 0, "LARGE": 0}
        for l in enter_logs:
            s = l["opa_overlay"]["size"]
            if s in sizes:
                sizes[s] += 1
        
        return {
            "total_entries": len(enter_logs),
            "opa_allow": allow_count,
            "opa_deny": deny_count,
            "deny_rate": f"{deny_count / len(enter_logs) * 100:.1f}%" if enter_logs else "N/A",
            "size_distribution": sizes,
            "hypothesis": "H-OPA-OVERLAY: OPA verdict 분포 분석"
        }
    
    def reset(self):
        """Reset shadow mode state"""
        self.engine.reset()
        self.opa_evaluator.reset()
        self.profit_analyzer = StateProfitAnalyzer()
        self.stats = ShadowModeStats()
        self.active_observe_position = None
        self.active_enter_position = None
        self.closed_positions = []
        self.state_distribution = []
        self.opa_log = []


def test_shadow_mode():
    """Test shadow mode with sample data"""
    shadow = ShadowModeAdapter()
    
    import numpy as np
    np.random.seed(42)
    
    price = 21000.0
    candles = []
    
    for i in range(100):
        change = np.random.randn() * 10
        high_ext = abs(np.random.randn() * 5)
        low_ext = abs(np.random.randn() * 5)
        
        open_price = price
        close_price = price + change
        high_price = max(open_price, close_price) + high_ext
        low_price = min(open_price, close_price) - low_ext
        
        candles.append({
            'open': open_price,
            'high': high_price,
            'low': low_price,
            'close': close_price,
            'close_time_utc': i * 60
        })
        price = close_price
    
    print("=" * 60)
    print("V7 SHADOW MODE TEST")
    print("=" * 60)
    
    for candle in candles:
        result = shadow.process(candle)
    
    summary = shadow.get_summary()
    
    print(f"\nTotal Candles: {summary['total_candles']}")
    print(f"\nAction Distribution:")
    for action, pct in summary['action_distribution'].items():
        print(f"  {action}: {pct}")
    
    print(f"\nOBSERVE Virtual Trades: {summary['observe_virtual_trades']['total']}")
    print(f"ENTER Virtual Trades: {summary['enter_virtual_trades']['total']}")
    
    print(f"\nHypothesis: {summary['hypothesis']['expectation']}")
    
    print("\n" + "=" * 60)
    print("OPA OVERLAY SUMMARY (H-OPA-OVERLAY)")
    print("=" * 60)
    opa_summary = shadow.get_opa_summary()
    print(f"Total ENTER signals: {opa_summary['total_entries']}")
    print(f"OPA ALLOW: {opa_summary['opa_allow']}")
    print(f"OPA DENY: {opa_summary['opa_deny']}")
    print(f"Deny Rate: {opa_summary['deny_rate']}")
    print(f"Size Distribution: {opa_summary['size_distribution']}")
    
    if shadow.opa_log:
        print("\nSample OPA Log (last 5):")
        for log in shadow.opa_log[-5:]:
            print(f"  Bar {log['bar']}: {log['v7_action']} → OPA {log['opa_overlay']['verdict']}")
    
    filepath = shadow.save_results("/tmp/shadow_test_results.json")
    print(f"\nResults saved to: {filepath}")
    
    print("\n" + "=" * 60)
    print("STATE → PROFIT ANALYSIS")
    print("=" * 60)
    shadow.print_profit_report()


if __name__ == "__main__":
    test_shadow_mode()
