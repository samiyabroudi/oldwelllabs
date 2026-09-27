async function request(path, options = {}) {
  const res = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const detail = Array.isArray(body.detail)
      ? body.detail.map((d) => `${d.loc.at(-1)}: ${d.msg}`).join("; ")
      : body.detail;
    throw new Error(detail || `${res.status} ${res.statusText}`);
  }
  return res.json();
}

export const listFunds = () => request("/funds");
export const createFund = (fund) => request("/funds", { method: "POST", body: JSON.stringify(fund) });
export const updateFund = (id, changes) =>
  request(`/funds/${id}`, { method: "PATCH", body: JSON.stringify(changes) });
