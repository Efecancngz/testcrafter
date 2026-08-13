import { useState, useEffect } from "react";
import { createProject, createScan, runScan, register, login, logout, isAuthenticated, fetchScreenshotUrl, setUnauthorizedHandler } from "./api";

function Screenshot({ path, stepIndex }) {
  const [src, setSrc] = useState(null);

  useEffect(() => {
    let objectUrl;
    let cancelled = false;
    fetchScreenshotUrl(path).then((url) => {
      if (cancelled) {
        URL.revokeObjectURL(url);
        return;
      }
      objectUrl = url;
      setSrc(url);
    }).catch(() => {});
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [path]);

  if (!src) return null;
  return <img src={src} alt={`Step ${stepIndex} screenshot`} loading="lazy" style={{ maxWidth: 200 }} />;
}

function AuthForm({ onAuthenticated }) {
  const [mode, setMode] = useState("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      if (mode === "login") {
        await login(email, password);
      } else {
        await register(email, password);
      }
      onAuthenticated();
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div style={{ maxWidth: 320, margin: "4rem auto", fontFamily: "sans-serif" }}>
      <h1>testcrafter</h1>
      <form onSubmit={handleSubmit}>
        <input placeholder="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} style={{ width: "100%", marginBottom: 8 }} />
        <input placeholder="Password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} style={{ width: "100%", marginBottom: 8 }} />
        <button type="submit" disabled={submitting}>{mode === "login" ? "Log in" : "Register"}</button>
      </form>
      {error && <p style={{ color: "red" }}>{error}</p>}
      <button onClick={() => setMode(mode === "login" ? "register" : "login")} style={{ marginTop: 8 }}>
        {mode === "login" ? "Need an account? Register" : "Have an account? Log in"}
      </button>
    </div>
  );
}

export default function App() {
  const [authenticated, setAuthenticated] = useState(isAuthenticated());
  const [url, setUrl] = useState("");
  const [description, setDescription] = useState("");
  const [scan, setScan] = useState(null);
  const [loading, setLoading] = useState(false);
  const [runs, setRuns] = useState(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    setUnauthorizedHandler(() => setAuthenticated(false));
  }, []);

  if (!authenticated) {
    return <AuthForm onAuthenticated={() => setAuthenticated(true)} />;
  }

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

  function handleLogout() {
    logout();
    setAuthenticated(false);
    setScan(null);
    setRuns(null);
  }

  return (
    <div style={{ maxWidth: 640, margin: "2rem auto", fontFamily: "sans-serif" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1>testcrafter</h1>
        <button onClick={handleLogout}>Log out</button>
      </div>
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
                      {step.screenshot_path && (
                        <div>
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
