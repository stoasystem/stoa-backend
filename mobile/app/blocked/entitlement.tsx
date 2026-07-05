import { ScreenScaffold } from "@/ui/ScreenScaffold";
import { StateCard } from "@/ui/StateCard";

export default function EntitlementBlockedRoute() {
  return (
    <ScreenScaffold eyebrow="Access" title="Access unavailable">
      <StateCard title="Plan or quota state" body="Use backend support-safe entitlement and quota explanations instead of generic forbidden copy." />
    </ScreenScaffold>
  );
}
