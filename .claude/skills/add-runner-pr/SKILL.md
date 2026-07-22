---
name: add-runner-pr
description: Create a branch, commit, and open a pull request that adds a new runner, following this repository's conventions. Assumes the user has already placed `metadata.json`, `preview.png`, and `<name>-frames.zip` under `runners/<name>/`. Triggers — "add a runner PR", "open a PR for the new runner", "ランナー追加のPRを作って", "〜のランナーをPRにして".
---

# Add-runner PR

## Preconditions

Before starting, confirm the user has placed:

- `runners/<name>/metadata.json`
- `runners/<name>/preview.png`
- `runners/<name>/<name>-frames.zip`

The `runners/manifest.json` entry may or may not already be in place. Check with `git status` and `git diff runners/manifest.json`. If missing, add `<name>` while preserving **alphabetical order**.

## Steps

### 1. Verify before checking the checklist

Do not tick the PR checkboxes mechanically. Run the checks first, then tick.

```bash
# Zip layout — expect <name>-frames/<name>-frame-<N>.png, no __MACOSX or .DS_Store
unzip -l runners/<name>/<name>-frames.zip

# Compare with an existing runner (e.g. dots) to confirm the same layout
unzip -l runners/dots/dots-frames.zip | head -5

# preview.png dimensions — height must be 36, width must be 10–100
file runners/<name>/preview.png
```

`Read` `metadata.json` and confirm `author`, `displayName`, `type` (`monochrome` or `color`), and `tags` are all present and correct.

If anything violates the spec (width out of range, height not 36, junk files inside the zip, etc.), **send the asset back to the user for fixing**. Do not loosen the spec ([[runner-spec-is-absolute]]).

### 2. Branch and commit

Follow the existing convention exactly. Confirm with `git log --oneline` if unsure.

- Branch name: `add-<name>`
- Commit message: `Add the <name> runner` (English, no trailing period)

```bash
git checkout -b add-<name>
git add runners/manifest.json runners/<name>/
git commit -m "$(cat <<'EOF'
Add the <name> runner

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
git push -u origin add-<name>
```

### 3. Open the PR

**Always start by `Read`ing `.github/pull_request_template.md`** and use its current contents as the PR body — never a hardcoded copy inside this skill, since the template can change and this document will drift. Fill it in by:

- Checking the `Add a new runner` box under `Type of Change`.
- Writing the `Summary` (see below).
- Ticking every item under `Checklist for Adding a Runner` that step 1 actually verified.

If a new checklist item appears in the template that step 1 did not cover, verify it now before ticking — do not tick blindly just because the item is new.

Write the Summary in **English**, even when the conversation with the user is in Japanese (per the global rule that PRs on OSS repos are written in English). Match the tone of recent PRs — inspect one with `gh pr view <number> --json body -q .body` first. Format:

```
`<name>` — a <monochrome|color> runner featuring <one-line visual description>. <N> frames at <W>×36.
```

- `<N>`: frame count from `unzip -l`
- `<W>×36`: width from `file runners/<name>/preview.png`

Create the PR by passing the filled-in template body via a heredoc:

```bash
gh pr create --title "Add the <name> runner" --body "$(cat <<'EOF'
<contents of .github/pull_request_template.md with the Type of Change box, Summary, and verified checklist items filled in>
EOF
)"
```

After creating, verify with `gh pr view <number> --json body -q .body` and return the PR URL to the user.

## Common mistakes

- **Skipping the PR template and writing a bespoke summary** → always `Read` the template first, then `gh pr create` with it.
- **Writing the Summary in Japanese** → English. The chat may be in Japanese; the PR body is not.
- **Ticking every checkbox without verifying** → verify first, then tick. If the asset breaks the spec, hand it back for fixes rather than loosening the checklist.
- **Breaking the manifest ordering** → keep `runners/manifest.json` alphabetical.
