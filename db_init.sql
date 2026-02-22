-- 1. 创建数据库
CREATE DATABASE IF NOT EXISTS tradesim DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE tradesim;

-- 2. 创建主表：simulation_records (用于高频检索和列表排序)
CREATE TABLE IF NOT EXISTS simulation_records (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '记录唯一标识',
    user_id BIGINT DEFAULT 0 COMMENT '目前暂无多用户,留空或置0',
    strategy_name VARCHAR(50) NOT NULL COMMENT '策略标识',
    symbol VARCHAR(20) NOT NULL COMMENT '交易标的代码',
    start_date DATE NOT NULL COMMENT '回测起始日',
    end_date DATE NOT NULL COMMENT '回测结束日',
    strategy_params JSON COMMENT '动态策略配置参数字典(可灵活扩展)',
    total_return DECIMAL(10,4) NOT NULL COMMENT '总收益率',
    annualized_return DECIMAL(10,4) DEFAULT 0.0 COMMENT '年化收益率',
    max_drawdown DECIMAL(10,4) NOT NULL COMMENT '最大回撤率',
    win_rate DECIMAL(10,4) NOT NULL COMMENT '胜率',
    total_trades INT NOT NULL COMMENT '交易总笔数',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '记录存储时间',
    INDEX idx_user_return (user_id, total_return DESC),
    INDEX idx_symbol (symbol)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='回测记录主表';

-- 3. （仅作备用，若全部走MySQL时的从表，大体积负载）
-- CREATE TABLE IF NOT EXISTS simulation_logs (
--     record_id BIGINT PRIMARY KEY COMMENT '对应 simulation_records 主表 ID',
--     equity_curve JSON COMMENT '资金曲线大数组',
--     execution_records JSON COMMENT '成交流水大数组',
--     CONSTRAINT fk_record_id FOREIGN KEY (record_id) REFERENCES simulation_records(id) ON DELETE CASCADE
-- 
-- 4. 二阶段平滑升级补丁 (请在此处执行历史补丁)
ALTER TABLE simulation_records 
    ADD COLUMN IF NOT EXISTS data_frequency VARCHAR(20) DEFAULT 'daily' COMMENT '数据切片频度' AFTER end_date; 