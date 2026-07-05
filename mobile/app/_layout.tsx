import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { AppProviders } from "@/providers/AppProviders";

export default function RootLayout() {
  return (
    <AppProviders>
      <StatusBar style="dark" />
      <Stack
        screenOptions={{
          headerStyle: { backgroundColor: "#faf8f4" },
          headerTintColor: "#1f1b18",
          headerTitleStyle: { fontWeight: "700" },
          contentStyle: { backgroundColor: "#faf8f4" }
        }}
      />
    </AppProviders>
  );
}
