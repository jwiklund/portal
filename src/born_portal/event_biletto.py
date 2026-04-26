import json
from html.parser import HTMLParser

from born_portal.model import EventData


def parse(html: str) -> EventData:
    p = _Parser()
    p.feed(html)
    return p.result()


class _Parser(HTMLParser):
    def __init__(self):
        super().__init__()
        self._name = ""
        self._description = ""
        self._price = None
        self._date = None
        self._location = None
        self._ld = None
        self._header = None
        self._description_div = None

    def handle_starttag(self, tag, attrs):
        if tag == "script" and dict(attrs).get("type") == "application/ld+json":
            self._ld = []
        if tag == "h2":
            self._header = []

    def handle_data(self, data):
        if self._ld is not None:
            self._ld.append(data)
        if self._header is not None:
            self._header.append(data)
        if self._description_div is not None:
            self._description_div.append(data)

    def handle_endtag(self, tag):
        if self._ld is not None:
            self.parse_ld("".join(self._ld))
            self._ld = None
        if tag == "h2":
            if "".join(self._header) == "Beskrivning":
                self._description_div = []
                self._header = None
        if tag == "div":
            if self._description_div is not None:
                self._description = "\n".join(self._description_div).strip()
            self._description_div = None

    def parse_ld(self, ld_str: str):
        ld = json.loads(ld_str)
        if ld["@type"] != "Event":
            return
        self._name = ld["name"]
        self._location = (
            ld["location"]["address"]["streetAddress"]
            + " "
            + ld["location"]["address"]["addressRegion"]
        )
        self._date = ld["startDate"]
        offers = [
            offer
            for offer in ld["offers"]
            if offer["availability"] == "http://schema.org/InStock"
        ]
        if not offers:
            offers = ld["offers"]
        self._price = offers[0]["price"] + offers[0]["priceCurrency"]

    def result(self) -> EventData:
        return EventData(
            name=self._name,
            description=self._description,
            location=self._location,
            price=self._price,
            date=self._date,
        )
