import { ArrowLeft, ArrowRight, FolderSearch, RefreshCw } from "lucide-react";
import {
  Children,
  cloneElement,
  isValidElement,
  useId,
  type ReactElement,
  type ReactNode,
} from "react";

export const label = (text: string | null | undefined) =>
  text
    ? text.replaceAll("_", " ").replace(/^\w/, (c) => c.toUpperCase())
    : "Not specified";
export const dateLabel = (value: string | null) =>
  value
    ? new Date(value).toLocaleDateString(undefined, {
        day: "numeric",
        month: "short",
        year: "numeric",
      })
    : "Not provided";
export const splitList = (text: string) => [
  ...new Set(
    text
      .split(",")
      .map((x) => x.trim())
      .filter(Boolean),
  ),
];

export function Field({
  label: text,
  children,
  hint,
}: {
  label: string;
  children: ReactNode;
  hint?: string;
}) {
  const id = useId();
  // Keep the label's accessible name concise and expose hints as descriptions.
  // Search controls may wrap their input in a decorative icon span.
  function decorate(nodes: ReactNode): ReactNode {
    return Children.map(nodes, (node) => {
      if (!isValidElement(node)) return node;
      const element = node as ReactElement<{
        children?: ReactNode;
        id?: string;
        "aria-describedby"?: string;
      }>;
      if (["input", "select", "textarea"].includes(String(element.type))) {
        return cloneElement(element, {
          id,
          "aria-describedby": hint ? `${id}-hint` : undefined,
        });
      }
      return element.props.children
        ? cloneElement(element, {}, decorate(element.props.children))
        : element;
    });
  }
  return (
    <div className="field">
      <label htmlFor={id}>{text}</label>
      {decorate(children)}
      {hint && <small id={`${id}-hint`}>{hint}</small>}
    </div>
  );
}
export function ErrorBox({
  error,
  retry,
}: {
  error: unknown;
  retry?: () => void;
}) {
  return (
    <div role="alert" className="error">
      {error instanceof Error ? error.message : "Something went wrong."}
      {retry && (
        <button className="text-button" onClick={retry}>
          <RefreshCw size={14} />
          Try again
        </button>
      )}
    </div>
  );
}
export function Loading() {
  return (
    <div role="status" className="loading">
      <span className="spinner" />
      Loading your workspace…
    </div>
  );
}
export function Empty({
  title,
  children,
  action,
}: {
  title: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="empty">
      <div className="empty-icon">
        <FolderSearch size={30} strokeWidth={1.5} />
      </div>
      <h3>{title}</h3>
      <p>{children}</p>
      {action}
    </div>
  );
}
export function Pagination({
  page,
  total,
  size = 12,
  change,
}: {
  page: number;
  total: number;
  size?: number;
  change: (p: number) => void;
}) {
  const pages = Math.max(1, Math.ceil(total / size));
  return (
    <div className="pagination">
      <span>
        {total} {total === 1 ? "record" : "records"} · Page {page} of {pages}
      </span>
      <div>
        <button
          aria-label="Previous page"
          disabled={page <= 1}
          onClick={() => change(page - 1)}
        >
          <ArrowLeft size={16} />
        </button>
        <button
          aria-label="Next page"
          disabled={page >= pages}
          onClick={() => change(page + 1)}
        >
          <ArrowRight size={16} />
        </button>
      </div>
    </div>
  );
}
export function PageHeading({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow: string;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <header className="page-heading">
      <div>
        <div className="eyebrow">{eyebrow}</div>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {action}
    </header>
  );
}
