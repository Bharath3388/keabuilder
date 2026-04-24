import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "KeaBuilder — AI-Powered SaaS Platform",
  description: "AI capabilities for funnels, lead capture, and automation",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <div className="min-h-screen">
          <nav className="bg-kea-800 text-white shadow-lg">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
              <div className="flex items-center justify-between h-16">
                <a href="/" className="flex items-center space-x-2">
                  <span className="text-2xl font-bold">Kea</span>
                  <span className="text-kea-300 text-lg">Builder</span>
                </a>
                <div className="flex space-x-4">
                  <a href="/leads" className="hover:text-kea-300 px-3 py-2 rounded-md text-sm font-medium">
                    Lead Intelligence
                  </a>
                  <a href="/generate" className="hover:text-kea-300 px-3 py-2 rounded-md text-sm font-medium">
                    Content Generator
                  </a>
                  <a href="/brand-kit" className="hover:text-kea-300 px-3 py-2 rounded-md text-sm font-medium">
                    Brand Kit
                  </a>
                  <a href="/assets" className="hover:text-kea-300 px-3 py-2 rounded-md text-sm font-medium">
                    Asset Library
                  </a>
                </div>
              </div>
            </div>
          </nav>
          <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}
