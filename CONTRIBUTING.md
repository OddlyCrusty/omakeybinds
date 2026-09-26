# Contributing

Thank you for improving OmaKeybinds. Bug reports and focused pull requests are
welcome.

## Before opening an issue

Search existing issues, update Omarchy and OmaKeybinds, then reproduce the
problem. Include your Omarchy version, the OmaKeybinds version from
`manifest.json`, relevant `omarchy-shell` log output, and exact reproduction
steps. Remove private commands or paths before posting logs.

## Development workflow

1. Fork and clone the repository.
2. Create a topic branch from `main`.
3. Keep changes narrowly scoped and add tests for Python behavior.
4. Run `./scripts/check.sh` on an Omarchy system.
5. Open a pull request describing behavior, safety impact, and manual testing.

Do not commit generated caches, local backups, personal keybindings, or state
files. Changes that write configuration must preserve backups, validation, and
rollback behavior.
