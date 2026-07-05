import type { createMobileApiClient } from "@/services/api/mobileApiClient";

type MobileApiClient = ReturnType<typeof createMobileApiClient>;

export type RegisterPushTokenInput = {
  provider: "expo";
  token: string;
  deviceId?: string;
  platform?: string;
  appVersion?: string;
};

export const createNotificationApi = (api: MobileApiClient) => ({
  listNotifications: () => api<unknown>({ path: "/notifications" }),

  getPreferences: () => api<unknown>({ path: "/notifications/preferences" }),

  registerPushToken: (input: RegisterPushTokenInput) =>
    api<unknown>({
      path: "/notifications/push-tokens",
      method: "POST",
      body: {
        provider: input.provider,
        token: input.token,
        device_id: input.deviceId,
        platform: input.platform,
        app_version: input.appVersion
      }
    }),

  revokePushToken: (tokenReference: string) =>
    api<unknown>({
      path: `/notifications/push-tokens/${encodeURIComponent(tokenReference)}`,
      method: "DELETE"
    }),

  markRead: (eventId: string) =>
    api<unknown>({
      path: `/notifications/${encodeURIComponent(eventId)}/read`,
      method: "POST"
    }),

  archive: (eventId: string) =>
    api<unknown>({
      path: `/notifications/${encodeURIComponent(eventId)}/archive`,
      method: "POST"
    })
});
