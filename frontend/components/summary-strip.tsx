import { Globe, Lightbulb, Quote } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import type { RunResultBrief } from "@/lib/types";

/**
 * A fast, purely computational at-a-glance readout — every number here
 * is just a length of an array already in `brief`, and source_status is
 * pre-computed backend-side (agent/gates.py::source_status) from data
 * the pipeline already fetched. No extra calls, no extra latency.
 */
export function SummaryStrip({ brief }: { brief: RunResultBrief }) {
  const isDegraded = brief.source_status !== "Full site content retrieved";

  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-2 rounded-lg border bg-card px-5 py-3.5">
      <SummaryItem
        icon={<Quote className="h-4 w-4 text-muted-foreground" />}
        label={`${brief.stated_facts.length} stated fact${brief.stated_facts.length === 1 ? "" : "s"}`}
      />
      <SummaryItem
        icon={<Lightbulb className="h-4 w-4 text-primary" />}
        label={`${brief.inferred_signals.length} opportunity signal${brief.inferred_signals.length === 1 ? "" : "s"}`}
      />
      <SummaryItem
        icon={
          <Globe
            className={cn(
              "h-4 w-4",
              isDegraded ? "text-amber-600 dark:text-amber-400" : "text-muted-foreground"
            )}
          />
        }
        label={brief.source_status}
        labelClassName={isDegraded ? "text-amber-700 dark:text-amber-300" : undefined}
      />
    </div>
  );
}

/** One icon + label pair within the summary strip. */
function SummaryItem({
  icon,
  label,
  labelClassName,
}: {
  icon: ReactNode;
  label: string;
  labelClassName?: string;
}) {
  return (
    <div className="flex items-center gap-2">
      {icon}
      <span className={cn("text-sm font-medium text-foreground", labelClassName)}>
        {label}
      </span>
    </div>
  );
}
