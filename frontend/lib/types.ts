// Mirrors the backend response models (backend/app).

export type Mode = "standard" | "graph" | "hybrid"
export type DocumentStatus = "uploaded" | "processing" | "ingested" | "failed"

export interface DocumentRow {
  id: string
  filename: string
  content_type: string
  size_bytes: number
  status: DocumentStatus
  error: string | null
  pages: number | null
  chunk_count: number
  entity_count: number
  relation_count: number
  created_at: string
  updated_at: string
}

export interface Chunk {
  id: string
  document_id: string
  filename: string
  page: number | null
  chunk_index: number
  text: string
  char_start: number
  char_end: number
}

export interface ExtractionError {
  chunk_id: string | null
  message: string
  raw_response: string | null
  created_at: string
}

export interface Health {
  status: "ok" | "degraded"
  neo4j: "up" | "down"
  neo4j_error: string | null
  llm_configured: boolean
  llm_base_url: string
  models: { extraction: string; answer: string; query_entity: string }
  embedding_model: string
}

export interface Stats {
  documents: number
  chunks: number
  entities: number | null
  relations: number | null
  entities_by_type: Record<string, number>
}

export interface Activity {
  kind: string
  message: string
  created_at: string
}

export interface Entity {
  id: string
  name: string
  type: string
  aliases: string[]
  description: string
  degree: number
}

export interface Mention {
  chunk_id: string
  document_id: string
  filename: string
  page: number | null
}

export interface Relation {
  source: string
  target: string
  type: string
  chunk_ids: string[]
  document_ids: string[]
  evidence: string[]
  confidence: number
  key: string
}

export interface EntityDetail extends Entity {
  mentions: Mention[]
  relations: Relation[]
}

export interface GraphData {
  entities: Entity[]
  relations: Relation[]
}

export interface GraphStats {
  entities: number
  relations: number
  by_type: Record<string, number>
  relation_types: Record<string, number>
}

export interface PathStep {
  source_id: string
  source_name: string
  type: string
  target_id: string
  target_name: string
  forward: boolean
}

export interface GraphPath {
  steps: PathStep[]
  score: number
  chunk_ids: string[]
  rendered: string
}

export interface RetrievedChunk {
  chunk: Chunk
  score: number
  sources: Record<string, { rank: number; score: number }>
}

export interface SeedMatch {
  entity_id: string
  mention: string
  score: number
  method: string
}

export interface Usage {
  model: string
  prompt_tokens: number
  completion_tokens: number
  latency_ms: number
  cached: boolean
}

export interface Retrieval {
  mode: Mode
  chunks: RetrievedChunk[]
  paths: GraphPath[]
  seeds: SeedMatch[]
  route: string
  route_reason: string
  latency_ms: number
  usage: Usage[]
}

export interface Citation {
  id: string
  kind: "chunk" | "path"
  chunk_id: string | null
  document_id: string | null
  filename: string | null
  page: number | null
  path: string | null
  filenames: string[]
}

export interface Answer {
  answer: string
  explanation: string
  citations: Citation[]
  insufficient_evidence: boolean
  conflicts: string[]
  invalid_citations: string[]
  grounded: boolean
  usage: Usage | null
}

export interface QueryResponse {
  question: string
  mode: Mode
  answer: Answer
  retrieval: Retrieval
  timings: { retrieval_ms: number; generation_ms: number; total_ms: number }
  usage: {
    llm_calls: number
    cached_calls: number
    prompt_tokens: number
    completion_tokens: number
    estimated_cost_usd: number
  }
}

export interface ModeSummary {
  questions: number
  errors: number
  accuracy: number | null
  f1: number | null
  context_recall: number | null
  citation_precision: number | null
  citation_recall: number | null
  retrieval_ms_mean: number | null
  total_ms_mean: number | null
  total_ms_median: number
  prompt_tokens: number
  completion_tokens: number
  llm_calls: number
  cached_calls: number
  estimated_cost_usd: number
}

export interface EvalSummary {
  modes: Record<string, ModeSummary>
  by_category: Record<string, Record<string, number | null>>
  error?: string
}

export interface EvalRun {
  id: string
  created_at: string
  status: "running" | "completed" | "failed"
  config: {
    modes: Mode[]
    models: Record<string, string>
    retrieval: Record<string, number>
    corpus_mismatch: boolean
    indexed_document_ids: string[]
    benchmark_document_ids: string[]
  }
  summary: EvalSummary | null
  progress?: { status: string; done: number; total: number | null; error: string | null } | null
}

export interface EvalRecord {
  question_id: string
  category: string
  question: string
  mode: Mode
  reference_answer: string
  required_documents: string[]
  answer: string
  explanation: string
  insufficient_evidence: boolean
  grounded: boolean
  conflicts: string[]
  invalid_citations: string[]
  citations: { id: string; kind: string; filenames: string[]; path: string | null }[]
  cited_documents: string[]
  retrieved_chunks: {
    chunk_id: string
    filename: string
    page: number | null
    score: number
    sources: Record<string, { rank: number; score: number }>
    text: string
  }[]
  paths: { rendered: string; score: number }[]
  seeds: { entity_id: string; method: string; score: number }[]
  route: string
  route_reason: string
  retrieval_ms: number
  total_ms: number
  usage: QueryResponse["usage"]
  error: string | null
  metrics: {
    correct: boolean
    f1: number
    context_recall: number | null
    citation_precision: number | null
    citation_recall: number | null
  }
}
