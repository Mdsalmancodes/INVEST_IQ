import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type * as AuthApiModule from "../../../lib/auth-api";
import { authApi } from "../../../lib/auth-api";
import { LoginForm } from "./LoginForm";

vi.mock("../../../lib/auth-api", async () => {
  const actual = await vi.importActual<typeof AuthApiModule>("../../../lib/auth-api");
  return {
    ...actual,
    authApi: { ...actual.authApi, login: vi.fn() },
  };
});

describe("LoginForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders email and password fields", () => {
    render(<LoginForm onSuccess={vi.fn()} />);
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
  });

  it("shows validation errors for an invalid email without calling the API", async () => {
    const user = userEvent.setup();
    render(<LoginForm onSuccess={vi.fn()} />);

    await user.type(screen.getByLabelText(/email/i), "not-an-email");
    await user.type(screen.getByLabelText(/password/i), "somepassword");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    expect(await screen.findByText(/valid email/i)).toBeInTheDocument();
    expect(authApi.login).not.toHaveBeenCalled();
  });

  it("calls authApi.login and onSuccess with the access token on valid submit", async () => {
    vi.mocked(authApi.login).mockResolvedValue({
      access_token: "fake-access-token",
      token_type: "bearer",
    });
    const onSuccess = vi.fn();
    const user = userEvent.setup();
    render(<LoginForm onSuccess={onSuccess} />);

    await user.type(screen.getByLabelText(/email/i), "user@example.com");
    await user.type(screen.getByLabelText(/password/i), "correctpassword");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => {
      expect(onSuccess).toHaveBeenCalledWith("fake-access-token");
    });
  });

  it("shows a server error message when login fails", async () => {
    const { ApiError } = await vi.importActual<typeof AuthApiModule>("../../../lib/auth-api");
    vi.mocked(authApi.login).mockRejectedValue(
      new ApiError("INVALID_CREDENTIALS", "Invalid email or password", 401)
    );
    const user = userEvent.setup();
    render(<LoginForm onSuccess={vi.fn()} />);

    await user.type(screen.getByLabelText(/email/i), "user@example.com");
    await user.type(screen.getByLabelText(/password/i), "wrongpassword");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/invalid email or password/i);
  });
});
