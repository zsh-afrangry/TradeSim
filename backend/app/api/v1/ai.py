from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Dict, Any
from openai import AsyncOpenAI
import json

from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

# 获取异步 OpenAI 客户端
client = AsyncOpenAI(
    api_key=settings.LLM_API_KEY,
    base_url=settings.LLM_BASE_URL
)

class AIAnalyzeRequest(BaseModel):
    symbol: str
    start_date: str
    end_date: str
    strategy_name: str
    strategy_params: Dict[str, Any]
    metrics: Dict[str, Any]

@router.post("/analyze-stream", summary="流式研判大屏幕回测结果")
async def analyze_stream(req: AIAnalyzeRequest):
    async def generate_chunks():
        # 这里拦截一下如果用户没有配置 key，给个错误提示的 Markdown 字符流
        if not settings.LLM_API_KEY or "修改为您的真实" in settings.LLM_API_KEY:
            yield "data: " + json.dumps({"content": "> **⚠️ 阻断拦截**：未能侦测到了有效的 LLM_API_KEY，请检查后端的 `.env` 文件配置。\n\n我已经准备就绪，只要赐给我算力接口，我就能为您诊断！"}, ensure_ascii=False) + "\n\n"
            yield "data: [DONE]\n\n"
            return
            
        system_prompt = "你是机构级量化回测复盘分析师。你的目标不是精确算数，而是解释“为什么盈利/为什么亏损”：用策略机制推导结果，指出最可能的1-3个根因，并用输入的配置与关键指标作为证据支撑。禁止编造未提供的数据；不确定就用“更可能/较可能”并说明依据来自哪些字段。风格：冷静、尖锐、直给，不寒暄。"
        
        # 组装参数
        p = req.strategy_params
        m = req.metrics
        
        user_prompt = f"""
        【回测上下文】
        * 标的片段：{req.symbol}  ({req.start_date} ~ {req.end_date})
        * 选用流派：{req.strategy_name}
        * 配置面具：底仓配置 {p.get('base_position_ratio', 0.5)*100}%, 网格区间 [{p.get('lower_bound')} ~ {p.get('upper_bound')}], 切分模式: {p.get('grid_type','geometric')}, 间距: {p.get('grid_step_pct',5)}%, 每笔消耗: {p.get('funds_per_grid')}
        * 战损通报：累计收益率 {m.get('total_return', 0)*100:.2f}%, 极致痛点(满回撤) {m.get('max_drawdown', 0)*100:.2f}%, 发生割肉/盈利等累计交易单 {m.get('total_trades', 0)} 宗, 胜率约为 {m.get('win_rate',0)*100:.2f}%
        
        【内部思考要求】
        先在心里选出最可能的 1 个主因 + 2 个次因（从区间错配/仓位极值/趋势环境/摩擦成本里选），再围绕它们写分析。
        
        【任务】
        请解释这次网格回测“为什么会盈利/为什么会亏损”。不要做精确算数推导；用机制解释即可，但每个关键判断必须引用至少一个输入字段或指标作为证据（例如：网格上下限、底仓比例、每笔规模、总收益、最大回撤、交易次数、胜率、时间区间、时间粒度）。

        你可以自由组织表达，不要求固定模板，但必须覆盖以下四类归因锚点（可合并）：
        - 区间匹配：网格区间与标的主要价格运行区间是否错配？错配会导致什么后果？
        - 仓位极值风险：底仓比例 + 每笔下单规模是否容易把策略推到“空仓/满仓”的两端？对应“卖飞/接盘”的哪一种？
        - 市场形态：结合时间范围内可能存在的趋势段/震荡段，解释网格在这些环境下的典型表现。
        - 交易摩擦：如果交易次数很大但收益一般/为负，指出交易成本或反复止盈止损磨损的可能性（若未提供手续费/滑点，就明确说明缺失）。

        输出要求：
        - 只用 Markdown 的标题(##/###)、粗体、无序列表。
        - 禁止寒暄。
        - 结尾给出“最值得优先改的 2~3 个参数方向”（只给方向，不需要算数）。
        """

        try:
            stream = await client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                stream=True,
                temperature=0.7
            )
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    yield "data: " + json.dumps({"content": content}, ensure_ascii=False) + "\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            logger.error(f"调用 AI 出错: {e}")
            yield "data: " + json.dumps({"content": f"\n\n**API 召唤失败**:\n`{str(e)}`\n请检查网络环境或配额。"}, ensure_ascii=False) + "\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(generate_chunks(), media_type="text/event-stream")
