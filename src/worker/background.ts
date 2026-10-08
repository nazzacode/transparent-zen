import type { Browser, Runtime } from "webextension-polyfill-ts";
import type { Message } from "../types/Message";

declare const browser: Browser;

browser.runtime.onMessage.addListener((message: Message, sender: Runtime.MessageSender) => {
	// from a page → that tab only; from popup/settings (extension page) → every matching tab
	const fromPage = !sender.url?.startsWith("moz-extension://");
	const tabId = sender.tab?.id;
	switch (message.action) {
		case "insertStyles": {
			if (fromPage && tabId === undefined) return Promise.resolve({ noTab: true });
			if (fromPage && tabId !== undefined) return browser.tabs.insertCSS(tabId, { file: message.filePath, frameId: sender.frameId }).then(() => ({ ok: true }));
			applyStyles(message.filePath, message.domains);
			break;
		}

		case "removeStyles": {
			if (fromPage && tabId !== undefined) browser.tabs.removeCSS(tabId, { file: message.filePath, frameId: sender.frameId });
			else if (!fromPage) removeStyles(message.filePath);
			break;
		}
	}
});

async function applyStyles(filePath?: string, domains?: Array<string>): Promise<void> {
	const tabs = await browser.tabs.query({ currentWindow: true });

	for (const tab of tabs) {
		if (!tab.id || !tab.url) continue;
		if (tab.discarded) continue;
		if (tabs.length > 40 && !tab.active) continue;
		if (domains) {
			for (const domain of domains) {
				const regex = new RegExp(domain);
				if (tab.url && regex.test(tab.url)) {
					browser.tabs.insertCSS(tab.id, { file: filePath });
				}
			}
		} else if (!tab.url.startsWith("moz-extension://")) {
			browser.tabs.insertCSS(tab.id, { file: filePath });
		}
	}
}

async function removeStyles(filePath?: string): Promise<void> {
	const tabs = await browser.tabs.query({ currentWindow: true });

	for (const tab of tabs) {
		browser.tabs.removeCSS(tab.id, { file: filePath });
	}
}
