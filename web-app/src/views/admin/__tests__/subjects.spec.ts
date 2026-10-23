import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { reactive, ref } from 'vue'

const { get } = vi.hoisted(() => ({ get: vi.fn() }))

vi.mock('../../../api/http', () => ({ agentApi: { get: (...args: unknown[]) => get(...args), post: vi.fn() } }))
vi.mock('../../../composables/useAdminWorkspace', () => ({
  useAdminWorkspace: () => ({
    subjects: ref([{ id: 2, name: '数据结构', description: '线性表、树、图' }]),
    loading: reactive({ subjects: false }),
    fetchSubjects: vi.fn(),
  }),
}))

import Subjects from '../subjects.vue'

const overview = {
  items: [
    {
      id: 2,
      name: '数据结构',
      code: 'data_structures',
      total_points: 2,
      covered_points: 1,
      published_points: 2,
      document_count: 2,
      unlinked_documents: 0,
      coverage: 0.5,
    },
  ],
}

const coverage = {
  subject_id: 2,
  subject_name: '数据结构',
  code: 'data_structures',
  total_points: 2,
  covered_points: 1,
  missing_points: [{ id: 12, name: '队列' }],
  unlinked_documents: [],
  coverage: 0.5,
  points: [
    {
      id: 11,
      name: '顺序表',
      chapter: '第1章 绪论',
      difficulty: 1,
      importance: 2,
      construction_status: 'PUBLISHED',
      objectives: [],
      prerequisites: [],
      covered: true,
      documents: [{ id: 'a1', title: '顺序表 · 线性表', status: 'PUBLISHED', index_status: 'INDEXED', usable: true }],
    },
    {
      id: 12,
      name: '队列',
      chapter: '第1章 绪论',
      difficulty: 1,
      importance: 1,
      construction_status: 'PLANNED',
      objectives: [],
      prerequisites: [],
      covered: false,
      documents: [],
    },
  ],
}

beforeEach(() => {
  get.mockReset()
  get.mockImplementation((url: string) => {
    if (url.includes('/subjects/overview')) return Promise.resolve({ data: overview })
    if (url.includes('/coverage')) return Promise.resolve({ data: coverage })
    return Promise.resolve({ data: {} })
  })
})

describe('学科管理：每个学科的知识点可见', () => {
  it('卡片上显示知识点与覆盖数量，不必点开也能看出建设情况', async () => {
    const wrapper = mount(Subjects)
    await flushPromises()
    const text = wrapper.text()
    expect(text).toContain('数据结构')
    expect(text).toContain('2 知识点')
    expect(text).toContain('1 有可用资料')
    expect(text).toContain('查看知识点（2）')
  })

  it('点开学科后按章节列出知识点、覆盖状态与关联资料', async () => {
    const wrapper = mount(Subjects)
    await flushPromises()
    expect(wrapper.text()).not.toContain('顺序表')

    const toggle = wrapper.findAll('el-button').find(button => button.text().includes('查看知识点'))!
    await toggle.trigger('click')
    await flushPromises()

    const text = wrapper.text()
    expect(text).toContain('第1章 绪论')
    expect(text).toContain('顺序表')
    expect(text).toContain('队列')
    expect(text).toContain('资料就绪')
    expect(text).toContain('缺资料')
    expect(text).toContain('顺序表 · 线性表')
    expect(text).toContain('尚未关联任何资料')
    expect(text).toContain('缺资料 1 个')
  })
})
