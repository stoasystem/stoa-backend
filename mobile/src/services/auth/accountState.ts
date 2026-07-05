export type AccountStateKind =
  | "ready"
  | "verification_required"
  | "session_expired"
  | "entitlement_required"
  | "billing_action_required"
  | "child_binding_required"
  | "quota_exhausted"
  | "provider_blocked"
  | "unauthorized"
  | "forbidden"
  | "unknown";

export type AccountState = {
  kind: AccountStateKind;
  title: string;
  message: string;
  supportCode: string;
  retryable: boolean;
};

type ApiErrorLike = {
  status?: number;
  code?: string;
  message?: string;
  support_code?: string;
};

const state = (
  kind: AccountStateKind,
  title: string,
  message: string,
  supportCode: string,
  retryable = false
): AccountState => ({
  kind,
  title,
  message,
  supportCode,
  retryable
});

export const readyAccountState = (): AccountState =>
  state("ready", "Ready", "Your STOA account is ready.", "account.ready");

export const accountStateFromApiError = (error: ApiErrorLike): AccountState => {
  const code = error.code ?? error.support_code ?? "";

  if (code.includes("verification")) {
    return state(
      "verification_required",
      "Verify your email",
      "Email verification is required before STOA can continue.",
      "account.verification_required"
    );
  }

  if (code.includes("entitlement") || code.includes("paid_access")) {
    return state(
      "entitlement_required",
      "Plan required",
      "Your current access does not include this STOA feature.",
      "account.entitlement_required"
    );
  }

  if (code.includes("billing") || code.includes("subscription")) {
    return state(
      "billing_action_required",
      "Billing action needed",
      "Review your subscription before continuing.",
      "account.billing_action_required"
    );
  }

  if (code.includes("child_binding")) {
    return state(
      "child_binding_required",
      "Child profile needed",
      "Connect a child profile before opening this parent view.",
      "account.child_binding_required"
    );
  }

  if (code.includes("quota")) {
    return state(
      "quota_exhausted",
      "Usage limit reached",
      "Your available STOA usage has been used for this period.",
      "account.quota_exhausted"
    );
  }

  if (code.includes("provider")) {
    return state(
      "provider_blocked",
      "Provider unavailable",
      "A required STOA provider is not available right now.",
      "account.provider_blocked",
      true
    );
  }

  if (error.status === 401) {
    return state(
      "session_expired",
      "Sign in again",
      "Your STOA session has expired. Sign in again to continue.",
      "account.session_expired",
      true
    );
  }

  if (error.status === 403) {
    return state(
      "forbidden",
      "Access unavailable",
      error.message || "Your account cannot access this STOA view.",
      "account.forbidden"
    );
  }

  return state(
    "unknown",
    "Something went wrong",
    "We could not load this STOA account state.",
    "account.unknown",
    true
  );
};
