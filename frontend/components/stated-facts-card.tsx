import { Quote } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { StatedFact } from "@/lib/types";

const CATEGORY_LABELS: Record<string, string> = {
  services: "Services",
  positioning: "Positioning",
  target_audience: "Target audience",
};

/**
 * Neutral treatment (slate border, secondary badge) is the deliberate
 * counterpoint to InferredSignalsCard's amber treatment — the contrast
 * between the two IS the fact/inference distinction, made visible.
 */
export function StatedFactsCard({ facts }: { facts: StatedFact[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Quote className="h-4 w-4 text-muted-foreground" />
          What They Say About Themselves
        </CardTitle>
      </CardHeader>
      <CardContent>
        {facts.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No stated facts were extracted from the site.
          </p>
        ) : (
          <ul className="space-y-4">
            {facts.map((fact, i) => (
              <li key={i} className="border-l-2 border-border pl-4">
                <Badge variant="secondary" className="mb-1.5 font-normal">
                  {CATEGORY_LABELS[fact.category] ?? fact.category}
                </Badge>
                <p className="text-sm leading-relaxed text-foreground">
                  &ldquo;{fact.quote}&rdquo;
                </p>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
