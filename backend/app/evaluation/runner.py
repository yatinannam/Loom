"""Benchmark runner: every question in every selected mode, recorded per query.

CLI: uv run python -m app.evaluation.runner --load-corpus --modes standard graph hybrid
"""

import argparse
import csv
import io
import json
import logging
import statistics
import threading
from pathlib import Path

from app.evaluation.dataset import Question, load_questions
from app.evaluation.metrics import citation_scores, context_recall, question_correct, token_f1
from app.ingestion.parsing import document_id_for
from app.query import MODES, QueryResponse

log = logging.getLogger(__name__)

RETRIEVAL_CONFIG_FIELDS = (
    "max_evidence_chunks", "vector_min_score", "entity_min_score", "max_seed_entities", "max_hops",
    "max_node_degree", "max_paths", "hop_decay", "path_min_score", "top_paths", "rrf_k", "vector_weight",
    "graph_weight", "chunk_size", "chunk_overlap",
)
CSV_FIELDS = (
    "run_id", "question_id", "category", "mode", "correct", "f1", "context_recall", "citation_precision",
    "citation_recall", "insufficient_evidence", "grounded", "route", "retrieval_ms", "total_ms",
    "prompt_tokens", "completion_tokens", "cached_calls", "retrieved_documents", "cited_documents", "paths",
    "answer",
)


def _mean(values) -> float | None:
    values = [v for v in values if v is not None]
    return statistics.fmean(values) if values else None


def _record(q: Question, resp: QueryResponse) -> dict:
    retrieved = [c.chunk.filename for c in resp.retrieval.chunks]
    cited = sorted({f for c in resp.answer.citations for f in c.filenames})
    precision, recall = citation_scores(cited, q.required_documents)
    a = resp.answer
    return {
        "question_id": q.id,
        "category": q.category,
        "question": q.question,
        "mode": resp.mode,
        "reference_answer": q.reference_answer,
        "required_documents": q.required_documents,
        "answer": a.answer,
        "explanation": a.explanation,
        "insufficient_evidence": a.insufficient_evidence,
        "grounded": a.grounded,
        "conflicts": a.conflicts,
        "invalid_citations": a.invalid_citations,
        "citations": [{"id": c.id, "kind": c.kind, "filenames": c.filenames, "path": c.path} for c in a.citations],
        "cited_documents": cited,
        "retrieved_chunks": [
            {"chunk_id": c.chunk.id, "filename": c.chunk.filename, "page": c.chunk.page, "score": c.score,
             "sources": c.sources, "text": c.chunk.text}
            for c in resp.retrieval.chunks
        ],
        "paths": [{"rendered": p.render(), "score": p.score} for p in resp.retrieval.paths],
        "seeds": [{"entity_id": s.entity_id, "method": s.method, "score": s.score} for s in resp.retrieval.seeds],
        "route": resp.retrieval.route,
        "route_reason": resp.retrieval.route_reason,
        "retrieval_ms": resp.timings["retrieval_ms"],
        "total_ms": resp.timings["total_ms"],
        "usage": resp.usage,
        "metrics": {
            "correct": question_correct(q.category, q.answer_keywords, a.answer, a.insufficient_evidence),
            "f1": token_f1(a.answer, q.reference_answer),
            "context_recall": context_recall(retrieved, q.required_documents),
            "citation_precision": precision,
            "citation_recall": recall,
        },
    }


def summarize(records: list[dict]) -> dict:
    modes: dict[str, dict] = {}
    by_category: dict[str, dict] = {}
    for mode in dict.fromkeys(r["mode"] for r in records):
        rs = [r for r in records if r["mode"] == mode]
        m = [r["metrics"] for r in rs]
        modes[mode] = {
            "questions": len(rs),
            "accuracy": _mean(float(x["correct"]) for x in m),
            "f1": _mean(x["f1"] for x in m),
            "context_recall": _mean(x["context_recall"] for x in m),
            "citation_precision": _mean(x["citation_precision"] for x in m),
            "citation_recall": _mean(x["citation_recall"] for x in m),
            "retrieval_ms_mean": _mean(r["retrieval_ms"] for r in rs),
            "total_ms_mean": _mean(r["total_ms"] for r in rs),
            "total_ms_median": statistics.median(r["total_ms"] for r in rs),
            "prompt_tokens": sum(r["usage"]["prompt_tokens"] for r in rs),
            "completion_tokens": sum(r["usage"]["completion_tokens"] for r in rs),
            "llm_calls": sum(r["usage"]["llm_calls"] for r in rs),
            "cached_calls": sum(r["usage"]["cached_calls"] for r in rs),
            "estimated_cost_usd": sum(r["usage"]["estimated_cost_usd"] for r in rs),
        }
        for r in rs:
            by_category.setdefault(r["category"], {}).setdefault(mode, []).append(float(r["metrics"]["correct"]))
    return {
        "modes": modes,
        "by_category": {c: {m: _mean(v) for m, v in per.items()} for c, per in by_category.items()},
    }


class EvaluationService:
    def __init__(self, services, questions_path: Path | None = None):
        self.services = services
        self.questions_path = Path(questions_path or services.settings.benchmark_dir / "questions.json")
        self._lock = threading.Lock()
        self._running: str | None = None
        self._progress: dict[str, dict] = {}

    def _corpus_files(self) -> list[Path]:
        return sorted(p for p in self.services.settings.benchmark_dir.iterdir()
                      if p.suffix.lower() in (".md", ".txt", ".pdf"))

    def load_corpus(self) -> list[str]:
        """Upload and ingest the benchmark corpus. Already-ingested documents are skipped."""
        ids = []
        for path in self._corpus_files():
            row = self.services.ingestion.add_file(path.name, path.read_bytes())
            if row.status != "ingested":
                self.services.ingestion.ingest(row.id)
            ids.append(row.id)
        return ids

    def _config(self, modes: list[str]) -> dict:
        s = self.services.settings
        indexed = sorted(d.id for d in self.services.registry.list_documents() if d.status == "ingested")
        benchmark = sorted(document_id_for(p.read_bytes()) for p in self._corpus_files())
        return {
            "modes": modes,
            "questions_file": str(self.questions_path.name),
            "models": {"extraction": s.extraction_model, "answer": s.answer_model,
                       "query_entity": s.query_entity_model, "embedding": s.embedding_model},
            "llm_base_url": s.llm_base_url,
            "retrieval": {f: getattr(s, f) for f in RETRIEVAL_CONFIG_FIELDS},
            "indexed_document_ids": indexed,
            "benchmark_document_ids": benchmark,
            "corpus_mismatch": indexed != benchmark,
        }

    def start(self, modes: list[str]) -> str:
        run_id = self._begin(modes)
        threading.Thread(target=self._execute, args=(run_id, modes), daemon=True).start()
        return run_id

    def run_now(self, modes: list[str]) -> str:
        run_id = self._begin(modes)
        self._execute(run_id, modes)
        return run_id

    def _begin(self, modes: list[str]) -> str:
        invalid = [m for m in modes if m not in MODES]
        if invalid or not modes:
            raise ValueError(f"modes must be a non-empty subset of {MODES}")
        with self._lock:
            if self._running:
                raise RuntimeError(f"evaluation run {self._running} is already in progress")
            questions = load_questions(self.questions_path)
            run_id = self.services.registry.create_eval_run(self._config(modes))
            self._running = run_id
            self._progress[run_id] = {"status": "running", "done": 0, "total": len(questions) * len(modes),
                                      "error": None}
        return run_id

    def _execute(self, run_id: str, modes: list[str]) -> None:
        registry = self.services.registry
        progress = self._progress[run_id]
        records: list[dict] = []
        try:
            for q in load_questions(self.questions_path):
                for mode in modes:
                    resp = self.services.query.run(q.question, mode)
                    record = _record(q, resp)
                    registry.add_eval_result(run_id, q.id, mode, record)
                    records.append(record)
                    progress["done"] += 1
            progress["status"] = "completed"
            registry.finish_eval_run(run_id, "completed", summarize(records))
            registry.log_activity("evaluation", f"Evaluation run {run_id} completed ({len(records)} queries)")
        except Exception as exc:
            code = getattr(exc, "code", type(exc).__name__)
            progress.update(status="failed", error=f"{code}: {exc}")
            log.error("evaluation run %s failed: %s", run_id, progress["error"])
            summary = summarize(records) if records else None
            if summary is not None:
                summary["error"] = progress["error"]
            registry.finish_eval_run(run_id, "failed", summary or {"error": progress["error"]})
            registry.log_activity("evaluation", f"Evaluation run {run_id} failed: {progress['error']}")
        finally:
            with self._lock:
                self._running = None

    def progress(self, run_id: str) -> dict | None:
        if run_id in self._progress:
            return dict(self._progress[run_id])
        run = self.services.registry.get_eval_run(run_id)
        if run is None:
            return None
        done = len(self.services.registry.eval_results(run_id))
        error = (run["summary"] or {}).get("error")
        return {"status": run["status"], "done": done, "total": None, "error": error}

    def export(self, run_id: str, fmt: str) -> tuple[str, str]:
        run = self.services.registry.get_eval_run(run_id)
        if run is None:
            raise KeyError(run_id)
        results = [r["record"] for r in self.services.registry.eval_results(run_id)]
        if fmt == "json":
            return json.dumps({"run": run, "results": results}, indent=2, default=str), "application/json"
        if fmt != "csv":
            raise ValueError("format must be csv or json")
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for r in results:
            m, u = r["metrics"], r["usage"]
            writer.writerow({
                "run_id": run_id, "question_id": r["question_id"], "category": r["category"], "mode": r["mode"],
                "correct": m["correct"], "f1": round(m["f1"], 4), "context_recall": m["context_recall"],
                "citation_precision": m["citation_precision"], "citation_recall": m["citation_recall"],
                "insufficient_evidence": r["insufficient_evidence"], "grounded": r["grounded"], "route": r["route"],
                "retrieval_ms": round(r["retrieval_ms"], 1), "total_ms": round(r["total_ms"], 1),
                "prompt_tokens": u["prompt_tokens"], "completion_tokens": u["completion_tokens"],
                "cached_calls": u["cached_calls"],
                "retrieved_documents": ";".join(dict.fromkeys(c["filename"] for c in r["retrieved_chunks"])),
                "cited_documents": ";".join(r["cited_documents"]),
                "paths": " | ".join(p["rendered"] for p in r["paths"]),
                "answer": r["answer"],
            })
        return buf.getvalue(), "text/csv"


def _print_summary(summary: dict) -> None:
    cols = ("accuracy", "f1", "context_recall", "citation_precision", "citation_recall", "total_ms_mean")
    print("mode       " + "  ".join(f"{c:>18}" for c in cols))
    for mode, m in summary["modes"].items():
        cells = [f"{m[c]:>18.3f}" if m[c] is not None else f"{'n/a':>18}" for c in cols]
        print(f"{mode:<10} " + "  ".join(cells))


def main() -> None:
    from app.config import get_settings
    from app.logging import configure_logging
    from app.services import build_services

    parser = argparse.ArgumentParser(description="Run the Loom benchmark")
    parser.add_argument("--modes", nargs="+", default=list(MODES), choices=MODES)
    parser.add_argument("--load-corpus", action="store_true", help="upload and ingest data/benchmark first")
    parser.add_argument("--out", type=Path, help="write the JSON export here")
    args = parser.parse_args()

    configure_logging("WARNING")
    services = build_services(get_settings())
    if args.load_corpus:
        services.evaluation.load_corpus()
    run_id = services.evaluation.run_now(args.modes)
    run = services.registry.get_eval_run(run_id)
    print(f"run {run_id}: {run['status']}  corpus_mismatch={run['config']['corpus_mismatch']}")
    if run["summary"] and "modes" in run["summary"]:
        _print_summary(run["summary"])
    out = args.out or services.settings.data_dir / "results" / f"{run_id}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(services.evaluation.export(run_id, "json")[0], encoding="utf-8")
    print(f"results written to {out}")


if __name__ == "__main__":
    main()
