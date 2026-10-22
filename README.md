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

Также в 1.0.0 удалён устаревший HTTP-путь `/mcp`: sessionful Streamable HTTP теперь обслуживается на корневом endpoint `/`, как у mcp-remnawave. Каждая публикация образа получает три тега: `:latest`, `:{version}` и `:{sha}`.

Версия 1.0.0 — первый контракт с корректными API routes, structured результатами и явной границей ответственности с Remnawave.

## Инструменты (Tools)

Сервер предоставляет ровно восемь инструментов, доступных через MCP-протокол. Все инструменты **readonly** — данные не изменяются.

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

### `bedolaga_subscription_get`

Получить бот-сторонние записи подписок и даты жизненного цикла (`created_at`, `start_date`, `end_date`, `is_trial`, `autopay_enabled`).

**Параметры:** `telegram_id` или `user_id` (ровно одно).

Возвращает `has_subscription_records`, `active_record_count`, список `subscriptions` и фиксированный `meta`. Поле `bot_record_status` — внутренняя запись бота, а **не** статус VPN-панели (фактическое состояние проверяется через Remnawave MCP).

### `bedolaga_tickets_get`

Получить сводку собственных обращений в поддержку (`id`, `title`, `status`, `priority`, даты создания/обновления/закрытия) без текстов сообщений и медиа.

**Параметры:** `telegram_id` или `user_id` (ровно одно), `limit` (по умолчанию 10, максимум 50).

### `bedolaga_payment_status_get`

Получить историю финансовых операций и статус завершённости в учётной системе бота (`completed` / `not_completed` / `unknown`).

**Параметры:** `telegram_id` или `user_id` (ровно одно), `limit` (по умолчанию 5, максимум 20).

Статус `not_completed` означает лишь отсутствие завершения операции в биллинге бота, а **не** сбой или ожидание на стороне платёжного шлюза.

### `bedolaga_promocode_check`

Проверить глобальное определение промокода, срок действия, активность, бонус и остаток применений.

**Параметры:** `code` (обязательно), `telegram_id` или `user_id` (ровно одно для пиннинга идентичности).

Возвращает маскированный код (`code_masked`), признак `globally_valid`, `reason_code` (`not_found`, `inactive`, `not_yet_valid`, `expired_or_exhausted`, `lookup_incomplete`) и `user_eligibility: "unknown"`.

### `bedolaga_gifts_get`

Получить историю покупок подарков владельца аккаунта.

**Параметры:** `telegram_id` или `user_id` (ровно одно), `limit` (по умолчанию 20, максимум 50).

Отображает только факт покупки подарков (бухгалтерия); токены подарков, получатели и статус активации не раскрываются.

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

Сырое тело ответа Bedolaga API и внутренние ошибки модели не возвращаются. Инструменты не возвращают email, ссылку подписки, crypto link, ключи, внешние платёжные ID, receipt-идентификаторы, Remnawave-идентификаторы и персональные данные рефералов.

### Error codes

| Код | Retryable | Когда возникает |
|---|---|---|
| `invalid_input` | нет | Переданы оба или ни одного identity-поля; недопустимое значение |
| `not_configured` | нет | Отсутствует/некорректна конфигурация окружения |
| `identity_unavailable` | нет | Идентичность нельзя сопоставить с пользователем Bedolaga |
| `user_not_found` | нет | Пользователь не найден (upstream 404 исключительно при поиске пользователя) |
| `unauthorized` | нет | Неверные/отсутствующие API-креденшелы (upstream 401/403) |
| `rate_limited` | да | Достигнут rate limit (upstream 429) |
| `upstream_timeout` | да | Таймаут или сбой сети до ответа |
| `upstream_unavailable` | да | Upstream недоступен (5xx, сбой запроса или upstream 404 для непользовательских ресурсов — не означает отсутствие аккаунта) |
| `invalid_upstream_response` | нет | Тело ответа — невалидный JSON или не объект |
| `internal_error` | нет | Непредвиденная внутренняя ошибка |

Пользовательское сообщение строится только из безопасного `error.message` и никогда не раскрывает HTTP body или внутренний URL. Ошибка `user_not_found` возникает только при прямом поиске учётной записи (`get_user_by_telegram_id` / `get_user_by_id`). При статусе 404 для зависимых ресурсов (транзакции, рефералы, подписки, тикеты, промокоды) возвращается `upstream_unavailable`, что указывает на недоступность конкретного ресурса и не свидетельствует об отсутствии аккаунта пользователя.

## Транспорты

Сервер поддерживает два транспорта на одном server factory и одном реестре инструментов:

| Транспорт | Launcher | Порт | Протокол |
|---|---|---|---|
| **Streamable HTTP** (основной) | `bedolaga-mcp http` | 3100 по умолчанию | Dual-era MCP на `/` (см. ниже), `GET /health`, `DELETE /` (только legacy-сессии) |
| Stdio | `bedolaga-mcp stdio` | — | MCP stdio handshake (тот же factory) |

Эндпоинт `/` — единственный, но обслуживает **две эры протокола** одновременно; SDK v2 сам определяет, к какой эре относится каждый запрос, по заголовку `MCP-Protocol-Version`:

- **Современный протокол `2026-07-28`** — stateless/sessionless. Каждый POST на `/` самодостаточен: сервер никогда не выдаёт `Mcp-Session-Id` и не хранит состояние между запросами. Официальные клиенты MCP SDK v2 (см. «Официальный клиент SDK v2» ниже) используют этот режим автоматически.
- **Legacy-клиенты с initialize-handshake** (протоколы вплоть до `2025-11-25`, включая `2024-11-05`) получают заголовок `Mcp-Session-Id` в ответ на `initialize` и обязаны передавать его во всех последующих запросах. `DELETE /` с этим заголовком завершает именно эту сессию; на другие сессии и на современных клиентов это не влияет.

`GET /health` отдаёт liveness процесса и версию сервера, не раскрывая конфигурацию и секреты.

## Версионная совместимость

| Компонент | Версия |
|---|---|
| Bedolaga Bot API (upstream) | commit `49b05d5`, приложение `4.1.0` |
| bedolaga-mcp | `1.2.0` |
| Official Go MCP SDK | `v1.7.0` |
| Поддерживаемые протоколы MCP | `2026-07-28` (современный, stateless) + legacy initialize-handshake вплоть до `2025-11-25` |
| supportBot | `2.0.1` |
| mcp-remnawave | `v3.2.1` |


Контракт инструментов проверен против указанного upstream-коммита и эталона mcp-remnawave v3.2.1.

## Требования

- Go 1.27+ для сборки (готовый контейнер не требует Go или Python)
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
# Собрать исполняемый файл
go build -o bedolaga-mcp ./cmd/bedolaga-mcp

# Запустить HTTP-сервер
BEDOLAGA_API_URL=https://your-bot.example.com \
BEDOLAGA_API_KEY=your-key \
./bedolaga-mcp http
```

Сервер будет слушать на `http://0.0.0.0:3100`, MCP endpoint — корень `/`.

**Stdio:**

```bash
BEDOLAGA_API_URL=https://your-bot.example.com \
BEDOLAGA_API_KEY=your-key \
MCP_HTTP_HOST=127.0.0.1 MCP_HTTP_PORT=3100 ./bedolaga-mcp stdio
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
      MCP_HTTP_HOST: "127.0.0.1"
      MCP_HTTP_PORT: "3100"
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

#### Проверка через curl (legacy compatibility check)

Сырой JSON-RPC через curl использует **legacy initialize-handshake** (протокол `2024-11-05`) — это ручная проверка обратной совместимости, а не то, как ходят современные клиенты. Современные клиенты MCP SDK v2 согласовывают протокол `2026-07-28` автоматически и `Mcp-Session-Id` не получают (см. «Официальный клиент SDK v2 (современный протокол)» ниже).

```bash
# Liveness
curl -s http://localhost:3100/health

# Legacy initialize handshake (получить session ID; работает для протоколов вплоть до 2025-11-25)
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

# Завершение legacy-сессии (для современного протокола 2026-07-28 не требуется и не применяется)
curl -s -X DELETE http://localhost:3100/ \
  -H "Mcp-Session-Id: <SESSION_ID>"
```

#### Официальный клиент SDK v2 (современный протокол)

Официальный клиент из Python MCP SDK v2 (`mcp==2.0.0`) сам согласовывает протокол — `2026-07-28`, если сервер его поддерживает, иначе legacy-handshake — без ручного построения `_meta` или заголовков:

```python
import asyncio

from mcp.client.client import Client


async def main() -> None:
    async with Client("http://localhost:3100/", mode="auto") as client:
        print("negotiated protocol:", client.protocol_version)  # "2026-07-28" against this server

        tools = await client.list_tools()
        print([tool.name for tool in tools.tools])

        result = await client.call_tool(
            "bedolaga_user_get", {"telegram_id": 123456789}
        )
        print(result.content)


asyncio.run(main())
```

`mode="auto"` — это то же самое согласование, которое использует supportBot: клиент сам решает, современный сервер перед ним или legacy, и не требует от вызывающего кода знать протокольную эру заранее.

### Stdio транспорт

#### Hermes Agent

```yaml
# ~/.hermes/config.yaml
mcp_servers:
  bedolaga:
    command: "/path/to/bedolaga-mcp/bedolaga-mcp"
    args: ["stdio"]
    env:
      BEDOLAGA_API_URL: "https://your-bot.example.com"
      BEDOLAGA_API_KEY: "your-api-key"
      MCP_HTTP_HOST: "127.0.0.1"
      MCP_HTTP_PORT: "3100"
```

#### Claude Desktop

```json
{
  "mcpServers": {
    "bedolaga": {
      "command": "/path/to/bedolaga-mcp/bedolaga-mcp",
      "args": ["stdio"],
      "env": {
        "BEDOLAGA_API_URL": "https://your-bot.example.com",
        "BEDOLAGA_API_KEY": "your-api-key",
        "MCP_HTTP_HOST": "127.0.0.1",
        "MCP_HTTP_PORT": "3100"
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
      "command": "/path/to/bedolaga-mcp/bedolaga-mcp",
      "args": ["stdio"],
      "env": {
        "BEDOLAGA_API_URL": "https://your-bot.example.com",
        "BEDOLAGA_API_KEY": "your-api-key",
        "MCP_HTTP_HOST": "127.0.0.1",
        "MCP_HTTP_PORT": "3100"
      }
    }
  }
}
```

## Управление сессиями

Streamable HTTP транспорт — dual-era, и сессии применимы только к одной из двух эр:

- **Legacy initialize-handshake** (протоколы вплоть до `2025-11-25`): после `initialize` сервер возвращает заголовок `Mcp-Session-Id`, который клиент должен передавать во всех последующих запросах. `DELETE /` с этим заголовком завершает только указанную сессию; один клиент не может завершить или переиспользовать чужую сессию.
- **Современный протокол `2026-07-28`**: stateless/sessionless — сервер никогда не выдаёт `Mcp-Session-Id`, и `DELETE /` для таких клиентов не нужен и не применяется.

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

Откат образа `bedolaga-mcp` до тега `1.1.0` (последний релиз до миграции на MCP SDK v2, только legacy-эра Streamable HTTP) тоже безопасен: клиент supportBot на MCP SDK v2 автоматически переходит (auto-fallback) на legacy initialize-handshake, если сервер не отвечает на современный протокол `2026-07-28`, поэтому инструменты Bedolaga MCP остаются доступны без дополнительной настройки.

## Go build and verification

Production is a statically linked Go executable at `/app/bedolaga-mcp` in a `scratch` image. The runtime contains the executable, HTTPS CA bundle, account records for the nonroot `appuser` (UID/GID 1000), its home directory and writable `/tmp`; it has no shell, package manager, shared libraries, Python or Go toolchain. Use `bedolaga-mcp http` (default) or `bedolaga-mcp stdio`. `bedolaga-mcp --version` prints the application version. `bedolaga-mcp healthcheck` checks the local HTTP health endpoint and exits nonzero on failure. The Compose image name, port 3100, environment variables, internal-only networking and restart policy are preserved.

```bash
go test -race -cover ./...
go vet ./...
go build -o bedolaga-mcp ./cmd/bedolaga-mcp
docker build -t bedolaga-mcp:local .
```

Tests include 104 normalization cases captured from the committed Python suite, real local upstream HTTP servers, both protocol eras, session termination, host/origin checks, and an executable subprocess handshake/tool call/EOF shutdown. No production API is contacted. The transport adapter preserves Python SDK response metadata and legacy HTTP status/error behavior around the official Go SDK.

## Docker build cache

The build context includes only production Go files, the embedded tool registry, `go.mod` and `go.sum`. Tests, golden fixtures, documentation, local files and secrets stay outside the context. Unit tests still run separately in CI.

Dependency manifests are copied before the production sources. `go mod download` writes dependencies into an ordinary cached layer, so a source-only edit reuses that layer. Compilation runs without network access and uses a persistent BuildKit compiler cache on the current builder. Changing only tests or documentation does not rebuild the executable.

Both CI image jobs import and export GitHub Actions layer cache with `mode=max`. This preserves intermediate dependency layers on fresh runners. BuildKit cache-mount contents are local to a builder and are not exported by that backend; correctness and dependency reuse do not rely on them. Ordinary `docker build -t bedolaga-mcp:local .` still works with Docker's default BuildKit builder.

The application parses UTC or explicit numeric-offset timestamps and does not load IANA time zones. The previous runtime did not install zoneinfo; the minimal runtime retains that behavior and does not add a time-zone database. The existing HTTP/stdio commands and Compose healthcheck use the executable directly.

## Build and dependency maintenance

Use Go 1.27.3. CI on Ubuntu26.04 verifies module tidy/integrity, formatting,
vet, golangci-lint 2.15.0, unit/race tests, the production executable and the
linux/amd64 scratch image. Actions use immutable release SHAs; weekly Dependabot
groups minor/patch Go, Actions and Docker updates. PR jobs only validate.
Publication is serialized after smoke succeeds on main and preserves latest,
package-version and commit image tags. The scratch runtime retains UID1000,
HTTP/SSE/stdio contracts and embedded resources. No Python runtime/tooling remains.
