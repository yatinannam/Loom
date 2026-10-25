import type {
  Activity,
  Chunk,
  DocumentRow,
  EntityDetail,
  Entity,
  EvalRecord,
  EvalRun,
  ExtractionError,
  GraphData,
  GraphStats,
  Health,
  Mode,
  QueryResponse,
  Stats,
} from "./types"

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message)
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${API_URL}${path}`, init)
  } catch {
    throw new ApiError(0, "network_error", `Cannot reach the API at ${API_URL}. Start the backend and retry.`)
  }
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new ApiError(res.status, body?.error?.code ?? "http_error", body?.error?.message ?? res.statusText)
  }
  return res.status === 204 ? (undefined as T) : res.json()
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
})

export const api = {
  health: () => request<Health>("/api/health"),
  stats: () => request<Stats>("/api/stats"),
  activity: (limit = 15) => request<Activity[]>(`/api/activity?limit=${limit}`),

  documents: () => request<DocumentRow[]>("/api/documents"),
  upload: (files: File[]) => {
    const form = new FormData()
    files.forEach((f) => form.append("files", f))
    return request<DocumentRow[]>("/api/documents/upload", { method: "POST", body: form })
  },
  deleteDocument: (id: string) => request<void>(`/api/documents/${id}`, { method: "DELETE" }),
  reingest: (id: string) => request<DocumentRow>(`/api/documents/${id}/ingest`, { method: "POST" }),
  chunks: (id: string) => request<Chunk[]>(`/api/documents/${id}/chunks`),
  errors: (id: string) => request<ExtractionError[]>(`/api/documents/${id}/errors`),

  graphStats: () => request<GraphStats>("/api/graph/stats"),
  subgraph: (limit = 200) => request<GraphData>(`/api/graph/subgraph?limit=${limit}`),
  searchEntities: (q: string) => request<Entity[]>(`/api/graph/search?q=${encodeURIComponent(q)}`),
  entity: (id: string) => request<EntityDetail>(`/api/graph/entities/${encodeURIComponent(id)}`),
  neighbors: (id: string, hops = 1) =>
    request<GraphData>(`/api/graph/entities/${encodeURIComponent(id)}/neighbors?hops=${hops}`),

  query: (question: string, mode: Mode) => request<QueryResponse>("/api/query", json({ question, mode })),

  loadCorpus: () => request<{ document_ids: string[] }>("/api/evaluation/load-corpus", { method: "POST" }),
  runEvaluation: (modes: Mode[]) => request<EvalRun>("/api/evaluation/run", json({ modes })),
  evalRuns: () => request<EvalRun[]>("/api/evaluation/runs"),
  evalRun: (id: string) => request<EvalRun>(`/api/evaluation/runs/${id}`),
  evalResults: (id: string) => request<EvalRecord[]>(`/api/evaluation/runs/${id}/results`),
  exportUrl: (id: string, format: "csv" | "json") => `${API_URL}/api/evaluation/runs/${id}/export?format=${format}`,
}
