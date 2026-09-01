# Наблюдаемость модельных проходов

`agent-ledger.json` хранит стоимость и результат уже состоявшихся BE/FE/test
вызовов. Он не входит в role-context и не создаёт model call. Начиная со schema-3
delivery case независимые gates используют ledger как machine binding: PASS
обязан ссылаться на свежий completed tester run, exact subject и output hash.

## Нулевая стоимость процесса

- Не добавляй reviewer, synthesis или verification ради telemetry.
- Используй нативный supervisor текущего harness. Не запускай CLI-agent или
  polling wrapper только ради idle/hard timeout.
- Пока supervisor не сообщил новое событие, не poll чаще 30 секунд; для
  ожидаемо долгой операции используй более крупный wait slice.
- Один retry допустим лишь после подтверждённого transient/tool/transport сбоя
  с тем же assignment. `degraded` coverage и содержательная ошибка не являются
  retry-сигналом.
- Старые schema-1/2 cases сохраняют legacy-совместимость; schema-3+ case с
  отсутствующим или повреждённым ledger fail-closed. Legacy case не повышается
  неявно до schema-4: новый conformance episode требует отдельной миграции как
  минимум в schema-3 с валидным ledger.

## Запись вызова

```text
python3 {baseDir}/scripts/agent_ledger.py record-run \
  --case-root "<path>" --role delivery-tester --role-mode verification \
  --model "<model>" --subject-sha256 "<sha256>" \
  --duration-seconds 42 --retries 0 --status completed \
  --tool-calls 8 --poll-calls 1 --wait-seconds 30 \
  --reported-blocker 0 --reported-major 1 --reported-minor 0 \
  --lens acceptance@1 --prompt-artifact "acceptance.md" \
  --output-artifact "reports/tester.md"
```

`completed|degraded|failed|timed_out` описывает фактический исход. Для degraded
или failed добавь `--degraded-reason`. Неизвестные token counters оставь `null`.
Так же оставь `null` недоступные `tool_calls`, `poll_calls` и `wait_seconds`;
не восстанавливай их по памяти или косвенным признакам.

`--prompt-artifact` и `--output-artifact` ссылаются только на уже существующие
case-owned файлы. Ledger сохраняет ref и SHA-256 без второй копии корпуса. Raw
content не дублируй, если case contract его не требует.

Lens имеет форму `stable-id@version` и указывает на существующую project/role
surface. Он не создаёт дополнительного агента. Project profile может объявить
aliases и их точные contract inputs; версия меняется при смысловой смене правил.

## Finding yield

После уже обязательной coordinator/tester проверки классифицируй все reported
findings одним receipt:

```text
python3 {baseDir}/scripts/agent_ledger.py record-verification \
  --case-root "<path>" --run-id AR-0001 \
  --accepted 1 --rejected 0 --duplicate 0 --verified 1 \
  --evidence-ref "reports/tester.md"
```

`accepted|rejected|duplicate` должны покрыть все findings ровно один раз;
`verified` — подмножество accepted. Отсутствующий receipt означает
`unclassified`, а не нулевую полезность роли.

## Границы

- Ledger не передаётся BE/FE/tester и не влияет на их scope.
- Code review не подменяет runtime/AC verification.
- Повреждённый ledger отклоняет schema-3+ independent gate; self-check
  разработчика всё равно не превращается в независимое evidence.
