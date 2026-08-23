# Bedolaga MCP Server

MCP-сервер для получения пользовательских фактов из [Bedolaga Bot](https://github.com/BEDOLAGA-DEV/remnawave-bedolaga-telegram-bot) по Telegram ID или внутреннему `user_id`.

Сервер **read-only**: через Bedolaga MCP нельзя менять баланс, создавать или продлевать подписки, применять промокоды, оформлять возвраты, выводить реферальные средства или выполнять иные действия от имени пользователя.

## Breaking migration (1.0.0)

Начиная с версии **1.0.0** публичный контракт инструментов изменён, а старые имена **удалены**. Обновите конфигурацию клиента:

| Старый инструмент | Что вместо него |
|---|---|
| `bedolaga_balance` | заменён на `bedolaga_user_get` |
| `bedolaga_transactions` | заменён на `bedolaga_billing_get` |
| `bedolaga_subscription` | **не имеет аналога в Bedolaga MCP**. Фактический статус подписки и состояние VPN-панели проверяются через отдельный [mcp-remnawave](https://github.com/mitetenov/mcp-remnawave), а не через этот сервер |

Также в 1.0.0 удалён устаревший HTTP-путь `/mcp`: sessionful Streamable HTTP теперь обслуживается на корневом endpoint `/`, как у mcp-remnawave. Публикация образа использует только теги `:{sha}` и `:{version}`; тега `:latest` нет.

Версия 1.0.0 — первый контракт с корректными API routes, structured результатами и явной границей ответственности с Remnawave.

## Инструменты (Tools)

Сервер предоставляет ровно три инструмента, доступных через MCP-протокол. Все инструменты **readonly** — данные не изменяются.

### Контракт идентичности

Каждый инструмент принимает **ровно одно** из двух полей:

- `telegram_id` — целое число, Telegram ID пользователя (положительное);
- `user_id` — целое число, внутренний ID пользователя в Bedolaga (положительное), используется для email-only тикетов кабинета.

Если не передано ни одного поля или переданы оба — инструмент возвращает ошибку `invalid_input`. Идентичность никогда не берётся от модели: supportBot всегда пинит фактического отправителя — положительный `telegram_id` из аутентифицированного Telegram update, либо внутренний `user_id` кабинета для email-only тикета.

### `bedolaga_user_get`

Получить аккаунт и баланс текущего пользователя Bedolaga.

**Параметры:**

| Параметр | Тип | Обязательный | Описание |
|---|---|---|---|
| `telegram_id` | `int` | ровно одно из двух | Telegram ID пользователя |
| `user_id` | `int` | ровно одно из двух | Внутренний ID пользователя Bedolaga (email-only тикет) |

**JSON-поля ответа (`data`):**

| Поле | Тип | Описание |
|---|---|---|
| `found` | `bool` | Признак, что пользователь найден |
| `telegram_id` | `int` \| `null` | Telegram ID пользователя |
| `display_name` | `string` \| `null` | Безопасное отображаемое имя |
| `status` | `string` \| `null` | Статус аккаунта Bedolaga |
| `balance_kopeks` | `int` \| `null` | Баланс в копейках |
| `balance_rubles` | `float` \| `null` | Баланс в рублях (всегда `kopeks / 100`) |
| `has_made_first_topup` | `bool` \| `null` | Признак первого пополнения в прошлом |
| `has_had_paid_subscription` | `bool` \| `null` | Признак наличия платной покупки в прошлом |
| `referral_code` | `string` \| `null` | Реферальный код |
| `was_referred` | `bool` \| `null` | Пользователь пришёл по приглашению |
| `promo_group` | `object` \| `null` | Название промогруппы и проценты скидок |
| `created_at` / `last_activity` | `string` \| `null` | Даты создания и последней активности |

Поле `promo_group` содержит только `name`, `server_discount_percent`, `traffic_discount_percent`, `device_discount_percent`.

**Пример интерпретации (синтетический):** `balance_kopeks: 350000` и `balance_rubles: 3500.0` означают баланс 3 500 рублей. `has_had_paid_subscription: false` означает, что платных покупок ещё не было.

### `bedolaga_billing_get`

Одним вызовом показать баланс, недавние финансовые события и внутренние записи покупок Bedolaga — чтобы отличить пополнение от покупки.

**Параметры:**

| Параметр | Тип | Обязательный | Описание |
|---|---|---|---|
| `telegram_id` | `int` | ровно одно из двух | Telegram ID пользователя |
| `user_id` | `int` | ровно одно из двух | Внутренний ID пользователя Bedolaga (email-only тикет) |
| `limit` | `int` | Нет | Лимит операций в списке (по умолчанию 20, максимум 50) |

**JSON-поля ответа (`data`):**

| Поле | Тип | Описание |
|---|---|---|
| `balance_kopeks` / `balance_rubles` | `int` / `float` \| `null` | Текущий баланс |
| `transactions` | `array` | Операции от новых к старым, не более `limit` |
| `latest_completed_deposit` | `object` \| `null` | Сводка последнего завершённого пополнения |
| `latest_completed_subscription_purchase` | `object` \| `null` | Сводка последней завершённой покупки подписки |
| `purchased_after_latest_deposit` | `bool` \| `null` | Завершённая покупка позже последнего завершённого пополнения |
| `bot_subscriptions` | `array` | Внутренние записи подписок Bedolaga |
| `meta` | `string` | Фиксированное пояснение «deposit ≠ purchase» |

Каждая операция в `transactions`:

| Поле | Тип | Описание |
|---|---|---|
| `id` | `number` \| `null` | Внутренний ID транзакции |
| `category` | `string` | Нормализованная категория: `deposit`, `subscription_purchase`, `gift_purchase`, `withdrawal`, `refund`, `failed_refund`, `referral_reward`, `poll_reward`, `unknown` |
| `direction` | `string` | `credit` / `debit` / `unknown` |
| `raw_type` | `string` \| `null` | Исходное безопасное имя типа |
| `amount_kopeks` / `amount_rubles` | `int` / `float` \| `null` | Абсолютная сумма |
| `payment_method` | `string` \| `null` | Платёжный метод |
| `is_completed` | `bool` \| `null` | Завершённость операции |
| `description` | `string` \| `null` | Описание |
| `created_at` / `completed_at` | `string` \| `null` | Время создания и завершения |

Каждая запись в `bot_subscriptions` содержит `id`, `bot_record_status`, `bot_record_effective_status`, `is_trial`, `tariff_id`, `tariff_name`, `start_date`, `end_date`, `autopay_enabled`, `autopay_days_before` и фиксированную `note`. Сервер предпочитает полный upstream-список `subscriptions`, удаляет повторяющиеся записи по `id` и сохраняет fallback на одиночное legacy-поле `subscription`. Поле называется `bot_record_status` намеренно: это внутренняя запись Bedolaga, а **не** статус VPN-панели. `bot_record_effective_status` — тоже бот-сторонний эффективный статус (вычисленный ботом из `status` и `end_date`), а не состояние панели.

**Пример интерпретации (синтетический):** `latest_completed_deposit: {amount_kopeks: 350000}` и `purchased_after_latest_deposit: false` — деньги зачислены на баланс, но отдельная покупка после пополнения не завершена.

### `bedolaga_referrals_get`

Получить реферальную сводку текущего пользователя.

**Параметры:**

| Параметр | Тип | Обязательный | Описание |
|---|---|---|---|
| `telegram_id` | `int` | ровно одно из двух | Telegram ID пользователя |
| `user_id` | `int` | ровно одно из двух | Внутренний ID пользователя Bedolaga (email-only тикет) |

**JSON-поля ответа (`data`):**

| Поле | Тип | Описание |
|---|---|---|
| `referral_code` | `string` \| `null` | Реферальный код владельца аккаунта |
| `was_referred` | `bool` \| `null` | Владелец пришёл по приглашению |
| `effective_referral_commission_percent` | `number` \| `null` | Эффективная комиссия |
| `invited_count` | `int` \| `null` | Всего приглашено |
| `active_referrals` | `int` \| `null` | Активных приглашённых |
| `total_earned_kopeks` / `total_earned_rubles` | `int` / `float` \| `null` | Заработок за всё время |
| `month_earned_kopeks` / `month_earned_rubles` | `int` / `float` \| `null` | Заработок за текущий месяц |
| `recent_referral_rewards` | `array` | Последние начисления владельца |
| `meta` | `string` | Фиксированное пояснение |

Возвращается статистика **только владельца аккаунта**. Telegram ID, внутренние ID, username, имена, баланс и активность приглашённых пользователей никогда не возвращаются.

## Decision table

Как LLM (supportBot) должен использовать данные Bedolaga и Remnawave по сценариям:

| Сценарий | Что видно в Bedolaga MCP | Действие LLM |
|---|---|---|
| Deposit без покупки | `deposit` есть, `purchased_after_latest_deposit: false` | Объяснить, что деньги зачислены на баланс, но отдельная покупка не завершена; направить завершить покупку из баланса. Не заявлять о неисправной подписке |
| Покупка с рабочей панелью | Завершённая `subscription_payment` есть | Проверить фактическое состояние панели через Remnawave MCP |
| Покупка без записи в панели | Завершённая `subscription_payment` есть | Эскалировать как подтверждённое расхождение с кратким factual summary |
| Нет пополнения | `deposit` нет | Не заявлять, что платёжный провайдер не списал деньги (Bedolaga подтверждает только отсутствие зачисления в своей учётной системе); эскалировать, если пользователь сообщает о фактическом списании |
| Реферальный вопрос | `bedolaga_referrals_get` | Маршрутизировать только в Bedolaga MCP |
| Вопрос о ноде / HWID | — | Маршрутизировать только в Remnawave MCP (состояние нод и устройств Bedolaga не знает) |

## Формат результата

Каждый инструмент возвращает JSON в текстовом MCP content с единой оболочкой:

- успех: `ok: true`, `source: "bedolaga-mcp"`, `tool`, `data`, `meta`;
- ошибка: `ok: false`, `source`, `tool`, `error.code`, безопасный `error.message`, `error.retryable`.

Сырое тело ответа Bedolaga API и исключения Python модели не возвращаются. Инструменты не возвращают email, ссылку подписки, crypto link, ключи, внешние платёжные ID, receipt-идентификаторы, Remnawave-идентификаторы и персональные данные рефералов.

### Error codes

| Код | Retryable | Когда возникает |
|---|---|---|
| `invalid_input` | нет | Переданы оба или ни одного identity-поля; недопустимое значение |
| `not_configured` | нет | Отсутствует/некорректна конфигурация окружения |
| `identity_unavailable` | нет | Идентичность нельзя сопоставить с пользователем Bedolaga |
| `user_not_found` | нет | Пользователь не найден (upstream 404) |
| `unauthorized` | нет | Неверные/отсутствующие API-креденшелы (upstream 401/403) |
| `rate_limited` | да | Достигнут rate limit (upstream 429) |
| `upstream_timeout` | да | Таймаут или сбой сети до ответа |
| `upstream_unavailable` | да | Upstream недоступен (5xx или невосстановимая ошибка) |
| `invalid_upstream_response` | нет | Тело ответа — невалидный JSON или не объект |
| `internal_error` | нет | Непредвиденная внутренняя ошибка |

Пользовательское сообщение строится только из безопасного `error.message` и никогда не раскрывает HTTP body или внутренний URL.

## Транспорты

Сервер поддерживает два транспорта на одном server factory и одном реестре инструментов:

| Транспорт | Launcher | Порт | Протокол |
|---|---|---|---|
| **Streamable HTTP** (основной) | `http_server.py` | 3100 по умолчанию | Sessionful MCP на `/`, `GET /health`, `DELETE /` |
| Stdio | `bedolaga_server.py` | — | MCP stdio handshake (тот же factory) |

Sessionful Streamable HTTP — современный транспорт MCP, тот же, что использует mcp-remnawave. `GET /health` отдаёт liveness процесса и версию сервера, не раскрывая конфигурацию и секреты. `DELETE /` завершает только указанную сессию (`Mcp-Session-Id`); каждая сессия независима.

## Версионная совместимость

| Компонент | Версия |
|---|---|
| Bedolaga Bot API (upstream) | commit `49b05d5`, приложение `4.1.0` |
| bedolaga-mcp | `1.0.1` |
| supportBot | `2.0.1` |
| mcp-remnawave | `v3.2.1` |

Контракт инструментов проверен против указанного upstream-коммита и эталона mcp-remnawave v3.2.1.

## Требования

- Python 3.11+
- Docker (опционально)
- Развёрнутый Bedolaga Bot с Web API
- API-ключ от Bedolaga (выдаётся в админ-панели бота)

## Быстрый старт

### 1. Клонировать

```bash
git clone https://github.com/mitetenov/bedolaga-mcp.git
cd bedolaga-mcp
```

### 2. Настроить

```bash
cp .env.example .env
# Заполнить BEDOLAGA_API_URL и BEDOLAGA_API_KEY
```

### 3. Запустить

**Streamable HTTP (рекомендуется):**

```bash
# Установить зависимости
pip install -r requirements.txt

# Запустить HTTP-сервер
BEDOLAGA_API_URL=https://your-bot.example.com \
BEDOLAGA_API_KEY=your-key \
python3 http_server.py
```

Сервер будет слушать на `http://0.0.0.0:3100`, MCP endpoint — корень `/`.

**Stdio:**

```bash
BEDOLAGA_API_URL=https://your-bot.example.com \
BEDOLAGA_API_KEY=your-key \
python3 bedolaga_server.py
```

**Через Docker:**

```bash
docker compose up -d
```

Docker-образ по умолчанию запускает Streamable HTTP сервер на порту 3100.

## Подключение как MCP-сервер

### Streamable HTTP

Сервер доступен по HTTP на порту 3100, endpoint — корень `/` (`http://localhost:3100`).

#### Hermes Agent

```yaml
# ~/.hermes/config.yaml
mcp_servers:
  bedolaga:
    transport: streamable-http
    url: "http://localhost:3100"
    env:
      BEDOLAGA_API_URL: "https://your-bot.example.com"
      BEDOLAGA_API_KEY: "your-api-key"
```

#### Claude Desktop

```json
{
  "mcpServers": {
    "bedolaga": {
      "type": "streamableHttp",
      "url": "http://localhost:3100"
    }
  }
}
```

#### Cursor / VS Code

```json
{
  "mcpServers": {
    "bedolaga": {
      "transport": "streamable-http",
      "url": "http://localhost:3100"
    }
  }
}
```

#### Проверка через curl

```bash
# Liveness
curl -s http://localhost:3100/health

# Инициализация (получить session ID)
curl -s -X POST http://localhost:3100/ \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{}},"id":1}' \
  -D - | grep -i mcp-session-id

# Список инструментов (с session ID)
curl -s -X POST http://localhost:3100/ \
  -H "Content-Type: application/json" \
  -H "Mcp-Session-Id: <SESSION_ID>" \
  -d '{"jsonrpc":"2.0","method":"tools/list","id":2}'

# Вызов инструментов
# Пользователь и баланс
curl -s -X POST http://localhost:3100/ \
  -H "Content-Type: application/json" \
  -H "Mcp-Session-Id: <SESSION_ID>" \
  -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"bedolaga_user_get","arguments":{"telegram_id":123456789}},"id":3}'

# Биллинг (операции и внутренние записи покупок)
curl -s -X POST http://localhost:3100/ \
  -H "Content-Type: application/json" \
  -H "Mcp-Session-Id: <SESSION_ID>" \
  -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"bedolaga_billing_get","arguments":{"telegram_id":123456789,"limit":20}},"id":4}'

# Реферальная сводка
curl -s -X POST http://localhost:3100/ \
  -H "Content-Type: application/json" \
  -H "Mcp-Session-Id: <SESSION_ID>" \
  -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"bedolaga_referrals_get","arguments":{"telegram_id":123456789}},"id":5}'

# Завершение сессии
curl -s -X DELETE http://localhost:3100/ \
  -H "Mcp-Session-Id: <SESSION_ID>"
```

### Stdio транспорт

#### Hermes Agent

```yaml
# ~/.hermes/config.yaml
mcp_servers:
  bedolaga:
    command: "python3"
    args: ["/path/to/bedolaga-mcp/bedolaga_server.py"]
    env:
      BEDOLAGA_API_URL: "https://your-bot.example.com"
      BEDOLAGA_API_KEY: "your-api-key"
```

#### Claude Desktop

```json
{
  "mcpServers": {
    "bedolaga": {
      "command": "python3",
      "args": ["/path/to/bedolaga-mcp/bedolaga_server.py"],
      "env": {
        "BEDOLAGA_API_URL": "https://your-bot.example.com",
        "BEDOLAGA_API_KEY": "your-api-key"
      }
    }
  }
}
```

#### Cursor / VS Code

Добавить в `.cursor/mcp.json` или `settings.json`:

```json
{
  "mcpServers": {
    "bedolaga": {
      "command": "python3",
      "args": ["/path/to/bedolaga-mcp/bedolaga_server.py"],
      "env": {
        "BEDOLAGA_API_URL": "https://your-bot.example.com",
        "BEDOLAGA_API_KEY": "your-api-key"
      }
    }
  }
}
```

## Управление сессиями

Streamable HTTP транспорт использует stateful-сессии. После инициализации сервер возвращает заголовок `mcp-session-id`, который клиент должен передавать во всех последующих запросах. `DELETE /` завершает только указанную сессию; один клиент не может завершить или переиспользовать чужую сессию.

## Переменные окружения

| Переменная | Назначение |
|---|---|
| `BEDOLAGA_API_URL` | URL Bedolaga Web API |
| `BEDOLAGA_API_KEY` | API-ключ Bedolaga (передаётся upstream в `X-API-Key`) |
| `MCP_HTTP_HOST` | Адрес для bind (по умолчанию: `0.0.0.0`) |
| `MCP_HTTP_PORT` | Порт HTTP-сервера (по умолчанию: `3100`) |
| `BEDOLAGA_TIMEOUT_MS` | Таймаут upstream в миллисекундах (по умолчанию: 10000) |

Для совместимости принимаются legacy-переменные `HOST`/`PORT`, если `MCP_HTTP_HOST`/`MCP_HTTP_PORT` не заданы.

## Upstream API

Bedolaga Web API: `X-API-Key` в заголовке. Используемые маршруты:

- `GET /users/by-telegram-id/{telegram_id}` — пользователь по Telegram ID;
- `GET /users/{user_id}` — пользователь по внутреннему ID (email-only тикеты);
- `GET /transactions?user_id=...` — операции с фильтрами и пагинацией;
- `GET /partners/referrers/{user_id}` — реферальная карточка.

Подробнее: https://docs.bedolagam.ru

## Ограничения первой версии

- **Нет provider-specific попыток платежей.** Bedolaga возвращает только операции, ставшие записями в общей таблице transactions. Сырые попытки платёжного провайдера, которые не стали записью, недоступны.
- **Нет чтения Redis-корзины пользователя.** Актуальный Web API не предоставляет безопасный read-only endpoint для этого. Текущую проблему «пополнил, а покупки нет» достоверно диагностируют по разнице между `deposit` и `subscription_payment` (см. decision table).
- **Email-only lookup поддерживается.** Для тикетов кабинета без Telegram ID сервер принимает внутренний `user_id` (положительное целое) и резолвит его через `GET /users/{user_id}`. supportBot пинит внутренний `user_id` кабинета (абсолютное значение отрицательного synthetic conversation key) — для таких тикетов Bedolaga-данные доступны, а Remnawave-инструменты возвращают `identity_unavailable`, потому что у такого пользователя нет Telegram-идентичности и доказанной записи в панели.

## Откат (rollback)

Выключение `BEDOLAGA_MCP_ENABLED=false` в supportBot возвращает его в Remnawave-only режим: Bedolaga MCP не подключается, его инструменты исчезают из allowlist, а вебхук/poller-обработка тикетов (`BEDOLAGA_ENABLED`) остаётся независимой. Откат не трогает пользовательскую базу и финансовые данные — Bedolaga MCP read-only и не хранит состояние.
