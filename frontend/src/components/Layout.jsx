import { Link } from "react-router-dom";
import { logout } from "../api";

export default function Layout({ children, onLogout }) {
  function handleLogout() {
    logout();
    onLogout();
  }

  return (
    <div className="flex min-h-screen">
      <aside className="w-56 shrink-0 border-r border-border bg-muted/30 p-4">
        <div className="mb-8 text-lg font-semibold tracking-tight">testcrafter</div>
        <nav className="space-y-1">
          <Link to="/" className="block rounded-md px-2 py-1.5 text-sm text-foreground hover:bg-muted">
            Projects
          </Link>
        </nav>
        <button
          onClick={handleLogout}
          className="mt-8 block w-full rounded-md px-2 py-1.5 text-left text-sm text-muted-foreground hover:bg-muted hover:text-foreground"
        >
          Log out
        </button>
      </aside>
      <main className="flex-1 p-8">{children}</main>
    </div>
  );
}
