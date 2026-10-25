"use client"

import { AlertTriangle, ChevronDown, Loader2 } from "lucide-react"
import { AnimatePresence, motion } from "motion/react"
import { useState } from "react"

import { PathThread } from "@/components/path-thread"
import { modeInfo, ms } from "@/lib/modes"
import type { Mode, QueryResponse } from "@/lib/types"
import { cn } from "@/lib/utils"

function Flag({ children, tone = "muted" }: { children: React.ReactNode; tone?: "muted" | "warn" }) {
  return (
    <span className={cn("inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs", tone === "warn" ? "bg-destructive/10 text-destructive" : "bg-muted text-muted-foreground")}>
      {tone === "warn" && <AlertTriangle className="size-3" aria-hidden />}
      {children}
    </span>
  )
}

function Disclosure({ title, children, defaultOpen = false }: { title: string; children: React.ReactNode; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <section className="border-t pt-3">
      <button onClick={() => setOpen(!open)} aria-expanded={open} className="flex w-full items-center justify-between text-sm font-medium">
        {title}
        <ChevronDown className={cn("size-4 transition-transform", open && "rotate-180")} aria-hidden />
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden">
            <div className="pt-3">{children}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  )
}

export type CardState = { status: "loading" } | { status: "error"; message: string } | { status: "done"; response: QueryResponse }

export function AnswerCard({ mode, state, id }: { mode: Mode; state: CardState; id: string }) {
  const info = modeInfo(mode)
  const [focus, setFocus] = useState<string | null>(null)

  return (
    <article className="flex min-w-0 flex-col gap-4 rounded-lg border bg-card p-4" style={{ borderTopColor: info.color, borderTopWidth: 3 }}>
      <header className="flex items-baseline justify-between gap-2">
        <h3 className="font-semibold" style={{ color: info.color }}>{info.label}</h3>
        {state.status === "done" && (
          <span className="text-xs text-muted-foreground tabular-nums">{ms(state.response.timings.total_ms)}</span>
        )}
      </header>

      {state.status === "loading" && (
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" aria-hidden /> Retrieving evidence and generating an answer
        </p>
      )}
      {state.status === "error" && <p role="alert" className="text-sm text-destructive">{state.message}</p>}

      {state.status === "done" && (() => {
        const { answer, retrieval, timings, usage } = state.response
        const sourceIds = new Map(retrieval.chunks.map((c, i) => [c.chunk.id, `S${i + 1}`]))
        return (
          <>
            <div className="rounded-md bg-muted/60 p-3">
              <div className="mb-1 text-xs text-muted-foreground">Generated answer{answer.usage ? `, ${answer.usage.model}` : ""}</div>
              <p className="leading-relaxed">{answer.answer}</p>
              {answer.explanation && <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{answer.explanation}</p>}
              <div className="mt-3 flex flex-wrap gap-1.5">
                {answer.insufficient_evidence && <Flag tone="warn">Insufficient evidence</Flag>}
                {!answer.grounded && <Flag tone="warn">No valid citation</Flag>}
                {answer.invalid_citations.length > 0 && <Flag tone="warn">Removed citations {answer.invalid_citations.join(", ")}</Flag>}
                {answer.citations.map((c) => (
                  <button
                    key={c.id}
                    onClick={() => setFocus(c.id)}
                    className="rounded border bg-background px-1.5 py-0.5 font-mono text-xs hover:border-primary"
                    title={c.kind === "chunk" ? `${c.filename}${c.page != null ? `, page ${c.page}` : ""}` : c.path ?? ""}
                  >
                    {c.id}
                  </button>
                ))}
              </div>
              {answer.conflicts.length > 0 && (
                <div className="mt-3 text-sm text-destructive">
                  <div className="font-medium">Conflicting evidence</div>
                  <ul className="list-disc pl-5">{answer.conflicts.map((c, i) => <li key={i}>{c}</li>)}</ul>
                </div>
              )}
            </div>

            {retrieval.paths.length > 0 && (
              <section>
                <h4 className="mb-2 text-sm font-medium">Graph paths</h4>
                <ol className="space-y-2.5">
                  {retrieval.paths.map((p, i) => (
                    <li key={i} className={cn("rounded-md p-1.5", focus === `P${i + 1}` && "bg-accent")} id={`${id}-P${i + 1}`}>
                      <div className="mb-1 flex gap-2 font-mono text-xs text-muted-foreground">
                        <span>P{i + 1}</span>
                        <span>score {p.score.toFixed(3)}</span>
                        <span>{p.chunk_ids.map((c) => sourceIds.get(c) ?? c).join(" ")}</span>
                      </div>
                      <PathThread path={p} color={info.color} index={i} />
                    </li>
                  ))}
                </ol>
              </section>
            )}

            <Disclosure title={`Retrieved evidence (${retrieval.chunks.length})`} defaultOpen={focus?.startsWith("S") ?? false}>
              {retrieval.chunks.length === 0 && <p className="text-sm text-muted-foreground">{retrieval.route_reason}</p>}
              <ol className="space-y-3">
                {retrieval.chunks.map((c, i) => (
                  <li key={c.chunk.id} className={cn("border-l-2 pl-3", focus === `S${i + 1}` && "border-primary bg-accent/50")}>
                    <div className="flex flex-wrap gap-x-3 font-mono text-xs text-muted-foreground">
                      <span>S{i + 1}</span>
                      <span>{c.chunk.filename}{c.chunk.page != null && ` p.${c.chunk.page}`}</span>
                      <span>score {c.score.toFixed(3)}</span>
                      {Object.entries(c.sources).map(([src, s]) => (
                        <span key={src}>{src} #{s.rank}</span>
                      ))}
                    </div>
                    <p className="mt-1 text-sm leading-relaxed whitespace-pre-wrap">{c.chunk.text}</p>
                  </li>
                ))}
              </ol>
            </Disclosure>

            <Disclosure title="Retrieval details">
              <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
                <dt className="text-muted-foreground">Route</dt>
                <dd>{retrieval.route}: {retrieval.route_reason}</dd>
                {retrieval.seeds.length > 0 && (
                  <>
                    <dt className="text-muted-foreground">Seed entities</dt>
                    <dd>{retrieval.seeds.map((s) => `${s.entity_id} (${s.method})`).join(", ")}</dd>
                  </>
                )}
                <dt className="text-muted-foreground">Retrieval</dt>
                <dd className="tabular-nums">{ms(timings.retrieval_ms)}</dd>
                <dt className="text-muted-foreground">Generation</dt>
                <dd className="tabular-nums">{ms(timings.generation_ms)}</dd>
                <dt className="text-muted-foreground">LLM calls</dt>
                <dd className="tabular-nums">
                  {usage.llm_calls} ({usage.cached_calls} from cache), {usage.prompt_tokens + usage.completion_tokens} tokens
                </dd>
              </dl>
            </Disclosure>
          </>
        )
      })()}
    </article>
  )
}
