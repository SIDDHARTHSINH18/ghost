---
name: token-efficient-coding
description: Reduce unnecessary token usage while coding by inspecting only relevant files, avoiding repeated work, and making targeted changes.
---

# Token Efficient Coding

## Purpose

Keep coding sessions efficient while preserving correctness and safety.

## Rules

1. Inspect only files relevant to the current task.
2. Do not scan the entire repository unless explicitly necessary.
3. Do not reread files that were already inspected unless they may have changed.
4. Before editing, identify the smallest set of files that need modification.
5. Prefer targeted searches over full-project searches.
6. Do not repeat information already established in the conversation.
7. Keep explanations concise unless detailed explanation is requested.
8. Do not run unnecessary commands, builds, or tests.
9. After a change, run only tests relevant to that change.
10. If the task is ambiguous, ask one concise clarification instead of exploring multiple possibilities.
11. Preserve the existing architecture unless the task explicitly requires an architectural change.
12. Never expose API keys, secrets, tokens, passwords, or `.env` contents.
13. Never perform unrelated refactoring.
14. Make the smallest safe change that solves the requested problem.
15. When reporting progress, state only:
   - what changed
   - what was verified
   - what remains
16. If a request enters a reconnecting, repeated-failure, or provider-fallback loop, stop and report the issue instead of repeatedly retrying the same request.
17. Do not resend a large request after a context or connection failure; start a fresh task or reduce the required context first.

## Workflow

### Before acting

- Identify the exact task.
- Identify the relevant files.
- Determine the minimum inspection required.

### While acting

- Make the smallest safe change.
- Avoid duplicate implementations.
- Avoid unnecessary repository-wide exploration.
- Reuse existing code and architecture.

### After acting

- Run targeted verification.
- Report the result briefly.
- Stop when the requested task is complete.