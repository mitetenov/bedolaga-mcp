package bedolaga

import (
	"encoding/json"
	"fmt"
	"math"
	"sort"
	"strconv"
	"strings"
	"time"
)

type M = map[string]any

func obj(v any) M {
	m, _ := v.(map[string]any)
	if m == nil {
		return M{}
	}
	return m
}
func arr(v any) []any {
	a, _ := v.([]any)
	if a == nil {
		return []any{}
	}
	return a
}
func trim(s string) string { return strings.TrimSpace(s) }
func integer(v any) (int64, bool) {
	switch n := v.(type) {
	case json.Number:
		i, e := n.Int64()
		return i, e == nil
	case int:
		return int64(n), true
	case int64:
		return n, true
	}
	return 0, false
}
func equal(a, b any) bool {
	ai, aok := integer(a)
	bi, bok := integer(b)
	if aok && bok {
		return ai == bi
	}
	return fmt.Sprintf("%T:%v", a, a) == fmt.Sprintf("%T:%v", b, b)
}
func ident(v any) string { return fmt.Sprintf("%T:%v", v, v) }
func selectFields(raw M, fields ...string) M {
	out := M{}
	for _, f := range fields {
		out[f] = raw[f]
	}
	return out
}
func money(v any, absolute bool) (any, any) {
	i, ok := integer(v)
	if !ok {
		return nil, nil
	}
	if absolute && i < 0 {
		i = -i
	}
	return i, float64(i) / 100
}

var categories = map[string]string{"deposit": "deposit", "subscription_payment": "subscription_purchase", "subscription_purchase": "subscription_purchase", "gift_payment": "gift_purchase", "gift_purchase": "gift_purchase", "withdrawal": "withdrawal", "refund": "refund", "failed_refund": "failed_refund", "referral_reward": "referral_reward", "poll_reward": "poll_reward"}

func category(v any) string {
	s, _ := v.(string)
	if c, ok := categories[s]; ok {
		return c
	}
	return "unknown"
}
func direction(v any) string {
	s, _ := v.(string)
	switch s {
	case "deposit", "referral_reward", "poll_reward", "refund":
		return "credit"
	case "subscription_payment", "subscription_purchase", "gift_payment", "gift_purchase", "withdrawal", "failed_refund":
		return "debit"
	}
	return "unknown"
}
func accounting(v any) string {
	if b, ok := v.(bool); ok {
		if b {
			return "completed"
		}
		return "not_completed"
	}
	return "unknown"
}
func timestamp(v any) time.Time {
	s, ok := v.(string)
	if !ok {
		return time.Time{}
	}
	s = trim(s)
	for _, layout := range []string{time.RFC3339Nano, "2006-01-02T15:04:05.999999999", "2006-01-02 15:04:05.999999999Z07:00", "2006-01-02 15:04:05.999999999", "2006-01-02"} {
		if t, e := time.Parse(layout, s); e == nil {
			return t
		}
	}
	return time.Time{}
}
func effective(tx M) time.Time {
	if t := timestamp(tx["created_at"]); !t.IsZero() {
		return t
	}
	return timestamp(tx["completed_at"])
}
func newest(items []any) {
	sort.SliceStable(items, func(i, j int) bool {
		a, b := obj(items[i]), obj(items[j])
		ta, tb := effective(a), effective(b)
		if ta.Equal(tb) {
			return timestamp(a["completed_at"]).After(timestamp(b["completed_at"]))
		}
		return ta.After(tb)
	})
}
func capItems(a []any, limit int) []any {
	if limit <= 0 {
		limit = 20
	}
	if len(a) > limit {
		return a[:limit]
	}
	return a
}
func transaction(tx M) M {
	k, r := money(tx["amount_kopeks"], true)
	m := selectFields(tx, "id", "payment_method", "is_completed", "description", "created_at", "completed_at")
	m["raw_type"] = tx["type"]
	m["category"] = category(tx["type"])
	m["direction"] = direction(tx["type"])
	m["amount_kopeks"] = k
	m["amount_rubles"] = r
	return m
}
func summary(items []any, kind string) M {
	found := []any{}
	for _, v := range items {
		m := obj(v)
		if m["type"] == kind && m["is_completed"] == true {
			found = append(found, m)
		}
	}
	if len(found) == 0 {
		return nil
	}
	newest(found)
	m := obj(found[0])
	k, r := money(m["amount_kopeks"], true)
	return M{"amount_kopeks": k, "amount_rubles": r, "category": category(kind), "created_at": m["created_at"], "completed_at": m["completed_at"]}
}
func purchased(items []any) any {
	d := summary(items, "deposit")
	if d == nil {
		return nil
	}
	t := effective(d)
	if t.IsZero() {
		return nil
	}
	for _, v := range items {
		m := obj(v)
		if m["type"] == "subscription_payment" && m["is_completed"] == true && effective(m).After(t) {
			return true
		}
	}
	return false
}
func botRecord(v any) M {
	m, ok := v.(map[string]any)
	if !ok {
		return nil
	}
	out := selectFields(m, "id", "is_trial", "tariff_id", "tariff_name", "created_at", "start_date", "end_date", "autopay_enabled", "autopay_days_before")
	out["bot_record_status"] = m["status"]
	out["bot_record_effective_status"] = m["actual_status"]
	out["note"] = BOT_RECORD_NOTE
	return out
}
func botRecords(user M) []any {
	out := []any{}
	seen := map[string]bool{}
	for _, v := range arr(user["subscriptions"]) {
		m := botRecord(v)
		if m == nil {
			continue
		}
		id := m["id"]
		_, isInt := integer(id)
		_, isString := id.(string)
		if isInt || isString {
			key := ident(id)
			if seen[key] {
				continue
			}
			seen[key] = true
		}
		out = append(out, m)
	}
	if len(out) == 0 {
		if m := botRecord(user["subscription"]); m != nil {
			out = append(out, m)
		}
	}
	return out
}
func owned(user M, raw any) []any {
	out := []any{}
	for _, v := range arr(obj(raw)["items"]) {
		m, ok := v.(map[string]any)
		if !ok {
			continue
		}
		if user["id"] != nil && !equal(user["id"], m["user_id"]) {
			continue
		}
		out = append(out, m)
	}
	return out
}
func userData(user M) M {
	k, r := money(user["balance_kopeks"], false)
	out := selectFields(user, "telegram_id", "status", "has_made_first_topup", "has_had_paid_subscription", "referral_code", "created_at", "last_activity")
	out["found"] = true
	out["balance_kopeks"] = k
	out["balance_rubles"] = r
	out["was_referred"] = user["referred_by_id"] != nil
	parts := []string{}
	for _, key := range []string{"first_name", "last_name"} {
		if s, ok := user[key].(string); ok && trim(s) != "" {
			parts = append(parts, s)
		}
	}
	name := trim(strings.Join(parts, " "))
	if name == "" {
		if s, ok := user["username"].(string); ok && trim(s) != "" {
			name = s
		}
	}
	out["display_name"] = nil
	if name != "" {
		out["display_name"] = name
	}
	out["promo_group"] = nil
	if p, ok := user["promo_group"].(map[string]any); ok {
		out["promo_group"] = selectFields(p, "name", "server_discount_percent", "traffic_discount_percent", "device_discount_percent")
	}
	return out
}
func billingData(user M, raw any, limit int) M {
	items := owned(user, raw)
	recent := append([]any{}, items...)
	newest(recent)
	txs := []any{}
	for _, v := range capItems(recent, limit) {
		txs = append(txs, transaction(obj(v)))
	}
	k, r := money(user["balance_kopeks"], false)
	return M{"balance_kopeks": k, "balance_rubles": r, "transactions": txs, "latest_completed_deposit": summary(items, "deposit"), "latest_completed_subscription_purchase": summary(items, "subscription_payment"), "purchased_after_latest_deposit": purchased(items), "bot_subscriptions": botRecords(user), "meta": BILLING_META_NOTE}
}
func subscriptionData(user M, raw any, owner any) M {
	tariffs := M{}
	for _, v := range arr(user["subscriptions"]) {
		m := obj(v)
		if m["id"] != nil {
			tariffs[ident(m["id"])] = m
		}
	}
	single := obj(user["subscription"])
	if single["id"] != nil {
		key := ident(single["id"])
		if tariffs[key] == nil {
			tariffs[key] = single
		}
	}
	records := []any{}
	seen := map[string]bool{}
	if len(arr(raw)) > 0 {
		for _, v := range arr(raw) {
			m := obj(v)
			if m["user_id"] != nil && !equal(m["user_id"], owner) {
				continue
			}
			rec := botRecord(v)
			if rec == nil {
				continue
			}
			id := rec["id"]
			key := ident(id)
			if id != nil {
				if seen[key] {
					continue
				}
				seen[key] = true
			}
			t := obj(tariffs[key])
			for _, f := range []string{"tariff_id", "tariff_name"} {
				if rec[f] == nil && t[f] != nil {
					rec[f] = t[f]
				}
			}
			records = append(records, rec)
		}
	} else {
		records = botRecords(user)
	}
	active := func(m M) bool {
		s := m["bot_record_effective_status"]
		if s == nil || s == "" {
			s = m["bot_record_status"]
		}
		return s == "active"
	}
	sort.SliceStable(records, func(i, j int) bool {
		a, b := obj(records[i]), obj(records[j])
		if active(a) != active(b) {
			return active(a)
		}
		return timestamp(a["end_date"]).After(timestamp(b["end_date"]))
	})
	count := 0
	for _, v := range records {
		if active(obj(v)) {
			count++
		}
	}
	return M{"has_subscription_records": len(records) > 0, "active_record_count": count, "subscriptions": records, "meta": SUBSCRIPTION_META_NOTE}
}
func ticketsData(raw any, owner any) M {
	out := []any{}
	for _, v := range arr(raw) {
		m := obj(v)
		if m["user_id"] != nil && !equal(m["user_id"], owner) {
			continue
		}
		out = append(out, selectFields(m, "id", "title", "status", "priority", "created_at", "updated_at", "closed_at"))
	}
	return M{"has_tickets": len(out) > 0, "tickets": out, "meta": TICKETS_META_NOTE}
}
func paymentData(raw any, owner any, limit int, gifts bool) M {
	out := []any{}
	for _, v := range arr(obj(raw)["items"]) {
		tx, ok := v.(map[string]any)
		if !ok {
			continue
		}
		if tx["user_id"] != nil && !equal(tx["user_id"], owner) {
			continue
		}
		cat := category(tx["type"])
		if gifts {
			if cat != "gift_purchase" {
				continue
			}
		} else {
			switch cat {
			case "deposit", "subscription_purchase", "gift_purchase", "refund", "failed_refund":
			default:
				continue
			}
		}
		k, r := money(tx["amount_kopeks"], true)
		m := selectFields(tx, "id", "payment_method", "created_at", "completed_at")
		m["amount_kopeks"] = k
		m["amount_rubles"] = r
		m["accounting_status"] = accounting(tx["is_completed"])
		if !gifts {
			m["category"] = cat
			m["direction"] = direction(tx["type"])
			m["raw_type"] = tx["type"]
		}
		out = append(out, m)
	}
	newest(out)
	out = capItems(out, limit)
	if gifts {
		return M{"scope": "own_gift_purchase_transactions", "gift_purchases": out, "received_gifts_available": false, "activation_status_available": false, "meta": GIFTS_META_NOTE}
	}
	return M{"scope": "bedolaga_accounting_transactions", "payments": out, "meta": PAYMENT_STATUS_META_NOTE}
}
func referralData(detail, user M, raw any) M {
	ref := obj(detail["referrer"])
	out := selectFields(ref, "referral_code", "effective_referral_commission_percent", "invited_count", "active_referrals")
	out["was_referred"] = nil
	if _, ok := user["referred_by_id"]; ok {
		out["was_referred"] = user["referred_by_id"] != nil
	}
	for _, p := range []string{"total_earned", "month_earned"} {
		k, r := money(ref[p+"_kopeks"], false)
		out[p+"_kopeks"] = k
		out[p+"_rubles"] = r
	}
	rewards := []any{}
	for _, v := range owned(user, raw) {
		m := obj(v)
		if m["type"] == "referral_reward" && m["is_completed"] == true {
			rewards = append(rewards, transaction(m))
		}
	}
	newest(rewards)
	out["recent_referral_rewards"] = capItems(rewards, 20)
	out["meta"] = REFERRAL_META_NOTE
	return out
}
func maskCode(code string) string {
	r := []rune(trim(code))
	if len(r) >= 4 {
		return string(r[:2]) + "***" + string(r[len(r)-2:])
	}
	if len(r) >= 2 {
		return string(r[:1]) + "***" + string(r[len(r)-1:])
	}
	return "***"
}
func promoData(raw M, code string, incomplete bool) M {
	out := M{"scope": "global_promocode_definition", "code_masked": maskCode(code), "globally_valid": false, "reason_code": "not_found", "type": nil, "balance_bonus_kopeks": nil, "balance_bonus_rubles": nil, "subscription_days": 0, "traffic_gb": 0, "uses_left": nil, "valid_from": nil, "valid_until": nil, "user_eligibility": "unknown", "meta": PROMOCODE_META_NOTE}
	if raw == nil {
		if incomplete {
			out["reason_code"] = "lookup_incomplete"
		}
		return out
	}
	out["type"] = raw["type"]
	out["valid_from"] = raw["valid_from"]
	out["valid_until"] = raw["valid_until"]
	uses, validUses := integer(raw["uses_left"])
	if raw["uses_left"] == nil && raw["max_uses"] != nil && raw["current_uses"] != nil {
		a, ok := numeric(raw["max_uses"])
		b, bok := numeric(raw["current_uses"])
		if ok && bok && math.Trunc(a-b) == a-b {
			uses = int64(math.Max(0, a-b))
			validUses = true
		}
	}
	if validUses {
		out["uses_left"] = uses
	}
	now := time.Now()
	from, until := timestamp(raw["valid_from"]), timestamp(raw["valid_until"])
	switch {
	case raw["is_active"] != true:
		out["reason_code"] = "inactive"
	case !from.IsZero() && from.After(now):
		out["reason_code"] = "not_yet_valid"
	case raw["is_valid"] != true || (!until.IsZero() && until.Before(now)) || (validUses && uses <= 0):
		out["reason_code"] = "expired_or_exhausted"
	default:
		out["globally_valid"] = true
		out["reason_code"] = nil
	}
	k, r := money(raw["balance_bonus_kopeks"], false)
	out["balance_bonus_kopeks"] = k
	out["balance_bonus_rubles"] = r
	for _, f := range []string{"subscription_days", "traffic_gb"} {
		if n, ok := integer(raw[f]); ok && n >= 0 {
			out[f] = n
		}
	}
	return out
}
func numeric(v any) (float64, bool) {
	if n, ok := v.(json.Number); ok {
		f, e := strconv.ParseFloat(string(n), 64)
		return f, e == nil
	}
	if n, ok := integer(v); ok {
		return float64(n), true
	}
	return 0, false
}
