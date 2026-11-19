import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "辩论工坊 | 框架稿工作台",
  description: "题解、人工确认、框架生成与审核的本地 Mock 工作台",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html lang="zh-CN"><body>{children}</body></html>;
}
