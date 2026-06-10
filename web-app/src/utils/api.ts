export function extractErrorMessage(error: unknown, fallback: string): string {
  const axiosError = error as {
    code?: string
    message?: string
    response?: { data?: unknown }
  }
  const response = axiosError.response
  const data = response?.data as
    | { detail?: string | Array<{ msg?: string }> }
    | undefined

  if (!response) {
    if (axiosError.code === 'ECONNABORTED') {
      return '请求超时，请确认后端服务已启动'
    }
    if (axiosError.message?.includes('Network Error')) {
      return '无法连接到后端服务，请确认相关服务已启动'
    }
    return fallback
  }

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
