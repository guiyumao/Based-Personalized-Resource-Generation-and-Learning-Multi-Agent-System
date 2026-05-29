export function extractErrorMessage(error: unknown, fallback: string): string {
  const response = (error as { response?: { data?: unknown } })?.response
  const data = response?.data as
    | { detail?: string | Array<{ msg?: string }> }
    | undefined

  if (!data) {
    return fallback
  }

  if (typeof data.detail === 'string' && data.detail.trim()) {
    return data.detail
  }

  if (Array.isArray(data.detail) && data.detail.length > 0) {
    const messages = data.detail
      .map((item) => item?.msg?.trim())
      .filter((item): item is string => Boolean(item))

    if (messages.length > 0) {
      return messages.join('；')
    }
  }

  return fallback
}
