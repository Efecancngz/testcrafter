const BASE_URL = "http://localhost:8000";

export async function createProject(name, baseUrl) {
  const res = await fetch(`${BASE_URL}/projects`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, base_url: baseUrl }),
  });
  return res.json();
}

export async function createScan(projectId, targetUrl, description) {
  const res = await fetch(`${BASE_URL}/projects/${projectId}/scans`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ target_url: targetUrl, description }),
  });
  return res.json();
}
