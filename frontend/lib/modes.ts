import type { Mode } from "./types"

export const MODES: { id: Mode; label: string; summary: string; color: string }[] = [
  {
    id: "standard",
    label: "Standard RAG",
    summary: "Vector similarity only",
    color: "var(--mode-standard)",
  },
  {
    id: "graph",
    label: "GraphRAG",
    summary: "Entity paths through the knowledge graph",
    color: "var(--mode-graph)",
  },
  {
    id: "hybrid",
    label: "Hybrid GraphRAG",
    summary: "Vector and graph results fused",
    color: "var(--mode-hybrid)",
  },
]

export const modeInfo = (id: string) => MODES.find((m) => m.id === id) ?? MODES[0]

export const ENTITY_COLORS: Record<string, string> = {
  PERSON: "#b23e4c",
  ORGANIZATION: "#3346a8",
  TEAM: "#6a4fb0",
  PROJECT: "#2c7a75",
  PRODUCT: "#a8781a",
  TECHNOLOGY: "#2f6fb5",
  LOCATION: "#5b8a3a",
  EVENT: "#c0612b",
  CONCEPT: "#6e7487",
  OTHER: "#8f95a3",
}

export const entityColor = (type: string) => ENTITY_COLORS[type] ?? ENTITY_COLORS.OTHER

export const pct = (v: number | null | undefined) => (v == null ? "n/a" : `${Math.round(v * 100)}%`)
export const ms = (v: number | null | undefined) =>
  v == null ? "n/a" : v >= 1000 ? `${(v / 1000).toFixed(1)} s` : `${Math.round(v)} ms`
