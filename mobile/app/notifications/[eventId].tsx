import { ScreenScaffold } from "@/ui/ScreenScaffold";
import { StateCard } from "@/ui/StateCard";

export default function NotificationDetailRoute() {
  return (
    <ScreenScaffold eyebrow="Notification" title="Notification detail">
      <StateCard title="Validated deep link" body="Deep links must be validated after session restore, role checks, and account-state checks." />
    </ScreenScaffold>
  );
}
