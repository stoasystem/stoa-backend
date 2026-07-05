import type {
  NotificationDeepLinkContext,
  NotificationRouteTarget
} from "./notificationTypes";

export type DeepLinkValidation =
  | { allowed: true; href: string }
  | { allowed: false; reason: "signed_out" | "account_blocked" | "role_mismatch" | "unknown_target" };

export const hrefForNotificationTarget = (target: NotificationRouteTarget): string | null => {
  switch (target.kind) {
    case "student_dashboard":
      return "/student";
    case "student_practice":
      return target.lessonId
        ? `/student/practice?lessonId=${encodeURIComponent(target.lessonId)}`
        : "/student/practice";
    case "student_question":
      return `/student/questions?questionId=${encodeURIComponent(target.questionId)}`;
    case "student_history":
      return "/student/history";
    case "parent_dashboard":
      return "/parent";
    case "parent_child_summary":
      return `/parent/children/${encodeURIComponent(target.childId)}`;
    case "parent_child_history":
      return `/parent/children/${encodeURIComponent(target.childId)}/history`;
    case "parent_child_report":
      return `/parent/children/${encodeURIComponent(target.childId)}/report`;
    case "notification_detail":
      return `/notifications/${encodeURIComponent(target.eventId)}`;
    default:
      return null;
  }
};

export const validateNotificationDeepLink = (
  target: NotificationRouteTarget,
  context: NotificationDeepLinkContext
): DeepLinkValidation => {
  if (!context.isSignedIn) {
    return { allowed: false, reason: "signed_out" };
  }
  if (!context.accountReady) {
    return { allowed: false, reason: "account_blocked" };
  }

  const href = hrefForNotificationTarget(target);
  if (!href) {
    return { allowed: false, reason: "unknown_target" };
  }

  if (href.startsWith("/student") && context.role !== "student") {
    return { allowed: false, reason: "role_mismatch" };
  }
  if (href.startsWith("/parent") && context.role !== "parent") {
    return { allowed: false, reason: "role_mismatch" };
  }

  return { allowed: true, href };
};
