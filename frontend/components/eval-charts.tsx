"use client"

import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"

import { modeInfo, ms, pct } from "@/lib/modes"
import type { EvalSummary, Mode } from "@/lib/types"

const QUALITY: { key: keyof EvalSummary["modes"][string]; label: string }[] = [
  { key: "accuracy", label: "Accuracy" },
  { key: "f1", label: "Token F1" },
  { key: "context_recall", label: "Context recall" },
  { key: "citation_precision", label: "Citation precision" },
  { key: "citation_recall", label: "Citation recall" },
]

const CATEGORY_LABELS: Record<string, string> = {
  direct: "Direct",
  relationship: "Relationship",
  two_hop: "Two-hop",
  three_hop: "Three-hop",
  multi_document: "Multi-document",
  insufficient_evidence: "Insufficient evidence",
  retrieval_trap: "Retrieval trap",
}
export const categoryLabel = (c: string) => CATEGORY_LABELS[c] ?? c

const axis = { stroke: "var(--border)", tick: { fill: "var(--muted-foreground)", fontSize: 12 } }

function ChartFrame({ title, children, height = 260 }: { title: string; children: React.ReactElement; height?: number }) {
  return (
    <figure className="min-w-0">
      <figcaption className="mb-2 text-sm font-medium">{title}</figcaption>
      <div style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">{children}</ResponsiveContainer>
      </div>
    </figure>
  )
}

function bars(modes: Mode[]) {
  return modes.map((m) => (
    <Bar key={m} dataKey={m} name={modeInfo(m).label} fill={modeInfo(m).color} radius={[4, 4, 0, 0]} maxBarSize={28} />
  ))
}

const tooltip = (format: (v: number) => string) => (
  <Tooltip
    cursor={{ fill: "var(--muted)", opacity: 0.6 }}
    contentStyle={{ background: "var(--popover)", border: "1px solid var(--border)", borderRadius: 6, color: "var(--popover-foreground)", fontSize: 12 }}
    formatter={(v) => (typeof v === "number" ? format(v) : "n/a")}
  />
)

export function EvalCharts({ summary, modes }: { summary: EvalSummary; modes: Mode[] }) {
  const quality = QUALITY.map((q) => ({
    metric: q.label,
    ...Object.fromEntries(modes.map((m) => [m, summary.modes[m]?.[q.key] ?? null])),
  }))
  const categories = Object.entries(summary.by_category).map(([c, per]) => ({ category: categoryLabel(c), ...per }))
  const latency = modes.map((m) => ({
    mode: modeInfo(m).label,
    retrieval: summary.modes[m]?.retrieval_ms_mean ?? 0,
    generation: (summary.modes[m]?.total_ms_mean ?? 0) - (summary.modes[m]?.retrieval_ms_mean ?? 0),
  }))

  return (
    <div className="grid gap-10 xl:grid-cols-2">
      <ChartFrame title="Answer and evidence quality">
        <BarChart data={quality} barGap={2} margin={{ left: -8, right: 8 }}>
          <CartesianGrid vertical={false} stroke="var(--border)" strokeDasharray="2 4" />
          <XAxis dataKey="metric" {...axis} interval={0} tickLine={false} />
          <YAxis {...axis} domain={[0, 1]} tickFormatter={(v) => `${Math.round(v * 100)}%`} tickLine={false} axisLine={false} />
          {tooltip((v) => pct(v))}
          <Legend wrapperStyle={{ fontSize: 12, color: "var(--muted-foreground)" }} />
          {bars(modes)}
        </BarChart>
      </ChartFrame>

      <ChartFrame title="Accuracy by question category">
        <BarChart data={categories} barGap={2} margin={{ left: -8, right: 8 }}>
          <CartesianGrid vertical={false} stroke="var(--border)" strokeDasharray="2 4" />
          <XAxis dataKey="category" {...axis} interval={0} tickLine={false} angle={-20} textAnchor="end" height={56} />
          <YAxis {...axis} domain={[0, 1]} tickFormatter={(v) => `${Math.round(v * 100)}%`} tickLine={false} axisLine={false} />
          {tooltip((v) => pct(v))}
          <Legend wrapperStyle={{ fontSize: 12, color: "var(--muted-foreground)" }} />
          {bars(modes)}
        </BarChart>
      </ChartFrame>

      <ChartFrame title="Mean end-to-end latency per question, split into retrieval and generation" height={60 + modes.length * 44}>
        <BarChart data={latency} layout="vertical" margin={{ left: 24, right: 16 }} barCategoryGap={10}>
          <CartesianGrid horizontal={false} stroke="var(--border)" strokeDasharray="2 4" />
          <XAxis type="number" {...axis} tickFormatter={(v) => ms(v)} tickLine={false} />
          <YAxis type="category" dataKey="mode" {...axis} width={120} tickLine={false} axisLine={false} />
          {tooltip((v) => ms(v))}
          <Legend wrapperStyle={{ fontSize: 12, color: "var(--muted-foreground)" }} />
          {/* Stage, not mode, is the series here: two neutral inks so mode colors keep one meaning. */}
          <Bar dataKey="retrieval" name="Retrieval" stackId="t" fill="var(--foreground)" fillOpacity={0.75} stroke="var(--card)" strokeWidth={2} />
          <Bar dataKey="generation" name="Generation" stackId="t" fill="var(--muted-foreground)" fillOpacity={0.45} radius={[0, 4, 4, 0]} stroke="var(--card)" strokeWidth={2} />
        </BarChart>
      </ChartFrame>
    </div>
  )
}
