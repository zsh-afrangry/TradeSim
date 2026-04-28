import requests
import time

# API endpoint and headers
url = 'http://127.0.0.1:8000/api/v1/simulate/run'
headers = {'Content-Type': 'application/json'}

# Initial parameters
symbol = '600585'
start_date = '2020-01-01'
end_date = '2024-01-01'
data_frequency = 'daily'
initial_capital = 100000.0
commission_rate = 0.00025
slippage = 0.01
strategy_name = 'GRID_TRADING'
base_position_ratio = 0.5
funds_per_grid = 10000.0

# Initialize the best parameters and their corresponding metrics
best_params = None
best_total_return = -float('inf')
best_max_drawdown = float('inf')

# Function to send a request and get the response
def send_request(lower_bound, upper_bound, grid_step_pct):
    payload = {
        'symbol': symbol,
        'start_date': start_date,
        'end_date': end_date,
        'data_frequency': data_frequency,
        'initial_capital': initial_capital,
        'commission_rate': commission_rate,
        'slippage': slippage,
        'strategy_name': strategy_name,
        'strategy_params': {
            'lower_bound': lower_bound,
            'upper_bound': upper_bound,
            'grid_step_pct': grid_step_pct,
            'base_position_ratio': base_position_ratio,
            'funds_per_grid': funds_per_grid
        }
    }
    response = requests.post(url, json=payload, headers=headers, timeout=30)
    return response

# Initial parameters for the first run
lower_bound = 10.0
upper_bound = 50.0
grid_step_pct = 0.05

# Run the optimization process continuously
iteration = 0
no_improvement_count = 0
max_no_improvement = 5  # Stop after 5 iterations without improvement
while no_improvement_count < max_no_improvement:
    # Send the request and get the response
    response = send_request(lower_bound, upper_bound, grid_step_pct)
    result = response.json()
    print(f'Iteration {iteration + 1} Response: {result}')

    # 接口报错（如无数据、参数越界）时跳过本次迭代，继续探索其他参数
    if response.status_code != 200 or 'metrics' not in result:
        print(f'[跳过] 本次请求失败（HTTP {response.status_code}），自动调整参数后重试...')
        iteration += 1
        no_improvement_count += 1
        time.sleep(1)
        continue

    try:
        total_return = result['metrics']['total_return']
        max_drawdown = result['metrics']['max_drawdown']
    except KeyError as e:
        print(f'[跳过] 解析 metrics 失败: {e}')
        iteration += 1
        no_improvement_count += 1
        time.sleep(1)
        continue

    # Print the current parameters and results
    print(f'Iteration {iteration + 1}: Lower Bound: {lower_bound}, Upper Bound: {upper_bound}, Grid Step Pct: {grid_step_pct}')
    print(f'Total Return: {total_return}, Max Drawdown: {max_drawdown}')

    # Update the best parameters if the current one is better
    if total_return > best_total_return:
        best_total_return = total_return
        best_max_drawdown = max_drawdown
        best_params = (lower_bound, upper_bound, grid_step_pct)
        no_improvement_count = 0
    else:
        no_improvement_count += 1

    # Adjust parameters based on the results
    if total_return < 0.1:
        # If the total return is low, try narrowing the bounds or decreasing the grid step
        lower_bound += 1.0
        upper_bound -= 1.0
        grid_step_pct -= 0.01
    elif max_drawdown > 0.2:
        # If the max drawdown is high, try narrowing the bounds
        lower_bound += 1.0
        upper_bound -= 1.0
    else:
        # Otherwise, try widening the bounds or increasing the grid step
        lower_bound -= 1.0
        upper_bound += 1.0
        grid_step_pct += 0.01

    # Ensure the grid step pct stays within the suggested range
    grid_step_pct = max(0.02, min(grid_step_pct, 0.15))

    # Wait for a short period before the next iteration
    time.sleep(1)
    iteration += 1

# Print the best parameters and their corresponding metrics
print('\n===== 优化结果 =====')
if best_params is None:
    print('所有迭代均未成功返回有效数据，未能找到最优参数。')
    print('请检查：① 股票代码是否正确 ② 日期范围内是否有行情数据 ③ 后端服务是否正常运行')
else:
    print(f'最优 Lower Bound  : {best_params[0]}')
    print(f'最优 Upper Bound  : {best_params[1]}')
    print(f'最优 Grid Step Pct: {best_params[2]}')
    print(f'Total Return      : {best_total_return:.4f}')
    print(f'Max Drawdown      : {best_max_drawdown:.4f}')
