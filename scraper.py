"""
Ekantipur.com scraper for entertainment news and editorial cartoons.
Uses Playwright to handle dynamic content and lazy-loaded images.
"""

from playwright.sync_api import sync_playwright
import json


def _extract_image_url(element_handle):
    """
    Extract image URL from an element, handling multiple lazy-load patterns.

    Checks (in order): img tags (src, data-src, data-original), picture/source
    srcset, and inline background-image styles. Returns the first valid URL found.
    """
    if not element_handle:
        return None

    try:
        return element_handle.evaluate(
            """el => {
                if (!el) return null;
                const container = el.closest("article, [class*='card'], [class*='item'], [class*='teaser']") || el.parentElement || el;
                const root = container || el;

                const imgs = root.querySelectorAll("img");
                for (const img of imgs) {
                    const url = img.getAttribute("src") || img.getAttribute("data-src") || img.getAttribute("data-original") || img.getAttribute("data-lazy-src");
                    if (url && (url.startsWith("http") || url.startsWith("//")))
                        return url.startsWith("//") ? "https:" + url : url;
                }

                const pictures = root.querySelectorAll("picture");
                for (const picture of pictures) {
                    const source = picture.querySelector("source[srcset]");
                    if (source) {
                        const srcset = source.getAttribute("srcset");
                        if (srcset) {
                            const url = srcset.split(/[,\\s]+/)[0].trim();
                            if (url && (url.startsWith("http") || url.startsWith("//")))
                                return url.startsWith("//") ? "https:" + url : url;
                        }
                    }
                }

                for (const div of root.querySelectorAll("[style*='background-image']")) {
                    const style = div.getAttribute("style") || "";
                    const match = style.match(/background-image:\\s*url\\s*\\(\\s*['"]?([^'")\\s]+)['"]?\\s*\\)/);
                    if (match && match[1]) {
                        const url = match[1];
                        if (url.startsWith("http") || url.startsWith("//"))
                            return url.startsWith("//") ? "https:" + url : url;
                    }
                }
                return null;
            }"""
        )
    except Exception:
        return None


def scrape_entertainment(page):
    """
    Scrape top 5 entertainment news articles from ekantipur.com/entertainment.

    Returns a list of dicts with title, image_url, category, and author.
    Handles lazy-loaded images by scrolling and searching parent containers.
    """
    data = []

    page.goto("https://ekantipur.com/entertainment", wait_until="networkidle")
    page.wait_for_selector("div.category-description", timeout=15000)

    # Scroll full page to trigger lazy-loaded images, then return to top
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    page.wait_for_timeout(1500)
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(500)

    cards = page.query_selector_all("div.category-description")
    print(f"Found {len(cards)} entertainment cards")

    for card in cards[:5]:
        try:
            # Scroll each card into view so lazy-loaded images can fire
            card.scroll_into_view_if_needed()
            page.wait_for_timeout(400)

            title_el = card.query_selector("h2 a")
            title = title_el.inner_text().strip() if title_el else None

            # Image may be inside card or in a sibling; search parent if not found
            image_url = _extract_image_url(card)
            if not image_url:
                try:
                    parent = card.evaluate_handle("el => el.closest('article, div[class]') || el.parentElement")
                    if parent:
                        parent_el = parent.as_element()
                        if parent_el:
                            image_url = _extract_image_url(parent_el)
                except Exception:
                    pass

            author_el = card.query_selector("div.author-name a")
            author = author_el.inner_text().strip() if author_el else None

            data.append({
                "title": title,
                "image_url": image_url,
                "category": "मनोरञ्जन",
                "author": author
            })

        except Exception as e:
            print("Error parsing entertainment card:", e)

    return data


def scrape_cartoon(page):
    """
    Scrape the latest editorial cartoon from ekantipur.com/cartoon.

    Returns a dict with title, image_url, and author. Caption format is
    typically "Title - Author" (e.g. "गजब छ बा! - अविन").
    """
    cartoon = {}

    page.goto("https://ekantipur.com/cartoon", wait_until="networkidle")
    page.wait_for_selector("img, a[href*='thumb.php'], a[href*='koseli']", timeout=15000)
    page.wait_for_timeout(2000)

    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(1000)

    try:
        # Run JS in page context to extract first cartoon (image + caption)
        # Structure: .cartoon-image (figure>a>img) + .cartoon-description (sibling with title - author)
        result = page.evaluate("""
            () => {
                const main = document.querySelector("main, #content, .content, [role='main']") || document.body;
                const cartoonImage = main.querySelector(".cartoon-image");
                if (!cartoonImage) return null;

                const link = cartoonImage.querySelector("a[href*='thumb.php'], a[href*='assets']");
                if (!link) return null;

                const img = link.querySelector("img");
                const href = link.getAttribute("href") || "";
                let imageUrl = img?.getAttribute("src") || img?.getAttribute("data-src") || img?.getAttribute("data-original");
                if (!imageUrl && href.startsWith("http")) imageUrl = href;

                const descEl = cartoonImage.nextElementSibling;
                let caption = descEl?.classList?.contains("cartoon-description") ? descEl.innerText?.trim() : (descEl?.innerText?.trim() || "");
                if (caption && caption.includes("\\n")) caption = caption.split("\\n")[0].trim();

                return { image_url: imageUrl || null, caption: caption || null };
            }
        """)

        if result:
            image_url = result.get("image_url")
            caption = (result.get("caption") or "").strip()

            # Fallback: .cartoon-description holds "Title - Author" when JS missed it
            if not caption:
                desc_el = page.query_selector(".cartoon-description")
                if desc_el:
                    caption = desc_el.inner_text().split("\n")[0].strip()

            title = None
            author = None
            if caption:
                if " - " in caption:
                    parts = caption.split(" - ", 1)
                    title = parts[0].strip()
                    author = parts[1].strip() if len(parts) > 1 else None
                else:
                    title = caption

            cartoon = {"title": title, "image_url": image_url, "author": author}
        else:
            all_links = page.query_selector_all("main a[href*='ekantipur.com'], a[href*='thumb.php']")
            for link in all_links[:30]:
                img = link.query_selector("img")
                href = link.get_attribute("href") or ""
                if img or "thumb.php" in href:
                    image_url = _extract_image_url(link)
                    if not image_url and href.startswith("http"):
                        image_url = href
                    if image_url:
                        caption = ""
                        try:
                            container = link.evaluate_handle("el => el.closest('article, figure, div')")
                            if container:
                                el = container.as_element()
                                if el:
                                    for sel in [".cartoon-description", "figcaption", "p", ".caption", ".title", "span"]:
                                        cap_el = el.query_selector(sel)
                                        if cap_el:
                                            t = cap_el.inner_text().strip()
                                            if t and " - " in t and len(t) < 100:
                                                caption = t
                                                break
                        except Exception:
                            pass
                        title = caption.split(" - ")[0].strip() if caption and " - " in caption else (caption or None)
                        author = caption.split(" - ", 1)[1].strip() if caption and " - " in caption else None
                        cartoon = {"title": title, "image_url": image_url, "author": author}
                        break

    except Exception as e:
        print("Cartoon scraping error:", e)

    return cartoon


def main():
    """Run both scrapers and save results to output.json."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)  # Set True for background run
        page = browser.new_page()

        entertainment_news = scrape_entertainment(page)
        cartoon_of_the_day = scrape_cartoon(page)

        output = {
            "entertainment_news": entertainment_news,
            "cartoon_of_the_day": cartoon_of_the_day
        }

        with open("output.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=4)

        print("Done! Data saved to output.json")
        browser.close()


if __name__ == "__main__":
    main()