import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { notificationsApi } from "../../../lib/notifications-api";
import { renderWithQueryClient } from "../../portfolio/test-utils";
import { NotificationPreferencesForm } from "./NotificationPreferencesForm";

vi.mock("../../../lib/notifications-api", () => ({
  notificationsApi: {
    getPreferences: vi.fn(),
    updatePreferences: vi.fn(),
  },
}));

vi.mock("../../../store/auth-store", () => ({
  useAuthStore: { getState: () => ({ accessToken: "fake-token" }) },
}));

const DEFAULT_PREFERENCES = {
  user_id: "u1",
  price_alerts_email: true,
  price_alerts_push: true,
  digest_frequency: "daily" as const,
  quiet_hours_start: null,
  quiet_hours_end: null,
};

describe("NotificationPreferencesForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows a loading state initially", () => {
    vi.mocked(notificationsApi.getPreferences).mockReturnValue(new Promise(() => {}));
    renderWithQueryClient(<NotificationPreferencesForm />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("pre-fills the form with the stored preferences", async () => {
    vi.mocked(notificationsApi.getPreferences).mockResolvedValue(DEFAULT_PREFERENCES);
    renderWithQueryClient(<NotificationPreferencesForm />);

    await waitFor(() => {
      expect(screen.getByLabelText(/digest frequency/i)).toHaveValue("daily");
    });
    expect(screen.getByLabelText(/email me/i)).toBeChecked();
    expect(screen.getByLabelText(/push notify me/i)).toBeChecked();
  });

  it("submits updated preferences", async () => {
    vi.mocked(notificationsApi.getPreferences).mockResolvedValue(DEFAULT_PREFERENCES);
    vi.mocked(notificationsApi.updatePreferences).mockResolvedValue({
      ...DEFAULT_PREFERENCES,
      price_alerts_push: false,
    });
    const user = userEvent.setup();
    renderWithQueryClient(<NotificationPreferencesForm />);

    await waitFor(() => {
      expect(screen.getByLabelText(/push notify me/i)).toBeChecked();
    });
    await user.click(screen.getByLabelText(/push notify me/i));
    await user.click(screen.getByRole("button", { name: /save preferences/i }));

    await waitFor(() => {
      expect(notificationsApi.updatePreferences).toHaveBeenCalledWith(
        expect.objectContaining({ price_alerts_push: false })
      );
    });
    expect(await screen.findByText(/preferences saved/i)).toBeInTheDocument();
  });

  it("shows a server error message when saving fails", async () => {
    vi.mocked(notificationsApi.getPreferences).mockResolvedValue(DEFAULT_PREFERENCES);
    vi.mocked(notificationsApi.updatePreferences).mockRejectedValue(new Error("Request failed"));
    const user = userEvent.setup();
    renderWithQueryClient(<NotificationPreferencesForm />);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /save preferences/i })).toBeInTheDocument();
    });
    await user.click(screen.getByRole("button", { name: /save preferences/i }));

    expect(await screen.findByText(/failed to save preferences/i)).toBeInTheDocument();
  });

  it("rejects setting quiet hours start without an end", async () => {
    vi.mocked(notificationsApi.getPreferences).mockResolvedValue(DEFAULT_PREFERENCES);
    const user = userEvent.setup();
    renderWithQueryClient(<NotificationPreferencesForm />);

    await waitFor(() => {
      expect(screen.getByLabelText(/quiet hours start/i)).toBeInTheDocument();
    });
    await user.type(screen.getByLabelText(/quiet hours start/i), "22:00");
    await user.click(screen.getByRole("button", { name: /save preferences/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/required together/i);
    expect(notificationsApi.updatePreferences).not.toHaveBeenCalled();
  });
});
