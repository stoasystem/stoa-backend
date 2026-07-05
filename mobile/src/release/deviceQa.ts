export type DevicePlatform = "ios" | "android";
export type QaStatus = "pending" | "passed" | "blocked" | "failed" | "deferred";

export type DeviceQaTarget = {
  id: string;
  platform: DevicePlatform;
  minimumCoverage: string;
  status: QaStatus;
  blocker: string | null;
};

export type MobileSmokeStep = {
  id: string;
  label: string;
  routeOrCapability: string;
  requiresNetwork: boolean;
  requiresPushCredentials: boolean;
  evidenceKind: "redacted_screenshot" | "redacted_log" | "operator_note";
  forbiddenEvidence: string[];
};

export const DEVICE_QA_TARGETS: DeviceQaTarget[] = [
  {
    id: "ios_phone",
    platform: "ios",
    minimumCoverage: "At least one currently supported iPhone",
    status: "blocked",
    blocker: "No physical iOS device and Apple signing evidence recorded in this repository."
  },
  {
    id: "android_phone",
    platform: "android",
    minimumCoverage: "At least one Android phone supported by Expo SDK 57",
    status: "blocked",
    blocker: "No physical Android device and Android signing evidence recorded in this repository."
  }
];

export const MOBILE_SMOKE_STEPS: MobileSmokeStep[] = [
  {
    id: "auth_session_restore",
    label: "Sign in and session restore",
    routeOrCapability: "/auth/sign-in",
    requiresNetwork: true,
    requiresPushCredentials: false,
    evidenceKind: "redacted_screenshot",
    forbiddenEvidence: ["password", "token", "cognito_token_material"]
  },
  {
    id: "student_dashboard_practice",
    label: "Student dashboard and practice",
    routeOrCapability: "/student/practice",
    requiresNetwork: true,
    requiresPushCredentials: false,
    evidenceKind: "redacted_screenshot",
    forbiddenEvidence: ["raw_prompt", "raw_answer"]
  },
  {
    id: "parent_child_report",
    label: "Parent child summary and report",
    routeOrCapability: "/parent/children/{childId}/report",
    requiresNetwork: true,
    requiresPushCredentials: false,
    evidenceKind: "redacted_screenshot",
    forbiddenEvidence: ["generated_report_artifact", "private_object_key"]
  },
  {
    id: "push_deep_link",
    label: "Push token registration and notification deep link",
    routeOrCapability: "push_and_deep_link",
    requiresNetwork: true,
    requiresPushCredentials: true,
    evidenceKind: "redacted_log",
    forbiddenEvidence: ["push_token", "provider_payload"]
  },
  {
    id: "offline_read_through",
    label: "Offline read-through stale state",
    routeOrCapability: "offline_cache",
    requiresNetwork: false,
    requiresPushCredentials: false,
    evidenceKind: "redacted_screenshot",
    forbiddenEvidence: ["raw_prompt", "raw_answer", "billing_payload"]
  },
  {
    id: "sign_out_cleanup",
    label: "Sign-out cleanup",
    routeOrCapability: "sign_out",
    requiresNetwork: true,
    requiresPushCredentials: false,
    evidenceKind: "operator_note",
    forbiddenEvidence: ["token", "secret"]
  }
];
