import polars as pl
from abc import ABC, abstractmethod
from typing import Dict, Any

class BaseStrategy(ABC):
    """
    所有策略的抽象基类，规范了生命周期与输入/输出契约。
    """
    
    def __init__(self, df: pl.DataFrame, params: Dict[str, Any], initial_capital: float, commission_rate: float, slippage: float):
        """
        :param df: 标准化的历史行情数据 (必须包含 日期、开盘、收盘、最高、最低 等列)
        :param params: 策略专属的配置参数 (比如网格参数，由子类负责校验)
        :param initial_capital: 初始本金
        :param commission_rate: 交易佣金率 (万分之几)
        :param slippage: 单边滑点 (绝对数值或百分比)
        """
        self.df = df
        self.params = params
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.commission_rate = commission_rate
        self.slippage = slippage

        # 初始化策略所需的内部状态变量
        self.position = 0         # 当前持仓股数
        self.cash = self.initial_capital  # 当前可用现金
        self.trade_logs = []      # 成交流水记录
        self.equity_curve = []    # 资金曲线快照序列

    @abstractmethod
    def execute(self) -> Dict[str, Any]:
        """
        执行主回测循环或者向量化计算。
        子类必须实现此方法。
        
        :return: 包含三个核心 Key 的字典:
            - metrics (基于 Pydantic SimulationMetrics 的字典)
            - equity_curve (基于 Pydantic EquitySnapshot 的列表字典)
            - execution_records (基于 Pydantic TradeRecord 的列表字典)
        """
        pass
    
    def _record_trade_log(self, date: str, action: str, price: float, volume: int, amount: float, commission: float, slip_cost: float):
        """记录具体的成交流水以便序列化输出"""
        self.trade_logs.append({
            "timestamp": date,
            "action": action,
            "price": round(price, 3),
            "volume": volume,
            "amount": round(amount, 2),
            "commission": round(commission, 2),
            "slippage_cost": round(slip_cost, 2)
        })

    def _record_equity_snapshot(self, date: str, close_price: float):
        """快照某日/时刻净值，以便序列化给图表使用"""
        stock_value = self.position * close_price
        net_value = self.cash + stock_value
        
        # 计算资金利用率（当前股票市值 / 账户总净值）
        utilization = (stock_value / net_value) if net_value > 0 else 0.0

        # 获取首日收盘价作为 Buy & Hold 的基准原点，以复原原生折线走势
        if not hasattr(self, '_base_close_price'):
            self._base_close_price = close_price
            
        # 归一化计算：基于初始本金的 Buy & Hold 净值
        benchmark_net_value = self.initial_capital * (close_price / self._base_close_price)
        
        # 实时计算当前时刻的最大回撤
        max_net_value_so_far = self.initial_capital
        if self.equity_curve:
            max_net_value_so_far = max([record["net_value"] for record in self.equity_curve])
        max_net_value_so_far = max(max_net_value_so_far, net_value)
        
        drawdown = (max_net_value_so_far - net_value) / max_net_value_so_far if max_net_value_so_far > 0 else 0.0

        self.equity_curve.append({
            "date": date,
            "close_price": round(close_price, 3),              # 新增：原生 K 线价格
            "net_value": round(net_value, 2),
            "benchmark_value": round(benchmark_net_value, 2),  # 记录标的无脑持有收益线
            "position_utilization": round(utilization, 4),     # 记录资金闲置/利用情况
            "drawdown": round(drawdown, 4)
        })

    def _calculate_metrics(self) -> Dict[str, Any]:
        """统筹计算最终的各种评判指标"""
        final_net_value = self.equity_curve[-1]["net_value"] if self.equity_curve else self.initial_capital
        total_return = (final_net_value - self.initial_capital) / self.initial_capital
        
        max_drawdown = 0.0
        if self.equity_curve:
            max_drawdown = max([record["drawdown"] for record in self.equity_curve])

        total_trades = len(self.trade_logs)
        
        # 粗略胜率估算：对于简单单向做多，只要有配对平仓利润为正即记为胜
        # 此处为一个极简实现，实际可能需要建立出入场匹配队列
        win_trades = 0
        for i in range(1, total_trades):
            if "SELL" in self.trade_logs[i]["action"] and self.trade_logs[i]["price"] > self.trade_logs[i-1]["price"]:
                win_trades += 1
                
        # 粗略将每对(买+卖)视为1笔完整交易
        completed_trades = total_trades / 2 if total_trades > 0 else 1
        win_rate = min(1.0, win_trades / completed_trades) if completed_trades > 0 else 0.0

        return {
             "total_return": round(total_return, 4),
             "annualized_return": 0.0, # 需根据起止天数计算年化，暂时填0
             "max_drawdown": round(max_drawdown, 4),
             "win_rate": round(win_rate, 4),
             "total_trades": total_trades
        }
