import { useState, useEffect } from 'react'
import { fetchJson } from '../api'

export function useApi<T>(path: string | null): {
  data: T | null
  loading: boolean
  error: string | null
} {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (path === null) {
      setData(null)
      setLoading(false)
      setError(null)
      return
    }
    const controller = new AbortController()
    let cancelled = false
    setLoading(true)
    setError(null)
    fetchJson<T>(path, { signal: controller.signal })
      .then((result) => { if (!cancelled) setData(result) })
      .catch((err) => {
        if (!cancelled && err instanceof Error && err.name !== 'AbortError') setError(err.message)
        if (!cancelled && !(err instanceof Error)) setError(String(err))
      })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => {
      cancelled = true
      controller.abort()
    }
  }, [path])

  return { data, loading, error }
}
