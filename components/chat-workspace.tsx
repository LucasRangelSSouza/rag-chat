"use client";

import { useEffect, useMemo, useRef, useState, type FormEvent, type KeyboardEvent as ReactKeyboardEvent } from "react";
import {
  ArrowDown,
  ArrowLeft,
  ArrowUp,
  BookOpen,
  Check,
  ChevronDown,
  CircleAlert,
  Database,
  ExternalLink,
  FileSearch,
  Menu,
  MessageSquareText,
  Plus,
  Trash2,
  RotateCcw,
  ShieldCheck,
  X,
} from "lucide-react";
import type { Answer, Citation, CorpusHealth } from "@/lib/contracts";

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  text: string;
  citations?: Citation[];
  status?: "loading" | "answered" | "abstained" | "refused" | "error";
};

const EXAMPLES = [
  "What procurement notices include school transport services?",
  "Quais editais de material escolar foram publicados em 2026?",
  "How many procurement records are included in this release?",
];

const INITIAL_HEALTH: CorpusHealth = {
  status: "pending",
  corpus_name: "PNCP",
  model_status: "unavailable",
};

function sourceHref(citation: Citation): string | null {
  const candidate = citation.dataset?.slug
    ? `https://www.kaggle.com/datasets/${citation.dataset.slug}${citation.dataset.version ? `/versions/${citation.dataset.version}` : ""}`
    : citation.source_uri;
  try {
    const url = new URL(candidate);
    return url.protocol === "https:" && (url.hostname === "kaggle.com" || url.hostname.endsWith(".kaggle.com"))
      ? url.toString()
      : null;
  } catch {
    return null;
  }
}

function formatCitation(citation: Citation, index: number) {
  const rows = citation.record_ids?.slice(0, 4) ?? [];
  const dataset = citation.dataset?.slug?.split("/").at(-1);
  return {
    href: sourceHref(citation),
    label: citation.title || dataset || `Source ${index + 1}`,
    dataset,
    version: citation.dataset?.version,
    rows,
    chunk: citation.chunk_id,
  };
}

function CorpusBadge({ health }: { health: CorpusHealth }) {
  const label = health.status === "ready" ? "Release verified" : health.status === "unavailable" ? "Service offline" : "Release pending";
  const icon = health.status === "ready" ? <Check size={13} aria-hidden /> : health.status === "unavailable" ? <CircleAlert size={13} aria-hidden /> : <Database size={13} aria-hidden />;
  return (
    <span className={`corpus-badge corpus-badge--${health.status}`} aria-live="polite">
      {icon}
      {label}
    </span>
  );
}

function CitationCard({ citation, index, compact = false }: { citation: Citation; index: number; compact?: boolean }) {
  const item = formatCitation(citation, index);
  return (
    <article className={`citation-card${compact ? " citation-card--compact" : ""}`}>
      <div className="citation-card__icon"><FileSearch size={16} aria-hidden /></div>
      <div className="citation-card__body">
        <p className="citation-card__title">{item.label}</p>
        <p className="citation-card__meta">
          {item.dataset ? <code>{item.dataset}</code> : <span>Source record</span>}
          {item.version ? <span>Version {item.version}</span> : null}
        </p>
        {item.rows.length > 0 ? <p className="citation-card__rows">Records: {item.rows.join(", ")}{(citation.record_ids?.length ?? 0) > item.rows.length ? " …" : ""}</p> : null}
        {item.chunk ? <p className="citation-card__rows">Evidence passage <code>{item.chunk}</code></p> : null}
        {item.href ? (
          <a className="citation-card__link" href={item.href} target="_blank" rel="noreferrer">
            Open source <ExternalLink size={13} aria-hidden />
            <span className="sr-only"> (opens in a new tab)</span>
          </a>
        ) : <span className="citation-card__unavailable">Source link unavailable</span>}
      </div>
    </article>
  );
}

type Conversation = { id: string; title: string; updatedAt: number; messages: ChatMessage[] };
const STORAGE_KEY = "rag-chat.conversations.v1";
const MAX_CONVERSATIONS = 30;

function readHistory(): Conversation[] {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.filter((item) => item && typeof item.id === "string" && Array.isArray(item.messages)) : [];
  } catch {
    return [];
  }
}

function writeHistory(items: Conversation[]) {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(items.slice(0, MAX_CONVERSATIONS)));
  } catch {
    /* storage can be unavailable (private window); history then lasts for the session only */
  }
}

export function ChatWorkspace() {
  const [health, setHealth] = useState<CorpusHealth>(INITIAL_HEALTH);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [history, setHistory] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState("");
  const [question, setQuestion] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sourcesOpen, setSourcesOpen] = useState(true);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    async function check() {
      try {
        const response = await fetch("/api/health", { cache: "no-store", signal: AbortSignal.timeout(12000) });
        const result: CorpusHealth = await response.json();
        if (active) setHealth(result);
        if (active) timer = setTimeout(check, result.status === "ready" ? 60000 : 8000);
      } catch {
        if (active) {
          setHealth((current) => (current.status === "ready" ? current : { ...INITIAL_HEALTH, status: "unavailable" }));
          timer = setTimeout(check, 8000);
        }
      }
    }
    void check();
    return () => { active = false; clearTimeout(timer); };
  }, []);

  useEffect(() => {
    setHistory(readHistory());
    setActiveId(crypto.randomUUID());
  }, []);

  useEffect(() => {
    const settled = messages.filter((message) => message.status !== "loading");
    if (!activeId || !settled.length || pending) return;
    const firstQuestion = settled.find((message) => message.role === "user")?.text ?? "Research";
    setHistory((current) => {
      const next = [
        { id: activeId, title: firstQuestion.slice(0, 60), updatedAt: Date.now(), messages: settled.slice(-40) },
        ...current.filter((item) => item.id !== activeId),
      ].slice(0, MAX_CONVERSATIONS);
      writeHistory(next);
      return next;
    });
  }, [messages, activeId, pending]);

  useEffect(() => {
    function onShortcut(event: globalThis.KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        textareaRef.current?.focus();
      }
    }
    window.addEventListener("keydown", onShortcut);
    return () => window.removeEventListener("keydown", onShortcut);
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  const citations = useMemo(
    () => [...messages].reverse().find((message) => message.role === "assistant" && message.citations?.length)?.citations ?? [],
    [messages],
  );

  async function ask(text: string) {
    const prompt = text.trim();
    if (!prompt || pending || prompt.length > 1000) return;
    const userMessage: ChatMessage = { id: crypto.randomUUID(), role: "user", text: prompt };
    const responseId = crypto.randomUUID();
    setQuestion("");
    setError(null);
    setMessages((current) => [...current, userMessage, { id: responseId, role: "assistant", text: "Searching the released records…", status: "loading" }]);
    setPending(true);
    try {
      const response = await fetch("/api/answer", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ question: prompt }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(typeof payload.error === "string" ? payload.error : "The research service is unavailable.");
      const answer = payload as Answer;
      setMessages((current) => current.map((message) => message.id === responseId
        ? { ...message, text: answer.answer, citations: answer.citations, status: answer.status }
        : message));
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : "The research service is unavailable. Try again shortly.";
      setError(message);
      setMessages((current) => current.map((item) => item.id === responseId
        ? { ...item, text: message, status: "error" }
        : item));
    } finally {
      setPending(false);
      setTimeout(() => textareaRef.current?.focus(), 0);
    }
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void ask(question);
  }

  function handleKeyDown(event: ReactKeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void ask(question);
    }
  }

  function startNewConversation() {
    if (pending) return;
    setActiveId(crypto.randomUUID());
    setMessages([]);
    setQuestion("");
    setError(null);
    setSidebarOpen(false);
    textareaRef.current?.focus();
  }

  function openConversation(id: string) {
    if (pending) return;
    const target = history.find((item) => item.id === id);
    if (!target) return;
    setActiveId(id);
    setMessages(target.messages);
    setError(null);
    setSidebarOpen(false);
  }

  function deleteConversation(id: string) {
    const next = history.filter((item) => item.id !== id);
    setHistory(next);
    writeHistory(next);
    if (id === activeId) startNewConversation();
  }

  const releaseDetail = health.status === "ready"
    ? `${health.table_count ?? "—"} ${health.table_count === 1 ? "table" : "tables"} · cutoff ${health.data_cutoff ?? "not reported"}`
    : health.status === "unavailable" ? "Research service is offline" : "Full release verification is in progress";

  return (
    <div className="workspace">
      {sidebarOpen ? <button className="mobile-scrim" aria-label="Close navigation" onClick={() => setSidebarOpen(false)} /> : null}
      <aside className={`sidebar${sidebarOpen ? " sidebar--open" : ""}`} aria-label="Research navigation">
        <div className="sidebar__top">
          <a className="brand" href="https://github.com/LucasRangelSSouza" aria-label="Lucas Rangel on GitHub">
            <span className="brand__mark">LR</span>
            <span className="brand__name">RAG Chat</span>
          </a>
          <button className="icon-button sidebar__close" onClick={() => setSidebarOpen(false)} aria-label="Close navigation"><X size={18} /></button>
          <button className="new-research" onClick={startNewConversation}>
            <Plus size={17} aria-hidden />
            <span>New research</span>
            <span className="new-research__shortcut">⌘ K</span>
          </button>
          <p className="nav-label">HISTORY</p>
          <nav className="history" aria-label="Conversation history">
            {history.length === 0 ? (
              <p className="history__empty">Your conversations are saved in this browser and listed here.</p>
            ) : (
              <ul>
                {history.map((item) => (
                  <li key={item.id} className={`history__item${item.id === activeId ? " history__item--active" : ""}`}>
                    <button className="history__open" onClick={() => openConversation(item.id)} aria-current={item.id === activeId ? "true" : undefined} title={item.title}>
                      <MessageSquareText size={15} aria-hidden />
                      <span>{item.title}</span>
                    </button>
                    <button className="history__delete" onClick={() => deleteConversation(item.id)} aria-label={`Delete conversation: ${item.title}`}>
                      <Trash2 size={14} aria-hidden />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </nav>
        </div>

        <div className="sidebar__corpus">
          <p className="nav-label">ACTIVE CORPUS</p>
          <div className="corpus-card">
            <div className="corpus-card__icon"><Database size={17} aria-hidden /></div>
            <div className="corpus-card__copy">
              <strong>PNCP public data</strong>
              <span>{health.release_version ? `Release ${health.release_version}` : "First corpus profile"}</span>
            </div>
            <ChevronDown size={15} aria-hidden className="corpus-card__chevron" />
            <div className="corpus-card__status"><CorpusBadge health={health} /></div>
          </div>
          <p className="sidebar__coverage">{releaseDetail}</p>
        </div>

        <div className="sidebar__bottom">
          <div className="research-contract">
            <ShieldCheck size={17} aria-hidden />
            <div><strong>Research contract</strong><span>Answers need source records. Unsupported questions receive an abstention.</span></div>
          </div>
          <a className="portfolio-link" href="https://github.com/LucasRangelSSouza" target="_blank" rel="noreferrer">
            <span className="portfolio-link__avatar">LR</span>
            <span><strong>Lucas Rangel</strong><small>Portfolio demonstration</small></span>
            <ArrowUp size={15} className="portfolio-link__arrow" aria-hidden />
          </a>
        </div>
      </aside>

      <main id="main" className="main-area">
        <header className="topbar">
          <div className="topbar__left">
            <button className="icon-button mobile-menu" onClick={() => setSidebarOpen(true)} aria-label="Open navigation" aria-expanded={sidebarOpen}><Menu size={19} /></button>
            <div className="topbar__title"><span>Research</span><span className="topbar__slash">/</span><span className="topbar__current">Public data</span></div>
          </div>
          <div className="topbar__right">
            <CorpusBadge health={health} />
            <span className="model-status"><span className={`model-status__dot model-status__dot--${health.model_status ?? "unavailable"}`} />
              {health.model_status === "ready" ? "Model ready" : health.model_status === "extractive" ? "Cited extractive mode" : "Model not connected"}
            </span>
          </div>
        </header>

        <div className="content-grid">
          <section className="conversation" aria-label="Research conversation">
            <div className="conversation__scroll">
              {messages.length === 0 ? (
                <div className="welcome" id="welcome">
                  <div className="welcome__eyebrow"><span className="welcome__eyebrow-mark"><BookOpen size={14} aria-hidden /></span> PUBLIC PROCUREMENT RESEARCH</div>
                  <h1>Ask the record.<br /><span>Follow the evidence.</span></h1>
                  <p className="welcome__intro">Explore a versioned PNCP release through a cited research interface. Answers follow your question's language and link back to the records used.</p>
                  <div className="welcome__release">
                    <div className="welcome__release-icon"><Database size={17} aria-hidden /></div>
                    <div><strong>PNCP corpus profile</strong><span>{releaseDetail}</span></div>
                    <CorpusBadge health={health} />
                  </div>
                  <div className="prompt-section">
                    <div className="prompt-section__heading"><span>START WITH A QUESTION</span><span>Examples</span></div>
                    <div className="prompt-list">
                      {EXAMPLES.map((example) => (
                        <button key={example} className="prompt-card" onClick={() => void ask(example)} disabled={pending || health.status !== "ready"}>
                          <span>{example}</span><ArrowUp size={15} aria-hidden />
                        </button>
                      ))}
                    </div>
                    {health.status !== "ready" ? <p className="pending-note">The public chat opens after the complete catalogue is pinned and verified.</p> : null}
                  </div>
                </div>
              ) : (
                <div className="message-list" aria-live="polite" aria-relevant="additions text">
                  {messages.map((message) => (
                    <article key={message.id} className={`message message--${message.role}${message.status ? ` message--${message.status}` : ""}`}>
                      {message.role === "assistant" ? <span className="message__avatar" aria-hidden="true">R</span> : null}
                      <div className="message__content">
                        {message.role === "assistant" ? <div className="message__byline"><strong>RAG Chat</strong><span>{message.status === "loading" ? "Searching" : message.status === "answered" ? "Cited response" : message.status === "abstained" ? "Insufficient evidence" : message.status === "refused" ? "Request declined" : message.status === "error" ? "Service unavailable" : "Response"}</span></div> : null}
                        {message.status === "loading" ? <div className="thinking-line"><span className="thinking-dots" aria-hidden="true"><i /><i /><i /></span>{message.text}</div> : null}
                        {message.status === "error" ? <div className="message__error"><CircleAlert size={16} aria-hidden />{message.text}</div> : null}
                        {message.status !== "loading" && message.status !== "error" ? <p className="message__text">{message.text}</p> : null}
                        {message.role === "assistant" && message.citations?.length ? (
                          <div className="inline-citations"><div className="inline-citations__label"><FileSearch size={14} aria-hidden /> SOURCES · {message.citations.length}</div>
                            {message.citations.slice(0, 4).map((citation, index) => <CitationCard key={`${citation.chunk_id ?? citation.source_uri}-${index}`} citation={citation} index={index} compact />)}
                          </div>
                        ) : null}
                        {message.role === "assistant" && message.status === "error" ? <button className="retry-link" onClick={() => void ask(messages.at(-2)?.text ?? "")}><RotateCcw size={14} /> Try again</button> : null}
                      </div>
                    </article>
                  ))}
                  <div ref={endRef} />
                </div>
              )}
            </div>

            <div className="composer-wrap">
              {error ? <p className="composer-error" role="status"><CircleAlert size={14} aria-hidden />{error}</p> : null}
              <form className="composer" onSubmit={submit}>
                <label className="sr-only" htmlFor="question">Ask a question about the released procurement records</label>
                <textarea
                  ref={textareaRef}
                  id="question"
                  value={question}
                  onChange={(event) => setQuestion(event.target.value.slice(0, 1000))}
                  onKeyDown={handleKeyDown}
                  placeholder={health.status === "ready" ? "Ask about the released PNCP records…" : "Research will be available when the release is ready"}
                  rows={1}
                  maxLength={1000}
                  disabled={pending || health.status !== "ready"}
                />
                <div className="composer__toolbar">
                  <div className="composer__meta"><span><ShieldCheck size={14} aria-hidden /> Sources required</span><span className="composer__counter">{question.length}/1,000</span></div>
                  <button className="send-button" type="submit" aria-label="Send question" disabled={!question.trim() || pending || health.status !== "ready"}>
                    {pending ? <span className="send-spinner" aria-hidden="true" /> : <ArrowUp size={18} aria-hidden />}
                  </button>
                </div>
              </form>
              <p className="composer-disclaimer">Research support only. Check cited records before relying on an answer.</p>
              {health.model_status === "ready" ? (
                <p className="composer-disclaimer">
                  Wording comes from a Qwen-based checkpoint (an abliterated variant published by a third party), served with reasoning capability for this constrained procurement-analysis workflow. It is an implementation case study, not an authoritative source or an unrestricted assistant.
                </p>
              ) : null}
            </div>
          </section>

          <aside className={`evidence-panel${sourcesOpen ? "" : " evidence-panel--collapsed"}`} aria-label="Evidence and corpus details">
            <div className="evidence-panel__header">
              <div><p className="evidence-panel__eyebrow">RESEARCH CONTEXT</p><h2>{citations.length ? "Sources" : "Corpus details"}</h2></div>
              <button className="icon-button evidence-panel__toggle" aria-label={sourcesOpen ? "Collapse evidence panel" : "Expand evidence panel"} aria-expanded={sourcesOpen} onClick={() => setSourcesOpen(!sourcesOpen)}><ArrowLeft size={16} aria-hidden /></button>
            </div>
            <div className="evidence-panel__body">
              {citations.length ? <>
                <p className="evidence-panel__lead">Records used in the latest answer. Open the dataset to inspect its release files and source manifest.</p>
                <div className="evidence-panel__list">{citations.map((citation, index) => <CitationCard key={`${citation.chunk_id ?? citation.source_uri}-${index}`} citation={citation} index={index} />)}</div>
              </> : <>
                <div className="evidence-empty"><div className="evidence-empty__icon"><FileSearch size={20} aria-hidden /></div><strong>Evidence stays in view</strong><p>When a response cites records, the dataset, release version, and record identifiers will appear here.</p></div>
                <div className="evidence-facts">
                  <p className="nav-label">RELEASE SNAPSHOT</p>
                  <div><span>Status</span><CorpusBadge health={health} /></div>
                  <div><span>Corpus</span><strong>PNCP public data</strong></div>
                  <div><span>Cutoff</span><strong>{health.data_cutoff ?? "Pending verification"}</strong></div>
                  <div><span>Tables</span><strong>{health.table_count ?? "Pending"}</strong></div>
                </div>
              </>}
              <div className="evidence-note"><ShieldCheck size={16} aria-hidden /><p>Answers cite retrieved records. If the release does not support a claim, the assistant should say so.</p></div>
            </div>
          </aside>
        </div>

        <footer className="app-footer">
          <span>RAG Chat · A public research prototype by Lucas Rangel</span>
          <span className="app-footer__links">
            <a href="https://github.com/LucasRangelSSouza/rag-chat" target="_blank" rel="noreferrer">Interface repository</a>
            <span aria-hidden="true">·</span>
            <a href="https://github.com/LucasRangelSSouza/qwen-abliterated-api" target="_blank" rel="noreferrer">Model case</a>
            <span aria-hidden="true">·</span>
            <a href="https://www.kaggle.com/lucasrangelss/datasets" target="_blank" rel="noreferrer">Kaggle catalogue</a>
          </span>
        </footer>
      </main>
    </div>
  );
}
