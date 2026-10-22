<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { teacherApi, type ApiEnvelope, type HomeworkFileItem } from '../api'
const props = withDefaults(defineProps<{ files?: HomeworkFileItem[]; editable?: boolean; assignmentId?: number }>(), { files: () => [], editable: false })
const emit = defineEmits<{ 'update:files': [files: HomeworkFileItem[]]; busy: [value: boolean] }>()
const uploading = ref(false), uploadName = ref(''), viewing = ref(false), previewBusy = ref(false)
const previewUrl = ref(''), previewText = ref(''), previewFile = ref<HomeworkFileItem | null>(null)
const accept = '.jpg,.jpeg,.png,.gif,.webp,.bmp,.heic,.heif,.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.md,.csv,.zip'
function message(error: any, fallback: string) { return typeof error?.response?.data?.detail === 'string' ? error.response.data.detail : fallback }
function size(bytes: number) { return bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB` }
function canPreview(file: HomeworkFileItem) { return /^(image\/(jpeg|png|gif|webp|bmp)|application\/pdf)$/.test(file.content_type) || /\.(docx|txt|md|csv)$/i.test(file.file_name) }
function release() { if (previewUrl.value) URL.revokeObjectURL(previewUrl.value); previewUrl.value = ''; previewText.value = '' }
onBeforeUnmount(release)
async function upload(event: Event) {
  const input = event.target as HTMLInputElement
  const selected = [...(input.files || [])]; input.value = ''
  if (!selected.length || uploading.value || !props.assignmentId) return
  uploading.value = true; emit('busy', true)
  const files = [...props.files]
  try {
    for (const file of selected) {
      if (files.length >= 10) { ElMessage.warning('每次作业最多10个附件'); break }
      if (file.size > 20 * 1024 * 1024) { ElMessage.error(`${file.name} 超过20MB`); continue }
      if (files.reduce((sum, f) => sum + f.size_bytes, 0) + file.size > 100 * 1024 * 1024) { ElMessage.warning('附件总大小不能超过100MB'); break }
      uploadName.value = file.name
      const body = new FormData(); body.append('file', file)
      try {
        const { data } = await teacherApi.post<ApiEnvelope<HomeworkFileItem>>(`/teacher/students/me/homework/${props.assignmentId}/attachments`, body)
        if (!files.some(f => f.id === data.data.id)) files.push(data.data)
        emit('update:files', [...files])
      } catch (error) { ElMessage.error(message(error, `${file.name} 上传失败，请重试`)) }
    }
  } finally { uploading.value = false; uploadName.value = ''; emit('busy', false) }
}
async function remove(file: HomeworkFileItem) {
  if (file.is_pending) {
    try { await teacherApi.delete(`/teacher/students/me/homework/attachments/${file.id}`) }
    catch (error) { ElMessage.error(message(error, '附件移除失败')); return }
  }
  emit('update:files', props.files.filter(f => f.id !== file.id))
}
async function download(file: HomeworkFileItem) {
  try {
    const { data } = await teacherApi.get(`/teacher/homework/attachments/${file.id}`, { responseType: 'blob' })
    const url = URL.createObjectURL(new Blob([data], { type: file.content_type }))
    const link = document.createElement('a'); link.href = url; link.download = file.file_name; document.body.append(link); link.click(); link.remove()
    setTimeout(() => URL.revokeObjectURL(url), 60_000)
  } catch (error) { ElMessage.error(message(error, '文件下载失败，请确认当前账号有权查看')) }
}
async function preview(file: HomeworkFileItem) {
  release(); previewFile.value = file; viewing.value = true; previewBusy.value = true
  try {
    if (/\.(docx|txt|md|csv)$/i.test(file.file_name)) {
      const { data } = await teacherApi.get<{ text: string; truncated: boolean }>(`/teacher/homework/attachments/${file.id}/preview`)
      previewText.value = data.text + (data.truncated ? '\n（内容较长，请下载原文件查看全部）' : '')
    } else {
      const { data } = await teacherApi.get(`/teacher/homework/attachments/${file.id}`, { responseType: 'blob' })
      previewUrl.value = URL.createObjectURL(new Blob([data], { type: file.content_type }))
    }
  } catch (error) { viewing.value = false; ElMessage.error(message(error, '预览失败，请下载原文件查看')) }
  finally { previewBusy.value = false }
}
</script>
<template>
  <div class="homework-attachments">
    <label v-if="editable" class="file-picker">选择照片或文档
      <input type="file" multiple :accept="accept" :disabled="uploading" aria-label="选择作业附件" @change="upload" />
    </label>
    <small v-if="editable">支持照片、Word、PDF、Excel、PPT、文本及ZIP；单个≤20MB，最多10个，总计≤100MB。文字和附件至少提交一项。</small>
    <p v-if="uploading" role="status">正在上传：{{ uploadName }}</p>
    <div v-for="file in files" :key="file.id" class="homework-file" data-testid="homework-file">
      <span><strong>{{ file.file_name }}</strong><small>{{ size(file.size_bytes) }}</small></span>
      <div><el-button v-if="canPreview(file)" size="small" @click="preview(file)">预览</el-button><el-button size="small" @click="download(file)">下载</el-button><el-button v-if="editable" size="small" :disabled="uploading" @click="remove(file)">移除</el-button></div>
    </div>
    <el-dialog v-model="viewing" :title="previewFile?.file_name || '作业附件'" width="min(960px, 94vw)" append-to-body @closed="release">
      <div v-loading="previewBusy" class="homework-preview">
        <img v-if="previewUrl && previewFile?.content_type.startsWith('image/')" :src="previewUrl" :alt="previewFile.file_name" />
        <iframe v-else-if="previewUrl" :src="previewUrl" title="PDF作业附件预览" />
        <pre v-else>{{ previewText }}</pre>
      </div>
      <p v-if="previewText">文本预览不保留原始版式，完整排版及文档内图片请下载查看。</p>
      <template #footer><el-button v-if="previewFile" @click="download(previewFile)">下载原文件</el-button><el-button @click="viewing = false">关闭预览</el-button></template>
    </el-dialog>
  </div>
</template>
<style scoped>
.homework-attachments{display:grid;gap:10px;min-width:0}.file-picker{display:grid;gap:8px;border:1px dashed var(--accent);padding:12px;border-radius:10px;color:var(--accent)}.file-picker input{max-width:100%}.homework-attachments small{color:var(--muted);line-height:1.6}.homework-file{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;border:1px solid var(--line);padding:12px;border-radius:10px;background:var(--panel)}.homework-file>span{display:grid;gap:4px;min-width:0;overflow-wrap:anywhere}.homework-preview{min-height:100px}.homework-preview img{max-width:100%;max-height:70vh;display:block;margin:auto}.homework-preview iframe{width:100%;height:65vh;border:0}.homework-preview pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:65vh;overflow:auto;line-height:1.8;color:var(--text)}
</style>
