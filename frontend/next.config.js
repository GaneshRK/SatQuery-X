/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: 'http://localhost:8000/:path*',
      },
      {
        source: '/v1/:path*',
        destination: 'http://localhost:8000/v1/:path*',
      },
    ];
  },
};

module.exports = nextConfig;
