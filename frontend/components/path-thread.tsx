"use client"

import { motion } from "motion/react"

import type { GraphPath } from "@/lib/types"

/** A graph path drawn as a thread: entity knots joined by relation strands that draw in order. */
export function PathThread({ path, color, index }: { path: GraphPath; color: string; index: number }) {
  const first = path.steps[0]
  const nodes = [first.forward ? first.source_name : first.target_name, ...path.steps.map((s) => (s.forward ? s.target_name : s.source_name))]
  return (
    <div className="flex flex-wrap items-center gap-y-2 text-sm" aria-label={path.rendered}>
      {nodes.map((name, i) => (
        <span key={i} className="flex items-center">
          <span className="rounded-full border bg-background px-2.5 py-0.5 whitespace-nowrap" style={{ borderColor: color }}>
            {name}
          </span>
          {i < path.steps.length && (
            <span className="relative mx-1 flex flex-col items-center" aria-hidden>
              <span className="font-mono text-[10px] leading-none text-muted-foreground">{path.steps[i].type}</span>
              <svg width="64" height="12" viewBox="0 0 64 12" className="mt-0.5">
                <motion.path
                  d="M2 6 C 18 0, 30 12, 46 6 S 58 4, 60 6"
                  fill="none"
                  stroke={color}
                  strokeWidth="2"
                  strokeLinecap="round"
                  initial={{ pathLength: 0 }}
                  animate={{ pathLength: 1 }}
                  transition={{ duration: 0.35, delay: index * 0.12 + i * 0.18, ease: "easeOut" }}
                  transform={path.steps[i].forward ? undefined : "translate(64 0) scale(-1 1)"}
                />
                <path d={path.steps[i].forward ? "M56 2 L62 6 L56 10" : "M8 2 L2 6 L8 10"} fill="none" stroke={color} strokeWidth="1.5" />
              </svg>
            </span>
          )}
        </span>
      ))}
    </div>
  )
}
