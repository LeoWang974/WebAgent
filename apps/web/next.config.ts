import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  distDir: process.env.NODE_ENV === "production" ? ".next-build" : ".next",
  async rewrites() {
    return [
      {
        destination: `${process.env.API_INTERNAL_BASE_URL ?? "http://127.0.0.1:8010"}/api/:path*`,
        source: "/api/:path*",
      },
    ];
  },
};

export default nextConfig;
