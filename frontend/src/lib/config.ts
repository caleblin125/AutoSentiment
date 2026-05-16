/** API base URL — set `VITE_API_URL` in `.env` (see `.env.example`). */
export function getApiBaseUrl(): string {
  const base = import.meta.env.VITE_API_URL as string | undefined
  return (base?.replace(/\/$/, '') || 'http://localhost:8000').trim()
}
