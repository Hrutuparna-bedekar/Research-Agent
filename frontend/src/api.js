const BASE = "http://localhost:8000/api";

export const startResearch = async (query, sessionId = null) => {
  const res = await fetch(`${BASE}/research/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, session_id: sessionId }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
};

export const getReport = async (sessionId) => {
  const res = await fetch(`${BASE}/research/${sessionId}/report`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
};

export const getSessions = async () => {
  const res = await fetch(`${BASE}/sessions`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
};

export const deleteSession = async (sessionId) => {
  const res = await fetch(`${BASE}/sessions/${sessionId}`, { method: "DELETE" });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
};

export const exportUrl = (sessionId, format) =>
  `${BASE}/research/${sessionId}/export/${format}`;
