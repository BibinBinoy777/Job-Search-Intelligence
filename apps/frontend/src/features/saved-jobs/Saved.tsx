import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, ApiError } from "../../services/api-client";
import type { Page, Saved } from "../../types";
import {
  Empty,
  ErrorBox,
  Loading,
  PageHeading,
  Pagination,
} from "../../components/ui";
import { JobCard } from "../job-discovery/Jobs";

export default function SavedPage() {
  const [page, setPage] = useState(1);
  const q = useQuery({
    queryKey: ["saved", page],
    queryFn: () => api<Page<Saved>>(`/saved-jobs?page=${page}&page_size=12`),
  });
  const missingProfile = q.error instanceof ApiError && q.error.status === 404;
  return (
    <>
      <PageHeading
        eyebrow="KEEP THE POSSIBILITIES CLOSE"
        title="Your shortlist, thoughtfully saved."
        description="A place for the opportunities you want to return to. Saving a job doesn’t mean you’ve applied."
      />
      {q.isPending ? (
        <Loading />
      ) : q.error && !missingProfile ? (
        <ErrorBox error={q.error} retry={() => q.refetch()} />
      ) : missingProfile || !q.data?.items.length ? (
        <section className="panel">
          <Empty
            title={
              missingProfile
                ? "Create your profile to save opportunities"
                : "Nothing saved. Plenty ahead."
            }
            action={
              <Link
                to={missingProfile ? "/profile" : "/jobs"}
                className="primary"
              >
                {missingProfile ? "Create profile" : "Explore jobs"}
              </Link>
            }
          >
            {missingProfile
              ? "Saved jobs belong to your candidate profile."
              : "When you find something worth a closer look, save it here."}
          </Empty>
        </section>
      ) : (
        <div className="job-list">
          {q.data.items.map((s) => (
            <JobCard key={s.id} job={s.job} saved />
          ))}
        </div>
      )}
      {q.data && (
        <Pagination page={page} total={q.data.total} change={setPage} />
      )}
    </>
  );
}
