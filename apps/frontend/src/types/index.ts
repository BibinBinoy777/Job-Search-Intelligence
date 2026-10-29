export interface User {
  id: string;
  email: string;
  is_operator?: boolean;
}
export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}
export interface Skill {
  id: string;
  name: string;
}
export interface Experience {
  is_current?: boolean | null;
  id: string;
  employer: string;
  title: string;
  start_date: string | null;
  end_date: string | null;
  responsibilities: string | null;
  achievements: string | null;
  technologies: string[];
}
export interface Education {
  completion_status?: "unknown" | "in_progress" | "completed";
  id: string;
  institution: string;
  qualification: string;
  field_of_study: string | null;
  start_date: string | null;
  end_date: string | null;
}
export interface Preferences {
  target_titles: string[];
  industries: string[];
  locations: string[];
  work_arrangements: string[];
  employment_types: string[];
  minimum_salary: number | null;
  currency: string | null;
  career_level: string | null;
  relocation: boolean | null;
  current_country?: string | null;
}
export interface Profile {
  id: string;
  name: string | null;
  headline: string | null;
  summary: string | null;
  qualifications: string[];
  certifications: string[];
  projects: string[];
  skills: Skill[];
  experience: Experience[];
  education: Education[];
  preferences: Preferences | null;
  updated_at: string;
}
export interface Source {
  id: string;
  name: string;
  source_type: string;
  enabled: boolean;
  operational_status: string;
  last_success_at: string | null;
  last_sync_at?: string | null;
  last_full_sync_at?: string | null;
  next_sync_at?: string | null;
  not_before_at?: string | null;
  error_code?: string | null;
  adapter_key?: string | null;
  page_limit?: number;
  schedule_hours?: number | null;
}
export interface Job {
  id: string;
  title: string;
  employer: string;
  description: string;
  responsibilities: string | null;
  qualifications: string | null;
  skills: (Skill & { kind: string })[];
  location: string | null;
  employment_type: string | null;
  work_arrangement: string | null;
  salary_min: number | null;
  salary_max: number | null;
  salary_currency: string | null;
  salary_period: string | null;
  experience_min: number | null;
  experience_max: number | null;
  source: Source | null;
  source_url: string | null;
  status: string;
  published_at: string | null;
  first_seen_at: string;
  last_seen_at: string;
  last_verified_at: string | null;
  material_updated_at: string;
  is_saved: boolean;
  source_updated_at?: string | null;
  source_expires_at?: string | null;
  status_basis?: string | null;
  location_restrictions?: string[] | null;
  timezone_restrictions?: (string | number)[] | null;
  source_categories?: string[] | null;
  availability?: string;
  is_available?: boolean;
}

export interface IngestionRun {
  id: string;
  source_id: string;
  source: Source;
  trigger: string;
  status: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  heartbeat_at: string | null;
  max_pages: number;
  pages: number;
  fetched: number;
  accepted: number;
  inserted: number;
  updated: number;
  unchanged: number;
  duplicates: number;
  rejected: number;
  skipped: number;
  retried: number;
  errors: number;
  error_code: string | null;
  has_more: boolean;
  reconciled: boolean | null;
}
export interface SourceHealth {
  sources: {
    source: Source;
    latest_run: IngestionRun | null;
    stored_jobs: number;
    available_jobs: number;
  }[];
  can_sync: boolean;
  worker_required: boolean;
  probable_duplicate_pairs: number;
}
export interface Saved {
  id: string;
  created_at: string;
  job: Job;
}
export type AppStatus =
  | "interested"
  | "planned"
  | "applied"
  | "interview"
  | "offer"
  | "rejected"
  | "withdrawn";
export const statuses: AppStatus[] = [
  "interested",
  "planned",
  "applied",
  "interview",
  "offer",
  "rejected",
  "withdrawn",
];
export interface Application {
  id: string;
  job_id: string;
  job: Job;
  status: AppStatus;
  notes: string | null;
  applied_on: string | null;
  follow_up_on: string | null;
  version: number;
  created_at: string;
  updated_at: string;
}
export interface AppEvent {
  id: string;
  application_id: string;
  from_status: string | null;
  to_status: string;
  reason: string | null;
  created_at: string;
}
export interface Overview {
  completion: number;
  completed_fields: number;
  total_fields: number;
  saved_count: number;
  application_count: number;
  recent_activity: AppEvent[];
  recent_applications: Application[];
}
