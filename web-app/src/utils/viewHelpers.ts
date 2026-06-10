/** Pure utility functions shared across sub-views — NO fallback data. */

import { contentApi, type ApiEnvelope, type ExerciseGenerationResponse } from '../api'

export type EnvelopeLike<T> = T | ApiEnvelope<T>

export function unwrapApiData<T>(payload: EnvelopeLike<T>): T {
  if (payload && typeof payload === 'object' && 'data' in payload && 'code' in payload) {
    return (payload as ApiEnvelope<T>).data as T
  }
  return payload as T
}

export async function postContentWithTimeout<T>(url: string, payload: unknown, timeoutMs: number): Promise<{ data: T }> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    return await contentApi.post<T>(url, payload, { signal: controller.signal, timeout: timeoutMs })
  } finally {
    clearTimeout(timer)
  }
}

export function normalizeExerciseResponse(payload: EnvelopeLike<ExerciseGenerationResponse> | null | undefined): ExerciseGenerationResponse | null {
  if (!payload) return null
  const result = unwrapApiData(payload)
  if (!result || typeof result !== 'object' || !('exercises' in result) || !Array.isArray(result.exercises)) return null
  if (result.exercises.length === 0) return null
  return result
}
