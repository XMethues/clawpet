# Issue tracker: GitHub

Issues and PRDs for this repo live as GitHub issues. Use the `gh` CLI and infer the repository from the current git remote.

## Conventions

- Create: `gh issue create`
- Read: `gh issue view <number> --comments`
- List: `gh issue list`
- Comment: `gh issue comment <number>`
- Label: `gh issue edit <number> --add-label/--remove-label`
- Close: `gh issue close <number>`

## Pull requests as a triage surface

PRs as a request surface: no.

## Publishing

When a skill says “publish to the issue tracker,” create a GitHub issue. When it asks for the relevant ticket, read the issue and its comments.

## Dependencies and wayfinding

Use GitHub sub-issues and native issue dependencies when available. Fall back to task lists and `Blocked by:` lines only when the repository does not support those features.
