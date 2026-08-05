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
    label: "Family-owned HVAC & plumbing company",
    url: "https://www.866myfamily.com/",
    raw_notes:
      "Referred by a customer of theirs. Family-run, been around for years, not sure they have much of an online presence beyond the phone number.",
  },
  {
    label: "Small seasonal donut shop",
    url: "https://backdoordonuts.com/",
    raw_notes:
      "Local favorite with a huge word-of-mouth following, open late-night only. Curious whether they've ever invested in online ordering or marketing beyond the storefront.",
  },
  {
    label: "Independent CPA firm",
    url: "https://www.cpafirmnyc.com/",
    raw_notes:
      "Small accounting practice, mostly serves local small-business owners. Likely booked via phone/email rather than any online scheduling tool.",
  },
];
