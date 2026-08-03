# Выжимка: risk-scoped secure delivery

ASVS используется как каталог проверяемых controls для web-приложений, а не как
автоматический scope каждого change.

## S01. Риск определяет глубину

**Источники:** `OWASP-ASVS-5.0.0`; `ISTQB-CTFL-4.0.1`, §5.2.

Сначала зафиксируй затронутые assets и trust boundaries: identity/session,
authorization, untrusted input/output, files, secrets, sensitive data, outbound
requests, audit trail. Затем выбери применимые controls и depth. Не объявляй
весь ASVS обязательным без risk/profile decision.

## S02. Secure construction и verification

**Источники:** `OWASP-ASVS-5.0.0`; `SWEBOK-4.0a`, Software Construction §1.5.

- Предпочитай проектные безопасные primitives и централизованные controls
  самодельной реализации.
- Проверяй deny path и object-level authorization, а не только happy-path login.
- Для untrusted data проверяй boundary validation, canonicalization и
  context-appropriate output handling.
- Не логируй secrets, credentials и чувствительные payload; error response не
  должен раскрывать внутреннюю структуру.
- Security test доказывает конкретный control на конкретной revision.

## S03. Versioned ASVS trace

**Источник:** `OWASP-ASVS-5.0.0`, requirement referencing guidance.

Если ASVS control применим, в матрице укажи:

```text
asset/threat -> v5.0.0-x.y.z -> implementation surface -> test/evidence -> result
```

Без версии идентификатор может изменить смысл между редакциями. `not-applicable`
требует обоснования. Проверка нескольких controls не означает ASVS conformance
продукта или уровня целиком.

## S04. Security findings и полномочия

Критичный риск опиши без эксплуатации сверх необходимого доказательства.
Не раскрывай секреты в report. Исправление, ротация credentials, изменение
доступов, deploy и уведомление внешних сторон требуют соответствующих
полномочий и отдельных gates.

