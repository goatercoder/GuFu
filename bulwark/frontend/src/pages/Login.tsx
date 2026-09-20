import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useLogin } from "../api/hooks";

export default function Login() {
  const [password, setPassword] = useState("");
  const login = useLogin();
  const navigate = useNavigate();

  function submit(event: FormEvent) {
    event.preventDefault();
    login.mutate(password, { onSuccess: () => navigate("/") });
  }

  return (
    <div className="login-shell">
      <div className="card login-card">
        <div className="card-body">
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 18 }}>
            <span className="brand-mark" aria-hidden="true">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                   strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 2l8 4v6c0 5-3.4 8.7-8 10-4.6-1.3-8-5-8-10V6z" />
              </svg>
            </span>
            <div>
              <div className="brand-name">Bulwark</div>
              <div className="brand-sub">CMMC Level 2 readiness</div>
            </div>
          </div>

          <form onSubmit={submit}>
            <div className="field">
              <label htmlFor="password">Administrator password</label>
              <input
                id="password"
                type="password"
                value={password}
                autoFocus
                autoComplete="current-password"
                onChange={(event) => setPassword(event.target.value)}
              />
              <div className="field-hint">
                Set with <code className="inline">BULWARK_ADMIN_PASSWORD</code>, or generated into
                <code className="inline">data/admin_password.txt</code> on first start.
              </div>
            </div>

            {login.isError ? (
              <div className="callout bad" style={{ marginBottom: 12 }}>
                {login.error instanceof Error ? login.error.message : "Sign-in failed"}
              </div>
            ) : null}

            <button type="submit" className="btn btn-primary" style={{ width: "100%" }}
                    disabled={login.isPending || !password}>
              {login.isPending ? "Signing in…" : "Sign in"}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
