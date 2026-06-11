# raw/ — immutable sources

Drop your source documents here: PDFs, markdown articles (e.g. from the Obsidian Web Clipper),
reports, transcripts, data files. Images go in `raw/assets/`.

**Rules:**
- This directory is the **source of truth**. The agent only ever **reads** from here.
- The agent must **never** modify, rename, or delete anything in `raw/`.
- Every claim in the wiki should trace back to a file here (or to a logged web lookup).

Then tell the agent: *"Ingest `raw/<filename>`."* See [`../CLAUDE.md`](../CLAUDE.md) for the
full ingest workflow.
