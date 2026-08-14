import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { login, register } from "../api";

export default function LoginPage() {
  const [mode, setMode] = useState("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const navigate = useNavigate();

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
      navigate("/");
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto mt-24 max-w-sm">
      <h1 className="mb-6 text-xl font-semibold tracking-tight">testcrafter</h1>
      <form onSubmit={handleSubmit} className="space-y-3">
        <input
          placeholder="Email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="w-full rounded-md border border-border bg-muted px-3 py-2 text-sm"
        />
        <input
          placeholder="Password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="w-full rounded-md border border-border bg-muted px-3 py-2 text-sm"
        />
        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
        >
          {mode === "login" ? "Log in" : "Register"}
        </button>
      </form>
      {error && <p className="mt-3 text-sm text-red-400">{error}</p>}
      <button
        onClick={() => setMode(mode === "login" ? "register" : "login")}
        className="mt-4 text-sm text-muted-foreground hover:text-foreground"
      >
        {mode === "login" ? "Need an account? Register" : "Have an account? Log in"}
      </button>
    </div>
  );
}
