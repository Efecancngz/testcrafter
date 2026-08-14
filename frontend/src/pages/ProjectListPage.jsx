import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { createProject, listProjects } from "../api";

export default function ProjectListPage() {
  const [projects, setProjects] = useState(null);
  const [error, setError] = useState(null);
  const [name, setName] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    listProjects().then(setProjects).catch((err) => setError(err.message));
  }, []);

  async function handleCreate(e) {
    e.preventDefault();
    setError(null);
    setCreating(true);
    try {
      const project = await createProject(name, baseUrl);
      setProjects((prev) => [...(prev || []), project]);
      setName("");
      setBaseUrl("");
    } catch (err) {
      setError(err.message);
    } finally {
      setCreating(false);
    }
  }

  return (
    <div>
      <h1 className="mb-6 text-xl font-semibold tracking-tight">Projects</h1>

      <form onSubmit={handleCreate} className="mb-8 flex gap-2">
        <input
          placeholder="Project name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="rounded-md border border-border bg-muted px-3 py-2 text-sm"
        />
        <input
          placeholder="Base URL"
          value={baseUrl}
          onChange={(e) => setBaseUrl(e.target.value)}
          className="rounded-md border border-border bg-muted px-3 py-2 text-sm"
        />
        <button
          type="submit"
          disabled={creating}
          className="rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
        >
          New project
        </button>
      </form>

      {error && <p className="mb-4 text-sm text-red-400">{error}</p>}

      {projects === null && <p className="text-sm text-muted-foreground">Loading...</p>}

      {projects !== null && projects.length === 0 && (
        <p className="text-sm text-muted-foreground">No projects yet — create one above to get started.</p>
      )}

      {projects !== null && projects.length > 0 && (
        <div className="grid grid-cols-3 gap-4">
          {projects.map((p) => (
            <Link
              key={p.id}
              to={`/projects/${p.id}`}
              className="rounded-lg border border-border bg-muted/30 p-4 hover:bg-muted/50"
            >
              <div className="font-medium">{p.name}</div>
              <div className="mt-1 text-sm text-muted-foreground">{p.base_url}</div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
