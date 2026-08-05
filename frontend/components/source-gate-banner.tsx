import { Info } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";

/**
 * Rendered directly from brief.source_usable (a boolean the backend
 * computed via agent.gates.source_is_usable), this banner's presence
 * doesn't depend on the model having remembered to mention the gap in
 * its own text. Same amber thread as the "INFERRED" treatment: both mean
 * "this isn't a verified fact," just at different scopes (one signal vs.
 * the whole brief).
 */
export function SourceGateBanner() {
  return (
    <Alert className="border-amber-300 bg-amber-50 dark:border-amber-800/60 dark:bg-amber-950/30">
      <Info className="h-4 w-4 !text-amber-600 dark:!text-amber-400" />
      <AlertTitle className="text-amber-900 dark:text-amber-200">
        Built from your notes only
      </AlertTitle>
      <AlertDescription className="text-amber-800/90 dark:text-amber-300/80">
        We couldn&apos;t retrieve content from this site, so nothing below is
        sourced from it. Everything here comes only from the notes you
        provided.
      </AlertDescription>
    </Alert>
  );
}
