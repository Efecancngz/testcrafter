export const BASE_URL = "http://localhost:8000";

function getToken() {
  return localStorage.getItem("token");
}

function authHeaders() {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

let onUnauthorized = () => {};
export function setUnauthorizedHandler(handler) {
  onUnauthorized = handler;
}

function handleUnauthorized() {
  localStorage.removeItem("token");
  onUnauthorized();
}

async function handleResponse(res) {
  if (res.status === 401) {
    handleUnauthorized();
  }
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail || `Request failed with status ${res.status}`);
  }
  return res.json();
}

export async function register(email, password) {
  const res = await fetch(`${BASE_URL}/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  const body = await handleResponse(res);
  localStorage.setItem("token", body.access_token);
  return body;
}

export async function login(email, password) {
  const res = await fetch(`${BASE_URL}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  const body = await handleResponse(res);
  localStorage.setItem("token", body.access_token);
  return body;
}

export function logout() {
  localStorage.removeItem("token");
}

export function isAuthenticated() {
  return !!getToken();
}

export async function createProject(name, baseUrl) {
  const res = await fetch(`${BASE_URL}/projects`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ name, base_url: baseUrl }),
  });
  return handleResponse(res);
}

export async function createScan(projectId, targetUrl, description) {
  const res = await fetch(`${BASE_URL}/projects/${projectId}/scans`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ target_url: targetUrl, description }),
  });
  return handleResponse(res);
}

export async function runScan(scanId) {
  const res = await fetch(`${BASE_URL}/scans/${scanId}/run`, {
    method: "POST",
    headers: { ...authHeaders() },
  });
  return handleResponse(res);
}

export async function fetchScreenshotUrl(path) {
  const res = await fetch(`${BASE_URL}${path}`, { headers: { ...authHeaders() } });
  if (res.status === 401) {
    handleUnauthorized();
  }
  if (!res.ok) {
    throw new Error(`Failed to load screenshot (status ${res.status})`);
  }
  const blob = await res.blob();
  return URL.createObjectURL(blob);
}
