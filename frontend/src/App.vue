<script setup lang="ts">
// 页面骨架（T24s）：登录后左侧是导航栏，右侧是内容区（最宽 1200px，居中）；
// 登录页不显示导航栏。窄屏（≤768px）时导航栏收成页面顶部的一行。
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { auth, logout } from './auth'
import AppIcon from './components/AppIcon.vue'
import ThemePicker from './features/theme/ThemePicker.vue'

const route = useRoute()
const router = useRouter()

const showShell = computed(() => auth.user !== null && route.name !== 'login')
// 预览页从文件列表或检索结果进入，都归在“文件”下面
const activeNav = computed(() => (route.name === 'search' ? 'search' : 'documents'))
const initial = computed(() => (auth.user?.username.slice(0, 1) ?? '').toUpperCase())

function onLogout() {
  logout()
  void router.push({ name: 'login' })
}
</script>

<template>
  <div v-if="showShell" class="shell">
    <aside class="sidebar">
      <div class="brand">
        <span class="app-logo"><AppIcon name="docs" :size="20" /></span>
        <span class="brand-text">智能文档管理系统</span>
      </div>
      <nav class="nav">
        <router-link :to="{ name: 'documents' }" class="nav-item" :class="{ active: activeNav === 'documents' }">
          <AppIcon name="folder" />
          文件
        </router-link>
        <router-link :to="{ name: 'search' }" class="nav-item" :class="{ active: activeNav === 'search' }">
          <AppIcon name="search" />
          检索
        </router-link>
      </nav>
      <div class="user">
        <div class="user-name">
          <span class="avatar">{{ initial }}</span>
          <span class="user-text" :title="auth.user?.username">{{ auth.user?.username }}</span>
          <el-tag v-if="auth.user?.role === 'admin'" size="small" type="warning">管理员</el-tag>
        </div>
        <el-button link class="logout" @click="onLogout">
          <AppIcon name="logout" :size="16" />
          退出登录
        </el-button>
      </div>
    </aside>
    <main class="content">
      <div class="content-inner">
        <router-view />
      </div>
    </main>
  </div>
  <router-view v-else />
  <!-- 系统配色面板（演示用），所有页面都有 -->
  <ThemePicker />
</template>

<style scoped>
.shell {
  display: grid;
  grid-template-columns: var(--app-sidebar-width) minmax(0, 1fr);
  min-height: 100vh;
}

.sidebar {
  position: sticky;
  top: 0;
  display: flex;
  flex-direction: column;
  gap: 24px;
  height: 100vh;
  box-sizing: border-box;
  padding: 20px 12px 16px;
  background: var(--app-surface);
  border-right: 1px solid var(--app-border);
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 6px;
  font-size: 15px;
  font-weight: 600;
  line-height: 1.3;
}

.nav {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 12px;
  border-radius: var(--app-radius);
  color: var(--app-text-regular);
  font-size: 14px;
  text-decoration: none;
}

.nav-item:hover {
  background: var(--el-fill-color);
}

.nav-item.active {
  background: var(--app-primary-soft);
  color: var(--app-primary);
  font-weight: 600;
}

.user {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
  margin-top: auto;
  padding: 12px 6px 0;
  border-top: 1px solid var(--app-border);
}

.user-name {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  min-width: 0;
}

.avatar {
  display: flex;
  flex: none;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--el-fill-color);
  color: var(--app-text-regular);
  font-size: 13px;
  font-weight: 600;
}

.user-text {
  overflow: hidden;
  font-size: 14px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.logout {
  color: var(--app-text-secondary);
}

.logout :deep(> span) {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.content {
  min-width: 0;
}

.content-inner {
  box-sizing: border-box;
  max-width: var(--app-content-max);
  margin: 0 auto;
  padding: 24px 32px 40px;
}

@media (max-width: 768px) {
  .shell {
    grid-template-columns: minmax(0, 1fr);
  }

  .sidebar {
    position: static;
    flex-direction: row;
    flex-wrap: wrap;
    align-items: center;
    gap: 12px;
    height: auto;
    padding: 10px 16px;
    border-right: none;
    border-bottom: 1px solid var(--app-border);
  }

  .brand-text {
    display: none;
  }

  .nav {
    flex-direction: row;
  }

  .user {
    flex-direction: row;
    align-items: center;
    margin: 0 0 0 auto;
    padding: 0;
    border-top: none;
  }

  .user-name {
    width: auto;
  }

  .content-inner {
    padding: 16px;
  }
}
</style>
