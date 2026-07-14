"use client";
import type { Metadata } from "next";
import "./globals.css";
import { AuthProvider } from "@/context/AuthContext";

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <head>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <title>Second Brain</title>
        <meta name="description" content="Your personal AI knowledge companion" />
      </head>
      <body className="bg-surface text-text-primary antialiased">
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
