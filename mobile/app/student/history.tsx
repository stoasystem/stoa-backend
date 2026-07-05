import { ScreenScaffold } from "@/ui/ScreenScaffold";
import { StateCard } from "@/ui/StateCard";

export default function StudentHistoryRoute() {
  return (
    <ScreenScaffold eyebrow="Learning history" title="Learning history">
      <StateCard title="Read-through candidate" body="History summaries can use bounded stale cache after authenticated successful reads." />
    </ScreenScaffold>
  );
}
