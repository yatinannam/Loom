import type { Metadata } from "next"
import { Hanken_Grotesk, JetBrains_Mono } from "next/font/google"

import { AppShell } from "@/components/app-shell"
import { Toaster } from "@/components/ui/sonner"

import "./globals.css"

const hanken = Hanken_Grotesk({ variable: "--font-hanken", subsets: ["latin"] })
const jetbrains = JetBrains_Mono({ variable: "--font-jetbrains", subsets: ["latin"] })

export const metadata: Metadata = {
  title: "Loom",
  description: "GraphRAG for multi-hop question answering, compared against standard RAG.",
}

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className={`${hanken.variable} ${jetbrains.variable} font-sans antialiased`}>
        <AppShell>{children}</AppShell>
        <Toaster position="bottom-right" />
      </body>
    </html>
  )
}
