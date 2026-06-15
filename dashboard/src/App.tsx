import { Landing } from "./components/Landing";
import { Dashboard } from "./components/Dashboard";

/* Two routes, no router dependency: "/" is the story, "/dashboard" is the terminal.
   Vite (and any static host with SPA fallback) serves index.html for both. */

export default function App() {
  const path = window.location.pathname;
  return path.startsWith("/dashboard") ? <Dashboard /> : <Landing />;
}
