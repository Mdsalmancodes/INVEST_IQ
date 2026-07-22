import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Standalone output — minimal runtime image per Document 7 §17.3.
  output: "standalone",
  transpilePackages: ["@investiq/ui"],
};

export default nextConfig;
