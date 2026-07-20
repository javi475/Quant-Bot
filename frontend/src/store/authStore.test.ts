import { beforeEach, describe, expect, it } from "vitest";

import { useAuthStore } from "./authStore";

describe("authStore", () => {
  beforeEach(() => {
    useAuthStore.getState().logout();
    window.localStorage.clear();
  });

  it("starts logged out", () => {
    expect(useAuthStore.getState().token).toBeNull();
    expect(useAuthStore.getState().username).toBeNull();
  });

  it("setToken stores token and username", () => {
    useAuthStore.getState().setToken("abc123", "admin");
    expect(useAuthStore.getState().token).toBe("abc123");
    expect(useAuthStore.getState().username).toBe("admin");
  });

  it("logout clears token and username", () => {
    useAuthStore.getState().setToken("abc123", "admin");
    useAuthStore.getState().logout();
    expect(useAuthStore.getState().token).toBeNull();
    expect(useAuthStore.getState().username).toBeNull();
  });

  it("persists across store re-reads (localStorage-backed)", () => {
    useAuthStore.getState().setToken("persisted-token", "admin");
    const raw = window.localStorage.getItem("ate-smp-auth");
    expect(raw).toBeTruthy();
    expect(JSON.parse(raw!).state.token).toBe("persisted-token");
  });
});
