# Task 1 - 第二个交易策略：前端导航改造

## 目标
为新增交易策略腾出位置，将顶部 header 导航改为可折叠左侧边栏。

## 已完成改动

### 1. `frontend/src/App.vue`
- 移除顶部 `el-header`
- 改为全高 `el-aside` 左侧边栏，使用 `el-menu` 组件
- 展开宽度 200px，折叠宽度 64px（保留图标）
- 侧边栏顶部显示 logo + 品牌名，折叠时只显示 logo
- 底部折叠/展开按钮（ArrowLeft / ArrowRight 图标）
- 菜单项：网格回测（/simulate）、年线策略（/yearline）、收藏库（/dashboard）

### 2. `frontend/src/router/index.js`
- 新增 `/yearline` 路由，懒加载 `YearLineStrategy.vue`

### 3. `frontend/src/views/YearLineStrategy.vue`（新建）
- 年线策略页面空壳，显示"开发中"占位

## 后续
- 年线策略具体逻辑待实现（后端 + 前端）
