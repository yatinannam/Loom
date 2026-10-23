# Original Task Brief

This is the requirements brief the project was started from, kept verbatim for
reference. `design.md` records how it is implemented and the decisions taken.

---

# Build a GraphRAG System for Multi-Hop Question Answering

Act as a senior AI engineer specializing in Retrieval-Augmented Generation (RAG), knowledge graphs, information retrieval, and LLM application development.

Build a **fully functional GraphRAG system** that answers complex, multi-hop questions by combining knowledge graph traversal with vector-based semantic retrieval. The primary goal is to demonstrate why GraphRAG can outperform standard vector-based RAG when the answer is distributed across multiple documents and connected through entities and relationships.

Do not just create a UI mockup, write a theoretical explanation, or produce disconnected code snippets. Implement a working, testable application with a clear end-to-end workflow.

## 1. Core Problem

Standard RAG retrieves documents or chunks based on semantic similarity. It can fail when a question requires connecting several pieces of information across multiple documents.

For example, consider these three documents:

**Document A — Employee**
> Alice works at Acme Technologies and leads the Autonomous Systems team.

**Document B — Project**
> The Autonomous Systems team developed Project Falcon, which uses the EdgeCore platform.

**Document C — Technology**
> EdgeCore is maintained by a separate infrastructure team and is deployed on NVIDIA Jetson devices.

A user asks:

"Which hardware platform is used by the project led by Alice's team, and which technology connects the project to that hardware?"

The system must connect the relevant entities and relationships across all three documents rather than relying on a single retrieved chunk.

The knowledge graph should represent relationships such as:

- Alice → WORKS_AT → Acme Technologies
- Alice → LEADS → Autonomous Systems
- Autonomous Systems → DEVELOPED → Project Falcon
- Project Falcon → USES → EdgeCore
- EdgeCore → DEPLOYED_ON → NVIDIA Jetson

Use this example as an initial demonstration, but design the architecture to work with arbitrary uploaded documents.

## 2. Required Architecture

Implement the following components.

### A. Document ingestion

Support uploading and processing PDF, TXT, and Markdown documents.

The ingestion pipeline must:

1. Extract text and basic metadata from uploaded files.
2. Split text into configurable, overlapping chunks.
3. Preserve document IDs, filenames, page numbers where available, and chunk IDs.
4. Generate embeddings for the chunks.
5. Extract entities and relationships from the text using an LLM or a structured extraction model.
6. Normalize entity names and deduplicate equivalent entities.
7. Build a knowledge graph from the extracted entities and relationships.
8. Store chunks, graph entities, relations, and provenance information so that every answer can be traced to its source.

Make ingestion repeatable and idempotent wherever practical, avoiding unnecessary duplicate entities, edges, and chunks when a document is processed again.

### B. Knowledge graph construction

Represent extracted information as a graph:

- Nodes: people, organizations, projects, products, technologies, locations, and other relevant entities.
- Edges: meaningful relationships between entities.
- Node metadata: canonical name, entity type, aliases, descriptions, and source references.
- Edge metadata: relationship type, supporting text, source document, confidence, and provenance.

Use a graph database such as Neo4j. Provide a Docker Compose configuration for local development.

Enforce a clear schema for extracted entities and relations. Validate model outputs before inserting them into the graph, and handle malformed or incomplete extraction responses gracefully.

Avoid inventing relationships that are not supported by the source documents.

### C. Vector retrieval

Create an embedding-based retrieval pipeline to identify relevant document chunks.

Requirements:

- Support semantic similarity search.
- Make the embedding model configurable.
- Return ranked chunks with similarity scores.
- Retain source references and metadata.
- Apply reasonable limits and configurable retrieval thresholds.

Use a suitable local vector store, such as ChromaDB, unless the existing repository already uses a compatible alternative.

### D. Graph traversal

Implement graph-based retrieval for questions that require multiple reasoning steps.

The pipeline should:

1. Extract or identify important entities from the user's query.
2. Resolve query entities to existing graph nodes.
3. Retrieve relevant seed nodes and relationships.
4. Traverse connected nodes using bounded, configurable graph hops.
5. Rank useful paths and remove irrelevant graph neighborhoods.
6. Collect supporting document chunks associated with the selected nodes and edges.
7. Combine graph evidence with semantic vector retrieval.
8. Pass the final evidence to the LLM to generate a grounded answer.

Support configurable traversal depth, defaulting to approximately 2–3 hops. Guard against unbounded traversal, extremely high-degree nodes, and unrelated graph connections.

If a question is better answered by semantic retrieval alone, allow the system to rely more heavily on vector search. Do not force graph traversal for every query.

### E. Hybrid GraphRAG retrieval

Implement two complementary retrieval methods:

**Vector retrieval**
- Finds semantically relevant chunks.
- Works well for direct factual questions and questions expressed differently from the source text.

**Graph retrieval**
- Finds entities and their relationships.
- Connects facts distributed across documents.
- Supports questions requiring multiple linked relationships.

Combine the results using a transparent, configurable ranking or fusion mechanism. Deduplicate overlapping chunks and prioritize evidence that directly supports the requested answer.

The system should explain which documents and graph paths contributed to its response.

### F. Grounded answer generation

Generate answers using only the retrieved evidence.

Every answer should include:

- A clear, direct response.
- A concise explanation of the reasoning path.
- Source citations identifying filenames and pages or chunks where available.
- Relevant entity and relationship paths when graph traversal contributes to the answer.
- An explicit statement when the documents do not contain enough evidence to answer reliably.

Do not expose private chain-of-thought. Provide a concise, evidence-based explanation instead.

If the graph or vector search returns conflicting evidence, disclose the conflict rather than silently selecting an unsupported answer.

## 3. Implement a Standard RAG Baseline

Build a separate baseline that uses the same document corpus, embeddings, LLM, and answer-generation settings but retrieves evidence using vector similarity without graph traversal.

Both retrieval modes must be switchable from the application:

- Standard RAG
- GraphRAG
- Hybrid GraphRAG

Keep the baseline and GraphRAG implementations separate enough to make comparisons fair and easy to understand.

## 4. Evaluation Framework

Build an evaluation pipeline that demonstrates whether GraphRAG improves multi-hop question answering.

Create a reproducible test dataset with at least 20 questions covering:

- Direct factual questions.
- Entity relationship questions.
- Two-hop questions.
- Three-hop questions.
- Questions requiring evidence from multiple documents.
- Questions with insufficient evidence.
- Questions designed to expose retrieval failures.

For each query, record:

- Ground-truth answer.
- Required source documents.
- Retrieval mode.
- Retrieved chunks.
- Graph paths traversed, where applicable.
- Generated answer.
- Retrieval latency.
- End-to-end latency.
- Token usage and estimated LLM cost, when provider usage data is available.
- Evaluation metrics.

Calculate appropriate metrics, including:

- Answer correctness or F1 against the reference answers.
- Evidence or context recall where ground-truth evidence annotations are available.
- Citation correctness.
- End-to-end latency.

Compare the baseline and GraphRAG on the same test set. Present results in a table and visualizations.

Do not fabricate evaluation results or hard-code better scores for GraphRAG. All reported results must come from actual evaluation runs. If an external LLM judge is used, make its limitations clear and use deterministic answer matching wherever appropriate.

## 5. Application Interface

Build a clean, modern web application that makes the entire workflow easy to demonstrate.

Include the following sections:

**Dashboard**
- Number of indexed documents.
- Number of graph entities.
- Number of relationships.
- Number of embedded chunks.
- Recent ingestion and query activity.

**Document Management**
- Upload supported files.
- Display ingestion status.
- View extracted chunks.
- View extraction errors.
- Reprocess or remove documents safely.

**Knowledge Graph Explorer**
- Interactive graph visualization.
- Distinct visual treatment for entity types.
- Clickable nodes and relationships.
- Entity details, relationship labels, and source provenance.
- Search for an entity and inspect its neighboring nodes.

**Question Answering**
- Chat-style query interface.
- Retrieval mode selector.
- Answer with source citations.
- Expandable supporting evidence.
- Graph traversal paths shown as readable sequences.
- A clear distinction between retrieved evidence and generated text.

**Evaluation Dashboard**
- Run the benchmark.
- Compare Standard RAG and GraphRAG.
- Show answer accuracy, context recall, citation correctness, and latency.
- Inspect individual failed queries and their retrieval results.
- Export evaluation results as CSV or JSON.

Prioritize functionality and clarity over unnecessary animations. The graph visualization and comparison dashboard should help someone understand exactly why the system succeeds or fails.

## 6. Suggested Technology Stack

First inspect the existing repository and reuse its architecture, dependencies, conventions, and package manager when appropriate.

If starting from scratch, use the following defaults:

**Backend**
- Python 3.12+
- FastAPI
- Pydantic for validation
- Neo4j for knowledge graph storage
- ChromaDB for vector retrieval
- A suitable document parsing library for PDFs
- An embedding abstraction that supports a local model
- An LLM provider abstraction for entity extraction and answer generation

**Frontend**
- Next.js with TypeScript
- Tailwind CSS and shadcn/ui
- A suitable interactive graph visualization library
- Recharts for evaluation charts

**Infrastructure**
- Docker Compose for local services.
- `.env.example` for configuration.
- Persistent volumes for database data.
- Health checks and clear startup instructions.

Keep external API credentials optional at installation time. Support a locally runnable configuration wherever feasible, and clearly document which models, dependencies, or resources are required for each operating mode.

Do not hard-code API keys, fabricate provider responses, or silently fall back to fake model outputs.

## 7. API Design

Implement clean API endpoints along these lines:

- `POST /api/documents/upload`
- `GET /api/documents`
- `GET /api/documents/{document_id}`
- `DELETE /api/documents/{document_id}`
- `POST /api/documents/{document_id}/ingest`
- `GET /api/graph/stats`
- `GET /api/graph/entities`
- `GET /api/graph/entities/{entity_id}`
- `GET /api/graph/entities/{entity_id}/neighbors`
- `POST /api/query`
- `POST /api/evaluation/run`
- `GET /api/evaluation/results`

You may adjust the route design to suit the implementation. Add validation, sensible error responses, timeouts, and structured logging.

## 8. Code Quality and Reliability

Follow these requirements throughout the implementation:

- Use modular, typed code with clear separation of concerns.
- Keep document ingestion, entity extraction, graph persistence, vector retrieval, hybrid ranking, answer generation, and evaluation in separate modules.
- Define reusable interfaces for embeddings, LLM providers, vector stores, and graph stores.
- Use parameterized database queries.
- Validate uploaded file types and impose configurable file-size limits.
- Handle missing API keys, service outages, malformed model outputs, and empty retrieval results.
- Add unit tests for entity extraction validation, entity resolution, graph traversal, hybrid retrieval, and answer citation generation.
- Add integration tests that verify the complete ingestion-to-query pipeline.
- Use deterministic mock fixtures in tests rather than relying on live LLM calls.
- Provide structured error messages and useful logs without leaking secrets.
- Never claim that an answer is verified unless it has actually been checked against the available evidence.

## 9. Demo Scenario and Acceptance Criteria

The finished application must include a reproducible demo corpus containing at least three documents linked through shared entities.

Demonstrate the following workflow:

1. Upload the three documents.
2. Ingest the documents and extract entities and relationships.
3. Inspect the resulting knowledge graph.
4. Ask a multi-hop question whose answer depends on information across the documents.
5. Run the query using Standard RAG.
6. Run the same query using GraphRAG.
7. Inspect the retrieved evidence and traversal paths for both modes.
8. Run the benchmark and compare actual results.

The implementation is successful when:

- The knowledge graph is constructed from actual document content.
- Entity and relationship provenance is preserved.
- Graph traversal can recover relevant evidence across multiple documents.
- Vector and graph evidence are combined without unnecessary duplication.
- Answers are grounded in source documents and include citations.
- Standard RAG and GraphRAG can be evaluated under comparable conditions.
- The application can be started using the documented setup procedure.
- Automated tests verify the important retrieval and ingestion behaviors.

Include the Alice / Acme Technologies / Project Falcon example from Section 1 as an initial smoke test, but do not make the system dependent on that particular dataset.

## 10. How to Execute This Task

Work directly in the repository using the available coding tools.

Follow this implementation sequence:

**Phase 1 — Repository inspection and planning**
- Inspect the directory structure, package manifests, existing dependencies, and current implementation.
- Identify reusable code and existing conventions.
- Create a concise implementation plan with clear milestones.

**Phase 2 — Core backend**
- Implement document ingestion and chunking.
- Implement validated entity and relationship extraction.
- Build graph persistence and entity resolution.
- Implement vector indexing and retrieval.
- Implement bounded graph traversal.
- Implement the hybrid retrieval and grounded answering pipeline.
- Implement the Standard RAG baseline.

**Phase 3 — Frontend**
- Build the document-management interface.
- Implement the graph explorer.
- Build the query interface and evidence visualization.
- Add the evaluation dashboard.

**Phase 4 — Testing and benchmarking**
- Create the reproducible multi-document test corpus.
- Add automated tests and the benchmark dataset.
- Run the actual tests and evaluation pipeline.
- Fix failures rather than working around them with hard-coded outputs.

**Phase 5 — Documentation and delivery**
- Write a complete README with architecture, prerequisites, setup commands, configuration, API documentation, limitations, and troubleshooting.
- Add Docker Compose and `.env.example`.
- Document how to start the application and run the demo.
- Summarize the files created, features implemented, tests executed, and any remaining limitations.

Do not stop after producing an implementation plan. Continue implementing the application end to end. Make reasonable engineering decisions without asking unnecessary questions. Prioritize a reliable working vertical slice first, then complete the remaining functionality.

**Final deliverable:** A runnable, testable GraphRAG application that clearly demonstrates how knowledge graph traversal combined with vector search can improve multi-hop question answering over a standard RAG baseline.
