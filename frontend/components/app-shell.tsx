"use client"

import { BarChart3, FileText, LayoutGrid, MessageSquareText, Share2 } from "lucide-react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { MotionConfig } from "motion/react"

import { api } from "@/lib/api"
import { useApi } from "@/lib/use-api"
import { cn } from "@/lib/utils"

const NAV = [
  { href: "/", label: "Overview", icon: LayoutGrid },
  { href: "/documents", label: "Documents", icon: FileText },
  { href: "/graph", label: "Graph", icon: Share2 },
  { href: "/ask", label: "Ask", icon: MessageSquareText },
  { href: "/evaluation", label: "Evaluation", icon: BarChart3 },
]

function LoomMark() {
  // Three warp threads crossed by one weft thread: the product in one glyph.
  return (
    <svg viewBox="0 0 24 24" className="size-6" aria-hidden>
      {[6, 12, 18].map((x, i) => (
        <line key={x} x1={x} y1="3" x2={x} y2="21" stroke={["var(--mode-standard)", "var(--mode-graph)", "var(--mode-hybrid)"][i]}
          strokeWidth="2.2" strokeLinecap="round" />
      ))}
      <path d="M3 12 C 6 8, 9 16, 12 12 S 18 8, 21 12" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  )
}

function ServiceStatus() {
  const { data, error } = useApi(api.health, 15000)
  const rows = error
    ? [{ label: "API", ok: false }]
    : [
        { label: "API", ok: !!data },
        { label: "Neo4j", ok: data?.neo4j === "up" },
        { label: "LLM key", ok: !!data?.llm_configured },
      ]
  return (
    <div className="space-y-1.5 text-xs text-muted-foreground" aria-label="Service status">
      {rows.map((r) => (
        <div key={r.label} className="flex items-center gap-2">
          <span className={cn("size-1.5 rounded-full", r.ok ? "bg-mode-hybrid" : "bg-destructive")} />
          <span>{r.label}</span>
          <span className="ml-auto">{r.ok ? "ready" : "unavailable"}</span>
        </div>
      ))}
    </div>
  )
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  return (
    <MotionConfig reducedMotion="user">
      <div className="flex min-h-screen flex-col md:flex-row">
        <aside className="flex shrink-0 flex-col gap-6 border-b bg-sidebar px-4 py-4 md:sticky md:top-0 md:h-screen md:w-56 md:border-r md:border-b-0 md:py-6">
          <Link href="/" className="flex items-center gap-2 rounded-md text-lg font-semibold tracking-tight">
            <LoomMark />
            Loom
          </Link>
          <nav className="flex gap-1 overflow-x-auto md:flex-col" aria-label="Main">
            {NAV.map(({ href, label, icon: Icon }) => {
              const active = href === "/" ? pathname === "/" : pathname.startsWith(href)
              return (
                <Link
                  key={href}
                  href={href}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-sm whitespace-nowrap text-sidebar-foreground/75 transition-colors hover:bg-sidebar-accent hover:text-sidebar-foreground",
                    active && "bg-sidebar-accent font-medium text-sidebar-foreground",
                  )}
                >
                  <Icon className="size-4" aria-hidden />
                  {label}
                </Link>
              )
            })}
          </nav>
          <div className="mt-auto hidden md:block">
            <ServiceStatus />
          </div>
        </aside>
        <main className="min-w-0 flex-1 px-4 py-6 md:px-10 md:py-10">{children}</main>
      </div>
    </MotionConfig>
  )
}

export function PageHeader({ title, description, actions }: { title: string; description?: string; actions?: React.ReactNode }) {
  return (
    <header className="mb-8 flex flex-wrap items-end justify-between gap-4">
      <div className="max-w-2xl">
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {description && <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </header>
  )
}

export function ErrorNote({ message }: { message: string }) {
  return (
    <p role="alert" className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
      {message}
    </p>
  )
}
