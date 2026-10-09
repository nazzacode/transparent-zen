import type { SupportedWebsite } from "./ContentScripts";

export type ExtensionSettings = {
	transparentZenSettings: {
		enableTransparency: boolean;
		lightweightTransparency: boolean;
		enableWhitelist: boolean;
		textColor: string;
		primaryColor: string;
		backgroundColor: string;
		transparencyDepth: number | null;
		backgroundImage: File | Blob | null;
		backgroundImageBlur: number;
		backgroundImageOpacity: number;
		backgroundImageBrightness: number;
		disabledWebsites: Array<SupportedWebsite>;
		blacklistedDomains: Array<string>;
		siteSpecificSettings: Array<SiteSpecificSetting>;
		glassTheme?: "auto" | "dark" | "light"; // auto = follow prefers-color-scheme (desktop theme)
		glassOpacity?: number;
		glassThemeV2?: boolean; // set once the user picks a mode in the auto-aware popup (migration from old "dark" default)
	};
};

export type SiteSpecificSetting = {
	domain: string;
	enabled: boolean;
	backgroundSelectors: Array<string>;
	customStyles: string;
};
