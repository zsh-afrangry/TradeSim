<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import axios from 'axios'
import { ElMessage } from 'element-plus'

const router = useRouter()
const loading = ref(false)
const tableData = ref([])

const fetchList = async () => {
    loading.value = true
    try {
        const { data } = await axios.get('http://127.0.0.1:8000/api/v1/records/list')
        tableData.value = data
    } catch(e) {
        console.error(e)
        ElMessage.error("检索回测收藏列表失败")
    } finally {
        loading.value = false
    }
}

onMounted(() => {
    fetchList()
})

const getReturnTagType = (val) => {
    if(val > 0.1) return 'danger'
    if(val > 0) return 'warning'
    return 'success'
}

const formatPct = (val) => {
    if(val === undefined || val === null) return '0.00%'
    return (val * 100).toFixed(2) + '%'
}
</script>

<template>
  <el-container class="dashboard-pannel fade-in">
    <el-main>
      <el-card shadow="never" style="border-radius: 12px; height: 100%">
        <template #header>
          <div style="display: flex; justify-content: space-between; align-items: center;">
            <div style="font-weight: bold; font-size: 18px; color: #303133;">
              <el-icon style="margin-right: 8px"><Trophy /></el-icon>
              量化组合收藏家榜单 
              <span style="font-size: 13px; font-weight: normal; color: #909399; margin-left:10px;">(数据直达 MySQL，按总收益率逆序速排)</span>
            </div>
            <el-button @click="fetchList" plain type="info" :icon="'Refresh'" circle></el-button>
          </div>
        </template>
        
        <el-table 
          v-loading="loading" 
          :data="tableData" 
          height="calc(100vh - 200px)"
          stripe 
          border
          style="width: 100%"
        >
          <el-table-column type="index" label="排名" width="70" align="center" fixed />
          <el-table-column prop="symbol" label="交易品种" width="120" align="center">
            <template #default="scope">
                <el-tag effect="plain" type="info" size="large"><b>{{ scope.row.symbol }}</b></el-tag>
            </template>
          </el-table-column>
          
          <el-table-column prop="total_return" label="累积总收益率" width="180" align="center" sortable>
            <template #default="scope">
                <el-tag :type="getReturnTagType(scope.row.total_return)" effect="dark" style="font-size: 15px;">
                   {{ formatPct(scope.row.total_return) }}
                </el-tag>
            </template>
          </el-table-column>
          
          <el-table-column prop="max_drawdown" label="期内最大痛点(回撤)" width="180" align="center">
            <template #default="scope">
                <span style="color: #67c23a; font-weight: bold">{{ formatPct(scope.row.max_drawdown) }}</span>
            </template>
          </el-table-column>
          
          <el-table-column prop="win_rate" label="盈亏交易比(估胜率)" width="160" align="center">
            <template #default="scope">
                <span style="color: #E6A23C">{{ formatPct(scope.row.win_rate) }}</span>
            </template>
          </el-table-column>

          <el-table-column prop="total_trades" label="总交割笔数" width="120" align="center" />
          
          <el-table-column prop="strategy_name" label="使用流派" width="180" align="center">
             <template #default="scope">
                <el-tag size="small">{{ scope.row.strategy_name }}</el-tag>
             </template>
          </el-table-column>

          <el-table-column prop="created_at" label="入库留存时间" align="center" />
          
          <el-table-column label="详情 (Mongo)" width="120" align="center" fixed="right">
             <template #default="scope">
                <el-button type="primary" link @click="router.push('/detail/' + scope.row.id)">查阅档案</el-button>
             </template>
          </el-table-column>

        </el-table>
      </el-card>
    </el-main>
  </el-container>
</template>

<style scoped>
.dashboard-pannel {
  height: calc(100vh - 60px);
  background-color: #f0f2f5;
  padding: 15px;
}

.fade-in {
  animation: fadeIn 0.4s;
}

@keyframes fadeIn {
  0% { opacity: 0; transform: translateY(10px); }
  100% { opacity: 1; transform: translateY(0); }
}
</style>
