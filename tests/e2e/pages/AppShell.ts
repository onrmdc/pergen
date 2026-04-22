import { Page, expect } from "@playwright/test";

/**
 * Tiny Page Object for the global SPA shell.
 *
 * The Pergen frontend is a hash-routed single-page app. Every page
 * lives in a `<section id="page-<name>">` and the router toggles the
 * `.active` class. Nav links are plain `<a href="#name">` anchors in
 * the menu drawer plus on the Home dashboard.
 */
export class AppShell {
  constructor(public readonly page: Page) {}

  /**
   * Load the SPA at the given hash route and wait for the matching
   * page section to become active.
   */
  async gotoHash(hash: string): Promise<void> {
    const url = hash.startsWith("#") ? `/${hash}` : `/#${hash}`;
    await this.page.goto(url);
    await this.waitForActive(hash.replace(/^#/, ""));
  }

  /**
   * Navigate by setting `location.hash` (mirrors a user clicking a
   * nav link) and wait for the section with id="page-<name>" to gain
   * the `.active` class.
   */
  async navigateTo(name: string): Promise<void> {
    await this.page.evaluate((h) => {
      window.location.hash = h;
    }, name);
    await this.waitForActive(name);
  }

  async waitForActive(name: string): Promise<void> {
    const section = this.page.locator(`#page-${name}`);
    await expect(section).toHaveClass(/(^|\s)active(\s|$)/, { timeout: 5_000 });
  }

  async currentHash(): Promise<string> {
    return this.page.evaluate(() => window.location.hash);
  }
}

/**
 * Canonical list of nav hashes shipped in `backend/static/index.html`
 * (menu drawer order). `prepost-results`, `custom`, and `help` exist as
 * pages but are not advertised as standalone menu entries; they have
 * their own dedicated specs only where they ship a real form.
 */
export const NAV_HASHES = [
  "home",
  "prepost",
  "nat",
  "findleaf",
  "bgp",
  "restapi",
  "transceiver",
  "credential",
  "routemap",
  "inventory",
  "notepad",
  "diff",
  "subnet",
  "help",
] as const;

export type NavHash = (typeof NAV_HASHES)[number];
