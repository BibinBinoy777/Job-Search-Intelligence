export interface Version {
  extraction_id?: string | null;
  extraction_status?: string | null;
  id: string;
  number: number;
  filename: string;
  detected_type: string;
  size_bytes: number;
  checksum: string;
  scan_status: string;
  created_at: string;
}
export interface Resume {
  id: string;
  name: string;
  status: string;
  version_count: number;
  versions: Version[];
  latest_extraction_id: string | null;
  latest_successful_extraction_id: string | null;
}
export interface Proposal {
  id: string;
  category: string;
  original_value: Record<string, unknown>;
  reviewed_value: Record<string, unknown> | null;
  review_state: string;
  warnings: string[];
  evidence: {
    excerpt: string;
    page: number | null;
    part: string | null;
    section: string | null;
    version_id: string;
    method: string;
  };
  applied_at: string | null;
}
export interface Extraction {
  id: string;
  version_id: string;
  status: string;
  extractor_version: string;
  revision: number;
  attempts: number;
  error_code: string | null;
  error_message: string | null;
  quality: Record<string, unknown>;
  proposals: Proposal[];
}
export interface Plan {
  id: string;
  category: string;
  action: string;
  value?: Record<string, unknown>;
  existing?: unknown;
  message?: string;
  allowed_resolutions?: string[];
}
export interface Preview {
  revision: number;
  profile_fingerprint: string;
  items: Plan[];
  unresolved_count: number;
}
export interface Confirmation {
  confirmation_id: string;
  status: string;
  changes: { proposal_id: string; action: string }[];
  unresolved_count: number;
  matching_requires_refresh: boolean;
}
