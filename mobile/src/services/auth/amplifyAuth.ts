import { Amplify } from "aws-amplify";
import {
  confirmSignUp,
  fetchAuthSession,
  getCurrentUser,
  resendSignUpCode,
  signIn,
  signOut,
  signUp
} from "aws-amplify/auth";
import type { MobileConfig } from "@/config/mobileConfig";
import type { MobileSession, RegisterInput, SignInInput, VerifyEmailInput } from "./authTypes";
import { MobileAuthError } from "./authTypes";

export const configureAmplifyAuth = (config: MobileConfig): void => {
  Amplify.configure({
    Auth: {
      Cognito: {
        userPoolId: config.cognitoUserPoolId,
        userPoolClientId: config.cognitoClientId,
        loginWith: {
          email: true
        }
      }
    }
  });
};

export const getAccessToken = async (): Promise<string> => {
  try {
    const session = await fetchAuthSession();
    const token = session.tokens?.accessToken?.toString();
    if (!token) {
      throw new MobileAuthError("session_expired", "Your STOA session has expired. Sign in again.");
    }
    return token;
  } catch (error) {
    if (error instanceof MobileAuthError) {
      throw error;
    }
    throw new MobileAuthError("session_expired", "We could not restore your STOA session.");
  }
};

export const restoreMobileSession = async (): Promise<MobileSession> => {
  const [user, session] = await Promise.all([getCurrentUser(), fetchAuthSession()]);
  const accessToken = session.tokens?.accessToken?.toString();
  const payload = session.tokens?.idToken?.payload ?? {};
  const rawRoles = payload["custom:roles"] ?? payload["cognito:groups"] ?? [];
  const roles = Array.isArray(rawRoles) ? rawRoles : String(rawRoles).split(",");

  if (!accessToken) {
    throw new MobileAuthError("session_expired", "Your STOA session has expired. Sign in again.");
  }

  return {
    userId: user.userId,
    email: String(payload.email ?? user.signInDetails?.loginId ?? ""),
    roles: roles.filter((role): role is "student" | "parent" => role === "student" || role === "parent"),
    accessToken,
    expiresAt: session.tokens?.accessToken?.payload.exp
      ? new Date(Number(session.tokens.accessToken.payload.exp) * 1000).toISOString()
      : null
  };
};

export const signInWithEmail = async ({ email, password }: SignInInput): Promise<void> => {
  const result = await signIn({ username: email, password });
  if (result.nextStep.signInStep === "CONFIRM_SIGN_UP") {
    throw new MobileAuthError(
      "email_verification_required",
      "Email verification is required before sign-in."
    );
  }
};

export const registerWithEmail = async ({ email, password, role, displayName }: RegisterInput) => {
  return signUp({
    username: email,
    password,
    options: {
      userAttributes: {
        email,
        name: displayName,
        "custom:role": role
      },
      autoSignIn: false
    }
  });
};

export const verifyEmailCode = async ({ email, code }: VerifyEmailInput): Promise<void> => {
  await confirmSignUp({ username: email, confirmationCode: code });
};

export const resendVerificationCode = async (email: string): Promise<void> => {
  await resendSignUpCode({ username: email });
};

export const signOutOfStoa = async (): Promise<void> => {
  await signOut();
};
