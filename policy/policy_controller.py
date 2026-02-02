#!/usr/bin/env python3
"""
Policy-C Layer: Execution Control ONLY

This layer does NOT modify V7 decisions or OPA logic.
It only controls WHEN and HOW MUCH to execute.

BOUNDARY: See docs/FINAL_POLICY_BOUNDARY.md
"""

from datetime import datetime
from typing import Dict, Optional
import json

class PolicyController:
    """
    Policy Layer for execution control.
    
    Allowed:
    - Size adjustment
    - Cooldown control
    - Position gating
    - Force OBSERVE
    
    Forbidden:
    - Signal modification
    - Entry condition change
    - Theta rule modification
    """
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or self._default_config()
        self.state = {
            "consecutive_losses": 0,
            "policy_state": "ACTIVE",
            "last_trade_result": None,
            "cooldown_until": None,
            "trade_history": []
        }
        self.log = []
    
    def _default_config(self) -> Dict:
        return {
            "C1_loss_brake": {
                "enabled": True,
                "max_consecutive_losses": 3,
                "cooldown_bars": 5
            },
            "C2_delta_sizing": {
                "enabled": True,
                "high_delta_threshold": 3.0,
                "high_delta_multiplier": 1.5,
                "low_delta_threshold": 1.0,
                "low_delta_multiplier": 0.5
            },
            "C3_range_protection": {
                "enabled": True,
                "range_loss_threshold": 2,
                "force_observe": True
            }
        }
    
    def evaluate(self, v7_decision: Dict, market_context: Dict) -> Dict:
        """
        Evaluate policy controls.
        
        Returns policy decision that wraps (not modifies) V7 decision.
        """
        result = {
            "timestamp": datetime.now().isoformat(),
            "v7_action": v7_decision.get("action"),
            "v7_direction": v7_decision.get("direction"),
            "policy_action": "ALLOW",
            "size_multiplier": 1.0,
            "policy_reason": None,
            "state_snapshot": self.state.copy()
        }
        
        if v7_decision.get("action") != "ENTRY":
            result["policy_action"] = "PASSTHROUGH"
            return result
        
        delta = market_context.get("delta", 1.0)
        regime = market_context.get("regime", "UNKNOWN")
        
        c1_result = self._check_c1_loss_brake()
        if c1_result["block"]:
            result["policy_action"] = "BLOCK"
            result["policy_reason"] = c1_result["reason"]
            self._log_policy_event("C1_BLOCK", result)
            return result
        
        c2_result = self._check_c2_delta_sizing(delta)
        result["size_multiplier"] = c2_result["multiplier"]
        
        c3_result = self._check_c3_range_protection(regime)
        if c3_result["force_observe"]:
            result["policy_action"] = "FORCE_OBSERVE"
            result["policy_reason"] = c3_result["reason"]
            self._log_policy_event("C3_OBSERVE", result)
            return result
        
        if c2_result["multiplier"] != 1.0:
            result["policy_reason"] = f"C2_SIZE_{c2_result['multiplier']}x"
        
        self._log_policy_event("ALLOW", result)
        return result
    
    def _check_c1_loss_brake(self) -> Dict:
        """C1: Consecutive Loss Brake"""
        config = self.config["C1_loss_brake"]
        
        if not config["enabled"]:
            return {"block": False, "reason": None}
        
        if self.state["policy_state"] == "COOLDOWN":
            return {
                "block": True,
                "reason": f"COOLDOWN (losses={self.state['consecutive_losses']})"
            }
        
        if self.state["consecutive_losses"] >= config["max_consecutive_losses"]:
            self.state["policy_state"] = "COOLDOWN"
            return {
                "block": True,
                "reason": f"C1_BRAKE (streak={self.state['consecutive_losses']})"
            }
        
        return {"block": False, "reason": None}
    
    def _check_c2_delta_sizing(self, delta: float) -> Dict:
        """C2: Δ Variance Size Gating"""
        config = self.config["C2_delta_sizing"]
        
        if not config["enabled"]:
            return {"multiplier": 1.0}
        
        if delta >= config["high_delta_threshold"]:
            return {"multiplier": config["high_delta_multiplier"]}
        elif delta < config["low_delta_threshold"]:
            return {"multiplier": config["low_delta_multiplier"]}
        else:
            return {"multiplier": 1.0}
    
    def _check_c3_range_protection(self, regime: str) -> Dict:
        """C3: RANGE Regime Protection"""
        config = self.config["C3_range_protection"]
        
        if not config["enabled"]:
            return {"force_observe": False, "reason": None}
        
        if regime == "RANGE":
            if self.state["consecutive_losses"] >= config["range_loss_threshold"]:
                return {
                    "force_observe": True,
                    "reason": f"C3_RANGE_PROTECT (losses={self.state['consecutive_losses']})"
                }
        
        return {"force_observe": False, "reason": None}
    
    def record_trade_result(self, result: str, pnl: float):
        """
        Record trade result for state tracking.
        
        result: "WIN" or "LOSS"
        """
        self.state["last_trade_result"] = result
        self.state["trade_history"].append({
            "ts": datetime.now().isoformat(),
            "result": result,
            "pnl": pnl
        })
        
        if result == "LOSS":
            self.state["consecutive_losses"] += 1
        else:
            self.state["consecutive_losses"] = 0
            if self.state["policy_state"] == "COOLDOWN":
                self.state["policy_state"] = "ACTIVE"
    
    def reset_cooldown(self):
        """Manual cooldown reset (e.g., after N bars)"""
        self.state["policy_state"] = "ACTIVE"
        self.state["consecutive_losses"] = 0
    
    def _log_policy_event(self, event_type: str, data: Dict):
        """Log policy decision for audit"""
        self.log.append({
            "ts": datetime.now().isoformat(),
            "event": event_type,
            "data": data
        })
    
    def get_state(self) -> Dict:
        """Get current policy state"""
        return {
            "state": self.state,
            "config": self.config,
            "log_count": len(self.log)
        }
    
    def export_log(self, path: str):
        """Export policy log to file"""
        with open(path, 'w') as f:
            json.dump({
                "exported": datetime.now().isoformat(),
                "state": self.state,
                "log": self.log
            }, f, indent=2)


if __name__ == "__main__":
    policy = PolicyController()
    
    print("Policy Controller Initialized")
    print(f"Config: {json.dumps(policy.config, indent=2)}")
    
    v7_decision = {"action": "ENTRY", "direction": "SHORT"}
    market = {"delta": 0.5, "regime": "TREND"}
    
    result = policy.evaluate(v7_decision, market)
    print(f"\nTest 1 (delta=0.5, TREND):")
    print(f"  Action: {result['policy_action']}")
    print(f"  Size: {result['size_multiplier']}x")
    
    for i in range(4):
        policy.record_trade_result("LOSS", -15)
    
    result = policy.evaluate(v7_decision, market)
    print(f"\nTest 2 (after 4 losses):")
    print(f"  Action: {result['policy_action']}")
    print(f"  Reason: {result['policy_reason']}")
