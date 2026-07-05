import { ScreenScaffold } from "@/ui/ScreenScaffold";
import { StateCard } from "@/ui/StateCard";

export default function ParentChildHistoryRoute() {
  return (
    <ScreenScaffold eyebrow="Child history" title="Child history">
      <StateCard title="Read-through candidate" body="History summary cache must be TTL-bound and cleared on sign-out or user switch." />
    </ScreenScaffold>
  );
}
