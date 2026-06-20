## Summary

Describe the change and the CodexQB surface it affects.

## Validation

- [ ] `make test`
- [ ] `make check`
- [ ] `git diff --check`
- [ ] `make export-sanitized` when release/package behavior changed
- [ ] Extracted `CodexQB-sanitized.zip` and ran `make check` when release/package behavior changed

## Compatibility Checklist

- [ ] Keeps the `$codexqb` invocation name unchanged
- [ ] Keeps required `Planing` filenames unchanged
- [ ] Keeps validation dependency-free unless explicitly discussed
- [ ] Does not print or commit secret values
- [ ] Does not weaken `export-sanitized` dirty index/worktree guards

## Notes

Mention any deferred work, compatibility warnings, or manual follow-up needed.
