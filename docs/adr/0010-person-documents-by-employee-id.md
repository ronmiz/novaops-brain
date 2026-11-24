# ADR 0010 — A person's documents are found by employee id, not by name

Date: 2026-11-24 · Status: accepted

## Context
"What does her offer letter say she needs on day one?" (S2 t2) failed 2 of 3 runs: dense
embeddings encode a person's name weakly, and the search returned Sara **Cohen**'s and Ben
Walker's documents instead of Maya Cohen's (#31).

An exact-name match fixed it (#31, #33), but a name is not an identity. The seed has two
Mayas (Maya Cohen, Maya Rosen). Putting the name in the embedded query also pulled S9 t1's
promotion question toward chunks about people (#34). Only 2 of 102 documents contain an
employee id; the rest name people in full.

## Decision
- **At ingest**, `documents.people_in()` tags every chunk with the employee ids of everyone its
  document names in full. The mapping (`db.ids_by_full_name()`) comes from the employee table.
  The ids go in a new `people` keyword field of the index. 36 documents are tagged.
- **`search_documents(query, employee_id=None)`**: when the model needs ONE employee's own
  documents, it passes the id `get_employee` returned. `retrieval.person_query()` adds a
  `term people=<id>` query **under the same `build_filter` permission filter** as the k-NN.
  Those hits join the k-NN candidates before the rerank.
- **The k-NN embeds only the topic** (`topic_of`: the query without the people in it).
- **No id passed**: the exact-name match (#31/#33) is the fallback.
- **The id is checked like any other `employee_id` argument**: `unverified_employee_id` and the
  someone-else guard (#28) apply unchanged. An invented id is refused before it reaches the
  server.

## Consequences
- An exact identifier: E001 is one person. The two Mayas can no longer be confused.
- The index must be rebuilt (`python -m novaops.rag.store`, 470 chunks) whenever the
  employee table or the corpus changes.
- A document that names someone only by first name is not tagged with them. The name
  fallback still covers it.
