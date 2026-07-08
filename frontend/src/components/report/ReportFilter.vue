<template>
  <div class="card-box filter-box">
    <div class="report-filter-top">
      <el-radio-group
        :model-value="filter.period"
        size="default"
        @update:model-value="emit('update:filter', { period: $event })"
      >
        <el-radio-button label="month">月度</el-radio-button>
        <el-radio-button label="year">年度</el-radio-button>
        <el-radio-button label="recent12">近12个月</el-radio-button>
        <el-radio-button label="custom">自定义</el-radio-button>
      </el-radio-group>

      <el-switch
        :model-value="hideRepayment"
        active-text="隐藏内部还款转账"
        size="default"
        @update:model-value="$emit('toggle-repayment', $event)"
      />
    </div>

    <div class="filter-bar report-filter-bar">
      <el-date-picker
        v-if="filter.period === 'year'"
        :model-value="String(filter.year)"
        type="year"
        placeholder="选择年份"
        size="default"
        value-format="YYYY"
        @update:model-value="handleYearChange"
      />

      <el-date-picker
        v-else-if="filter.period !== 'custom'"
        :model-value="`${filter.year}-${String(filter.month).padStart(2, '0')}`"
        type="month"
        placeholder="选择月份"
        size="default"
        value-format="YYYY-MM"
        @update:model-value="handleMonthChange"
      />

      <el-date-picker
        v-else
        :model-value="customRange"
        type="daterange"
        unlink-panels
        range-separator="至"
        start-placeholder="开始日期"
        end-placeholder="结束日期"
        size="default"
        value-format="YYYY-MM-DD"
        @update:model-value="handleRangeChange"
      />

      <el-select
        :model-value="filter.family_id"
        placeholder="家庭视角"
        clearable
        size="default"
        @update:model-value="handleFamilyChange"
      >
        <el-option
          v-for="f in families"
          :key="f.id"
          :label="f.name"
          :value="f.id"
        />
      </el-select>

      <el-select
        :model-value="filter.role_id"
        placeholder="角色视角"
        clearable
        size="default"
        @update:model-value="handleRoleChange"
      >
        <el-option
          v-for="r in roles"
          :key="r.id"
          :label="r.name"
          :value="r.id"
        />
      </el-select>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  filter: { type: Object, required: true },
  hideRepayment: { type: Boolean, default: false },
  families: { type: Array, default: () => [] },
  roles: { type: Array, default: () => [] },
})

const emit = defineEmits(['update:filter', 'toggle-repayment'])
const customRange = computed(() => [props.filter.start_date, props.filter.end_date])

function handleMonthChange(value) {
  if (!value) return
  const [year, month] = value.split('-')
  emit('update:filter', { year: Number(year), month: Number(month) })
}

function handleYearChange(value) {
  if (!value) return
  emit('update:filter', { year: Number(value) })
}

function handleRangeChange(value) {
  if (!value || value.length !== 2) return
  emit('update:filter', { start_date: value[0], end_date: value[1] })
}

function handleFamilyChange(value) {
  emit('update:filter', { family_id: value || null, role_id: null })
}

function handleRoleChange(value) {
  emit('update:filter', { role_id: value || null })
}
</script>

<style scoped>
.report-filter-top {
  display: flex;
  justify-content: space-between;
  gap: var(--spacing-md);
  align-items: center;
  margin-bottom: var(--spacing-md);
  flex-wrap: wrap;
}

.report-filter-bar {
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
}
</style>
