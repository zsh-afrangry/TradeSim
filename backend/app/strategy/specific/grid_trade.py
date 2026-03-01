from app.strategy.base import BaseStrategy
from datetime import datetime
from typing import Dict, Any, List
import logging

logger = logging.getLogger(__name__)

# 网格节点的两种状态
IDLE = "IDLE"           # 空闲：可以执行买入
OCCUPIED = "OCCUPIED"   # 占用：已持有仓位，等待卖出释放


class GridNode:
    """
    代表一条具体的网格线，持有其价格锚点与当前状态。
    买入后变为 OCCUPIED，只有触发卖出平仓后才重置回 IDLE。
    """
    def __init__(self, price: float):
        self.price = price
        self.status: str = IDLE

    def occupy(self):
        """买入时调用，将该格标记为占用"""
        self.status = OCCUPIED

    def release(self):
        """卖出时调用，将该格重置为空闲"""
        self.status = IDLE

    @property
    def is_idle(self) -> bool:
        return self.status == IDLE

    @property
    def is_occupied(self) -> bool:
        return self.status == OCCUPIED

    def __repr__(self):
        return f"GridNode(price={self.price:.3f}, status={self.status})"


class GridTradingStrategy(BaseStrategy):
    """
    有状态（Stateful）网格交易策略实现。

    核心规则（来自需求文档）：
    - 每一个网格节点都有独立的状态机（IDLE / OCCUPIED）。
    - 价格向下穿越某格时，仅当该格处于 IDLE 状态时才触发买入，买入后该格变为 OCCUPIED。
    - 价格向上穿越某格的上方格（即对应的卖出格）时，若下方买入格处于 OCCUPIED，
      则触发卖出并将买入格重置为 IDLE。
    - 同一格在没有完成"买入→卖出"完整配对前，绝不会重复买入，
      彻底杜绝同一价位区间来回震荡导致的异常仓位累积。
    """

    def __init__(self, df, params, initial_capital, commission_rate, slippage):
        super().__init__(df, params, initial_capital, commission_rate, slippage)

        # 提取专属参数并进行默认降级处理
        self.lower_bound = params.get('lower_bound', 20.0)
        self.upper_bound = params.get('upper_bound', 30.0)
        self.grid_step_pct = params.get('grid_step_pct', 0.05)
        self.grid_type = params.get('grid_type', 'geometric')
        self.grid_count = params.get('grid_count', 20)
        self.base_position_ratio = params.get('base_position_ratio', 0.5)
        self.trade_mode = params.get('trade_mode', 'amount')
        self.funds_per_grid = params.get('funds_per_grid', 10000.0)

        # 构建有状态的网格线节点列表（核心升级：从 float list → GridNode list）
        self.grid_nodes: List[GridNode] = self._build_grid_nodes()

        # 记录上一根 K 线收盘价所在的网格索引（-1 表示尚未初始化）
        self.last_grid_idx = -1

    # ──────────────────────────────────────────────────
    # 网格构建
    # ──────────────────────────────────────────────────

    def _build_grid_nodes(self) -> List[GridNode]:
        """按照价格区间和划分模式构建 GridNode 状态节点列表"""
        prices = []
        if self.grid_type == 'arithmetic':
            count = max(1, self.grid_count)
            step = (self.upper_bound - self.lower_bound) / count
            prices = [self.lower_bound + i * step for i in range(count + 1)]
        else:
            # 等比切分（geometric）
            current = self.lower_bound
            while current <= self.upper_bound * 1.0001:   # 容忍浮点误差
                prices.append(current)
                current *= (1 + self.grid_step_pct)

        return [GridNode(p) for p in prices]

    def _grid_prices(self) -> List[float]:
        """辅助方法：快速取出所有节点的价格列表（用于索引定位）"""
        return [node.price for node in self.grid_nodes]

    def _find_nearest_grid_idx(self, price: float) -> int:
        """
        找到当前价格"踩在"哪一格区间内。
        返回价格刚好 >= 的最右侧网格线索引（即价格所处区间的下边界之格）。
        """
        for i in range(len(self.grid_nodes) - 1, -1, -1):
            if price >= self.grid_nodes[i].price:
                return i
        return -1

    # ──────────────────────────────────────────────────
    # 回测主循环
    # ──────────────────────────────────────────────────

    def execute(self) -> Dict[str, Any]:
        """覆盖并执行基类的回测生命周期主循环"""
        if self.df is None or self.df.is_empty():
            logger.warning("历史数据不足或为空，网格回测强制跳过产出空结果。")
            return self._build_empty_response()

        selected_df = self.df.select(["日期", "开盘", "收盘"])

        for row in selected_df.iter_rows(named=True):
            raw_date = row["日期"]
            date_str = raw_date.strftime("%Y-%m-%d %H:%M:%S") if isinstance(raw_date, datetime) else str(raw_date)
            open_price = row["开盘"]
            close_price = row["收盘"]

            # ── 第一天：建立底仓，初始化上一格索引 ──────────────
            if self.last_grid_idx == -1 and self.position == 0:
                self._initialize_base_position(date_str, open_price)
                self.last_grid_idx = self._find_nearest_grid_idx(open_price)
                # 底仓对应的格全部标记为占用
                for i in range(self.last_grid_idx + 1):
                    self.grid_nodes[i].occupy()
                self._record_equity_snapshot(date_str, close_price)
                continue

            # ── 后续每天：检测收盘价穿格情况，触发有状态的买卖逻辑 ──
            current_grid_idx = self._find_nearest_grid_idx(close_price)

            if current_grid_idx > self.last_grid_idx:
                # 价格向上穿越了若干格：逐格触发卖出（必须该买入格处于 OCCUPIED 才能卖）
                for step in range(current_grid_idx - self.last_grid_idx):
                    sell_at_idx = self.last_grid_idx + step + 1
                    buy_at_idx  = self.last_grid_idx + step        # 买入格 = 卖出格的下方一格
                    if 0 <= buy_at_idx < len(self.grid_nodes):
                        buy_node = self.grid_nodes[buy_at_idx]
                        if buy_node.is_occupied:
                            grid_price = self.grid_nodes[sell_at_idx].price
                            sold = self._sell(date_str, grid_price, "GRID_SELL")
                            if sold:
                                buy_node.release()   # 卖出成功 → 释放对应买入格

            elif current_grid_idx < self.last_grid_idx:
                # 价格向下穿越了若干格：逐格触发买入（必须该格处于 IDLE 才能买）
                for step in range(self.last_grid_idx - current_grid_idx):
                    buy_at_idx = self.last_grid_idx - step - 1
                    if 0 <= buy_at_idx < len(self.grid_nodes):
                        buy_node = self.grid_nodes[buy_at_idx]
                        if buy_node.is_idle:
                            grid_price = buy_node.price
                            bought = self._buy(date_str, grid_price, "GRID_BUY")
                            if bought:
                                buy_node.occupy()    # 买入成功 → 封锁该格，等待卖出释放

            self.last_grid_idx = current_grid_idx
            self._record_equity_snapshot(date_str, close_price)

        return {
            "metrics": self._calculate_metrics(),
            "equity_curve": self.equity_curve,
            "execution_records": self.trade_logs
        }

    # ──────────────────────────────────────────────────
    # 交易执行
    # ──────────────────────────────────────────────────

    def _initialize_base_position(self, date: str, price: float):
        """首日启动：购买指定占比份额的底仓筹码"""
        target_cost = self.initial_capital * self.base_position_ratio
        shares_to_buy = int(target_cost / (price + self.slippage) / 100) * 100
        if shares_to_buy > 0:
            self._buy(date, price, "BASE_OPEN", expected_volume=shares_to_buy)

    def _buy(self, date: str, trigger_price: float, action_type: str, expected_volume: int = None) -> bool:
        """
        触发买单、计算磨损、检查余额并沉淀历史。
        返回值：True = 买入成功；False = 余额不足或手数为0，买入失败
        """
        exec_price = trigger_price + self.slippage

        if expected_volume is None:
            if self.trade_mode == 'amount':
                volume = int(self.funds_per_grid / exec_price / 100) * 100
            else:
                volume = int(self.funds_per_grid / 100) * 100
        else:
            volume = expected_volume

        if volume <= 0:
            return False

        cost = exec_price * volume
        commission = cost * self.commission_rate
        total_cost = cost + commission

        if self.cash >= total_cost:
            self.cash -= total_cost
            self.position += volume
            self._record_trade_log(date, action_type, exec_price, volume, total_cost, commission, self.slippage * volume)
            return True

        return False

    def _sell(self, date: str, trigger_price: float, action_type: str) -> bool:
        """
        触发卖单、检查持仓、计征印花及佣金并结算。
        返回值：True = 卖出成功；False = 持仓不足，卖出失败
        """
        exec_price = max(0.01, trigger_price - self.slippage)

        if self.trade_mode == 'amount':
            volume = int(self.funds_per_grid / exec_price / 100) * 100
        else:
            volume = int(self.funds_per_grid / 100) * 100

        volume = min(volume, self.position)
        if volume <= 0:
            return False

        revenue = exec_price * volume
        commission = revenue * self.commission_rate
        net_revenue = revenue - commission

        self.cash += net_revenue
        self.position -= volume
        self._record_trade_log(date, action_type, exec_price, volume, net_revenue, commission, self.slippage * volume)
        return True

    # ──────────────────────────────────────────────────
    # 兜底
    # ──────────────────────────────────────────────────

    def _build_empty_response(self) -> Dict[str, Any]:
        """当遇到极端停牌日无数据时返回兜底空字典"""
        return {
            "metrics": {
                "total_return": 0.0, "annualized_return": 0.0,
                "max_drawdown": 0.0, "win_rate": 0.0, "total_trades": 0
            },
            "equity_curve": [],
            "execution_records": []
        }
