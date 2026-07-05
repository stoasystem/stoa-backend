import { accountStateFromApiError, type AccountState } from "@/services/auth/accountState";
import { MobileApiError } from "@/services/api/mobileApiClient";

export type JourneyState<T> =
  | { status: "loading" }
  | { status: "ready"; data: T; stale: boolean }
  | { status: "empty"; title: string; message: string }
  | { status: "blocked"; accountState: AccountState }
  | { status: "error"; title: string; message: string; retryable: boolean };

export const readyJourneyState = <T>(data: T, stale = false): JourneyState<T> => ({
  status: "ready",
  data,
  stale
});

export const emptyJourneyState = <T>(title: string, message: string): JourneyState<T> => ({
  status: "empty",
  title,
  message
});

export const journeyStateFromError = <T>(error: unknown): JourneyState<T> => {
  if (error instanceof MobileApiError) {
    const accountState = accountStateFromApiError({
      status: error.status,
      code: error.body.code,
      support_code: error.body.support_code,
      message: error.body.detail
    });
    if (accountState.kind !== "unknown") {
      return { status: "blocked", accountState };
    }
  }

  return {
    status: "error",
    title: "Could not load this STOA view",
    message: "Check your connection and try again.",
    retryable: true
  };
};

export const REQUIRED_SCREEN_STATES = ["loading", "ready", "empty", "blocked", "stale", "error"] as const;
