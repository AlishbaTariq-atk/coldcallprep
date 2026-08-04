"use client";

import { useState } from "react";
import { Check, Copy, Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

/** The generated outreach opener, with a one-click copy-to-clipboard button. */
export function OutreachOpenerCard({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  /** Copy the opener text to the clipboard and briefly show a "Copied" confirmation. */
  async function handleCopy() {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0">
        <CardTitle className="flex items-center gap-2 text-base">
          <Send className="h-4 w-4 text-muted-foreground" />
          Outreach Opener
        </CardTitle>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={handleCopy}
          className="h-8 gap-1.5 text-xs text-muted-foreground hover:text-foreground"
        >
          {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
          {copied ? "Copied" : "Copy"}
        </Button>
      </CardHeader>
      <CardContent>
        <p className="text-sm leading-relaxed text-foreground">{text}</p>
      </CardContent>
    </Card>
  );
}
