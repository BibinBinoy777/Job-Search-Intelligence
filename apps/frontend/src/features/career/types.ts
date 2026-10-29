export interface SkillEvidence {
  key: string;
  name: string;
  status: string;
  used_for_role_overlap: boolean;
  sources: {
    kind: string;
    path?: string;
    extraction_id?: string;
    proposal_id?: string;
    review_state?: string;
  }[];
  note: string;
}
export interface Listing {
  id: string;
  title: string;
  location: string | null;
  source_name: string;
  href: string;
  availability: string;
}
export interface Requirement {
  job_id: string;
  category: string;
  evidence: {
    text: string;
    field: string;
    origin: string;
    section?: string;
    start: number;
    end: number;
  }[];
  extraction: string;
}
export interface Statistic {
  key: string;
  name: string;
  count: number;
  required_count: number;
  preferred_count: number;
  denominator: number;
  percentage: number | null;
  candidate_status: string;
  observation_strength: string;
  supporting_listings: Listing[];
  requirements: Requirement[];
  support_truncated: boolean;
}
export interface Gap extends Statistic {
  priority: number;
  priority_reason: string;
  relationship: string;
  next_action: string;
  action_kind: string;
}
export interface Additional {
  job_id: string;
  category: string;
  requirement: {
    kind?: string;
    level?: string;
    minimum?: number;
    evidence: { text: string; field: string };
  };
  interpretation: string;
}
export interface Role {
  id: string;
  title: string;
  listing_count: number;
  overlap: string[];
  missing_skills: string[];
  required_skill_count: number;
  overlap_ratio: number;
  candidate_sources: { skill: string; status: string; references: unknown[] }[];
  additional_requirements: Additional[];
  representative_listings: Listing[];
  reason: string;
  evidence_strength: string;
  next_action: string;
  limitations: string[];
}
export interface Transition {
  origin: string;
  origin_kind: string;
  origin_evidence: unknown[];
  destination_id: string;
  destination: string;
  transferable_skills: string[];
  skills_to_investigate: string[];
  additional_requirements: Additional[];
  supporting_listings: Listing[];
  next_steps: string[];
  evidence_strength: string;
  limitations: string[];
}
export interface Resource {
  title: string;
  provider: string | null;
  url: string | null;
  verification_status: string;
  verified_on: string | null;
  verification_source: string | null;
  verification_evidence: string | null;
  level: string;
}
export interface Learning {
  skill_key: string;
  skill: string;
  why: string;
  practice: string;
  action_kind: string;
  supporting_job_ids: string[];
  resources: Resource[];
}
export interface Filters {
  target_role?: string;
  origin_role?: string;
  location?: string;
  source_id?: string;
  published_after?: string;
  published_before?: string;
  requirement_kind?: string;
}
export interface Career {
  analysis_version: string;
  generated_at: string;
  input_fingerprint: string;
  profile_completeness: string;
  filters: Filters;
  candidate_skills: SkillEvidence[];
  origin_roles: string[];
  market: {
    stored_listing_records: number;
    scoped_records: number;
    excluded_unavailable: number;
    analyzed_records: number;
    population_truncated: boolean;
    duplicate_records_excluded: number;
    unique_scoped_listings: number;
    relevant_listings: number;
    listings_with_usable_requirements: number;
    denominator_definition: string;
    relevance_basis: string;
    target_roles: string[];
    requirement_kind: string;
    sources: { id: string | null; name: string; count: number }[];
    locations: { label: string; count: number }[];
    publication_range: {
      earliest: string | null;
      latest: string | null;
      unknown_count: number;
    };
    geography_definition: string;
    limitations: string[];
  };
  skill_statistics: Statistic[];
  gaps: Gap[];
  roles: Role[];
  transitions: Transition[];
  learning: Learning[];
  notices: string[];
}
