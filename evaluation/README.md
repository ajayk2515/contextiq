# Evaluation

Phase 10 evaluates the real application pipeline against the versioned cases in
`dataset.json`. The five Markdown files under `documents/` are synthetic Northstar
policies with deliberate role boundaries; they contain no production or private data.

From `backend/`, load or refresh the corpus through the normal ingestion path:

```powershell
python -m scripts.seed_evaluation_data
```

The seed is idempotent for each filename, content hash, and role assignment. It uses
the Executive demo user as uploader, then runs the existing Docling, OpenAI dense
embedding, FastEmbed sparse embedding, and Qdrant indexing flow. The evaluation API
never accepts a dataset path; it reads only this checked-in dataset.
