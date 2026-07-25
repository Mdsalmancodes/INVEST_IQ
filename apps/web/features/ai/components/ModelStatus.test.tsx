import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { aiApi, type ModelStatusResponse } from "../../../lib/ai-api";
import { useAuthStore } from "../../../store/auth-store";
import { renderWithQueryClient } from "../../portfolio/test-utils";
import { ModelStatus } from "./ModelStatus";

vi.mock("../../../lib/ai-api", () => ({
  aiApi: {
    getModelStatus: vi.fn(),
    trainModel: vi.fn(),
    retrainModel: vi.fn(),
    deleteModel: vi.fn(),
  },
}));

function base64UrlEncode(input: string): string {
  return btoa(input).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function makeToken(role: string): string {
  const header = base64UrlEncode(JSON.stringify({ alg: "HS256", typ: "JWT" }));
  const body = base64UrlEncode(
    JSON.stringify({ sub: "u", role, exp: Math.floor(Date.now() / 1000) + 900 })
  );
  return `${header}.${body}.fake-signature`;
}

const statusResponse: ModelStatusResponse = {
  families: [
    {
      family: "lstm",
      active_version: {
        id: "11111111-1111-1111-1111-111111111111",
        version_tag: "20240601T120000",
        trained_at: "2024-06-01T12:00:00Z",
        status: "active",
        validation_metrics: { rmse: 1.2 },
        artifact_location: "/models/lstm/v1.pt",
      },
      version_count: 1,
    },
    {
      family: "finbert",
      active_version: null,
      version_count: 0,
    },
  ],
};

describe("ModelStatus", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.getState().clearSession();
  });

  it("shows a loading state initially", () => {
    vi.mocked(aiApi.getModelStatus).mockReturnValue(new Promise(() => {}));
    renderWithQueryClient(<ModelStatus />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("renders an active version for a trained family and 'Not trained' for an untrained one", async () => {
    vi.mocked(aiApi.getModelStatus).mockResolvedValue(statusResponse);
    renderWithQueryClient(<ModelStatus />);

    await waitFor(() => {
      expect(screen.getByText("LSTM")).toBeInTheDocument();
    });
    expect(screen.getByText("Active")).toBeInTheDocument();
    expect(screen.getByText("Version: 20240601T120000")).toBeInTheDocument();
    expect(screen.getByText("FinBERT")).toBeInTheDocument();
    expect(screen.getByText("Not trained")).toBeInTheDocument();
  });

  it("shows an error state when the request fails", async () => {
    vi.mocked(aiApi.getModelStatus).mockRejectedValue(new Error("Network error"));
    renderWithQueryClient(<ModelStatus />);

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });
  });

  describe("admin panel", () => {
    it("is not rendered for a logged-out user", async () => {
      vi.mocked(aiApi.getModelStatus).mockResolvedValue(statusResponse);
      renderWithQueryClient(<ModelStatus />);

      await waitFor(() => expect(screen.getByText("LSTM")).toBeInTheDocument());
      expect(screen.queryByText("Model Administration")).not.toBeInTheDocument();
    });

    it("is not rendered for a non-admin (Basic User) role", async () => {
      useAuthStore.getState().setAccessToken(makeToken("user"));
      vi.mocked(aiApi.getModelStatus).mockResolvedValue(statusResponse);
      renderWithQueryClient(<ModelStatus />);

      await waitFor(() => expect(screen.getByText("LSTM")).toBeInTheDocument());
      expect(screen.queryByText("Model Administration")).not.toBeInTheDocument();
    });

    it("is rendered for an admin, and can trigger a train request", async () => {
      useAuthStore.getState().setAccessToken(makeToken("admin"));
      vi.mocked(aiApi.getModelStatus).mockResolvedValue(statusResponse);
      vi.mocked(aiApi.trainModel).mockResolvedValue({
        model_version: statusResponse.families[0]?.active_version as never,
        validation_metrics: { rmse: 1.1 },
      });
      renderWithQueryClient(<ModelStatus />);

      await waitFor(() => expect(screen.getByText("Model Administration")).toBeInTheDocument());

      await userEvent.type(screen.getByLabelText("Symbol"), "aapl");
      await userEvent.click(screen.getByRole("button", { name: "Train" }));

      await waitFor(() => {
        expect(aiApi.trainModel).toHaveBeenCalledWith({ family: "lstm", symbol: "AAPL" });
      });
    });

    it("is rendered for a super_admin and can trigger a delete request", async () => {
      useAuthStore.getState().setAccessToken(makeToken("super_admin"));
      vi.mocked(aiApi.getModelStatus).mockResolvedValue(statusResponse);
      vi.mocked(aiApi.deleteModel).mockResolvedValue(undefined);
      renderWithQueryClient(<ModelStatus />);

      await waitFor(() => expect(screen.getByText("Model Administration")).toBeInTheDocument());

      await userEvent.type(
        screen.getByLabelText("Model version id (to delete)"),
        "11111111-1111-1111-1111-111111111111"
      );
      await userEvent.click(screen.getByRole("button", { name: "Delete" }));

      await waitFor(() => {
        expect(aiApi.deleteModel).toHaveBeenCalledWith("11111111-1111-1111-1111-111111111111");
      });
    });
  });
});
