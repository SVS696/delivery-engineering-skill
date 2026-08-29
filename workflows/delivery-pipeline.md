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
   Одним read-only probe собери известные runtime/tool/dependency capabilities и
   названные project checks; неизвестное не устанавливай без разрешённого scope.
2. Для каждой surface найди инструкции, tool configs, аналогичный код и тесты;
   проследи реальный поток от входа до результата, callers и соседних
   потребителей изменяемого контракта.
   Независимые navigation probes объединяй в один batch/parallel round; второй
   round отвечает только на вопросы, возникшие из первого. Узкие previews служат
   навигации, но выбранные instructions/config/source для реализации читаются
   полностью. При отсутствии канонического config/contract сравни два реальных
   примера точной project-конвенции; при наличии канона дополнительный lookup не нужен.
3. Составь `conformance.md`: правило, источник, выбранный паттерн, конфликт.
4. Отдели устойчивый style от legacy/дефекта; спорный публичный выбор вынеси в
   decision, не маскируй «стилем проекта».
5. Если способность уже реализована, составь change-local inventory её owners,
   entrypoints, callers, routes/config/flags/data/tests/docs. Прими из handoff
   `evolve-in-place|replace-and-remove|staged-migration`. При отсутствии поля
   допустим только evidence-backed `evolve-in-place` у единственного текущего
   owner; новый/replacement owner, coexistence или конфликт требуют spec gap.

**Выход:** change-local codebase canon с evidence paths.

## Фаза 4. Slicing и test design

**Вход:** scope, conformance, закреплённый lane basis и разрешённые lanes.

1. Назначь lanes REQ/AC, worktree и непересекающиеся file boundaries.
2. Зафиксируй BE ↔ FE зависимости и test prerequisites.
3. Получи `context --lane test`, затем запусти tester `test-design` до claims о
   готовности; сохрани test matrix.
4. Не создавай BE/FE lane, если профиль запрещает её или влияние отсутствует.

### Process YAGNI

Перед новым lane, артефактом, check или review-pass назови текущий повторяемый
сбой/существенный риск. Сначала проверь deterministic/project check, текущего
semantic owner и уже назначенную tester surface. Только если они не закрывают
риск, вводи минимальный механизм с exit criteria и условием пересмотра. Это не
отменяет обязательную независимую verification; оно запрещает дублирующую
обвязку «для уверенности».

**Выход:** независимые lane cards и test model.

## Фаза 5. Implementation

**Вход:** lane cards, conformance, закреплённый basis каждой lane и test model.

1. Для каждой lane получи `delivery_case.py context --lane <lane>` и запусти
   разрешённые BE/FE-роли в свежих контекстах.
2. Параллель допустима только без общих файлов и при стабильном контракте.
3. Каждая роль до кода понимает реальный поток и проходит лестницу реализации:
   не строить → reuse проекта → stdlib → native platform/runtime → принятая
   dependency → прямой код у текущего владельца → минимальный новый механизм.
4. Исправляй `root_owner` общей причины один раз, а не размножай симптоматические
   исключения по callers. Минимальный diff в неверном месте не считается простым.
5. Реализуй принятый `implementation_transition`. В каждый момент один owner
   authoritative; compatibility adapter только переводит контракт и не получает
   новых правил. `replace-and-remove` удаляет superseded runtime paths в этой
   поставке. `staged-migration` сохраняет только перечисленный residue текущей
   стадии с retirement trigger и rollback boundary.
6. Сохраняй protected floor: подтверждённое поведение, trust boundaries,
   безопасность/данные, accessibility, совместимость, наблюдаемость и доказанную
   extension seam. Простота не равна одноразовому hardcode.
7. Добавь релевантные risk-based tests; для новой нетривиальной логики оставь
   хотя бы один минимальный runnable check, затем запусти project checks.
   Named task/project check определяет `local-green` только вместе с применимыми
   delivery gates. Если тот же check дважды падает при неизменной гипотезе,
   смени причину или подход до следующей правки, а не исправляй очередной симптом.
8. Координатор проверяет file boundaries, объединяет результат и помечает lane
   `implemented`, но не `verified`.
9. После каждого уже состоявшегося role call запиши его outcome в
   `agent-ledger.json` по `references/agent-observability.md`; запись не запускает
   новый вызов и ledger не передаётся следующей роли.

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
   нового tester `verification`. До вызова выполни `begin-verification` с exact
   subject и передай полученный SHA-256 в agent ledger.
2. Проверяй persisted/live result; preview, mergeability и HTTP 200 сами по себе
   недостаточны.
3. Классифицируй defect/spec gap/environment blocker/coverage gap/baseline.
4. Для replacement/cutover проверь наблюдаемую недостижимость superseded пути и
   сохранность только разрешённого compatibility residue; HTTP 404 без проверки
   callers/config/flags/data flow не доказывает removal.
5. После исправления повтори defect и regression neighborhood новым запуском.
6. После штатной классификации findings добавь verification receipt; не запускай
   отдельный review ради заполнения метрики.
7. Initial verification плюс два correction passes — предел одной source
   revision. Затем объедини все accepted spec gaps в один `record-feedback`
   batch; не возвращай их в Vigers по одному.

**Выход:** `verified`, `failed`, `partial` или `blocked` с evidence.

## Фаза 8. Project conformance и quality gates

**Вход:** итоговый diff и verification report.

1. В свежем tester `conformance` пройди матрицу style/architecture/API/data/UI.
2. Запусти обязательные lint/build/test/static/security/visual checks профиля.
3. Сверь `REQ/AC → diff → tests → evidence` и отсутствие scope creep.
4. Сверь implementation-transition report с diff/search/runtime evidence:
   authoritative owner единственный, legacy не получил новые правила,
   superseded routes/config/flags/tests/docs удалены либо точно ограничены
   принятой стадией и retirement trigger.
5. Если после review изменился subject, затронутые gates становятся stale.
6. Свяжи conformance PASS с отдельным свежим tester run и exact output artifact.
7. Выполни `delivery_case.py validate --final`; команда сначала сохраняет
   effective stale state.

**Выход:** локальная поставка готова к следующему внешнему gate.

## Фаза 9. Handoff

**Вход:** final case PASS.

1. Commit/MR выполняй только если это входит в запрос; после записи сделай
   read-back.
2. Не self-merge; merge, deploy и post-deploy verification остаются отдельными.
3. Верни covered IDs, revisions, commands/evidence, gaps и точный next gate.
4. Определи достигнутый green-level по `references/case-state.md`. Read-back
   разрешённой внешней записи является частью результата, а после доказанного
   terminal level не запускай дополнительный review/check без нового evidence.

**Выход:** фактическое состояние без смешения implementation и delivery.
