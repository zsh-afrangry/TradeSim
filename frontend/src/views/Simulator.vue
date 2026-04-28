<script setup>
import { reactive, ref, computed, onMounted, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { QuestionFilled } from '@element-plus/icons-vue'
import axios from 'axios'
import * as echarts from 'echarts'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import 'github-markdown-css/github-markdown-light.css'

const loading = ref(false)
const chartRef = ref(null)
let chartInstance = null

const date_range = ref(['2015-01-01', '2025-01-01'])
const basePosPct = ref(50)

// 初始化表单数据
const form = reactive({
  symbol: '600585',
  start_date: '2015-01-01',
  end_date: '2025-01-01',
  initial_capital: 100000,
  commission_rate: 0.00000,
  slippage: 0.0,
  data_frequency: 'daily',
  strategy_name: 'GRID_TRADING',
  strategy_params: {
    lower_bound: 10.0,
    upper_bound: 50.0,
    grid_type: 'geometric',
    grid_step_pct: 0.05,
    grid_count: 20,
    base_position_ratio: 0.5,
    trade_mode: 'amount',
    funds_per_grid: 10000
  }
})

// 定投金额或股数的验证
const isAmountTooSmall = computed(() => {
    if (form.strategy_params.trade_mode === 'amount') {
        const min_cost = form.strategy_params.lower_bound * 100;
        return form.strategy_params.funds_per_grid < min_cost;
    }
    return false;
})

// 为用户展示等比切割下的对数估算结果以缓解焦虑
const estimatedGeometricGrids = computed(() => {
    const lb = form.strategy_params.lower_bound
    const ub = form.strategy_params.upper_bound
    const pct = form.strategy_params.grid_step_pct
    if (lb > 0 && ub > lb && pct > 0) {
        const ratio = ub / lb;
        const count = Math.log(ratio) / Math.log(1 + pct);
        return Math.floor(count);
    }
    return 0;
})

const logTableRef = ref(null)

// 结果指标状态
const metrics = reactive({
  total_return: 0,
  max_drawdown: 0,
  total_trades: 0,
  win_rate: 0
})

const logs = ref([])
const curve = ref([])

const recentLogs = computed(() => {
  return [...logs.value].reverse().slice(0, 50)
})

const returnColor = computed(() => metrics.total_return >= 0 ? '#f56c6c' : '#67c23a')

const formatPct = (val) => {
  return (val * 100).toFixed(2) + '%'
}

onMounted(() => {
  chartInstance = echarts.init(chartRef.value)
  window.addEventListener('resize', () => {
    chartInstance.resize()
  })
})

const renderChart = () => {
  if (!chartInstance) return
  
  const dates = curve.value.map(item => item.date)
  const netValues = curve.value.map(item => item.net_value)
  const benchValues = curve.value.map(item => item.benchmark_value)
  const closePrices = curve.value.map(item => item.close_price) // 提取真实股票价格
  const utilValues = curve.value.map(item => item.position_utilization * 100)
  const drawdowns = curve.value.map(item => -item.drawdown * 100)
  
  // 核心特性：自动计算并构筑前端环境下的纯显示网格基准线 (markLine)
  const dynamicGrids = []
  if (form.strategy_params.grid_type === 'arithmetic') {
      const count = Math.max(1, form.strategy_params.grid_count)
      const step = (form.strategy_params.upper_bound - form.strategy_params.lower_bound) / count
      for (let i = 0; i <= count; i++) {
          dynamicGrids.push({ yAxis: form.strategy_params.lower_bound + i * step, label: { formatter: `{c}` } })
      }
  } else {
      let currentGrid = form.strategy_params.lower_bound
      while (currentGrid <= form.strategy_params.upper_bound) {
          dynamicGrids.push({ yAxis: currentGrid, label: { formatter: `{c}` } })
          currentGrid *= (1 + form.strategy_params.grid_step_pct)
      }
  }
  
  // 创建与时间轴等长的空数组，用来承载离散买卖点（无交易的日期填 '-'），并在主图绘制实心 Circle 散点
  const buyScatterData = new Array(dates.length).fill('-');
  const sellScatterData = new Array(dates.length).fill('-');
  
  logs.value.forEach(log => {
      const ptIndex = dates.indexOf(log.timestamp)
      if (ptIndex !== -1) {
         if (log.action.includes("BUY")) {
             buyScatterData[ptIndex] = log.price;
         } else if (log.action.includes("SELL")) {
             sellScatterData[ptIndex] = log.price;
         }
      }
  })

  const option = {
    tooltip: { 
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      formatter: function (params) {
         let res = `<b>${params[0].axisValue}</b><br/>`;
         params.forEach(item => {
             // 过滤掉原本为了填位使用的 '-' 空数据
             if (item.value !== '-' && item.value !== undefined) {
                 let valStr = typeof item.value === 'number' ? item.value.toFixed(2) : item.value;
                 
                 // 为不同的系列定制前缀格式，保持图例颜色圆点
                 const marker = item.marker;
                 let seriesName = item.seriesName;
                 res += `${marker} ${seriesName}: <b>${valStr}</b><br/>`;
             }
         });
         return res;
      }
    },
    axisPointer: { link: {xAxisIndex: 'all'} }, // 四图神同步十字光标
    legend: { 
      data: ['标的真实价格', '策略资产净值', '标的基准收益', '仓位利用率(%)', '水下痛苦回撤(%)'],
      top: 0
    },
    grid: [
      { left: '10%', right: '4%', top: '5%', height: '30%' },         // 图1：原生价格 + 密集网格线 (占 30%)
      { left: '10%', right: '4%', top: '43%', height: '22%' },        // 图2：资产净值竞争 (上空闲 8%)
      { left: '10%', right: '4%', top: '72%', height: '11%' },        // 图3：仓位百分比 (上空闲 7%)
      { left: '10%', right: '4%', top: '88%', height: '11%' }         // 图4：水下回撤百分比 (上空闲 5%)
    ],
    xAxis: [
      { type: 'category', data: dates, gridIndex: 0, axisLabel: { show: false }, axisTick: { show: false } },
      { type: 'category', data: dates, gridIndex: 1, axisLabel: { show: false }, axisTick: { show: false } },
      { type: 'category', data: dates, gridIndex: 2, axisLabel: { show: false }, axisTick: { show: false } },
      { type: 'category', data: dates, gridIndex: 3 }
    ],
    yAxis: [
      { type: 'value', name: '股价(元)', nameTextStyle: { padding: [0, 50, 0, 0] }, gridIndex: 0, scale: true },
      { type: 'value', name: '总净值(元)', nameTextStyle: { padding: [0, 50, 0, 0] }, gridIndex: 1, scale: true },
      { type: 'value', name: '仓位(%)', nameTextStyle: { padding: [0, 30, 0, 0] }, gridIndex: 2, min: 0, max: 100 },
      { type: 'value', name: '回撤(%)', nameTextStyle: { padding: [0, 30, 0, 0] }, gridIndex: 3, max: 0 }
    ],
    dataZoom: [
      { type: 'inside', xAxisIndex: [0, 1, 2, 3], start: 0, end: 100 },
      { type: 'slider', xAxisIndex: [0, 1, 2, 3], bottom: '0%' }
    ],
    series: [
      // 图1 - 标的真实价格走势与触发网格
      {
        name: '标的真实价格',
        type: 'line',
        xAxisIndex: 0,
        yAxisIndex: 0,
        data: closePrices,
        smooth: false,
        showSymbol: false,
        lineStyle: { width: 2, color: '#303133', opacity: 0.6 },
        markLine: {
            symbol: 'none',
            label: { position: 'end' },
            lineStyle: { type: 'dashed', color: '#909399', opacity: 0.4 },
            data: dynamicGrids // 前端测算后自动铺上静置网格线！
        }
      },
      // 图1附加 - 离散的买入成交实心点 (Scatter)
      {
        name: '买入成交动作',
        type: 'scatter',
        xAxisIndex: 0,
        yAxisIndex: 0,
        data: buyScatterData,
        symbol: 'circle',
        symbolSize: 8,
        itemStyle: { color: '#f56c6c', borderColor: '#fff', borderWidth: 1.5 },
        z: 10
      },
      // 图1附加 - 离散的卖出成交实心点 (Scatter)
      {
        name: '卖出成交动作',
        type: 'scatter',
        xAxisIndex: 0,
        yAxisIndex: 0,
        data: sellScatterData,
        symbol: 'circle',
        symbolSize: 8,
        itemStyle: { color: '#67c23a', borderColor: '#fff', borderWidth: 1.5 },
        z: 10
      },
      // 图2 - 本产品策略对抗基准的净值
      {
        name: '策略资产净值',
        type: 'line',
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: netValues,
        smooth: true,
        showSymbol: false,
        lineStyle: { width: 3, color: '#409EFF' }
      },
      {
        name: '标的基准收益',
        type: 'line',
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: benchValues,
        smooth: true,
        showSymbol: false,
        lineStyle: { width: 2, color: '#E6A23C', type: 'dashed' }
      },
      // 图3 - 仓位占比面积
      {
        name: '仓位利用率(%)',
        type: 'line',
        xAxisIndex: 2,
        yAxisIndex: 2,
        data: utilValues,
        areaStyle: { opacity: 0.2, color: '#67c23a' },
        lineStyle: { color: '#67c23a' },
        showSymbol: false
      },
      // 图4 - 回撤面积
      {
        name: '水下痛苦回撤(%)',
        type: 'line',
        xAxisIndex: 3,
        yAxisIndex: 3,
        data: drawdowns,
        areaStyle: { opacity: 0.2, color: '#f56c6c' },
        lineStyle: { color: '#f56c6c' },
        showSymbol: false
      }
    ]
  }
  chartInstance.setOption(option, true)
  
  // 注入穿透层交互：点击图表上的买卖点时，联动下面的 Table 滚动至对应行
  chartInstance.off('click')
  chartInstance.on('click', function (params) {
      if (params.seriesType === 'scatter' && (params.seriesName.includes('买入') || params.seriesName.includes('卖出'))) {
          const clickDate = dates[params.dataIndex];
          highlightAndScrollToLogRow(clickDate)
      }
  })
}

// 供事件绑定的：穿透表格查阅能力
const highlightAndScrollToLogRow = (dateStr) => {
    // 寻找表格数据源中对应日期的一行
    const index = recentLogs.value.findIndex(row => row.timestamp === dateStr)
    if (index !== -1) {
        ElMessage.warning(`触发靶向追溯: 正锁定 ${dateStr} 日志详情`)
        // 如果用 Element Table，可通过 setCurrentRow 或自定义高亮 class 来实现，此处暂用简单日志代替强滚动
        console.log("联动找到对应日志: ", recentLogs.value[index])
    }
}

// 反向穿透：当在表格中点击某行时，在图表上飞跃缩放过去
const handleRowClick = (row) => {
    if (!chartInstance) return
    
    // 寻找对应日期在 dates 里的下标
    const dates = curve.value.map(item => item.date)
    const targetIdx = dates.indexOf(row.timestamp)
    
    if (targetIdx !== -1) {
        // 计算前后 10 根 K 线的缩放窗口
        const total = dates.length
        const startWindow = Math.max(0, targetIdx - 10)
        const endWindow = Math.min(total - 1, targetIdx + 10)
        
        // 缩放图表
        chartInstance.dispatchAction({
            type: 'dataZoom',
            startValue: dates[startWindow],
            endValue: dates[endWindow]
        })
        
        chartInstance.dispatchAction({
            type: 'showTip',
            seriesIndex: 0,
            dataIndex: targetIdx
        })
        
        ElMessage.success(`穿透追踪: 飞跃至 ${row.timestamp} ${row.action} 动作发生点`)
    }
}

// AI 交互状态
const aiDrawerVisible = ref(false)
const aiContent = ref('')
const aiHtml = computed(() => {
    try {
        return DOMPurify.sanitize(marked.parse(aiContent.value || ''))
    } catch(err) {
        console.error("Markdown parse error:", err)
        return aiContent.value
    }
})

const startAiAnalysis = async () => {
    // 只有当有回测结果时才允许召唤 AI
    if (metrics.total_trades === 0 && metrics.total_return === 0) {
        ElMessage.warning('请先点击 🚀 发射回测引擎，产出结果后再呼叫 AI 分析！')
        return
    }
    
    aiDrawerVisible.value = true
    aiContent.value = ''
    try {
        const response = await fetch('http://127.0.0.1:8000/api/v1/ai/analyze-stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                symbol: form.symbol,
                start_date: form.start_date,
                end_date: form.end_date,
                strategy_name: form.strategy_name,
                strategy_params: form.strategy_params,
                metrics: metrics
            })
        })
        
        if (!response.body) return
        const reader = response.body.getReader()
        const decoder = new TextDecoder()
        
        let partialLine = ''
        while(true) {
             const { done, value } = await reader.read()
             if (done) break
             
             const chunkStr = partialLine + decoder.decode(value, { stream: true })
             const lines = chunkStr.split('\n')
             partialLine = lines.pop() || ''
             
             for (let line of lines) {
                 line = line.trim()
                 if (line.startsWith('data: ')) {
                     const dataPayload = line.substring(6)
                     if (dataPayload === '[DONE]') break
                     try {
                         const obj = JSON.parse(dataPayload)
                         if(obj.content) {
                             aiContent.value += obj.content
                         }
                     } catch(err) {
                     }
                 }
             }
        }
    } catch(e) {
        console.error(e)
        aiContent.value = '> **网络遭遇阻击**\n\nAI 通讯中转节点抛出异常，未能唤醒分析引擎。'
    }
}

// 保持最新跑出的response本体
let currentResponse = null;

const runTest = async () => {
  if (isAmountTooSmall.value) {
    return ElMessage.error('每格交易金额过小，无法在底价买入最少100股验证将不通过！')
  }
  
  loading.value = true
  // 组装最新状态给到引擎
  form.start_date = date_range.value[0]
  form.end_date = date_range.value[1]
  form.strategy_params.base_position_ratio = basePosPct.value / 100

  try {
    const { data } = await axios.post('http://127.0.0.1:8000/api/v1/simulate/run', form)
    currentResponse = data
    
    // 更新指标
    Object.assign(metrics, data.metrics)
    logs.value = data.execution_records
    curve.value = data.equity_curve
    
    ElMessage.success('回测完毕！')
    
    // 渲染图表
    nextTick(() => {
      renderChart()
    })

  } catch (error) {
    console.error(error)
    ElMessage.error(error.response?.data?.detail || '回测异常，请检查网络或参数')
  } finally {
    loading.value = false
  }
}

const isSaving = ref(false)
const saveRecord = async () => {
  if (!currentResponse) {
    return ElMessage.warning('请先运行一次回测再进行收藏！')
  }
  isSaving.value = true
  try {
    await axios.post('http://127.0.0.1:8000/api/v1/records/save-favorite', {
      request: form,
      response: currentResponse
    })
    ElMessage.success('🚀 已成功写入 MySQL 和 MongoDB 的温冷分离集群！')
  } catch (e) {
    console.error(e)
    ElMessage.error('数据库存储异常')
  } finally {
    isSaving.value = false
  }
}
</script>

<template>
  <el-container class="app-container">
    <el-container class="main-body">
      <!-- 左侧表单区域 -->
      <el-aside width="400px" class="aside-pannel">
        <el-form :model="form" label-width="120px" size="small" label-position="left">
          
          <el-divider content-position="left">基础环境配置</el-divider>
          <el-form-item label="股票代码">
            <el-input v-model="form.symbol" placeholder="如: 000400" />
          </el-form-item>
          <el-form-item label="时间粒度">
            <el-select v-model="form.data_frequency" style="width: 100%">
              <el-option label="日线 (极速回放)" value="daily" />
              <el-option label="5分钟线 (精细模拟)" value="5min" />
              <el-option label="1分钟线 (极限穿透)" value="1min" />
            </el-select>
          </el-form-item>
          <el-form-item label="时间范围">
            <el-date-picker 
              v-model="date_range" 
              type="daterange" 
              range-separator="至" 
              start-placeholder="开始日期" 
              end-placeholder="结束日期" 
              value-format="YYYY-MM-DD" 
              style="width: 100%" 
            />
          </el-form-item>
          <el-form-item label="初始资金">
            <el-input-number v-model="form.initial_capital" :step="10000" style="width: 100%" />
          </el-form-item>
          
          <el-collapse>
            <el-collapse-item name="1">
              <template #title>
                <strong>⚙️ 进阶：交易摩擦与滑点</strong>
              </template>
              <div style="padding: 10px 0;">
                  <el-form-item>
                    <template #label>
                      双边摩擦费率
                      <el-tooltip content="单边买入和卖出时均会扣除的规费及互不抵消的佣金比例" placement="top">
                        <el-icon style="margin-left: 2px; color: #909399; margin-top: 5px; cursor: help;"><QuestionFilled /></el-icon>
                      </el-tooltip>
                    </template>
                    <el-input-number v-model="form.commission_rate" :step="0.0001" :precision="5" style="width: 100%" />
                  </el-form-item>
                  
                  <el-form-item>
                    <template #label>
                      单边滑点(元)
                      <el-tooltip content="模拟真实交易价格延迟: 买入更贵，卖出更廉价" placement="top">
                        <el-icon style="margin-left: 2px; color: #909399; margin-top: 5px; cursor: help;"><QuestionFilled /></el-icon>
                      </el-tooltip>
                    </template>
                    <el-input-number v-model="form.slippage" :step="0.01" style="width: 100%" />
                  </el-form-item>
              </div>
            </el-collapse-item>
          </el-collapse>
          
          <el-divider content-position="left">核心策略与参数定距</el-divider>
          <el-form-item label="策略驱动核心">
            <el-select v-model="form.strategy_name" style="width: 100%">
              <el-option label="网格交易 (GRID)" value="GRID_TRADING" />
            </el-select>
          </el-form-item>
          
          <el-form-item label="网格下限价">
            <el-input-number v-model="form.strategy_params.lower_bound" :step="1" style="width: 100%" />
          </el-form-item>
          <el-form-item label="网格上限价">
            <el-input-number v-model="form.strategy_params.upper_bound" :step="1" style="width: 100%" />
          </el-form-item>
          
          <el-form-item label="网格切分模式">
            <el-select v-model="form.strategy_params.grid_type" style="width: 100%">
              <el-option label="等比划分 (按百分比间距)" value="geometric" />
              <el-option label="等差划分 (均分价格差)" value="arithmetic" />
            </el-select>
          </el-form-item>
          
          <el-form-item label="网格间距(%)" v-if="form.strategy_params.grid_type === 'geometric'">
            <el-input-number v-model="form.strategy_params.grid_step_pct" :step="0.01" :precision="2" style="width: 100%" />
            <div style="color: #909399; font-size: 11px; line-height: 1.2; margin-top: 4px; width: 100%;">
              (预估区间将被切割为约 {{ estimatedGeometricGrids }} 格)
            </div>
          </el-form-item>

          <el-form-item label="网格数量(格)" v-if="form.strategy_params.grid_type === 'arithmetic'">
            <el-input-number v-model="form.strategy_params.grid_count" :step="1" :min="1" :precision="0" style="width: 100%" />
            <div style="color: #909399; font-size: 11px; line-height: 1.2; margin-top: 4px; width: 100%;">
              (每格上下价格差约为 {{ ((form.strategy_params.upper_bound - form.strategy_params.lower_bound) / form.strategy_params.grid_count).toFixed(2) }} 元)
            </div>
          </el-form-item>
          
          <el-form-item>
            <template #label>
              建仓底仓比(%)
              <el-tooltip content="首个交易日，按该资金比例重仓打底，涨时出货使用" placement="top">
                <el-icon style="margin-left: 4px; color: #909399; margin-top: 5px; cursor: help;"><QuestionFilled /></el-icon>
              </el-tooltip>
            </template>
            <el-input-number v-model="basePosPct" :step="5" :precision="0" :max="100" :min="0" style="width: 100%" />
          </el-form-item>
          
          <el-form-item>
            <template #label>
              交易模式设定
              <el-tooltip content="【固定资金】代表每次用钱拉满；【固定股数】代表保证手数一致" placement="top">
                <el-icon style="margin-left: 4px; color: #909399; margin-top: 5px; cursor: help;"><QuestionFilled /></el-icon>
              </el-tooltip>
            </template>
            <el-select v-model="form.strategy_params.trade_mode" style="width: 100%">
              <el-option label="每次交易 固定金额 (元)" value="amount" />
              <el-option label="每次交易 固定股数 (股)" value="volume" />
            </el-select>
          </el-form-item>

          <el-form-item>
            <template #label>
              {{ form.strategy_params.trade_mode === 'amount' ? '每格交易额' : '每格交易量' }}
              <el-tooltip content="每次碰到网格触发点时分配的动能" placement="top">
                <el-icon style="margin-left: 4px; color: #909399; margin-top: 5px; cursor: help;"><QuestionFilled /></el-icon>
              </el-tooltip>
            </template>
            <el-input-number 
               v-model="form.strategy_params.funds_per_grid" 
               :step="form.strategy_params.trade_mode === 'amount' ? 5000 : 100" 
               style="width: 100%" 
            />
            <div v-if="isAmountTooSmall" style="color: #F56C6C; font-size: 11px; line-height: 1.2; margin-top: 4px; width: 100%;">
              ⚠️ 预警: 当前定额甚至不够在下限网格买入1手股票 (即100股)，此测算可能被拒接。
            </div>
          </el-form-item>
          
          <div style="margin-top: 30px; text-align: center;">
            <el-button type="primary" size="large" :loading="loading" @click="runTest" style="width: 100%; border-radius: 8px;">🚀 发射回测引擎</el-button>
            <el-button type="warning" plain size="large" :loading="isSaving" @click="saveRecord" style="width: 100%; border-radius: 8px; margin-top: 15px; margin-left: 0;">💾 将该次组合列为【收藏】</el-button>
          </div>
        </el-form>
      </el-aside>
      
      <!-- 右侧数据展示区域 -->
      <el-main class="main-pannel" style="background-color: #f0f2f5;">
        
        <!-- 四大数据卡片 -->
        <el-row :gutter="20" class="stat-cards">
          <el-col :span="6">
            <el-card shadow="always" style="border-radius: 10px;">
              <div class="stat-title">总收益率</div>
              <div class="stat-val" :style="{color: returnColor}">{{ formatPct(metrics.total_return) }}</div>
            </el-card>
          </el-col>
          <el-col :span="6">
            <el-card shadow="always" style="border-radius: 10px;">
              <div class="stat-title">最大回撤</div>
              <div class="stat-val text-danger">{{ formatPct(metrics.max_drawdown) }}</div>
            </el-card>
          </el-col>
          <el-col :span="6">
            <el-card shadow="always" style="border-radius: 10px;">
              <div class="stat-title">交易频次</div>
              <div class="stat-val" style="color: #409EFF">{{ metrics.total_trades }} <span style="font-size: 14px">笔</span></div>
            </el-card>
          </el-col>
          <el-col :span="6">
            <el-card shadow="always" style="border-radius: 10px;">
              <div class="stat-title">胜率</div>
              <div class="stat-val" style="color: #E6A23C">{{ formatPct(metrics.win_rate) }}</div>
            </el-card>
          </el-col>
        </el-row>
        
        <!-- 资金曲线 ECharts -->
        <el-card shadow="always" style="border-radius: 10px; margin-bottom: 20px;">
          <template #header>
            <div class="card-header" style="display: flex; justify-content: space-between; align-items: center;">
              <span>四轴专业微观刻画引擎 (顶层:股价与网格, 中层:策略净值竞跑, 辅窗:仓位及水下回撤)</span>
              <el-button color="#626aef" :dark="true" @click="startAiAnalysis" style="font-weight: bold;">
                <el-icon style="margin-right: 5px"><Cpu /></el-icon> 🧠 召唤 AI 深度复盘研判
              </el-button>
            </div>
          </template>
          <!-- 这里使用超高 800px 尺寸来塞入最震撼的四轴宏大世界观，并拉开充足间隔避免重叠 -->
          <div class="chart-container" ref="chartRef" style="height: 850px;"></div>
        </el-card>
        
        <!-- 交易流水明细 -->
        <el-card shadow="always" style="border-radius: 10px;">
          <template #header>
             <div class="card-header">
              <span>近期交易流水 (倒序 50 笔) - 💡支持双向透传: [点击图表气泡定位表格] 或 [点击此表格行缩放图表]</span>
            </div>
          </template>
          <el-table 
            ref="logTableRef"
            :data="recentLogs" 
            stripe 
            style="width: 100%; cursor: pointer;" 
            height="350px"
            @row-click="handleRowClick"
          >
            <el-table-column prop="timestamp" label="发生日期" width="120" />
            <el-table-column prop="action" label="操作类型" width="120">
               <template #default="scope">
                  <el-tag :type="scope.row.action.includes('BUY') ? 'danger' : 'success'" effect="dark" size="small">
                    {{ scope.row.action }}
                  </el-tag>
               </template>
            </el-table-column>
            <el-table-column prop="price" label="成交滑点价(元)" />
            <el-table-column prop="volume" label="成交股数" />
            <el-table-column prop="amount" label="发生金额(元)">
               <template #default="scope">
                  <span :class="scope.row.action.includes('BUY') ? 'text-success' : 'text-danger'">
                    {{ scope.row.action.includes('BUY') ? '-' : '+' }}{{ scope.row.amount }}
                  </span>
               </template>
            </el-table-column>
            <el-table-column prop="commission" label="规费与滑点成本">
              <template #default="scope">
                <span style="color: #E6A23C; font-size: 13px;">
                  佣: {{ scope.row.commission }} | 滑: {{ scope.row.slippage_cost }}
                </span>
              </template>
            </el-table-column>
          </el-table>
        </el-card>

        <!-- 隐藏的 AI 智能脑回放抽屉 -->
        <el-drawer
          v-model="aiDrawerVisible"
          title="⚠️ 机构级量化全栈剖析"
          direction="rtl"
          size="45%"
          :with-header="true"
        >
          <div style="padding: 0 10px; height: 100%; overflow-y: auto;">
             <div class="markdown-body" v-html="aiHtml" style="font-size: 14.5px; line-height: 1.6;"></div>
             <div v-if="!aiContent" style="text-align: center; margin-top: 50px; color: #909399;">
               <el-icon class="is-loading" style="font-size: 30px;"><Loading /></el-icon>
               <p>正在拉取最新模拟测试数据，高维解析计算中...</p>
             </div>
          </div>
        </el-drawer>

      </el-main>
    </el-container>
  </el-container>
</template>

<style>
/* Reset basic styles */
html, body {
  margin: 0;
  padding: 0;
  height: 100%;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
}

#app {
  height: 100vh;
}

.app-container {
  height: 100%;
}

.header {
  background-color: #2c3e50;
  color: #fff;
  display: flex;
  align-items: center;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.2);
  z-index: 10;
}

.header-logo {
  font-size: 28px;
  margin-right: 15px;
}

.header h2 {
  margin: 0;
  font-weight: 500;
  letter-spacing: 1px;
}

.main-body {
  height: calc(100vh - 60px);
}

.aside-pannel {
  background-color: #fff;
  padding: 20px;
  border-right: 1px solid #e4e7ed;
  overflow-y: auto;
  box-shadow: 2px 0 8px rgba(0,0,0,0.05);
}

.main-pannel {
  padding: 20px;
  overflow-y: auto;
}

.text-center {
  text-align: center;
}

.stat-cards {
  margin-bottom: 20px;
}

.stat-title {
  font-size: 13px;
  color: #909399;
  text-transform: uppercase;
}

.stat-val {
  font-size: 26px;
  font-weight: bold;
  margin-top: 8px;
  font-family: monospace;
}

.text-danger { color: #f56c6c; }
.text-success { color: #67c23a; }

.chart-container {
  width: 100%;
  height: 400px;
}

.card-header {
  font-weight: bold;
  color: #303133;
}
</style>
