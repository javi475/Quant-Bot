import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useAuthStore } from "../store/authStore";
import { ApiError, apiClient } from "./client";

function mockFetchOnce(status: number, body: unknown, statusText = "") {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(status === 204 ? null : JSON.stringify(body), { status, statusText }),
    ),
  );
}

describe("apiClient", () => {
  beforeEach(() => {
    useAuthStore.getState().logout();
    window.localStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("does not attach an Authorization header when logged out", async () => {
    mockFetchOnce(200, { ok: true });
    await apiClient.get("/api/whatever");
    const [, options] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect((options.headers as Headers).has("Authorization")).toBe(false);
  });

  it("attaches a Bearer Authorization header when logged in", async () => {
    useAuthStore.getState().setToken("my-token", "admin");
    mockFetchOnce(200, { ok: true });
    await apiClient.get("/api/whatever");
    const [, options] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect((options.headers as Headers).get("Authorization")).toBe("Bearer my-token");
  });

  it("returns parsed JSON on success", async () => {
    mockFetchOnce(200, { hello: "world" });
    const result = await apiClient.get<{ hello: string }>("/api/whatever");
    expect(result).toEqual({ hello: "world" });
  });

  it("returns undefined on 204 No Content", async () => {
    mockFetchOnce(204, null);
    const result = await apiClient.post("/api/whatever");
    expect(result).toBeUndefined();
  });

  it("throws ApiError with the backend's detail message on failure", async () => {
    mockFetchOnce(400, { detail: "bad request reason" });
    await expect(apiClient.get("/api/whatever")).rejects.toMatchObject({
      status: 400,
      message: "bad request reason",
    });
  });

  it("falls back to statusText when the error body isn't JSON", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("not json", { status: 500, statusText: "Server Error" })));
    await expect(apiClient.get("/api/whatever")).rejects.toMatchObject({ status: 500, message: "Server Error" });
  });

  it("logs the user out on a 401 response", async () => {
    useAuthStore.getState().setToken("stale-token", "admin");
    mockFetchOnce(401, { detail: "invalid token" });
    await expect(apiClient.get("/api/whatever")).rejects.toBeInstanceOf(ApiError);
    expect(useAuthStore.getState().token).toBeNull();
  });

  it("sends a JSON Content-Type header only when a body is present", async () => {
    mockFetchOnce(200, {});
    await apiClient.get("/api/whatever");
    const [, getOptions] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect((getOptions.headers as Headers).has("Content-Type")).toBe(false);

    mockFetchOnce(200, {});
    await apiClient.post("/api/whatever", { a: 1 });
    const [, postOptions] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect((postOptions.headers as Headers).get("Content-Type")).toBe("application/json");
  });
});
