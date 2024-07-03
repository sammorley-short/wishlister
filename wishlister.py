import random
import time
from dataclasses import dataclass
from urllib.parse import urlparse

import bs4
import requests

DELAY_MIN = 1000
DELAY_MAX = 2000
WISHLIST_URL = "https://www.amazon.co.uk/hz/wishlist/ls/1BXMRCIR7311A"
WISHLIST_DOMAIN = urlparse(WISHLIST_URL).netloc


@dataclass
class WishlistItem:
    title: str
    url: str
    price: float = None


class PageRequestError(Exception):
    "Raised if the page request succeeds, but we don't get the right one."


class PriceNotFoundError(Exception):
    "Thrown if no strategy returns a price."


def start_session():
    # Inits
    print("Setting up session")
    headers = {
        # "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:87.0) Gecko/20100101 Firefox/87.0",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate",
        "DNT": "1",
        # "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }
    session = requests.session()
    session.headers.update(headers)

    return session


def run_wishlist_scraper(session):
    print("\nRunning wishlist scraping")
    wishlist = parse_wishlist(session, WISHLIST_URL)
    print("Wishlist parsed")
    delay()

    PRICE_THRESHOLD = 16
    items_below_threshold = []
    for wishlist_item in wishlist:
        url = wishlist_item.url
        response = request_page(session, url)
        price = find_item_price(response)
        wishlist_item.price = price

        name = wishlist_item.title
        print(f"{name}: {price}")

        if price <= PRICE_THRESHOLD:
            items_below_threshold.append(wishlist_item)

    print(items_below_threshold)


def parse_wishlist(session, wishlist_url):
    wishlist = []
    page = request_page(session, wishlist_url)

    wishlist_domain = urlparse(wishlist_url).netloc
    parse_wishlist_page(session, wishlist, page)

    return wishlist


def request_page(session, wishlist_url):
    response = session.get(wishlist_url, timeout=20)
    response.raise_for_status()
    check_successful_request(response)
    print(f"Successfully requested page: {wishlist_url}")
    return response


def check_successful_request(response):
    soup = bs4.BeautifulSoup(response.text, features="html.parser")
    items = soup.find_all("p", attrs={"class": "a-last"})
    if items:
        spam_el_text = items[0].text
        if spam_el_text.startswith("Sorry, we just need to make sure you're not a robot."):
            raise PageRequestError(f"Caught by bot check. URL: {response.url}")


def parse_wishlist_page(session, wishlist, page):
    soup = bs4.BeautifulSoup(page.text, features="html.parser")
    wishlist_item_els = soup.find_all("li", attrs={"class": "a-spacing-none g-item-sortable"})

    if wishlist_item_els:
        for wishlist_item_el in wishlist_item_els:
            try:
                title = wishlist_item_el.find("a", attrs={"class": "a-link-normal"})["title"]

                # Out of stock items marked with negative infinity price
                price = wishlist_item_el["data-price"]
                if price == "-Infinity":
                    continue
                href = wishlist_item_el.find("a", attrs={"class": "a-link-normal"})["href"]
                url = build_wishlist_url(href)

                wishlist.append(
                    WishlistItem(
                        title=title,
                        url=url,
                    )
                )
            except (KeyError, TypeError):
                print("Couldn't parse wishlist item; may not be available.")

        # Check for pagination / next page of wishlist.
        see_more_el = soup.find(
            "a",
            attrs={"class": "a-size-base a-link-nav-icon " "a-js g-visible-no-js wl-see-more"},
        )
        if see_more_el:
            # Pace request rate to avoid bot detection
            delay()
            href = see_more_el["href"]
            url = build_wishlist_url(href)
            page = request_page(session, url)
            parse_wishlist_page(session, wishlist, page)
        else:
            # No more pages to wishlist.
            print("Success parsing wishlist.")
    else:
        # Pagination led to page without any items or wishlist was empty.
        print(f"End of wishlist or wrong URL? No items found on page {page.url}.")


def delay():
    time.sleep(random.randint(DELAY_MIN, DELAY_MAX) / 1000.0)


def build_wishlist_url(href):
    return f"https://{WISHLIST_DOMAIN}{href}"


def find_item_price_from_format_selection_box_prime(element):
    price_element = element.find_all("span", attrs={"class": "a-size-base a-color-price a-color-price"})
    if len(price_element) != 1:
        return

    price = float(price_element[0].attrs["aria-label"].lstrip("£"))
    return price


def find_item_price_from_format_selection_box_no_prime(element):
    price_element = element.find_all("span", attrs={"class": "a-color-base"})
    if len(price_element) != 1:
        return

    price = float(price_element[0].text.split("£")[1].rstrip())
    return price


def find_item_price(response):
    soup = bs4.BeautifulSoup(response.text, features="html.parser")

    find_strategies = [
        find_item_price_from_other_sellers_on_amazon_box,
        find_item_price_from_format_selection_box,
    ]

    price = find_item_price_in_element(soup, find_strategies)

    if price is not None:
        return price

    raise PriceNotFoundError(response.url)


def find_item_price_from_other_sellers_on_amazon_box(soup):
    elements = soup.find_all("div", attrs={"class": "a-section a-spacing-none daodi-content"})
    if len(elements) != 1:
        return

    element = elements[0]
    price_el = element.find("span", attrs={"class": "a-offscreen"})

    # Case if just on prime and so delivery is free
    if not price_el:
        base_price = float(wishlist_item["price"].lstrip("£"))
        delivery_price = 0
    else:
        base_price = float(price_el.text.lstrip("£"))
        delivery_el = element.find("span", attrs={"class": "a-color-secondary a-size-base"})
        delivery_price = delivery_el.text if delivery_el else "+ £0 delivery"
        delivery_price = float(delivery_price.lstrip("+ £").rstrip(" delivery"))

    full_price = base_price + delivery_price
    return full_price


def find_item_price_from_format_selection_box(soup):
    format_selection_box_el = soup.find_all(
        "span", attrs={"class": "a-button a-button-selected a-spacing-mini a-button-toggle format"}
    )
    if len(format_selection_box_el) != 1:
        return

    format_selection_box_find_strategies = [
        find_item_price_from_format_selection_box_prime,
        find_item_price_from_format_selection_box_no_prime,
    ]
    return find_item_price_in_element(format_selection_box_el[0], format_selection_box_find_strategies)


def find_item_price_in_element(element, find_strategies):
    for price_finder_strategy in find_strategies:
        price = price_finder_strategy(element)
        if price is not None:
            return price


def run_test_cases(session):
    print("\nRunning test cases")
    STRATEGY_TEST_CASES = [
        # Sob's Air Guitar -> only prime
        "https://www.amazon.co.uk/dp/B0C91YY6XD",
        # Sadurn's Radiator -> only non-prime new
        "https://www.amazon.co.uk/dp/B09RMBJHV5",
        # Ohtis' Curve of Earth -> non-prime new and used
        "https://www.amazon.co.uk/dp/B07M7ZXD8B",
        # Nina Simone's Black Gold
        "https://www.amazon.co.uk/dp/B00499SA0U",
        # Explosions in the sky -> default case
        "https://www.amazon.co.uk/dp/B0CKS4WQV7",
    ]
    for test_case in STRATEGY_TEST_CASES:
        delay()
        response = request_page(session, test_case)
        price = find_item_price(response)


if __name__ == "__main__":
    session = start_session()
    # run_test_cases(session)
    run_wishlist_scraper(session)
