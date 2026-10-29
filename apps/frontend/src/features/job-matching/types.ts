import type { Job } from "../../types";
export interface Evidence {
  text: string;
  field?: string;
  path?: string;
  origin?: string;
  kind?: string;
  section?: string | null;
}
export interface SkillAssessment {
  key: string;
  name: string;
  state: string;
  candidate_evidence: Evidence[];
  job_evidence: Evidence[];
}
export interface Assessment {
  assessment_status: string;
  score: number | null;
  ranking_version: string;
  profile_completeness: string;
  eligibility: {
    status: string;
    excluded: boolean;
    checks: {
      code: string;
      status: string;
      message: string;
      evidence: Record<string, unknown>;
    }[];
    limitations: string[];
  };
  features: Record<
    string,
    { value: number | null; reason: string; details: Record<string, unknown> }
  >;
  skills: {
    required: SkillAssessment[];
    preferred: SkillAssessment[];
    ambiguous_mentions: { name: string; evidence: Evidence[] }[];
  };
  evidence_coverage: {
    value: number | null;
    supported_units: number;
    identified_units: number;
    definition: string;
  };
  weight_coverage: number;
  contributing_weights: Record<string, number>;
  unavailable_components: string[];
  normalization: string;
  positive_factors: { code: string; text: string }[];
  concerns: { code: string; text: string; skills?: string[] }[];
  unknown_information: { code: string; text: string }[];
  score_interpretation: string;
}
export interface Match {
  id: string;
  job: Job;
  score: number | null;
  eligibility_status: string;
  assessment_status: string;
  evidence_coverage: number | null;
  ranking_version: string;
  generated_at: string;
  is_stale: boolean;
  stale_reasons: string[];
  assessment: Assessment;
}
export interface Pair {
  state: string;
  match: Match | null;
  message: string;
}
export interface Refresh {
  id: string;
  status: string;
  considered: number;
  calculated: number;
  reused: number;
  failed: number;
  has_more: boolean;
  next_job_id: string | null;
  finished_at: string;
  errors: { job_id: string; code: string }[];
}
export interface MatchingStatus {
  ranking_version: string;
  profile_completeness: string;
  available_job_count: number;
  current_results: number;
  stale_results: number;
  uncalculated_jobs: number;
  all_available_jobs_current: boolean;
  last_refresh: Refresh | null;
  max_batch: number;
}
