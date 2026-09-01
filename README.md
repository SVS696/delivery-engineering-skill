# Delivery Engineering

Переносимый мультиагентный workflow для реализации утверждённых требований,
test-design и независимой проверки готового изменения.

Skill намеренно отделён от requirements engineering. Он содержит три
опциональные роли:

- `delivery-backend`;
- `delivery-frontend`;
- `delivery-tester` в режимах design, automation, verification и conformance.

Backend/frontend доступны только через приватный профиль проекта и явный
implementation scope. Generic profile включает только test capability.

Реализация нативно проходит лестницу `не строить → reuse проекта → stdlib →
native platform → принятая dependency → прямой код → минимальный новый
механизм`. Роль исправляет корневого владельца причины, сохраняет protected
floor безопасности, данных, accessibility, совместимости и доказанной
расширяемости. Отдельный simplicity-reviewer для этого не создаётся.

## Project-first conformance

Перед изменением роль изучает ближайшие инструкции, formatter/linter/compiler
configs, несколько аналогичных участков кода и tests. Результат сохраняется в
change-local conformance matrix. Случайный legacy-файл не становится стилем, а
конфликт с архитектурным каноном или security rule не разрешается молча.

Проектная конфигурация хранится отдельно:

```text
<project-root>/.delivery-engineering/profile.md
```

Публичный пакет не содержит названий, путей, архитектуры и внутренних правил
конкретных проектов.

## Установка

```bash
git clone https://github.com/SVS696/delivery-engineering-skill.git ~/.codex/skills/delivery-engineering
python3 ~/.codex/skills/delivery-engineering/scripts/install.py --dry-run
python3 ~/.codex/skills/delivery-engineering/scripts/install.py
python3 ~/.codex/skills/delivery-engineering/scripts/install.py --check
```

Installer подключает skill в Codex/Claude discovery и три именованных агента.
Он выполняет полный preflight, не перетирает существующие targets и повторно
запускается идемпотентно.

### Опциональная зависимость revmux

Native conformance работает без внешней зависимости. Явный
`review_backend: revmux` требует бинарь и caller-интеграцию активного
reviewer runtime из
[umputun/revmux](https://github.com/umputun/revmux) из совместимой ревизии
`33ede7aaf632cebbde08f2dd53ffa06c4722d81b`. Это compatibility pin текущей
интеграции, а не временный тип Delivery case. Для Codex нужен установленный
skill `revmux` из `plugins/codex/skills/revmux`; для Claude Code — включённый
plugin `revmux@revmux` версии `0.4.3`, содержащий skill `revmux:revmux`; Claude
reviewer предзагружает его через agent frontmatter и явно вызывает через
`Skill` tool. Профили revmux также запускают Claude subprocesses, поэтому им
нужен доступный и аутентифицированный `claude` CLI.

`scripts/revmux_review.py prepare` fail-closed проверяет `revmux --version`,
архивирует exact diff и сохраняет dependency version в review context.
Reviewer adapter отдельно требует caller skill/plugin своего runtime;
отсутствие любого компонента или иная ревизия останавливает revmux assignment
без тихого fallback на native. Один локальный checkout не считается
установленной зависимостью.

## Профиль проекта

```bash
mkdir -p .delivery-engineering
cp ~/.codex/skills/delivery-engineering/profiles/project-profile-template.md \
  .delivery-engineering/profile.md
python3 ~/.codex/skills/delivery-engineering/scripts/delivery_pipeline.py \
  validate --project-root "$PWD"
```

Capabilities перечисляются явно: `backend`, `frontend`, `test`. Test обязателен
для независимого verification; отсутствие capability запрещает lane.

## Использование

```text
Используй delivery-engineering. Реализуй REQ-12 и AC-12.1 в указанном backend
репозитории, сохрани стиль ближайшего модуля и передай результат свежему tester.
Не создавай MR и не деплой.
```

Case-state хранит lane statuses, gates, revisions, fingerprints, отдельную
инженерную базу каждой роли и conformance convergence episode. Initial review,
один finding-bound correction batch и final являются разрешёнными переходами,
а не свободно повторяемыми prompts, поэтому работу можно продолжить в новых
контекстах без пересказа чата и без повторного полного цикла. Failed targeted
recheck, scope expansion и drift frozen subject останавливаются в
`user-decision`; новый episode требует material evidence и affected rechecks.

## Skill-native инженерная база

Источники не сваливаются в prompt целиком. Машинная карта выбирает bounded
выжимку по поверхности изменения:

```bash
python3 scripts/delivery_context.py route --task "изменить HTTP API"
python3 scripts/delivery_context.py materialize \
  --assign backend=backend-http --assign test=test-design \
  --write .delivery-engineering/cases/example

python3 scripts/delivery_case.py init \
  --case-root .delivery-engineering/cases/example --case-id example \
  --intent implement --profile-id project --lane backend --lane test
```

`materialize` создаёт общий sidecar `engineering-context.json` и отдельные
`basis/<lane>.md`. `init` проверяет их по текущим выжимкам и привязывает hashes
к manifest. Команда `delivery_case.py context --lane` выдаёт агенту только basis
его lane; например, tester не получает HTTP-корпус backend.

Реестр охватывает SWEBOK 4.0a, Software Engineering at Google, ISTQB CTFL
4.0.1, публичный обзор ISO/IEC/IEEE 29119, RFC 9110, WCAG 2.2, Testing Library,
OWASP ASVS 5.0.0 и официальные OpenAI prompt guides. В репозитории находятся
собственные переработанные карты и чек-листы, а не копии стандартов и книг.

## Проверка

```bash
python3 scripts/delivery_pipeline.py validate
python3 scripts/delivery_context.py validate
python3 scripts/prompt_audit.py validate --skill-root .
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s scripts -p 'test_*.py'
```

Validator проверяет профили, role contracts для Codex/Claude, workflow,
литературные routes, prompt boundaries, отсутствие приватных project markers и
жёстких домашних путей.

## Состав

```text
.
├── SKILL.md
├── agents/{contracts,codex,claude}
├── profiles
├── references
├── scripts
└── workflows/delivery-pipeline.md
```
