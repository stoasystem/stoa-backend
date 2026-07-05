import Constants from "expo-constants";
import * as Notifications from "expo-notifications";
import { Platform } from "react-native";
import type { MobileConfig } from "@/config/mobileConfig";
import type { RegisterPushTokenInput } from "./notificationApi";
import type { PushPermissionState } from "./notificationTypes";

export const getPushPermissionState = async (): Promise<PushPermissionState> => {
  const permissions = await Notifications.getPermissionsAsync();
  if (permissions.granted) {
    return "granted";
  }
  if (permissions.canAskAgain) {
    return "unknown";
  }
  return "denied";
};

export const requestPushPermission = async (): Promise<PushPermissionState> => {
  const permissions = await Notifications.requestPermissionsAsync();
  if (permissions.granted) {
    return "granted";
  }
  return permissions.canAskAgain ? "unknown" : "denied";
};

export const getExpoPushRegistrationInput = async (
  config: MobileConfig
): Promise<RegisterPushTokenInput> => {
  if (!config.expoProjectId) {
    throw new Error("Expo project ID is required before registering push tokens.");
  }

  const permissionState = await getPushPermissionState();
  if (permissionState !== "granted") {
    throw new Error(`Push permission is not granted: ${permissionState}`);
  }

  const token = await Notifications.getExpoPushTokenAsync({
    projectId: config.expoProjectId
  });

  return {
    provider: "expo",
    token: token.data,
    platform: Platform.OS,
    appVersion: Constants.expoConfig?.version
  };
};

export const configureForegroundNotificationHandling = (): void => {
  Notifications.setNotificationHandler({
    handleNotification: async () => ({
      shouldShowBanner: true,
      shouldShowList: true,
      shouldPlaySound: false,
      shouldSetBadge: true
    })
  });
};
