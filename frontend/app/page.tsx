"use client"

import Link from "next/link"

import { ErrorNote, PageHeader } from "@/components/app-shell"
import { api } from "@/lib/api"
import { useApi } from "@/lib/use-api"

const STEPS = [
  { href: "/documents", title: "Upload documents", body: "Add the three files in data/demo, or your own PDF, TXT or Markdown files." },
  { href: "/graph", title: "Inspect the graph", body: "See the entities and relationships extracted from each document, with sources." },
  { href: "/ask", title: "Ask across documents", body: "Ask a multi-hop question and compare Standard RAG, GraphRAG and Hybrid side by side." },
  { href: "/evaluation", title: "Run the benchmark", body: "Score all three modes on 22 questions and inspect where each one fails." },
]

function Figure({ label, value }: { label: string; value: number | null | undefined }) {
  return (
    <div className="border-l-2 border-border pl-4">
      <div className="text-3xl font-semibold tabular-nums tracking-tight">{value ?? "–"}</div>
      <div className="mt-0.5 text-sm text-muted-foreground">{label}</div>
    </div>
  )
}

export default function Overview() {
  const stats = useApi(api.stats, 10000)
  const activity = useApi(() => api.activity(12), 10000)
  const health = useApi(api.health)

  return (
    <div className="max-w-5xl">
      <PageHeader
        title="Overview"
        description="Loom answers questions by following relationships between entities across documents, and measures that against plain vector search on the same corpus."
      />

      {stats.error && <ErrorNote message={stats.error.message} />}
      <section aria-label="Index size" className="grid grid-cols-2 gap-6 sm:grid-cols-4">
        <Figure label="Documents" value={stats.data?.documents} />
        <Figure label="Chunks embedded" value={stats.data?.chunks} />
        <Figure label="Entities" value={stats.data?.entities} />
        <Figure label="Relationships" value={stats.data?.relations} />
      </section>
      {stats.data && stats.data.entities === null && (
        <p className="mt-3 text-sm text-muted-foreground">Graph counts are unavailable while Neo4j is not reachable.</p>
      )}

      <div className="mt-12 grid gap-10 lg:grid-cols-[1.1fr_1fr]">
        <section>
          <h2 className="mb-4 text-base font-semibold">Demo walkthrough</h2>
          <ol className="space-y-1">
            {STEPS.map((s, i) => (
              <li key={s.href}>
                <Link href={s.href} className="group flex gap-4 rounded-md p-3 transition-colors hover:bg-muted">
                  <span className="flex size-7 shrink-0 items-center justify-center rounded-full border text-sm tabular-nums text-muted-foreground group-hover:border-primary group-hover:text-primary">
                    {i + 1}
                  </span>
                  <span>
                    <span className="block font-medium">{s.title}</span>
                    <span className="block text-sm text-muted-foreground">{s.body}</span>
                  </span>
                </Link>
              </li>
            ))}
          </ol>

          {health.data && (
            <dl className="mt-8 grid grid-cols-[auto_1fr] gap-x-6 gap-y-1.5 text-sm">
              <dt className="text-muted-foreground">Extraction model</dt>
              <dd>{health.data.models.extraction}</dd>
              <dt className="text-muted-foreground">Answer model</dt>
              <dd>{health.data.models.answer}</dd>
              <dt className="text-muted-foreground">Embeddings</dt>
              <dd>{health.data.embedding_model}</dd>
              <dt className="text-muted-foreground">Provider</dt>
              <dd className="break-all">{health.data.llm_base_url}</dd>
            </dl>
          )}
          {health.data && !health.data.llm_configured && (
            <p className="mt-4 text-sm text-destructive">
              LLM_API_KEY is not set. Add it to .env and restart the backend to ingest documents and ask questions.
            </p>
          )}
          {health.data?.neo4j === "down" && (
            <p className="mt-2 text-sm text-destructive">Neo4j is not reachable. Start it with docker compose up -d neo4j.</p>
          )}
        </section>

        <section>
          <h2 className="mb-4 text-base font-semibold">Recent activity</h2>
          {activity.data?.length === 0 && (
            <p className="text-sm text-muted-foreground">Nothing yet. Upload a document to start.</p>
          )}
          <ul className="divide-y text-sm">
            {activity.data?.map((a, i) => (
              <li key={i} className="flex gap-3 py-2.5">
                <span className="w-20 shrink-0 capitalize text-muted-foreground">{a.kind}</span>
                <span className="min-w-0 flex-1 break-words">{a.message}</span>
                <time className="shrink-0 text-xs tabular-nums text-muted-foreground" dateTime={a.created_at}>
                  {new Date(a.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                </time>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  )
}
