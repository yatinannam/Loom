"use client"

import { AlertTriangle, CheckCircle2, Loader2, RotateCw, Trash2, Upload } from "lucide-react"
import { useCallback, useRef, useState } from "react"
import { toast } from "sonner"

import { ErrorNote, PageHeader } from "@/components/app-shell"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog"
import { Button } from "@/components/ui/button"
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { api, ApiError } from "@/lib/api"
import type { Chunk, DocumentRow, ExtractionError } from "@/lib/types"
import { useApi } from "@/lib/use-api"
import { cn } from "@/lib/utils"

const ACCEPT = ".pdf,.txt,.md"

function StatusCell({ doc }: { doc: DocumentRow }) {
  if (doc.status === "ingested")
    return (
      <span className="inline-flex items-center gap-1.5 text-sm">
        <CheckCircle2 className="size-4 text-mode-hybrid" aria-hidden /> Ingested
      </span>
    )
  if (doc.status === "failed")
    return (
      <span className="inline-flex items-center gap-1.5 text-sm text-destructive">
        <AlertTriangle className="size-4" aria-hidden /> Failed
      </span>
    )
  return (
    <span className="inline-flex items-center gap-1.5 text-sm text-muted-foreground">
      <Loader2 className="size-4 animate-spin text-mode-graph" aria-hidden />
      {doc.status === "processing" ? "Extracting" : "Queued"}
    </span>
  )
}

type Panel = { doc: DocumentRow; kind: "chunks" | "errors" } | null

function DetailSheet({ panel, onClose }: { panel: Panel; onClose: () => void }) {
  const [chunks, setChunks] = useState<Chunk[] | null>(null)
  const [errors, setErrors] = useState<ExtractionError[] | null>(null)
  const [failure, setFailure] = useState<string | null>(null)
  const key = panel ? `${panel.doc.id}:${panel.kind}` : null
  const loaded = useRef<string | null>(null)

  if (panel && loaded.current !== key) {
    loaded.current = key
    setChunks(null)
    setErrors(null)
    setFailure(null)
    const load = panel.kind === "chunks" ? api.chunks(panel.doc.id).then(setChunks) : api.errors(panel.doc.id).then(setErrors)
    load.catch((e: ApiError) => setFailure(e.message))
  }

  return (
    <Sheet open={!!panel} onOpenChange={(o) => !o && onClose()}>
      <SheetContent className="w-full overflow-y-auto sm:max-w-xl">
        <SheetHeader>
          <SheetTitle>{panel?.kind === "chunks" ? "Chunks" : "Extraction errors"}</SheetTitle>
          <SheetDescription>{panel?.doc.filename}</SheetDescription>
        </SheetHeader>
        <div className="space-y-3 px-4 pb-6">
          {failure && <ErrorNote message={failure} />}
          {panel?.doc.error && panel.kind === "errors" && <ErrorNote message={panel.doc.error} />}
          {chunks?.length === 0 && <p className="text-sm text-muted-foreground">This document has no stored chunks.</p>}
          {chunks?.map((c) => (
            <article key={c.id} className="rounded-md border p-3">
              <div className="mb-1.5 flex gap-3 font-mono text-xs text-muted-foreground">
                <span>{c.id}</span>
                {c.page != null && <span>page {c.page}</span>}
                <span>
                  chars {c.char_start}–{c.char_end}
                </span>
              </div>
              <p className="text-sm leading-relaxed whitespace-pre-wrap">{c.text}</p>
            </article>
          ))}
          {errors?.length === 0 && !panel?.doc.error && (
            <p className="text-sm text-muted-foreground">No extraction problems were recorded for this document.</p>
          )}
          {errors?.map((e, i) => (
            <article key={i} className="rounded-md border p-3 text-sm">
              {e.chunk_id && <div className="mb-1 font-mono text-xs text-muted-foreground">{e.chunk_id}</div>}
              <p className="break-words">{e.message}</p>
            </article>
          ))}
        </div>
      </SheetContent>
    </Sheet>
  )
}

export default function DocumentsPage() {
  const [polling, setPolling] = useState(false)
  const docs = useApi(api.documents, polling ? 2000 : null)
  const [dragging, setDragging] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [panel, setPanel] = useState<Panel>(null)
  const input = useRef<HTMLInputElement>(null)

  const busy = docs.data?.some((d) => d.status === "uploaded" || d.status === "processing") ?? false
  if (busy !== polling) setPolling(busy)

  const upload = useCallback(
    async (files: File[]) => {
      if (!files.length) return
      setUploading(true)
      setUploadError(null)
      try {
        const rows = await api.upload(files)
        toast.success(`Uploaded ${rows.length} ${rows.length === 1 ? "file" : "files"}. Extraction has started.`)
        await docs.refresh()
        setPolling(true)
      } catch (e) {
        setUploadError((e as ApiError).message)
      } finally {
        setUploading(false)
      }
    },
    [docs],
  )

  const act = async (fn: () => Promise<unknown>, done: string) => {
    try {
      await fn()
      toast.success(done)
      await docs.refresh()
      setPolling(true)
    } catch (e) {
      toast.error((e as ApiError).message)
    }
  }

  return (
    <div className="max-w-6xl">
      <PageHeader
        title="Documents"
        description="Each upload is chunked, embedded and passed through entity and relationship extraction. Identical files map to the same document, so uploading again does not duplicate anything."
      />

      <div
        onDragOver={(e) => {
          e.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault()
          setDragging(false)
          upload(Array.from(e.dataTransfer.files))
        }}
        className={cn(
          "flex flex-col items-start gap-3 rounded-lg border border-dashed p-6 transition-colors sm:flex-row sm:items-center",
          dragging ? "border-primary bg-accent" : "bg-card",
        )}
      >
        <Upload className="size-5 text-muted-foreground" aria-hidden />
        <div className="flex-1 text-sm">
          <p className="font-medium">Drop PDF, TXT or Markdown files here</p>
          <p className="text-muted-foreground">PDFs need a text layer; scanned images are not read.</p>
        </div>
        <input
          ref={input}
          type="file"
          multiple
          accept={ACCEPT}
          className="sr-only"
          onChange={(e) => {
            upload(Array.from(e.target.files ?? []))
            e.target.value = ""
          }}
        />
        <Button onClick={() => input.current?.click()} disabled={uploading}>
          {uploading && <Loader2 className="animate-spin" aria-hidden />}
          Choose files
        </Button>
      </div>
      {uploadError && (
        <div className="mt-3">
          <ErrorNote message={uploadError} />
        </div>
      )}

      <section className="mt-8">
        {docs.error && <ErrorNote message={docs.error.message} />}
        {docs.data?.length === 0 && (
          <p className="text-sm text-muted-foreground">No documents yet. Upload the files in data/demo to try the walkthrough.</p>
        )}
        {!!docs.data?.length && (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>File</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Chunks</TableHead>
                <TableHead className="text-right">Entities</TableHead>
                <TableHead className="text-right">Relations</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {docs.data.map((d) => (
                <TableRow key={d.id}>
                  <TableCell className="max-w-64">
                    <div className="truncate font-medium">{d.filename}</div>
                    <div className="font-mono text-xs text-muted-foreground">{d.id}</div>
                    {d.error && <div className="mt-1 text-xs whitespace-normal text-destructive">{d.error}</div>}
                  </TableCell>
                  <TableCell>
                    <StatusCell doc={d} />
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{d.chunk_count}</TableCell>
                  <TableCell className="text-right tabular-nums">{d.entity_count}</TableCell>
                  <TableCell className="text-right tabular-nums">{d.relation_count}</TableCell>
                  <TableCell>
                    <div className="flex justify-end gap-1">
                      <Button variant="ghost" size="sm" onClick={() => setPanel({ doc: d, kind: "chunks" })}>
                        Chunks
                      </Button>
                      <Button variant="ghost" size="sm" onClick={() => setPanel({ doc: d, kind: "errors" })}>
                        Errors
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label={`Re-ingest ${d.filename}`}
                        disabled={d.status === "processing"}
                        onClick={() => act(() => api.reingest(d.id), `Re-ingesting ${d.filename}`)}
                      >
                        <RotateCw />
                      </Button>
                      <AlertDialog>
                        <AlertDialogTrigger asChild>
                          <Button variant="ghost" size="icon" aria-label={`Remove ${d.filename}`}>
                            <Trash2 />
                          </Button>
                        </AlertDialogTrigger>
                        <AlertDialogContent>
                          <AlertDialogHeader>
                            <AlertDialogTitle>Remove {d.filename}?</AlertDialogTitle>
                            <AlertDialogDescription>
                              Its chunks, its provenance on graph relationships, and any entities only this document
                              mentions are deleted. Entities and relationships supported by other documents stay.
                            </AlertDialogDescription>
                          </AlertDialogHeader>
                          <AlertDialogFooter>
                            <AlertDialogCancel>Keep document</AlertDialogCancel>
                            <AlertDialogAction onClick={() => act(() => api.deleteDocument(d.id), `Removed ${d.filename}`)}>
                              Remove document
                            </AlertDialogAction>
                          </AlertDialogFooter>
                        </AlertDialogContent>
                      </AlertDialog>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </section>

      <DetailSheet panel={panel} onClose={() => setPanel(null)} />
    </div>
  )
}
