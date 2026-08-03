import type { MetadataRoute } from "next";

/**
 * Minimal sitemap covering the public, unauthenticated marketing surface
 * only — /dashboard/* is intentionally excluded since it's behind auth
 * and has no SEO value (search engines can't render it usefully anyway).
 * Placeholder base URL matches app/layout.tsx's SITE_URL constant; update
 * both together once a real production domain exists.
 */
export default function sitemap(): MetadataRoute.Sitemap {
  const baseUrl = "https://investiq.app";

  return [
    {
      url: baseUrl,
      lastModified: new Date(),
      changeFrequency: "weekly",
      priority: 1,
    },
  ];
}
