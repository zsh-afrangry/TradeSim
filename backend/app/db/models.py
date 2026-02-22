from sqlalchemy import Column, Integer, String, Date, Numeric, JSON, TIMESTAMP, text, BigInteger
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class SimulationRecord(Base):
    """
    回测记录关系型主表：专门用来记录参与倒序排序及条件筛选的核心指标。
    大体积数组不存放于此，以达到极速返回列表数据的目的。
    """
    __tablename__ = 'simulation_records'

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment='记录唯一标识')
    
    # 羁绊字段：用于关联查询时去 MongoDB 挂靠对应的大型数组账本
    mongo_log_id = Column(String(50), index=True, comment='绑定的 MongoDB 文档主键 ID')
    
    user_id = Column(BigInteger, server_default=text("0"), comment='目前暂无多用户,留空或置0')
    strategy_name = Column(String(50), nullable=False, comment='策略标识')
    symbol = Column(String(20), nullable=False, index=True, comment='交易标的代码')
    start_date = Column(Date, nullable=False, comment='回测起始日')
    end_date = Column(Date, nullable=False, comment='回测结束日')
    
    # 增加二阶段粒度区分维度
    data_frequency = Column(String(20), server_default=text("'daily'"), comment='数据粒度')
    
    # MySQL 5.7+ 原生支持 JSON。策略的动态传参丢在这个里面
    strategy_params = Column(JSON, comment='动态策略配置参数字典')
    
    # 核心指标
    total_return = Column(Numeric(10, 4), nullable=False, index=True, comment='总收益率')
    annualized_return = Column(Numeric(10, 4), server_default=text("0.0000"), comment='年化收益率')
    max_drawdown = Column(Numeric(10, 4), nullable=False, comment='最大回撤率')
    win_rate = Column(Numeric(10, 4), nullable=False, comment='胜率')
    total_trades = Column(Integer, nullable=False, comment='交易总笔数')
    
    created_at = Column(TIMESTAMP, server_default=text("CURRENT_TIMESTAMP"), index=True, comment='记录存储时间')
