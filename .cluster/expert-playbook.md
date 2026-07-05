# Agent Cluster Playbook(read before S2 / S5)

## Workspace (.cluster/<taskId>/)
- plan.md: subtasks, worker assignment, expected files, dependencies, review items, and delivery items.
- worker_NN.md: worker output. Format: conclusion / evidence / analysis / gaps and risks / suggested placement in the final document.
- review.md: review findings with confidence High / Medium / Low / Conflict.
- brief.md: pre-delivery brief.
- DELIVERY/: final artifacts. The system checks this folder to confirm real delivery.

## S2 Dispatch
- Default to one subtask per worker. One-off data fetches or lightweight commands may stay on the main thread.
- For long writing, split by chapter and use at least as many writers as research dimensions.
- Draw dependencies and schedule prerequisites in earlier rounds.

## S3 Worker Prompt
First sentence: "You are not working alone; do not touch artifacts outside your responsibility."
Always provide the task boundary, needed context, target worker_NN.md, and return format. If there is no evidence, the worker must say so instead of presenting guesses as conclusions.
Research workers use autoglm-websearch/open-link and cite only sources they actually read. When a worker should use a skill, provide the skill name and task boundary, not a pasted copy of the skill.

## S4 Review
Start review when the output contains synthesized conclusions, forecasts, value judgments, non-trivial code, irreversible actions, or decisions the user may act on. Review facts, logic, numbers, and code as separate dimensions.

## S5 Delivery
- Follow the user's requested format. If none is specified, short answers can be plain text; otherwise default to `docx`.
- Reports, plans, minutes, and research → `docx`; decks → `ppt`; tables/data models → `xlsx`; fixed layouts → `pdf`; charts → `charts`.
- For long text, use `write-skill` by chapter, then render the final artifact with `docx` or another artifact skill.
- Use strict UTF-8; do not ignore decoding errors.
- Put final artifacts in DELIVERY/. In the final reply, show completed progress, clickable deliverable links, and any necessary limitations.