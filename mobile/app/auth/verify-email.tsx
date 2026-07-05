import { Text } from "react-native";
import { ScreenScaffold } from "@/ui/ScreenScaffold";

export default function VerifyEmailRoute() {
  return (
    <ScreenScaffold eyebrow="Email verification" title="Verify your email">
      <Text>Verification-code entry and resend-code policy are implemented in Phase 268.</Text>
    </ScreenScaffold>
  );
}
