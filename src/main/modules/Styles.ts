import type { Browser } from "webextension-polyfill-ts";

declare const browser: Browser;

// Ask the worker to inject into *this* tab. If the worker can't see a tab for us
// (headless/WebDriver contexts), fall back to a <link> to the packaged stylesheet.
export async function insertStyles(filePath?: string, domains?: Array<string>): Promise<void> {
	if (!filePath) return;
	const response = await browser.runtime.sendMessage({ action: "insertStyles", filePath, domains }).catch(() => null);
	if (!response?.noTab || document.querySelector(`link[data-tz-file="${filePath}"]`)) return;
	const link = document.createElement("link");
	link.rel = "stylesheet";
	link.href = browser.runtime.getURL(filePath);
	link.dataset.tzFile = filePath;
	(document.head ?? document.documentElement).append(link);
}

export function removeStyles(filePath: string): void {
	browser.runtime.sendMessage({ action: "removeStyles", filePath });
	document.querySelector(`link[data-tz-file="${filePath}"]`)?.remove();
}
