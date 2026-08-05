"use client";

import { useState, type FormEvent } from "react";
import { ChevronDown, Loader2, Sparkles } from "lucide-react";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { EXAMPLE_PROSPECTS } from "@/lib/example-prospects";
import { cn } from "@/lib/utils";

interface ProspectFormProps {
  onSubmit: (url: string, notes: string) => void;
  isRunning: boolean;
}

/** Prospect URL + notes input, with a dropdown to fill in one of the canned example prospects. */
export function ProspectForm({ onSubmit, isRunning }: ProspectFormProps) {
  const [url, setUrl] = useState("");
  const [notes, setNotes] = useState("");

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!url.trim() || isRunning) return;
    onSubmit(url.trim(), notes.trim());
  }

  function applyExample(index: number) {
    const example = EXAMPLE_PROSPECTS[index];
    setUrl(example.url);
    setNotes(example.raw_notes);
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      <div className="space-y-2">
        <Label htmlFor="url">Company URL</Label>
        <Input
          id="url"
          type="url"
          placeholder="https://example-company.com"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          disabled={isRunning}
          required
        />
      </div>

      <div className="space-y-2">
        <Label htmlFor="notes">
          Notes <span className="font-normal text-muted-foreground">(optional)</span>
        </Label>
        <Textarea
          id="notes"
          placeholder="Anything you already know, how you got this lead, prior conversations, etc."
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          disabled={isRunning}
          rows={4}
          className="resize-none"
        />
      </div>

      <div className="flex items-center gap-2">
        <Button type="submit" disabled={isRunning || !url.trim()} className="flex-1 gap-2">
          {isRunning ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              Researching...
            </>
          ) : (
            <>
              <Sparkles className="h-4 w-4" />
              Generate Brief
            </>
          )}
        </Button>

        <DropdownMenu>
          <DropdownMenuTrigger
            disabled={isRunning}
            className={cn(buttonVariants({ variant: "outline" }), "gap-1.5")}
          >
            Example
            <ChevronDown className="h-3.5 w-3.5" />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            {EXAMPLE_PROSPECTS.map((example, i) => (
              <DropdownMenuItem key={example.url} onClick={() => applyExample(i)}>
                {example.label}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </form>
  );
}
