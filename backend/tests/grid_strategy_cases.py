import sys
from pathlib import Path

import polars as pl

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.strategy.specific.grid_trade import GridTradingStrategy


def make_df(closes):
    return pl.DataFrame({
        "日期": [f"d{i + 1}" for i in range(len(closes))],
        "开盘": closes,
        "收盘": closes,
        "最高": closes,
        "最低": closes,
    })


def default_params(**overrides):
    params = {
        "lower_bound": 8.0,
        "upper_bound": 12.0,
        "grid_type": "arithmetic",
        "grid_count": 8,
        "base_position_ratio": 0.0,
        "trade_mode": "volume",
        "funds_per_grid": 100,
    }
    params.update(overrides)
    return params


def make_engine(closes, params=None, initial_capital=10000, commission_rate=0.0, slippage=0.0):
    return GridTradingStrategy(
        df=make_df(closes),
        params=params or default_params(),
        initial_capital=initial_capital,
        commission_rate=commission_rate,
        slippage=slippage,
    )


def assert_equal(actual, expected, name):
    if actual != expected:
        raise AssertionError(f"{name}: expected {expected!r}, got {actual!r}")


def assert_close(actual, expected, name, tolerance=1e-9):
    if abs(actual - expected) > tolerance:
        raise AssertionError(f"{name}: expected {expected!r}, got {actual!r}")


def grid_logs(result):
    return [
        log for log in result["execution_records"]
        if log["action"] in {"GRID_BUY", "GRID_SELL"}
    ]


def test_geometric_percent_contract():
    engine = make_engine(
        [10.0],
        {
            "lower_bound": 10.0,
            "upper_bound": 11.1,
            "grid_type": "geometric",
            "grid_step_pct": 5.0,
            "base_position_ratio": 0.0,
            "trade_mode": "volume",
            "funds_per_grid": 100,
        },
    )

    prices = engine._grid_prices()
    assert_close(prices[0], 10.0, "first geometric grid")
    assert_close(prices[1], 10.5, "5 percent grid step")
    assert_close(prices[2], 11.025, "second 5 percent grid step")


def test_basic_grid_cycle_should_buy_low_and_sell_high():
    engine = make_engine([10.0, 9.5, 10.0])
    result = engine.execute()
    logs = grid_logs(result)

    assert_equal(len(logs), 2, "trade count for one completed grid cycle")
    assert_equal(logs[0]["action"], "GRID_BUY", "first grid action")
    assert_close(logs[0]["price"], 9.5, "buy price")
    assert_equal(logs[0]["volume"], 100, "buy volume")
    assert_equal(logs[1]["action"], "GRID_SELL", "second grid action")
    assert_close(logs[1]["price"], 10.0, "sell price")
    assert_equal(logs[1]["volume"], 100, "sell volume")
    assert_close(result["metrics"]["total_return"], 0.005, "50 yuan profit on 10000 capital")
    assert_equal(result["metrics"]["total_trades"], 2, "grid-only trade count")
    assert_close(result["metrics"]["win_rate"], 1.0, "completed cycle win rate")


def test_multi_grid_drop_buys_each_crossed_level():
    engine = make_engine([10.0, 9.0])
    result = engine.execute()
    logs = grid_logs(result)

    assert_equal([log["action"] for log in logs], ["GRID_BUY", "GRID_BUY"], "two buy actions")
    assert_equal([log["price"] for log in logs], [9.5, 9.0], "buy prices for crossed levels")
    assert_equal([log["volume"] for log in logs], [100, 100], "buy volumes")
    assert_equal(result["metrics"]["total_trades"], 2, "two grid buy orders")
    assert_close(result["metrics"]["win_rate"], 0.0, "no completed cycles yet")


def test_multi_grid_rise_sells_only_open_grid_nodes():
    engine = make_engine([10.0, 9.0, 10.5])
    result = engine.execute()
    logs = grid_logs(result)

    assert_equal([log["action"] for log in logs], ["GRID_BUY", "GRID_BUY", "GRID_SELL", "GRID_SELL"], "buy and sell actions")
    assert_equal([log["price"] for log in logs], [9.5, 9.0, 9.5, 10.0], "paired grid prices")
    assert_equal(result["metrics"]["total_trades"], 4, "grid order count")
    assert_equal(result["metrics"]["win_rate"], 1.0, "all completed cycles are winners")
    assert_close(result["metrics"]["total_return"], 0.01, "two 50 yuan cycles")


def test_base_position_does_not_occupy_grid_nodes():
    engine = make_engine([10.0, 9.5, 10.0], default_params(base_position_ratio=0.5))
    result = engine.execute()
    all_logs = result["execution_records"]
    logs = grid_logs(result)

    assert_equal(all_logs[0]["action"], "BASE_OPEN", "base position opens first")
    assert_equal([log["action"] for log in logs], ["GRID_BUY", "GRID_SELL"], "base does not block grid cycle")
    assert_equal(result["metrics"]["total_trades"], 2, "base open excluded from grid trade count")
    assert_close(result["metrics"]["win_rate"], 1.0, "base open excluded from win rate")
    assert_close(result["metrics"]["total_return"], 0.005, "grid profit plus unchanged base")


def test_commission_and_slippage_reduce_realized_profit():
    engine = make_engine([10.0, 9.5, 10.0], commission_rate=0.01, slippage=0.1)
    result = engine.execute()

    # Buy at 9.6: total cost 969.6. Sell at 9.9: net revenue 980.1.
    assert_close(engine.realized_grid_profit, 10.5, "realized profit after friction")
    assert_close(result["metrics"]["total_return"], 0.001, "rounded account return after friction")
    assert_close(result["metrics"]["win_rate"], 1.0, "cycle remains profitable")


def test_insufficient_cash_does_not_occupy_grid_node():
    engine = make_engine(
        [10.0, 9.5],
        default_params(funds_per_grid=200),
        initial_capital=1000,
    )
    result = engine.execute()

    assert_equal(grid_logs(result), [], "no grid trade when cash is insufficient")
    assert_equal(engine.grid_nodes[3].is_idle, True, "9.5 node remains idle")
    assert_equal(result["metrics"]["total_trades"], 0, "no grid orders")


def test_invalid_params_raise_value_error():
    try:
        make_engine([10.0], default_params(lower_bound=12.0, upper_bound=8.0))
    except ValueError as exc:
        if "upper_bound" not in str(exc):
            raise AssertionError(f"unexpected validation error: {exc}")
        return
    raise AssertionError("invalid bounds should raise ValueError")


def main():
    tests = [
        test_geometric_percent_contract,
        test_basic_grid_cycle_should_buy_low_and_sell_high,
        test_multi_grid_drop_buys_each_crossed_level,
        test_multi_grid_rise_sells_only_open_grid_nodes,
        test_base_position_does_not_occupy_grid_nodes,
        test_commission_and_slippage_reduce_realized_profit,
        test_insufficient_cash_does_not_occupy_grid_node,
        test_invalid_params_raise_value_error,
    ]
    failed = 0

    for test in tests:
        try:
            test()
            print(f"PASS {test.__name__}")
        except Exception as exc:
            failed += 1
            print(f"FAIL {test.__name__}: {exc}")

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
