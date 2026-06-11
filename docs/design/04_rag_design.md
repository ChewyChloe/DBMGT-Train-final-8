# 4. Vector / RAG Design

## 4.1 Policy Sources

TransitFlow uses policy JSON files as semi-structured knowledge sources. These include refund policies, booking rules, ticket types, travel conduct policies, and Task 6 membership policy rules.

## 4.2 Embedding Pipeline

The `seed_vectors.py` script parses policy JSON files, flattens nested policy structures into natural-language documents, generates embeddings using Ollama, and stores them in PostgreSQL with pgvector.

## 4.3 Vector Storage

Policy documents are stored in the `policy_documents` table. Each row contains:

- title
- category
- content
- embedding

## 4.4 Retrieval

The query function `query_policy_vector_search` retrieves semantically similar policy documents by comparing query embeddings with stored document embeddings.

## 4.5 Task 6 Extension

Task 6 adds `membership_policy.json`, which includes:

- loyalty point earning rules
- loyalty point redemption rules
- transfer waiting penalty policy
- crowded station penalty policy

After Task 6, the policy document count increases from 71 to 75.