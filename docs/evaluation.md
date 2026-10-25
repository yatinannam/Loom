# Evaluation

This document describes the benchmark corpus, the question set and how results are
measured. Results are added only from actual runs, with the date, models and
configuration they were produced with.

## Corpus

`data/benchmark/` contains 11 short fictional documents about an invented company,
Acme Technologies. Fictional content means the LLM cannot answer from prior knowledge.

| File | Content | Role |
|---|---|---|
| `employee.md` | Alice works at Acme, leads Autonomous Systems | demo corpus |
| `project.md` | Autonomous Systems developed Project Falcon, which uses EdgeCore | demo corpus |
| `technology.md` | EdgeCore maintained by the infrastructure team, deployed on NVIDIA Jetson | demo corpus |
| `people-directory.md` | Bob Tanaka leads Perception; Carla Mendes leads infrastructure; Dmitri Volkov reports to Alice | links people to teams |
| `perception.md` | Perception developed Project Heron, which uses VisionKit | second project chain |
| `visionkit.md` | VisionKit maintained by Lumen Labs, runs on Intel Arc GPUs | second project chain |
| `lumen-labs.md` | Lumen Labs headquartered in Porto; support agreement with Acme | vendor |
| `sites.md` | Pune robotics lab; Falcon field tests there; Northwind supplies Jetson devices | facilities and suppliers |
| `northwind.md` | Northwind Components based in Rotterdam; account manager Eva Lindqvist | supplier |
| `edge-hardware-guide.md` | generic article on choosing an edge hardware platform, no named entities | distractor |
| `quarterly-update.md` | hiring news; Dmitri Volkov coordinates Falcon test schedules | distractor |

The two distractors share vocabulary with several questions ("hardware platform",
"project", "team", "Project Falcon") without containing the answers.

The first three files are byte-identical to `data/demo/`, so the smoke-test scenario is
part of the benchmark.

## Questions

`data/benchmark/questions.json`, 22 questions:

| Category | Count | What it tests |
|---|---|---|
| `direct` | 3 | fact stated in one sentence |
| `relationship` | 3 | one relation between two named entities |
| `two_hop` | 4 | two relations across two documents |
| `three_hop` | 3 | three or more relations across three documents |
| `multi_document` | 4 | independent facts from two documents combined |
| `insufficient_evidence` | 3 | answer not in the corpus; correct behavior is to say so |
| `retrieval_trap` | 2 | question vocabulary matches a distractor better than the evidence |

Each question has `reference_answer`, `answer_keywords` (a list of groups; every group
must be matched by at least one of its alternatives) and `required_documents` (the
documents that together contain the answer).

`backend/tests/test_benchmark_data.py` checks that every required document exists and
every keyword alternative appears in the required documents, so a question cannot be
unanswerable by construction.

## Integrity rules

- The corpus and questions were committed before the first live evaluation run, in the
  commit `data: freeze benchmark corpus and questions`.
- They are not edited to improve scores. Any later change is committed with its reason
  in `docs/progress.md`, and earlier results stay recorded.
- Every mode runs on the same indexed corpus, the same embedding model, the same answer
  model and prompt, and the same evidence budget (`MAX_EVIDENCE_CHUNKS`).
- Results are reported as measured, including results unfavorable to GraphRAG.
