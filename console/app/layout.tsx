import type { Metadata } from "next";
import { Literata, JetBrains_Mono } from "next/font/google";
import "./globals.css";

const literata = Literata({
  variable: "--font-literata",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  display: "swap",
});

const mono = JetBrains_Mono({
  variable: "--font-mono",
  subsets: ["latin"],
  weight: ["400", "500"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "Best By",
  description:
    "Recall decisions for one food pantry: what to pull off the shelf, and which households already took it home.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className={`${literata.variable} ${mono.variable}`}>
        {children}
      </body>
    </html>
  );
}
