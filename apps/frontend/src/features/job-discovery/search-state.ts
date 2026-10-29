export const choices: Record<string, string[]> = {
  employment_type: [
    "full_time",
    "part_time",
    "contract",
    "internship",
    "temporary",
  ],
  work_arrangement: ["remote", "hybrid", "on_site"],
  status: ["active", "unknown", "closed", "expired"],
  availability_scope: ["available", "all", "requires_verification"],
  sort: [
    "recent",
    "text_relevance",
    "candidate_match",
    "published_desc",
    "verified_desc",
    "title",
    "employer",
    "salary_desc",
  ],
  salary_period: ["hour", "week", "fortnight", "month", "year"],
  eligibility: [
    "confirmed_compatible",
    "confirmed_mismatch",
    "unknown",
    "not_applicable",
  ],
  match_state: ["any", "current", "stale", "missing", "insufficient"],
};
const numbers: Record<string, [number, number]> = {
  page: [1, 10000],
  page_size: [1, 100],
  salary_min: [0, 999999999999],
  salary_max: [0, 999999999999],
  experience_min: [0, 80],
  experience_max: [0, 80],
  minimum_score: [0, 100],
  required_coverage: [0, 1],
};
const textFields = [
  "q",
  "title",
  "employer",
  "location",
  "country",
  "source_id",
  "salary_currency",
  "published_after",
  "updated_after",
  "verified_after",
  "skills",
  "employment_types",
  "work_arrangements",
];
export function readSearch(input: URLSearchParams): {
  params: URLSearchParams;
  error: string | null;
} {
  const params = new URLSearchParams(input);
  if (params.toString().length > 3000)
    return { params, error: "Search URL is too long. Remove some filters." };
  for (const key of params.keys()) {
    const values = params.getAll(key);
    if (!(key in numbers) && !(key in choices) && !textFields.includes(key))
      return { params, error: `Unsupported filter: ${key}` };
    if (
      !["skills", "employment_types", "work_arrangements"].includes(key) &&
      values.length > 1
    )
      return { params, error: `Use one value for ${key}.` };
    for (const value of values) {
      if (value.length > (key === "q" ? 200 : 250))
        return { params, error: `${key} is too long.` };
      if (choices[key] && value && !choices[key].includes(value))
        return { params, error: `Invalid ${key}.` };
      if (
        numbers[key] &&
        (!Number.isFinite(Number(value)) ||
          Number(value) < numbers[key][0] ||
          Number(value) > numbers[key][1] ||
          (["page", "page_size"].includes(key) &&
            !Number.isInteger(Number(value))))
      )
        return { params, error: `Invalid ${key}.` };
      if (
        key === "source_id" &&
        !/^[\da-f]{8}(-[\da-f]{4}){3}-[\da-f]{12}$/i.test(value)
      )
        return { params, error: "Invalid source identifier." };
      if (
        key.endsWith("_after") &&
        (!/(Z|[+-]\d\d:\d\d)$/.test(value) || Number.isNaN(Date.parse(value)))
      )
        return {
          params,
          error: "Date filters need an ISO timestamp with a timezone.",
        };
    }
  }
  if (
    (params.has("salary_min") ||
      params.has("salary_max") ||
      params.get("sort") === "salary_desc") &&
    !(params.get("salary_currency") && params.get("salary_period"))
  )
    return {
      params,
      error: "Salary filters require a currency and pay period.",
    };
  for (const prefix of ["salary", "experience"])
    if (
      params.has(`${prefix}_min`) &&
      params.has(`${prefix}_max`) &&
      Number(params.get(`${prefix}_max`)) < Number(params.get(`${prefix}_min`))
    )
      return { params, error: "Maximum must be at least minimum." };
  return { params, error: null };
}
export function criteriaOf(params: URLSearchParams): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  for (const [key, value] of params) {
    if (["page", "page_size"].includes(key)) continue;
    result[key] = ["skills", "employment_types", "work_arrangements"].includes(
      key,
    )
      ? params.getAll(key)
      : key in numbers
        ? Number(value)
        : value;
  }
  return result;
}
export function criteriaUrl(criteria: Record<string, unknown>) {
  const params = new URLSearchParams();
  Object.entries(criteria).forEach(([key, value]) => {
    if (value === null || value === undefined || value === "") return;
    if (Array.isArray(value))
      value.forEach((v) => params.append(key, String(v)));
    else params.set(key, String(value));
  });
  return params;
}
