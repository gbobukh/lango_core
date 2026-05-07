# Rule: Git Synchronization Rule

## When to apply
Apply this rule only when the user explicitly asks to synchronize Git (for example: "sync git", "синхронизируй git", "обнови ветку с GitHub").

## Required sequence
1. Run `git fetch --all --prune`.
2. Check state with:
   - `git status`
   - `git branch -vv`
3. If the branch can be updated safely, use `git pull --ff-only`.
4. If fast-forward is not possible, stop and ask the user to choose strategy (`merge` or `rebase`).

## Must not
- Do not run destructive commands (`git reset --hard`, force push) unless explicitly requested.
