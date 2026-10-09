import { useEffect, useRef, useState, type FormEvent } from "react";
import { Plus, SendHorizonal, X } from "lucide-react";
import { clsx } from "clsx";
import { api, ApiError } from "../lib/api";
import type { Conversation, Message } from "../lib/types";
import { MessageBubble } from "../components/MessageBubble";
import { SaveChartDialog } from "../components/SaveChartDialog";
import { Button } from "../components/ui/Button";
import { Spinner } from "../components/ui/Spinner";

const SUGGESTIONS = [
  "Which supplier has the worst on-time delivery rate?",
  "Monthly procurement spend in 2025, converted to TND",
  "Which projects exceed their contract value (in TND)?",
  "Average customs clearance time to Libya by quarter",
];

export default function Chat() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [pinTarget, setPinTarget] = useState<Message | null>(null);
  const [toast, setToast] = useState("");
  const [tier, setTier] = useState<"fast" | "smart">("fast");
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => { api.conversations().then(setConversations).catch(() => {}); }, []);
  useEffect(() => {
    if (activeId === null) { setMessages([]); return; }
    api.messages(activeId).then(setMessages).catch(() => {});
  }, [activeId]);
  useEffect(() => { bottom.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, busy]);

  const send = async (q?: string) => {
    const text = (q ?? question).trim();
    if (!text || busy) return;
    setBusy(true); setError(""); setQuestion("");
    setMessages((m) => [...m, {
      message_id: -Date.now(), role: "user", content: text,
      sql_query: null, chart: null, result_meta: null, created_at: "",
    }]);
    try {
      const turn = await api.chat(text, activeId ?? undefined, tier);
      setActiveId(turn.conversation_id);
      setMessages((m) => [...m.slice(0, -1), turn.user_message, turn.assistant_message]);
      api.conversations().then(setConversations).catch(() => {});
    } catch (e) {
      setMessages((m) => m.slice(0, -1));
      setError(e instanceof ApiError ? e.message : "The agent is unreachable — check the server.");
    } finally {
      setBusy(false);
    }
  };

  const submit = (e: FormEvent) => { e.preventDefault(); send(); };

  return (
    <div className="flex h-screen flex-1 overflow-hidden">
      {/* conversation list */}
      <div className="flex w-64 shrink-0 flex-col border-r border-line bg-card">
        <div className="p-3">
          <Button variant="ghost" className="w-full justify-center"
                  onClick={() => setActiveId(null)}>
            <Plus className="size-4" /> New analysis
          </Button>
        </div>
        <div className="flex-1 overflow-y-auto px-2 pb-3">
          {conversations.map((c) => (
            <div key={c.conversation_id} className="group relative">
              <button
                onClick={() => setActiveId(c.conversation_id)}
                className={clsx(
                  "mb-1 w-full truncate rounded-md px-3 py-2 pr-8 text-left text-[13px] transition-colors",
                  c.conversation_id === activeId
                    ? "bg-navy-900/6 font-medium text-navy-900"
                    : "text-ink-muted hover:bg-line/50 hover:text-ink",
                )}
              >
                {c.title}
              </button>
              <button
                onClick={async (e) => {
                  e.stopPropagation();
                  if (!window.confirm("Delete this conversation?")) return;
                  await api.deleteConversation(c.conversation_id);
                  setConversations((cs) =>
                    cs.filter((x) => x.conversation_id !== c.conversation_id));
                  if (activeId === c.conversation_id) setActiveId(null);
                }}
                title="Delete conversation"
                className="absolute right-1.5 top-1/2 -translate-y-1/2 hidden group-hover:block text-ink-muted hover:text-danger"
              >
                <X className="size-3.5" />
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* thread */}
      <div className="flex flex-1 flex-col">
        <div className="flex-1 overflow-y-auto">
          <div className="mx-auto flex max-w-3xl flex-col gap-4 px-6 py-6">
            {messages.length === 0 && !busy && (
              <div className="mt-16 text-center">
                <h2 className="font-display text-2xl font-bold text-navy-900">
                  Chat with your Data
                </h2>
                <p className="mx-auto mt-2 max-w-md text-sm text-ink-muted">
                  Ask anything about your operations. The agent translates your question into
                  precise data, charts, and actionable insights.
                </p>
                <div className="mx-auto mt-6 grid max-w-xl gap-2 sm:grid-cols-2">
                  {SUGGESTIONS.map((s) => (
                    <button key={s} onClick={() => send(s)}
                            className="rounded-md border border-line bg-card px-3 py-2.5 text-left text-[13px] text-ink transition-colors hover:border-action/50 hover:bg-action/5">
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {messages.map((m) => (
              <MessageBubble key={m.message_id} message={m} onPin={setPinTarget} />
            ))}
            {busy && (
              <div className="flex items-center gap-3 text-sm text-ink-muted">
                <Spinner className="size-4" />
                The agent is querying the database…
              </div>
            )}
            {error && <p className="text-sm text-danger">{error}</p>}
            <div ref={bottom} />
          </div>
        </div>
        <form onSubmit={submit} className="border-t border-line bg-card px-6 py-4">
          <div className="mx-auto flex max-w-3xl items-center gap-3">
            <input
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="e.g. spend by material category this quarter…"
              className="flex-1 rounded-md border border-line bg-canvas px-4 py-2.5 text-sm focus:border-action focus:outline-none focus:ring-2 focus:ring-action/20"
            />
            <select
              value={tier}
              onChange={(e) => setTier(e.target.value as "fast" | "smart")}
              title="Model tier: fast for everyday questions, smart for hard ones"
              className="rounded-md border border-line bg-canvas px-2 py-2.5 text-sm"
            >
              <option value="fast">fast</option>
              <option value="smart">smart</option>
            </select>
            <Button disabled={busy || !question.trim()} className="!px-3">
              <SendHorizonal className="size-4.5" />
            </Button>
          </div>
        </form>
      </div>

      <SaveChartDialog
        message={pinTarget}
        onClose={() => setPinTarget(null)}
        onSaved={() => { setToast("Chart pinned — it will live on the dashboard."); setTimeout(() => setToast(""), 3500); }}
      />
      {toast && (
        <div className="fixed bottom-5 left-1/2 -translate-x-1/2 rounded-md bg-navy-900 px-4 py-2.5 text-sm text-white shadow-lg">
          {toast}
        </div>
      )}
    </div>
  );
}
