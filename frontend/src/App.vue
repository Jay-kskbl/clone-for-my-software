<script setup lang="ts">
// 页面骨架（T24s）：登录后左侧是导航栏，右侧是内容区（最宽 1200px，居中）；
// 登录页不显示导航栏。窄屏（≤768px）时导航栏收成页面顶部的一行。
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { auth, logout } from './auth'
import AppIcon from './components/AppIcon.vue'
import LocaleSwitch from './features/theme/LocaleSwitch.vue'
import ThemePicker from './features/theme/ThemePicker.vue'
import { m } from './i18n'

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
        <span class="brand-text">{{ m().app.title }}</span>
      </div>
      <nav class="nav">
        <router-link :to="{ name: 'documents' }" class="nav-item" :class="{ active: activeNav === 'documents' }">
          <AppIcon name="folder" />
          {{ m().app.nav.documents }}
        </router-link>
        <router-link :to="{ name: 'search' }" class="nav-item" :class="{ active: activeNav === 'search' }">
          <AppIcon name="search" />
          {{ m().app.nav.search }}
        </router-link>
      </nav>
      <div class="user">
        <div class="user-name">
          <span class="avatar">{{ initial }}</span>
          <span class="user-text" :title="auth.user?.username">{{ auth.user?.username }}</span>
          <el-tag v-if="auth.user?.role === 'admin'" size="small" type="warning">{{ m().app.admin }}</el-tag>
        </div>
        <el-button link class="logout" @click="onLogout">
          <AppIcon name="logout" :size="16" />
          {{ m().app.logout }}
        </el-button>
      </div>
    </aside>
    <main class="content">
      <div class="content-inner">
        <!-- key：从一个文件直接跳到另一个文件（浏览器后退两步）时重新创建预览页，否则地址变了、内容还是上一个文件（T24bb） -->
        <router-view :key="route.path" />
      </div>
    </main>
  </div>
  <router-view v-else :key="route.path" />
  <!-- 右下角：语言切换 + 系统配色面板（T24bc），所有页面都有 -->
  <div class="floating-tools">
    <LocaleSwitch />
    <ThemePicker />
  </div>
</template>

<style scoped>
.floating-tools {
  position: fixed;
  right: 20px;
  bottom: 20px;
  z-index: 2000;
  display: flex;
  align-items: flex-end;
  gap: 10px;
}

@media (max-width: 600px) {
  .floating-tools {
    right: 12px;
    bottom: 12px;
  }
}

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
  /* 底部留出右下角浮动按钮的高度（44 px + 离底边 20 px），滚到底时分页按钮一定在它上方 */
  padding: 24px 32px 76px;
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
    padding: 16px 16px 76px;
  }
}
</style>
