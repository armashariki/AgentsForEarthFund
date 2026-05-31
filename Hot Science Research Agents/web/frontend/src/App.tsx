import {
  AlertCircle,
  Archive,
  ChevronDown,
  Database,
  Download,
  FileText,
  History,
  Loader2,
  Lock,
  LogOut,
  Play,
  Settings2,
  Shield,
  Upload,
  User
} from "lucide-react";
import { ChangeEvent, FormEvent, useEffect, useMemo, useState } from "react";
import {
  downloadArtifact,
  listAdminRuns,
  listRuns,
  login,
  me,
  runHotScience
} from "./api";
import type {
  AdminRunHistoryItem,
  ArtifactLink,
  ProgressEvent,
  RunHistoryItem,
  RunResponse,
  UserIdentity
} from "./types";

const TOKEN_KEY = "deepgreen_hot_science_token";
const DEFAULT_SOURCES = "";
const STAGES = [
  "scanning_sources",
  "resolving_primary_sources",
  "verifying_dates_and_sources",
  "checking_access",
  "evaluating_significance",
  "attaching_coverage",
  "checking_prior_editions",
  "compiling_outputs",
  "storing_results"
];

function App() {
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY) ?? "");
  const [user, setUser] = useState<UserIdentity | null>(null);
  const [authLoading, setAuthLoading] = useState(Boolean(token));

  useEffect(() => {
    if (!token) {
      setAuthLoading(false);
      return;
    }
    me(token)
      .then((payload) => setUser(payload.user))
      .catch(() => {
        localStorage.removeItem(TOKEN_KEY);
        setToken("");
      })
      .finally(() => setAuthLoading(false));
  }, [token]);

  function handleLogin(nextToken: string, nextUser: UserIdentity) {
    localStorage.setItem(TOKEN_KEY, nextToken);
    setToken(nextToken);
    setUser(nextUser);
  }

  function handleLogout() {
    localStorage.removeItem(TOKEN_KEY);
    setToken("");
    setUser(null);
  }

  if (authLoading) {
    return <FullPageStatus label="Checking session" />;
  }

  if (!token || !user) {
    return <LoginScreen onLogin={handleLogin} />;
  }

  return <Workspace token={token} user={user} onLogout={handleLogout} />;
}

function LoginScreen({
  onLogin
}: {
  onLogin: (token: string, user: UserIdentity) => void;
}) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const payload = await login(username, password);
      onLogin(payload.access_token, payload.user);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="login-shell">
      <form className="login-panel" onSubmit={submit}>
        <div className="brand-mark">
          <FileText size={24} aria-hidden="true" />
        </div>
        <h1>DeepGreen Hot Science</h1>
        <label>
          <span>Username</span>
          <input
            autoComplete="username"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
          />
        </label>
        <label>
          <span>Password</span>
          <input
            autoComplete="current-password"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </label>
        {error ? <InlineError message={error} /> : null}
        <button className="primary-action" type="submit" disabled={loading}>
          {loading ? <Loader2 className="spin" size={18} /> : <Lock size={18} />}
          Sign in
        </button>
      </form>
    </main>
  );
}

function Workspace({
  token,
  user,
  onLogout
}: {
  token: string;
  user: UserIdentity;
  onLogout: () => void;
}) {
  const [targetMonth, setTargetMonth] = useState(previousMonth());
  const [criteriaText, setCriteriaText] = useState("");
  const [retrievalQuery, setRetrievalQuery] = useState("");
  const [sourceIds, setSourceIds] = useState(DEFAULT_SOURCES);
  const [maxResults, setMaxResults] = useState(25);
  const [result, setResult] = useState<RunResponse | null>(null);
  const [error, setError] = useState("");
  const [running, setRunning] = useState(false);
  const [downloadError, setDownloadError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setDownloadError("");
    setRunning(true);
    setResult(null);
    try {
      const response = await runHotScience(token, {
        target_month: targetMonth,
        criteria_text: criteriaText,
        retrieval_query: retrievalQuery || null,
        source_ids: splitSources(sourceIds),
        max_results_per_source: maxResults
      });
      setResult(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Run failed");
    } finally {
      setRunning(false);
    }
  }

  async function handleFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }
    setCriteriaText(await file.text());
  }

  async function handleDownload(artifact: ArtifactLink) {
    setDownloadError("");
    try {
      await downloadArtifact(token, artifact);
    } catch (err) {
      setDownloadError(err instanceof Error ? err.message : "Download failed");
    }
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">DeepGreen</p>
          <h1>Hot Science agent</h1>
        </div>
        <div className="user-cluster">
          <span className="user-chip">
            {user.is_admin ? <Shield size={15} /> : <User size={15} />}
            {user.username}
          </span>
          <button className="icon-button" onClick={onLogout} title="Sign out">
            <LogOut size={18} />
          </button>
        </div>
      </header>

      <section className="workspace-grid">
        <form className="run-panel" onSubmit={submit}>
          <div className="panel-heading">
            <div>
              <h2>Run agents</h2>
            </div>
            <button className="primary-action" type="submit" disabled={running}>
              {running ? <Loader2 className="spin" size={18} /> : <Play size={18} />}
              Run
            </button>
          </div>

          <div className="form-row">
            <label>
              <span>Target month</span>
              <input
                value={targetMonth}
                onChange={(event) => setTargetMonth(event.target.value)}
                placeholder="YYYY-MM"
              />
            </label>
          </div>

          <label className="criteria-field">
            <span>Criteria</span>
            <textarea
              value={criteriaText}
              onChange={(event) => setCriteriaText(event.target.value)}
              placeholder="Full criteria prompt"
              rows={13}
            />
          </label>

          <div className="upload-row">
            <label className="file-trigger">
              <Upload size={16} />
              Upload .md or .txt
              <input accept=".md,.txt,text/markdown,text/plain" type="file" onChange={handleFile} />
            </label>
          </div>

          <details className="fold">
            <summary>
              <Settings2 size={17} />
              Advanced settings
              <ChevronDown size={16} />
            </summary>
            <div className="advanced-grid">
              <label>
                <span>Retrieval query</span>
                <input
                  value={retrievalQuery}
                  onChange={(event) => setRetrievalQuery(event.target.value)}
                  placeholder="Optional short API query"
                />
              </label>
              <label>
                <span>Sources</span>
                <input
                  value={sourceIds}
                  onChange={(event) => setSourceIds(event.target.value)}
                  placeholder="Blank uses all enabled sources"
                />
              </label>
              <label>
                <span>Max per source</span>
                <input
                  min={1}
                  max={100}
                  type="number"
                  value={maxResults}
                  onChange={(event) => setMaxResults(Number(event.target.value))}
                />
              </label>
            </div>
          </details>

          {error ? <InlineError message={error} /> : null}
        </form>

        <aside className="status-panel">
          <h2>Status</h2>
          {running ? <RunningState /> : null}
          {!running && !result ? <EmptyState /> : null}
          {result ? (
            <RunResult
              result={result}
              downloadError={downloadError}
              onDownload={handleDownload}
            />
          ) : null}
        </aside>
      </section>

      <SecondaryPanels token={token} user={user} />
    </main>
  );
}

function RunningState() {
  return (
    <div className="running-state">
      <Loader2 className="spin" size={22} />
      <p>Running agents</p>
      <ol className="stage-list pending">
        {STAGES.map((stage) => (
          <li key={stage}>{stageLabel(stage)}</li>
        ))}
      </ol>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="empty-state">
      <FileText size={28} />
      <p>No run yet.</p>
    </div>
  );
}

function RunResult({
  result,
  downloadError,
  onDownload
}: {
  result: RunResponse;
  downloadError: string;
  onDownload: (artifact: ArtifactLink) => void;
}) {
  const sourceEvents = result.progress_events.filter((event) =>
    event.event_type.startsWith("source_")
  );
  const stageEvents = result.progress_events.filter((event) =>
    event.event_type.startsWith("stage_")
  );

  return (
    <div className="result-block">
      <div className="document-ready">
        <FileText size={24} />
        <div>
          <h3>Document ready</h3>
          <p>{result.primary_artifact.filename}</p>
        </div>
      </div>
      <button className="download-action" onClick={() => onDownload(result.primary_artifact)}>
        <Download size={18} />
        Download Word document
      </button>
      {downloadError ? <InlineError message={downloadError} /> : null}
      <div className="metric-strip">
        <Metric label="Top" value={result.summary.evaluated} />
        <Metric label="Manual" value={result.summary.manual_review} />
        <Metric label="Excluded" value={result.summary.excluded} />
        <Metric label="Errors" value={result.summary.source_errors} />
      </div>
      <ProgressTimeline events={stageEvents} />
      {sourceEvents.length ? <SourceProgress events={sourceEvents} /> : null}
    </div>
  );
}

function ProgressTimeline({ events }: { events: ProgressEvent[] }) {
  const completed = new Set(
    events
      .filter((event) => event.event_type === "stage_completed")
      .map((event) => event.stage)
  );
  return (
    <section className="mini-section">
      <h3>Stages</h3>
      <ol className="stage-list">
        {STAGES.map((stage) => (
          <li className={completed.has(stage) ? "done" : ""} key={stage}>
            {stageLabel(stage)}
          </li>
        ))}
      </ol>
    </section>
  );
}

function SourceProgress({ events }: { events: ProgressEvent[] }) {
  const completed = events.filter((event) => event.event_type === "source_completed");
  return (
    <section className="mini-section">
      <h3>Sources</h3>
      <div className="source-list">
        {completed.map((event) => (
          <div className="source-row" key={`${event.source_id}-${event.timestamp}`}>
            <span>{event.source_name ?? event.source_id}</span>
            <span>
              {event.counts.candidates ?? 0} candidates
              {event.counts.source_errors ? `, ${event.counts.source_errors} errors` : ""}
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}

function SecondaryPanels({ token, user }: { token: string; user: UserIdentity }) {
  return (
    <section className="secondary-panels">
      <HistoryPanel token={token} />
      {user.is_admin ? <AdminPanel token={token} /> : null}
    </section>
  );
}

function HistoryPanel({ token }: { token: string }) {
  const [runs, setRuns] = useState<RunHistoryItem[]>([]);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState("");

  async function load() {
    setOpen((value) => !value);
    if (runs.length) {
      return;
    }
    try {
      const payload = await listRuns(token);
      setRuns(payload.runs);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load run history");
    }
  }

  return (
    <div className="fold-panel">
      <button className="fold-button" onClick={load}>
        <History size={18} />
        Run history
        <ChevronDown size={16} />
      </button>
      {open ? <RunHistory runs={runs} error={error} /> : null}
    </div>
  );
}

function AdminPanel({ token }: { token: string }) {
  const [runs, setRuns] = useState<AdminRunHistoryItem[]>([]);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState("");

  async function load() {
    setOpen((value) => !value);
    if (runs.length) {
      return;
    }
    try {
      const payload = await listAdminRuns(token);
      setRuns(payload.runs);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load admin artifacts");
    }
  }

  return (
    <div className="fold-panel">
      <button className="fold-button" onClick={load}>
        <Database size={18} />
        Admin/debug
        <ChevronDown size={16} />
      </button>
      {open ? <AdminHistory runs={runs} error={error} token={token} /> : null}
    </div>
  );
}

function RunHistory({ runs, error }: { runs: RunHistoryItem[]; error: string }) {
  if (error) {
    return <InlineError message={error} />;
  }
  if (!runs.length) {
    return <p className="muted">No prior runs.</p>;
  }
  return (
    <div className="history-list">
      {runs.map((run) => (
        <div className="history-row" key={run.run_id}>
          <Archive size={17} />
          <div>
            <strong>{run.target_month}</strong>
            <span>{formatDate(run.created_at)}</span>
          </div>
          <span>{run.summary.evaluated} top</span>
        </div>
      ))}
    </div>
  );
}

function AdminHistory({
  runs,
  error,
  token
}: {
  runs: AdminRunHistoryItem[];
  error: string;
  token: string;
}) {
  const [downloadError, setDownloadError] = useState("");

  async function download(artifact: ArtifactLink) {
    setDownloadError("");
    try {
      await downloadArtifact(token, artifact);
    } catch (err) {
      setDownloadError(err instanceof Error ? err.message : "Download failed");
    }
  }

  if (error) {
    return <InlineError message={error} />;
  }
  if (!runs.length) {
    return <p className="muted">No debug artifacts.</p>;
  }
  return (
    <div className="admin-list">
      {downloadError ? <InlineError message={downloadError} /> : null}
      {runs.map((run) => (
        <div className="admin-row" key={run.run_id}>
          <div>
            <strong>{run.target_month}</strong>
            <span>{run.run_id}</span>
          </div>
          <div className="artifact-cluster">
            {run.artifacts.map((artifact) => (
              <button
                className="text-button"
                key={artifact.artifact_id}
                onClick={() => download(artifact)}
              >
                {artifact.kind}
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function InlineError({ message }: { message: string }) {
  return (
    <div className="inline-error">
      <AlertCircle size={16} />
      {message}
    </div>
  );
}

function FullPageStatus({ label }: { label: string }) {
  return (
    <main className="login-shell">
      <div className="loading-card">
        <Loader2 className="spin" size={22} />
        {label}
      </div>
    </main>
  );
}

function previousMonth() {
  const now = new Date();
  const month = now.getMonth();
  const year = month === 0 ? now.getFullYear() - 1 : now.getFullYear();
  const targetMonth = month === 0 ? 12 : month;
  return `${year}-${String(targetMonth).padStart(2, "0")}`;
}

function splitSources(value: string) {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function stageLabel(stage: string) {
  return stage
    .split("_")
    .map((part) => part[0].toUpperCase() + part.slice(1))
    .join(" ");
}

function formatDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(date);
}

export default App;
