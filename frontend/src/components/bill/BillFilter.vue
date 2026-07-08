<template>
  <div class="card-box filter-box">
    <div class="filter-bar bill-filter-bar">
      <el-select v-model="localFilter.channel" placeholder="渠道" clearable size="default">
        <el-option label="微信" value="wechat" />
        <el-option label="支付宝" value="alipay" />
        <el-option label="建行" value="ccb" />
        <el-option label="手工记账" value="manual" />
      </el-select>

      <el-date-picker
        v-model="startDate"
        type="date"
        placeholder="开始日期"
        size="default"
        value-format="YYYY-MM-DD"
        style="width: 100%"
      />

      <el-date-picker
        v-model="endDate"
        type="date"
        placeholder="结束日期"
        size="default"
        value-format="YYYY-MM-DD"
        style="width: 100%"
      />

      <el-select v-model="localFilter.family_id" placeholder="家庭视角" clearable size="default">
        <el-option
          v-for="f in families"
          :key="f.id"
          :label="f.name"
          :value="f.id"
        />
      </el-select>

      <el-select v-model="localFilter.role_id" placeholder="角色" clearable size="default">
        <el-option
          v-for="r in roles"
          :key="r.id"
          :label="r.name"
          :value="r.id"
        />
      </el-select>

      <el-select v-model="localFilter.category_id" placeholder="分类" clearable size="default">
        <el-option
          v-for="c in categories"
          :key="c.id"
          :label="c.name"
          :value="c.id"
        />
      </el-select>

      <el-select v-model="localFilter.direction" placeholder="收支方向" clearable size="default">
        <el-option label="支出" value="expense" />
        <el-option label="收入" value="income" />
        <el-option label="中性" value="neutral" />
      </el-select>

      <el-select v-model="localFilter.trade_type" placeholder="交易类型" clearable size="default">
        <el-option
          v-for="option in tradeTypeSelectOptions"
          :key="option.value"
          :label="option.label"
          :value="option.value"
        />
      </el-select>

      <el-select v-model="localFilter.assign_status" placeholder="分配状态" clearable size="default">
        <el-option label="已分配" value="assigned" />
        <el-option label="待分配" value="pending" />
        <el-option label="未分配" value="unassigned" />
      </el-select>

      <el-select v-model="localFilter.merge_status" placeholder="溯源状态" clearable size="default">
        <el-option label="正常" value="normal" />
        <el-option label="待溯源" value="orphan" />
        <el-option label="已溯源（发起方）" value="merged_source" />
        <el-option label="已溯源（真实支付者）" value="merged_target" />
      </el-select>

      <el-input
        v-model="localFilter.keyword"
        placeholder="搜索交易对方/商品说明"
        clearable
        size="default"
      />

      <div class="filter-actions">
        <el-button type="primary" size="default" @click="handleSearch">
          <el-icon><Search /></el-icon>
          查询
        </el-button>
        <el-button size="default" @click="handleReset">重置</el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref, onMounted, watch } from 'vue'
import { Search } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useSystemStore } from '@/stores/system'
import { tradeTypeSelectOptions } from '@/utils/formatters'

const props = defineProps({
  filter: { type: Object, default: () => ({}) },
})

const emit = defineEmits(['search', 'reset'])

const systemStore = useSystemStore()

const localFilter = reactive(defaultFilter())

const startDate = ref(null)
const endDate = ref(null)
const families = ref([])
const roles = ref([])
const categories = ref([])

onMounted(async () => {
  await Promise.all([
    systemStore.loadFamilies(),
    systemStore.loadRoles(null),
    systemStore.loadCategories(),
  ])
  families.value = systemStore.families
  roles.value = systemStore.roles
  categories.value = systemStore.categories
})

watch(() => props.filter, (filter) => {
  syncFromFilter(filter || {})
}, { immediate: true, deep: true })

function defaultFilter() {
  return {
    channel: null,
    family_id: null,
    role_id: null,
    category_id: null,
    direction: null,
    trade_type: null,
    assign_status: null,
    merge_status: null,
    keyword: '',
    start_time: null,
    end_time: null,
  }
}

function syncFromFilter(filter) {
  Object.assign(localFilter, defaultFilter(), filter)
  startDate.value = datePart(filter.start_time)
  endDate.value = endDateFromFilter(filter.end_time)
}

function datePart(value) {
  return value ? String(value).slice(0, 10) : null
}

function endDateFromFilter(value) {
  if (!value) return null
  const text = String(value)
  const date = text.slice(0, 10)
  if (text.includes('T00:00:00')) {
    return addDays(date, -1)
  }
  return date
}

function addDays(dateText, days) {
  if (!dateText) return null
  const date = new Date(`${dateText}T00:00:00+08:00`)
  date.setDate(date.getDate() + days)
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function handleSearch() {
  if (startDate.value && endDate.value && startDate.value > endDate.value) {
    ElMessage.warning('开始日期不能晚于结束日期')
    return
  }

  localFilter.start_time = startDate.value ? `${startDate.value}T00:00:00+08:00` : null
  localFilter.end_time = endDate.value ? `${addDays(endDate.value, 1)}T00:00:00+08:00` : null

  const filter = {}
  for (const [k, v] of Object.entries(localFilter)) {
    if (v !== null && v !== '' && v !== undefined) {
      filter[k] = v
    }
  }
  emit('search', filter)
}

function handleReset() {
  Object.assign(localFilter, defaultFilter())
  startDate.value = null
  endDate.value = null
  emit('reset')
}
</script>

<style scoped>
.bill-filter-bar :deep(.el-date-editor.el-input) {
  width: 100%;
}
</style>
