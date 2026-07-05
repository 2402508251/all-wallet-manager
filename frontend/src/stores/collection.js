// stores/collection.js — 采集状态（采集记录/邮箱配置/上传/解析/进度任务）

import { defineStore } from 'pinia'
import { call, on, off } from '@/utils/bridge'

export const useCollectionStore = defineStore('collection', {
  state: () => ({
    collections: [],
    total: 0,
    page: 1,
    pageSize: 20,
    emailConfigs: [],
    activeTasks: {},
    loading: false,
  }),

  actions: {
    // ─── 采集记录 ─────────────────────────
    async loadCollections(page, pageSize) {
      if (page !== undefined) this.page = page
      if (pageSize !== undefined) this.pageSize = pageSize
      this.loading = true
      try {
        const data = await call('get_collection_list', {
          page: this.page,
          page_size: this.pageSize,
        })
        this.collections = data.list
        this.total = data.total
      } finally {
        this.loading = false
      }
    },

    async uploadFiles(files) {
      const data = await call('upload_files', { files })
      await this.loadCollections()
      return data
    },

    async parseCollection(recordId) {
      const data = await call('parse_collection', { record_id: recordId })
      await this.loadCollections()
      return data
    },

    async parseBatch(recordIds) {
      const data = await call('parse_batch', { record_ids: recordIds })
      await this.loadCollections()
      return data
    },

    async setChannelManual(recordId, channel) {
      await call('set_channel_manual', { record_id: recordId, channel })
      await this.loadCollections()
    },

    async setZipPassword(recordId, password) {
      await call('set_zip_password', { record_id: recordId, password })
      await this.loadCollections()
    },

    async deleteCollectionRecords(recordIds) {
      const data = await call('delete_collection_records', { record_ids: recordIds })
      await this.loadCollections()
      return data
    },

    async deleteBillsByCollections(recordIds) {
      const data = await call('delete_bills_by_collections', { record_ids: recordIds })
      await this.loadCollections()
      return data
    },

    // ─── 邮箱配置 ─────────────────────────
    async loadEmailConfigs() {
      const data = await call('get_email_configs', {})
      this.emailConfigs = data.list
    },

    async saveEmailConfig(config) {
      await call('save_email_config', config)
      await this.loadEmailConfigs()
    },

    async testEmailConnection(configId) {
      return await call('test_email_connection', { config_id: configId })
    },

    async fetchEmailBills(configId) {
      return await call('fetch_email_bills', { config_id: configId })
    },

    async deleteEmailConfig(configId) {
      await call('delete_email_config', { config_id: configId })
      await this.loadEmailConfigs()
    },

    // ─── 任务进度 ─────────────────────────
    updateTaskProgress(taskId, data) {
      this.activeTasks[taskId] = {
        taskId,
        step: data.step || '',
        message: data.message || '',
        percent: data.percent || 0,
      }
    },

    removeTask(taskId) {
      delete this.activeTasks[taskId]
    },

    // ─── 事件监听 ─────────────────────────
    startTaskListeners(taskId, onDone) {
      const progressHandler = (data) => {
        if (data.task_id === taskId) {
          this.updateTaskProgress(taskId, data)
        }
      }
      const doneHandler = (data) => {
        if (data.task_id === taskId) {
          this.removeTask(taskId)
          off('task_progress', progressHandler)
          off('task_done', doneHandler)
          this.loadCollections()
          if (onDone) onDone(data)
        }
      }
      on('task_progress', progressHandler)
      on('task_done', doneHandler)
    },
  },
})