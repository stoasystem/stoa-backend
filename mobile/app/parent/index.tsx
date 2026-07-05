import { ScreenScaffold } from "@/ui/ScreenScaffold";
import { StateCard } from "@/ui/StateCard";

export default function ParentDashboardRoute() {
  return (
    <ScreenScaffold eyebrow="Parent" title="Parent dashboard">
      <StateCard title="Dashboard contract" body="Loads subscription, child summary, notification, and account-operation state from real backend APIs." />
    </ScreenScaffold>
  );
}
