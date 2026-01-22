"""
State Logger
============

θ 상태 히스토리 로깅

로그 구조:
- timestamp
- signal
- state_history (θ 전이 경로)
- execution (진입/청산 정보)
"""

import json
from dataclasses import dataclass, asdict
from typing import List, Optional
from datetime import datetime


@dataclass
class StateEvent:
    """상태 이벤트"""
    bar: int
    theta: int
    event: str
    sensors: Optional[dict] = None


@dataclass
class ExecutionLog:
    """실행 로그"""
    entry_bar: int
    entry_theta: int
    exit_bar: Optional[int] = None
    exit_theta: Optional[int] = None
    result: Optional[str] = None
    pnl: Optional[float] = None


@dataclass
class TradeLog:
    """트레이드 로그"""
    timestamp: str
    signal: str
    state_history: List[StateEvent]
    execution: ExecutionLog
    notes: str = ""


class StateLogger:
    """상태 로거"""
    
    def __init__(self):
        self.logs: List[TradeLog] = []
        self.current_trade: Optional[TradeLog] = None
    
    def start_trade(self, signal: str):
        """트레이드 시작"""
        self.current_trade = TradeLog(
            timestamp=datetime.now().isoformat(),
            signal=signal,
            state_history=[],
            execution=ExecutionLog(entry_bar=0, entry_theta=0),
        )
    
    def log_state(self, bar: int, theta: int, event: str, sensors: dict = None):
        """상태 이벤트 로깅"""
        if self.current_trade is None:
            return
        
        self.current_trade.state_history.append(
            StateEvent(bar=bar, theta=theta, event=event, sensors=sensors)
        )
    
    def log_entry(self, bar: int, theta: int):
        """진입 로깅"""
        if self.current_trade is None:
            return
        
        self.current_trade.execution.entry_bar = bar
        self.current_trade.execution.entry_theta = theta
    
    def log_exit(self, bar: int, theta: int, result: str, pnl: float):
        """청산 로깅"""
        if self.current_trade is None:
            return
        
        self.current_trade.execution.exit_bar = bar
        self.current_trade.execution.exit_theta = theta
        self.current_trade.execution.result = result
        self.current_trade.execution.pnl = pnl
    
    def end_trade(self, notes: str = ""):
        """트레이드 종료"""
        if self.current_trade is None:
            return
        
        self.current_trade.notes = notes
        self.logs.append(self.current_trade)
        self.current_trade = None
    
    def export_json(self, filepath: str):
        """JSON으로 내보내기"""
        data = [asdict(log) for log in self.logs]
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def get_summary(self) -> dict:
        """요약 반환"""
        if not self.logs:
            return {"total": 0}
        
        return {
            "total": len(self.logs),
            "tp": sum(1 for l in self.logs if l.execution.result == "TP"),
            "sl": sum(1 for l in self.logs if l.execution.result == "SL"),
            "total_pnl": sum(l.execution.pnl or 0 for l in self.logs),
        }
