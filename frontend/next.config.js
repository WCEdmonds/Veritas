/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000',
    NEXT_PUBLIC_AGENCY_TOKEN: process.env.NEXT_PUBLIC_AGENCY_TOKEN || 'dev-token-12345',
  },
}

module.exports = nextConfig
