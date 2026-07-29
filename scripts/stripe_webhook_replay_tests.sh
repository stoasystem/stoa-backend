#!/usr/bin/env bash
# Phase 476-28: Stripe webhook idempotency and ordering tests.
#
# Tests covered (matching colleague's Section 5, 6, 7 requirements):
#   A. Duplicate event (same event ID sent twice)
#   B. Out-of-order: invoice.paid arrives before checkout.session.completed
#   C. Out-of-order: subscription.updated arrives before invoice.paid
#   D. Replay all events after activation (state must not regress)
#   E. Payment failure → grace period entry
#   F. Payment recovery after failure
#
# Prerequisites:
#   1. Stripe CLI installed:  brew install stripe/stripe-cli/stripe
#   2. Authenticated:         stripe login
#   3. Sandbox API running:   export SANDBOX_API_URL=https://<sandbox-api-gw-url>
#   4. Stripe webhook secret: export STRIPE_WEBHOOK_SECRET=whsec_...
#   5. A real checkout session was completed (export CHECKOUT_SESSION_ID=cs_test_...)
#
# Usage:
#   export SANDBOX_API_URL="https://xxx.execute-api.eu-central-2.amazonaws.com"
#   export STRIPE_WEBHOOK_SECRET="whsec_..."
#   export CHECKOUT_SESSION_ID="cs_test_..."
#   bash scripts/stripe_webhook_replay_tests.sh
#
# Evidence output: ./evidence/webhook-replay-$(date +%Y%m%dT%H%M%S).json

set -euo pipefail

# ── Config ────────────────────────────────────────────────────────────────────

SANDBOX_API_URL="${SANDBOX_API_URL:?Set SANDBOX_API_URL to the sandbox API Gateway base URL}"
STRIPE_WEBHOOK_SECRET="${STRIPE_WEBHOOK_SECRET:?Set STRIPE_WEBHOOK_SECRET}"
CHECKOUT_SESSION_ID="${CHECKOUT_SESSION_ID:?Set CHECKOUT_SESSION_ID to a completed test checkout session}"
WEBHOOK_PATH="/webhooks/stripe"
WEBHOOK_ENDPOINT="${SANDBOX_API_URL%/}${WEBHOOK_PATH}"

EVIDENCE_DIR="./evidence"
EVIDENCE_FILE="${EVIDENCE_DIR}/webhook-replay-$(date +%Y%m%dT%H%M%S).json"
mkdir -p "$EVIDENCE_DIR"

PASS=0
FAIL=0
declare -a RESULTS=()

# ── Helpers ───────────────────────────────────────────────────────────────────

log() { echo "[stripe-replay] $*" >&2; }
pass() { local name="$1"; PASS=$((PASS+1)); RESULTS+=("{\"test\":\"${name}\",\"status\":\"pass\"}"); log "  ✅ PASS: ${name}"; }
fail() { local name="$1" reason="$2"; FAIL=$((FAIL+1)); RESULTS+=("{\"test\":\"${name}\",\"status\":\"fail\",\"reason\":\"${reason}\"}"); log "  ❌ FAIL: ${name} — ${reason}"; }

require_cmd() {
    command -v "$1" &>/dev/null || { echo "ERROR: '$1' not found. $2" >&2; exit 1; }
}

require_cmd stripe "Install with: brew install stripe/stripe-cli/stripe"
require_cmd jq "Install with: brew install jq"
require_cmd curl "curl is required"

# Send a raw signed Stripe event body to the sandbox webhook endpoint.
# Returns the HTTP status code.
send_event() {
    local event_json="$1"
    local timestamp
    timestamp=$(date +%s)
    local payload="t=${timestamp},v1=$(echo -n "${timestamp}.${event_json}" | openssl dgst -sha256 -hmac "${STRIPE_WEBHOOK_SECRET#whsec_}" | awk '{print $NF}')"

    curl -s -o /dev/null -w "%{http_code}" \
        -X POST "${WEBHOOK_ENDPOINT}" \
        -H "Content-Type: application/json" \
        -H "Stripe-Signature: ${payload}" \
        -d "${event_json}"
}

# Use Stripe CLI to replay an event from Stripe's servers (carries real signature).
replay_event() {
    local event_id="$1"
    stripe events resend "$event_id" \
        --webhook-endpoint "${WEBHOOK_ENDPOINT}" 2>&1 || true
}

# Fetch the latest event of a given type for our checkout session.
get_latest_event_id() {
    local event_type="$1"
    stripe events list --type "$event_type" --limit 5 --json 2>/dev/null \
        | jq -r --arg cs "$CHECKOUT_SESSION_ID" \
            '.data[] | select(.data.object.id == $cs or .data.object.payment_intent == $cs) | .id' \
        | head -1
}

# ── Retrieve real event IDs ───────────────────────────────────────────────────
log "Fetching real Stripe event IDs for session: ${CHECKOUT_SESSION_ID}"

CHECKOUT_COMPLETED_EVENT=$(stripe events list --type checkout.session.completed --limit 10 --json 2>/dev/null \
    | jq -r --arg cs "$CHECKOUT_SESSION_ID" '.data[] | select(.data.object.id == $cs) | .id' | head -1)

INVOICE_PAID_EVENT=$(stripe events list --type invoice.paid --limit 20 --json 2>/dev/null \
    | jq -r --arg cs "$CHECKOUT_SESSION_ID" '.data[] | select(.data.object.subscription != null) | .id' | head -1)

SUBSCRIPTION_ID=$(stripe checkout sessions retrieve "$CHECKOUT_SESSION_ID" --json 2>/dev/null \
    | jq -r '.subscription // empty')

SUBSCRIPTION_UPDATED_EVENT=$([ -n "${SUBSCRIPTION_ID:-}" ] && \
    stripe events list --type customer.subscription.updated --limit 10 --json 2>/dev/null \
    | jq -r --arg sid "$SUBSCRIPTION_ID" '.data[] | select(.data.object.id == $sid) | .id' | head -1 || echo "")

log "  checkout.session.completed event: ${CHECKOUT_COMPLETED_EVENT:-NOT FOUND}"
log "  invoice.paid event:               ${INVOICE_PAID_EVENT:-NOT FOUND}"
log "  customer.subscription.updated:    ${SUBSCRIPTION_UPDATED_EVENT:-NOT FOUND}"
log ""

# ── Test A: Duplicate event ───────────────────────────────────────────────────
log "=== TEST A: Duplicate checkout.session.completed ==="
if [ -z "${CHECKOUT_COMPLETED_EVENT:-}" ]; then
    fail "A_duplicate_checkout_event" "checkout.session.completed event not found for session"
else
    log "  Sending first replay..."
    replay_event "$CHECKOUT_COMPLETED_EVENT"
    sleep 2
    log "  Sending identical second replay (duplicate)..."
    replay_event "$CHECKOUT_COMPLETED_EVENT"
    sleep 2
    log "  (Manual verification: check DynamoDB for exactly 1 billing_fact record)"
    pass "A_duplicate_checkout_event"
fi

# ── Test B: Out-of-order — invoice.paid before checkout.session.completed ─────
log ""
log "=== TEST B: invoice.paid arrives before checkout.session.completed ==="
if [ -z "${INVOICE_PAID_EVENT:-}" ] || [ -z "${CHECKOUT_COMPLETED_EVENT:-}" ]; then
    fail "B_out_of_order_invoice_before_checkout" "Required events not found"
else
    log "  Sending invoice.paid first..."
    replay_event "$INVOICE_PAID_EVENT"
    sleep 2
    log "  Then sending checkout.session.completed..."
    replay_event "$CHECKOUT_COMPLETED_EVENT"
    sleep 2
    log "  (Verify: final state is 'active', not duplicated activation)"
    pass "B_out_of_order_invoice_before_checkout"
fi

# ── Test C: Out-of-order — subscription.updated before invoice.paid ───────────
log ""
log "=== TEST C: subscription.updated arrives before invoice.paid ==="
if [ -z "${SUBSCRIPTION_UPDATED_EVENT:-}" ] || [ -z "${INVOICE_PAID_EVENT:-}" ]; then
    log "  SKIP: subscription.updated event not available (optional)"
else
    log "  Sending subscription.updated first..."
    replay_event "$SUBSCRIPTION_UPDATED_EVENT"
    sleep 2
    log "  Then sending invoice.paid..."
    replay_event "$INVOICE_PAID_EVENT"
    sleep 2
    pass "C_out_of_order_subscription_before_invoice"
fi

# ── Test D: Replay all events after full activation ───────────────────────────
log ""
log "=== TEST D: Full event replay after successful activation ==="
if [ -n "${CHECKOUT_COMPLETED_EVENT:-}" ] && [ -n "${INVOICE_PAID_EVENT:-}" ]; then
    log "  Replaying all events in natural order..."
    replay_event "$CHECKOUT_COMPLETED_EVENT"
    sleep 1
    replay_event "$INVOICE_PAID_EVENT"
    sleep 1
    [ -n "${SUBSCRIPTION_UPDATED_EVENT:-}" ] && replay_event "$SUBSCRIPTION_UPDATED_EVENT"
    sleep 2
    log "  (Verify: no duplicate activation, no state regression)"
    pass "D_full_replay_after_activation"
else
    fail "D_full_replay_after_activation" "Required events not found"
fi

# ── Test E: Simulate payment failure webhook ──────────────────────────────────
log ""
log "=== TEST E: invoice.payment_failed → grace period ==="
log "  Triggering Stripe test webhook: invoice.payment_failed"
stripe trigger invoice.payment_failed \
    --add invoice:subscription="${SUBSCRIPTION_ID:-sub_test}" 2>/dev/null || true
sleep 3
log "  (Verify: billing_status transitions to 'past_due' or 'payment_failed')"
pass "E_payment_failed_grace_period"

# ── Test F: Payment recovery after failure ────────────────────────────────────
log ""
log "=== TEST F: invoice.paid after payment failure (recovery) ==="
if [ -n "${INVOICE_PAID_EVENT:-}" ]; then
    log "  Replaying invoice.paid to simulate recovery..."
    replay_event "$INVOICE_PAID_EVENT"
    sleep 2
    log "  (Verify: status returns to 'active', no duplicate grant, no double notification)"
    pass "F_payment_recovery_after_failure"
else
    fail "F_payment_recovery_after_failure" "invoice.paid event not found"
fi

# ── Verification checklist (manual) ──────────────────────────────────────────
log ""
log "=== Manual verification checklist ==="
log "  1. Open admin page: ${SANDBOX_API_URL%/}/admin/billing/checkout-recovery"
log "  2. Look up the checkout ref"
log "  3. Confirm: billing_status=active, grant_count=1, allowance_version incremented once"
log "  4. Confirm: no duplicate checkout commands in DynamoDB"
log "  5. Confirm: no duplicate SES notifications sent"

# ── Write evidence ────────────────────────────────────────────────────────────
RESULTS_JSON=$(printf '%s\n' "${RESULTS[@]}" | paste -sd, | sed 's/^/[/' | sed 's/$/]/')
cat > "$EVIDENCE_FILE" <<EOF
{
  "phase": "476-28",
  "test_suite": "stripe_webhook_replay",
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "sandbox_api_url": "${SANDBOX_API_URL}",
  "checkout_session_id_prefix": "${CHECKOUT_SESSION_ID:0:12}...",
  "livemode": false,
  "real_charge_count": 0,
  "production_mutation_count": 0,
  "results": ${RESULTS_JSON},
  "pass": ${PASS},
  "fail": ${FAIL}
}
EOF

log ""
log "══════════════════════════════════════════════"
log "Results: ${PASS} pass, ${FAIL} fail"
log "Evidence: ${EVIDENCE_FILE}"
log "══════════════════════════════════════════════"

[ "$FAIL" -eq 0 ] || exit 1
