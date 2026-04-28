import akshare as ak
import polars as pl
from datetime import datetime
import logging
import os

logger = logging.getLogger(__name__)

class DataFetcher:
    """
    负责从外部数据源（如 AkShare）获取金融数据，
    并将其标准化清洗为统一的 Polars DataFrame 格式，供后端策略引擎极速处理。
    """
    
    @staticmethod
    def fetch_a_share_data(symbol: str, start_date: str, end_date: str, frequency: str = "daily", adjust: str = "qfq") -> pl.DataFrame | None:
        """
        根据指定频率 (daily/5min/1min) 获取 A 股历史数据并转换为标准化的 Polars DataFrame。
        """
        logger.info(f"正在通过 AkShare 获取 [{symbol}] 的 [{frequency}] 级别数据 ({start_date} -- {end_date})...")

        # ── 临时绕过系统代理，避免 akshare 走代理导致 ProxyError ──────────
        _proxy_keys = ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy")
        _saved_proxies = {k: os.environ.pop(k, None) for k in _proxy_keys}

        try:
            if frequency == "daily":
                ak_start = start_date.replace("-", "")
                ak_end = end_date.replace("-", "")
                
                df_ak = ak.stock_zh_a_hist(
                    symbol=symbol,
                    period="daily",
                    start_date=ak_start,
                    end_date=ak_end,
                    adjust=adjust
                )
            elif frequency in ["1min", "5min"]:
                # 分钟级 API 字典映射处理
                period_map = {"1min": "1", "5min": "5"}
                ak_start = f"{start_date} 09:30:00"
                ak_end = f"{end_date} 15:00:00"
                
                df_ak = ak.stock_zh_a_hist_min_em(
                    symbol=symbol,
                    start_date=ak_start,
                    end_date=ak_end,
                    period=period_map[frequency],
                    adjust=adjust
                )
                if not df_ak.empty:
                    # 分钟级数据的列名为 "时间"，需要重命名为 "日期" 以适配后端的既有逻辑契约
                    if "时间" in df_ak.columns:
                        df_ak.rename(columns={"时间": "日期"}, inplace=True)
            else:
                logger.error(f"不支持的 frequency 参数: {frequency}")
                return None
                
            if df_ak.empty:
                logger.warning(f"数据源返回为空：未能找到股票 '{symbol}' 在此区间的数据。")
                return None

            # 统一转置为多线程性能霸主 Polars
            df_pl = pl.from_pandas(df_ak)
            
            # 策略引擎契约检查
            required_cols = ["日期", "开盘", "收盘", "最高", "最低"]
            missing_cols = [col for col in required_cols if col not in df_pl.columns]
            if missing_cols:
                logger.error(f"数据源返回的列不完整，缺失: {missing_cols}")
                return None
                
            logger.info(f"成功获取并转换数据: 共 {df_pl.height} 行。")
            return df_pl

        except Exception as e:
            logger.error(f"获取股票 [{symbol}] 数据时发生异常: {str(e)}", exc_info=True)
            return None
        finally:
            # ── 恢复原始代理环境变量 ──────────────────────────────────────
            for k, v in _saved_proxies.items():
                if v is not None:
                    os.environ[k] = v
