import { useState, useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, NavLink, Navigate, Route, Routes } from "react-router-dom";
import {
  ArrowRight,
  Bookmark,
  BriefcaseBusiness,
  Compass,
  Database,
  LayoutDashboard,
  LogOut,
  Menu,
  Settings2,
  Sparkles,
  ScanSearch,
  UserRound,
  X,
} from "lucide-react";
import { api, ApiError } from "../services/api-client";
import type { User } from "../types";
import { ErrorBox, Field, Loading } from "../components/ui";
import OverviewPage from "../features/overview/Overview";
import ProfilePage from "../features/candidate-profile/Profile";
import JobsPage, { JobDetailPage } from "../features/job-discovery/Jobs";
import SavedPage from "../features/saved-jobs/Saved";
import ApplicationsPage from "../features/applications/Applications";
import SettingsPage from "../features/settings/Settings";
import SourcesPage from "../features/job-discovery/Sources";
import ComparisonPage from "../features/job-discovery/Comparison";
import RecommendedPage from "../features/job-matching/Recommended";
import ResumesPage from "../features/resumes/Resumes";
import CareerPage from "../features/career/Career";
import NotificationsPage, {
  NotificationIndicator,
} from "../features/automation/Notifications";
import AlertsPage from "../features/automation/Alerts";
import RemindersPage from "../features/automation/Reminders";

const links = [
  ["/", "Overview", LayoutDashboard],
  ["/jobs", "Discover jobs", Compass],
  ["/recommended", "Recommended jobs", ScanSearch],
  ["/career", "Career intelligence", Sparkles],
  ["/notifications", "Notifications", Bookmark],
  ["/alerts", "Job alerts", ScanSearch],
  ["/reminders", "Application reminders", BriefcaseBusiness],
  ["/sources", "Data sources", Database],
  ["/saved", "Saved jobs", Bookmark],
  ["/applications", "Applications", BriefcaseBusiness],
  ["/profile", "My profile", UserRound],
  ["/resumes", "Resume intelligence", BriefcaseBusiness],
  ["/settings", "Settings", Settings2],
] as const;

function AuthPage() {
  const client = useQueryClient();
  const [register, setRegister] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const form = new FormData(event.currentTarget);
    try {
      const user = await api<User>(
        `/auth/${register ? "register" : "login"}`,
        "POST",
        Object.fromEntries(form),
      );
      // A fresh login may follow an expired session for a different account.
      // Do not carry candidate-private query data across that boundary.
      await client.cancelQueries();
      client.removeQueries({
        predicate: (query) => query.queryKey[0] !== "user",
      });
      client.setQueryData(["user"], user);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="auth-layout">
      <div className="auth-story">
        <Link to="/" className="brand">
          <span className="brand-symbol">
            <Compass size={23} />
          </span>
          Job Search<span>Intelligence</span>
        </Link>
        <div>
          <div className="eyebrow">YOUR NEXT CHAPTER STARTS HERE</div>
          <h1>
            A thoughtful search.
            <br />A meaningful next step.
          </h1>
          <p>
            A personal space to understand your strengths, explore
            opportunities, and keep your career moving.
          </p>
          <div className="story-line" />
          <small>Phase 7 · Your search, with timely follow-ups</small>
        </div>
      </div>
      <main className="auth-form">
        <div className="eyebrow">WELCOME TO YOUR WORKSPACE</div>
        <h1>
          {register ? "Start your next chapter" : "Good to see you again"}
        </h1>
        <p>
          {register
            ? "Create an account to begin building your candidate profile."
            : "Sign in to pick up your job search where you left off."}
        </p>
        <form onSubmit={submit}>
          <Field label="Email address">
            <input
              name="email"
              type="email"
              autoComplete="email"
              required
              maxLength={320}
            />
          </Field>
          <Field label="Password" hint="Use 12–128 characters.">
            <input
              name="password"
              type="password"
              autoComplete={register ? "new-password" : "current-password"}
              required
              minLength={12}
              maxLength={128}
            />
          </Field>
          {error !== null && <ErrorBox error={error} />}
          <button className="primary wide" disabled={busy}>
            {busy ? "Please wait…" : register ? "Create account" : "Sign in"}
            <ArrowRight size={17} />
          </button>
        </form>
        <button
          className="text-button auth-switch"
          onClick={() => {
            setRegister(!register);
            setError(null);
          }}
        >
          {register
            ? "Already have an account? Sign in"
            : "New here? Create an account"}
        </button>
        <p className="small muted">
          Your account uses a private server-side session. Job-source listings
          retain their source and availability evidence.
        </p>
      </main>
    </div>
  );
}

export default function App() {
  const client = useQueryClient();
  useEffect(() => {
    const changed = () => {
      client.invalidateQueries({ queryKey: ["matching-status"] });
      client.invalidateQueries({ queryKey: ["career"] });
      client.invalidateQueries({ queryKey: ["matches"] });
      client.invalidateQueries({ queryKey: ["match"] });
      client.invalidateQueries({ queryKey: ["jobs"] });
      client.invalidateQueries({ queryKey: ["comparison"] });
    };
    window.addEventListener("candidate-updated", changed);
    return () => window.removeEventListener("candidate-updated", changed);
  }, [client]);
  const user = useQuery({
    queryKey: ["user"],
    queryFn: () => api<User>("/auth/me"),
  });
  const [mobile, setMobile] = useState(false);
  const [logoutError, setLogoutError] = useState<unknown>(null);
  if (user.isPending) return <Loading />;
  if (user.error)
    return user.error instanceof ApiError && user.error.status === 401 ? (
      <AuthPage />
    ) : (
      <div className="standalone-error">
        <ErrorBox error={user.error} retry={() => user.refetch()} />
      </div>
    );
  if (!user.data) return null;
  async function logout() {
    try {
      await api("/auth/logout", "POST");
      client.clear();
      await client.invalidateQueries();
      window.location.assign("/");
    } catch (e) {
      setLogoutError(e);
    }
  }
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <aside className={`sidebar ${mobile ? "open" : ""}`}>
        <Link to="/" className="brand" onClick={() => setMobile(false)}>
          <span className="brand-symbol">
            <Compass size={24} />
          </span>
          Job Search<span>Intelligence</span>
        </Link>
        <div className="nav-caption">YOUR WORKSPACE</div>
        <nav aria-label="Main navigation">
          {links.map(([to, text, Icon]) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              onClick={() => setMobile(false)}
            >
              <Icon size={19} />
              {text}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="phase-note">
            <Sparkles size={18} />
            <strong>A search grounded in real data</strong>
            <p>
              Inspect source data and matching evidence. Recommendations reflect
              your recorded qualifications.
            </p>
            <span className="phase-tag">PHASE 07 · AUTOMATION</span>
          </div>
          <div className="account">
            <span className="avatar">{user.data.email[0].toUpperCase()}</span>
            <div>
              <strong>Personal account</strong>
              <small title={user.data.email}>{user.data.email}</small>
            </div>
            <button
              className="icon-button"
              onClick={logout}
              aria-label="Sign out"
            >
              <LogOut size={17} />
            </button>
          </div>
          {logoutError !== null && <ErrorBox error={logoutError} />}
        </div>
      </aside>
      {mobile && (
        <button
          className="mobile-scrim"
          aria-label="Close navigation"
          onClick={() => setMobile(false)}
        />
      )}
      <div className="workspace">
        <div className="topbar">
          <button
            className="icon-button mobile-menu"
            aria-label={mobile ? "Close menu" : "Open menu"}
            onClick={() => setMobile(!mobile)}
          >
            {mobile ? <X /> : <Menu />}
          </button>
          <span>Your career, with intention.</span>
          <div>
            <NotificationIndicator />
            <span className="status-dot" />
            Personal workspace{" "}
            <span className="avatar small-avatar">
              {user.data.email[0].toUpperCase()}
            </span>
          </div>
        </div>
        <main id="main">
          <Routes>
            <Route path="/" element={<OverviewPage />} />
            <Route path="/profile" element={<ProfilePage />} />
            <Route path="/resumes" element={<ResumesPage />} />
            <Route path="/career" element={<CareerPage />} />
            <Route path="/notifications" element={<NotificationsPage />} />
            <Route path="/alerts" element={<AlertsPage />} />
            <Route path="/reminders" element={<RemindersPage />} />
            <Route path="/jobs" element={<JobsPage />} />
            <Route path="/compare" element={<ComparisonPage />} />
            <Route path="/recommended" element={<RecommendedPage />} />
            <Route path="/sources" element={<SourcesPage />} />
            <Route path="/jobs/:id" element={<JobDetailPage />} />
            <Route path="/saved" element={<SavedPage />} />
            <Route path="/applications" element={<ApplicationsPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
        <footer>
          JOB SEARCH INTELLIGENCE <span>One thoughtful step at a time.</span>
        </footer>
      </div>
    </div>
  );
}
