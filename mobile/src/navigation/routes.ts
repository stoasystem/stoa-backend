export type StoaRole = "student" | "parent";

export type RouteGuard = "public" | "student" | "parent" | "authenticated";

export type MobileRouteContract = {
  path: string;
  label: string;
  guard: RouteGuard;
  deepLink: boolean;
};

export const AUTH_ROUTES: MobileRouteContract[] = [
  { path: "/auth/sign-in", label: "Sign in", guard: "public", deepLink: false },
  { path: "/auth/register", label: "Register", guard: "public", deepLink: false },
  { path: "/auth/verify-email", label: "Verify email", guard: "public", deepLink: true }
];

export const STUDENT_ROUTES: MobileRouteContract[] = [
  { path: "/student", label: "Student dashboard", guard: "student", deepLink: true },
  { path: "/student/practice", label: "Practice", guard: "student", deepLink: true },
  { path: "/student/questions", label: "Ask a question", guard: "student", deepLink: true },
  { path: "/student/history", label: "Learning history", guard: "student", deepLink: true }
];

export const PARENT_ROUTES: MobileRouteContract[] = [
  { path: "/parent", label: "Parent dashboard", guard: "parent", deepLink: true },
  { path: "/parent/children/[childId]", label: "Child summary", guard: "parent", deepLink: true },
  { path: "/parent/children/[childId]/history", label: "Child history", guard: "parent", deepLink: true },
  { path: "/parent/children/[childId]/report", label: "Child report", guard: "parent", deepLink: true },
  { path: "/parent/billing", label: "Billing", guard: "parent", deepLink: true }
];

export const NOTIFICATION_ROUTES: MobileRouteContract[] = [
  { path: "/notifications", label: "Notifications", guard: "authenticated", deepLink: true },
  { path: "/notifications/[eventId]", label: "Notification detail", guard: "authenticated", deepLink: true }
];

export const BLOCKED_ROUTES: MobileRouteContract[] = [
  { path: "/blocked/verification", label: "Verification required", guard: "authenticated", deepLink: false },
  { path: "/blocked/entitlement", label: "Access unavailable", guard: "authenticated", deepLink: false },
  { path: "/blocked/provider", label: "Provider unavailable", guard: "authenticated", deepLink: false }
];

export const MOBILE_ROUTES = [
  ...AUTH_ROUTES,
  ...STUDENT_ROUTES,
  ...PARENT_ROUTES,
  ...NOTIFICATION_ROUTES,
  ...BLOCKED_ROUTES
];

export const isKnownMobileRoute = (path: string): boolean =>
  MOBILE_ROUTES.some((route) => route.path === path);
