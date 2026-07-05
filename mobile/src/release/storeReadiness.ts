export type StoreReadinessItem = {
  area: string;
  status: "ready" | "blocked" | "not_started" | "out_of_scope";
  owner: "product" | "engineering" | "design" | "support" | "legal";
  action: string;
};

export const STORE_READINESS_CHECKLIST: StoreReadinessItem[] = [
  {
    area: "Account ownership",
    status: "blocked",
    owner: "product",
    action: "Confirm Apple Developer and Google Play account ownership."
  },
  {
    area: "Privacy declarations",
    status: "not_started",
    owner: "legal",
    action: "Prepare privacy labels and data-use disclosures for mobile auth, push, analytics, and support."
  },
  {
    area: "Screenshots and review notes",
    status: "not_started",
    owner: "design",
    action: "Capture approved device screenshots and review notes after device QA passes."
  },
  {
    area: "Support staffing",
    status: "blocked",
    owner: "support",
    action: "Approve support owner, support hours, escalation path, and incident coverage."
  },
  {
    area: "Rollout approval",
    status: "blocked",
    owner: "product",
    action: "Approve cohort, monitoring, rollback, and go/no-go decision."
  }
];
