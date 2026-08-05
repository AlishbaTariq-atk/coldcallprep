/**
 * Canned inputs for the "Use example prospect" button, zero-typing demo
 * data. These are real small/independent businesses chosen to plausibly
 * exhibit the kind of gaps infer_opportunity_signals looks for (no
 * booking system, no pricing page, dated design). If a URL ever goes
 * stale, the Source Gate still produces a valid brief from raw_notes
 * alone, so a dead link degrades the demo rather than breaking it.
 */

export interface ExampleProspect {
  label: string;
  url: string;
  raw_notes: string;
}

export const EXAMPLE_PROSPECTS: ExampleProspect[] = [
  {
    label: "Independent CPA firm",
    url: "https://www.cpafirmnyc.com/",
    raw_notes:
      "Small accounting practice, mostly serves local small-business owners. Likely booked via phone/email rather than any online scheduling tool.",
  },
  {
    label: "Bourke Street Bakery (Sydney)",
    url: "https://bourkestreetbakery.com.au",
    raw_notes:
      "Small independent neighborhood bakery, curious about their online ordering and delivery options.",
  },
];
