# Branching Strategy

This repository follows a **Git Flow–lite** strategy: a protected `main` branch for production, a `develop` integration branch, and short-lived feature/fix branches.

## Branches

| Branch | Purpose | Rules |
|--------|---------|-------|
| `main` | Production-ready code only | Direct pushes **blocked**. Requires PR + review. |
| `develop` | Integration branch | All features merge here first before release to `main`. |
| `feature/part-XX-description` | New features | Branch off `develop`, merge back via PR. E.g. `feature/part-12-rag-pipeline` |
| `fix/brief-description` | Bug fixes | Branch off `develop` (or `main` for hotfixes). E.g. `fix/chat-stream-timeout` |

## Workflow

```bash
# 1. Start a feature
git checkout develop
git pull origin develop
git checkout -b feature/part-19-github-repo-organization

# 2. Work, commit, push
git add .
git commit -m "feat: add issue and PR templates"
git push -u origin feature/part-19-github-repo-organization

# 3. Open a PR into develop on GitHub
# 4. After review + merge, delete the feature branch
git checkout develop
git pull origin develop
git branch -d feature/part-19-github-repo-organization

# 5. Release: PR from develop into main
```

## Rules of thumb

- **Keep feature branches short-lived** (< 1 week). Long-lived branches cause painful merges.
- **One PR = one concern.** Don't mix features and unrelated refactors.
- **Rebase or merge `develop` into your branch regularly** to stay current.
- **Never commit secrets** (`.env`, API keys). Use `.env.example` for reference.
- **Commit messages:** use conventional prefixes — `feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`.
