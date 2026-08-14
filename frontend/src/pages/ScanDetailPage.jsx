import { useState, useEffect, useRef } from "react";
import { useParams } from "react-router-dom";
import { getScan, runScan, listScanRuns } from "../api";
import StatusBadge from "../components/StatusBadge";
import RunAccordion from "../components/RunAccordion";

const POLL_INTERVAL_MS = 1500;

function hasInFlightRun(runs) {
  return runs.some((r) => r.status === "pending" || r.status === "running");
}

export default function ScanDetailPage() {
  const { scanId } = useParams();
  const [scan, setScan] = useState(null);
  const [notFound, setNotFound] = useState(false);
  const [runs, setRuns] = useState(null);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState(null);
  const pollRef = useRef(null);

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
    listScanRuns(scanId)
      .then((fetchedRuns) => {
        setRuns(fetchedRuns);
        if (hasInFlightRun(fetchedRuns)) {
          startPolling();
        }
      })
      .catch(() => {
        // No runs yet is not an error state here; getScan's own error
        // handling above covers real fetch failures for this scan.
      });

    return stopPolling;
  }, [scanId]);

  function startPolling() {
    if (pollRef.current) return;
    pollRef.current = setInterval(async () => {
      try {
        const latest = await listScanRuns(scanId);
        setRuns(latest);
        if (!hasInFlightRun(latest)) {
          stopPolling();
        }
      } catch {
        // Transient poll failure: retried on the next tick, no error shown.
      }
    }, POLL_INTERVAL_MS);
  }

  function stopPolling() {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }

  async function handleRun() {
    setError(null);
    setStarting(true);
    try {
      const pendingRuns = await runScan(scanId);
      setRuns(pendingRuns);
      startPolling();
    } catch (err) {
      if (err.status === 409) {
        const latest = await listScanRuns(scanId);
        setRuns(latest);
        startPolling();
      } else {
        setError(err.message);
      }
    } finally {
      setStarting(false);
    }
  }

  if (notFound) {
    return <p className="text-sm text-muted-foreground">Scan not found.</p>;
  }

  if (!scan) {
    return <p className="text-sm text-muted-foreground">Loading...</p>;
  }

  const running = hasInFlightRun(runs || []);

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
          disabled={starting || running}
          className="mb-6 rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
        >
          {starting || running ? "Running..." : "Run scenarios"}
        </button>
      )}

      {runs && runs.length > 0 && (
        <div>
          <h2 className="mb-3 text-lg font-semibold tracking-tight">Results</h2>
          <RunAccordion runs={runs} scenarios={scan.scenarios} />
        </div>
      )}
    </div>
  );
}
