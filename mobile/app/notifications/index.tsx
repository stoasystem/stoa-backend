import { ScreenScaffold } from "@/ui/ScreenScaffold";
import { StateCard } from "@/ui/StateCard";

export default function NotificationsRoute() {
  return (
    <ScreenScaffold eyebrow="Notifications" title="Notifications">
      <StateCard title="Notification contract" body="List, read, archive, and foreground/background handling are implemented in Phase 270." />
    </ScreenScaffold>
  );
}
