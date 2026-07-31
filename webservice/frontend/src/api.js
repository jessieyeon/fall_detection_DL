async function req(path, options = {}) {
  const res = await fetch(path, {
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
  return res.json();
}

export const login = (email, password) =>
  req("/api/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
export const logout = () => req("/api/auth/logout", { method: "POST" });
export const me = () => req("/api/auth/me");
