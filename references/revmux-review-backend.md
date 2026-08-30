# Opt-in backend revmux для Delivery review

`revmux` — заменяемый semantic backend существующего tester-режима
`conformance`, а не новая роль и не дополнительный gate. Backend по умолчанию
остаётся `native`. Выбор `review_backend: revmux` должен быть явным в assignment
или case-local решении и действует только на `project_conformance`.

## Контракт reviewer-driver

При `review_backend: revmux` свежий `delivery-tester` в режиме `conformance`:

1. фиксирует `revmux --version`, exact diff/subject SHA-256, task/run, профиль и
   project inputs;
2. запускает один `comprehensive` для initial review либо один `final` после
   correction batch с `--config-dir <delivery-engineering-root>/revmux`;
3. проверяет JSON report/manifest, completeness sources и отсутствие degraded
   или unverified critical/major;
4. возвращает immutable output artifact существующего tester run, включая
   revmux report hashes и adoption telemetry.

Этот tester является driver: он не добавляет собственный model-review, не
перезапускает native conformance и не продолжает review loop. Revmux read-only и
не исправляет код. Existing schema-3 binding к completed tester run и exact
output artifact сохраняется без нового gate.

## Opt-in dependency

Native conformance не зависит от revmux. Выбранный `review_backend: revmux`
fail-closed требует бинарь `revmux` в `PATH` и установленный Codex skill revmux
из той же совместимой ревизии. Текущий compatibility pin:
`33ede7aaf632cebbde08f2dd53ffa06c4722d81b`; ожидаемый `revmux --version`
содержит `33ede7a`. `revmux_review.py prepare` проверяет бинарь и записывает его
resolved path, version и pin в immutable context. Отсутствующая либо иная
ревизия не запускает ни revmux, ни тихий native fallback.

Skill-local профили сохраняют стандартные имена и severity semantics revmux,
но заменяют recursive Codex slot отдельным Claude subprocess. Panel separation
остаётся, а Codex-hosted reviewer не вызывает Codex CLI рекурсивно.

Одновременный native conformance и revmux на одном gate запрещены. Исключение —
заранее помеченный `comparison_measurement`; два результата измеряются отдельно
и не превращаются в два последовательных барьера.

## Материализация exact review context

Revmux не выбирает объект и baseline самостоятельно. После
`delivery_case.py context` сохрани полный JSON assignment, вызови `revmux new`
и передай возвращённые paths команде:

```text
python3 <delivery-root>/scripts/revmux_review.py prepare \
  --assignment <assignment.json> --case-root <case-root> \
  --profile-source <resolved-delivery-profile.md> \
  --worktree <repository-worktree> \
  --base-ref <exact-base-commit> --head-ref <exact-head-commit> \
  --repository-instruction <nearest-AGENTS-or-CLAUDE.md> \
  --scope-output <revmux-new.scope> --goal-output <revmux-new.goal> \
  --profile-output <revmux-new.profile> --context-dir <revmux-new.context>
```

`prepare` fail-closed проверяет conformance assignment, phase/profile и ровно
`covered_gates: [project_conformance]`; разрешает base/head только как реальные
commits одного Git worktree; строит и архивирует exact binary diff; фиксирует
base/head SHA, changed files, shortstat и SHA-256 diff. В
`context/delivery-assignment.json` попадает точное сравнение:

- target — архивированный diff `base_sha..head_sha`;
- product baseline — approved `scope.md`, `acceptance.md`, `conformance.md`,
  lane basis, decisions, evidence и developer reports, если assignment их
  разрешил;
- engineering baseline — frozen Delivery profile, reviewer contract и
  ближайшие явно переданные repository instructions;
- question — выполняет ли этот diff утверждённый scope/AC, сохраняет ли
  authoritative implementation path и не вносит ли regression или scope creep.

Каждый baseline имеет абсолютный path и SHA-256. Файл, отсутствующий в
assignment либо `--repository-instruction`, не становится источником review
просто из-за наличия в worktree. `profile.md` копируется byte-for-byte.
Запускай revmux с `--workdir <repository-worktree>` и
`--config-dir <delivery-root>/revmux`.

## Ограниченный review-цикл

1. Готовый Delivery diff прошёл implementation self-checks, project tests/CI и
   отдельный tester `verification`, включая live/persisted verification, когда
   она применима.
2. Tester-driver запускает один `comprehensive` review.
3. Координатор подтверждает findings. Только confirmed/refined
   `critical|major` образуют один consolidated fix batch. `minor`, immaterial,
   pre-existing и open questions не запускают correction round.
4. После исправления и повторных affected tests/verification свежий
   tester-driver запускает один профиль `final` на новом exact subject.
5. Любой оставшийся/new critical/major завершает review case как failed либо
   user-decision; второй fix/review cycle автоматически не открывается.

`scripts/revmux_review.py` материализует context, создаёт round evidence,
сводит initial/final pair и агрегирует 3–5 adoption receipts. Метрики: human
active time, revmux elapsed time,
model calls, tokens, confirmed critical/major, correction rounds, новые и
повторившиеся gating areas. Model calls включают reviewer-driver и все revmux
agents/stages/retries. Решение о permanent enablement всегда ручное.
Revmux tokens берутся из report, driver tokens — из completed agent ledger;
нулём неизвестное не заменяется. Метка adoption относится только к решению о
смене default после 3–5 кейсов: отдельного временного типа Delivery case,
assignment или профиля нет.

## Сохранённые границы

Revmux не заменяет implementation, test design/automation, CI, lint/build/test,
independent tester `verification`, live acceptance, persisted-result checks,
traceability, merge/deploy/post-deploy/read-back gates. Merge, deploy и status
transitions требуют отдельного разрешения.

Process Auditor не является частью этого backend. Интеграция не включает hooks,
не запускает auditor и не удаляет его skill.
