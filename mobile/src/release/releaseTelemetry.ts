export type MobileReleaseSignal =
  | "app_started"
  | "route_loaded"
  | "auth_state_changed"
  | "push_state_changed"
  | "offline_state_changed"
  | "native_build_blocked"
  | "native_build_available"
  | "mobile_regression_detected";

export type MobileReleaseHealthEvent = {
  signal: MobileReleaseSignal;
  buildProfile: "development" | "preview" | "production";
  appVersion: string;
  routeGroup: "auth" | "student" | "parent" | "notifications" | "blocked" | "system";
  accountState:
    | "ready"
    | "verification_required"
    | "entitlement_required"
    | "billing_action_required"
    | "provider_blocked"
    | "session_expired"
    | "unknown";
  pushState: "unknown" | "granted" | "denied" | "unavailable" | "provider_blocked";
  offlineState: "online" | "offline_fresh" | "offline_stale" | "not_applicable";
  blockerCategory:
    | "none"
    | "credential_config"
    | "provider_blocker"
    | "product_regression"
    | "user_permission"
    | "stale_data";
};

export const FORBIDDEN_TELEMETRY_FIELDS = [
  "raw_prompt",
  "raw_answer",
  "chat_transcript",
  "token",
  "secret",
  "provider_payload",
  "billing_payload",
  "private_user_id",
  "private_s3_key",
  "free_text"
] as const;

export const classifyMobileReleaseEvent = (
  event: MobileReleaseHealthEvent
): "healthy" | "blocked" | "regression" | "permission_denied" | "stale" => {
  if (event.blockerCategory === "product_regression") {
    return "regression";
  }
  if (event.blockerCategory === "credential_config" || event.blockerCategory === "provider_blocker") {
    return "blocked";
  }
  if (event.blockerCategory === "user_permission") {
    return "permission_denied";
  }
  if (event.blockerCategory === "stale_data") {
    return "stale";
  }
  return "healthy";
};
