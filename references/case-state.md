# Сохраняемое состояние delivery case

## Структура

```text
<case-root>/
  engineering-context.json
  basis/
    backend.md
    frontend.md
    test.md
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

До `init` case-root содержит только `engineering-context.json` и basis активных
lanes, созданные `delivery_context.py materialize`. Новый manifest schema v2
связывает общий fingerprint, route IDs и content hashes. `init` проверяет
snapshot по текущим skill-native выжимкам; дальнейшая `validate` проверяет его
неизменность относительно manifest. Ручное изменение basis или sidecar делает
case невалидным. `--allow-unrecorded-engineering-context` существует только для
явной миграции legacy case и не используется новым workflow.

`delivery_case.py context --lane <lane>` возвращает точный allowed-input bundle
с `engineering-context.json` и только `basis/<lane>.md`. Basis другой lane и
история родительского диалога исключены.

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
В schema-3 `independent_verification` и `project_conformance` дополнительно
связаны с конкретным completed `delivery-tester` run нужного role mode, тем же
subject SHA-256 и точным immutable output artifact.
При `review_backend: revmux` binding не меняется: tester `conformance` является
driver одного revmux round, а его output содержит hashes report/manifest.
Собственный tester model-review в этот run запрещён. Final gate связывается
только с final driver run; initial report хранится как adoption evidence.

## Инвалидация

- Изменение `scope.md`/`acceptance.md` инвалидирует test-design и все следующие
  результаты.
- Изменение product diff после verification инвалидирует verification,
  conformance, project checks и traceability.
- Изменение testware после verification инвалидирует verification и traceability.
- Чат не восстанавливает pass: только повторный запуск на новом fingerprint.
- `show`, `context` и `validate` сначала reconciliруют fingerprints: изменённый
  PASS сохраняется как `stale` в manifest/status, а не остаётся зелёным текстом.

## Бюджет verification и обратная связь

`begin-verification` фиксирует exact subject и увеличивает счётчик текущей
source revision. Допустимы три полных assignment: initial и два correction.
Четвёртый блокируется. Spec gaps из исчерпанного или явно остановленного цикла
передаются одной командой `record-feedback --gap ... --evidence ...`; она
создаёт один immutable `feedback-batches/FB-*.json` с `batch_complete=true` и
блокирует дальнейшее verification до новой Vigers source revision.
После того как Vigers экспортировал более новую revision, команда
`migrate-source-handoff` архивирует прежний handoff, связывает новый, помечает
зависимые PASS как `stale` и сбрасывает verification budget ровно для новой
revision.

## Final invariants

- `implement`: все dev lanes `implemented`, test `verified`, все применимые
  gates `pass`.
- `accept`: test `verified`, verification/conformance/trace gates `pass`.
- `test-design`: test `designed`; implementation/verification gates явно
  `not_required`, остальные применимые gates закрыты.
- `blocked`, `failed`, `partial`, `stale` никогда не округляются до `pass`.

## Terminal green

Green определяется границей текущего запроса, а не одной успешной командой:

- `local-green` — локальный diff/артефакт, named project checks и применимые
  delivery gates актуальны; открытых defects, меняющих результат, нет;
- `projection-green` — разрешённая внешняя проекция или MR/задача обновлена,
  прочитана обратно и совпадает с локальным result revision;
- `handoff-green` — требуемая передача следующему владельцу/гейту зафиксирована
  вместе с evidence и точным состоянием результата;
- `final-green` — доказан terminal state текущего запроса, включая merge/deploy/
  post-deploy только когда они были отдельно разрешены и фактически проверены.

Это human-facing proof labels, а не новые lane/gate statuses и не обход
существующей state machine.

Уровни не дают новых полномочий. Если запрос заканчивается на `local-green`,
внешняя запись не выполняется. Если он требует projection/handoff, read-back
является частью green, а не дополнительным проходом. После достигнутого уровня
новый review, повторное чтение или check запускаются только при новом evidence,
изменившемся subject либо более дальней явно разрешённой границе.
