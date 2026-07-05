export type MobileEnvironmentName = "development" | "preview" | "production";

export type MobileConfig = {
  apiBaseUrl: string;
  cognitoRegion: string;
  cognitoUserPoolId: string;
  cognitoClientId: string;
  expoProjectId: string | null;
  releaseChannel: MobileEnvironmentName;
  noDemoFallback: boolean;
};

const required = (name: keyof NodeJS.ProcessEnv): string => {
  const value = process.env[name];
  if (!value || value.trim().length === 0) {
    throw new Error(`Missing required mobile environment value: ${name}`);
  }
  return value.trim();
};

const releaseChannel = (): MobileEnvironmentName => {
  const value = process.env.EXPO_PUBLIC_STOA_RELEASE_CHANNEL;
  if (value === "preview" || value === "production") {
    return value;
  }
  return "development";
};

export const getMobileConfig = (): MobileConfig => ({
  apiBaseUrl: required("EXPO_PUBLIC_STOA_API_BASE_URL").replace(/\/+$/, ""),
  cognitoRegion: required("EXPO_PUBLIC_STOA_COGNITO_REGION"),
  cognitoUserPoolId: required("EXPO_PUBLIC_STOA_COGNITO_USER_POOL_ID"),
  cognitoClientId: required("EXPO_PUBLIC_STOA_COGNITO_CLIENT_ID"),
  expoProjectId: process.env.EXPO_PUBLIC_STOA_EXPO_PROJECT_ID?.trim() || null,
  releaseChannel: releaseChannel(),
  noDemoFallback: process.env.EXPO_PUBLIC_STOA_NO_DEMO_FALLBACK !== "false"
});

export const assertNoDemoFallback = (config: MobileConfig): void => {
  if (!config.noDemoFallback) {
    throw new Error("Mobile no-demo-fallback mode must stay enabled for STOA release builds.");
  }
};
