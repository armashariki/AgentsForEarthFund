export type UserIdentity = {
  username: string;
  is_admin: boolean;
};

export type ArtifactLink = {
  artifact_id: string;
  run_id: string;
  kind: string;
  filename: string;
  path: string;
  download_url: string;
  mime_type: string;
  size_bytes: number;
};

export type ProgressEvent = {
  event_type: string;
  stage: string;
  message: string;
  run_id?: string | null;
  target_month?: string | null;
  source_id?: string | null;
  source_name?: string | null;
  counts: Record<string, number>;
  detail?: string | null;
  timestamp: string;
};

export type RunSummary = {
  run_id: string;
  target_month: string;
  user_criteria: string;
  raw_candidates: number;
  source_errors: number;
  unresolved_press: number;
  manual_review: number;
  verified: number;
  evaluated: number;
  preprints: number;
  excluded: number;
};

export type RunResponse = {
  run_id: string;
  target_month: string;
  summary: RunSummary;
  primary_artifact: ArtifactLink;
  progress_events: ProgressEvent[];
};

export type RunHistoryItem = {
  run_id: string;
  created_at: string;
  expires_at: string;
  target_month: string;
  requested_by?: string | null;
  summary: RunSummary;
  primary_artifact?: ArtifactLink | null;
};

export type AdminRunHistoryItem = RunHistoryItem & {
  artifacts: ArtifactLink[];
};

export type RunRequest = {
  target_month: string;
  criteria_text: string;
  retrieval_query?: string | null;
  source_ids: string[];
  max_results_per_source: number;
};
