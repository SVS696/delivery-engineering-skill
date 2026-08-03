# Сохраняемое состояние delivery case

## Структура

```text
<case-root>/
  manifest.json
  status.md
  scope.md
  acceptance.md
  conformance.md
  evidence.md
  decisions.md
  lanes/
    backend.md
    frontend.md
    test.md
  reports/
    backend.md
    frontend.md
    test-design.md
    verification.md
    conformance.md
```

Создаются только нужные lane cards. Пустая FE/BE lane запрещена.

## Состояния lanes

Developer lane:

```text
planned -> ready -> in_progress -> implemented
```

Test lane:

```text
planned -> designing -> designed -> ready -> verifying -> verified
```

Из рабочего состояния допускаются `blocked` и `failed`; после изменения basis
или subject затронутый результат становится `stale`. Возврат в работу должен
содержать note и новый revision.

`test-design` завершается на `designed`. `accept` не создаёт dev lanes.

## Гейты

| Gate | Что доказывает |
|---|---|
| `authorization` | intent, lanes и write boundaries разрешены |
| `scope` | basis, REQ/AC, repositories и baseline сохранены |
| `codebase_conformance` | локальный style исследован до правок |
| `lane_reports` | каждая активная lane отдала contract report |
| `project_checks` | обязательные project commands выполнены |
| `independent_verification` | новый tester проверил subject |
| `project_conformance` | итоговый diff повторно сверен с локальным каноном |
| `traceability` | basis связан с diff, tests и evidence |

Gate имеет `pending | pass | fail | not_required | stale`, evidence, note и
subject fingerprint. `not_required` требует причины.

## Инвалидация

- Изменение `scope.md`/`acceptance.md` инвалидирует test-design и все следующие
  результаты.
- Изменение product diff после verification инвалидирует verification,
  conformance, project checks и traceability.
- Изменение testware после verification инвалидирует verification и traceability.
- Чат не восстанавливает pass: только повторный запуск на новом fingerprint.

## Final invariants

- `implement`: все dev lanes `implemented`, test `verified`, все применимые
  gates `pass`.
- `accept`: test `verified`, verification/conformance/trace gates `pass`.
- `test-design`: test `designed`; implementation/verification gates явно
  `not_required`, остальные применимые gates закрыты.
- `blocked`, `failed`, `partial`, `stale` никогда не округляются до `pass`.

