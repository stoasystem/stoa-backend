export type ParentScreenContract = {
  route: string;
  titleKey: string;
  endpointContracts: string[];
  states: Array<"loading" | "ready" | "empty" | "blocked" | "stale" | "error">;
  offlineReadThrough: boolean;
  onlineOnlyMutations: string[];
};

export const PARENT_SCREEN_CONTRACTS: ParentScreenContract[] = [
  {
    route: "/parent",
    titleKey: "parentDashboard",
    endpointContracts: [
      "/parents/me/children",
      "/parents/me/subscription",
      "/parents/me/account-operations",
      "/notifications"
    ],
    states: ["loading", "ready", "empty", "blocked", "stale", "error"],
    offlineReadThrough: true,
    onlineOnlyMutations: []
  },
  {
    route: "/parent/children/[childId]",
    titleKey: "childSummary",
    endpointContracts: [
      "/parents/me/children/{childId}/summary",
      "/parents/me/children/{childId}/usage",
      "/parents/me/children/{childId}/learning-profile"
    ],
    states: ["loading", "ready", "empty", "blocked", "stale", "error"],
    offlineReadThrough: true,
    onlineOnlyMutations: []
  },
  {
    route: "/parent/children/[childId]/history",
    titleKey: "childHistory",
    endpointContracts: ["/parents/me/children/{childId}/history"],
    states: ["loading", "ready", "empty", "blocked", "stale", "error"],
    offlineReadThrough: true,
    onlineOnlyMutations: []
  },
  {
    route: "/parent/children/[childId]/report",
    titleKey: "childReport",
    endpointContracts: ["/parents/me/children/{childId}/report"],
    states: ["loading", "ready", "empty", "blocked", "stale", "error"],
    offlineReadThrough: true,
    onlineOnlyMutations: []
  },
  {
    route: "/parent/billing",
    titleKey: "billing",
    endpointContracts: ["/parents/me/subscription", "/parents/me/subscription/billing"],
    states: ["loading", "ready", "empty", "blocked", "error"],
    offlineReadThrough: false,
    onlineOnlyMutations: ["/parents/me/subscription/requests"]
  }
];
