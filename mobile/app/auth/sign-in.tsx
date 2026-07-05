import { Text } from "react-native";
import { ScreenScaffold } from "@/ui/ScreenScaffold";
import { StateCard } from "@/ui/StateCard";

export default function SignInRoute() {
  return (
    <ScreenScaffold
      eyebrow="Authentication"
      title="Sign in"
      description="Use your STOA account. Native session handling is backed by Cognito-compatible Amplify Auth."
    >
      <StateCard
        title="Real account required"
        body="This mobile client does not provide demo fallback data for authenticated routes."
      />
      <Text>Email, password, verification, and resend-code controls are implemented in Phase 268.</Text>
    </ScreenScaffold>
  );
}
