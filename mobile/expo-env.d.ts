/// <reference types="expo/types" />

declare namespace NodeJS {
  interface ProcessEnv {
    EXPO_PUBLIC_STOA_API_BASE_URL?: string;
    EXPO_PUBLIC_STOA_COGNITO_REGION?: string;
    EXPO_PUBLIC_STOA_COGNITO_USER_POOL_ID?: string;
    EXPO_PUBLIC_STOA_COGNITO_CLIENT_ID?: string;
    EXPO_PUBLIC_STOA_EXPO_PROJECT_ID?: string;
    EXPO_PUBLIC_STOA_RELEASE_CHANNEL?: string;
    EXPO_PUBLIC_STOA_NO_DEMO_FALLBACK?: string;
  }
}
