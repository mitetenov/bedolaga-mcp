package bedolaga

const (
	SOURCE                   = "bedolaga-mcp"
	UNKNOWN_CATEGORY         = "unknown"
	UNKNOWN_DIRECTION        = "unknown"
	BOT_RECORD_NOTE          = "This is the bot-side Bedolaga purchase record, not the VPN panel status. Verify the actual panel state via the separate Remnawave MCP."
	BILLING_META_NOTE        = "deposit = a balance credit (money added to the balance), not a purchase. Only a completed subscription_payment confirms a purchase. bot_record_status is the bot-side purchase record, not the VPN panel status; verify the actual panel state via the separate Remnawave MCP."
	REFERRAL_META_NOTE       = "Aggregates belong to the account owner only; invited users' personal data is intentionally excluded."
	SUBSCRIPTION_META_NOTE   = "Bedolaga subscription records are not the VPN panel status."
	TICKETS_META_NOTE        = "Tickets belong to the account owner only; messages and media are intentionally excluded."
	PAYMENT_STATUS_META_NOTE = "This does not expose payment-provider attempt status. not_completed is not proof of pending or failure."
	PROMOCODE_META_NOTE      = "Global validity only; the existing API cannot check whether this user already used or may apply the code."
	GIFTS_META_NOTE          = "The existing Web API exposes gift purchase accounting only."
)
