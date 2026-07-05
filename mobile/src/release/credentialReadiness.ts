export type CredentialState = "ready" | "blocked" | "not_required";

export type CredentialReadinessItem = {
  key: string;
  label: string;
  state: CredentialState;
  owner: "engineering" | "release" | "apple" | "google" | "product";
  requiredFor: string[];
  action: string;
  secretSafe: true;
};

export type MobileEnvironmentProfile = {
  name: "local" | "staging" | "production_read_only" | "safe_fixture";
  apiMutationPolicy: "local_only" | "read_only" | "safe_fixture_only";
  customerImpact: "none" | "approved_fixture_only";
};

export const MOBILE_ENVIRONMENT_PROFILES: MobileEnvironmentProfile[] = [
  {
    name: "local",
    apiMutationPolicy: "local_only",
    customerImpact: "none"
  },
  {
    name: "staging",
    apiMutationPolicy: "safe_fixture_only",
    customerImpact: "approved_fixture_only"
  },
  {
    name: "production_read_only",
    apiMutationPolicy: "read_only",
    customerImpact: "none"
  },
  {
    name: "safe_fixture",
    apiMutationPolicy: "safe_fixture_only",
    customerImpact: "approved_fixture_only"
  }
];

export const MOBILE_CREDENTIAL_READINESS: CredentialReadinessItem[] = [
  {
    key: "expo_project_id",
    label: "Expo project ID",
    state: "blocked",
    owner: "engineering",
    requiredFor: ["eas_build", "push_token_registration"],
    action: "Create or confirm the Expo/EAS project and provide EXPO_PUBLIC_STOA_EXPO_PROJECT_ID.",
    secretSafe: true
  },
  {
    key: "apple_developer_account",
    label: "Apple Developer account and signing credentials",
    state: "blocked",
    owner: "apple",
    requiredFor: ["ios_internal_build", "ios_push", "app_store_submission"],
    action: "Confirm Apple team, bundle ID ownership, signing certificates, profiles, and APNs capability.",
    secretSafe: true
  },
  {
    key: "google_play_account",
    label: "Google Play account and Android signing credentials",
    state: "blocked",
    owner: "google",
    requiredFor: ["android_internal_build", "play_store_submission"],
    action: "Confirm package ownership, upload key policy, and internal distribution track.",
    secretSafe: true
  },
  {
    key: "fcm_credentials",
    label: "FCM credentials",
    state: "blocked",
    owner: "google",
    requiredFor: ["android_push"],
    action: "Configure FCM credentials for Expo/EAS push delivery.",
    secretSafe: true
  },
  {
    key: "production_rollout_approval",
    label: "Production rollout approval",
    state: "blocked",
    owner: "product",
    requiredFor: ["production_mutation", "public_launch"],
    action: "Approve rollout cohort, mutation policy, support staffing, rollback, and monitoring.",
    secretSafe: true
  }
];

export const getBlockedCredentials = (): CredentialReadinessItem[] =>
  MOBILE_CREDENTIAL_READINESS.filter((item) => item.state === "blocked");
