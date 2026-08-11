import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Avatar Proxy · 内部控制台",
  description: "管理项目、业务 API Key，并验证独立部署的 Seedance 视频接口。",
  icons: { icon: "/ruichi-logo.jpg", shortcut: "/ruichi-logo.jpg", apple: "/ruichi-logo.jpg" },
  openGraph: {
    title: "Avatar Proxy 内部控制台",
    description: "项目级 API Key 与 Seedance 视频接口管理。",
    images: [{ url: "/og-console.png", width: 1200, height: 630 }],
  },
  twitter: { card: "summary_large_image", title: "Avatar Proxy 内部控制台", images: ["/og-console.png"] },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="zh-CN" suppressHydrationWarning><body className={`${geistSans.variable} ${geistMono.variable}`}>{children}</body></html>;
}
