# Реестр источников

Реестр фиксирует baseline выжимки. Перед заявлением нормативной совместимости
проверь актуальную редакцию и применимые условия в первоисточнике.

<!-- delivery-engineering:sources -->
```json
{
  "version": 1,
  "sources": [
    {
      "id": "SWEBOK-4.0a",
      "title": "Guide to the Software Engineering Body of Knowledge",
      "version": "4.0a",
      "url": "https://www.computer.org/education/bodies-of-knowledge/software-engineering",
      "access": "official public PDF",
      "used": ["KA Software Construction", "KA Software Testing", "KA Software Quality"]
    },
    {
      "id": "SWE-GOOGLE-2020",
      "title": "Software Engineering at Google",
      "version": "online edition, 2020",
      "url": "https://abseil.io/resources/swe-book",
      "access": "official HTML, CC BY-NC-ND 4.0",
      "used": ["ch08 Style Guides and Rules", "ch09 Code Review", "ch11-14 Testing", "ch20 Static Analysis"]
    },
    {
      "id": "ISTQB-CTFL-4.0.1",
      "title": "Certified Tester Foundation Level Syllabus",
      "version": "4.0.1, 2024-09-15",
      "url": "https://www.istqb.org/certifications/certified-tester-foundation-level-ctfl-v4-0/",
      "access": "official public syllabus",
      "used": ["1.4 Test Activities", "4 Test Analysis and Design", "5.2 Risk Management", "5.3 Test Reporting"]
    },
    {
      "id": "ISO-29119-OVERVIEW",
      "title": "ISO/IEC/IEEE 29119 series overview",
      "version": "public overview; normative parts edition-dependent",
      "url": "https://committee.iso.org/sites/jtc1sc7/home/projects/flagship-standards/isoiecieee-29119-series.html",
      "access": "official overview only; full standards may be licensed",
      "used": ["series structure: concepts, processes, documentation, techniques"]
    },
    {
      "id": "RFC-9110",
      "title": "HTTP Semantics",
      "version": "RFC 9110, June 2022",
      "url": "https://www.rfc-editor.org/rfc/rfc9110.html",
      "access": "official public standard",
      "used": ["methods", "status codes", "representations", "conditional requests", "caching"]
    },
    {
      "id": "WCAG-2.2",
      "title": "Web Content Accessibility Guidelines 2.2",
      "version": "W3C Recommendation 2024-12-12",
      "url": "https://www.w3.org/TR/WCAG22/",
      "access": "official public recommendation",
      "used": ["POUR principles", "success criteria", "conformance requirements"]
    },
    {
      "id": "TESTING-LIBRARY-GP",
      "title": "Testing Library Guiding Principles",
      "version": "living documentation",
      "url": "https://testing-library.com/docs/guiding-principles/",
      "access": "official public documentation",
      "used": ["user-oriented queries and observable behavior"]
    },
    {
      "id": "OWASP-ASVS-5.0.0",
      "title": "Application Security Verification Standard",
      "version": "5.0.0",
      "url": "https://owasp.org/www-project-application-security-verification-standard/",
      "access": "official open standard",
      "used": ["risk-scoped security requirements and versioned identifiers"]
    },
    {
      "id": "OPENAI-GPT5-PROMPTING-2025",
      "title": "GPT-5 prompting guide",
      "version": "2025-08-07",
      "url": "https://developers.openai.com/cookbook/examples/gpt-5/gpt-5_prompting_guide",
      "access": "official public cookbook",
      "used": ["scoped structured instructions", "stop conditions", "context gathering", "instruction consistency", "codebase standards"]
    },
    {
      "id": "OPENAI-MODEL-GUIDANCE-LATEST",
      "title": "Model guidance",
      "version": "living documentation, checked 2026-08-04",
      "url": "https://developers.openai.com/api/docs/guides/latest-model",
      "access": "official public documentation",
      "used": ["lean prompts", "autonomy boundaries", "success criteria", "eval-oriented iteration"]
    },
    {
      "id": "PONYTAIL-2ED6C52",
      "title": "Ponytail skill",
      "version": "snapshot 2ed6c52",
      "url": "https://github.com/DietrichGebert/ponytail/blob/2ed6c52c9d7e5e56942508591085fd45dea277d3/skills/ponytail/SKILL.md",
      "access": "public GitHub source",
      "used": ["ordered implementation ladder", "protected floor", "smallest runnable check", "conscious ceiling and revisit trigger"]
    },
    {
      "id": "BENJAMIN-PLUS-532771B",
      "title": "Benjamin Plus skill",
      "version": "snapshot 532771be5687566b12a9f62e17fbe7ad3591518c",
      "url": "https://github.com/JetBrains/benjamin-plus-skill/tree/532771be5687566b12a9f62e17fbe7ad3591518c",
      "access": "public GitHub source, MIT",
      "used": ["batched reconnaissance", "inspection versus ingestion", "named check boundary", "bounded polling", "paired efficiency measurement"]
    }
  ]
}
```

## Правило цитирования в case

Записывай `source-id`, rule ID выжимки и точный project fact. Для ASVS используй
версионированный идентификатор вида `v5.0.0-x.y.z`. Не заявляй соответствие
ISO/WCAG/ASVS шире реально проверенной поверхности.
