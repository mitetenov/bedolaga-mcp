package bedolaga

import (
	"bytes"
	_ "embed"
	"encoding/json"
	"fmt"
	"reflect"
	"testing"
)

// These golden cases were captured by running the committed Python unit suite
// before replacing that implementation. They exercise its real normalization,
// privacy, ownership, chronology and money contracts without a Python runtime.
//
//go:embed golden.json
var goldens []byte

func decodeJSON(b []byte) any {
	d := json.NewDecoder(bytes.NewReader(b))
	d.UseNumber()
	var v any
	if e := d.Decode(&v); e != nil {
		panic(e)
	}
	return v
}
func normalized(v any) any {
	b, e := json.Marshal(v)
	if e != nil {
		panic(e)
	}
	var out any
	json.Unmarshal(b, &out)
	return out
}
func TestCommittedContractGolden(t *testing.T) {
	for i, v := range arr(decodeJSON(goldens)) {
		m := obj(v)
		name := m["name"].(string)
		args := arr(m["args"])
		kwargs := obj(m["kwargs"])
		t.Run(fmt.Sprintf("%03d_%s", i, name), func(t *testing.T) {
			arg := func(i int) any {
				if i < len(args) {
					return args[i]
				}
				return nil
			}
			limit := func(i int, def int) int {
				v := arg(i)
				if v == nil {
					v = kwargs["limit"]
				}
				n, ok := integer(v)
				if !ok {
					return def
				}
				return int(n)
			}
			owner := func(i int) any {
				v := arg(i)
				if v == nil {
					v = kwargs["owner_id"]
				}
				return v
			}
			var got any
			switch name {
			case "sanitize_user":
				got = userData(obj(arg(0)))
			case "sanitize_billing":
				got = billingData(obj(arg(0)), arg(1), limit(2, 20))
			case "sanitize_subscriptions":
				got = subscriptionData(obj(arg(0)), arg(1), owner(2))
			case "sanitize_referrals":
				got = referralData(obj(arg(0)), obj(kwargs["raw_user"]), kwargs["raw_referral_transactions"])
			case "sanitize_tickets":
				got = ticketsData(arg(0), owner(1))
			case "sanitize_payment_status":
				got = paymentData(arg(0), owner(1), limit(2, 5), false)
			case "sanitize_gifts":
				got = paymentData(arg(0), owner(1), limit(2, 20), true)
			case "sanitize_promocode":
				var raw M
				if arg(0) != nil {
					raw = obj(arg(0))
				}
				code, _ := arg(1).(string)
				incomplete, _ := kwargs["lookup_incomplete"].(bool)
				got = promoData(raw, code, incomplete)
			case "accounting_status":
				got = accounting(arg(0))
			case "bot_subscription_record":
				got = botRecord(arg(0))
			case "bot_subscription_records":
				got = botRecords(obj(arg(0)))
			case "latest_completed_deposit":
				got = summary(arr(arg(0)), "deposit")
			case "latest_completed_subscription_purchase":
				got = summary(arr(arg(0)), "subscription_payment")
			case "purchased_after_latest_deposit":
				got = purchased(arr(arg(0)))
			case "mask_code":
				got = maskCode(arg(0).(string))
			case "money_pair", "amount_money", "balance_money", "total_earned_money", "month_earned_money":
				k, r := money(arg(0), name == "amount_money")
				if k == nil {
					got = nil
					break
				}
				if name == "money_pair" {
					got = M{"kopeks": k, "rubles": r}
					break
				}
				prefix := map[string]string{"amount_money": "amount", "balance_money": "balance", "total_earned_money": "total_earned", "month_earned_money": "month_earned"}[name]
				got = M{prefix + "_kopeks": k, prefix + "_rubles": r}
			default:
				t.Fatalf("unhandled golden function %s", name)
			}
			if !reflect.DeepEqual(normalized(got), normalized(m["expected"])) {
				a, _ := json.Marshal(got)
				b, _ := json.Marshal(m["expected"])
				t.Fatalf("got %s\nwant %s", a, b)
			}
		})
	}
}
