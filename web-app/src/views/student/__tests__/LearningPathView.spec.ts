import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../../api', () => ({
  agentApi: { post: vi.fn(), get: vi.fn() },
  resourceApi: { get: vi.fn() },
  teacherApi: { get: vi.fn() },
  evaluationApi: { get: vi.fn(), post: vi.fn() },
}))

vi.mock('../../../stores/auth', () => ({
  useAuthStore: () => ({ user: { userId: 1, username: 'learner' } }),
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: {}, params: {} }),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}))

vi.mock('../../../utils/studentWorkspace', () => ({
  clearStudentWorkspaceArtifacts: vi.fn(),
  COURSEWARE_STORAGE_KEY: 'courseware',
  EXERCISE_STORAGE_KEY: 'exercise',
  sameWorkspaceTopic: () => false,
  writeStudentWorkspaceContext: vi.fn(),
}))

import { agentApi, evaluationApi, resourceApi, teacherApi } from '../../../api'
import { resetPathGeneration } from '../../../stores/pathGeneration'

import LearningPathView from '../LearningPathView.vue'

const agentPost = vi.mocked(agentApi.post)
const agentGet = vi.mocked(agentApi.get)
const resourceGet = vi.mocked(resourceApi.get)
const teacherGet = vi.mocked(teacherApi.get)
const evaluationGet = vi.mocked(evaluationApi.get)

function pathPayload(overrides: Record<string, unknown> = {}) {
  return {
    id: 11,
    user_id: 1,
    subject: '数据结构',
    knowledge_point: '栈',
    stages: [],
    knowledge_scope: 'public',
    knowledge_versions: [],
    ...overrides,
  }
}

async function mountView() {
  const wrapper = mount(LearningPathView, {
    global: {
      plugins: [ElementPlus],
      // Real Element Plus rendering so the alert states are asserted for real;
      // only the sibling student panels are stubbed out.
      stubs: {
        LearningAtmosphere: true,
        PlanAdaptationPanel: true,
        PlanFeedbackPanel: true,
        TaskFeedbackButton: true,
      },
    },
  })
  await wrapper.vm.$nextTick()
  return wrapper
}

type Wrapper = Awaited<ReturnType<typeof mountView>>

it('历史生成按需读取详情，查看时不提交生成请求', async () => {
  const scroll = vi.spyOn(window, 'scrollTo').mockImplementation(() => {})
  agentGet.mockImplementation(async (url: string) => {
    if (url === '/paths/history/1') return { data: { items: [{ id: 21, subject: '历史数学', knowledge_point: '方程', stage_count: 1, task_count: 0 }] } }
    if (url === '/paths/history/item/21') return { data: pathPayload({ subject: '历史数学', knowledge_point: '方程', stages: [{ stage_id: 's1', title: '基础', tasks: [] }] }) }
    return { data: { subjects: [] } }
  })
  const wrapper = await mountView()
  await flush()
  expect(wrapper.find('.history-item').text()).toContain('历史数学')
  expect(agentGet.mock.calls.some(([url]) => url === '/paths/history/item/21')).toBe(false)
  await wrapper.find('.history-path-open').trigger('click')
  await flush()
  expect(agentGet).toHaveBeenCalledWith('/paths/history/item/21')
  expect((wrapper.find('input[aria-label="输入学科"]').element as HTMLInputElement).value).toBe('历史数学')
  expect(agentPost).not.toHaveBeenCalled()
  wrapper.unmount()
  scroll.mockRestore()
})

it('历史记录带课件时直接读取已保存课件，不重新生成', async () => {
  const scroll = vi.spyOn(window, 'scrollTo').mockImplementation(() => {})
  agentGet.mockImplementation(async (url: string) => {
    if (url === '/paths/history/1') {
      return {
        data: {
          items: [
            {
              id: 21,
              subject: '计算机组成原理',
              knowledge_point: '存储系统',
              stage_count: 1,
              task_count: 1,
              courseware_resource_id: 237,
              courseware_title: '存储系统个性化课件',
              courseware_created_at: '2026-10-22T12:56:45',
            },
          ],
        },
      }
    }
    if (url === '/paths/history/item/21') {
      return {
        data: pathPayload({
          subject: '计算机组成原理',
          knowledge_point: '存储系统',
          stages: [{ stage_id: 's1', title: '基础', tasks: [] }],
        }),
      }
    }
    return { data: { subjects: [] } }
  })
  resourceGet.mockResolvedValue({
    data: { data: { id: 237, title: '存储系统个性化课件', content: '# 存储系统\n\n历史课件正文' } },
  })

  const wrapper = await mountView()
  await flush()
  const openButton = wrapper.find('.history-courseware-open')
  expect(openButton.text()).toContain('查看历史课件')

  await wrapper.find('.history-item').trigger('click')
  await flush(2)
  await wrapper.vm.$nextTick()

  expect(resourceGet).toHaveBeenCalledWith('/resources/237')
  expect(agentGet.mock.calls.some(([url]) => url === '/paths/history/item/21')).toBe(false)
  expect(agentPost).not.toHaveBeenCalled()
  expect(document.body.textContent).toContain('历史课件正文')

  wrapper.unmount()
  scroll.mockRestore()
})

async function fillForm(wrapper: Wrapper) {
  await wrapper.find('input[aria-label="输入学科"]').setValue('数据结构')
  await wrapper.find('input[placeholder="知识点 / 主题"]').setValue('栈')
}

// Scoped to the path form: the success state adds a workspace button that would
// otherwise be found first.
function generateButton(wrapper: Wrapper) {
  return wrapper.find('.path-form button')
}

function readyPreflight() {
  return Promise.resolve({ data: { ready: true, message: '知识库已就绪', reason: 'READY' } })
}

function readyCoordination(response: { data: unknown }) {
  agentGet.mockImplementation(async (url: string) => {
    if (url === '/agents/coordinate/tasks/101') return { data: { status: 'SUCCEEDED', result: response.data } }
    if (url.startsWith('/paths/history/')) return { data: { items: [] } }
    return { data: { subjects: [] } }
  })
  return Promise.resolve({ data: { task_id: 101 } })
}

async function flush(times = 8) {
  await new Promise((resolve) => setTimeout(resolve, 1600))
  // The generate flow chains several awaits (preflight, coordinate, persistence).
  for (let index = 0; index < times; index += 1) {
    await new Promise((resolve) => setTimeout(resolve, 0))
  }
}

beforeEach(() => {
  // The generation module is a singleton that outlives a component on purpose.
  resetPathGeneration()
  window.sessionStorage.clear()
  agentPost.mockReset()
  agentGet.mockReset()
  resourceGet.mockReset()
  teacherGet.mockReset()
  evaluationGet.mockReset()
  agentGet.mockResolvedValue({ data: { subjects: [] } })
  resourceGet.mockResolvedValue({ data: { data: null } })
  teacherGet.mockResolvedValue({ data: { data: [] } })
  evaluationGet.mockResolvedValue({ data: { data: [] } })
})

describe('LearningPathView 自动入库结果展示', () => {
  it('请求进行中按钮进入加载态并禁用', async () => {
    // Coordination never settles, so the busy state can be observed directly.
    agentPost.mockImplementation((url: string) =>
      url === '/paths/preflight' ? readyPreflight() : new Promise(() => {}),
    )

    const wrapper = await mountView()
    await fillForm(wrapper)
    void generateButton(wrapper).trigger('click')
    await flush(5)
    await wrapper.vm.$nextTick()

    const button = generateButton(wrapper)
    expect(button.text()).toBe('正在生成...')
    expect(button.attributes('disabled')).toBeDefined()
  })

  it('入库成功时展示公共知识成功态，不出现草稿提示', async () => {
    agentPost.mockImplementation((url: string) =>
      url === '/paths/preflight'
        ? readyPreflight()
        : readyCoordination({
            data: {
              outputs: {
                path_planning_agent: {
                  learning_path: pathPayload({
                    knowledge_scope: 'public',
                    knowledge_versions: [{ id: 1, version: 1 }],
                  }),
                },
              },
            },
          }),
    )

    const wrapper = await mountView()
    await fillForm(wrapper)
    await generateButton(wrapper).trigger('click')
    await flush()
    await wrapper.vm.$nextTick()

    const text = wrapper.text()
    expect(text).toContain('本次基于公共知识库资料生成（已引用 1 个已发布知识版本）')
    expect(text).not.toContain('临时学习草稿')
    expect(wrapper.find('.knowledge-draft').exists()).toBe(false)
    // The busy state is cleared once the request settles.
    expect(generateButton(wrapper).text()).toBe('生成学习路径')
    expect(generateButton(wrapper).attributes('disabled')).toBeUndefined()
  })

  it('入库失败时展示历史草稿态并给出具体未入库原因', async () => {
    agentPost.mockImplementation((url: string) =>
      url === '/paths/preflight'
        ? readyPreflight()
        : readyCoordination({
            data: {
              outputs: {
                path_planning_agent: {
                  learning_path: pathPayload({
                    knowledge_scope: 'personal_draft',
                    knowledge_backfill_reason: 'LOCK_BUSY',
                    knowledge_draft: {
                      description: '自动构建的临时草稿',
                      chapters: [{ name: '第一章', points: [{ name: '栈' }] }],
                    },
                  }),
                },
              },
            },
          }),
    )

    const wrapper = await mountView()
    await fillForm(wrapper)
    await generateButton(wrapper).trigger('click')
    await flush()
    await wrapper.vm.$nextTick()

    const text = wrapper.text()
    // The draft is presented as history to be re-integrated, never as a final state.
    expect(text).toContain('历史个人草稿：不是公共知识。请重新生成，经模型审核入公共知识库后使用。')
    expect(text).toContain('未入库原因：知识库正在被其他写入占用，已跳过本次入库')
    expect(text).not.toContain('本次基于公共知识库资料生成')
    expect(text).not.toContain('正在使用已发布版本')
  })

  it('未知入库失败原因使用兜底文案而不是空白', async () => {
    agentPost.mockImplementation((url: string) =>
      url === '/paths/preflight'
        ? readyPreflight()
        : readyCoordination({
            data: {
              outputs: {
                path_planning_agent: {
                  learning_path: pathPayload({
                    knowledge_scope: 'personal_draft',
                    knowledge_backfill_reason: 'SOMETHING_NEW',
                  }),
                },
              },
            },
          }),
    )

    const wrapper = await mountView()
    await fillForm(wrapper)
    await generateButton(wrapper).trigger('click')
    await flush()
    await wrapper.vm.$nextTick()

    expect(wrapper.text()).toContain(
      '未入库原因：历史记录尚未进入公共知识，请重新生成以自动完成融入',
    )
  })
})
