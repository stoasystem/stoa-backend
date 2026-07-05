import * as SecureStore from "expo-secure-store";

const LAST_SIGNED_IN_EMAIL_KEY = "stoa.mobile.lastSignedInEmail";
const LAST_ROLE_KEY = "stoa.mobile.lastRole";

export type SessionMetadata = {
  lastSignedInEmail?: string;
  lastRole?: "student" | "parent";
};

export const saveSessionMetadata = async (metadata: SessionMetadata): Promise<void> => {
  if (metadata.lastSignedInEmail) {
    await SecureStore.setItemAsync(LAST_SIGNED_IN_EMAIL_KEY, metadata.lastSignedInEmail);
  }
  if (metadata.lastRole) {
    await SecureStore.setItemAsync(LAST_ROLE_KEY, metadata.lastRole);
  }
};

export const readSessionMetadata = async (): Promise<SessionMetadata> => {
  const [lastSignedInEmail, lastRole] = await Promise.all([
    SecureStore.getItemAsync(LAST_SIGNED_IN_EMAIL_KEY),
    SecureStore.getItemAsync(LAST_ROLE_KEY)
  ]);

  return {
    lastSignedInEmail: lastSignedInEmail ?? undefined,
    lastRole: lastRole === "student" || lastRole === "parent" ? lastRole : undefined
  };
};

export const clearSessionMetadata = async (): Promise<void> => {
  await Promise.all([
    SecureStore.deleteItemAsync(LAST_SIGNED_IN_EMAIL_KEY),
    SecureStore.deleteItemAsync(LAST_ROLE_KEY)
  ]);
};
