# Delivery pipeline

## Фаза 1. Authorization и профиль

**Вход:** запрос на `implement`, `accept` или `test-design`.

1. Разреши ближайший профиль через `delivery_pipeline.py`.
2. Прочитай project instructions каждого целевого репозитория.
3. Сопоставь intent, capabilities и фактически разрешённые записи.
4. Отдели локальный diff от commit/MR/merge/deploy/external status.

**Выход:** разрешённые intent и lanes; запреты названы явно.

## Фаза 2. Intake и case-state

**Вход:** утверждённый handoff либо источник с criteria.

1. Проверь revision, scope, REQ/AC, decisions и component impact.
2. Выбери один, максимум два маршрута инженерной базы для каждой BE/FE lane и
   максимум три для test, затем выполни `delivery_context.py materialize`.
3. Инициализируй case с тем же набором lanes; `init` обязан связать
   `engineering-context.json` и hashes каждого `basis/<lane>.md` с manifest.
4. Запиши `scope.md`, `acceptance.md`, baseline и source refs.
5. Если обязательный смысл отсутствует, верни spec gap; не додумывай контракт.

**Выход:** case продолжается без истории чата.

## Фаза 3. Codebase reconnaissance

**Вход:** target repo, profile и затронутые surfaces.

1. Зафиксируй dirty baseline и чужие изменения.
2. Для каждой surface найди инструкции, tool configs, аналогичный код и тесты.
3. Составь `conformance.md`: правило, источник, выбранный паттерн, конфликт.
4. Отдели устойчивый style от legacy/дефекта; спорный публичный выбор вынеси в
   decision, не маскируй «стилем проекта».

**Выход:** change-local codebase canon с evidence paths.

## Фаза 4. Slicing и test design

**Вход:** scope, conformance, закреплённый lane basis и разрешённые lanes.

1. Назначь lanes REQ/AC, worktree и непересекающиеся file boundaries.
2. Зафиксируй BE ↔ FE зависимости и test prerequisites.
3. Получи `context --lane test`, затем запусти tester `test-design` до claims о
   готовности; сохрани test matrix.
4. Не создавай BE/FE lane, если профиль запрещает её или влияние отсутствует.

**Выход:** независимые lane cards и test model.

## Фаза 5. Implementation

**Вход:** lane cards, conformance, закреплённый basis каждой lane и test model.

1. Для каждой lane получи `delivery_case.py context --lane <lane>` и запусти
   разрешённые BE/FE-роли в свежих контекстах.
2. Параллель допустима только без общих файлов и при стабильном контракте.
3. Каждая роль делает минимальный diff, следует conformance matrix, добавляет
   релевантные тесты и запускает project checks.
4. Координатор проверяет file boundaries, объединяет результат и помечает lane
   `implemented`, но не `verified`.

**Выход:** продуктовый diff и developer reports.

## Фаза 6. Test automation

**Вход:** test model и отдельный test-file scope.

1. При необходимости запусти tester в `test-automation`.
2. Tester не правит product code и не меняет expected result под реализацию.
3. Сохрани test diff отдельно; после записи используй новый verification run.

**Выход:** testware отделён от авторской реализации.

## Фаза 7. Independent verification

**Вход:** requirements basis, закреплённый `basis/test.md`, result revision,
код/CI/стенд и developer reports.

1. После готовности dev lanes заново получи `context --lane test` и запусти
   нового tester `verification`.
2. Проверяй persisted/live result; preview, mergeability и HTTP 200 сами по себе
   недостаточны.
3. Классифицируй defect/spec gap/environment blocker/coverage gap/baseline.
4. После исправления повтори defect и regression neighborhood новым запуском.

**Выход:** `verified`, `failed`, `partial` или `blocked` с evidence.

## Фаза 8. Project conformance и quality gates

**Вход:** итоговый diff и verification report.

1. В свежем tester `conformance` пройди матрицу style/architecture/API/data/UI.
2. Запусти обязательные lint/build/test/static/security/visual checks профиля.
3. Сверь `REQ/AC → diff → tests → evidence` и отсутствие scope creep.
4. Если после review изменился subject, затронутые gates становятся stale.
5. Выполни `delivery_case.py validate --final`.

**Выход:** локальная поставка готова к следующему внешнему gate.

## Фаза 9. Handoff

**Вход:** final case PASS.

1. Commit/MR выполняй только если это входит в запрос; после записи сделай
   read-back.
2. Не self-merge; merge, deploy и post-deploy verification остаются отдельными.
3. Верни covered IDs, revisions, commands/evidence, gaps и точный next gate.

**Выход:** фактическое состояние без смешения implementation и delivery.
