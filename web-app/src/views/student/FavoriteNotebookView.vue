<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { evaluationApi, type ApiEnvelope, type ExerciseFavoriteItem, type ExerciseFavoriteNotebook } from '../../api'
import LearningContent from '../../components/LearningContent.vue'
import { useAuthStore } from '../../stores/auth'

const authStore = useAuthStore()
const notebook = ref<ExerciseFavoriteNotebook>({ user_id: authStore.user?.userId ?? 0, favorite_count: 0, items: [] })
const loading = ref(true)
const removingId = ref<number | null>(null)
const revealedIds = ref<Set<number>>(new Set())

function unwrap<T>(data: T | ApiEnvelope<T>): T {
  return ((data as ApiEnvelope<T>)?.data ?? data) as T
}

async function loadFavorites() {
  loading.value = true
  try {
    const { data } = await evaluationApi.get<ApiEnvelope<ExerciseFavoriteNotebook>>('/evaluation/practice/favorites')
    notebook.value = unwrap(data)
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail ?? '收藏本加载失败，请稍后重试')
  } finally {
    loading.value = false
  }
}

async function removeFavorite(item: ExerciseFavoriteItem) {
  if (removingId.value === item.exercise_id) return
  removingId.value = item.exercise_id
  try {
    await evaluationApi.delete(`/evaluation/practice/favorites/${item.exercise_id}`)
    notebook.value = {
      ...notebook.value,
      favorite_count: Math.max(0, notebook.value.favorite_count - 1),
      items: notebook.value.items.filter((favorite) => favorite.exercise_id !== item.exercise_id),
    }
    ElMessage.success('已从收藏本移除')
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail ?? '移除失败，请稍后重试')
  } finally {
    removingId.value = null
  }
}

function toggleAnswer(exerciseId: number) {
  const next = new Set(revealedIds.value)
  if (next.has(exerciseId)) next.delete(exerciseId)
  else next.add(exerciseId)
  revealedIds.value = next
}

function formatDate(value: string) {
  if (!value) return '刚刚收藏'
  return new Intl.DateTimeFormat('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(new Date(value))
}

onMounted(() => { void loadFavorites() })
</script>

<template>
  <div class="favorite-page">
    <header class="favorite-hero">
      <div>
        <p class="eyebrow">STUDY COLLECTION</p>
        <h2>收藏本</h2>
        <p class="hero-copy">把值得回看的题目收在一起，随时复习重点与解题思路。</p>
      </div>
      <div class="hero-count">
        <strong>{{ notebook.favorite_count }}</strong>
        <span>道已收藏</span>
      </div>
    </header>

    <div v-if="loading" class="state-card">正在加载你的收藏题目…</div>
    <div v-else-if="!notebook.items.length" class="state-card empty-card">
      <div class="empty-icon">☆</div>
      <strong>还没有收藏题目</strong>
      <p>在练习测评中点击“收藏题目”，它们会出现在这里。</p>
    </div>
    <section v-else class="favorite-list" aria-label="收藏题目列表">
      <article v-for="(item, index) in notebook.items" :key="item.id" class="favorite-card">
        <div class="card-topline">
          <span class="index-badge">{{ String(index + 1).padStart(2, '0') }}</span>
          <div class="tag-list">
            <span>{{ item.question_type }}</span>
            <span>{{ item.difficulty }}</span>
            <span v-if="item.knowledge_point">{{ item.knowledge_point }}</span>
          </div>
          <time>{{ formatDate(item.created_at) }}</time>
        </div>
        <LearningContent class="favorite-prompt" :content="item.prompt" empty="(无题干内容)" />
        <div v-if="item.options.length" class="option-list">
          <div v-for="option in item.options" :key="option" class="option-item"><LearningContent :content="option" inline /></div>
        </div>
        <div class="card-actions">
          <button type="button" class="answer-button" @click="toggleAnswer(item.exercise_id)">
            {{ revealedIds.has(item.exercise_id) ? '收起解析' : '查看答案与解析' }}
          </button>
          <button type="button" class="remove-button" :disabled="removingId === item.exercise_id" @click="removeFavorite(item)">
            {{ removingId === item.exercise_id ? '移除中…' : '取消收藏' }}
          </button>
        </div>
        <div v-if="revealedIds.has(item.exercise_id)" class="answer-panel">
          <div><strong>参考答案</strong><LearningContent class="answer-text" :content="item.answer" empty="暂无答案" /></div>
          <div><strong>题目解析</strong><LearningContent class="answer-text" :content="item.analysis" empty="暂无解析" /></div>
        </div>
      </article>
    </section>
  </div>
</template>

<style scoped>
.favorite-page { display:grid; gap:20px; max-width:1120px; }
.favorite-hero { display:flex; justify-content:space-between; align-items:center; gap:24px; padding:28px 32px; border:1px solid var(--line); border-radius:22px; background:linear-gradient(135deg, color-mix(in srgb,var(--accent) 10%,var(--panel)), var(--panel)); box-shadow:0 18px 42px var(--shadow-soft); }
.eyebrow { margin:0 0 8px; color:var(--accent); font-size:11px; font-weight:800; letter-spacing:.16em; }
h2 { margin:0; color:var(--text); font-size:30px; letter-spacing:-.04em; }
.hero-copy { margin:10px 0 0; color:var(--muted); font-size:14px; }
.hero-count { min-width:120px; padding:14px 20px; text-align:center; border:1px solid color-mix(in srgb,var(--accent) 22%,var(--line)); border-radius:18px; background:color-mix(in srgb,var(--panel) 84%,transparent); }
.hero-count strong { display:block; color:var(--accent); font-size:32px; line-height:1; }
.hero-count span { display:block; margin-top:8px; color:var(--muted); font-size:12px; }
.favorite-list { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:16px; }
.favorite-card,.state-card { border:1px solid var(--line); border-radius:20px; background:var(--panel); box-shadow:0 12px 32px var(--shadow-soft); }
.favorite-card { padding:22px; transition:transform .2s ease,box-shadow .2s ease,border-color .2s ease; }
.favorite-card:hover { transform:translateY(-2px); border-color:color-mix(in srgb,var(--accent) 34%,var(--line)); box-shadow:0 18px 38px var(--shadow); }
.card-topline { display:flex; align-items:center; gap:10px; min-width:0; }
.index-badge { display:grid; place-items:center; width:34px; height:34px; flex:0 0 auto; border-radius:11px; color:var(--accent); background:var(--accent-soft); font-weight:800; font-size:12px; }
.tag-list { display:flex; flex-wrap:wrap; gap:6px; min-width:0; }
.tag-list span { padding:4px 8px; border-radius:999px; color:var(--muted); background:var(--surface-soft); font-size:11px; }
time { margin-left:auto; color:var(--muted); font-size:11px; white-space:nowrap; }
h3, .favorite-prompt { margin:18px 0 14px; color:var(--text); font-size:17px; line-height:1.7; }
.option-list { display:grid; gap:8px; }
.option-item { padding:10px 12px; border:1px solid var(--line); border-radius:11px; color:var(--text); background:var(--bg); font-size:13px; }
.card-actions { display:flex; align-items:center; gap:10px; margin-top:18px; }
.answer-button,.remove-button { border:1px solid var(--line); border-radius:10px; padding:8px 12px; font:600 12px inherit; cursor:pointer; }
.answer-button { color:var(--accent); background:var(--accent-soft); border-color:color-mix(in srgb,var(--accent) 22%,var(--line)); }
.remove-button { margin-left:auto; color:var(--muted); background:var(--bg); }
.remove-button:hover { color:var(--red); border-color:color-mix(in srgb,var(--red) 42%,var(--line)); }
.answer-panel { display:grid; gap:10px; margin-top:16px; padding:14px; border-radius:14px; background:var(--surface-soft); }
.answer-panel strong { color:var(--text); font-size:12px; }
.answer-panel p, .answer-panel .answer-text { margin:5px 0 0; color:var(--muted); font-size:13px; line-height:1.65; }
.state-card { padding:64px 24px; text-align:center; color:var(--muted); }
.empty-card strong { display:block; margin-top:12px; color:var(--text); font-size:17px; }
.empty-card p { margin:8px 0 0; font-size:13px; }
.empty-icon { color:var(--accent); font-size:42px; line-height:1; }
@media (max-width:900px) { .favorite-list { grid-template-columns:1fr; } }
@media (max-width:600px) { .favorite-hero { align-items:flex-start; flex-direction:column; padding:22px; } .hero-count { width:100%; } time { display:none; } }
</style>
