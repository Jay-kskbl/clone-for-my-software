<script setup lang="ts">
import { useRouter } from 'vue-router'

import { auth, logout } from './auth'

const router = useRouter()

function onLogout() {
  logout()
  void router.push({ name: 'login' })
}
</script>

<template>
  <el-container class="app">
    <el-header class="app-header">
      <span class="app-left">
        <span class="app-title">智能文档管理系统</span>
        <nav v-if="auth.user" class="app-nav">
          <router-link :to="{ name: 'documents' }" class="app-nav-link">文件</router-link>
          <router-link :to="{ name: 'search' }" class="app-nav-link">检索</router-link>
        </nav>
      </span>
      <span v-if="auth.user" class="app-user">
        {{ auth.user.username }}
        <el-tag v-if="auth.user.role === 'admin'" size="small" type="warning">管理员</el-tag>
        <el-button link type="primary" @click="onLogout">退出登录</el-button>
      </span>
    </el-header>
    <el-main>
      <router-view />
    </el-main>
  </el-container>
</template>

<style>
body {
  margin: 0;
  background: #f5f7fa;
}

.app {
  min-height: 100vh;
}

.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #fff;
  border-bottom: 1px solid #e4e7ed;
}

.app-title {
  font-size: 18px;
  font-weight: 600;
}

.app-left {
  display: flex;
  align-items: center;
  gap: 24px;
}

.app-nav {
  display: flex;
  gap: 16px;
}

.app-nav-link {
  color: #606266;
  text-decoration: none;
}

.app-nav-link.router-link-exact-active {
  color: #409eff;
  font-weight: 600;
}

.app-user {
  display: flex;
  align-items: center;
  gap: 8px;
}
</style>
