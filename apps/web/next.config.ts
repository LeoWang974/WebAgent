/**
 * File purpose: Configures the Next.js application build output.
 * Main declarations: nextConfig keeps the frontend deployable behind the single public port;
 * API forwarding is implemented by the streaming Route Handler under src/app/api.
 */

import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  distDir: process.env.NODE_ENV === "production" ? ".next-build" : ".next",
};

export default nextConfig;
