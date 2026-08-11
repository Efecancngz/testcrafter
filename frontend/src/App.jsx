import { useState } from "react";
import { createProject, createScan } from "./api";

export default function App() {
  const [url, setUrl] = useState("");
  const [description, setDescription] = useState("");
  const [scan, setScan] = useState(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setLoading(true);
    const project = await createProject("Ad-hoc scan", url);
    const result = await createScan(project.id, url, description);
    setScan(result);
    setLoading(false);
  }

  return (
    <div style={{ maxWidth: 640, margin: "2rem auto", fontFamily: "sans-serif" }}>
      <h1>testcrafter</h1>
      <form onSubmit={handleSubmit}>
        <input placeholder="Target URL" value={url} onChange={(e) => setUrl(e.target.value)} style={{ width: "100%", marginBottom: 8 }} />
        <textarea placeholder="What should be tested?" value={description} onChange={(e) => setDescription(e.target.value)} style={{ width: "100%", marginBottom: 8 }} />
        <button type="submit" disabled={loading}>{loading ? "Generating..." : "Generate scenarios"}</button>
      </form>
      {scan && (
        <div>
          <h2>Status: {scan.status}</h2>
          <ul>
            {scan.scenarios.map((s) => (
              <li key={s.id}>{s.title}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
