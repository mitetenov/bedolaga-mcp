# Payment Lookup Errors Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development в рамках sol-flash-sdd. Реализацию и тесты пишет Gemini 3.8 Flash; Sol выполняет независимые review. Шаги отмечаются чекбоксами. Текстовый override исключает код, псевдокод и исполняемые команды из плана. До согласования человеком реализация запрещена.

**Goal:** Прекратить выдавать отсутствие пользователя при HTTP 404 финансового или другого непользовательского ресурса.

**Architecture:** Явно ограничить семантику lookup в общем HTTP-слое клиента. Для остальных 404 использовать существующую доменную ошибку и неизменный structured envelope; проверить весь путь через registry на синтетическом HTTP.

**Tech Stack:** Python 3.14, httpx, unittest, существующие MCP registry и contracts.

**Spec:** docs/superpowers/specs/2026-09-03-payment-lookup-errors-design.md

## Global Constraints

Сохраняются десять кодов SPEC_ERROR_CODES и действующий retryable для upstream_unavailable: true.

Без изменения идентичности, allowlist, HTTP read-only, обработки секретов, нормализации денег, пагинации и финансовых выводов.

Без live API, новых API-ключей, смены провайдера, deployment, push, merge и изменения версии.

Реализацию и тесты пишет только Gemini 3.8 Flash после явного согласования человеком; Sol выполняет review.

### Task 1: Разделить 404 пользователя и ресурса с проверкой envelope

**Spec:** Все разделы docs/superpowers/specs/2026-09-03-payment-lookup-errors-design.md.

**Files:** Изменить bedolaga_mcp/client.py, tests/test_client.py, tests/test_tool_registry.py и README.md. При необходимости дополнить tests/test_contracts.py и tests/test_billing_tool.py; читать bedolaga_mcp/errors.py, contracts.py, tools/__init__.py, tools/identity.py и tools/billing.py. Менять описание в errors.py или contracts.py только если существующий текст действительно противоречит уточнению; каталог кодов сохраняется.

**Interfaces:** Публичные методы BedolagaClient сохраняют входы и результаты. Только get_user_by_telegram_id и get_user_by_id обозначают запрос как lookup; внутренние _get, _get_object и _request_json передают этот контекст до места отображения HTTP-статуса. _get_list и обычные вызовы не получают семантику отсутствия пользователя. Registry возвращает текущий structured envelope из доменной ошибки без новой схемы.

- [ ] Добавить регрессию для успешного lookup пользователя и последующего 404 transactions: ожидается UpstreamUnavailableError вместо UserNotFoundError. Зафиксировать lookup по telegram_id и внутреннему user_id: оба при своём 404 продолжают возвращать UserNotFoundError. Проверить, что новые тесты различают старое и требуемое поведение.
- [ ] В общем HTTP-слое реализовать явное различие операции с безопасным значением по умолчанию для непользовательского ресурса. Не распознавать lookup по произвольной строке пути и не добавлять код ошибки. Для ресурса использовать безопасное сообщение о его недоступности и прежний retryable true.
- [ ] Расширить матрицу 404 на transactions, referrers, subscriptions, tickets и promo-codes, включая object/list-пути и общий helper без контекста lookup. Проверить успешные пустые коллекции и опциональные данные; не скрывать отказ ресурса успешным пустым ответом. Сохранить текущие 401/403, 422, 429, 5xx, network, timeout, JSON и shape-регрессии.
- [ ] Добавить интеграционный тест client плюс registry на синтетическом HTTP: успешный lookup, затем 404 истории дают error envelope с source bedolaga-mcp, именем billing-инструмента, кодом upstream_unavailable и retryable true. Отдельно проверить lookup 404, код user_not_found, retryable false и отсутствие дальнейшего запроса истории. Проверить, что сообщения и envelope не содержат секретный ключ или содержимое upstream-ответа.
- [ ] Уточнить README: user_not_found означает 404 только поиска пользователя, 404 иных ресурсов относится к upstream_unavailable и не доказывает отсутствие аккаунта. Сохранить набор десяти кодов и все флаги, подтвердив это contract-тестами.
- [ ] Выполнить полный unittest и smoke пакета/реестра восьми инструментов по .github/workflows/ci.yml на Python 3.14. Проверить diff на отсутствие изменений API, identity и версий. Не добавлять несуществующие lint/type/coverage-гейты. Подготовить только изменения задачи к коммиту, Sol review Task 1 и финальному review всей ветки по управляемому workflow.

**Acceptance:** Оба пользовательских lookup сохраняют user_not_found при 404, каждый непользовательский endpoint выдаёт upstream_unavailable, registry сохраняет различие в действующем envelope. Старые коды, успешные формы ответов, security и status mapping сохранены. Полный unittest и registry smoke проходят без реальных запросов к Bedolaga.
