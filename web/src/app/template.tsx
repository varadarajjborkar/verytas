// Re-mounted on every navigation, so each page rises in once (see .vt-page).
export default function Template({ children }: { children: React.ReactNode }) {
  return <div className="vt-page">{children}</div>;
}
