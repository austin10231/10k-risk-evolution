# Codex Push Workflow

- Default target remote: `origin`
- Default target branch: `test-new-function`
- When the user explicitly asks to `push` or `commit + push`, Codex should run:
  - `git add -A`
  - `git commit -m "<user provided message>"` (skip commit only if no staged changes)
  - `git push origin HEAD:test-new-function`
- Only push when the user gives explicit push instruction.
