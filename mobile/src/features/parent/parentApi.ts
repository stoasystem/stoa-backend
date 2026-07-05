import type { createMobileApiClient } from "@/services/api/mobileApiClient";

type MobileApiClient = ReturnType<typeof createMobileApiClient>;

export type ParentChild = {
  id: string;
  userId: string;
  name: string;
  email: string;
  grade?: string | null;
};

export type ParentDashboardSummary = {
  children: ParentChild[];
  subscription: unknown;
  accountOperations: unknown;
  notifications: unknown;
};

export const createParentApi = (api: MobileApiClient) => ({
  listChildren: () => api<{ items: ParentChild[] }>({ path: "/parents/me/children" }),

  getSubscription: () => api<unknown>({ path: "/parents/me/subscription" }),

  getBilling: () => api<unknown>({ path: "/parents/me/subscription/billing" }),

  getAccountOperations: () => api<unknown>({ path: "/parents/me/account-operations" }),

  getChildSummary: (childId: string) =>
    api<unknown>({ path: `/parents/me/children/${encodeURIComponent(childId)}/summary` }),

  getChildLearningProfile: (childId: string) =>
    api<unknown>({ path: `/parents/me/children/${encodeURIComponent(childId)}/learning-profile` }),

  getChildUsage: (childId: string) =>
    api<unknown>({ path: `/parents/me/children/${encodeURIComponent(childId)}/usage` }),

  getChildHistory: (childId: string) =>
    api<unknown>({ path: `/parents/me/children/${encodeURIComponent(childId)}/history` }),

  getChildReport: (childId: string) =>
    api<unknown>({ path: `/parents/me/children/${encodeURIComponent(childId)}/report` }),

  getNotifications: () => api<unknown>({ path: "/notifications" }),

  getDashboardSummary: async (): Promise<ParentDashboardSummary> => {
    const [children, subscription, accountOperations, notifications] = await Promise.all([
      api<{ items: ParentChild[] }>({ path: "/parents/me/children" }),
      api<unknown>({ path: "/parents/me/subscription" }),
      api<unknown>({ path: "/parents/me/account-operations" }),
      api<unknown>({ path: "/notifications" })
    ]);

    return {
      children: children.items,
      subscription,
      accountOperations,
      notifications
    };
  }
});
