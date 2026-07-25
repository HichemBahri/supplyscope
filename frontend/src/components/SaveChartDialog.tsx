import * as Dialog from "@radix-ui/react-dialog";
import { useState } from "react";
import { X } from "lucide-react";
import { api, ApiError } from "../lib/api";
import type { Message } from "../lib/types";
import { Button } from "./ui/Button";
import { Input } from "./ui/Input";

interface Props {
  message: Message | null;
  onClose: () => void;
  onSaved: () => void;
}

export function SaveChartDialog({ message, onClose, onSaved }: Props) {
  const [title, setTitle] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const save = async () => {
    if (!message?.sql_query || !message.chart) return;
    setBusy(true); setError("");
    try {
      await api.saveChart(title || message.chart.title, message.sql_query, message.chart);
      onSaved(); onClose(); setTitle("");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not save the chart — try again.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog.Root open={!!message} onOpenChange={(o) => !o && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-navy-900/40 backdrop-blur-[2px]" />
        <Dialog.Content className="fixed left-1/2 top-1/2 w-[420px] -translate-x-1/2 -translate-y-1/2 rounded-lg border border-line bg-card p-5 shadow-xl">
          <div className="flex items-center justify-between">
            <Dialog.Title className="font-display text-lg font-bold text-navy-900">
              Pin to dashboard
            </Dialog.Title>
            <Dialog.Close className="rounded p-1 text-ink-muted hover:bg-line/60">
              <X className="size-4" />
            </Dialog.Close>
          </div>
          <Dialog.Description className="mt-1 text-sm text-ink-muted">
            This chart will update automatically whenever the underlying data changes.
          </Dialog.Description>
          <label className="eyebrow mt-4 block">Chart title</label>
          <Input
            className="mt-1.5"
            value={title}
            placeholder={message?.chart?.title ?? ""}
            onChange={(e) => setTitle(e.target.value)}
            autoFocus
          />
          {error && <p className="mt-2 text-sm text-danger">{error}</p>}
          <div className="mt-5 flex justify-end gap-2">
            <Button variant="ghost" onClick={onClose}>Cancel</Button>
            <Button onClick={save} disabled={busy}>
              {busy ? "Saving…" : "Pin chart"}
            </Button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
