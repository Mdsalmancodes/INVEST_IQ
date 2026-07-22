import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type * as AuthApiModule from "../../../lib/auth-api";
import { authApi } from "../../../lib/auth-api";
import { RegisterForm } from "./RegisterForm";

vi.mock("../../../lib/auth-api", async () => {
  const actual = await vi.importActual<typeof AuthApiModule>("../../../lib/auth-api");
  return {
    ...actual,
    authApi: { ...actual.authApi, register: vi.fn() },
  };
});

const VALID_PASSWORD = "a-genuinely-strong-passphrase";

async function fillValidForm(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText(/full name/i), "Jane Investor");
  await user.type(screen.getByLabelText(/^email$/i), "jane@example.com");
  await user.type(screen.getByLabelText(/^password$/i), VALID_PASSWORD);
  await user.type(screen.getByLabelText(/confirm password/i), VALID_PASSWORD);
}

describe("RegisterForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders all expected fields including the password strength meter", async () => {
    const user = userEvent.setup();
    render(<RegisterForm onSuccess={vi.fn()} />);

    expect(screen.getByLabelText(/full name/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^email$/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^password$/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/confirm password/i)).toBeInTheDocument();

    await user.type(screen.getByLabelText(/^password$/i), VALID_PASSWORD);
    expect(await screen.findByText(/password strength/i)).toBeInTheDocument();
  });

  it("shows a validation error when passwords do not match", async () => {
    const user = userEvent.setup();
    render(<RegisterForm onSuccess={vi.fn()} />);

    await user.type(screen.getByLabelText(/full name/i), "Jane Investor");
    await user.type(screen.getByLabelText(/^email$/i), "jane@example.com");
    await user.type(screen.getByLabelText(/^password$/i), VALID_PASSWORD);
    await user.type(screen.getByLabelText(/confirm password/i), "a-different-passphrase");
    await user.click(screen.getByRole("button", { name: /create account/i }));

    expect(await screen.findByText(/passwords do not match/i)).toBeInTheDocument();
    expect(authApi.register).not.toHaveBeenCalled();
  });

  it("calls authApi.register and onSuccess with the email on valid submit", async () => {
    vi.mocked(authApi.register).mockResolvedValue({
      user_id: "user-123",
      email: "jane@example.com",
      message: "Registration successful.",
    });
    const onSuccess = vi.fn();
    const user = userEvent.setup();
    render(<RegisterForm onSuccess={onSuccess} />);

    await fillValidForm(user);
    await user.click(screen.getByRole("button", { name: /create account/i }));

    await waitFor(() => {
      expect(onSuccess).toHaveBeenCalledWith("jane@example.com");
    });
    expect(authApi.register).toHaveBeenCalledWith({
      email: "jane@example.com",
      password: VALID_PASSWORD,
      full_name: "Jane Investor",
    });
  });

  it("shows a server error message when registration fails (e.g. duplicate email)", async () => {
    const { ApiError } = await vi.importActual<typeof AuthApiModule>("../../../lib/auth-api");
    vi.mocked(authApi.register).mockRejectedValue(
      new ApiError("USER_ALREADY_EXISTS", "An account with this email already exists", 409)
    );
    const user = userEvent.setup();
    render(<RegisterForm onSuccess={vi.fn()} />);

    await fillValidForm(user);
    await user.click(screen.getByRole("button", { name: /create account/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/already exists/i);
  });
});
