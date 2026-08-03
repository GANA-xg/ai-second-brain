import "./globals.css";
import { AuthProvider } from "@/context/AuthContext";
import { DocumentProvider } from "@/context/DocumentContext";
import { ToastProvider } from "@/components/ui/Toast";
import { ThemeProvider } from "@/context/ThemeContext";

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <title>Second Brain</title>
        <meta name="description" content="Your personal AI knowledge companion" />
        <script
          dangerouslySetInnerHTML={{
            __html: `
              try {
                const t = localStorage.getItem('theme');
                if (t === 'dark' || (!t && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
                  document.documentElement.classList.add('dark');
                }
              } catch(e) {}
            `,
          }}
        />
      </head>
      <body className="bg-canvas text-ink antialiased transition-colors duration-200">
        <ThemeProvider>
          <AuthProvider>
            <DocumentProvider>
              <ToastProvider>{children}</ToastProvider>
            </DocumentProvider>
          </AuthProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
