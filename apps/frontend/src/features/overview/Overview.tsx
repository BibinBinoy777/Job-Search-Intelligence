import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  ArrowRight,
  Bookmark,
  BriefcaseBusiness,
  Check,
  Compass,
  UserRound,
} from "lucide-react";
import { api } from "../../services/api-client";
import type { Overview, Profile, Page } from "../../types";
import type { Match } from "../job-matching/types";
import {
  dateLabel,
  Empty,
  ErrorBox,
  label,
  Loading,
  PageHeading,
} from "../../components/ui";

export default function OverviewPage() {
  const data = useQuery({
    queryKey: ["overview"],
    queryFn: () => api<Overview>("/overview"),
  });
  const profile = useQuery({
    queryKey: ["profile"],
    queryFn: () => api<Profile>("/profile"),
  });
  if (data.isPending) return <Loading />;
  if (data.error)
    return <ErrorBox error={data.error} retry={() => data.refetch()} />;
  const d = data.data!;
  return (
    <>
      <PageHeading
        eyebrow="A LITTLE CLARITY. A LOT OF POSSIBILITY."
        title={
          profile.data?.name
            ? `Welcome back, ${profile.data.name.split(" ")[0]}.`
            : "Your next chapter starts here."
        }
        description="Bring your opportunities, progress, and career story together."
        action={
          <Link className="primary" to="/jobs">
            Explore jobs
            <ArrowRight size={17} />
          </Link>
        }
      />
      <section className="welcome-banner">
        <div>
          <span className="eyebrow">MAKE ROOM FOR WHAT’S NEXT</span>
          <h2>
            A more intentional
            <br />
            way to find your next role.
          </h2>
          <p>
            Build your profile. Keep the right opportunities close.
            <br />
            Take the next step when you’re ready.
          </p>
          <Link to="/profile" className="text-button">
            Shape your candidate profile <ArrowRight size={16} />
          </Link>
        </div>
        <div className="path-illustration" aria-hidden="true">
          <div className="orbit orbit-a" />
          <div className="orbit orbit-b" />
          <div className="path-circle one">
            <UserRound />
          </div>
          <div className="path-circle two">
            <Compass size={32} />
          </div>
          <div className="path-circle three">
            <Check />
          </div>
          <div className="path-label">A career that feels like you.</div>
        </div>
      </section>
      <section
        className="stats-grid"
        aria-label="Your actual workspace statistics"
      >
        <div className="stat-card">
          <span className="stat-icon lavender">
            <UserRound size={20} />
          </span>
          <span>Profile completeness</span>
          <strong>
            {d.completion}
            <small>%</small>
          </strong>
          <p>
            {d.completed_fields} of {d.total_fields} profile sections added
          </p>
          <div className="progress-track">
            <div style={{ width: `${d.completion}%` }} />
          </div>
        </div>
        <Link to="/saved" className="stat-card">
          <span className="stat-icon green">
            <Bookmark size={20} />
          </span>
          <span>Saved opportunities</span>
          <strong>{d.saved_count.toString().padStart(2, "0")}</strong>
          <p>
            Worth coming back to <ArrowRight size={14} />
          </p>
        </Link>
        <Link to="/applications" className="stat-card">
          <span className="stat-icon peach">
            <BriefcaseBusiness size={20} />
          </span>
          <span>Applications tracked</span>
          <strong>{d.application_count.toString().padStart(2, "0")}</strong>
          <p>
            Every step, in one place <ArrowRight size={14} />
          </p>
        </Link>
      </section>
      <div className="overview-grid">
        <section className="panel">
          <div className="section-heading">
            <div>
              <h2>Your application journey</h2>
              <p>Keep a clear view of where things stand.</p>
            </div>
            <Link to="/applications" className="text-button">
              View all <ArrowRight size={15} />
            </Link>
          </div>
          {d.recent_applications.length ? (
            <div className="compact-list">
              {d.recent_applications.map((a) => (
                <Link key={a.id} to={`/applications?open=${a.id}`}>
                  <span className="employer-icon">{a.job.employer[0]}</span>
                  <div>
                    <strong>{a.job.title}</strong>
                    <small>{a.job.employer}</small>
                  </div>
                  <span className={`badge ${a.status}`}>{label(a.status)}</span>
                </Link>
              ))}
            </div>
          ) : (
            <Empty
              title="Every journey starts with one step"
              action={
                <Link to="/jobs" className="secondary">
                  Discover opportunities <ArrowRight size={16} />
                </Link>
              }
            >
              When you start tracking an application, its progress will appear
              here.
            </Empty>
          )}
        </section>
        <section className="panel activity-panel">
          <div className="section-heading">
            <div>
              <h2>Recent activity</h2>
              <p>Your search, as it unfolds.</p>
            </div>
            <span className="live-dot" />
          </div>
          {d.recent_activity.length ? (
            <ol className="timeline">
              {d.recent_activity.map((e) => (
                <li key={e.id}>
                  <span />
                  <div>
                    <strong>
                      {e.from_status
                        ? `Moved to ${label(e.to_status).toLowerCase()}`
                        : "Added to your tracker"}
                    </strong>
                    <small>{dateLabel(e.created_at)}</small>
                    <Link to={`/applications?open=${e.application_id}`}>
                      View application
                    </Link>
                  </div>
                </li>
              ))}
            </ol>
          ) : (
            <div className="activity-empty">
              <span className="activity-ring">
                <BriefcaseBusiness size={23} />
              </span>
              <strong>A fresh start</strong>
              <p>Your application milestones will show up here.</p>
            </div>
          )}
          <div className="quiet-note">Built around your real progress.</div>
        </section>
      </div>
      <RecommendationPreview enabled={!!profile.data} />
      <section className="next-step">
        <span className="step-number">01</span>
        <div>
          <h3>Start with your story</h3>
          <p>
            Add your skills and preferences to lay the groundwork for future
            matching.
          </p>
        </div>
        <Link to="/profile" className="text-button">
          Go to my profile <ArrowRight size={16} />
        </Link>
      </section>
    </>
  );
}

function RecommendationPreview({ enabled }: { enabled: boolean }) {
  const q = useQuery({
    queryKey: ["matches", "overview"],
    queryFn: () => api<Page<Match>>("/matches?page_size=3"),
    enabled,
    refetchOnMount: "always",
  });
  if (!enabled) return null;
  return (
    <section className="panel" style={{ marginTop: 22 }}>
      <div className="section-heading">
        <div>
          <h2>Recommendations with evidence</h2>
          <p>Calculated from your recorded qualifications.</p>
        </div>
        <Link to="/recommended" className="text-button">
          View recommendations <ArrowRight size={15} />
        </Link>
      </div>
      {q.isPending || q.isFetching ? (
        <Loading />
      ) : q.error ? (
        <ErrorBox error={q.error} retry={() => q.refetch()} />
      ) : q.data?.items.length ? (
        <div className="compact-list">
          {q.data.items.map((m) => (
            <Link key={m.id} to={`/jobs/${m.job.id}#match-analysis`}>
              <div>
                <strong>{m.job.title}</strong>
                <small>
                  {m.job.employer} ·{" "}
                  {m.evidence_coverage === null
                    ? "Evidence coverage unknown"
                    : `${Math.round(m.evidence_coverage * 100)}% requirement evidence`}
                </small>
              </div>
              <span className="badge">
                {m.score === null
                  ? "More information needed"
                  : `${m.score.toFixed(1)} relevance`}
              </span>
            </Link>
          ))}
        </div>
      ) : (
        <Empty
          title="A clearer picture starts with a refresh"
          action={
            <Link to="/recommended" className="secondary">
              Review recommendations
            </Link>
          }
        >
          Your current recommendations will appear here after an evidence-based
          calculation. A resume upload is not required.
        </Empty>
      )}
    </section>
  );
}
