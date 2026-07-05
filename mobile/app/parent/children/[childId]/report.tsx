import { ScreenScaffold } from "@/ui/ScreenScaffold";
import { StateCard } from "@/ui/StateCard";

export default function ParentChildReportRoute() {
  return (
    <ScreenScaffold eyebrow="Child report" title="Child report">
      <StateCard title="Privacy boundary" body="Report summaries may be cached, but generated report artifacts and private object keys are not cached." />
    </ScreenScaffold>
  );
}
