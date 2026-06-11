# 4. Vector / RAG Design

## 4.1 Policy Sources

TransitFlow utilizes semi-structured JSON files as the ground-truth knowledge base for passenger compliance and operational rules. To simulate commercial real-world complexity, the baseline text corpora have been extensively customized and extended across four core functional domains, forcing the LLM Agent to resolve dense, non-linear edge cases:

### 1. `refund_policy.json` (Fare Refunding & Service Disruptions)
*   **Medical Assistance (`medical_assistance`):** Explicitly maps emergency workflows for incapacitated passengers. On moving **Metro** lines (typically lacking onboard conductors), passengers are directed to use the door-side **Emergency Intercom**. On **National Rail** long-distance lines, guidelines mandate contacting the **Onboard Train Conductor/Crew**.
*   **Fines & Penalties (`penalty`):** Establishes explicit penalty tiering structures for active fare evasion (e.g., buying incorrect tickets or traveling without a valid ticket), smuggling prohibited items, and behavioral conflict/assault.
*   **Maintenance Disruptions (`maintenance_rules`):** Guarantees a 100% full refund with zero processing fees (0.00 USD) if a train service is canceled due to infrastructure maintenance. Crucially, it details structured operational protocols regarding alternative transit logic (**`alternative_transport`** bridging protocols) and legal claims processing (**`how_to_claim`**).

### 2. `booking_rules.json` (Ticketing Protocols & Constraints)
*   **Official Tax Receipts (`tax_receipts`):** Introduces a post-travel fiscal compliance rule allowing passengers to download automated PDF-formatted tax receipts or itemized booking invoices via the mobile application history logs for up to 6 months post-journey. It explicitly notes that physical station ticket window staff cannot manually print these electronic invoices.
*   **Accessibility Accommodation (`accessible_booking`):** Standardizes free-of-charge wheelchair and specialized accessibility seating options across all service classes. A strict operational constraint is enforced requiring eligible passengers to submit booking requests at least 48 hours in advance through dedicated help hotlines or interactive terminal nodes.
*   **Frequent Traveler Loyalty Program (`frequent_traveler_points`):** Embeds an automated system-wide point accumulation matrix where registered users automatically earn 1 reward point for every 1.00 USD spent across National Rail and Metro networks. Points are dynamically credited into the ledger within 24 hours post-journey and can be redeemed to directly offset subsequent ticket purchases.

### 3. `ticket_types.json` (Commuter Pass & Tiering Specifications)
*   **Metro 30-Day Commuter Pass:** Establishes a fixed-rate subscription model priced at 45.00 USD. Entitles the cardholder to unlimited travel segments across the entire Metro grid immediately following the initial gate tap activation. Once activated, it is strictly non-refundable; unactivated passes qualify for a 100% refund with zero processing fees.
*   **National Rail 30-Day Commuter Pass:** Establishes a fixed-rate subscription model priced at 90.00 USD. Restricts usage exclusively to the **Standard Class (`standard`)** cabin type on normal scheduled train services along a designated origin-to-destination route snippet, completely deactivating explicit seat assignments (`seat_assignment: false`). Refunds are computed via a **pro-rata** matrix based on unutilized days, subject to a mandatory 5.00 USD administrative processing fee deducted at a physical station ticket window.

### 4. `travel_policies.json` (Passenger Conduct & Onboard Amenities)
*   **Lost & Found Property Clauses (`lost_and_found`):** Implements a strict 30-day temporal retention boundary window for items recovered within the Metro system or station hubs at the Central Lost and Found Office. Passengers can register tracking claims digitally via the application interface. Items unclaimed after the 30-day window are automatically scheduled for destruction or donated to registered charitable institutions.
*   **Onboard Power Grid Infrastructure (`charging_stations`):** Outlines physical device charging infrastructure availability. Passengers in **First Class** cabins have universal, complimentary access to standard 110V AC outlets and integrated USB charging hubs at every seat. In **Standard Class** cabins, physical charging availability is highly constrained, restricted only to select newer rolling stock models with power strips deployed underneath window-side armrests.

## 4.2 Embedding Pipeline

The ingestion and preprocessing pipeline is fully automated via `seed_vectors.py`:
1. **Parsing & Flattening:** The script systematically reads each policy JSON file. Nested objects (such as tiered penalty percentages or specific exception clauses) are flattened into coherent, standalone natural-language text documents to maintain semantic hierarchy.
2. **Chunking Strategy:** Each distinct leaf-node policy block is treated as an individual document to guarantee granular retrieval without diluting specific clauses.
3. **Embedding Generation:** Text chunks are sent to the local Ollama API to generate high-density vector representations using an open-source text embedding model.
4. **PostgreSQL Ingestion:** Generated embeddings and corresponding text metadata are upserted into the PostgreSQL instance.

## 4.3 Vector Storage

To enable hybrid relational and semantic querying within a single unified environment, the `pgvector` extension is configured in PostgreSQL. Policy chunks are stored in the dedicated `policy_documents` table:

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE policy_documents (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    category VARCHAR(100) NOT NULL,
    content TEXT NOT NULL,
    embedding VECTOR(4096) -- Vector dimension matches the Ollama embedding model output
);

CREATE INDEX ON policy_documents USING cosine (embedding);
```

## 4.4 Retrieval

The live semantic retrieval logic is centrally implemented in `databases/relational/queries.py` via the function `query_policy_vector_search`, which is exposed to the LLM Agent framework in `skeleton/agent.py` as an executable tool.

When a passenger or operational query requires policy context, the system generates a high-density query embedding from the user's question via the LLM provider. This embedding vector is then evaluated against the pre-seeded `policy_documents` table using **Cosine Distance** via the `pgvector` extension.

### 1. Database Execution & Similarity Calculation
To present human-readable metrics, the SQL query transforms the Cosine Distance operator (`<=>`) into a **Cosine Similarity** score using the mathematical derivation `1 - (embedding <=> %s::vector)`. 

Furthermore, to maintain factual precision and filter out irrelevant noise or low-confidence semantic matches, a strict similarity threshold restriction (`VECTOR_SIMILARITY_THRESHOLD`) is enforced directly within the database execution boundary.

### 2. Implementation Reference
The production implementation extracted from `databases/relational/queries.py` executes the following parameterized transaction:

```python
# Reference implementation from databases/relational/queries.py
def query_policy_vector_search(embedding: list[float], top_k: int = VECTOR_TOP_K) -> list[dict]:
    """
    Find the most relevant policy documents for a given query embedding.

    Args:
        embedding: Query vector from llm.embed(user_question)
        top_k:     Number of results to return

    Returns:
        List of dicts with title, category, content, and similarity score
    """
    sql = """
        SELECT
            title,
            category,
            content,
            1 - (embedding <=> %s::vector) AS similarity
        FROM policy_documents
        WHERE 1 - (embedding <=> %s::vector) > %s
        ORDER BY embedding <=> %s::vector
        LIMIT %s
    """
    vec_str = "[" + ",".join(str(x) for x in embedding) + "]"
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (vec_str, vec_str, VECTOR_SIMILARITY_THRESHOLD, vec_str, top_k))
            return _to_jsonable([dict(row) for row in cur.fetchall()])
```