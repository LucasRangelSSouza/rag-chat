import type { NextConfig } from "next";
import path from "node:path";

const nextConfig: NextConfig = {
  poweredByHeader: false,
  output: "standalone",
  compress: true,
  outputFileTracingRoot: path.join(__dirname),
};

export default nextConfig;
