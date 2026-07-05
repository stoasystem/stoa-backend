import { ScreenScaffold } from "@/ui/ScreenScaffold";
import { StateCard } from "@/ui/StateCard";

export default function ParentChildRoute() {
  return (
    <ScreenScaffold eyebrow="Child summary" title="Child summary">
      <StateCard title="Authorized child data" body="Child summary must come from backend-authorized parent endpoints, not demo fallback data." />
    </ScreenScaffold>
  );
}
