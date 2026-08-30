import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "TigonD Intelligent Ingestion",
  description: "AI-assisted source intelligence, quality and ingestion studio.",
  other: {
    "codex-preview": "development",
  },
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
