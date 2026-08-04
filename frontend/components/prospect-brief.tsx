import { Building2, ExternalLink } from "lucide-react";
import { InferredSignalsCard } from "@/components/inferred-signals-card";
import { OutreachOpenerCard } from "@/components/outreach-opener-card";
import { SourceGateBanner } from "@/components/source-gate-banner";
import { StatedFactsCard } from "@/components/stated-facts-card";
import { SummaryStrip } from "@/components/summary-strip";
import type { RunResult } from "@/lib/types";

/**
 * Assembles the completed brief from its section components: summary strip,
 * source gate banner (if degraded), company snapshot, stated facts,
 * inferred signals, and the outreach opener.
 */
export function ProspectBrief({ result }: { result: RunResult }) {
  const { prospect, brief } = result;

  return (
    <div className="space-y-5">
      <div>
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Prospect Brief
        </p>
        <a
          href={prospect.url}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-primary hover:underline"
        >
          {prospect.url}
          <ExternalLink className="h-3 w-3" />
        </a>
      </div>

      <SummaryStrip brief={brief} />

      {!brief.source_usable && <SourceGateBanner />}

      <div className="rounded-lg border bg-card p-5">
        <div className="mb-2 flex items-center gap-2">
          <Building2 className="h-4 w-4 text-primary" />
          <h2 className="text-sm font-semibold text-foreground">Company Snapshot</h2>
        </div>
        <p className="text-sm leading-relaxed text-foreground">
          {brief.company_snapshot}
        </p>
      </div>

      <StatedFactsCard facts={brief.stated_facts} />
      <InferredSignalsCard signals={brief.inferred_signals} />
      <OutreachOpenerCard text={brief.outreach_opener} />
    </div>
  );
}
