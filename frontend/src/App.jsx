import { useState } from "react";
import { createProject, createScan, runScan } from "./api";

export default function App() {
  const [url, setUrl] = useState("");
  const [description, setDescription] = useState("");
  const [scan, setScan] = useState(null);
  const [loading, setLoading] = useState(false);
  const [runs, setRuns] = useState(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setRuns(null);
    setLoading(true);
    try {
      const project = await createProject("Ad-hoc scan", url);
      const result = await createScan(project.id, url, description);
      setScan(result);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleRun() {
    setError(null);
    setRunning(true);
    try {
      const result = await runScan(scan.id);
      setRuns(result);
    } catch (err) {
      setError(err.message);
    } finally {
      setRunning(false);
    }
  }

  return (
    <div style={{ maxWidth: 640, margin: "2rem auto", fontFamily: "sans-serif" }}>
      <h1>testcrafter</h1>
      <form onSubmit={handleSubmit}>
        <input placeholder="Target URL" value={url} onChange={(e) => setUrl(e.target.value)} style={{ width: "100%", marginBottom: 8 }} />
        <textarea placeholder="What should be tested?" value={description} onChange={(e) => setDescription(e.target.value)} style={{ width: "100%", marginBottom: 8 }} />
        <button type="submit" disabled={loading}>{loading ? "Generating..." : "Generate scenarios"}</button>
      </form>
      {error && <p style={{ color: "red" }}>{error}</p>}
      {scan && (
        <div>
          <h2>Status: {scan.status}</h2>
          <ul>
            {scan.scenarios.map((s) => (
              <li key={s.id}>{s.title}</li>
            ))}
          </ul>
          {scan.status === "ready" && (
            <button onClick={handleRun} disabled={running}>{running ? "Running..." : "Run scenarios"}</button>
          )}
        </div>
      )}
      {runs && (
        <div>
          <h2>Results</h2>
          <ul>
            {runs.map((run) => (
              <li key={run.id}>
                Scenario {run.scenario_id}: {run.status}
                <ul>
                  {run.steps.map((step) => (
                    <li key={step.id}>
                      Step {step.step_index}: {step.status} {step.log_message ? `— ${step.log_message}` : ""}
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
