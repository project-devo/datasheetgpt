import type { NextConfig } from "next";

// Same Tailwind setup as FestPass. The browser calls the Render API directly
// (NEXT_PUBLIC_API_URL), so there is no /api proxy here.
const nextConfig: NextConfig = {
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
