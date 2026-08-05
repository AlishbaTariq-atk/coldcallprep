import { Lightbulb } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { InferredSignal } from "@/lib/types";

/** Format a snake_case signal_type (e.g. "no_pricing_page") as Title Case for display. */
function formatSignalType(signalType: string): string {
  return signalType.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

/**
 * This is the single most important visual distinction in the product:
 * every item here carries the amber border + "INFERRED" badge +
 * reasoning-underneath treatment, everywhere it appears, never silently
 * blended in with a stated fact. See StatedFactsCard for the neutral
 * counterpoint this is deliberately contrasted against.
 */
export function InferredSignalsCard({ signals }: { signals: InferredSignal[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Lightbulb className="h-4 w-4 text-primary" />
          Opportunity Signals
        </CardTitle>
      </CardHeader>
      <CardContent>
        {signals.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No opportunity signals were identified.
          </p>
        ) : (
          <ul className="space-y-3">
            {signals.map((signal, i) => (
              <li
                key={i}
                className="rounded-md border-l-2 border-primary bg-primary/5 py-2.5 pl-4 pr-3 dark:bg-primary/10"
              >
                <div className="mb-1 flex flex-wrap items-center gap-2">
                  <Badge className="border-primary/30 bg-primary/15 font-medium tracking-wide text-primary hover:bg-primary/15 dark:border-primary/40 dark:bg-primary/25 dark:text-primary-foreground">
                    INFERRED
                  </Badge>
                  <span className="text-sm font-medium text-foreground">
                    {formatSignalType(signal.signal_type)}
                  </span>
                </div>
                <p className="text-sm leading-relaxed text-muted-foreground">
                  {signal.reasoning}
                </p>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
