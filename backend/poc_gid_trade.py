import akshare as ak
import polars as pl
import pandas as pd
from datetime import datetime

class GridTradingStrategy:
    def __init__(self, df: pl.DataFrame, params: dict, initial_capital: float, commission_rate: float, slippage: float):
        """
        初始化网格交易策略
        :param df: 包含历史行情的 Polars DataFrame，必须包含 '日期', '开盘', '收盘', '最高', '最低' 等列
        :param params: 网格参数配置 (包含下限、上限、网格间距、底仓比例、每格资金等)
        :param initial_capital: 初始本金
        :param commission_rate: 交易手续费率
        :param slippage: 滑点 (暂按固定数值计算)
        """
        self.df = df
        self.params = params
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.commission_rate = commission_rate
        self.slippage = slippage

        # 从 params 中解析网格配置
        self.lower_bound = params.get('lower_bound', 20.0)
        self.upper_bound = params.get('upper_bound', 30.0)
        self.grid_step_pct = params.get('grid_step_pct', 0.05)
        self.base_position_ratio = params.get('base_position_ratio', 0.5)
        self.funds_per_grid = params.get('funds_per_grid', 10000.0)

        # 状态变量
        self.position = 0  # 当前持仓股数
        self.cash = self.initial_capital  # 当前可用现金
        self.trade_logs = []  # 交易记录流水
        self.equity_curve = []  # 资金曲线记录

        # 构建价格网格线 (从下限到上限)
        self.grids = self._build_grids()
        
        # 记录当前穿越的网格索引，用于判断买卖
        self.last_grid_idx = -1

    def _build_grids(self):
        """构建网格区间"""
        grids = []
        current_price = self.lower_bound
        while current_price <= self.upper_bound:
            grids.append(current_price)
            current_price *= (1 + self.grid_step_pct)
        return grids

    def _find_nearest_grid(self, price: float) -> int:
        """寻找当前价格最接近的下方网格线索引"""
        for i in range(len(self.grids) - 1, -1, -1):
            if price >= self.grids[i]:
                return i
        return -1

    def execute(self):
        """执行回测主循环"""
        if self.df.is_empty():
            print("警告: 历史行情数据为空，无法执行回测。")
            return self._generate_results()

        # 选取回测所需的数据列
        selected_df = self.df.select(["日期", "开盘", "收盘", "最高", "最低"])

        # 将 Polars DataFrame 转换为迭代器进行逐日遍历 (回测常态)
        for row in selected_df.iter_rows(named=True):
            date = row["日期"].strftime("%Y-%m-%d") if isinstance(row["日期"], datetime) else str(row["日期"])
            open_price = row["开盘"]
            close_price = row["收盘"]
            
            # --- 1. 初始化底仓 (第一天开盘) ---
            if self.last_grid_idx == -1 and self.position == 0:
                self._initialize_base_position(date, open_price)
                self.last_grid_idx = self._find_nearest_grid(open_price)
                self._record_equity(date, close_price)
                continue

            # --- 2. 日常网格触发逻辑 (按收盘价判断，简化模型) ---
            current_grid_idx = self._find_nearest_grid(close_price)
            
            # 价格上涨，穿越上方网格 -> 卖出
            if current_grid_idx > self.last_grid_idx and current_grid_idx >= 0:
                # 遍历中间跨越的每一格 (应对暴涨)
                for step in range(current_grid_idx - self.last_grid_idx):
                    grid_price = self.grids[self.last_grid_idx + step + 1]
                    self._sell(date, grid_price, "GRID_SELL")
            
            # 价格下跌，穿越下方网格 -> 买入
            elif current_grid_idx < self.last_grid_idx and current_grid_idx >= 0:
                 # 遍历中间跨越的每一格 (应对暴跌)
                for step in range(self.last_grid_idx - current_grid_idx):
                    grid_price = self.grids[self.last_grid_idx - step]
                    self._buy(date, grid_price, "GRID_BUY")
            
            self.last_grid_idx = current_grid_idx
            
            # 每周末计算并记录一次资金曲线
            self._record_equity(date, close_price)

        return self._generate_results()

    def _initialize_base_position(self, date: str, price: float):
        """建底仓"""
        target_cost = self.initial_capital * self.base_position_ratio
        # 计算能买多少股 (排除手续费和滑点的大致估算)
        shares_to_buy = int((target_cost) / (price + self.slippage) / 100) * 100  # 手数为 100 整数倍
        if shares_to_buy > 0:
            self._buy(date, price, "BASE_OPEN", expected_volume=shares_to_buy)

    def _buy(self, date: str, trigger_price: float, action_type: str, expected_volume: int = None):
        """执行买入操作"""
        # 实际成交价 = 触发价 + 滑点
        exec_price = trigger_price + self.slippage
        
        if expected_volume is None:
            # 默认按每格资金量买入
            volume = int(self.funds_per_grid / exec_price / 100) * 100
        else:
            volume = expected_volume

        if volume <= 0:
            return

        cost = exec_price * volume
        commission = cost * self.commission_rate
        total_cost = cost + commission

        # 检查资金是否充足
        if self.cash >= total_cost:
            self.cash -= total_cost
            self.position += volume
            self.trade_logs.append({
                "timestamp": date,
                "action": action_type,
                "price": round(exec_price, 3),
                "volume": volume,
                "amount": round(total_cost, 2),
                "commission": round(commission, 2),
                "slippage_cost": round(self.slippage * volume, 2)
            })

    def _sell(self, date: str, trigger_price: float, action_type: str):
        """执行卖出操作"""
        # 实际成交价 = 触发价 - 滑点
        exec_price = max(0.01, trigger_price - self.slippage)
        
        # 默认按每格资金量估算要卖的股数
        volume = int(self.funds_per_grid / exec_price / 100) * 100

        # 不能卖空，最多清仓
        volume = min(volume, self.position)
        
        if volume <= 0:
            return

        revenue = exec_price * volume
        commission = revenue * self.commission_rate
        # A股可能还有印花税等，此处为了简便统一使用 commission_rate
        net_revenue = revenue - commission

        self.cash += net_revenue
        self.position -= volume
        self.trade_logs.append({
            "timestamp": date,
            "action": action_type,
            "price": round(exec_price, 3),
            "volume": volume,
            "amount": round(net_revenue, 2),
            "commission": round(commission, 2),
            "slippage_cost": round(self.slippage * volume, 2)
        })

    def _record_equity(self, date: str, current_price: float):
        """记录每日资金净值"""
        stock_value = self.position * current_price
        net_value = self.cash + stock_value
        
        # 计算回撤
        max_net_value_so_far = self.initial_capital
        if self.equity_curve:
            max_net_value_so_far = max([record["net_value"] for record in self.equity_curve])
        max_net_value_so_far = max(max_net_value_so_far, net_value)
        
        drawdown = (max_net_value_so_far - net_value) / max_net_value_so_far if max_net_value_so_far > 0 else 0

        self.equity_curve.append({
            "date": date,
            "net_value": round(net_value, 2),
            "drawdown": round(drawdown, 4)
        })

    def _generate_results(self) -> dict:
        """整理输出结果"""
        final_net_value = self.equity_curve[-1]["net_value"] if self.equity_curve else self.initial_capital
        total_return = (final_net_value - self.initial_capital) / self.initial_capital
        
        max_drawdown = 0
        if self.equity_curve:
             max_drawdown = max([record["drawdown"] for record in self.equity_curve])

        win_trades = 0
        total_trades = len(self.trade_logs)
        # 简单的胜率统计：卖出价格高于上一次操作价格则视为盈利 (粗略估计，严谨的话应配对开平仓)
        for i in range(1, total_trades):
            if self.trade_logs[i]["action"] == "GRID_SELL" and self.trade_logs[i]["price"] > self.trade_logs[i-1]["price"]:
                win_trades += 1
        win_rate = win_trades / (total_trades / 2) if total_trades > 0 else 0.0 # 粗略地将买卖一对视为一次完整交易

        metrics = {
             "total_return": round(total_return, 4),
             "annualized_return": 0.0, # 需根据实际天数计算，此处简化
             "max_drawdown": round(max_drawdown, 4),
             "win_rate": round(win_rate, 4),
             "total_trades": total_trades
        }

        return {
            "metrics": metrics,
            "equity_curve": self.equity_curve,
            "execution_records": self.trade_logs
        }


def main():
    print(">>> 1. 通过 AkShare 获取历史数据...")
    symbol = "000400"
    start_date = "20240101"
    end_date = "20241231"
    try:
        # 获取前复权历史日线数据
        df_ak = ak.stock_zh_a_hist(symbol=symbol, period="daily", start_date=start_date, end_date=end_date, adjust="qfq")
        if df_ak.empty:
            print("未能获取到数据，请检查网络或股票代码是否正确。")
            return
        print(f"成功获取数据: {len(df_ak)} 行")
    except Exception as e:
        print(f"数据获取失败: {e}")
        return

    print(">>> 2. 转换为 Polars DataFrame 进行处理...")
    df_pl = pl.from_pandas(df_ak)
    # 打印前几行查看数据结构
    print(df_pl.head(2))

    print(">>> 3. 配置网格交易策略参数...")
    # 获取历史价格区间以适配网格
    hist_min = df_pl['最低'].min()
    hist_max = df_pl['最高'].max()
    print(f"数据期间价位: {hist_min:.2f} - {hist_max:.2f}")

    strategy_params = {
        "lower_bound": max(1.0, hist_min * 0.9),  # 历史最低价下浮 10%
        "upper_bound": hist_max * 1.1,         # 历史最高价上浮 10%
        "grid_step_pct": 0.05,                   # 每个网格 5% 间距
        "base_position_ratio": 0.3,              # 30% 底仓
        "funds_per_grid": 10000.0                # 每格动用 1 万元
    }
    
    initial_capital = 100_000.0  # 10 万本金
    commission_rate = 0.00025    # 万分之 2.5 手续费
    slippage = 0.01              # 滑点 1 分钱

    print(f"策略入参: {strategy_params}")

    print(">>> 4. 实例化引擎并执行回测...")
    engine = GridTradingStrategy(
        df=df_pl,
        params=strategy_params,
        initial_capital=initial_capital,
        commission_rate=commission_rate,
        slippage=slippage
    )
    
    result_payload = engine.execute()

    print("\n>>> 5. 回测结果产出 (JSON 字典结构) <<<")
    metrics = result_payload["metrics"]
    print("\n[核心指标 Metrics]")
    print(f"- 总收益率: {metrics['total_return'] * 100:.2f}%")
    print(f"- 最大回撤: {metrics['max_drawdown'] * 100:.2f}%")
    print(f"- 交易总频: {metrics['total_trades']} 笔")
    print(f"- (粗略)胜率: {metrics['win_rate'] * 100:.2f}%")

    print(f"\n[成交流水 Log] (展示前 5 笔)")
    for log in result_payload["execution_records"][:5]:
        print(f"  > {log['timestamp']}: {log['action']} @ {log['price']}元, 股数: {log['volume']}, 金额: {log['amount']}")

    print(f"\n[资金曲线 Curve] (展示头尾)")
    if result_payload["equity_curve"]:
       print(f"  首日: {result_payload['equity_curve'][0]}")
       print(f"  末日: {result_payload['equity_curve'][-1]}")

if __name__ == "__main__":
    main()
