import { ScreenScaffold } from "@/ui/ScreenScaffold";
import { StateCard } from "@/ui/StateCard";

export default function ParentBillingRoute() {
  return (
    <ScreenScaffold eyebrow="Billing" title="Billing">
      <StateCard title="Server-authoritative" body="Billing and entitlement state remain online-first and are never mutated offline." />
    </ScreenScaffold>
  );
}
