export interface Notification {
  id: string;
  category: string;
  title: string;
  message: string;
  href: string;
  job_id: string | null;
  application_id: string | null;
  in_app_status: string;
  read_at: string | null;
  created_at: string;
  deliveries: {
    id: string;
    channel: string;
    status: string;
    attempts: number;
    error_code: string | null;
    delivered_at: string | null;
  }[];
}
export interface Preferences {
  job_alerts: boolean;
  reminders: boolean;
  in_app: boolean;
  email: boolean;
  timezone: string;
}
export interface Capabilities {
  preferences: Preferences;
  email_available: boolean;
  frequency: string;
  quiet_hours_supported: boolean;
  worker_required: boolean;
}
export interface Subscription {
  id: string;
  name: string;
  criteria: Record<string, unknown>;
  saved_search_id: string | null;
  enabled: boolean;
  include_updates: boolean;
  email: boolean;
  revision: number;
  starts_after: string;
  created_at: string;
}
export interface Reminder {
  id: string;
  application_id: string;
  kind: string;
  due_at: string;
  timezone: string;
  note: string | null;
  email: boolean;
  status: string;
  revision: number;
  completed_at: string | null;
}
export interface Task {
  id: string;
  kind: string;
  status: string;
  attempts: number;
  retries: number;
  due_at: string;
  lease_until: string | null;
  error_code: string | null;
  outcome: Record<string, unknown>;
  created_at: string;
}
export interface AutomationStatus {
  enabled: boolean;
  email_available: boolean;
  last_completed_tick_at: string | null;
  worker_required: boolean;
  health_note: string;
  task_counts: Record<string, number>;
  outbox_counts: Record<string, number>;
  pending_reminders: number;
  due_reminders: number;
  retrying_source_runs: number;
  pending_task_oldest: string | null;
}
