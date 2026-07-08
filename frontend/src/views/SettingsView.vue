<template>
  <div class="page-container">
    <section class="page-hero">
      <div>
        <div class="page-kicker">Settings</div>
        <h2 class="page-title">系统设置</h2>
        <p class="page-subtitle">维护家庭、角色、账户、分类规则、邮箱配置和高影响数据操作。</p>
      </div>
    </section>

    <div class="settings-layout">
      <aside class="settings-nav card-box">
        <button
          v-for="item in settingItems"
          :key="item.name"
          type="button"
          class="settings-nav-item"
          :class="{ 'is-active': activeTab === item.name }"
          @click="activeTab = item.name"
        >
          <strong>{{ item.label }}</strong>
          <span>{{ item.desc }}</span>
        </button>
      </aside>

      <div class="card-box settings-panel">
      <el-tabs v-model="activeTab" class="hidden-tabs">
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
        <el-tab-pane label="分类规则" name="keyword">
          <KeywordSetting />
        </el-tab-pane>
        <el-tab-pane label="数据管理" name="data">
          <DataManager />
        </el-tab-pane>
      </el-tabs>
      </div>
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
const settingItems = [
  { name: 'family', label: '家庭管理', desc: '报表统计与归属维度' },
  { name: 'role', label: '角色管理', desc: '成员、主体与家庭关系' },
  { name: 'account', label: '账户管理', desc: '账户归属、别名和合并' },
  { name: 'category', label: '分类管理', desc: '业务分类基础资料' },
  { name: 'email', label: '邮箱配置', desc: 'IMAP 同步与授权维护' },
  { name: 'keyword', label: '分类规则', desc: '关键词与匹配字段' },
  { name: 'data', label: '数据管理', desc: '重解析、快照和清理' },
]
</script>

<style scoped>
.settings-layout {
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr);
  gap: var(--spacing-md);
  align-items: start;
}

.settings-nav {
  display: grid;
  gap: var(--spacing-xs);
  position: sticky;
  top: var(--spacing-md);
}

.settings-nav-item {
  display: grid;
  gap: 2px;
  width: 100%;
  border: 1px solid transparent;
  border-radius: var(--radius-lg);
  padding: var(--spacing-sm);
  background: transparent;
  color: var(--color-text-regular);
  cursor: pointer;
  text-align: left;
}

.settings-nav-item strong {
  color: var(--color-text-primary);
}

.settings-nav-item span {
  color: var(--color-text-secondary);
  font-size: var(--font-size-small);
}

.settings-nav-item:hover,
.settings-nav-item.is-active {
  border-color: var(--color-primary);
  background: var(--color-primary-soft);
}

.settings-panel {
  min-width: 0;
}

.hidden-tabs :deep(.el-tabs__header) {
  display: none;
}

@media (max-width: 1200px) {
  .settings-layout {
    grid-template-columns: 1fr;
  }

  .settings-nav {
    position: static;
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
