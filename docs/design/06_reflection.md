# 6. Reflection and Trade-offs

## 6.1 Relational vs Graph vs Vector Databases

PostgreSQL is used for structured transactional data. Neo4j is used for station connectivity and routing. pgvector is used for semantic policy retrieval.

## 6.2 Transaction Safety

Booking and payment operations are implemented using database transactions to keep booking state and payment records consistent.

## 6.3 Agent Runtime Limitations

The Agent can call backend tools, but the final natural-language response may sometimes summarize tool results imperfectly because the system uses a lightweight local LLM. Debug mode is used to verify actual tool calls and backend results.

## 6.4 Future Improvements

Future work could include improved Agent response grounding, express-only route filtering, fewest-transfer optimization, and more advanced membership reward rules.