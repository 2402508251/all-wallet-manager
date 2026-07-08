<template>
  <div class="page-container dashboard-page">
    <section class="page-hero">
      <div>
        <div class="page-kicker">Dashboard</div>
        <h2 class="page-title">{{ dashboardStore.currentMonth }} 财务概览</h2>
        <p class="page-subtitle">
          汇总当月收支、分类结构、近期交易和需要处理的数据问题。
        </p>
      </div>
      <div class="dashboard-filters">
        <el-select
          v-model="familyId"
          placeholder="家庭视角"
          clearable
          @change="handleFamilyChange"
        >
          <el-option v-for="f in systemStore.families" :key="f.id" :label="f.name" :value="f.id" />
        </el-select>
        <el-select
          v-model="roleId"
          placeholder="角色视角"
          clearable
          @change="handleRoleChange"
        >
          <el-option v-for="r in systemStore.roles" :key="r.id" :label="r.name" :value="r.id" />
        </el-select>
      </div>
    </section>

    <div v-loading="dashboardStore.loading" class="dashboard-content">
      <section class="metric-grid">
        <div class="metric-card expense">
          <div class="metric-label">当月支出</div>
          <div class="metric-value amount-expense">{{ formatYuan(summary.expense) }}</div>
          <div class="metric-hint">不含信用消费</div>
        </div>
        <div class="metric-card income">
          <div class="metric-label">当月收入</div>
          <div class="metric-value amount-income">{{ formatYuan(summary.income) }}</div>
          <div class="metric-hint">已排除逻辑删除账单</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">当月结余</div>
          <div class="metric-value" :class="balanceClass">{{ formatYuan(balance) }}</div>
          <div class="metric-hint">收入 - 支出</div>
        </div>
        <div class="metric-card credit">
          <div class="metric-label">信用消费 / 还款</div>
          <div class="metric-value">{{ formatYuan(summary.credit) }}</div>
          <div class="metric-hint">还款 {{ formatYuan(summary.repayment) }}</div>
        </div>
      </section>

      <section class="dashboard-grid">
        <div class="dashboard-main">
          <TrendLineChart :data="dashboardStore.trendData" />
          <div class="chart-row">
            <CategoryPieChart
              :data="dashboardStore.categoryDistribution"
              @slice-click="goCategory"
            />
            <div class="card-box recent-card">
              <div class="action-bar">
                <div>
                  <div class="section-title">近期交易</div>
                  <div class="section-subtitle">按交易时间倒序展示最近 6 条</div>
                </div>
                <el-button link type="primary" @click="goBills">查看全部</el-button>
              </div>
              <el-table :data="dashboardStore.recentBills" size="small" empty-text="暂无交易记录">
                <el-table-column prop="trade_time" label="时间" width="128">
                  <template #default="{ row }">{{ formatDateTime(row.trade_time) }}</template>
                </el-table-column>
                <el-table-column label="渠道" width="72">
                  <template #default="{ row }">
                    <el-tag size="small" :type="channelTag(row.channel)">
                      {{ channelLabel(row.channel) }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column prop="product_desc" label="说明" min-width="140" show-overflow-tooltip />
                <el-table-column label="金额" width="108" align="right">
                  <template #default="{ row }">
                    <span :class="directionClass(row.direction)">
                      {{ formatSignedYuan(row.amount_cents, row.direction) }}
                    </span>
                  </template>
                </el-table-column>
              </el-table>
            </div>
          </div>
        </div>

        <aside class="dashboard-side">
          <div class="card-box todo-card">
            <div class="section-title">待处理事项</div>
            <div class="section-subtitle">来自现有采集、账单与账务接口</div>
            <button
              v-for="item in dashboardStore.todoItems"
              :key="item.key"
              type="button"
              class="todo-item"
              @click="goTodo(item)"
            >
              <span class="todo-dot" :class="item.level"></span>
              <span>{{ item.label }}</span>
              <strong>{{ item.count === null ? '待接口' : item.count }}</strong>
            </button>
          </div>

          <div class="card-box collection-card">
            <div class="action-bar">
              <div>
                <div class="section-title">采集状态</div>
                <div class="section-subtitle">最近 8 条采集记录</div>
              </div>
              <el-button link type="primary" @click="router.push('/collection')">处理</el-button>
            </div>
            <div class="collection-list">
              <div
                v-for="record in dashboardStore.collectionRecords"
                :key="record.id"
                class="collection-row"
              >
                <div class="collection-name">{{ record.file_name }}</div>
                <el-tag size="small" :type="collectionStatusTag(record.status)">
                  {{ collectionStatusLabel(record.status) }}
                </el-tag>
              </div>
              <div v-if="dashboardStore.collectionRecords.length === 0" class="empty-block">
                暂无采集记录
              </div>
            </div>
          </div>
        </aside>
      </section>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useDashboardStore } from '@/stores/dashboard'
import { useSystemStore } from '@/stores/system'
import CategoryPieChart from '@/components/report/CategoryPieChart.vue'
import TrendLineChart from '@/components/report/TrendLineChart.vue'
import {
  channelLabel,
  channelTag,
  collectionStatusLabel,
  collectionStatusTag,
  directionClass,
  formatDateTime,
  formatSignedYuan,
  formatYuan,
} from '@/utils/formatters'

const router = useRouter()
const dashboardStore = useDashboardStore()
const systemStore = useSystemStore()
const familyId = ref(null)
const roleId = ref(null)

const summary = computed(() => dashboardStore.monthlySummary || {})
const balance = computed(() => (summary.value.income || 0) - (summary.value.expense || 0))
const balanceClass = computed(() => balance.value >= 0 ? 'amount-income' : 'amount-expense')

onMounted(async () => {
  await Promise.all([
    systemStore.loadFamilies(),
    systemStore.loadRoles(null),
    systemStore.loadCategories(),
    dashboardStore.loadDashboard(),
  ])
})

async function handleFamilyChange(value) {
  familyId.value = value || null
  roleId.value = null
  await systemStore.loadRoles(familyId.value)
  dashboardStore.setFilter({ family_id: familyId.value, role_id: null })
}

function handleRoleChange(value) {
  roleId.value = value || null
  dashboardStore.setFilter({ role_id: roleId.value })
}

function currentBillQuery(extra = {}) {
  const range = monthDateRange(dashboardStore.filter.year, dashboardStore.filter.month)
  const query = { ...range, ...extra }
  if (dashboardStore.filter.family_id) query.family_id = dashboardStore.filter.family_id
  if (dashboardStore.filter.role_id) query.role_id = dashboardStore.filter.role_id
  return query
}

function goBills() {
  router.push({ path: '/bills', query: currentBillQuery() })
}

function goCategory(categoryName) {
  const cat = systemStore.categories.find(c => c.name === categoryName)
  router.push({
    path: '/bills',
    query: currentBillQuery({
      category_id: cat?.id || '',
      direction: 'expense',
    }),
  })
}

function goTodo(item) {
  router.push({ path: item.path, query: item.query || {} })
}
</script>

<style scoped>
.dashboard-page {
  padding-bottom: var(--spacing-lg);
}

.dashboard-filters {
  display: flex;
  gap: var(--spacing-sm);
  min-width: 360px;
}

.dashboard-filters .el-select {
  width: 180px;
}

.dashboard-content {
  min-height: 520px;
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: var(--spacing-md);
  margin-bottom: var(--spacing-md);
}

.metric-card {
  min-height: 132px;
  padding: var(--spacing-lg);
  border: 1px solid var(--border-color-lighter);
  border-radius: var(--radius-lg);
  background: var(--bg-card);
  box-shadow: var(--shadow-card);
}

.metric-card.expense {
  background: linear-gradient(180deg, #fff, var(--color-danger-soft));
}

.metric-card.income {
  background: linear-gradient(180deg, #fff, var(--color-success-soft));
}

.metric-card.credit {
  background: linear-gradient(180deg, #fff, var(--color-warning-soft));
}

.metric-label {
  color: var(--color-text-secondary);
  font-weight: 700;
  margin-bottom: var(--spacing-sm);
}

.metric-hint {
  color: var(--color-text-secondary);
  font-size: var(--font-size-small);
  margin-top: var(--spacing-sm);
}

.dashboard-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 340px;
  gap: var(--spacing-md);
}

.dashboard-main,
.dashboard-side {
  min-width: 0;
}

.recent-card {
  min-width: 0;
}

.todo-card,
.collection-card {
  margin-bottom: var(--spacing-md);
}

.todo-item {
  width: 100%;
  height: 46px;
  display: grid;
  grid-template-columns: 10px 1fr auto;
  align-items: center;
  gap: var(--spacing-sm);
  margin-top: var(--spacing-sm);
  border: 1px solid var(--border-color-lighter);
  border-radius: var(--radius-lg);
  padding: 0 var(--spacing-sm);
  background: var(--bg-card-subtle);
  cursor: pointer;
  color: var(--color-text-regular);
  text-align: left;
}

.todo-item:hover {
  border-color: var(--color-primary);
  background: var(--color-primary-soft);
}

.todo-dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: var(--color-info);
}

.todo-dot.warning { background: var(--color-warning); }
.todo-dot.danger { background: var(--color-danger); }
.todo-dot.primary { background: var(--color-primary); }

.collection-list {
  display: grid;
  gap: var(--spacing-xs);
}

.collection-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm);
  border-radius: var(--radius-base);
  background: var(--bg-card-subtle);
}

.collection-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--color-text-regular);
  font-size: var(--font-size-small);
}

@media (max-width: 1280px) {
  .metric-grid,
  .dashboard-grid {
    grid-template-columns: 1fr 1fr;
  }

  .dashboard-side {
    grid-column: 1 / -1;
  }
}
</style>
