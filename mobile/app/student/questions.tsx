import { ScreenScaffold } from "@/ui/ScreenScaffold";
import { StateCard } from "@/ui/StateCard";

export default function StudentQuestionsRoute() {
  return (
    <ScreenScaffold eyebrow="Questions" title="Ask a question">
      <StateCard title="Online-only" body="Question submission remains online-only so quota and usage ledger checks stay server-authoritative." />
    </ScreenScaffold>
  );
}
