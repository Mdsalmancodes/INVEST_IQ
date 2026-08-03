import type { MetadataRoute } from "next";

/**
 * Disallows the authenticated dashboard surface from crawling (no SEO
 * value behind auth) while allowing the public marketing pages.
 */
export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      allow: "/",
      disallow: "/dashboard",
    },
    sitemap: "https://investiq.app/sitemap.xml",
  };
}
