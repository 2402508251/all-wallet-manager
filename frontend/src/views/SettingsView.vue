<template>
  <div class="page-container">
    <h2 class="page-title">系统设置</h2>

    <div class="card-box">
      <el-tabs v-model="activeTab" type="border-card">
        <el-tab-pane label="家庭管理" name="family">
          <FamilyManager />
        </el-tab-pane>
        <el-tab-pane label="角色管理" name="role">
          <RoleManager />
        </el-tab-pane>
        <el-tab-pane label="账户管理" name="account">
          <AccountManager />
        </el-tab-pane>
        <el-tab-pane label="分类管理" name="category">
          <CategoryManager />
        </el-tab-pane>
        <el-tab-pane label="邮箱配置" name="email">
          <EmailSetting />
        </el-tab-pane>
        <el-tab-pane label="分类关键词" name="keyword">
          <KeywordSetting />
        </el-tab-pane>
        <el-tab-pane label="数据管理" name="data">
          <DataManager />
        </el-tab-pane>
      </el-tabs>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import FamilyManager from '@/components/settings/FamilyManager.vue'
import RoleManager from '@/components/settings/RoleManager.vue'
import AccountManager from '@/components/settings/AccountManager.vue'
import CategoryManager from '@/components/settings/CategoryManager.vue'
import EmailSetting from '@/components/settings/EmailSetting.vue'
import KeywordSetting from '@/components/settings/KeywordSetting.vue'
import DataManager from '@/components/settings/DataManager.vue'

const activeTab = ref('family')
</script>
