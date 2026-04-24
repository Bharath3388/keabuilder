/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    // In production on Vercel, vercel.json handles rewrites at the edge.
    // next.config.js rewrites are only used for local development.
    if (process.env.VERCEL) return [];
    const backendUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl}/api/:path*`,
      },
      {
        source: "/storage/:path*",
        destination: `${backendUrl}/storage/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
