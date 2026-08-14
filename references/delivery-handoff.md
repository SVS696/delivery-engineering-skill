# Контракт delivery handoff

## Вход в case

```yaml
case_id: stable-id
intent: implement | accept | test-design
profile_id: resolved-project-profile
source_revision: immutable-or-versioned-reference
target_repositories:
  - root: resolved-path
    baseline: branch-and-sha-or-dirty-fingerprint
requirements: [REQ-...]
acceptance: [AC-...]
open_decisions: []
component_impact: [backend, frontend, data, integration, ui]
allowed_actions: [local-edit, test]
forbidden_actions: [merge, deploy, external-status]
engineering_context:
  fingerprint: immutable-hash
  lane_basis: {backend: basis/backend.md, test: basis/test.md}
```

Если ID отсутствуют, используй стабильные локальные IDs внутри case. Нельзя
передавать роли только пересказ чата.

## Lane card

Каждая `lanes/<name>.md` содержит:

- role и mode;
- assigned REQ/AC;
- target root, baseline и allowed file scope;
- зависимости и входные contracts;
- выбранные literature rule IDs;
- `engineering-context.json` и только собственный `basis/<lane>.md` с hash из
  manifest;
- project conformance sources;
- required checks и report path;
- явные запреты.

## Codebase conformance

`conformance.md` хранит change-local матрицу:

```text
surface | rule | precedence | evidence path/config | applied decision | status
```

Минимальные surfaces по применимости: module layout, naming/types, public API,
data/schema, errors/logging, dependency pattern, UI/design system, tests.
Путь к одному случайному примеру недостаточен; укажи инструкцию/config или
несколько согласованных аналогов.

## Developer report

```yaml
lane: backend | frontend
status: implemented | blocked
baseline: exact-revision
result: worktree-or-commit
covered_ids: []
changed_files: []
style_evidence:
  - surface: naming
    sources: []
    applied: concise-decision
simplicity:
  root_owner: semantic-owner-path-or-symbol
  chosen_rung: existing-behavior | existing-project | stdlib | native | dependency | direct | minimal-new
  protected_floor: preserved | finding
  ceiling: optional-known-limit
  revisit_trigger: optional-measurable-event
  upgrade_path: optional-next-mechanism
checks:
  - command: exact-command
    cwd: repo-root
    result: pass | fail | partial
    evidence: path-or-summary
gaps: []
next_gate: independent-verification
```

Автор не ставит `verified`.

`ceiling`, `revisit_trigger` и `upgrade_path` появляются только вместе и только
для сознательного компромисса. Обычная прямая реализация не создаёт debt-запись.

## Tester report

```yaml
mode: test-design | test-automation | verification | conformance
status: designed | verified | failed | partial | blocked
basis_revision: exact-source
subject_revision: exact-result
coverage:
  - basis_id: AC-...
    checks: []
    result: pass | fail | not-run
findings:
  - kind: defect | spec-gap | environment-blocker | coverage-gap | baseline-failure
    severity: project-scale
    evidence: reproducible-fact
conformance: []
residual_risks: []
next_gate: explicit-step
```

Tester не меняет product code в `verification`/`conformance`.

## Итог координатора

Итог содержит source/result revisions, covered IDs, lane states, project gates,
evidence, gaps, residual risks и next external gate. Термины `implemented`,
`verified`, `committed`, `merged`, `deployed` используются раздельно.
