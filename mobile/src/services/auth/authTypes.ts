import type { StoaRole } from "@/navigation/routes";

export type AuthFlowState =
  | "anonymous"
  | "signed_in"
  | "email_verification_required"
  | "session_expired"
  | "provider_blocked";

export type MobileSession = {
  userId: string;
  email: string;
  roles: StoaRole[];
  accessToken: string;
  expiresAt: string | null;
};

export type RegisterInput = {
  email: string;
  password: string;
  role: StoaRole;
  displayName: string;
};

export type SignInInput = {
  email: string;
  password: string;
};

export type VerifyEmailInput = {
  email: string;
  code: string;
};

export type AuthErrorCode =
  | "email_verification_required"
  | "invalid_credentials"
  | "session_expired"
  | "provider_blocked"
  | "network_unavailable"
  | "unknown";

export class MobileAuthError extends Error {
  code: AuthErrorCode;

  constructor(code: AuthErrorCode, message: string) {
    super(message);
    this.name = "MobileAuthError";
    this.code = code;
  }
}
