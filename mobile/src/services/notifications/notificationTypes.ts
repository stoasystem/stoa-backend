import type { StoaRole } from "@/navigation/routes";

export type PushPermissionState =
  | "unknown"
  | "granted"
  | "denied"
  | "unavailable"
  | "provider_blocked";

export type PushTokenRegistration = {
  provider: "expo";
  tokenReference: string;
  deviceId?: string;
  platform?: "ios" | "android" | "web" | "unknown";
};

export type NotificationRouteTarget =
  | { kind: "student_dashboard" }
  | { kind: "student_practice"; lessonId?: string }
  | { kind: "student_question"; questionId: string }
  | { kind: "student_history" }
  | { kind: "parent_dashboard" }
  | { kind: "parent_child_summary"; childId: string }
  | { kind: "parent_child_history"; childId: string }
  | { kind: "parent_child_report"; childId: string }
  | { kind: "notification_detail"; eventId: string };

export type NotificationDeepLinkContext = {
  role: StoaRole;
  isSignedIn: boolean;
  accountReady: boolean;
};
