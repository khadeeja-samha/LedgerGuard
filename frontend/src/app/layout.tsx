import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "LedgerGuard Findings",
  description: "Smart Contract Auditor",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark h-full">
      <head>
        <link href="https://fonts.googleapis.com" rel="preconnect" />
        <link crossOrigin="anonymous" href="https://fonts.gstatic.com" rel="preconnect" />
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet" />
        <link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap" rel="stylesheet" />
      </head>
      <body className="bg-background text-on-background font-body-md h-screen overflow-hidden flex flex-col m-0">
        
        {/* TopAppBar */}
        <header className="bg-surface dark:bg-surface border-b border-outline-variant fixed top-0 w-full z-50 flex items-center justify-between px-gutter h-16">
          <div className="flex items-center gap-3">
            <span className="material-symbols-outlined text-primary font-headline-md text-headline-md font-bold" style={{ fontVariationSettings: "'FILL' 1" }}>security</span>
            <h1 className="font-headline-md text-headline-md font-bold text-primary m-0">LedgerGuard</h1>
          </div>
          <div className="flex items-center gap-4">
            <nav className="hidden md:flex items-center gap-6">
              <span className="text-primary border-b-2 border-primary h-16 flex items-center font-label-caps text-label-caps px-2">Findings</span>
            </nav>
          </div>
        </header>

        <div className="flex flex-1 pt-16 overflow-hidden h-full">
          {/* NavigationDrawer (Sidebar on Desktop) */}
          <aside className="bg-surface-container-low dark:bg-surface-container-low border-r border-outline-variant h-full w-64 hidden md:flex flex-col gap-unit p-gutter flex-shrink-0 m-0">
            <div className="mb-6 px-2 pt-4">
              <h2 className="font-headline-sm text-headline-sm text-primary m-0">Audit Framework</h2>
            </div>
            <nav className="flex flex-col gap-2">
              <span className="bg-secondary-container text-on-secondary-container rounded-lg flex items-center gap-3 p-3 transition-all duration-150 ease-in-out">
                <span className="material-symbols-outlined">bug_report</span>
                <span className="font-body-md text-body-md font-medium">Findings</span>
              </span>
            </nav>
            <div className="mt-auto pt-6 pb-2">
              <div className="bg-surface-container rounded p-4 border border-outline-variant">
                <div className="text-xs text-on-surface-variant mb-1 font-body-sm">Target Contract</div>
                <div className="font-code-sm text-code-sm text-on-surface truncate">Custom Target</div>
              </div>
            </div>
          </aside>

          {/* Main Content Canvas */}
          {children}
        </div>
      </body>
    </html>
  );
}
