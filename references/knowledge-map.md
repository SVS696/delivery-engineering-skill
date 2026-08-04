# Карта знаний Delivery Engineering

Выбери на каждую активную lane один основной маршрут. Для BE/FE допустим один
дополнительный маршрут; для test — два, когда проверяются независимые BE/FE или
security surfaces. Материализуй только указанные sections; общая литература не
перекрывает профиль проекта.

<!-- delivery-engineering:routes -->
```json
{
  "version": 1,
  "default_route": "core-change",
  "routes": [
    {
      "id": "core-change",
      "when": "Любое изменение продукта",
      "lanes": ["backend", "frontend", "test"],
      "signals": [],
      "distilled": [
        {"file": "references/native-engineering.md", "heading": "E01. Минимальный проверяемый change"},
        {"file": "references/native-engineering.md", "heading": "E02. Construction for verification"}
      ]
    },
    {
      "id": "codebase-conformance",
      "when": "Нужно соответствовать стилю, структуре и соглашениям существующей кодовой базы",
      "lanes": ["backend", "frontend", "test"],
      "signals": ["стиль кодовой базы", "именование", "соглашения", "паттерн проекта", "project conformance"],
      "distilled": [
        {"file": "references/native-engineering.md", "heading": "E03. Иерархия локального канона"},
        {"file": "references/native-engineering.md", "heading": "E04. Разведка соседнего кода"},
        {"file": "references/native-engineering.md", "heading": "E05. Conformance matrix"}
      ]
    },
    {
      "id": "backend-http",
      "when": "Меняется HTTP API или backend-контракт",
      "lanes": ["backend", "test"],
      "signals": ["backend", "api", "http", "endpoint", "rest", "status code"],
      "distilled": [
        {"file": "references/native-backend.md", "heading": "B01. Ресурс, метод и наблюдаемая семантика"},
        {"file": "references/native-backend.md", "heading": "B02. Ответы, ошибки и representations"},
        {"file": "references/native-backend.md", "heading": "B03. Совместимость и повтор запроса"}
      ]
    },
    {
      "id": "frontend-behavior",
      "when": "Меняется UI, состояние экрана или пользовательский сценарий",
      "lanes": ["frontend", "test"],
      "signals": ["frontend", "ui", "компонент", "экран", "браузер", "пользовательский сценарий"],
      "distilled": [
        {"file": "references/native-frontend.md", "heading": "F01. Наблюдаемое поведение вместо внутренностей"},
        {"file": "references/native-frontend.md", "heading": "F02. Состояния пользовательского потока"},
        {"file": "references/native-frontend.md", "heading": "F03. Визуальное и адаптивное evidence"}
      ]
    },
    {
      "id": "accessibility",
      "when": "Меняется доступность интерфейса или нужен WCAG-scope",
      "lanes": ["frontend", "test"],
      "signals": ["accessibility", "wcag", "доступность", "клавиатура", "screen reader", "aria"],
      "distilled": [
        {"file": "references/native-frontend.md", "heading": "F04. Accessibility по применимым критериям"},
        {"file": "references/native-frontend.md", "heading": "F05. Граница conformance claim"}
      ]
    },
    {
      "id": "test-design",
      "when": "Нужно спроектировать, выполнить или завершить тестирование",
      "lanes": ["test"],
      "signals": ["тест", "приемка", "verification", "test design", "coverage", "регресс"],
      "distilled": [
        {"file": "references/native-testing.md", "heading": "T01. Test basis и test conditions"},
        {"file": "references/native-testing.md", "heading": "T02. Выбор техник и уровней"},
        {"file": "references/native-testing.md", "heading": "T03. Traceability и coverage"},
        {"file": "references/native-testing.md", "heading": "T04. Независимость и evidence"},
        {"file": "references/native-testing.md", "heading": "T05. Completion без ложной полноты"}
      ]
    },
    {
      "id": "risk-security",
      "when": "Изменение затрагивает trust boundary, auth, ввод, секреты или чувствительные данные",
      "lanes": ["backend", "frontend", "test"],
      "signals": ["security", "безопасность", "auth", "авторизация", "инъекция", "секрет", "персональные данные"],
      "distilled": [
        {"file": "references/native-security.md", "heading": "S01. Риск определяет глубину"},
        {"file": "references/native-security.md", "heading": "S02. Secure construction и verification"},
        {"file": "references/native-security.md", "heading": "S03. Versioned ASVS trace"}
      ]
    },
    {
      "id": "review-static-analysis",
      "when": "Нужны project checks, code review или статический анализ",
      "lanes": ["backend", "frontend", "test"],
      "signals": ["code review", "static analysis", "lint", "formatter", "анализатор", "ревью кода"],
      "distilled": [
        {"file": "references/native-engineering.md", "heading": "E06. Независимое review"},
        {"file": "references/native-engineering.md", "heading": "E07. Автоматизируй механические правила"},
        {"file": "references/native-engineering.md", "heading": "E08. Evidence проверок"}
      ]
    }
  ]
}
```
