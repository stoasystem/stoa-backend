export type BuildProfileName = "development" | "preview" | "production";

export type BuildCommand = {
  profile: BuildProfileName;
  platform: "ios" | "android" | "all";
  command: string;
  distribution: "internal" | "store";
  requiresCredentials: string[];
};

export type BuildArtifactEvidence = {
  buildId: string;
  commitSha: string;
  profile: BuildProfileName;
  platform: "ios" | "android";
  apiEnvironment: string;
  createdAt: string;
  distributionAudience: string;
  releaseChannel: string;
  secretSafe: true;
};

export const INTERNAL_BUILD_COMMANDS: BuildCommand[] = [
  {
    profile: "development",
    platform: "all",
    command: "eas build --platform all --profile development",
    distribution: "internal",
    requiresCredentials: ["expo_project_id", "apple_developer_account", "google_play_account"]
  },
  {
    profile: "preview",
    platform: "all",
    command: "eas build --platform all --profile preview",
    distribution: "internal",
    requiresCredentials: ["expo_project_id", "apple_developer_account", "google_play_account"]
  }
];

export const ROLLBACK_INSTRUCTIONS = [
  "Stop distributing the blocked internal build link.",
  "Promote the last known-good EAS update channel only after release owner approval.",
  "Disable production mutation flags for mobile clients if account-state or quota behavior regresses.",
  "Record rollback build ID, reason, owner, and user-facing support message."
] as const;

export const assertBuildEvidenceSecretSafe = (evidence: BuildArtifactEvidence): void => {
  const serialized = JSON.stringify(evidence).toLowerCase();
  for (const forbidden of ["secret", "token", "provider_payload", "private_s3_key", "cognito"]) {
    if (serialized.includes(forbidden)) {
      throw new Error(`Build evidence includes forbidden material: ${forbidden}`);
    }
  }
};
