"use client"

import { useCallback, useEffect, useRef, useState } from "react"

import { ApiError } from "./api"

/** Load data on mount, optionally re-polling while `pollMs` is a number. */
export function useApi<T>(load: () => Promise<T>, pollMs?: number | null) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [loading, setLoading] = useState(true)
  const loadRef = useRef(load)
  loadRef.current = load

  const refresh = useCallback(async () => {
    try {
      setData(await loadRef.current())
      setError(null)
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError(0, "unknown", String(e)))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  useEffect(() => {
    if (!pollMs) return
    const t = setInterval(refresh, pollMs)
    return () => clearInterval(t)
  }, [pollMs, refresh])

  return { data, error, loading, refresh, setData }
}
