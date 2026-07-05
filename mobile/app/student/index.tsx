import { ScreenScaffold } from "@/ui/ScreenScaffold";
import { StateCard } from "@/ui/StateCard";

export default function StudentDashboardRoute() {
  return (
    <ScreenScaffold eyebrow="Student" title="Student dashboard">
      <StateCard title="Dashboard contract" body="Loads account, curriculum, quota, practice, and notification summaries from real backend APIs." />
    </ScreenScaffold>
  );
}
