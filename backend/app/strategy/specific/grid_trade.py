from app.strategy.base import BaseStrategy
from datetime import datetime
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)

class GridTradingStrategy(BaseStrategy):
    """
    网格交易策略的具体实现。
    根据初始底仓比例在第一天开仓，然后根据设定的网格间距和价格上下限，
    穿越网格线时进行高抛低吸。
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

        # 构建价格网格线 (从下限到上限的等比序列)
        self.grids = self._build_grids()
        
        # 记录当前刚穿过的网格线索引，借此决定买卖方向
        self.last_grid_idx = -1

    def _build_grids(self):
        """用配置的区间和划分模式构建静态网格"""
        grids = []
        if self.grid_type == 'arithmetic':
            # 等差数列切分方式
            count = max(1, self.grid_count)
            step = (self.upper_bound - self.lower_bound) / count
            for i in range(count + 1):
                grids.append(self.lower_bound + i * step)
        else:
            # 默认的等比切分方式 (geometric)
            current_price = self.lower_bound
            while current_price <= self.upper_bound:
                grids.append(current_price)
                current_price *= (1 + self.grid_step_pct)
        return grids

    def _find_nearest_grid(self, price: float) -> int:
        """寻找当前价格刚好跌破、或者刚好站在其上方的最近一根网格线索引"""
        for i in range(len(self.grids) - 1, -1, -1):
            if price >= self.grids[i]:
                return i
        return -1

    def execute(self) -> Dict[str, Any]:
        """覆盖并执行基类的回测生命周期主循环"""
        if self.df is None or self.df.is_empty():
            logger.warning("历史数据不足或为空，网格回测强制跳过产出空结果。")
            return self._build_empty_response()

        # 我们假设 DataFrame 一定包含了 ["日期", "开盘", "收盘", "最高", "最低"]
        selected_df = self.df.select(["日期", "开盘", "收盘"])

        # 以逐日跌宕方式遍历历史序列产生买卖点信号
        for row in selected_df.iter_rows(named=True):
            # 处理时间类型（兼容 datetime 或者 string），保留全精度分钟级切片以备不时之需
            raw_date = row["日期"]
            date_str = raw_date.strftime("%Y-%m-%d %H:%M:%S") if isinstance(raw_date, datetime) else str(raw_date)
            
            open_price = row["开盘"]
            close_price = row["收盘"]
            
            # 1. 初始建仓段 (只在整个回测周期第1天起效)
            if self.last_grid_idx == -1 and self.position == 0:
                self._initialize_base_position(date_str, open_price)
                self.last_grid_idx = self._find_nearest_grid(open_price)
                self._record_equity_snapshot(date_str, close_price)
                continue

            # 2. 日常收盘价触发式探测 (采用简化的日线收盘模型)
            current_grid_idx = self._find_nearest_grid(close_price)
            
            # --- 价格暴涨/上涨，穿过上方阻力格 -> 抛除
            if current_grid_idx > self.last_grid_idx and current_grid_idx >= 0:
                for step in range(current_grid_idx - self.last_grid_idx):
                    # 卖出应该按照当前突破的这根网格线来卖
                    grid_price = self.grids[self.last_grid_idx + step + 1]
                    self._sell(date_str, grid_price, "GRID_SELL")
            
            # --- 价格暴跌/下跌，跌落防守格 -> 捡筹
            elif current_grid_idx < self.last_grid_idx and current_grid_idx >= 0:
                for step in range(self.last_grid_idx - current_grid_idx):
                    # 买入应该按照跌破的这根网格线来买 (相比于原来少退一个索引，做到跌穿即买)
                    grid_price = self.grids[self.last_grid_idx - step - 1]
                    self._buy(date_str, grid_price, "GRID_BUY")
            
            # 重定向基线格索引
            self.last_grid_idx = current_grid_idx
            
            # 资金净值入库
            self._record_equity_snapshot(date_str, close_price)

        # 封装聚合字典，符合 Pydantic Response 契约
        return {
            "metrics": self._calculate_metrics(),
            "equity_curve": self.equity_curve,
            "execution_records": self.trade_logs
        }
        
    def _build_empty_response(self) -> Dict[str, Any]:
        """当遇到极端如停牌日无数据时返回兜底空字典"""
        return {
           "metrics": {
               "total_return": 0.0, "annualized_return": 0.0,
               "max_drawdown": 0.0, "win_rate": 0.0, "total_trades": 0
           }, 
           "equity_curve": [], 
           "execution_records": []
        }

    def _initialize_base_position(self, date: str, price: float):
        """首日启动：购买指定占比份额的底仓筹码"""
        target_cost = self.initial_capital * self.base_position_ratio
        shares_to_buy = int((target_cost) / (price + self.slippage) / 100) * 100
        if shares_to_buy > 0:
            self._buy(date, price, "BASE_OPEN", expected_volume=shares_to_buy)

    def _buy(self, date: str, trigger_price: float, action_type: str, expected_volume: int = None):
        """触发买单、计算磨损、检查余额并沉淀历史"""
        exec_price = trigger_price + self.slippage
        
        # 使用动态资金定调还是期望股数目定调
        if expected_volume is None:
            if self.trade_mode == 'amount':
                volume = int(self.funds_per_grid / exec_price / 100) * 100
            else:
                volume = int(self.funds_per_grid / 100) * 100
        else:
            volume = expected_volume

        if volume <= 0: return

        cost = exec_price * volume
        commission = cost * self.commission_rate
        total_cost = cost + commission

        # 余额足才能开仓吃入
        if self.cash >= total_cost:
            self.cash -= total_cost
            self.position += volume
            self._record_trade_log(date, action_type, exec_price, volume, total_cost, commission, self.slippage * volume)

    def _sell(self, date: str, trigger_price: float, action_type: str):
        """触发卖单、检查持仓、计征印花及佣金"""
        exec_price = max(0.01, trigger_price - self.slippage)
        if self.trade_mode == 'amount':
            volume = int(self.funds_per_grid / exec_price / 100) * 100
        else:
            volume = int(self.funds_per_grid / 100) * 100
        
        # 避免裸奔卖空
        volume = min(volume, self.position)
        if volume <= 0: return

        revenue = exec_price * volume
        commission = revenue * self.commission_rate
        net_revenue = revenue - commission

        self.cash += net_revenue
        self.position -= volume
        self._record_trade_log(date, action_type, exec_price, volume, net_revenue, commission, self.slippage * volume)
