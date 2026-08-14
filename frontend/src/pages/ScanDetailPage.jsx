import { useState, useEffect } from "react";
import { useParams, Link } from "react-router-dom";
import { getScan, runScan } from "../api";
import StatusBadge from "../components/StatusBadge";
import Screenshot from "../components/Screenshot";

export default function ScanDetailPage() {
  const { scanId } = useParams();
  const [scan, setScan] = useState(null);
  const [notFound, setNotFound] = useState(false);
  const [runs, setRuns] = useState(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    setNotFound(false);
    setRuns(null);
    getScan(scanId)
      .then(setScan)
      .catch((err) => {
        if (err.status === 404) {
          setNotFound(true);
        } else {
          setError(err.message);
        }
      });
  }, [scanId]);

  async function handleRun() {
    setError(null);
    setRunning(true);
    try {
      const result = await runScan(scanId);
      setRuns(result);
    } catch (err) {
      setError(err.message);
    } finally {
      setRunning(false);
    }
  }

  if (notFound) {
    return <p className="text-sm text-muted-foreground">Scan not found.</p>;
  }

  if (!scan) {
    return <p className="text-sm text-muted-foreground">Loading...</p>;
  }

  return (
    <div>
      <h1 className="mb-1 text-xl font-semibold tracking-tight">{scan.target_url}</h1>
      <div className="mb-6">
        <StatusBadge status={scan.status} />
      </div>

      {scan.status === "blocked" && (
        <p className="mb-4 text-sm text-yellow-400">
          This site uses {scan.blocked_reason} bot protection and couldn't be scanned.
        </p>
      )}

      {error && <p className="mb-4 text-sm text-red-400">{error}</p>}

      <ul className="mb-6 space-y-1 text-sm">
        {scan.scenarios.map((s) => (
          <li key={s.id}>{s.title}</li>
        ))}
      </ul>

      {scan.status === "ready" && (
        <button
          onClick={handleRun}
          disabled={running}
          className="mb-6 rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
        >
          {running ? "Running..." : "Run scenarios"}
        </button>
      )}

      {runs && (
        <div>
          <h2 className="mb-3 text-lg font-semibold tracking-tight">Results</h2>
          <ul className="space-y-4">
            {runs.map((run) => (
              <li key={run.id}>
                <div className="mb-2 flex items-center gap-2">
                  <span className="text-sm">Scenario {run.scenario_id}</span>
                  <StatusBadge status={run.status} />
                </div>
                <ul className="space-y-2 pl-4">
                  {run.steps.map((step) => (
                    <li key={step.id} className="text-sm">
                      Step {step.step_index}: {step.status} {step.log_message ? `— ${step.log_message}` : ""}
                      {step.screenshot_path && (
                        <div className="mt-1">
                          <Screenshot path={step.screenshot_path} stepIndex={step.step_index} />
                        </div>
                      )}
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
