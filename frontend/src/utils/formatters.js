export const channelOptions = {
  wechat: { label: '微信', tag: 'success' },
  alipay: { label: '支付宝', tag: 'primary' },
  ccb: { label: '建行', tag: 'warning' },
  manual: { label: '手工记账', tag: 'info' },
  self_export: { label: '自导出格式', tag: 'primary' },
  unknown: { label: '未知', tag: 'info' },
}

export const directionOptions = {
  income: { label: '收入', className: 'amount-income' },
  expense: { label: '支出', className: 'amount-expense' },
  neutral: { label: '中性', className: 'amount-neutral' },
}

export const tradeTypeOptions = {
  consumption: { label: '消费', tag: 'info' },
  credit_consumption: { label: '信用消费', tag: 'warning' },
  refund: { label: '退款', tag: 'success' },
  transfer_out: { label: '转出', tag: '' },
  transfer_in: { label: '转入', tag: 'success' },
  repayment: { label: '还款', tag: 'info' },
  repayment_mirror: { label: '还款镜像', tag: 'info' },
  fee: { label: '手续费', tag: 'danger' },
  topup: { label: '充值', tag: 'primary' },
  withdrawal: { label: '提现', tag: 'warning' },
  investment: { label: '理财', tag: 'success' },
  other_income: { label: '其他收入', tag: 'success' },
  other_expense: { label: '其他支出', tag: 'warning' },
  other: { label: '其他', tag: 'info' },
}

export const tradeTypeSelectOptions = Object.entries(tradeTypeOptions).map(([value, meta]) => ({
  value,
  label: meta.label,
}))

export const creditTypeOptions = {
  huabei: '花呗',
  baitiao: '白条',
  fenfu: '分付',
  ccb_credit: '建行信用卡',
}

export const collectionStatusOptions = {
  pending: { label: '待解析', tag: 'info' },
  parsing: { label: '解析中', tag: 'warning' },
  parsed: { label: '已解析', tag: 'success' },
  error: { label: '失败', tag: 'danger' },
}

export function formatYuan(cents = 0, options = {}) {
  const value = Number(cents || 0) / 100
  const text = value.toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
  return options.withSymbol === false ? text : `¥${text}`
}

export function formatSignedYuan(cents = 0, direction) {
  const prefix = direction === 'income' ? '+' : direction === 'expense' ? '-' : ''
  return `${prefix}${formatYuan(cents)}`
}

export function formatDateTime(value) {
  if (!value) return ''
  return String(value).slice(0, 16).replace('T', ' ')
}

export function channelLabel(channel) {
  return channelOptions[channel]?.label || channel || '-'
}

export function channelTag(channel) {
  return channelOptions[channel]?.tag || 'info'
}

export function directionLabel(direction) {
  return directionOptions[direction]?.label || direction || '-'
}

export function directionClass(direction) {
  return directionOptions[direction]?.className || ''
}

export function tradeTypeLabel(type) {
  return tradeTypeOptions[type]?.label || type || '-'
}

export function tradeTypeTag(type) {
  return tradeTypeOptions[type]?.tag || 'info'
}

export function creditTypeLabel(type) {
  return creditTypeOptions[type] || type || '-'
}

export function collectionStatusLabel(status) {
  return collectionStatusOptions[status]?.label || status || '-'
}

export function collectionStatusTag(status) {
  return collectionStatusOptions[status]?.tag || 'info'
}

export function currentMonthParts() {
  const now = new Date()
  return {
    year: now.getFullYear(),
    month: now.getMonth() + 1,
  }
}

export function monthDateRange(year, month) {
  const start = `${year}-${String(month).padStart(2, '0')}-01T00:00:00+08:00`
  const nextMonth = month === 12 ? 1 : month + 1
  const nextYear = month === 12 ? year + 1 : year
  const end = `${nextYear}-${String(nextMonth).padStart(2, '0')}-01T00:00:00+08:00`
  return { start_time: start, end_time: end }
}
