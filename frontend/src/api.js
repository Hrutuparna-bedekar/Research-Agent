const envUrl = import.meta.env.VITE_API_URL;
export const BASE = envUrl ? (envUrl.endsWith('/api') ? envUrl : `${envUrl}/api`) : "http://localhost:8000/api";

const getUserId = () => {
  let uid = localStorage.getItem("research_user_id");
  if (!uid) {
    uid = Math.random().toString(36).substring(2, 15) + Math.random().toString(36).substring(2, 15);
    localStorage.setItem("research_user_id", uid);
  }
  return uid;
};

const getHeaders = (extra = {}) => ({
  "Content-Type": "application/json",
  "X-User-ID": getUserId(),
  ...extra
});

export const startResearch = async (query, sessionId = null) => {
  const res = await fetch(`${BASE}/research/start`, {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify({ query, session_id: sessionId }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
};

export const getHistory = async (sessionId) => {
  const res = await fetch(`${BASE}/research/${sessionId}/history`, {
    headers: getHeaders()
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
};

export const getReport = async (sessionId) => {
  const res = await fetch(`${BASE}/research/${sessionId}/report`, {
    headers: getHeaders()
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
};

export const getSessions = async () => {
  const res = await fetch(`${BASE}/sessions`, {
    headers: getHeaders()
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
};

export const deleteSession = async (sessionId) => {
  const res = await fetch(`${BASE}/sessions/${sessionId}`, { 
    method: "DELETE",
    headers: getHeaders()
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
};

export const exportUrl = (sessionId, format) => {
  const url = new URL(`${BASE}/research/${sessionId}/export/${format}`);
  url.searchParams.append("user_id", getUserId());
  return url.toString();
};
