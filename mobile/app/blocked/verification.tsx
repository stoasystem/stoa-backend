import { ScreenScaffold } from "@/ui/ScreenScaffold";
import { StateCard } from "@/ui/StateCard";

export default function VerificationBlockedRoute() {
  return (
    <ScreenScaffold eyebrow="Action required" title="Verify your email">
      <StateCard title="Verification required" body="Email verification is required before mobile sign-in can continue." />
    </ScreenScaffold>
  );
}
