"use client"

import { Loader2 } from "lucide-react"
import { useRef, useState } from "react"

import { PageHeader } from "@/components/app-shell"
import { AnswerCard, type CardState } from "@/components/answer-card"
import { Button } from "@/components/ui/button"
import { api, ApiError } from "@/lib/api"
import { MODES } from "@/lib/modes"
import type { Mode } from "@/lib/types"
import { cn } from "@/lib/utils"

type Choice = Mode | "compare"

interface Exchange {
  id: number
  question: string
  modes: Mode[]
  results: Partial<Record<Mode, CardState>>
}

const EXAMPLES = [
  "Which hardware platform is used by the project led by Alice's team, and which technology connects the project to that hardware?",
  "What GPUs does the library used by Bob Tanaka's team's project run on?",
  "In which city is the vendor that maintains VisionKit headquartered?",
]

const CHOICES: { id: Choice; label: string }[] = [...MODES.map((m) => ({ id: m.id as Choice, label: m.label })), { id: "compare", label: "Compare all" }]

export default function AskPage() {
  const [question, setQuestion] = useState("")
  const [choice, setChoice] = useState<Choice>("compare")
  const [thread, setThread] = useState<Exchange[]>([])
  const nextId = useRef(1)
  const pending = thread.some((x) => Object.values(x.results).some((r) => r?.status === "loading"))

  const ask = (q: string) => {
    const text = q.trim()
    if (!text || pending) return
    const modes = choice === "compare" ? MODES.map((m) => m.id) : [choice]
    const id = nextId.current++
    setThread((t) => [{ id, question: text, modes, results: Object.fromEntries(modes.map((m) => [m, { status: "loading" }])) }, ...t])
    setQuestion("")
    // Sequential, not parallel: keeps provider requests within free-tier rate limits.
    ;(async () => {
      for (const mode of modes) {
        let state: CardState
        try {
          state = { status: "done", response: await api.query(text, mode) }
        } catch (e) {
          state = { status: "error", message: (e as ApiError).message }
        }
        setThread((t) => t.map((x) => (x.id === id ? { ...x, results: { ...x.results, [mode]: state } } : x)))
      }
    })()
  }

  return (
    <div className="max-w-7xl">
      <PageHeader
        title="Ask"
        description="Questions are answered only from retrieved evidence. Each answer lists what it was built from, so you can see where the modes differ."
      />

      <form
        onSubmit={(e) => {
          e.preventDefault()
          ask(question)
        }}
        className="rounded-lg border bg-card p-3"
      >
        <label htmlFor="question" className="sr-only">Question</label>
        <textarea
          id="question"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault()
              ask(question)
            }
          }}
          rows={2}
          maxLength={2000}
          placeholder="Ask a question that spans several documents"
          className="w-full resize-none bg-transparent px-1 text-base outline-none placeholder:text-muted-foreground"
        />
        <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
          <div role="radiogroup" aria-label="Retrieval mode" className="flex flex-wrap gap-1 rounded-md bg-muted p-1">
            {CHOICES.map((c) => (
              <button
                key={c.id}
                type="button"
                role="radio"
                aria-checked={choice === c.id}
                onClick={() => setChoice(c.id)}
                className={cn("rounded px-2.5 py-1 text-sm transition-colors", choice === c.id ? "bg-background font-medium shadow-sm" : "text-muted-foreground hover:text-foreground")}
              >
                {c.label}
              </button>
            ))}
          </div>
          <Button type="submit" disabled={!question.trim() || pending}>
            {pending && <Loader2 className="animate-spin" aria-hidden />}
            Ask
          </Button>
        </div>
      </form>

      {thread.length === 0 && (
        <section className="mt-8">
          <h2 className="mb-2 text-sm font-medium text-muted-foreground">Questions from the benchmark corpus</h2>
          <ul className="space-y-1">
            {EXAMPLES.map((q) => (
              <li key={q}>
                <button onClick={() => setQuestion(q)} className="rounded px-2 py-1.5 text-left text-sm hover:bg-muted">
                  {q}
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      <div className="mt-8 space-y-10">
        {thread.map((x) => (
          <section key={x.id} aria-label={x.question}>
            <p className="mb-3 max-w-3xl text-lg font-medium leading-snug">{x.question}</p>
            <div className={cn("grid gap-4", x.modes.length > 1 && "xl:grid-cols-3")}>
              {x.modes.map((m) => (
                <AnswerCard key={m} id={`q${x.id}-${m}`} mode={m} state={x.results[m] ?? { status: "loading" }} />
              ))}
            </div>
          </section>
        ))}
      </div>
    </div>
  )
}
