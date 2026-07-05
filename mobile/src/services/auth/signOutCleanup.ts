import type { QueryClient } from "@tanstack/react-query";
import { clearSessionMetadata } from "./secureSessionMetadata";
import { signOutOfStoa } from "./amplifyAuth";

type RevokePushToken = () => Promise<void>;

export const runSignOutCleanup = async (
  queryClient: QueryClient,
  revokePushToken?: RevokePushToken
): Promise<void> => {
  await revokePushToken?.();
  queryClient.clear();
  await clearSessionMetadata();
  await signOutOfStoa();
};
