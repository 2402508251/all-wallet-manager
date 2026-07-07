<template>
  <div class="card-box filter-box">
    <div class="filter-bar">
      <el-date-picker
        :model-value="`${filter.year}-${String(filter.month).padStart(2, '0')}`"
        type="month"
        placeholder="选择月份"
        size="default"
        value-format="YYYY-MM"
        @update:model-value="handleMonthChange"
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
        placeholder="角色"
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

      <el-switch
        :model-value="hideRepayment"
        active-text="隐藏内部还款转账"
        size="default"
        @update:model-value="$emit('toggle-repayment', $event)"
      />
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useSystemStore } from '@/stores/system'

const props = defineProps({
  filter: { type: Object, required: true },
  hideRepayment: { type: Boolean, default: false },
  families: { type: Array, default: () => [] },
  roles: { type: Array, default: () => [] },
})

const emit = defineEmits(['update:filter', 'toggle-repayment'])

const systemStore = useSystemStore()

function handleMonthChange(value) {
  if (value) {
    const [year, month] = value.split('-')
    emit('update:filter', { year: Number(year), month: Number(month) })
  }
}

function handleFamilyChange(value) {
  emit('update:filter', { family_id: value })
}

function handleRoleChange(value) {
  emit('update:filter', { role_id: value })
}
</script>
