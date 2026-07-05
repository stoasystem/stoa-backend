import { ScreenScaffold } from "@/ui/ScreenScaffold";
import { StateCard } from "@/ui/StateCard";

export default function ProviderBlockedRoute() {
  return (
    <ScreenScaffold eyebrow="Provider status" title="Provider unavailable">
      <StateCard title="External blocker" body="Provider-blocked states should identify the unavailable capability without exposing provider payloads." />
    </ScreenScaffold>
  );
}
