# Bedolaga MCP Server

MCP-сервер для получения пользовательских фактов из [Bedolaga Bot](https://github.com/BEDOLAGA-DEV/remnawave-bedolaga-telegram-bot) по Telegram ID.

## Breaking migration (1.0.0)

Начиная с версии **1.0.0** публичный контракт инструментов изменён, а старые имена **удалены**. Обновите конфигурацию клиента:

| Старый инструмент | Что вместо него |
|---|---|
| `bedolaga_balance` | заменён на `bedolaga_user_get` |
| `bedolaga_transactions` | заменён на `bedolaga_billing_get` |
| `bedolaga_subscription` | **не имеет аналога в Bedolaga MCP**. Фактический статус подписки и состояние VPN-панели проверяются через отдельный [mcp-remnawave](https://github.com/mitetenov/mcp-remnawave), а не через этот сервер |

Версия 1.0.0 — первый контракт с корректными API routes, structured результатами и явной границей ответственности с Remnawave. Все инструменты **readonly**: через Bedolaga MCP нельзя менять баланс, создавать или продлевать подписки, применять промокоды, оформлять возвраты или выполнять иные действия от имени пользователя.

## Инструменты (Tools)

Сервер предоставляет три инструмента, доступных через MCP-протокол. Все инструменты **readonly** — данные не изменяются.

### `bedolaga_user_get`

Получить аккаунт и баланс текущего пользователя Bedolaga по Telegram ID.

**Параметры:**

| Параметр | Тип | Обязательный | Описание |
|---|---|---|---|
| `telegram_id` | `int` | Да | Telegram ID пользователя |

**Назначение:** пополнение баланса (`deposit`) не является покупкой — покупку подтверждает только завершённая операция `subscription_payment`. Инструмент не знает фактический статус VPN-панели: он проверяется через отдельный Remnawave MCP.

### `bedolaga_billing_get`

Одним вызовом показать баланс, недавние финансовые события и внутренние записи покупок Bedolaga.

**Параметры:**

| Параметр | Тип | Обязательный | Описание |
|---|---|---|---|
| `telegram_id` | `int` | Да | Telegram ID пользователя |
| `limit` | `int` | Нет | Лимит операций (по умолчанию 20, максимум 50) |

**Важно:** `deposit` означает зачисление на баланс; покупку подтверждает только завершённый `subscription_payment`. Внутренний статус записи бота (`bot_record_status`) — это **не** статус VPN-панели; фактическое состояние панели проверяется через отдельный Remnawave MCP.

### `bedolaga_referrals_get`

Получить реферальную сводку текущего пользователя.

**Параметры:**

| Параметр | Тип | Обязательный | Описание |
|---|---|---|---|
| `telegram_id` | `int` | Да | Telegram ID пользователя |

**Назначение:** реферальный код, количество приглашённых и начисления владельца аккаунта без персональных данных третьих лиц.

## Формат результата

Каждый инструмент возвращает JSON в текстовом MCP content с единой оболочкой:

- успех: `ok: true`, `source`, `tool`, `data`, `meta`;
- ошибка: `ok: false`, `source`, `tool`, `error.code`, безопасный `error.message`, `error.retryable`.

Сырое тело ответа Bedolaga API и исключения Python модели не возвращаются. Инструменты не возвращают ссылку подписки, crypto link, ключи, email, внешние платёжные ID, receipt-идентификаторы, Remnawave-идентификаторы и персональные данные рефералов.

## Транспорты

Сервер поддерживает два транспортных протокола:

| Транспорт | Файл | Порт | Протокол |
|---|---|---|---|
| **Streamable HTTP** (новый) | `http_server.py` | 3100 | HTTP (REST + SSE) |
| Stdio (legacy) | `bedolaga_server.py` | — | stdin/stdout JSON |

Streamable HTTP — это современный транспорт MCP, рекомендованный для production. Он позволяет подключаться по HTTP без необходимости запускать дочерний процесс на клиенте.

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

Сервер будет слушать на `http://0.0.0.0:3100`, MCP endpoint доступен по `POST /mcp`.

**Stdio (legacy):**

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

### Streamable HTTP (новый транспорт)

Сервер доступен по HTTP на порту 3100, endpoint: `/mcp`.

#### Hermes Agent

```yaml
# ~/.hermes/config.yaml
mcp_servers:
  bedolaga:
    transport: streamable-http
    url: "http://localhost:3100/mcp"
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
      "url": "http://localhost:3100/mcp"
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
      "url": "http://localhost:3100/mcp"
    }
  }
}
```

#### Проверка через curl

```bash
# Инициализация (получить session ID)
curl -s -X POST http://localhost:3100/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{}},"id":1}' \
  -D - | grep -i mcp-session-id

# Список инструментов (с session ID)
curl -s -X POST http://localhost:3100/mcp \
  -H "Content-Type: application/json" \
  -H "Mcp-Session-Id: <SESSION_ID>" \
  -d '{"jsonrpc":"2.0","method":"tools/list","id":2}'

# Вызов инструментов
# Пользователь и баланс
curl -s -X POST http://localhost:3100/mcp \
  -H "Content-Type: application/json" \
  -H "Mcp-Session-Id: <SESSION_ID>" \
  -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"bedolaga_user_get","arguments":{"telegram_id":123456789}},"id":3}'

# Биллинг (операции и внутренние записи покупок)
curl -s -X POST http://localhost:3100/mcp \
  -H "Content-Type: application/json" \
  -H "Mcp-Session-Id: <SESSION_ID>" \
  -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"bedolaga_billing_get","arguments":{"telegram_id":123456789,"limit":20}},"id":4}'

# Реферальная сводка
curl -s -X POST http://localhost:3100/mcp \
  -H "Content-Type: application/json" \
  -H "Mcp-Session-Id: <SESSION_ID>" \
  -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"bedolaga_referrals_get","arguments":{"telegram_id":123456789}},"id":5}'
```

### Stdio (legacy транспорт)

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

Streamable HTTP транспорт использует stateful-сессии по умолчанию (`stateless_http=False`). После инициализации сервер возвращает заголовок `mcp-session-id`, который клиент должен передавать во всех последующих запросах.

Если нужен stateless-режим (без отслеживания сессий), отредактируйте `http_server.py` и установите `stateless_http=True`.

## Переменные окружения

| Переменная | Назначение |
|---|---|
| `BEDOLAGA_API_URL` | URL Bedolaga Web API |
| `BEDOLAGA_API_KEY` | API-ключ Bedolaga |
| `PORT` | Порт HTTP-сервера (по умолчанию: 3100) |
| `HOST` | Адрес для bind (по умолчанию: 0.0.0.0) |

## API

Bedolaga Web API: `X-API-Key` в заголовке, endpoint `/users/by-telegram-id/{telegram_id}`. Подробнее: https://docs.bedolagam.ru
