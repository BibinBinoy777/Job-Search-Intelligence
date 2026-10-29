import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, ApiError } from "../../services/api-client";
import { ErrorBox, Field } from "../../components/ui";
import type { Page } from "../../types";
import { criteriaOf, criteriaUrl } from "./search-state";
interface SavedSearch {
  id: string;
  name: string;
  criteria: Record<string, unknown>;
}
export default function SavedSearches({
  params,
  load,
  invalid,
}: {
  params: URLSearchParams;
  load: (p: URLSearchParams) => void;
  invalid: boolean;
}) {
  const client = useQueryClient();
  const [message, setMessage] = useState("");
  const query = useQuery({
    queryKey: ["saved-searches"],
    queryFn: () => api<Page<SavedSearch>>("/saved-searches?page_size=50"),
  });
  const mutation = useMutation({
    mutationFn: ({
      path = "",
      method = "POST",
      body,
    }: {
      path?: string;
      method?: string;
      body?: unknown;
    }) => api<SavedSearch>(`/saved-searches${path}`, method, body),
    onMutate: () => setMessage(""),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["saved-searches"] });
      setMessage("Saved-search change confirmed.");
    },
  });
  const use = useMutation({
    mutationFn: (id: string) =>
      api<SavedSearch>(`/saved-searches/${id}/use`, "POST"),
    onSuccess: (data) => {
      load(criteriaUrl(data.criteria));
      client.invalidateQueries({ queryKey: ["saved-searches"] });
    },
  });
  if (query.error instanceof ApiError && query.error.status === 404)
    return (
      <p>
        <Link to="/profile">Create a profile</Link> to save searches.
      </p>
    );
  return (
    <details className="panel saved-search-panel">
      <summary>Saved searches · definitions only, no automatic alerts</summary>
      <p>
        <Link
          to={`/alerts?criteria=${encodeURIComponent(JSON.stringify(criteriaOf(params)))}`}
        >
          Create an alert from these search filters
        </Link>
        . This opens a separate subscription form; saving alone does not
        subscribe.
      </p>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          const f = new FormData(e.currentTarget);
          mutation.mutate({
            body: { name: f.get("search_name"), criteria: criteriaOf(params) },
          });
        }}
      >
        <Field label="Search name">
          <input
            name="search_name"
            maxLength={100}
            required
            placeholder="Name these applied filters"
          />
        </Field>
        <button className="secondary" disabled={invalid || mutation.isPending}>
          Save current search
        </button>
      </form>
      {message && <p role="status">{message}</p>}
      {mutation.error && <ErrorBox error={mutation.error} />}
      {use.error && <ErrorBox error={use.error} />}
      {query.isPending ? (
        <p>Loading saved searches…</p>
      ) : query.error ? (
        <ErrorBox error={query.error} retry={() => query.refetch()} />
      ) : query.data?.items.length ? (
        <ul className="saved-search-list">
          {query.data.items.map((item) => (
            <li key={item.id}>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  mutation.mutate({
                    path: `/${item.id}`,
                    method: "PATCH",
                    body: { name: new FormData(e.currentTarget).get("rename") },
                  });
                }}
              >
                <Field label={`Name for ${item.name}`}>
                  <input
                    name="rename"
                    defaultValue={item.name}
                    maxLength={100}
                    required
                  />
                </Field>
                <button className="text-button" disabled={mutation.isPending}>
                  Rename
                </button>
              </form>
              <div className="saved-search-actions">
                <Link to={`/alerts?saved_search=${item.id}`}>
                  Create alert from {item.name}
                </Link>
                <button
                  className="secondary"
                  onClick={() => use.mutate(item.id)}
                  disabled={use.isPending}
                >
                  Load {item.name}
                </button>
                <button
                  className="text-button"
                  disabled={invalid || mutation.isPending}
                  onClick={() =>
                    mutation.mutate({
                      path: `/${item.id}`,
                      method: "PATCH",
                      body: { criteria: criteriaOf(params) },
                    })
                  }
                >
                  Replace with current filters
                </button>
                <button
                  className="text-button"
                  disabled={mutation.isPending}
                  onClick={() =>
                    mutation.mutate({ path: `/${item.id}`, method: "DELETE" })
                  }
                >
                  Delete {item.name}
                </button>
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <p>
          No saved searches yet. Save a definition to return to these filters
          later.
        </p>
      )}
    </details>
  );
}
