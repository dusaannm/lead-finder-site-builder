def _trade_key(category):
    return (category or "").strip().lower().replace(" ", "_").replace("-", "_")


def _base_price(category, options):
    key = _trade_key(category)
    prices = options["by_trade"]
    if key in prices:
        return prices[key]
    match = next((price for trade, price in prices.items() if trade in key), None)
    return options["default"] if match is None else match


def _review_count(lead):
    try:
        return int(float(str(lead.get("review_count") or 0)))
    except ValueError:
        return 0


def quote(lead, trade, options):
    price = _base_price(lead.get("category") or trade, options)
    reviews = _review_count(lead)
    for bonus in options["review_bonus"]:
        if reviews >= bonus["reviews"]:
            price += bonus["amount"]
    price = max(options["floor"], min(options["ceiling"], price))
    return int(round(price / options["step"]) * options["step"])
