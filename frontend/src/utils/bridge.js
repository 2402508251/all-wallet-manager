// utils/bridge.js — PyWebView API 调用封装

// PyWebView API 是否就绪检测
export function isReady() {
  return !!window.pywebview?.api
}

// 等待 PyWebView API 就绪（Vue app mount 前调用）
export function ready() {
  return new Promise((resolve) => {
    if (window.pywebview?.api) return resolve()
    window.addEventListener('pywebviewready', () => resolve())
  })
}

// 通用 API 调用封装（统一错误处理 + 返回值解包）
// PyWebView 传参机制：api.method(params) → Python method(self, params)
// 前端 call('method', { key1: val1, key2: val2 }) → api.method({ key1: val1, key2: val2 })
// Python 端方法统一接收 params 字典，从中提取参数
export async function call(method, params = {}) {
  const api = window.pywebview?.api
  if (!api || !api[method]) {
    throw new Error(`API 方法不可用: ${method}`)
  }
  const result = await api[method](params)
  if (result.success === false) {
    throw new Error(result.message || '操作失败')
  }
  return result.data
}

// 事件监听封装
export function on(eventName, handler) {
  window.addEventListener(eventName, (event) => handler(event.detail))
}

export function off(eventName, handler) {
  window.removeEventListener(eventName, handler)
}

// 便捷方法：监听任务进度
export function onTaskProgress(taskId, onProgress, onDone) {
  const progressHandler = (data) => {
    if (data.task_id === taskId) onProgress(data)
  }
  const doneHandler = (data) => {
    if (data.task_id === taskId) {
      off('task_progress', progressHandler)
      off('task_done', doneHandler)
      onDone(data)
    }
  }
  return () => {
    off('task_progress', progressHandler)
    off('task_done', doneHandler)
  }
}