import { useState, useEffect } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { getProject, listProjectScans, createScan } from "../api";
import StatusBadge from "../components/StatusBadge";

export default function ProjectDetailPage() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const [project, setProject] = useState(null);
  const [scans, setScans] = useState(null);
  const [notFound, setNotFound] = useState(false);
  const [error, setError] = useState(null);
  const [url, setUrl] = useState("");
  const [description, setDescription] = useState("");
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    setNotFound(false);
    Promise.all([getProject(projectId), listProjectScans(projectId)])
      .then(([p, s]) => {
        setProject(p);
        setScans(s);
      })
      .catch((err) => {
        if (err.status === 404) {
          setNotFound(true);
        } else {
          setError(err.message);
        }
      });
  }, [projectId]);

  async function handleCreateScan(e) {
    e.preventDefault();
    setError(null);
    setCreating(true);
    try {
      const scan = await createScan(projectId, url, description);
      navigate(`/scans/${scan.id}`);
    } catch (err) {
      setError(err.message);
    } finally {
      setCreating(false);
    }
  }

  if (notFound) {
    return <p className="text-sm text-muted-foreground">Project not found.</p>;
  }

  if (!project || scans === null) {
    return <p className="text-sm text-muted-foreground">Loading...</p>;
  }

  return (
    <div>
      <Link to="/" className="text-sm text-muted-foreground hover:text-foreground">
        &larr; Projects
      </Link>
      <h1 className="mb-1 mt-2 text-xl font-semibold tracking-tight">{project.name}</h1>
      <p className="mb-6 text-sm text-muted-foreground">{project.base_url}</p>

      <form onSubmit={handleCreateScan} className="mb-8 flex gap-2">
        <input
          placeholder="Target URL"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          className="rounded-md border border-border bg-muted px-3 py-2 text-sm"
        />
        <input
          placeholder="What should be tested?"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          className="w-64 rounded-md border border-border bg-muted px-3 py-2 text-sm"
        />
        <button
          type="submit"
          disabled={creating}
          className="rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
        >
          {creating ? "Scanning..." : "New scan"}
        </button>
      </form>

      {error && <p className="mb-4 text-sm text-red-400">{error}</p>}

      {scans.length === 0 && (
        <p className="text-sm text-muted-foreground">No scans yet — start one above.</p>
      )}

      {scans.length > 0 && (
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-border text-muted-foreground">
              <th className="pb-2 font-medium">Target URL</th>
              <th className="pb-2 font-medium">Status</th>
              <th className="pb-2 font-medium">Created</th>
            </tr>
          </thead>
          <tbody>
            {scans.map((s) => (
              <tr key={s.id} className="border-b border-border/50">
                <td className="py-2">
                  <Link to={`/scans/${s.id}`} className="hover:underline">
                    {s.target_url}
                  </Link>
                </td>
                <td className="py-2">
                  <StatusBadge status={s.status} />
                </td>
                <td className="py-2 text-muted-foreground">{new Date(s.created_at).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
