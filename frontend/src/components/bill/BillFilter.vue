<template>
  <div class="card-box filter-box">
    <div class="filter-bar">
      <el-select v-model="localFilter.channel" placeholder="渠道" clearable size="default">
        <el-option label="微信" value="wechat" />
        <el-option label="支付宝" value="alipay" />
        <el-option label="建行" value="ccb" />
      </el-select>

      <el-date-picker
        v-model="dateRange"
        type="daterange"
        range-separator="至"
        start-placeholder="开始日期"
        end-placeholder="结束日期"
        size="default"
        value-format="YYYY-MM-DD"
      />

      <el-select v-model="localFilter.family_id" placeholder="家庭" clearable size="default">
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
        <el-option label="消费" value="consumption" />
        <el-option label="信用消费" value="credit_consumption" />
        <el-option label="转出" value="transfer_out" />
        <el-option label="转入" value="transfer_in" />
        <el-option label="还款" value="repayment" />
        <el-option label="手续费" value="fee" />
        <el-option label="镜像" value="mirror" />
        <el-option label="退款" value="refund" />
      </el-select>

      <el-select v-model="localFilter.assign_status" placeholder="分配状态" clearable size="default">
        <el-option label="已分配" value="assigned" />
        <el-option label="待分配" value="pending" />
        <el-option label="未分配" value="unassigned" />
      </el-select>

      <el-select v-model="localFilter.merge_status" placeholder="合并状态" clearable size="default">
        <el-option label="正常" value="normal" />
        <el-option label="待合并（孤儿）" value="orphan" />
        <el-option label="已合并（发起方）" value="merged_source" />
        <el-option label="已合并（真实支付者）" value="merged_target" />
      </el-select>

      <el-input
        v-model="localFilter.keyword"
        placeholder="搜索交易对方/商品说明"
        clearable
        size="default"
      />

      <el-button type="primary" size="default" @click="handleSearch">
        <el-icon><Search /></el-icon>
        查询
      </el-button>
      <el-button size="default" @click="handleReset">重置</el-button>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref, watch, onMounted } from 'vue'
import { Search } from '@element-plus/icons-vue'
import { useSystemStore } from '@/stores/system'

const emit = defineEmits(['search', 'reset'])

const systemStore = useSystemStore()

const localFilter = reactive({
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
})

const dateRange = ref(null)

const families = ref([])
const roles = ref([])
const categories = ref([])

onMounted(async () => {
  await systemStore.loadFamilies()
  await systemStore.loadCategories()
  families.value = systemStore.families
  categories.value = systemStore.categories
})

watch(() => localFilter.family_id, async (val) => {
  if (val) {
    await systemStore.loadRoles(val)
    roles.value = systemStore.roles
    localFilter.role_id = null
  } else {
    roles.value = []
  }
})

watch(dateRange, (val) => {
  if (val && val.length === 2) {
    localFilter.start_time = val[0] + 'T00:00:00+08:00'
    localFilter.end_time = val[1] + 'T23:59:59+08:00'
  } else {
    localFilter.start_time = null
    localFilter.end_time = null
  }
})

function handleSearch() {
  const filter = {}
  for (const [k, v] of Object.entries(localFilter)) {
    if (v !== null && v !== '' && v !== undefined) {
      filter[k] = v
    }
  }
  emit('search', filter)
}

function handleReset() {
  Object.keys(localFilter).forEach(k => {
    localFilter[k] = k === 'keyword' ? '' : null
  })
  dateRange.value = null
  emit('reset')
}
</script>