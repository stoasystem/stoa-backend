export type CacheSurface =
  | "student_dashboard"
  | "student_practice_overview"
  | "student_learning_history"
  | "parent_dashboard"
  | "parent_child_summary"
  | "parent_child_history"
  | "parent_child_report_summary"
  | "notifications";

export type ForbiddenCacheCategory =
  | "raw_prompt"
  | "raw_answer"
  | "tutoring_transcript"
  | "generated_report_artifact"
  | "provider_payload"
  | "billing_payload"
  | "cognito_token_material"
  | "secret"
  | "private_object_key";

export type CachePolicy = {
  surface: CacheSurface;
  ttlSeconds: number;
  staleLabel: string;
  clearOnSignOut: true;
  clearOnUserSwitch: true;
};

export const READ_THROUGH_CACHE_POLICIES: CachePolicy[] = [
  {
    surface: "student_dashboard",
    ttlSeconds: 300,
    staleLabel: "Student dashboard may be out of date.",
    clearOnSignOut: true,
    clearOnUserSwitch: true
  },
  {
    surface: "student_practice_overview",
    ttlSeconds: 900,
    staleLabel: "Practice overview may be out of date.",
    clearOnSignOut: true,
    clearOnUserSwitch: true
  },
  {
    surface: "student_learning_history",
    ttlSeconds: 1800,
    staleLabel: "Learning history may be out of date.",
    clearOnSignOut: true,
    clearOnUserSwitch: true
  },
  {
    surface: "parent_dashboard",
    ttlSeconds: 300,
    staleLabel: "Parent dashboard may be out of date.",
    clearOnSignOut: true,
    clearOnUserSwitch: true
  },
  {
    surface: "parent_child_summary",
    ttlSeconds: 900,
    staleLabel: "Child summary may be out of date.",
    clearOnSignOut: true,
    clearOnUserSwitch: true
  },
  {
    surface: "parent_child_history",
    ttlSeconds: 1800,
    staleLabel: "Child history may be out of date.",
    clearOnSignOut: true,
    clearOnUserSwitch: true
  },
  {
    surface: "parent_child_report_summary",
    ttlSeconds: 3600,
    staleLabel: "Report summary may be out of date.",
    clearOnSignOut: true,
    clearOnUserSwitch: true
  },
  {
    surface: "notifications",
    ttlSeconds: 300,
    staleLabel: "Notifications may be out of date.",
    clearOnSignOut: true,
    clearOnUserSwitch: true
  }
];

export const FORBIDDEN_CACHE_CATEGORIES: ForbiddenCacheCategory[] = [
  "raw_prompt",
  "raw_answer",
  "tutoring_transcript",
  "generated_report_artifact",
  "provider_payload",
  "billing_payload",
  "cognito_token_material",
  "secret",
  "private_object_key"
];

export const ONLINE_ONLY_MUTATION_PATHS = [
  "/questions",
  "/questions/{questionId}/request-teacher",
  "/practice/teacher-help",
  "/practice/challenges/{challengeId}/answer",
  "/parents/me/subscription/requests",
  "/parents/me/subscription/billing"
] as const;

export const getCachePolicy = (surface: CacheSurface): CachePolicy =>
  READ_THROUGH_CACHE_POLICIES.find((policy) => policy.surface === surface) ?? (() => {
    throw new Error(`No read-through cache policy exists for ${surface}`);
  })();

export const assertCacheCategoryAllowed = (category: string): void => {
  if (FORBIDDEN_CACHE_CATEGORIES.includes(category as ForbiddenCacheCategory)) {
    throw new Error(`Mobile offline cache rejects sensitive category: ${category}`);
  }
};

export const assertMutationOnlineOnly = (path: string): void => {
  if (ONLINE_ONLY_MUTATION_PATHS.some((onlineOnly) => path.startsWith(onlineOnly.split("{")[0]))) {
    throw new Error(`Mobile mutation is online-only: ${path}`);
  }
};
