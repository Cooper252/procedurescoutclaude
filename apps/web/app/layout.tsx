import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
import { AppStateProvider } from "@/components/AppState";
import { Footer, Header } from "@/components/Chrome";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "ProcedureScout — Know the price before you go", template: "%s · ProcedureScout" },
  description:
    "Compare real published prices for medical care near you, and see if you qualify for free or reduced-cost care. Free, private, no account.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#0b6e75",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <AppStateProvider>
          <Header />
          <main id="main">{children}</main>
          <Footer />
        </AppStateProvider>
      </body>
    </html>
  );
}
