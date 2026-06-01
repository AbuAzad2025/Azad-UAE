# AI runtime memory

This directory holds **runtime AI memory** files created and updated by the application during use.

## Local only — do not commit

- Files matching `*_memory.json` (for example `episodic_memory.json`) are **local runtime data** and must **not** be pushed to Git.
- They may contain chat history, customer or operational data, UAT traces, and timestamps.
- The app creates these files automatically on first use if they are missing (see `ai_knowledge/memory_system.py`).

## Examples

- Use `episodic_memory.example.json` as a safe empty structure reference only.
- **Do not** put real conversations, PII, or production data in example files.
