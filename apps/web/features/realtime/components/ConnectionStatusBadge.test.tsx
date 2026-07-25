import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ConnectionStatusBadge } from "./ConnectionStatusBadge";
import { useRealtimeConnection } from "../hooks/useRealtimeConnection";
import type { RealtimeConnectionState } from "../hooks/useRealtimeConnection";

vi.mock("../hooks/useRealtimeConnection", () => ({
  useRealtimeConnection: vi.fn(),
}));

function mockConnectionState(state: RealtimeConnectionState): void {
  vi.mocked(useRealtimeConnection).mockReturnValue({
    connectionState: state,
    subscribe: () => () => {},
  });
}

describe("ConnectionStatusBadge", () => {
  it("renders nothing while connected", () => {
    mockConnectionState("connected");
    render(<ConnectionStatusBadge />);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("renders nothing while offline (logged out)", () => {
    mockConnectionState("offline");
    render(<ConnectionStatusBadge />);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("shows a Connecting badge while connecting", () => {
    mockConnectionState("connecting");
    render(<ConnectionStatusBadge />);
    expect(screen.getByRole("status")).toHaveTextContent("Connecting…");
  });

  it("shows a Reconnecting badge while reconnecting", () => {
    mockConnectionState("reconnecting");
    render(<ConnectionStatusBadge />);
    expect(screen.getByRole("status")).toHaveTextContent("Reconnecting…");
  });
});
