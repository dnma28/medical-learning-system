# Architecture v0.1

```text
Medical PDFs / source documents
            |
            v
   RAG-Anything / parser
            |
      +-----+-------------------+
      |                         |
      v                         v
 Retrieval index         Candidate/Evidence Graph
                                  |
                             validation gates
                                  |
                                  v
                       Canonical Medical KG
                                  |
                          Learning Router
                     +------------+------------+
                     |                         |
                   HỌC90                 Assessment
                                               |
                                      Student/Error Graph
```

## Invariants

1. Canonical truth is not learner state.
2. Automatic extraction is not canonical truth.
3. Every promoted medical assertion needs provenance.
4. Raw copyrighted PDFs are not committed to Git.
5. Retrieval is evidence, not authority.
