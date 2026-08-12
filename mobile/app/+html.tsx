import { ScrollViewStyleReset } from "expo-router/html";
import type { PropsWithChildren } from "react";

/**
 * Expo Router 的 Web 根 HTML 樣板（僅影響 Web／PWA 版本，不影響原生 App）。
 *
 * 2026-08-12 新增：關閉手機瀏覽器的雙指縮放／雙擊縮放，讓網頁版更接近原生 App 的操作
 * 手感（`maximum-scale=1, user-scalable=no`）。這是單純的 viewport 設定，不需要把
 * 專案改成真正的原生 App 也能達到同樣效果。
 */
export default function Root({ children }: PropsWithChildren) {
  return (
    <html lang="zh-Hant">
      <head>
        <meta charSet="utf-8" />
        <meta httpEquiv="X-UA-Compatible" content="IE=edge" />
        <meta
          name="viewport"
          content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no,viewport-fit=cover"
        />
        {/* 2026-08-12 新增：加入主畫面時使用真正的羅賓森大頭貼，而不是瀏覽器預設用 App
            名稱第一個字產生的替代圖示；同時補上 manifest.json 讓「加入主畫面」以全螢幕
            模式開啟（不顯示網址列），體驗更接近原生 App。 */}
        <link rel="manifest" href="/manifest.json" />
        <link rel="icon" href="/icon.png" />
        <link rel="apple-touch-icon" href="/icon.png" />
        <meta name="theme-color" content="#0F766E" />
        <meta name="apple-mobile-web-app-capable" content="yes" />
        <meta name="apple-mobile-web-app-status-bar-style" content="default" />
        <meta name="apple-mobile-web-app-title" content="羅賓森" />
        <ScrollViewStyleReset />
      </head>
      <body>{children}</body>
    </html>
  );
}
