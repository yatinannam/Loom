"use client"

import { Search } from "lucide-react"
import { useMemo, useState } from "react"

import { ErrorNote, PageHeader } from "@/components/app-shell"
import { entityShape, GraphCanvas } from "@/components/graph-canvas"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { api, ApiError } from "@/lib/api"
import { entityColor } from "@/lib/modes"
import type { Entity, EntityDetail, GraphData, Relation } from "@/lib/types"
import { useApi } from "@/lib/use-api"

function merge(a: GraphData, b: GraphData): GraphData {
  const entities = new Map(a.entities.map((e) => [e.id, e]))
  b.entities.forEach((e) => entities.set(e.id, e))
  const relations = new Map(a.relations.map((r) => [r.key, r]))
  b.relations.forEach((r) => relations.set(r.key, r))
  return { entities: [...entities.values()], relations: [...relations.values()] }
}

function TypeMark({ type }: { type: string }) {
  const shape = entityShape(type)
  const radius = shape === "ellipse" ? "9999px" : shape.includes("round") ? "3px" : "0"
  return <span className="inline-block size-2.5 shrink-0" style={{ background: entityColor(type), borderRadius: radius }} aria-hidden />
}

function EntityPanel({ detail, names, onSelect }: { detail: EntityDetail; names: Map<string, string>; onSelect: (key: string) => void }) {
  return (
    <div className="space-y-5">
      <div>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <TypeMark type={detail.type} /> <span className="capitalize">{detail.type.toLowerCase()}</span>
          <span>{detail.degree} relationships</span>
        </div>
        <h2 className="mt-1 text-lg font-semibold">{detail.name}</h2>
        {detail.description && <p className="mt-1 text-sm text-muted-foreground">{detail.description}</p>}
        {detail.aliases.length > 0 && <p className="mt-2 text-sm">Also called {detail.aliases.join(", ")}</p>}
      </div>
      <section>
        <h3 className="mb-2 text-sm font-medium">Relationships</h3>
        <ul className="space-y-1">
          {detail.relations.map((r) => (
            <li key={r.key}>
              <button onClick={() => onSelect(r.key)} className="w-full rounded px-2 py-1 text-left font-mono text-xs hover:bg-muted">
                {names.get(r.source) ?? r.source} -[{r.type}]-&gt; {names.get(r.target) ?? r.target}
              </button>
            </li>
          ))}
        </ul>
      </section>
      <section>
        <h3 className="mb-2 text-sm font-medium">Mentioned in</h3>
        <ul className="space-y-1 text-sm">
          {detail.mentions.map((m) => (
            <li key={m.chunk_id} className="flex justify-between gap-3">
              <span className="truncate">{m.filename}{m.page != null && `, page ${m.page}`}</span>
              <span className="font-mono text-xs text-muted-foreground">{m.chunk_id}</span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}

function RelationPanel({ relation, names, filenames }: { relation: Relation; names: Map<string, string>; filenames: Map<string, string> }) {
  return (
    <div className="space-y-4">
      <div>
        <div className="text-xs text-muted-foreground">Relationship, confidence {relation.confidence.toFixed(2)}</div>
        <h2 className="mt-1 font-mono text-sm font-semibold">
          {names.get(relation.source) ?? relation.source} -[{relation.type}]-&gt; {names.get(relation.target) ?? relation.target}
        </h2>
      </div>
      <section>
        <h3 className="mb-2 text-sm font-medium">Supporting text</h3>
        <ul className="space-y-3">
          {relation.evidence.map((ev, i) => (
            <li key={relation.chunk_ids[i]} className="border-l-2 pl-3 text-sm">
              <p className="leading-relaxed">{ev}</p>
              <p className="mt-1 text-xs text-muted-foreground">
                {filenames.get(relation.document_ids[i]) ?? relation.document_ids[i]} <span className="font-mono">{relation.chunk_ids[i]}</span>
              </p>
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}

export default function GraphPage() {
  const initial = useApi(() => api.subgraph(200))
  const docs = useApi(api.documents)
  const [extra, setExtra] = useState<GraphData>({ entities: [], relations: [] })
  const [selected, setSelected] = useState<string | null>(null)
  const [detail, setDetail] = useState<EntityDetail | null>(null)
  const [query, setQuery] = useState("")
  const [results, setResults] = useState<Entity[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  const graph = useMemo(() => merge(initial.data ?? { entities: [], relations: [] }, extra), [initial.data, extra])
  const names = useMemo(() => new Map(graph.entities.map((e) => [e.id, e.name])), [graph])
  const filenames = useMemo(() => new Map((docs.data ?? []).map((d) => [d.id, d.filename])), [docs.data])
  const relation = selected ? graph.relations.find((r) => r.key === selected) ?? null : null
  const types = useMemo(() => [...new Set(graph.entities.map((e) => e.type))].sort(), [graph])

  const run = async (fn: () => Promise<void>) => {
    try {
      setError(null)
      await fn()
    } catch (e) {
      setError((e as ApiError).message)
    }
  }

  const selectNode = (id: string) =>
    run(async () => {
      setSelected(id)
      const [d, hood] = await Promise.all([api.entity(id), api.neighbors(id, 1)])
      setDetail(d)
      setExtra((x) => merge(x, hood))
    })
  const expand = (id: string) => run(async () => setExtra(merge(extra, await api.neighbors(id, 2))))
  const search = (e: React.FormEvent) => {
    e.preventDefault()
    if (query.trim()) run(async () => setResults(await api.searchEntities(query.trim())))
  }

  return (
    <div>
      <PageHeader
        title="Knowledge graph"
        description="Entities and relationships extracted from your documents. Select a node for its sources, select an edge for the sentence it came from, and double-click a node to load its wider neighborhood."
      />
      {(initial.error || error) && <ErrorNote message={(initial.error?.message ?? error)!} />}

      <div className="grid gap-4 lg:grid-cols-[1fr_22rem]">
        <div className="relative h-[60vh] min-h-96 overflow-hidden rounded-lg border bg-card lg:h-[calc(100vh-14rem)]">
          {initial.data?.entities.length === 0 && (
            <p className="absolute inset-0 flex items-center justify-center p-6 text-center text-sm text-muted-foreground">
              The graph is empty. Upload and ingest documents to build it.
            </p>
          )}
          <GraphCanvas
            data={graph}
            selected={selected}
            onSelectNode={selectNode}
            onSelectEdge={(key) => {
              setSelected(key)
              setDetail(null)
            }}
            onExpand={expand}
          />
          {types.length > 0 && (
            <ul className="absolute bottom-3 left-3 flex max-w-[80%] flex-wrap gap-x-3 gap-y-1 rounded-md bg-background/90 px-3 py-2 text-xs" aria-label="Legend">
              {types.map((t) => (
                <li key={t} className="flex items-center gap-1.5 capitalize">
                  <TypeMark type={t} /> {t.toLowerCase()}
                </li>
              ))}
            </ul>
          )}
        </div>

        <aside className="space-y-6 lg:max-h-[calc(100vh-14rem)] lg:overflow-y-auto">
          <form onSubmit={search} className="flex gap-2" role="search">
            <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Find an entity" aria-label="Find an entity" />
            <Button type="submit" variant="secondary" size="icon" aria-label="Search">
              <Search />
            </Button>
          </form>
          {results && (
            <ul className="space-y-0.5">
              {results.length === 0 && <li className="text-sm text-muted-foreground">No entity matches that name.</li>}
              {results.map((e) => (
                <li key={e.id}>
                  <button onClick={() => selectNode(e.id)} className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-sm hover:bg-muted">
                    <TypeMark type={e.type} /> {e.name}
                    <span className="ml-auto text-xs text-muted-foreground tabular-nums">{e.degree}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
          {detail && <EntityPanel detail={detail} names={names} onSelect={setSelected} />}
          {!detail && relation && <RelationPanel relation={relation} names={names} filenames={filenames} />}
          {!detail && !relation && (
            <p className="text-sm text-muted-foreground">Select a node or a relationship to see where it came from.</p>
          )}
        </aside>
      </div>
    </div>
  )
}
