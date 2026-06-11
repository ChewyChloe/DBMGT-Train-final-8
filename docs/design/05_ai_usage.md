# 5. AI Tool Usage Evidence

## 5.1 AI Use Case 1 — Debugging Neo4j Authentication

AI assistance was used to identify a mismatch between the Neo4j password fallback and Docker configuration. Human verification confirmed the issue by searching for `transitflow2026` and testing Neo4j connectivity.

## 5.2 AI Use Case 2 — RAG Seeder Review

AI assistance was used to review the RAG vector seeder for idempotency, network labels, and semantic retrieval quality. Human testing confirmed that `seed_vectors.py` produced the expected policy document count and semantic search results.

## 5.3 AI Use Case 3 — Task 6 Optional Bonus

AI assistance was used to draft and implement the Task 6 extension. Human verification tested PostgreSQL loyalty booking, Neo4j transfer penalty routing, and RAG membership policy retrieval.

## 5.4 Human Verification

All AI-generated changes were manually tested using backend function calls, seed scripts, graph queries, and vector search queries before being considered for integration.