<template>
  <el-container class="app-container">
    <el-header height="60px" class="header">
      <div class="header-logo">📈</div>
      <h2>TradeSim 智能回测系统</h2>
      <div class="header-nav">
        <router-link to="/simulate" custom v-slot="{ navigate, isActive }">
          <el-button 
            type="primary" 
            :text="!isActive"
            :class="{'nav-active': isActive}"
            @click="navigate"
          >
            <el-icon><DataLine /></el-icon>
            策略回测实验室
          </el-button>
        </router-link>
        
        <router-link to="/dashboard" custom v-slot="{ navigate, isActive }">
          <el-button 
            type="success"
            :text="!isActive"
            :class="{'nav-active': isActive}"
            @click="navigate"
          >
            <el-icon><Star /></el-icon>
            我的历史收藏库
          </el-button>
        </router-link>
      </div>
    </el-header>
    
    <router-view></router-view>
  </el-container>
</template>

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
.header-nav {
  margin-left: auto; /* 推到最右侧 */
  display: flex;
  gap: 15px;
}
.nav-active {
  font-weight: bold;
}
</style>
