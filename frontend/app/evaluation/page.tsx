"use client"

import { AlertTriangle, Check, Download, Loader2, X } from "lucide-react"
import { useEffect, useMemo, useState } from "react"
import { toast } from "sonner"

import { ErrorNote, PageHeader } from "@/components/app-shell"
import { categoryLabel, EvalCharts } from "@/components/eval-charts"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Progress } from "@/components/ui/progress"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { api, ApiError } from "@/lib/api"
import { MODES, modeInfo, ms, pct } from "@/lib/modes"
import type { EvalRecord, EvalRun, Mode, ModeSummary } from "@/lib/types"
import { useApi } from "@/lib/use-api"

const ROWS: { label: string; value: (m: ModeSummary) => string }[] = [
  { label: "Answer accuracy", value: (m) => pct(m.accuracy) },
  { label: "Token F1", value: (m) => pct(m.f1) },
  { label: "Context recall", value: (m) => pct(m.context_recall) },
  { label: "Citation precision", value: (m) => pct(m.citation_precision) },
  { label: "Citation recall", value: (m) => pct(m.citation_recall) },
  { label: "Mean retrieval latency", value: (m) => ms(m.retrieval_ms_mean) },
  { label: "Mean end-to-end latency", value: (m) => ms(m.total_ms_mean) },
  { label: "Median end-to-end latency", value: (m) => ms(m.total_ms_median) },
  { label: "LLM calls (from cache)", value: (m) => `${m.llm_calls} (${m.cached_calls})` },
  { label: "Tokens (prompt + completion)", value: (m) => (m.prompt_tokens + m.completion_tokens).toLocaleString() },
]

function Verdict({ ok }: { ok: boolean | undefined }) {
  if (ok === undefined) return <span className="text-muted-foreground">n/a</span>
  return ok ? (
    <span className="inline-flex items-center gap-1 text-sm"><Check className="size-4 text-mode-hybrid" aria-hidden />Correct</span>
  ) : (
    <span className="inline-flex items-center gap-1 text-sm text-destructive"><X className="size-4" aria-hidden />Wrong</span>
  )
}

function Drilldown({ records, onClose }: { records: EvalRecord[] | null; onClose: () => void }) {
  const q = records?.[0]
  return (
    <Sheet open={!!records} onOpenChange={(o) => !o && onClose()}>
      <SheetContent className="w-full overflow-y-auto sm:max-w-3xl">
        {q && (
          <>
            <SheetHeader>
              <SheetTitle className="leading-snug">{q.question}</SheetTitle>
              <SheetDescription>
                {categoryLabel(q.category)}. Reference: {q.reference_answer}
              </SheetDescription>
            </SheetHeader>
            <div className="space-y-6 px-4 pb-8">
              <p className="text-sm">
                <span className="text-muted-foreground">Required documents: </span>
                {q.required_documents.length ? q.required_documents.join(", ") : "none (the answer is not in the corpus)"}
              </p>
              {records!.map((r) => {
                const info = modeInfo(r.mode)
                return (
                  <section key={r.mode} className="space-y-3 rounded-lg border p-4" style={{ borderLeftColor: info.color, borderLeftWidth: 3 }}>
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <h3 className="font-semibold" style={{ color: info.color }}>{info.label}</h3>
                      <Verdict ok={r.metrics.correct} />
                    </div>
                    <div className="rounded-md bg-muted/60 p-3 text-sm">
                      <div className="mb-1 text-xs text-muted-foreground">Generated answer</div>
                      {r.answer}
                      {r.insufficient_evidence && <div className="mt-1 text-xs text-muted-foreground">Declared insufficient evidence</div>}
                    </div>
                    <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-4">
                      <div><dt className="text-xs text-muted-foreground">F1</dt><dd>{pct(r.metrics.f1)}</dd></div>
                      <div><dt className="text-xs text-muted-foreground">Context recall</dt><dd>{pct(r.metrics.context_recall)}</dd></div>
                      <div><dt className="text-xs text-muted-foreground">Citation precision</dt><dd>{pct(r.metrics.citation_precision)}</dd></div>
                      <div><dt className="text-xs text-muted-foreground">End to end</dt><dd>{ms(r.total_ms)}</dd></div>
                    </dl>
                    <p className="text-sm"><span className="text-muted-foreground">Route: </span>{r.route}, {r.route_reason}</p>
                    {r.paths.length > 0 && (
                      <div>
                        <div className="mb-1 text-sm font-medium">Graph paths</div>
                        <ul className="space-y-1 font-mono text-xs">{r.paths.map((p, i) => <li key={i}>{p.rendered}</li>)}</ul>
                      </div>
                    )}
                    <div>
                      <div className="mb-1 text-sm font-medium">Retrieved chunks</div>
                      <ul className="space-y-1 text-sm">
                        {r.retrieved_chunks.map((c) => (
                          <li key={c.chunk_id} className="flex flex-wrap gap-x-3">
                            <span className={q.required_documents.includes(c.filename) ? "font-medium" : "text-muted-foreground"}>{c.filename}</span>
                            <span className="font-mono text-xs text-muted-foreground">
                              {Object.entries(c.sources).map(([s, v]) => `${s} #${v.rank}`).join(", ")}
                            </span>
                          </li>
                        ))}
                        {r.retrieved_chunks.length === 0 && <li className="text-muted-foreground">Nothing retrieved.</li>}
                      </ul>
                    </div>
                  </section>
                )
              })}
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  )
}

export default function EvaluationPage() {
  const runs = useApi(api.evalRuns)
  const [runId, setRunId] = useState<string | null>(null)
  const [run, setRun] = useState<EvalRun | null>(null)
  const [records, setRecords] = useState<EvalRecord[]>([])
  const [modes, setModes] = useState<Mode[]>(["standard", "graph", "hybrid"])
  const [busy, setBusy] = useState<"corpus" | "run" | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [onlyFailures, setOnlyFailures] = useState(false)
  const [category, setCategory] = useState("all")
  const [open, setOpen] = useState<string | null>(null)

  const selected = runId ?? runs.data?.[0]?.id ?? null

  useEffect(() => {
    if (!selected) return
    let stop = false
    let timer: ReturnType<typeof setTimeout>
    const load = async () => {
      try {
        const r = await api.evalRun(selected)
        if (stop) return
        setRun(r)
        setRecords(await api.evalResults(selected))
        if (r.status === "running") timer = setTimeout(load, 2000)
        else runs.refresh()
      } catch (e) {
        if (!stop) setError((e as ApiError).message)
      }
    }
    load()
    return () => {
      stop = true
      clearTimeout(timer)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected])

  const runModes = (run?.config.modes ?? []) as Mode[]
  const byQuestion = useMemo(() => {
    const map = new Map<string, EvalRecord[]>()
    records.forEach((r) => map.set(r.question_id, [...(map.get(r.question_id) ?? []), r]))
    return [...map.entries()]
  }, [records])
  const categories = [...new Set(records.map((r) => r.category))]
  const visible = byQuestion.filter(
    ([, rs]) => (category === "all" || rs[0].category === category) && (!onlyFailures || rs.some((r) => !r.metrics.correct)),
  )

  const act = async (kind: "corpus" | "run") => {
    setBusy(kind)
    setError(null)
    try {
      if (kind === "corpus") {
        const r = await api.loadCorpus()
        toast.success(`Benchmark corpus ready: ${r.document_ids.length} documents ingested`)
      } else {
        const r = await api.runEvaluation(modes)
        await runs.refresh()
        setRunId(r.id)
        toast.success("Benchmark started")
      }
    } catch (e) {
      setError((e as ApiError).message)
    } finally {
      setBusy(null)
    }
  }

  const summary = run?.summary?.modes ? run.summary : null
  const progress = run?.progress

  return (
    <div className="max-w-7xl">
      <PageHeader
        title="Evaluation"
        description="All modes answer the same 22 questions on the same corpus, with the same models and evidence budget. Scores are computed by keyword matching and document overlap, not by an LLM judge."
      />

      <section className="flex flex-wrap items-center gap-x-6 gap-y-3 rounded-lg border bg-card p-4">
        <Button variant="secondary" onClick={() => act("corpus")} disabled={!!busy}>
          {busy === "corpus" && <Loader2 className="animate-spin" aria-hidden />}
          Load benchmark corpus
        </Button>
        <fieldset className="flex flex-wrap gap-4">
          <legend className="sr-only">Modes to evaluate</legend>
          {MODES.map((m) => (
            <label key={m.id} className="flex items-center gap-2 text-sm">
              <Checkbox
                checked={modes.includes(m.id)}
                onCheckedChange={(c) => setModes((ms) => (c ? [...ms, m.id] : ms.filter((x) => x !== m.id)))}
              />
              {m.label}
            </label>
          ))}
        </fieldset>
        <Button onClick={() => act("run")} disabled={!!busy || modes.length === 0 || run?.status === "running"}>
          {busy === "run" && <Loader2 className="animate-spin" aria-hidden />}
          Run benchmark
        </Button>
        {!!runs.data?.length && (
          <div className="ml-auto flex items-center gap-2 text-sm">
            <span className="text-muted-foreground">Run</span>
            <Select value={selected ?? undefined} onValueChange={setRunId}>
              <SelectTrigger className="w-64" aria-label="Evaluation run">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {runs.data.map((r) => (
                  <SelectItem key={r.id} value={r.id}>
                    {new Date(r.created_at).toLocaleString()} ({r.status})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}
      </section>

      <div className="mt-4 space-y-3">
        {(error || runs.error) && <ErrorNote message={(error ?? runs.error?.message)!} />}
        {runs.data?.length === 0 && (
          <p className="text-sm text-muted-foreground">No runs yet. Load the benchmark corpus, then run the benchmark.</p>
        )}
        {run?.status === "running" && progress && (
          <div className="max-w-md space-y-1.5">
            <div className="flex justify-between text-sm">
              <span>Running</span>
              <span className="tabular-nums text-muted-foreground">{progress.done} of {progress.total ?? "?"} queries</span>
            </div>
            <Progress value={progress.total ? (progress.done / progress.total) * 100 : 0} />
          </div>
        )}
        {run?.status === "failed" && (
          <ErrorNote message={`This run stopped early: ${progress?.error ?? run.summary?.error ?? "unknown error"}. Completed queries are shown below.`} />
        )}
        {run?.config.corpus_mismatch && (
          <p className="flex items-start gap-2 text-sm text-destructive">
            <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />
            The indexed documents differ from the benchmark corpus, so other documents acted as distractors in this run.
          </p>
        )}
      </div>

      {run && summary && (
        <>
          <section className="mt-8">
            <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
              <div className="text-sm text-muted-foreground">
                Answer model {run.config.models.answer}, extraction {run.config.models.extraction}, embeddings{" "}
                {run.config.models.embedding}, {run.config.retrieval.max_hops} hops, {run.config.retrieval.max_evidence_chunks} evidence chunks
              </div>
              <div className="flex gap-2">
                <Button asChild variant="outline" size="sm">
                  <a href={api.exportUrl(run.id, "csv")} download><Download aria-hidden />CSV</a>
                </Button>
                <Button asChild variant="outline" size="sm">
                  <a href={api.exportUrl(run.id, "json")} download><Download aria-hidden />JSON</a>
                </Button>
              </div>
            </div>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Metric</TableHead>
                  {runModes.map((m) => (
                    <TableHead key={m} className="text-right">
                      <span className="inline-flex items-center gap-2">
                        <span className="size-2.5 rounded-sm" style={{ background: modeInfo(m).color }} aria-hidden />
                        {modeInfo(m).label}
                      </span>
                    </TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {ROWS.map((row) => (
                  <TableRow key={row.label}>
                    <TableCell>{row.label}</TableCell>
                    {runModes.map((m) => (
                      <TableCell key={m} className="text-right tabular-nums">
                        {summary.modes[m] ? row.value(summary.modes[m]) : "n/a"}
                      </TableCell>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </section>

          <section className="mt-10">
            <EvalCharts summary={summary} modes={runModes} />
          </section>
        </>
      )}

      {byQuestion.length > 0 && (
        <section className="mt-12">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-base font-semibold">Questions</h2>
            <div className="flex flex-wrap items-center gap-4 text-sm">
              <label className="flex items-center gap-2">
                <Checkbox checked={onlyFailures} onCheckedChange={(c) => setOnlyFailures(!!c)} />
                Only questions some mode got wrong
              </label>
              <Select value={category} onValueChange={setCategory}>
                <SelectTrigger className="w-48" aria-label="Question category">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All categories</SelectItem>
                  {categories.map((c) => (
                    <SelectItem key={c} value={c}>{categoryLabel(c)}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Question</TableHead>
                <TableHead>Category</TableHead>
                {runModes.map((m) => <TableHead key={m}>{modeInfo(m).label}</TableHead>)}
              </TableRow>
            </TableHeader>
            <TableBody>
              {visible.map(([qid, rs]) => (
                <TableRow key={qid} className="cursor-pointer" onClick={() => setOpen(qid)}>
                  <TableCell className="max-w-md whitespace-normal">
                    <button className="text-left hover:underline" onClick={() => setOpen(qid)}>{rs[0].question}</button>
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">{categoryLabel(rs[0].category)}</TableCell>
                  {runModes.map((m) => (
                    <TableCell key={m}><Verdict ok={rs.find((r) => r.mode === m)?.metrics.correct} /></TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </section>
      )}

      <Drilldown records={open ? byQuestion.find(([q]) => q === open)?.[1] ?? null : null} onClose={() => setOpen(null)} />
    </div>
  )
}
