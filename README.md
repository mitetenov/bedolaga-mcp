# Bedolaga MCP Server

MCP-сервер для получения баланса пользователя из [Bedolaga Bot](https://github.com/BEDOLAGA-DEV/remnawave-bedolaga-telegram-bot) по Telegram ID.

## Возможности

- `bedolaga_balance` — получить баланс пользователя в рублях по Telegram ID

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

**Напрямую:**
```bash
BEDOLAGA_API_URL=https://your-bot.example.com \
BEDOLAGA_API_KEY=your-key \
python3 bedolaga_server.py
```

**Через Docker:**
```bash
docker compose up -d
```

## Подключение как MCP-сервер

### Hermes Agent

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

### Claude Desktop

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

### Cursor / VS Code

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

## API

Bedolaga Web API: `X-API-Key` в заголовке, endpoint `/users/by-telegram-id/{telegram_id}`. Подробнее: https://docs.bedolagam.ru
