import { ScreenScaffold } from "@/ui/ScreenScaffold";
import { StateCard } from "@/ui/StateCard";

export default function StudentPracticeRoute() {
  return (
    <ScreenScaffold eyebrow="Practice" title="Practice">
      <StateCard title="Practice contract" body="Curriculum, lessons, challenges, hints, and teacher-help states are implemented in Phase 269." />
    </ScreenScaffold>
  );
}
