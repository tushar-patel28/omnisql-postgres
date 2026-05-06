import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "OmniSQL Postgres — Natural language to PostgreSQL, fine-tuned",
  description:
    "Production-grade text-to-SQL for PostgreSQL. OmniSQL-7B fine-tuned with QLoRA on 1,800 PostgreSQL query pairs. 46% execution accuracy vs 7% baseline.",
  metadataBase: new URL("https://omnisql-pg.vercel.app"),
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