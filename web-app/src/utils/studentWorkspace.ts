export const COURSEWARE_STORAGE_KEY = 'student-workspace-courseware'
export const EXERCISE_STORAGE_KEY = 'student-workspace-exercise-set'
export const STUDENT_WORKSPACE_CONTEXT_KEY = 'student-workspace-context'

export type StudentWorkspaceContext = {
  userId: number
  subject: string
  topic: string
  goal?: string
  generatedAt: number
}

export function buildPracticeSessionStorageKey(userId: number) {
  return `student-practice-session-${userId}`
}

export function sameWorkspaceTopic(left: string | undefined, right: string | undefined) {
  return normalizeWorkspaceTopic(left) === normalizeWorkspaceTopic(right)
}

export function readStudentWorkspaceContext(userId: number): StudentWorkspaceContext | null {
  if (typeof window === 'undefined') {
    return null
  }

  try {
    const raw = window.sessionStorage.getItem(STUDENT_WORKSPACE_CONTEXT_KEY)
    if (!raw) {
      return null
    }
    const parsed = JSON.parse(raw) as Partial<StudentWorkspaceContext>
    if (
      parsed.userId !== userId
      || typeof parsed.topic !== 'string'
      || !parsed.topic.trim()
    ) {
      return null
    }
    return {
      userId,
      subject: typeof parsed.subject === 'string' ? parsed.subject.trim() : '',
      topic: parsed.topic.trim(),
      goal: typeof parsed.goal === 'string' ? parsed.goal : '',
      generatedAt: typeof parsed.generatedAt === 'number' ? parsed.generatedAt : Date.now(),
    }
  } catch {
    return null
  }
}

export function writeStudentWorkspaceContext(context: StudentWorkspaceContext) {
  if (typeof window === 'undefined') {
    return
  }

  window.sessionStorage.setItem(
    STUDENT_WORKSPACE_CONTEXT_KEY,
    JSON.stringify({
      ...context,
      subject: context.subject.trim(),
      topic: context.topic.trim(),
      goal: context.goal ?? '',
    }),
  )
}

export function clearStudentWorkspaceArtifacts(
  userId: number,
  options: {
    clearCourseware?: boolean
    clearExercises?: boolean
    clearPracticeSession?: boolean
    clearContext?: boolean
  } = {},
) {
  if (typeof window === 'undefined') {
    return
  }

  const {
    clearCourseware = true,
    clearExercises = true,
    clearPracticeSession = true,
    clearContext = false,
  } = options

  if (clearCourseware) {
    window.sessionStorage.removeItem(COURSEWARE_STORAGE_KEY)
  }
  if (clearExercises) {
    window.sessionStorage.removeItem(EXERCISE_STORAGE_KEY)
  }
  if (clearPracticeSession) {
    window.localStorage.removeItem(buildPracticeSessionStorageKey(userId))
  }
  if (clearContext) {
    window.sessionStorage.removeItem(STUDENT_WORKSPACE_CONTEXT_KEY)
  }
}

function normalizeWorkspaceTopic(value: string | undefined) {
  return (value ?? '').trim().replace(/\s+/g, ' ').toLowerCase()
}
