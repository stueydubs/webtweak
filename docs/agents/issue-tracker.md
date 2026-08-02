# Issue tracker: GitHub

Issues and PRDs for this repo live as GitHub issues on `stueydubs/webtweak`. Use the `gh` CLI for all operations.

## Conventions

- **Create an issue**: `gh issue create --title "..." --body "..."`. Use `--body-file` for anything multi-line; heredocs into a file are more reliable than inline quoting.
- **Read an issue**: `gh issue view <number> --comments`.
- **List issues**: `gh issue list --state open --json number,title,body,labels,comments --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body]}]'` with appropriate `--label` and `--state` filters.
- **Comment on an issue**: `gh issue comment <number> --body "..."`
- **Apply / remove labels**: `gh issue edit <number> --add-label "..."` / `--remove-label "..."`
- **Close**: `gh issue close <number> --comment "..."`

Infer the repo from `git remote -v` - `gh` does this automatically when run inside a clone.

## Pull requests as a triage surface

**PRs as a request surface: no.** _(Set to `yes` if this repo treats external PRs as feature requests; `/triage` reads this flag.)_

When set to `yes`, PRs run through the same labels and states as issues, using the `gh pr` equivalents:

- **Read a PR**: `gh pr view <number> --comments` and `gh pr diff <number>` for the diff.
- **List external PRs for triage**: `gh pr list --state open --json number,title,body,labels,author,authorAssociation,comments` then keep only `authorAssociation` of `CONTRIBUTOR`, `FIRST_TIME_CONTRIBUTOR`, or `NONE` (drop `OWNER`/`MEMBER`/`COLLABORATOR`).
- **Comment / label / close**: `gh pr comment`, `gh pr edit --add-label`/`--remove-label`, `gh pr close`.

GitHub shares one number space across issues and PRs, so a bare `#42` may be either - resolve with `gh pr view 42` and fall back to `gh issue view 42`.

## When a skill says "publish to the issue tracker"

Create a GitHub issue.

## When a skill says "fetch the relevant ticket"

Run `gh issue view <number> --comments`.

## Wayfinding operations

Used by `/wayfinder`. The **map** is a single issue with **child** issues as tickets.

These commands were verified against this repo on 2026-08-02 with `gh` 2.97.0, which has **native** flags for sub-issues and dependencies. The older `gh api` route still works and is kept below as a fallback for older `gh` versions.

- **Map**: a single issue labelled `wayfinder:map`, holding the Destination / Notes / Decisions-so-far / Fog body.

  ```bash
  gh issue create --label wayfinder:map --title "Map: ..." --body-file map.md
  ```

- **Child ticket**: an issue linked to the map as a GitHub sub-issue. Labels: `wayfinder:<type>` (`research` / `prototype` / `grilling` / `task`).

  ```bash
  gh issue create --label wayfinder:grilling --title "..." --body-file ticket.md
  gh issue edit <map> --add-sub-issue <child>        # or several: 2,3,4
  gh issue edit <child> --parent <map>               # equivalent, from the other side
  ```

  Fallback where `--add-sub-issue` is unavailable: add the child to a task list in the map body and put `Part of #<map>` at the top of the child body.

- **Blocking**: GitHub's native issue dependencies, which render in the GitHub UI so the frontier is visible without opening the map.

  ```bash
  gh issue edit <child> --add-blocked-by <blocker>   # or several: 4,7
  gh issue edit <child> --add-blocking <blocked>     # the same edge, stated forwards
  ```

  Fallback for older `gh`: `gh api --method POST repos/stueydubs/webtweak/issues/<child>/dependencies/blocked_by -F issue_id=<blocker-db-id>`, where `<blocker-db-id>` is the blocker's numeric **database id** (`gh api repos/stueydubs/webtweak/issues/<n> --jq .id`, _not_ the `#number` or `node_id`). Failing that, a `Blocked by: #<n>, #<n>` line at the top of the child body.

  A ticket is unblocked when every ticket blocking it is closed.

- **Frontier query**: the map's open children with no open blocker and no assignee. Note that `parent` and `blockedBy` come back as objects, not arrays, so the `jq` reads `.parent.number` and `.blockedBy.nodes`.

  ```bash
  for n in $(gh issue list --state open --json number --jq '.[].number'); do
    gh issue view $n --json number,title,parent,blockedBy,assignees,labels \
      --jq 'select((.blockedBy.nodes|length)==0 and (.assignees|length)==0)
            | "#\(.number)  [\(.labels[0].name)]  \(.title)"'
  done
  ```

  First in map order wins.

- **Claim**: `gh issue edit <n> --add-assignee @me` - the session's first write, before any work, so concurrent sessions skip it.

- **Resolve**: `gh issue comment <n> --body "<answer>"`, then `gh issue close <n>`, then append a context pointer (one-line gist plus link) to the map's Decisions-so-far. Update the map body with `gh issue edit <map> --body-file <edited-map.md>`.

- **Verify, do not assume.** `gh issue edit` exits 0 on success but the wiring is worth reading back, because a silently unwired ticket is invisible until the frontier query returns the wrong answer. Check with `gh issue view <n> --json parent,blockedBy`.
