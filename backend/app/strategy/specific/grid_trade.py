from app.strategy.base import BaseStrategy
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Any, List, Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class GridNode:
    """
    A concrete grid buy level.

    The node is occupied only after a real GRID_BUY succeeds. Base position is
    tracked only at account level and never marks grid nodes as occupied.
    """
    price: float
    volume: int = 0
    buy_price: float = 0.0
    buy_amount: float = 0.0
    buy_commission: float = 0.0
    buy_slippage_cost: float = 0.0

    def occupy(self, trade: Dict[str, Any]):
        """Persist the real position opened by a GRID_BUY at this node."""
        self.volume = int(trade["volume"])
        self.buy_price = float(trade["price"])
        self.buy_amount = float(trade["amount"])
        self.buy_commission = float(trade["commission"])
        self.buy_slippage_cost = float(trade["slippage_cost"])

    def release(self):
        """Clear this node after its paired GRID_SELL completes."""
        self.volume = 0
        self.buy_price = 0.0
        self.buy_amount = 0.0
        self.buy_commission = 0.0
        self.buy_slippage_cost = 0.0

    @property
    def is_idle(self) -> bool:
        return self.volume <= 0

    @property
    def is_occupied(self) -> bool:
        return self.volume > 0

    def __repr__(self):
        return f"GridNode(price={self.price:.3f}, volume={self.volume})"


class GridTradingStrategy(BaseStrategy):
    """
    Stateful daily-close grid strategy.

    Rules:
    - Only close-to-close grid crossings trigger trades.
    - Base position is independent from grid positions.
    - A grid node can be sold only if it was previously opened by GRID_BUY.
    """

    def __init__(self, df, params, initial_capital, commission_rate, slippage):
        super().__init__(df, params, initial_capital, commission_rate, slippage)

        self.lower_bound = float(params.get("lower_bound", 20.0))
        self.upper_bound = float(params.get("upper_bound", 30.0))
        self.grid_step_pct = float(params.get("grid_step_pct", 5.0))
        self.grid_type = params.get("grid_type", "geometric")
        self.grid_count = int(params.get("grid_count", 20))
        self.base_position_ratio = float(params.get("base_position_ratio", 0.5))
        self.trade_mode = params.get("trade_mode", "amount")
        self.funds_per_grid = float(params.get("funds_per_grid", 10000.0))

        self._validate_params()
        self.grid_step_ratio = self._percent_to_ratio(self.grid_step_pct)

        self.completed_cycles = 0
        self.winning_cycles = 0
        self.realized_grid_profit = 0.0

        self.grid_nodes: List[GridNode] = self._build_grid_nodes()
        self.last_grid_idx = -1

    # ------------------------------------------------------------------
    # Parameter and grid setup
    # ------------------------------------------------------------------

    def _validate_params(self):
        if self.initial_capital <= 0:
            raise ValueError("initial_capital 必须大于 0")
        if self.commission_rate < 0:
            raise ValueError("commission_rate 不能为负")
        if self.slippage < 0:
            raise ValueError("slippage 不能为负")
        if self.lower_bound <= 0:
            raise ValueError("lower_bound 必须大于 0")
        if self.upper_bound <= self.lower_bound:
            raise ValueError("upper_bound 必须大于 lower_bound")
        if self.grid_step_pct <= 0:
            raise ValueError("grid_step_pct 必须大于 0，例如 5 表示 5%")
        if self.grid_type not in {"geometric", "arithmetic"}:
            raise ValueError("grid_type 必须是 geometric 或 arithmetic")
        if self.grid_type == "arithmetic" and self.grid_count <= 0:
            raise ValueError("grid_count 必须大于 0")
        if not 0 <= self.base_position_ratio <= 1:
            raise ValueError("base_position_ratio 必须在 0 到 1 之间")
        if self.trade_mode not in {"amount", "volume"}:
            raise ValueError("trade_mode 必须是 amount 或 volume")
        if self.funds_per_grid <= 0:
            raise ValueError("funds_per_grid 必须大于 0")

    def _percent_to_ratio(self, value: float) -> float:
        """Convert API/user percent input to calculation ratio. 5 means 5%."""
        ratio = float(value) / 100
        if ratio <= 0:
            raise ValueError("grid_step_pct 必须大于 0，例如 5 表示 5%")
        return ratio

    def _build_grid_nodes(self) -> List[GridNode]:
        prices = []
        if self.grid_type == "arithmetic":
            step = (self.upper_bound - self.lower_bound) / self.grid_count
            prices = [self.lower_bound + i * step for i in range(self.grid_count + 1)]
        else:
            current = self.lower_bound
            while current <= self.upper_bound * 1.0001:
                prices.append(current)
                current *= (1 + self.grid_step_ratio)

        return [GridNode(price) for price in prices]

    def _grid_prices(self) -> List[float]:
        return [node.price for node in self.grid_nodes]

    def _find_nearest_grid_idx(self, price: float) -> int:
        """
        Return the rightmost grid line index at or below price.
        -1 means price is below the lower bound.
        """
        for i in range(len(self.grid_nodes) - 1, -1, -1):
            if price >= self.grid_nodes[i].price:
                return i
        return -1

    # ------------------------------------------------------------------
    # Backtest lifecycle
    # ------------------------------------------------------------------

    def execute(self) -> Dict[str, Any]:
        if self.df is None or self.df.is_empty():
            logger.warning("历史数据不足或为空，网格回测强制跳过产出空结果。")
            return self._build_empty_response()

        selected_df = self.df.select(["日期", "开盘", "收盘"])

        for row in selected_df.iter_rows(named=True):
            raw_date = row["日期"]
            date_str = raw_date.strftime("%Y-%m-%d %H:%M:%S") if isinstance(raw_date, datetime) else str(raw_date)
            open_price = row["开盘"]
            close_price = row["收盘"]

            if self.last_grid_idx == -1:
                self._initialize_base_position(date_str, open_price)
                self.last_grid_idx = self._find_nearest_grid_idx(close_price)
                self._record_equity_snapshot(date_str, close_price)
                continue

            current_grid_idx = self._find_nearest_grid_idx(close_price)

            if current_grid_idx > self.last_grid_idx:
                self._handle_upward_cross(date_str, current_grid_idx)
            elif current_grid_idx < self.last_grid_idx:
                self._handle_downward_cross(date_str, current_grid_idx)

            self.last_grid_idx = current_grid_idx
            self._record_equity_snapshot(date_str, close_price)

        return {
            "metrics": self._calculate_metrics(),
            "equity_curve": self.equity_curve,
            "execution_records": self.trade_logs
        }

    def _handle_downward_cross(self, date: str, current_grid_idx: int):
        for step in range(self.last_grid_idx - current_grid_idx):
            buy_at_idx = self.last_grid_idx - step - 1
            if 0 <= buy_at_idx < len(self.grid_nodes):
                buy_node = self.grid_nodes[buy_at_idx]
                if buy_node.is_idle:
                    bought = self._buy(date, buy_node.price, "GRID_BUY")
                    if bought:
                        buy_node.occupy(bought)

    def _handle_upward_cross(self, date: str, current_grid_idx: int):
        for step in range(current_grid_idx - self.last_grid_idx):
            sell_at_idx = self.last_grid_idx + step + 1
            buy_at_idx = self.last_grid_idx + step
            if 0 <= buy_at_idx < len(self.grid_nodes) and 0 <= sell_at_idx < len(self.grid_nodes):
                buy_node = self.grid_nodes[buy_at_idx]
                if buy_node.is_occupied:
                    sold = self._sell(date, self.grid_nodes[sell_at_idx].price, "GRID_SELL", expected_volume=buy_node.volume)
                    if sold:
                        cycle_profit = sold["amount"] - buy_node.buy_amount
                        self.completed_cycles += 1
                        self.realized_grid_profit += cycle_profit
                        if cycle_profit > 0:
                            self.winning_cycles += 1
                        buy_node.release()

    # ------------------------------------------------------------------
    # Execution helpers
    # ------------------------------------------------------------------

    def _initialize_base_position(self, date: str, price: float):
        target_cost = self.initial_capital * self.base_position_ratio
        shares_to_buy = int(target_cost / (price + self.slippage) / 100) * 100
        if shares_to_buy > 0:
            self._buy(date, price, "BASE_OPEN", expected_volume=shares_to_buy)

    def _buy(self, date: str, trigger_price: float, action_type: str, expected_volume: int = None) -> Optional[Dict[str, Any]]:
        exec_price = trigger_price + self.slippage

        if expected_volume is None:
            if self.trade_mode == "amount":
                volume = int(self.funds_per_grid / exec_price / 100) * 100
            else:
                volume = int(self.funds_per_grid / 100) * 100
        else:
            volume = int(expected_volume)

        if volume <= 0:
            return None

        cost = exec_price * volume
        commission = cost * self.commission_rate
        total_cost = cost + commission
        slippage_cost = self.slippage * volume

        if self.cash < total_cost:
            return None

        self.cash -= total_cost
        self.position += volume
        trade = {
            "price": exec_price,
            "volume": volume,
            "amount": total_cost,
            "commission": commission,
            "slippage_cost": slippage_cost
        }
        self._record_trade_log(date, action_type, exec_price, volume, total_cost, commission, slippage_cost)
        return trade

    def _sell(self, date: str, trigger_price: float, action_type: str, expected_volume: int = None) -> Optional[Dict[str, Any]]:
        exec_price = max(0.01, trigger_price - self.slippage)

        if expected_volume is not None:
            volume = int(expected_volume)
            if self.position < volume:
                return None
        elif self.trade_mode == "amount":
            volume = int(self.funds_per_grid / exec_price / 100) * 100
            volume = min(volume, self.position)
        else:
            volume = int(self.funds_per_grid / 100) * 100
            volume = min(volume, self.position)

        if volume <= 0:
            return None

        revenue = exec_price * volume
        commission = revenue * self.commission_rate
        net_revenue = revenue - commission
        slippage_cost = self.slippage * volume

        self.cash += net_revenue
        self.position -= volume
        trade = {
            "price": exec_price,
            "volume": volume,
            "amount": net_revenue,
            "commission": commission,
            "slippage_cost": slippage_cost
        }
        self._record_trade_log(date, action_type, exec_price, volume, net_revenue, commission, slippage_cost)
        return trade

    # ------------------------------------------------------------------
    # Metrics and fallback
    # ------------------------------------------------------------------

    def _calculate_metrics(self) -> Dict[str, Any]:
        final_net_value = self.equity_curve[-1]["net_value"] if self.equity_curve else self.initial_capital
        total_return = (final_net_value - self.initial_capital) / self.initial_capital

        max_drawdown = 0.0
        if self.equity_curve:
            max_drawdown = max(record["drawdown"] for record in self.equity_curve)

        grid_trades = [
            log for log in self.trade_logs
            if log["action"] in {"GRID_BUY", "GRID_SELL"}
        ]
        win_rate = self.winning_cycles / self.completed_cycles if self.completed_cycles > 0 else 0.0

        return {
            "total_return": round(total_return, 4),
            "annualized_return": 0.0,
            "max_drawdown": round(max_drawdown, 4),
            "win_rate": round(win_rate, 4),
            "total_trades": len(grid_trades)
        }

    def _build_empty_response(self) -> Dict[str, Any]:
        return {
            "metrics": {
                "total_return": 0.0,
                "annualized_return": 0.0,
                "max_drawdown": 0.0,
                "win_rate": 0.0,
                "total_trades": 0
            },
            "equity_curve": [],
            "execution_records": []
        }
