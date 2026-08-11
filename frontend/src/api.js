const BASE_URL = "http://localhost:8000";

async function handleResponse(res) {
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail || `Request failed with status ${res.status}`);
  }
  return res.json();
}

export async function createProject(name, baseUrl) {
  const res = await fetch(`${BASE_URL}/projects`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, base_url: baseUrl }),
  });
  return handleResponse(res);
}

export async function createScan(projectId, targetUrl, description) {
  const res = await fetch(`${BASE_URL}/projects/${projectId}/scans`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ target_url: targetUrl, description }),
  });
  return handleResponse(res);
}

export async function runScan(scanId) {
  const res = await fetch(`${BASE_URL}/scans/${scanId}/run`, {
    method: "POST",
  });
  return handleResponse(res);
}
