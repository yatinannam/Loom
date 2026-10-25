"use client"

import cytoscape, { type Core, type ElementDefinition } from "cytoscape"
import { useEffect, useRef } from "react"

import { ENTITY_COLORS } from "@/lib/modes"
import type { GraphData } from "@/lib/types"

// Shape encodes type redundantly with color, so the legend works without color vision.
const SHAPES: Record<string, string> = {
  PERSON: "ellipse",
  ORGANIZATION: "round-rectangle",
  TEAM: "hexagon",
  PROJECT: "diamond",
  PRODUCT: "round-tag",
  TECHNOLOGY: "rectangle",
  LOCATION: "triangle",
  EVENT: "star",
  CONCEPT: "octagon",
  OTHER: "ellipse",
}
export const entityShape = (type: string) => SHAPES[type] ?? "ellipse"

function css(name: string, fallback: string) {
  if (typeof window === "undefined") return fallback
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback
}

function elements(data: GraphData): ElementDefinition[] {
  const ids = new Set(data.entities.map((e) => e.id))
  return [
    ...data.entities.map((e) => ({
      group: "nodes" as const,
      data: { id: e.id, label: e.name, type: e.type, degree: e.degree },
    })),
    ...data.relations
      .filter((r) => ids.has(r.source) && ids.has(r.target))
      .map((r) => ({ group: "edges" as const, data: { id: r.key, source: r.source, target: r.target, label: r.type } })),
  ]
}

export function GraphCanvas({
  data,
  selected,
  onSelectNode,
  onSelectEdge,
  onExpand,
}: {
  data: GraphData
  selected: string | null
  onSelectNode: (id: string) => void
  onSelectEdge: (key: string) => void
  onExpand: (id: string) => void
}) {
  const container = useRef<HTMLDivElement>(null)
  const cy = useRef<Core | null>(null)
  const handlers = useRef({ onSelectNode, onSelectEdge, onExpand })
  handlers.current = { onSelectNode, onSelectEdge, onExpand }

  useEffect(() => {
    const fg = css("--foreground", "#1a2136")
    const muted = css("--muted-foreground", "#586176")
    const bg = css("--background", "#f3f5f8")
    const ring = css("--ring", "#3346a8")
    const instance = cytoscape({
      container: container.current,
      minZoom: 0.2,
      maxZoom: 3,
      style: [
        {
          selector: "node",
          style: {
            "background-color": (n) => ENTITY_COLORS[n.data("type")] ?? ENTITY_COLORS.OTHER,
            shape: ((n: cytoscape.NodeSingular) => entityShape(n.data("type"))) as unknown as cytoscape.Css.NodeShape,
            label: "data(label)",
            color: fg,
            "font-size": 11,
            "text-valign": "bottom",
            "text-margin-y": 5,
            "text-background-color": bg,
            "text-background-opacity": 0.85,
            "text-background-padding": "2px",
            width: (n: cytoscape.NodeSingular) => 18 + Math.min(n.data("degree") ?? 0, 10) * 2,
            height: (n: cytoscape.NodeSingular) => 18 + Math.min(n.data("degree") ?? 0, 10) * 2,
          },
        },
        {
          selector: "edge",
          style: {
            width: 1.4,
            "line-color": muted,
            "line-opacity": 0.55,
            "target-arrow-color": muted,
            "target-arrow-shape": "triangle",
            "arrow-scale": 0.8,
            "curve-style": "bezier",
            label: "data(label)",
            "font-size": 8,
            color: muted,
            "text-rotation": "autorotate",
            "text-background-color": bg,
            "text-background-opacity": 0.9,
            "text-background-padding": "1px",
          },
        },
        { selector: "node:selected", style: { "border-width": 3, "border-color": ring } },
        { selector: "edge:selected", style: { "line-color": ring, "target-arrow-color": ring, width: 2.5, "line-opacity": 1 } },
        { selector: ".faded", style: { opacity: 0.25 } },
      ],
    })
    instance.on("tap", "node", (e) => handlers.current.onSelectNode(e.target.id()))
    instance.on("tap", "edge", (e) => handlers.current.onSelectEdge(e.target.id()))
    instance.on("dbltap", "node", (e) => handlers.current.onExpand(e.target.id()))
    cy.current = instance
    return () => instance.destroy()
  }, [])

  useEffect(() => {
    const instance = cy.current
    if (!instance) return
    const next = elements(data)
    const nextIds = new Set(next.map((e) => e.data.id as string))
    instance.elements().filter((el) => !nextIds.has(el.id())).remove()
    const added = next.filter((e) => instance.getElementById(e.data.id as string).empty())
    if (added.length) {
      instance.add(added)
      const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches
      instance.layout({ name: "cose", animate: !reduce, animationDuration: 400, nodeRepulsion: () => 9000, idealEdgeLength: () => 90, padding: 30 }).run()
    }
  }, [data])

  useEffect(() => {
    const instance = cy.current
    if (!instance) return
    instance.elements().removeClass("faded").unselect()
    if (!selected) return
    const node = instance.nodes().getElementById(selected)
    const edge = instance.edges().getElementById(selected)
    if (node.empty() && edge.empty()) return
    const hood = node.nonempty() ? node.closedNeighborhood() : edge.union(edge.connectedNodes())
    ;(node.nonempty() ? node : edge).select()
    instance.elements().not(hood).addClass("faded")
  }, [selected, data])

  return <div ref={container} className="h-full w-full" role="img" aria-label="Knowledge graph. Use the search and detail panel for keyboard access." />
}
