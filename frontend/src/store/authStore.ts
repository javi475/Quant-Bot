import { create } from "zustand";
import { persist } from "zustand/middleware";

interface AuthState {
  token: string | null;
  username: string | null;
  setToken: (token: string, username: string) => void;
  logout: () => void;
}

/** Persisted to localStorage so a page refresh doesn't force a re-login —
 * the JWT itself still expires server-side after 30 minutes (DOC 1 US-030). */
export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      username: null,
      setToken: (token, username) => set({ token, username }),
      logout: () => set({ token: null, username: null }),
    }),
    { name: "ate-smp-auth" },
  ),
);
