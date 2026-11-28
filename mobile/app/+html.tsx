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
        {/* 2026-11-28（見 docs/ADR/debug/mobile-app.md）：Robin 回報不管 iOS 或 Android，只要是從
            登入頁「導頁」進到首頁（而不是直接重新整理/重開 App 直接落在首頁），畫面就可以被用力
            左右滑動、版面會跟著位移；但直接重開 App 落在首頁時完全鎖死不會動。研判是 Stack
            導頁切換時某個畫面短暫比螢幕寬（例如切換動畫），導致瀏覽器把文件的「可橫向捲動範圍」
            撐大後沒有收回來，`expo-router/html` 內建的 `ScrollViewStyleReset` 只鎖住
            `body{overflow:hidden}`，沒有同時限制寬度，不足以完全擋住這種情況。這裡額外明確鎖定
            `html`／`body`／`#root` 的寬度上限與橫向捲動，當作最後一道防線，不管哪個元件日後不小心
            撐寬都擋得住。 */}
        <style
          dangerouslySetInnerHTML={{
            __html: "html,body,#root{overflow-x:hidden;max-width:100%;width:100%}",
          }}
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
