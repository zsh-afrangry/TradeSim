<template>
  <el-container class="app-container">
    <el-aside :width="isCollapsed ? '64px' : '200px'" class="sidebar">
      <div class="sidebar-logo" @click="toggleCollapse">
        <span class="logo-icon">📈</span>
        <span v-if="!isCollapsed" class="logo-text">TradeSim</span>
      </div>

      <el-menu
        :default-active="$route.path"
        :collapse="isCollapsed"
        :collapse-transition="true"
        router
        class="sidebar-menu"
      >
        <el-menu-item index="/simulate">
          <el-icon><DataLine /></el-icon>
          <template #title>网格回测</template>
        </el-menu-item>

        <el-menu-item index="/yearline">
          <el-icon><TrendCharts /></el-icon>
          <template #title>年线策略</template>
        </el-menu-item>

        <el-menu-item index="/dashboard">
          <el-icon><Star /></el-icon>
          <template #title>收藏库</template>
        </el-menu-item>
      </el-menu>

      <div class="sidebar-collapse-btn" @click="toggleCollapse">
        <el-icon>
          <ArrowLeft v-if="!isCollapsed" />
          <ArrowRight v-else />
        </el-icon>
      </div>
    </el-aside>

    <el-main class="main-content">
      <router-view></router-view>
    </el-main>
  </el-container>
</template>

<script setup>
import { ref } from 'vue'
import { DataLine, Star, ArrowLeft, ArrowRight, TrendCharts } from '@element-plus/icons-vue'

const isCollapsed = ref(false)

function toggleCollapse() {
  isCollapsed.value = !isCollapsed.value
}
</script>

<style>
html, body {
  margin: 0;
  padding: 0;
  height: 100%;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
}

#app {
  height: 100vh;
}
</style>

<style scoped>
.app-container {
  height: 100vh;
}

.sidebar {
  background-color: #2c3e50;
  display: flex;
  flex-direction: column;
  transition: width 0.3s;
  overflow: hidden;
}

.sidebar-logo {
  height: 60px;
  display: flex;
  align-items: center;
  padding: 0 20px;
  cursor: pointer;
  color: #fff;
  border-bottom: 1px solid rgba(255,255,255,0.1);
  white-space: nowrap;
  overflow: hidden;
}

.logo-icon {
  font-size: 24px;
  flex-shrink: 0;
}

.logo-text {
  margin-left: 10px;
  font-size: 16px;
  font-weight: 600;
  letter-spacing: 1px;
}

.sidebar-menu {
  flex: 1;
  border-right: none;
  background-color: #2c3e50;
  --el-menu-bg-color: #2c3e50;
  --el-menu-text-color: #bdc3c7;
  --el-menu-active-color: #fff;
  --el-menu-hover-bg-color: #34495e;
  --el-menu-item-height: 52px;
}

.sidebar-collapse-btn {
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #bdc3c7;
  cursor: pointer;
  border-top: 1px solid rgba(255,255,255,0.1);
  transition: background-color 0.2s;
}

.sidebar-collapse-btn:hover {
  background-color: #34495e;
  color: #fff;
}

.main-content {
  padding: 0;
  overflow: auto;
  background-color: #f0f2f5;
}
</style>
