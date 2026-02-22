<script setup>
import { ref, reactive, onMounted, nextTick, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import axios from 'axios'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import 'github-markdown-css/github-markdown-light.css'

const route = useRoute()
const router = useRouter()
const loading = ref(true)

const recordId = route.params.id
const chartRef = ref(null)
let chartInstance = null

// 只读表单展示 (左侧)
const form = reactive({
  symbol: '',
  start_date: '',
  end_date: '',
  strategy_name: '',
  strategy_params: {}
})

// 结果指标状态 (右侧)
const metrics = reactive({
  total_return: 0,
  max_drawdown: 0,
  total_trades: 0,
  win_rate: 0
})

const logs = ref([])
const curve = ref([])

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

onMounted(() => {
  chartInstance = echarts.init(chartRef.value)
  window.addEventListener('resize', () => {
    chartInstance.resize()
  })
  fetchDetail()
})

const fetchDetail = async () => {
  loading.value = true
  try {
    const { data } = await axios.get(`http://127.0.0.1:8000/api/v1/records/detail/${recordId}`)
    
    // 注入表单回显
    form.symbol = data.symbol
    form.start_date = data.start_date
    form.end_date = data.end_date
    form.strategy_name = data.strategy_name
    form.strategy_params = data.strategy_params
    
    // 注入右侧结果指标与大流数组
    metrics.total_return = data.total_return
    metrics.max_drawdown = data.max_drawdown
    metrics.win_rate = data.win_rate
    metrics.total_trades = data.total_trades
    
    curve.value = data.equity_curve
    logs.value = [...data.execution_records].reverse().slice(0, 100) // 展示倒序前100笔
    
    nextTick(() => {
      renderChart()
    })
  } catch (error) {
    console.error(error)
    ElMessage.error('无法从服务器获取该记录详情数据，可能已被归档或不存在')
  } finally {
    loading.value = false
  }
}

const formatPct = (val) => {
  if (val === undefined || val === null) return '0.00%'
  return (val * 100).toFixed(2) + '%'
}

const renderChart = () => {
  if (!chartInstance) return
  const dates = curve.value.map(item => item.date)
  const netValues = curve.value.map(item => item.net_value)
  const drawdowns = curve.value.map(item => -item.drawdown * 100)
  
  // 安全平滑检查：如果数据包含 close_price 和 position_utilization，说明是新版四层结构
  const isNewVersion = curve.value.length > 0 && curve.value[0].close_price !== undefined
  
  let option = {}
  
  if (isNewVersion) {
      const benchValues = curve.value.map(item => item.benchmark_value)
      const closePrices = curve.value.map(item => item.close_price)
      const utilValues = curve.value.map(item => item.position_utilization * 100)
      
      const dynamicGrids = []
      if(form.strategy_params.grid_type === 'arithmetic' && form.strategy_params.grid_count) {
          const count = Math.max(1, form.strategy_params.grid_count)
          const step = (form.strategy_params.upper_bound - form.strategy_params.lower_bound) / count
          for (let i = 0; i <= count; i++) {
              dynamicGrids.push({ yAxis: form.strategy_params.lower_bound + i * step, label: { formatter: `{c}` } })
          }
      } else if(form.strategy_params.lower_bound && form.strategy_params.upper_bound && form.strategy_params.grid_step_pct) {
          let currentGrid = form.strategy_params.lower_bound
          while (currentGrid <= form.strategy_params.upper_bound) {
              dynamicGrids.push({ yAxis: currentGrid, label: { formatter: `{c}` } })
              currentGrid *= (1 + form.strategy_params.grid_step_pct)
          }
      }
      
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
      
      option = {
        tooltip: { 
          trigger: 'axis', axisPointer: { type: 'cross' },
          formatter: function (params) {
             let res = `<b>${params[0].axisValue}</b><br/>`;
             params.forEach(item => {
                 if (item.value !== '-' && item.value !== undefined) {
                     let valStr = typeof item.value === 'number' ? item.value.toFixed(2) : item.value;
                     res += `${item.marker} ${item.seriesName}: <b>${valStr}</b><br/>`;
                 }
             });
             return res;
          }
        },
        axisPointer: { link: {xAxisIndex: 'all'} },
        legend: { data: ['标的真实价格', '策略资产净值', '标的基准收益', '仓位利用率(%)', '水下痛苦回撤(%)'], top: 0 },
        grid: [
          { left: '10%', right: '4%', top: '5%', height: '30%' },
          { left: '10%', right: '4%', top: '43%', height: '22%' },
          { left: '10%', right: '4%', top: '72%', height: '11%' },
          { left: '10%', right: '4%', top: '88%', height: '11%' }
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
          { name: '标的真实价格', type: 'line', xAxisIndex: 0, yAxisIndex: 0, data: closePrices, smooth: false, showSymbol: false, lineStyle: { width: 2, color: '#303133', opacity: 0.6 }, markLine: { symbol: 'none', label: { position: 'end' }, lineStyle: { type: 'dashed', color: '#909399', opacity: 0.4 }, data: dynamicGrids } },
          { name: '买入成交动作', type: 'scatter', xAxisIndex: 0, yAxisIndex: 0, data: buyScatterData, symbol: 'circle', symbolSize: 8, itemStyle: { color: '#f56c6c', borderColor: '#fff', borderWidth: 1.5 }, z: 10 },
          { name: '卖出成交动作', type: 'scatter', xAxisIndex: 0, yAxisIndex: 0, data: sellScatterData, symbol: 'circle', symbolSize: 8, itemStyle: { color: '#67c23a', borderColor: '#fff', borderWidth: 1.5 }, z: 10 },
          { name: '策略资产净值', type: 'line', xAxisIndex: 1, yAxisIndex: 1, data: netValues, smooth: true, showSymbol: false, lineStyle: { width: 3, color: '#409EFF' } },
          { name: '标的基准收益', type: 'line', xAxisIndex: 1, yAxisIndex: 1, data: benchValues, smooth: true, showSymbol: false, lineStyle: { width: 2, color: '#E6A23C', type: 'dashed' } },
          { name: '仓位利用率(%)', type: 'line', xAxisIndex: 2, yAxisIndex: 2, data: utilValues, areaStyle: { opacity: 0.2, color: '#67c23a' }, lineStyle: { color: '#67c23a' }, showSymbol: false },
          { name: '水下痛苦回撤(%)', type: 'line', xAxisIndex: 3, yAxisIndex: 3, data: drawdowns, areaStyle: { opacity: 0.2, color: '#f56c6c' }, lineStyle: { color: '#f56c6c' }, showSymbol: false }
        ]
      }
      
  } else {
      // 兼容旧版单一图表渲染
      option = {
        tooltip: { trigger: 'axis' },
        legend: { data: ['策略净值(元)', '回撤幅度(%)'] },
        grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
        xAxis: { type: 'category', data: dates },
        yAxis: [
          { type: 'value', name: '净值 (元)', scale: true, splitLine: { show: true, lineStyle: { type: 'dashed' } } },
          { type: 'value', name: '回撤 (%)', position: 'right', max: 0, splitLine: { show: false } }
        ],
        series: [
          { name: '策略净值(元)', type: 'line', data: netValues, smooth: true, showSymbol: false, lineStyle: { width: 2 } },
          { name: '回撤幅度(%)', type: 'line', yAxisIndex: 1, data: drawdowns, areaStyle: { opacity: 0.3 }, showSymbol: false, lineStyle: { width: 0 } }
        ]
      }
  }

  // 计算完成后重设 DOM 高度以支持四图的超长纵深
  if (isNewVersion && chartRef.value) {
      chartRef.value.style.height = '850px';
      chartInstance.resize();
  }

  chartInstance.setOption(option, true)
}
</script>

<template>
  <el-container class="detail-container">
    <el-main v-loading="loading">
      
      <!-- 顶部操作条 -->
      <div class="breadcrumb-bar">
         <el-button @click="router.back()" :icon="'Back'" plain type="info" size="large" circle></el-button>
         <div class="title-text">
            <span>量化组合档案库  /  </span>
            <b>档案号 #{{ recordId }} (只读快照)</b>
         </div>
         <div style="flex: 1"></div>
         <el-button color="#626aef" :dark="true" @click="startAiAnalysis" style="margin-right: 15px; font-weight: bold;">
            <el-icon style="margin-right: 5px"><Cpu /></el-icon> 🧠 AI 深度复盘研判
         </el-button>
         <el-tag type="success" effect="dark" size="large"><el-icon><Monitor /></el-icon> Mongo冷库联表恢复成功</el-tag>
      </div>

      <el-container class="main-body">
        
        <!-- 左侧参数快照 (只读) -->
        <el-aside width="350px" class="aside-pannel">
          <el-descriptions title="测试环境参数 (快照)" :column="1" border size="small">
            <el-descriptions-item label="交易标的"><el-tag type="info">{{ form.symbol }}</el-tag></el-descriptions-item>
            <el-descriptions-item label="测试起始">{{ form.start_date }}</el-descriptions-item>
            <el-descriptions-item label="测试终了">{{ form.end_date }}</el-descriptions-item>
            <el-descriptions-item label="策略算法">{{ form.strategy_name }}</el-descriptions-item>
          </el-descriptions>

          <h4 style="margin-top: 25px; color: #606266; font-size: 14px;">策略特征超惨对象 (JSON JSONB)</h4>
          <el-card shadow="never" style="background-color: #f8f9fa;">
            <pre class="json-viewer">{{ JSON.stringify(form.strategy_params, null, 2) }}</pre>
          </el-card>
        </el-aside>

        <!-- 右侧回测图表还原 -->
        <el-main class="main-pannel">
           <!-- 四大数据卡片 -->
          <el-row :gutter="20" class="stat-cards">
            <el-col :span="6">
              <el-card shadow="always" style="border-radius: 10px;">
                <div class="stat-title">总收益率</div>
                <div class="stat-val" :style="{color: metrics.total_return >= 0 ? '#f56c6c' : '#67c23a'}">{{ formatPct(metrics.total_return) }}</div>
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
                <div class="stat-title">总交易频次</div>
                <div class="stat-val" style="color: #409EFF">{{ metrics.total_trades }} <span style="font-size: 14px">笔</span></div>
              </el-card>
            </el-col>
            <el-col :span="6">
              <el-card shadow="always" style="border-radius: 10px;">
                <div class="stat-title">历史估胜率</div>
                <div class="stat-val" style="color: #E6A23C">{{ formatPct(metrics.win_rate) }}</div>
              </el-card>
            </el-col>
          </el-row>

          <el-card shadow="always" style="border-radius: 10px; margin-bottom: 20px;">
            <div class="chart-container" ref="chartRef"></div>
          </el-card>

          <el-card shadow="always" style="border-radius: 10px;">
           <el-table :data="logs" stripe style="width: 100%" height="320px">
              <el-table-column prop="timestamp" label="发生日期" width="120" />
              <el-table-column prop="action" label="操作类型" width="120">
                <template #default="scope">
                    <el-tag :type="scope.row.action.includes('BUY') ? 'danger' : 'success'" effect="dark" size="small">{{ scope.row.action }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="price" label="成交价" />
              <el-table-column prop="volume" label="成交股数" />
              <el-table-column prop="amount" label="发生金额">
                <template #default="scope">
                    <span :class="scope.row.action.includes('BUY') ? 'text-success' : 'text-danger'">
                      {{ scope.row.action.includes('BUY') ? '-' : '+' }}{{ scope.row.amount }}
                    </span>
                </template>
              </el-table-column>
            </el-table>
          </el-card>
        </el-main>
      </el-container>
      
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
             <p>数据正在灌入神经网格中，高维解析计算中...</p>
           </div>
        </div>
      </el-drawer>
      
    </el-main>
  </el-container>
</template>

<style scoped>
.detail-container {
  height: calc(100vh - 60px);
  background-color: #f0f2f5;
}
.breadcrumb-bar {
  display: flex;
  align-items: center;
  padding: 10px 20px;
  background-color: #fff;
  border-radius: 8px;
  margin-bottom: 15px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.05);
}
.title-text {
  margin-left: 15px;
  font-size: 16px;
  color: #303133;
}
.main-body {
  height: calc(100vh - 160px);
}
.aside-pannel {
  background-color: #fff;
  padding: 20px;
  border-radius: 8px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.05);
}
.main-pannel {
  padding: 0 0 0 20px;
  overflow-y: auto;
}
.json-viewer {
  font-family: monospace;
  font-size: 13px;
  color: #E6A23C;
  white-space: pre-wrap;
  word-wrap: break-word;
}
.stat-cards {
  margin-bottom: 20px;
}
.stat-title {
  font-size: 13px;
  color: #909399;
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
  height: 350px;
}
</style>
